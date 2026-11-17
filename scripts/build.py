#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pinned Buildroot entry point. Builds run as the invoking user."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
LOCK = json.loads((ROOT / 'sources.lock.json').read_text())
CACHE = ROOT / '.cache'
SOURCE = CACHE / ('buildroot-' + LOCK['buildroot']['version'])
PROFILES = {'baseline': 'qemu_riscv64_defconfig',
            'linux-7.3.5': 'qemu_riscv64_linux_7_3_5_defconfig',
            'd213ecv-demo128-nand': 'd213ecv_demo128_nand_defconfig',
            'd213ecv-demo128-nand-linux618': 'd213ecv_demo128_nand_linux618_defconfig'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch():
    CACHE.mkdir(exist_ok=True)
    pin = LOCK['buildroot']
    archive = CACHE / ('buildroot-' + pin['version'] + '.tar.xz')
    if not archive.exists() or digest(archive) != pin['sha256']:
        tmp = archive.with_suffix('.part')
        print('Fetching pinned Buildroot', flush=True)
        with urllib.request.urlopen(pin['url'], timeout=60) as response, tmp.open('wb') as out:
            shutil.copyfileobj(response, out)
        if digest(tmp) != pin['sha256']:
            tmp.unlink()
            raise RuntimeError('Buildroot archive SHA256 mismatch')
        tmp.replace(archive)
    marker = SOURCE / '.artinchip-source-sha256'
    if marker.exists():
        if marker.read_text().strip() != pin['sha256']:
            raise RuntimeError('Source provenance changed; remove .cache and retry')
        return
    if SOURCE.exists():
        raise RuntimeError('Unmanaged source tree; remove it before fetching')
    # Buildroot contains intentional absolute symlinks in target skeletons.
    # Only extract the SHA256-pinned upstream archive, into a staging directory.
    with tempfile.TemporaryDirectory(dir=CACHE, prefix='extract-') as staging:
        with tarfile.open(archive) as tar:
            tar.extractall(staging, filter='tar')
        (Path(staging) / SOURCE.name).rename(SOURCE)
    marker.write_text(pin['sha256'] + '\n')


def jobs():
    available = 2 * 1024 * 1024
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            available = int(line.split()[1])
    automatic = max(1, min(8, os.cpu_count() or 1, available // (1536 * 1024)))
    requested = int(os.environ.get('JOBS', automatic))
    if not 1 <= requested <= 8:
        raise RuntimeError('JOBS must be between 1 and 8')
    return requested


def make(output, *targets):
    env = os.environ.copy()
    env.update(LC_ALL='C', TZ='UTC', SOURCE_DATE_EPOCH=str(LOCK['source_date_epoch']))
    count = jobs()
    print(f"Buildroot: jobs={count}, targets={','.join(targets)}", flush=True)
    cmd = ['make', '-C', str(SOURCE), f'O={output}', f'BR2_EXTERNAL={ROOT}',
           f"BR2_DL_DIR={CACHE / 'dl'}", f'BR2_JLEVEL={count}', *targets]
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'build.log').open('a') as log:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in iter(proc.stdout.readline, b''):
            text = line.decode(errors='replace')
            sys.stdout.write(text)
            log.write(text)
        if proc.wait():
            raise RuntimeError(f'Buildroot failed; see output/{output.name}/build.log')


def config_values(path):
    result = {}
    for line in path.read_text().splitlines():
        if line.startswith('BR2_') and '=' in line:
            k, v = line.split('=', 1)
            result[k] = v.strip('"')
    return result


def export_text(source, dest):
    text = source.read_text(errors='replace')
    text = text.replace(str(ROOT), '<PROJECT_ROOT>').replace(str(Path.home()), '<USER_HOME>')
    dest.write_text(text)


def artifacts(output, profile):
    dest = ROOT / 'artifacts' / profile
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    board = profile.startswith('d213ecv-demo128-nand')
    images = ('rootfs.ubifs', 'rootfs.ubi', 'rootfs.tar') if board else ('Image', 'fw_jump.bin', 'rootfs.ext2')
    kernel = not board or profile.endswith('-linux618')
    if board and kernel:
        images += ('Image.gz', 'd213ecv-demo128-nand.dtb')
    for name in images:
        shutil.copy2(output / 'images' / name, dest / name)
    export_text(output / '.config', dest / 'buildroot.config')
    patterns = [('busybox-*/.config', 'busybox.config')]
    if kernel:
        patterns.append(('linux-*/.config', 'linux.config'))
    for pattern, name in patterns:
        matches = list((output / 'build').glob(pattern))
        if len(matches) != 1:
            raise RuntimeError(f'Expected exactly one {name}; clean stale output')
        export_text(matches[0], dest / name)
    for name in ('build.log', 'smoke.log', 'smoke-result.json'):
        if (output / name).exists():
            export_text(output / name, dest / name)
    cfg = config_values(output / '.config')
    version_keys = ('BR2_LINUX_KERNEL_CUSTOM_VERSION_VALUE', 'BR2_TARGET_OPENSBI_CUSTOM_VERSION_VALUE',
                    'BR2_GCC_VERSION', 'BR2_BINUTILS_VERSION', 'BR2_BUSYBOX_VERSION')
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True))
    qemu = subprocess.check_output(['qemu-system-riscv64', '--version'], text=True).splitlines()[0]
    packages = sorted(p.name for p in (output / 'build').iterdir()
                      if p.is_dir() and (p / '.stamp_built').exists())
    manifest = {'project_commit': commit, 'working_tree_dirty': dirty, 'profile': profile,
                'sources': LOCK, 'config_versions': {k: cfg[k] for k in version_keys if k in cfg},
                'built_packages': packages, 'qemu': qemu,
                'sha256': {p.name: digest(p) for p in sorted(dest.iterdir()) if p.is_file()}}
    if board:
        manifest['vendor_sources'] = json.loads((ROOT / 'board/artinchip/d213ecv-demo128-nand/vendor-sources.json').read_text())
        manifest['hardware_boot'] = 'not_verified'
        if kernel:
            release = next((output / 'build').glob('linux-*/include/config/kernel.release'))
            manifest['kernel_release'] = release.read_text().strip()
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (dest / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in sorted(dest.iterdir()) if p.is_file()))
    print(f'Artifacts: artifacts/{profile}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('fetch', 'configure', 'build', 'clean', 'distclean', 'artifacts', 'run', 'test'))
    parser.add_argument('profile', nargs='?', default='baseline', choices=PROFILES)
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('Run as an ordinary user; root builds are unsupported')
    output = ROOT / 'output' / args.profile
    if args.command == 'distclean':
        if output.exists():
            shutil.rmtree(output)
        return
    if args.command in ('fetch', 'configure', 'build'):
        fetch()
    if args.command == 'fetch':
        return
    if args.command == 'configure' or (args.command == 'build' and not (output / '.config').exists()):
        make(output, PROFILES[args.profile])
    if args.command == 'build':
        make(output, 'all')
    elif args.command == 'clean':
        if (output / '.config').exists():
            make(output, 'clean')
    elif args.command == 'artifacts':
        artifacts(output, args.profile)
    elif args.command in ('run', 'test'):
        if args.profile.startswith('d213ecv-demo128-nand'):
            raise RuntimeError('This is a physical-board rootfs profile; QEMU cannot validate board hardware')
        subprocess.run([sys.executable, str(ROOT / 'scripts/qemu.py'), args.command, args.profile], check=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))

#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build isolated D213ECV SD/RAM FIT comparisons; never flash NAND."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from boot_contract import check_config, check_dtb
from firmware import sha256, require
from riscv_image import parse_image

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / 'board/artinchip/d213ecv-demo128-nand'
PIN = json.loads((BOARD / 'vendor-sources.json').read_text())['kernel_reference']['commit']
BASE = ROOT / 'output/d213ecv-demo128-nand-linux618'


def run(*args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)


def diagnostic_build():
    archive = ROOT / '.cache/vendor' / f'linux-{PIN}.tar.gz'
    expected = (BOARD / 'hashes/linux/linux.hash').read_text().splitlines()[-1].split()[1]
    require(sha256(archive) == expected, 'Pinned kernel archive hash mismatch')
    dest = ROOT / 'output/m2-diagnostic'
    # Rebuild from exported, checked sources each time; no cache-only edits.
    if dest.exists():
        shutil.rmtree(dest)
    source = dest / f'linux-{PIN}'
    dest.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter='data')
    for patch in [*sorted((BOARD / 'hashes/linux').glob('*.patch')),
                  *sorted((BOARD / 'debug-patches').glob('*.patch'))]:
        with patch.open('rb') as stream:
            run('patch', '-p1', '--batch', '--forward', cwd=source, stdin=stream)
    shutil.copytree(BOARD / 'dts', source / 'arch/riscv/boot/dts', dirs_exist_ok=True)
    build = dest / 'build'
    build.mkdir()
    shutil.copyfile(BASE / 'build/linux-custom/.config', build / '.config')
    for name in ('D213ECV_EARLY_DEBUG', 'RISCV_SBI_V01'):
        run(source / 'scripts/config', '--file', build / '.config', '--enable', name)
    # Check the committed fragment is exactly the set of intended toggles.
    fragment = (BOARD / 'linux-ram-debug.fragment').read_text()
    require([x for x in fragment.splitlines() if x.startswith('CONFIG_')] ==
            ['CONFIG_D213ECV_EARLY_DEBUG=y', 'CONFIG_RISCV_SBI_V01=y'], 'Debug fragment changed; update builder')
    env = os.environ.copy()
    env.update(PATH=str(BASE / 'host/bin') + os.pathsep + env['PATH'],
               PKG_CONFIG_LIBDIR=str(BASE / 'host/lib/pkgconfig'),
               HOSTPKG_CONFIG=str(BASE / 'host/bin/pkgconf'),
               PKG_CONFIG_SYSROOT_DIR='/',
               LD_LIBRARY_PATH=str(BASE / 'host/lib'),
               ARCH='riscv', CROSS_COMPILE=str(BASE / 'host/bin/riscv64-linux-'),
               KBUILD_BUILD_USER='builder', KBUILD_BUILD_HOST='artinchip-linux',
               KBUILD_BUILD_TIMESTAMP='Thu Jan 1 00:00:00 UTC 2026', KBUILD_BUILD_VERSION='1')
    jobs = int(os.environ.get('JOBS', '6'))
    require(1 <= jobs <= 8, 'JOBS must be between 1 and 8')
    command = ['make', '-C', source, f'O={build}',
               'HOSTPKG_CONFIG=' + str(BASE / 'host/bin/pkgconf') +
               ' --keep-system-cflags --keep-system-libs']
    run(*command, 'olddefconfig', env=env)
    check_config(build / '.config', diagnostic=True)
    run(*command, f'-j{jobs}', 'Image.gz', 'dtbs', env=env)
    return build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic', action='store_true', help='Also build isolated opt-in UART-marker kernel')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/d213ecv-linux618-ram-debug')
    args = parser.parse_args()
    require(os.geteuid() != 0, 'Do not build as root')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # No inherited evidence from an older invocation.
    require(not any(out.iterdir()), 'Use an empty output directory to avoid mixing builds')
    base = BASE / 'build/linux-custom'
    os.environ['PATH'] = str(BASE / 'host/bin') + os.pathsep + os.environ['PATH']
    env = os.environ.copy()
    records = {}
    variants = [('baseline-40000000', base, 0x40000000, False),
                ('offset-40200000', base, 0x40200000, False)]
    if args.diagnostic:
        variants.append(('diagnostic-40200000', diagnostic_build(), 0x40200000, True))
    for name, build, load, debug in variants:
        dtb = build / 'arch/riscv/boot/dts/artinchip/d213ecv-demo128-nand.dtb'
        kernel = build / 'arch/riscv/boot/Image.gz'
        config = check_config(build / '.config', diagnostic=debug)
        dtb_contract = check_dtb(dtb)
        run(sys.executable, ROOT / 'scripts/make-kernel-fit.py', '--kernel', kernel,
            '--dtb', dtb, '--opensbi', ROOT / '.cache/vendor-boot/components/fw_dynamic.bin',
            '--load', hex(load), '--entry', hex(load), '--output', out / (name + '.itb'), env=env)
        shutil.copyfile(build / '.config', out / (name + '.config'))
        readelf = BASE / 'host/bin/riscv64-linux-readelf'
        elf = subprocess.check_output([str(readelf), '-h', '-l', str(build / 'vmlinux')], text=True)
        (out / (name + '-elf.txt')).write_text(elf)
        records[name] = {'config_check': config, 'dtb_check': dtb_contract,
                         'input_sha256': {p: sha256(build / p) for p in
                                          ['.config', 'vmlinux', 'arch/riscv/boot/Image.gz']},
                         'dtb_sha256': sha256(dtb),
                         'image_header': parse_image((build / 'arch/riscv/boot/Image').read_bytes())}
    tracked = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard',
                                      'scripts', 'tests', 'board', 'configs', 'docs/m2-early-boot-debug.md', '.github/workflows/board.yml'],
                                     cwd=ROOT, text=True).splitlines()
    manifest = {'project_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
                'kernel_reference_commit': PIN, 'buildroot': json.loads((ROOT / 'sources.lock.json').read_text())['buildroot'],
                'source_sha256': {p: sha256(ROOT / p) for p in tracked if (ROOT / p).is_file()},
                'opensbi_sha256': sha256(ROOT / '.cache/vendor-boot/components/fw_dynamic.bin'),
                'variants': records, 'hardware_boot': 'not_verified',
                'baseline_inputs': 'existing Buildroot output; content hashes above identify actual intermediates',
                'm1_hardware_evidence': 'operator reports Linux 5.10.44 + Buildroot UBIFS shell and reboot persistence passed'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copyfile(ROOT / 'docs/m2-early-boot-debug.md', out / 'TEST-INSTRUCTIONS.md')
    (out / 'SHA256SUMS').write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(out.iterdir()) if p.is_file()))
    print('SD/RAM debug bundle ready. No hardware boot result is asserted.')


if __name__ == '__main__':
    main()

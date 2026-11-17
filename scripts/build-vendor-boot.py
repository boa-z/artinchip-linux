#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the pinned vendor boot components directly, outside Luban's build system."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / 'board/artinchip/d213ecv-demo128-nand'
PIN = json.loads((BOARD / 'vendor-sources.json').read_text())
WORK = ROOT / '.cache/vendor-boot'


def run(cmd, env=None):
    subprocess.run([str(c) for c in cmd], env=env, check=True)


def blob(repo, source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        dest.unlink()
    dest.write_bytes(subprocess.check_output(['git', '-C', str(repo), 'show', PIN['commit'] + ':' + source]))


def export(repo, subtree, dest):
    marker = dest / '.source-pin'
    if marker.exists():
        if marker.read_text().strip() != PIN['commit']:
            sys.exit('Cached vendor source pin changed; clean .cache/vendor-boot first')
        return
    if dest.exists():
        sys.exit('Incomplete vendor export; clean .cache/vendor-boot first')
    dest.mkdir(parents=True)
    proc = subprocess.Popen(['git', '-C', str(repo), 'archive', PIN['commit'] + ':' + subtree], stdout=subprocess.PIPE)
    with tarfile.open(fileobj=proc.stdout, mode='r|') as archive:
        archive.extractall(dest, filter='tar')
    proc.stdout.close()
    if proc.wait():
        sys.exit('Source export failed')
    marker.write_text(PIN['commit'] + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True, help='Existing Luban Git checkout (source import only)')
    parser.add_argument('--host', type=Path, required=True, help='Built board profile host directory')
    args = parser.parse_args()
    if os.geteuid() == 0:
        sys.exit('Build as an ordinary user')
    host = args.host.resolve()
    cross = host / 'bin/riscv64-linux-'
    if not Path(str(cross) + 'gcc').exists():
        sys.exit('Build the board rootfs/toolchain before boot components')
    WORK.mkdir(parents=True, exist_ok=True)
    ub = WORK / 'uboot-src'
    sbi = WORK / 'opensbi-src'
    export(args.reference, 'source/uboot-2021.10', ub)
    export(args.reference, 'source/opensbi', sbi)
    names = subprocess.check_output(['git', '-C', str(args.reference), 'ls-tree', '--name-only',
                                    PIN['commit'] + ':target/d211/common'], text=True).splitlines()
    for name in names:
        if name.endswith('.dtsi'):
            blob(args.reference, 'target/d211/common/' + name, ub / 'arch/riscv/dts' / name)
    blob(args.reference, 'target/d211/demo128_nand/board.dts', ub / 'arch/riscv/dts/artinchip-board.dts')
    blob(args.reference, 'target/d211/demo128_nand/image_cfg.json', ub / 'include/configs/image_cfg.json')
    # The SDK normally links these headers from Linux into U-Boot. Import only
    # the pinned headers instead, keeping the exported boot source independent.
    for category in ('clock', 'reset', 'display'):
        directory = 'source/linux-5.10/include/dt-bindings/' + category
        headers = subprocess.check_output(['git', '-C', str(args.reference), 'ls-tree', '--name-only',
                                           PIN['commit'] + ':' + directory], text=True).splitlines()
        for name in headers:
            if name.startswith('artinchip') and name.endswith('.h'):
                blob(args.reference, directory + '/' + name, ub / 'include/dt-bindings' / category / name)
    env = os.environ.copy()
    env.update(PATH=str(host / 'bin') + ':' + env['PATH'], LC_ALL='C', TZ='UTC',
               SOURCE_DATE_EPOCH='1767225600', KBUILD_BUILD_USER='buildroot', KBUILD_BUILD_HOST='buildroot',
               PKG_CONFIG_PATH=str(host / 'lib/pkgconfig'))
    jobs = min(4, max(1, int(os.environ.get('JOBS', '2'))))
    out = WORK / 'uboot-build'
    common = ['make', '-C', ub, 'O=' + str(out), 'ARCH=riscv', 'CROSS_COMPILE=' + str(cross),
              'HOSTCFLAGS=-O2 -I' + str(host / 'include'), 'HOSTLDFLAGS=-L' + str(host / 'lib')]
    if not (out / '.config').exists():
        run(common + ['d211_demo128_nand_defconfig'], env)
    run(common + [f'-j{jobs}', 'all'], env)
    sbi_out = WORK / 'opensbi-build'
    run(['make', '-C', sbi, 'O=' + str(sbi_out), 'CROSS_COMPILE=' + str(cross), 'PLATFORM=generic',
         'CHIP=ARCH_ARTINCHIP', 'FW_TEXT_START=0x47FE0000',
         'PLATFORM_RISCV_ISA=rv64imafdc_zicsr_zifencei', f'-j{jobs}'], env)
    assets = WORK / 'components'
    assets.mkdir(exist_ok=True)
    for source, name in ((out / 'u-boot.dtb', 'u-boot.dtb'), (out / 'u-boot-nodtb.bin', 'u-boot-nodtb.bin'),
                         (out / 'spl/u-boot-spl-dtb.bin', 'u-boot-spl-dtb.bin'),
                         (out / 'u-boot.its', 'u-boot.its'),
                         (sbi_out / 'platform/generic/firmware/fw_dynamic.bin', 'fw_dynamic.bin')):
        shutil.copyfile(source, assets / name)
    for source, name in (('target/d211/common/d211.pbp', 'd211.pbp'),
                         ('target/d211/demo128_nand/ddr_init.json', 'ddr_init.json'),
                         ('target/d211/common/env.txt', 'env.txt'),
                         ('target/d211/common/logo.its', 'logo.its'),
                         ('tools/scripts/mk_private_resource.py', 'mk_private_resource.py')):
        blob(args.reference, source, assets / name)
    logo_files = subprocess.check_output(['git', '-C', str(args.reference), 'ls-tree', '--name-only',
                                         PIN['commit'] + ':target/d211/demo128_nand/logo'], text=True).splitlines()
    for name in logo_files:
        blob(args.reference, 'target/d211/demo128_nand/logo/' + name, assets / 'logo' / name)
    run([sys.executable, assets / 'mk_private_resource.py', '-c', assets / 'ddr_init.json', '-o', assets / 'ddr_init.bin'], env)
    # Parse the original JSON-with-comments using the vendor's existing parser.
    sys.path.insert(0, str(ROOT / 'tools/vendor/aic'))
    import mk_image
    cfg = mk_image.parse_image_cfg(ub / 'include/configs/image_cfg.json')
    cfg['pre-process']['itb'] = {n: v for n, v in cfg['pre-process']['itb'].items()
                                 if n in ('u-boot.itb', 'logo.itb')}
    config = assets / 'boot-image-config.json'
    config.write_text(json.dumps(cfg, indent=2) + '\n')
    run([sys.executable, ROOT / 'tools/vendor/aic/mk_image.py', '-p', '-c', config, '-d', assets], env)
    files = ('usbupg-ddr-init.aic', 'env.bin', 'u-boot.itb', 'logo.itb', 'u-boot-spl-dtb.aic', 'fw_dynamic.bin')
    manifest = {'board': 'D213ECV-DEMO-V4-0', 'source_revision': PIN['commit'],
                'uboot': '2021.10 vendor', 'opensbi': 'vendor source snapshot',
                'hardware_boot': 'not_verified',
                'boot_resource_license': 'PBP/DDR resources have no per-file license statement; local evaluation',
                'sha256': {n: hashlib.sha256((assets / n).read_bytes()).hexdigest() for n in files}}
    (assets / 'components.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Boot components built in .cache/vendor-boot/components; hardware boot not verified.')


if __name__ == '__main__':
    main()

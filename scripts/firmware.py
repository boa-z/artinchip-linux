#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate and package recovery-preserving D213ECV NAND updates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / 'board/artinchip/d213ecv-demo128-nand'
LAYOUT = json.loads((BOARD / 'layout.json').read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def partitions(layout=LAYOUT):
    offset = 0
    result = {}
    for part in layout['partitions']:
        name, size = part['name'], part['size']
        require(name not in result and size > 0, 'Duplicate or empty partition')
        require(offset % layout['eraseblock_size'] == size % layout['eraseblock_size'] == 0,
                'Partition is not eraseblock-aligned')
        result[name] = dict(part, offset=offset)
        offset += size
    require(offset == layout['size'], 'Partition layout does not fill the NAND')
    require(result['recovery']['offset'] == 0x1000000 and result['recovery']['size'] == 0x1000000,
            'Factory recovery region changed')
    require(result['ubiroot']['offset'] == 0x2000000, 'Factory rootfs offset changed')
    return result


def check_rootfs(path):
    size = path.stat().st_size
    with path.open('rb') as f:
        sb = f.read(4096)
    require(len(sb) == 4096 and struct.unpack_from('<I', sb)[0] == 0x06101831,
            'Not a UBIFS image')
    minimum, leb, count, maximum = struct.unpack_from('<IIII', sb, 32)
    fmt = struct.unpack_from('<I', sb, 80)[0]
    compression = struct.unpack_from('<H', sb, 84)[0]
    ro_compat = struct.unpack_from('<I', sb, 124)[0]
    require((minimum, leb) == (LAYOUT['page_size'], LAYOUT['leb_size']), 'Wrong NAND geometry')
    require(0 < count <= maximum <= LAYOUT['max_leb_count'], 'UBIFS exceeds reserved LEB budget')
    require(size <= maximum * leb and size % leb == 0, 'Invalid UBIFS capacity/alignment')
    require(fmt <= 5 and ro_compat == 0 and compression == 2,
            'UBIFS format/compression is outside the Linux 5.10 compatibility contract')
    return {'bytes': size, 'min_io': minimum, 'leb_size': leb, 'leb_count': count,
            'max_leb_count': maximum, 'format': fmt, 'compression': 'zlib', 'sha256': sha256(path),
            'linux_5_10_static_contract': 'passed', 'hardware_mount': 'not_verified'}


def fdtget(path, node, prop, kind='s'):
    return subprocess.check_output(['fdtget', '-t', kind, str(path), node, prop], text=True).strip()


def check_fit(path, require_hashes=False):
    require(path.stat().st_size <= partitions()['kernel']['size'], 'FIT exceeds kernel partition')
    listing = subprocess.check_output(['dumpimage', '-l', str(path)], text=True)
    require('FIT description:' in listing, 'Not a recognized FIT')
    names = subprocess.check_output(['fdtget', '-l', str(path), '/images'], text=True).split()
    default = fdtget(path, '/configurations', 'default')
    conf = '/configurations/' + default
    properties = subprocess.check_output(['fdtget', '-p', str(path), conf], text=True).split()
    for prop in ('kernel', 'firmware', 'fdt', 'loadables'):
        if prop in properties:
            require(all(n in names for n in fdtget(path, conf, prop).split()), 'Broken FIT image reference')
    records = []
    kernel_contract = None
    board_contract = None
    with tempfile.TemporaryDirectory() as tmp:
        for index, name in enumerate(names):
            node = '/images/' + name
            kind = fdtget(path, node, 'type')
            if kind == 'kernel':
                require('kernel' in properties and 'fdt' in properties, 'Kernel FIT requires kernel and FDT references')
            if kind in ('kernel', 'firmware', 'standalone'):
                require(fdtget(path, node, 'arch') == 'riscv', 'FIT payload architecture mismatch')
            payload = Path(tmp) / 'payload'
            subprocess.run(['dumpimage', '-T', 'flat_dt', '-p', str(index), '-o', str(payload), str(path)],
                           check=True, stdout=subprocess.DEVNULL)
            children = subprocess.check_output(['fdtget', '-l', str(path), node], text=True).split()
            hashes = [n for n in children if n.startswith('hash')]
            require(not require_hashes or hashes, 'Generated FIT payload lacks a hash')
            for child in hashes:
                algo = fdtget(path, node + '/' + child, 'algo')
                require(algo in ('sha256', 'sha1', 'crc32'), 'Unsupported FIT hash algorithm')
                value = bytes(int(x, 16) for x in fdtget(path, node + '/' + child, 'value', 'bx').split())
                data = payload.read_bytes()
                actual = (struct.pack('>I', zlib.crc32(data)) if algo == 'crc32'
                          else hashlib.new(algo, data).digest())
                require(actual == value, 'FIT payload hash mismatch')
            records.append({'name': name, 'type': kind, 'hashes': len(hashes), 'sha256': sha256(payload)})
            if kind == 'kernel' and fdtget(path, node, 'arch') == 'riscv':
                import gzip
                from riscv_image import parse_image
                compression = fdtget(path, node, 'compression')
                require(compression in ('gzip', 'none'), 'Unsupported kernel compression')
                raw = gzip.decompress(payload.read_bytes()) if compression == 'gzip' else payload.read_bytes()
                release = re.search(rb'Linux version ([0-9][^ \x00]{0,63}) \(', raw)
                if release:
                    records[-1]['release'] = release[1].decode('ascii')
                kernel_contract = (parse_image(raw), int(fdtget(path, node, 'load', 'x'), 16),
                                   int(fdtget(path, node, 'entry', 'x'), 16))
            if kind == 'flat_dt' and 'kernel' in properties:
                from boot_contract import check_dtb
                board_contract = check_dtb(payload)
    if kernel_contract:
        from riscv_image import check_layout
        require(board_contract is not None, 'Missing board DTB contract')
        header, load, entry = kernel_contract
        check_layout(header, load, entry, path.stat().st_size, baseline=load == 0x40000000,
                     extra_reserved=board_contract['reserved'])
    return {'default_configuration': default, 'images': records,
            'legacy_without_hashes': any(r['hashes'] == 0 for r in records)}


def check_env(path):
    data = path.read_bytes()
    require(len(data) == 0x4000, 'Expected factory 16 KiB redundant U-Boot environment')
    require(zlib.crc32(data[5:]) == struct.unpack_from('<I', data)[0], 'U-Boot environment CRC mismatch')
    values = {}
    for item in data[5:].split(b'\0'):
        if b'=' in item:
            k, v = item.split(b'=', 1)
            values[k.decode()] = v.decode()
    entries = values.get('MTD', '').split(':', 1)
    require(len(entries) == 2 and entries[0] == 'spi0.0', 'Wrong MTD controller in updater environment')
    parsed = []
    offset = 0
    for entry in entries[1].split(','):
        m = re.fullmatch(r'(-|[0-9a-fA-Fx]+[kKmM]?)(?:@([0-9a-fA-Fx]+))?\(([^)]+)\)', entry)
        require(m is not None, 'Unsupported MTD partition syntax')
        size, explicit, name = m.groups()
        if explicit:
            require(int(explicit, 0) == offset, 'Unexpected partition offset')
        if size == '-':
            size = LAYOUT['size'] - offset
        elif size[-1:].lower() in ('k', 'm'):
            size = int(size[:-1], 0) * (1024 if size[-1].lower() == 'k' else 1024 ** 2)
        else:
            size = int(size, 0)
        parsed.append((name, size, offset))
        offset += size
    expected = [(n, p['size'], p['offset']) for n, p in partitions().items()]
    require(parsed == expected, 'Updater environment changes the factory partition layout')
    require(values.get('ubi_rootfs_mtd') == '10' and values.get('nand_root') == 'ubi0:rootfs',
            'Factory root mount contract changed')
    return {'crc': 'passed', 'partition_layout': 'factory', 'root_mtd': 10}


def verify_image(path, allow_system_update=False):
    data = path.read_bytes()
    require(len(data) >= 2048, 'Truncated firmware header')
    require(data[:8].rstrip(b'\0') == b'AIC.FW', 'Invalid AiBurn image magic')
    require(data[200:264].rstrip(b'\0') == b'spi-nand', 'Unexpected image media')
    start, length, file_start, file_length = struct.unpack_from('<IIII', data, 332)
    require(start == 2048 and length > 0 and length % 512 == 0 and file_start == start + length,
            'Invalid metadata layout')
    require(file_start + file_length == len(data), 'Truncated or extended firmware data')
    records = []
    allowed = {'image.target.rootfs': 'ubiroot:rootfs', 'image.target.kernel': 'kernel'}
    if allow_system_update:
        allowed.update({'image.target.spl': 'spl', 'image.target.uboot': 'uboot',
                        'image.target.env': 'env;env_r', 'image.target.logo': 'logo'})
    updaters = {'image.updater.' + n for n in ('ddr', 'env', 'uboot', 'logo', 'spl')}
    seen = set()
    for offset in range(start, start + length, 512):
        meta = data[offset:offset + 512]
        require(meta[:8].rstrip(b'\0') == b'META', 'Invalid component metadata')
        name = meta[8:72].split(b'\0')[0].decode()
        part = meta[72:136].split(b'\0')[0].decode()
        require(name not in seen, 'Duplicate component metadata')
        seen.add(name)
        require(name in allowed or name in updaters or name == 'image.info',
                'Unknown component metadata name')
        pos, size, crc = struct.unpack_from('<III', meta, 136)
        require(size > 0 and pos + size <= len(data), 'Invalid component bounds')
        if name == 'image.info':
            require(pos == 0 and size == 2048, 'Invalid image header reference')
        else:
            require(pos >= file_start, 'Component overlaps header/metadata')
        require(zlib.crc32(data[pos:pos + size]) == crc, 'Component CRC mismatch')
        if name in allowed:
            require(part == allowed[name], 'Update targets a protected or unknown partition')
            maximum = min(partitions()[n.split(':')[0]]['size'] for n in part.split(';'))
            require(size <= maximum, 'Component exceeds its NAND partition')
        else:
            require(part == '', 'RAM updater or header targets a NAND partition')
        records.append({'name': name, 'partition': part, 'bytes': size})
    require('image.target.rootfs' in seen, 'No rootfs update in firmware')
    if allow_system_update:
        require(set(allowed).issubset(seen), 'System update requires SPL, U-Boot, both environments, logo, kernel and rootfs')
    return {'components': records, 'recovery_targeted': False,
            'system_update': allow_system_update, 'sha256': sha256(path)}


def system_update_env(source, destination):
    """Derive a debuggable normal-U-Boot environment; preserve factory layout."""
    check_env(source)
    values = {}
    for item in source.read_bytes()[5:].split(b'\0'):
        if b'=' in item:
            key, value = item.split(b'=', 1)
            values[key.decode()] = value.decode()
    overrides = json.loads((BOARD / 'system-update-env.json').read_text())
    values.update(overrides)
    text = destination.with_suffix('.txt')
    text.write_text(''.join(f'{k}={v}\n' for k, v in sorted(values.items())))
    subprocess.run(['mkenvimage', '-r', '-s', '0x4000', '-o', str(destination), str(text)], check=True)
    result = check_env(destination)
    result.update(overrides=overrides, sha256=sha256(destination))
    return result


def pack(args):
    parts = partitions()
    system_update = getattr(args, 'system_update', False)
    require(not system_update or args.kernel, 'System update requires a kernel FIT')
    vendor510 = getattr(args, 'vendor_linux510', False)
    require(not vendor510 or system_update, 'Vendor Linux 5.10 requires a system update')
    pins = json.loads((BOARD / 'vendor-sources.json').read_text())
    components = args.components.resolve()
    provenance = json.loads((components / 'components.json').read_text())
    require(provenance['board'] == LAYOUT['board'], 'Components are for another board')
    require(provenance.get('source_revision'), 'Component source revision is required')
    rootfs = check_rootfs(args.rootfs)
    environment = check_env(components / 'env.bin')
    names = ['usbupg-ddr-init.aic', 'env.bin', 'u-boot.itb', 'logo.itb', 'u-boot-spl-dtb.aic']
    fits = {}
    for name in names:
        require(sha256(components / name) == provenance['sha256'][name], 'Component provenance hash mismatch')
        if name.endswith('.itb'):
            fits[name] = check_fit(components / name)
            partition = 'uboot' if name == 'u-boot.itb' else 'logo'
            require((components / name).stat().st_size <= parts[partition]['size'], 'Oversized boot component')
    if args.kernel:
        fits['kernel.itb'] = check_fit(args.kernel, require_hashes=True)
        if vendor510:
            releases = [r.get('release') for r in fits['kernel.itb']['images'] if r['type'] == 'kernel']
            require(releases == [pins['vendor_kernel']['release']], 'Expected the pinned vendor Linux release')
        if system_update:
            sbi = [r for r in fits['kernel.itb']['images'] if r['type'] == 'firmware']
            require(len(sbi) == 1 and sbi[0]['sha256'] == provenance['sha256']['fw_dynamic.bin'],
                    'Kernel FIT OpenSBI differs from bundled U-Boot firmware')
    args.output.mkdir(parents=True, exist_ok=True)
    require(not any(args.output.glob('*.img')), 'Use a fresh output directory for a new package')
    with tempfile.TemporaryDirectory(dir=args.output, prefix='staging-') as tmp:
        stage = Path(tmp)
        for name in names:
            shutil.copyfile(components / name, stage / name)
        if system_update:
            environment = system_update_env(components / 'env.bin', stage / 'env.bin')
        shutil.copyfile(args.rootfs, stage / 'rootfs_page_2k_block_128k.ubifs')
        target = {'rootfs': {'file': 'rootfs*.ubifs', 'attr': ['ubi', 'required'], 'part': ['ubiroot:rootfs']}}
        if args.kernel:
            shutil.copyfile(args.kernel, stage / 'kernel.itb')
            target['kernel'] = {'file': 'kernel.itb', 'attr': ['mtd', 'required'], 'part': ['kernel']}
        if system_update:
            for key, filename, targets in (
                    ('spl', 'u-boot-spl-dtb.aic', ['spl']),
                    ('uboot', 'u-boot.itb', ['uboot']),
                    ('env', 'env.bin', ['env', 'env_r']),
                    ('logo', 'logo.itb', ['logo'])):
                target[key] = {'file': filename, 'attr': ['mtd', 'required'], 'part': targets}
        cfg = {'spi-nand': {'size': '128m', 'partitions': {}}, 'image': {
            'info': {'platform': 'd211', 'product': 'demo128_nand', 'version': '1.0.0',
                     'media': {'type': 'spi-nand', 'device_id': 0,
                               'array_organization': [{'page': '2k', 'block': '128k'}]}},
            'updater': {}, 'target': target}}
        for name, p in parts.items():
            # The vendor parser accepts unit-suffixed or hexadecimal sizes.
            entry = {'size': hex(p['size'])}
            if 'volume' in p:
                entry['ubi'] = {p['volume']: {'size': '-'}}
            cfg['spi-nand']['partitions'][name] = entry
        for key, name, address, run in (
                ('ddr', names[0], '0x00103000', True), ('env', names[1], '0x41000000', False),
                ('uboot', names[2], '0x41100000', False), ('logo', names[3], '0x42400000', False),
                ('spl', names[4], '0x40000000', True)):
            cfg['image']['updater'][key] = {'file': name, 'ram': address,
                                          'attr': ['required', 'run'] if run else ['required']}
        (stage / 'image_cfg.json').write_text(json.dumps(cfg, indent=2) + '\n')
        subprocess.run([sys.executable, str(ROOT / 'tools/vendor/aic/mk_image.py'),
                        '-d', str(stage), '-c', str(stage / 'image_cfg.json'), '-o', str(stage)], check=True)
        images = list(stage.glob('*.img'))
        require(len(images) == 1, 'Vendor packer did not produce exactly one NAND image')
        result = verify_image(images[0], allow_system_update=system_update)
        filename = ('d213ecv-linux510-system-update.img' if vendor510 else
                    'd213ecv-linux618-system-update.img' if system_update else 'd213ecv-demo128-nand.img')
        final = args.output / filename
        shutil.copyfile(images[0], final)
        shutil.copyfile(stage / 'image_cfg.json', args.output / 'image_cfg.json')
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True))
    manifest = {'board': LAYOUT['board'], 'vendor_compatibility_name': LAYOUT['vendor_profile'],
                'project_commit': commit, 'working_tree_dirty': dirty,
                'image_kind': 'experimental-system-update' if system_update else 'selective-update',
                'boot_environment': environment,
                'kernel_policy': ('rebuilt_vendor_5_10' if vendor510 else
                                  'experimental_6_18' if args.kernel else 'retain_factory_5_10'),
                'buildroot_source': json.loads((ROOT / 'sources.lock.json').read_text())['buildroot'],
                'kernel_source': (pins['vendor_kernel'] if vendor510 else pins['kernel_reference']
                                  if args.kernel else 'existing factory NAND kernel; unchanged by this image'),
                'rootfs': rootfs, 'fits': fits, 'environment': environment, 'firmware': result,
                'component_provenance': provenance, 'packaging': 'passed',
                'hardware_boot': 'not_verified', 'recovery_policy': 'never targeted'}
    (args.output / 'firmware-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if system_update:
        guide = 'vendor-linux510.md' if vendor510 else 'system-update.md'
        shutil.copyfile(ROOT / 'docs' / guide, args.output / 'README.md')
    (args.output / 'SHA256SUMS').write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(args.output.iterdir())
                                                if p.is_file() and p.name != 'SHA256SUMS'))
    print('Packaging passed; hardware boot is NOT verified.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('layout')
    for name in ('rootfs', 'fit', 'verify'):
        p = sub.add_parser(name)
        p.add_argument('path', type=Path)
        if name == 'verify':
            p.add_argument('--system-update', action='store_true',
                           help='Explicitly verify the complete system-update target set')
    p = sub.add_parser('pack')
    p.add_argument('--components', type=Path, required=True)
    p.add_argument('--rootfs', type=Path, required=True)
    p.add_argument('--kernel', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--system-update', action='store_true',
                   help='Update SPL/U-Boot/env/logo/kernel/rootfs; preserve Recovery and device data')
    p.add_argument('--vendor-linux510', action='store_true',
                   help='Label and validate the rebuilt vendor Linux 5.10 system image')
    args = parser.parse_args()
    if args.command == 'pack':
        pack(args)
    else:
        fn = {'layout': partitions, 'rootfs': check_rootfs, 'fit': check_fit, 'verify': verify_image}[args.command]
        result = (fn() if args.command == 'layout' else
                  fn(args.path, allow_system_update=args.system_update) if args.command == 'verify' else
                  fn(args.path))
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))

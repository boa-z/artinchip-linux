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


def verify_image(path):
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
            maximum = partitions()[part.split(':')[0]]['size']
            require(size <= maximum, 'Component exceeds its NAND partition')
        else:
            require(part == '', 'RAM updater or header targets a NAND partition')
        records.append({'name': name, 'partition': part, 'bytes': size})
    require('image.target.rootfs' in seen, 'No rootfs update in firmware')
    return {'components': records, 'recovery_targeted': False, 'sha256': sha256(path)}


def pack(args):
    parts = partitions()
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
    args.output.mkdir(parents=True, exist_ok=True)
    require(not any(args.output.glob('*.img')), 'Use a fresh output directory for a new package')
    with tempfile.TemporaryDirectory(dir=args.output, prefix='staging-') as tmp:
        stage = Path(tmp)
        for name in names:
            shutil.copyfile(components / name, stage / name)
        shutil.copyfile(args.rootfs, stage / 'rootfs_page_2k_block_128k.ubifs')
        target = {'rootfs': {'file': 'rootfs*.ubifs', 'attr': ['ubi', 'required'], 'part': ['ubiroot:rootfs']}}
        if args.kernel:
            shutil.copyfile(args.kernel, stage / 'kernel.itb')
            target['kernel'] = {'file': 'kernel.itb', 'attr': ['mtd', 'required'], 'part': ['kernel']}
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
        result = verify_image(images[0])
        final = args.output / 'd213ecv-demo128-nand.img'
        shutil.copyfile(images[0], final)
        shutil.copyfile(stage / 'image_cfg.json', args.output / 'image_cfg.json')
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True))
    manifest = {'board': LAYOUT['board'], 'vendor_compatibility_name': LAYOUT['vendor_profile'],
                'project_commit': commit, 'working_tree_dirty': dirty,
                'kernel_policy': 'experimental_6_18' if args.kernel else 'retain_factory_5_10',
                'buildroot_source': json.loads((ROOT / 'sources.lock.json').read_text())['buildroot'],
                'kernel_source': (json.loads((BOARD / 'vendor-sources.json').read_text())['kernel_reference']
                                  if args.kernel else 'existing factory NAND kernel; unchanged by this image'),
                'rootfs': rootfs, 'fits': fits, 'environment': environment, 'firmware': result,
                'component_provenance': provenance, 'packaging': 'passed',
                'hardware_boot': 'not_verified', 'recovery_policy': 'never targeted'}
    (args.output / 'firmware-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
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
    p = sub.add_parser('pack')
    p.add_argument('--components', type=Path, required=True)
    p.add_argument('--rootfs', type=Path, required=True)
    p.add_argument('--kernel', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'pack':
        pack(args)
    else:
        fn = {'layout': partitions, 'rootfs': check_rootfs, 'fit': check_fit, 'verify': verify_image}[args.command]
        print(json.dumps(fn() if args.command == 'layout' else fn(args.path), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))

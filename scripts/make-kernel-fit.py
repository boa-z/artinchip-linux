#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create a hash-checked kernel FIT using the vendor's existing firmware contract."""
import argparse
import gzip
import os
from pathlib import Path
import shutil
import json
import hashlib
import subprocess
import tempfile

from firmware import check_fit, require
from riscv_image import parse_image, check_layout
from boot_contract import check_dtb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True, help='Built Image or Image.gz')
    parser.add_argument('--dtb', type=Path, required=True)
    parser.add_argument('--opensbi', type=Path, required=True, help='Matching vendor fw_dynamic.bin')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--load', type=lambda x: int(x, 0), default=0x40000000)
    parser.add_argument('--entry', type=lambda x: int(x, 0))
    parser.add_argument('--legacy-baseline', action='store_true',
                        help='Explicitly permit the vendor DDR-base load address')
    args = parser.parse_args()
    if args.entry is None:
        args.entry = args.load
    packed = args.kernel.read_bytes()
    compressed = packed.startswith(b'\x1f\x8b')
    image = gzip.decompress(packed) if compressed else packed
    header = parse_image(image)
    dtb_contract = check_dtb(args.dtb)
    # Default retains the M1 ABI; nondefault addresses must match the header.
    baseline = args.legacy_baseline or args.load == 0x40000000
    check_layout(header, args.load, args.entry, 1, baseline=baseline,
                 extra_reserved=dtb_contract['reserved'])
    require(0 < args.opensbi.stat().st_size <= 0x20000, 'OpenSBI exceeds the factory 128 KiB slot')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
        d = Path(tmp)
        for source, name in ((args.kernel, 'kernel.bin'), (args.dtb, 'board.dtb'), (args.opensbi, 'fw_dynamic.bin')):
            shutil.copyfile(source, d / name)
        its = '''/dts-v1/;
/ {
    description = "D213ECV-DEMO-V4-0 Linux";
    #address-cells = <1>;
    images {
        kernel {
            description = "Linux";
            data = /incbin/("kernel.bin");
            type = "kernel"; arch = "riscv"; os = "linux";
            compression = "KERNEL_COMPRESSION"; load = <0x40000000>; entry = <0x40000000>;
            hash-1 { algo = "sha256"; };
        };
        opensbi {
            description = "Vendor generic-platform OpenSBI";
            data = /incbin/("fw_dynamic.bin");
            type = "firmware"; arch = "riscv"; os = "opensbi"; compression = "none";
            hash-1 { algo = "sha256"; };
        };
        fdt-1 {
            description = "D213ECV board device tree";
            data = /incbin/("board.dtb");
            type = "flat_dt"; arch = "riscv"; compression = "none";
            hash-1 { algo = "sha256"; };
        };
    };
    configurations {
        default = "conf-1";
        conf-1 { firmware = "opensbi"; kernel = "kernel"; fdt = "fdt-1"; };
    };
};
'''
        its = its.replace('load = <0x40000000>; entry = <0x40000000>;',
                          f'load = <0x{args.load:x}>; entry = <0x{args.entry:x}>;')
        (d / 'kernel.its').write_text(its.replace('KERNEL_COMPRESSION', 'gzip' if compressed else 'none'))
        env = os.environ.copy()
        env['SOURCE_DATE_EPOCH'] = '1767225600'
        subprocess.run(['mkimage', '-f', 'kernel.its', 'kernel.itb'], cwd=d, env=env, check=True)
        check_fit(d / 'kernel.itb', require_hashes=True)
        layout = check_layout(header, args.load, args.entry, (d / 'kernel.itb').stat().st_size,
                              baseline=baseline, extra_reserved=dtb_contract['reserved'])
        shutil.copyfile(d / 'kernel.itb', args.output)
        report = {'image_header': header, 'memory': layout, 'hardware_boot': 'not_verified',
                  'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest()}
        args.output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
        lines = [f'FIT: {args.output.name}', f'SHA256: {report["sha256"]}',
                 f'load=entry=0x{args.load:08x}',
                 f'Header text_offset=0x{header["text_offset"]:x}',
                 f'Header runtime image_size=0x{header["image_size"]:x} ({header["image_size"]} bytes)',
                 f'Image file size={header["file_size"]} bytes',
                 f'Header offset consistent: {layout["header_load_consistent"]}']
        for key in ('kernel_file_range', 'kernel_runtime_range', 'fit_staging_range'):
            start, end = layout[key]
            lines.append(f'{key}: [0x{start:08x},0x{end:08x})')
        for region in layout['reserved_ranges']:
            lines.append(f'{region["name"]}: [0x{region["start"]:08x},0x{region["end"]:08x})')
        lines += ['U-Boot guard is conservative; confirm actual bdinfo and fixed-up FDT.',
                  'Software checks only. Physical boot still requires verification.']
        args.output.with_suffix('.txt').write_text('\n'.join(lines) + '\n')
    print('Kernel FIT built and checked; hardware boot is not verified.')


if __name__ == '__main__':
    main()

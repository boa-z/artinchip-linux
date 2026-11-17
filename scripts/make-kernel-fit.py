#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create a hash-checked kernel FIT using the vendor's existing firmware contract."""
import argparse
import gzip
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from firmware import check_fit, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True, help='Built Image.gz')
    parser.add_argument('--dtb', type=Path, required=True)
    parser.add_argument('--opensbi', type=Path, required=True, help='Matching vendor fw_dynamic.bin')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    image = gzip.decompress(args.kernel.read_bytes())
    require(len(image) >= 64 and image[48:56] == b'RISCV\0\0\0', 'Not a RISC-V Linux Image.gz')
    # Preserve the vendor load address and keep the decompression destination
    # clear of the factory FIT staging buffer at 0x41200000.
    require(len(image) < 0x1200000, 'Kernel overlaps factory FIT staging buffer; revise RAM plan explicitly')
    require(struct.unpack_from('<Q', image, 16)[0] < 0x2200000,
            'Kernel runtime image overlaps the factory DTB address')
    require(0 < args.opensbi.stat().st_size <= 0x20000, 'OpenSBI exceeds the factory 128 KiB slot')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
        d = Path(tmp)
        for source, name in ((args.kernel, 'Image.gz'), (args.dtb, 'board.dtb'), (args.opensbi, 'fw_dynamic.bin')):
            shutil.copyfile(source, d / name)
        its = '''/dts-v1/;
/ {
    description = "D213ECV-DEMO-V4-0 Linux 6.18 bring-up";
    #address-cells = <1>;
    images {
        kernel {
            description = "Linux";
            data = /incbin/("Image.gz");
            type = "kernel"; arch = "riscv"; os = "linux";
            compression = "gzip"; load = <0x40000000>; entry = <0x40000000>;
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
        (d / 'kernel.its').write_text(its)
        env = os.environ.copy()
        env['SOURCE_DATE_EPOCH'] = '1767225600'
        subprocess.run(['mkimage', '-f', 'kernel.its', 'kernel.itb'], cwd=d, env=env, check=True)
        check_fit(d / 'kernel.itb', require_hashes=True)
        shutil.copyfile(d / 'kernel.itb', args.output)
    print('Kernel FIT built and checked; hardware boot is not verified.')


if __name__ == '__main__':
    main()

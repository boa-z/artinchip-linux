#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""RISC-V RV64 S-mode Image and D213ECV RAM boot contract checks."""
import struct

DDR_BASE = 0x40000000
DDR_END = 0x48000000
FIT_STAGE = 0x41200000
# Conservative policy, not a measurement of a running bootloader.
RESERVED = [('DTB staging budget', 0x42200000, 0x42400000),
            ('U-Boot relocation/heap/stack and relocated DTB guard', 0x46000000, 0x47fe0000),
            ('resident OpenSBI', 0x47fe0000, DDR_END)]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse_image(data):
    require(len(data) >= 64, 'Truncated RISC-V Image header')
    offset, size, flags, version = struct.unpack_from('<QQQI', data, 8)
    require(data[48:56] == b'RISCV\0\0\0' and data[56:60] == b'RSC\x05', 'Invalid RISC-V Image magic')
    require(version == 2, 'Unsupported RISC-V Image header version')
    require(flags == 0, 'Only little-endian Image flags=0 supported')
    require(offset == 0x200000, 'Expected RV64 S-mode text_offset=0x200000')
    require(size >= len(data) and size > 64, 'Invalid Image runtime size')
    require(struct.unpack_from('<I', data, 36)[0] == 0 and data[40:48] == bytes(8), 'Nonzero reserved Image fields')
    return {'magic': 'RISCV\\0\\0\\0', 'magic2': 'RSC\\x05', 'text_offset': offset,
            'image_size': size, 'flags': flags, 'version': version, 'file_size': len(data)}


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def check_layout(header, load, entry, fit_size, *, baseline=False, extra_reserved=()):
    require(load == entry, 'Raw Image entry must equal load (header code branches to _start_kernel)')
    require(load % 0x200000 == 0, 'RV64 load must be 2 MiB aligned')
    expected = DDR_BASE + header['text_offset']
    require(load == expected or (baseline and load == DDR_BASE),
            'Image header/load mismatch: only explicit legacy baseline may omit text_offset')
    runtime = (load, load + max(header['image_size'], header['file_size']))
    staging = (FIT_STAGE, FIT_STAGE + fit_size)
    require(DDR_BASE <= runtime[0] < runtime[1] <= DDR_END, 'Kernel exceeds DDR boundary')
    require(fit_size > 0 and DDR_BASE <= staging[0] < staging[1] <= DDR_END, 'FIT exceeds DDR boundary')
    require(not overlap(runtime, staging), 'Kernel runtime overlaps FIT staging')
    regions = [*RESERVED, *extra_reserved]
    for name, start, end in regions:
        require(DDR_BASE <= start < end <= DDR_END, 'Invalid reserved DDR range')
        require(not overlap(runtime, (start, end)), 'Kernel runtime overlaps ' + name)
        require(not overlap(staging, (start, end)), 'FIT staging overlaps ' + name)
    return {'load': load, 'entry': entry, 'header_expected_load': expected,
            'header_load_consistent': load == expected, 'legacy_baseline': baseline,
            'kernel_file_range': [load, load + header['file_size']],
            'kernel_runtime_range': list(runtime), 'fit_staging_range': list(staging),
            'reserved_ranges': [{'name': n, 'start': s, 'end': e} for n, s, e in regions],
            'bootloader_reservations': 'conservative guard; confirm bdinfo and final FDT on hardware'}

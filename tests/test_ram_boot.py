# SPDX-License-Identifier: MIT
"""Image/ABI rejection cases and real built-FIT corruption regression."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from riscv_image import parse_image, check_layout
from boot_contract import check_config, check_dtb
from firmware import check_fit


def image_fixture():
    data = bytearray(4096)
    struct.pack_into('<QQQI', data, 8, 0x200000, 0x300000, 0, 2)
    data[48:60] = b'RISCV\0\0\0RSC\x05'
    return data


class ImageChecks(unittest.TestCase):
    def test_header_and_both_explicit_controls(self):
        header = parse_image(image_fixture())
        self.assertTrue(check_layout(header, 0x40200000, 0x40200000, 1024)['header_load_consistent'])
        report = check_layout(header, 0x40000000, 0x40000000, 1024, baseline=True)
        self.assertFalse(report['header_load_consistent'])
        with self.assertRaisesRegex(ValueError, 'header/load'):
            check_layout(header, 0x40000000, 0x40000000, 1024)

    def test_bad_header_fields(self):
        for offset, replacement in [(48, b'BAD!!'), (56, b'BAD!'), (32, b'\x03'),
                                    (24, b'\x01'), (8, b'\x01'), (36, b'\x01')]:
            with self.subTest(offset=offset):
                data = image_fixture()
                data[offset:offset + len(replacement)] = replacement
                with self.assertRaises(ValueError):
                    parse_image(data)
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            parse_image(bytes(63))

    def test_runtime_not_file_size_controls_overlap(self):
        header = parse_image(image_fixture())
        header['image_size'] = 0x1000001
        with self.assertRaisesRegex(ValueError, 'FIT staging'):
            check_layout(header, 0x40200000, 0x40200000, 4096)

    def test_invalid_entry_alignment_and_ddr(self):
        header = parse_image(image_fixture())
        for load, entry in [(0x40200000, 0x40400000), (0x40201000, 0x40201000),
                            (0x48000000, 0x48000000)]:
            with self.subTest(load=load), self.assertRaises(ValueError):
                check_layout(header, load, entry, 4096)
        header['image_size'] = 0x8000000
        with self.assertRaisesRegex(ValueError, 'DDR boundary'):
            check_layout(header, 0x40200000, 0x40200000, 4096)

    def test_fit_and_reserved_memory_collision(self):
        header = parse_image(image_fixture())
        with self.assertRaisesRegex(ValueError, 'DTB staging'):
            check_layout(header, 0x40200000, 0x40200000, 0x1100000)
        with self.assertRaisesRegex(ValueError, 'board carveout'):
            check_layout(header, 0x40200000, 0x40200000, 4096,
                         extra_reserved=[('board carveout', 0x40400000, 0x40500000)])
        with self.assertRaisesRegex(ValueError, 'staging overlaps'):
            check_layout(header, 0x40200000, 0x40200000, 0x4f00000)

    def test_invalid_runtime_size(self):
        data = image_fixture()
        struct.pack_into('<Q', data, 16, 64)
        with self.assertRaisesRegex(ValueError, 'runtime size'):
            parse_image(data)


BASE = ROOT / 'output/d213ecv-demo128-nand-linux618'
BOOT = ROOT / '.cache/vendor-boot/components/fw_dynamic.bin'


@unittest.skipUnless((BASE / 'images/Image.gz').exists() and BOOT.exists(),
                     'Build board kernel and boot components for real FIT integration checks')
class BuiltFitChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_path = os.environ['PATH']
        os.environ['PATH'] = str(BASE / 'host/bin') + os.pathsep + cls.old_path
        cls.addClassCleanup(os.environ.__setitem__, 'PATH', cls.old_path)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.fit = self.tmp / 'offset.itb'
        subprocess.run([sys.executable, str(ROOT / 'scripts/make-kernel-fit.py'),
                        '--kernel', str(BASE / 'images/Image.gz'),
                        '--dtb', str(BASE / 'images/d213ecv-demo128-nand.dtb'),
                        '--opensbi', str(BOOT), '--load', '0x40200000', '--output', str(self.fit)],
                       check=True, stdout=subprocess.DEVNULL)

    def test_real_fit_hashes_and_each_corrupted_payload(self):
        report = check_fit(self.fit, require_hashes=True)
        self.assertEqual(len(report['images']), 3)
        original = self.fit.read_bytes()
        for index in range(3):
            payload = self.tmp / 'payload'
            subprocess.run(['dumpimage', '-T', 'flat_dt', '-p', str(index), '-o', str(payload), str(self.fit)],
                           check=True, stdout=subprocess.DEVNULL)
            raw = payload.read_bytes()
            start = original.find(raw)
            self.assertGreater(start, 0)
            data = bytearray(original)
            data[start + len(raw) // 2] ^= 1
            damaged = self.tmp / f'damaged-{index}.itb'
            damaged.write_bytes(data)
            with self.subTest(component=index), self.assertRaisesRegex(ValueError, 'hash mismatch'):
                check_fit(damaged, require_hashes=True)

    def test_mutated_load_and_entry_are_rejected(self):
        subprocess.run(['fdtput', '-t', 'x', str(self.fit), '/images/kernel', 'load', '40400000'], check=True)
        with self.assertRaisesRegex(ValueError, 'entry must equal load'):
            check_fit(self.fit, require_hashes=True)

    def test_cpu_uart_memory_and_required_config(self):
        dtb = self.tmp / 'board.dtb'
        shutil.copyfile(BASE / 'images/d213ecv-demo128-nand.dtb', dtb)
        check_dtb(dtb)
        subprocess.run(['fdtput', '-t', 'x', str(dtb), '/memory@40000000', 'reg',
                        '0', '40000000', '0', '10000000'], check=True)
        with self.assertRaisesRegex(ValueError, 'DDR mismatch'):
            check_dtb(dtb)
        config = BASE / 'build/linux-custom/.config'
        check_config(config)
        broken = self.tmp / '.config'
        broken.write_text(config.read_text().replace('CONFIG_SERIAL_8250_ARTINCHIP=y',
                                                    'CONFIG_SERIAL_8250_ARTINCHIP=m'))
        with self.assertRaisesRegex(ValueError, 'SERIAL_8250_ARTINCHIP'):
            check_config(broken)


@unittest.skipUnless((ROOT / 'output/m2-diagnostic/build/arch/riscv/boot/Image.gz').exists(),
                     'Build the optional diagnostic kernel for emitted-code checks')
class DiagnosticChecks(unittest.TestCase):
    def test_debug_is_opt_in_and_sbi_compatibility_enabled(self):
        debug = ROOT / 'output/m2-diagnostic/build/.config'
        result = check_config(debug, diagnostic=True)
        self.assertTrue(result['earlycon_sbi_compatible_with_vendor_0_9'])
        self.assertNotIn('CONFIG_D213ECV_EARLY_DEBUG=y', (BASE / 'build/linux-custom/.config').read_text())

    def test_entry_marker_preserves_boot_arguments_without_stack(self):
        tool = BASE / 'host/bin/riscv64-linux-objdump'
        elf = ROOT / 'output/m2-diagnostic/build/vmlinux'
        listing = subprocess.check_output([str(tool), '-d', '--disassemble=_start_kernel', str(elf)], text=True)
        # E0 is before the first interrupt-mask CSR. No prologue/stack or call
        # is allowed while the incoming a0/a1 still carry the boot ABI state.
        marker = listing.split('<_start_kernel>:', 1)[1].split('csrw', 1)[0]
        self.assertIn('lw\tt2,20(t0)', marker)
        self.assertIn('sw\tt3,0(t0)', marker)
        for reg in ('a0', 'a1', 'ra', 'sp', 's0', 's1'):
            self.assertNotRegex(marker, r'\b' + reg + r'\b')
        self.assertNotIn('ecall', marker)


if __name__ == '__main__':
    unittest.main()

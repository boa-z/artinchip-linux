# SPDX-License-Identifier: MIT
"""Negative checks for the partition and image boundaries used before flashing."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

SPEC = importlib.util.spec_from_file_location('firmware', Path(__file__).resolve().parents[1] / 'scripts/firmware.py')
fw = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fw)


class FirmwareChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'fixture.bin'

    def superblock(self):
        data = bytearray(126976 * 20)
        struct.pack_into('<I', data, 0, 0x06101831)
        struct.pack_into('<IIII', data, 32, 2048, 126976, 20, 480)
        struct.pack_into('<I', data, 80, 5)
        struct.pack_into('<H', data, 84, 2)
        return data

    def image(self, target='ubiroot:rootfs'):
        payload = b'fixture, never firmware'
        data = bytearray(2048 + 512 + len(payload))
        data[:8] = b'AIC.FW\0\0'
        data[200:208] = b'spi-nand'
        struct.pack_into('<IIII', data, 332, 2048, 512, 2560, len(payload))
        data[2048:2056] = b'META\0\0\0\0'
        name = b'image.target.rootfs'
        data[2056:2056 + len(name)] = name
        data[2120:2120 + len(target)] = target.encode()
        struct.pack_into('<III', data, 2184, 2560, len(payload), zlib.crc32(payload))
        data[2560:] = payload
        return data

    def test_factory_layout_and_root_index(self):
        parts = fw.partitions()
        self.assertEqual(list(parts).index('ubiroot'), 10)
        self.assertEqual(parts['bbt']['offset'], 0x240000)
        self.assertEqual(parts['recovery']['offset'], 0x1000000)

    def test_moved_recovery_is_rejected(self):
        layout = copy.deepcopy(fw.LAYOUT)
        layout['partitions'][8]['size'] += 131072
        layout['partitions'][-1]['size'] -= 131072
        with self.assertRaisesRegex(ValueError, 'recovery'):
            fw.partitions(layout)

    def test_geometry_and_compression_contract(self):
        data = self.superblock()
        self.path.write_bytes(data)
        self.assertEqual(fw.check_rootfs(self.path)['hardware_mount'], 'not_verified')
        struct.pack_into('<I', data, 36, 129024)
        self.path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'geometry'):
            fw.check_rootfs(self.path)

    def test_new_ubifs_format_is_rejected(self):
        data = self.superblock()
        struct.pack_into('<I', data, 80, 6)
        self.path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'compatibility'):
            fw.check_rootfs(self.path)

    def test_oversized_leb_budget_is_rejected(self):
        data = self.superblock()
        struct.pack_into('<I', data, 44, 512)
        self.path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'budget'):
            fw.check_rootfs(self.path)

    def test_recovery_target_is_rejected_even_with_valid_crc(self):
        self.path.write_bytes(self.image('recovery'))
        with self.assertRaisesRegex(ValueError, 'protected'):
            fw.verify_image(self.path)

    def test_corrupted_payload_is_rejected(self):
        data = self.image()
        data[-1] ^= 1
        self.path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'CRC'):
            fw.verify_image(self.path)

    def test_truncated_image_is_rejected(self):
        self.path.write_bytes(self.image()[:-1])
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            fw.verify_image(self.path)

    def test_short_header_is_rejected(self):
        self.path.write_bytes(b'AIC.FW')
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            fw.verify_image(self.path)

    def test_unknown_component_name_is_rejected(self):
        data = self.image()
        data[2056:2120] = b'image.extension.rootfs'.ljust(64, b'\0')
        self.path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            fw.verify_image(self.path)

    def test_rootfs_only_metadata_passes(self):
        self.path.write_bytes(self.image())
        self.assertFalse(fw.verify_image(self.path)['recovery_targeted'])


if __name__ == '__main__':
    unittest.main()

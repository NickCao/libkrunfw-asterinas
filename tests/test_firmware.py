import ctypes
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pack


class BootDataTests(unittest.TestCase):
    def test_acpi_checksums_and_addresses(self):
        base = 0x9601000
        data = pack.acpi(base)
        self.assertEqual(data[:8], b"RSD PTR ")
        self.assertEqual(sum(data[:20]) % 256, 0)
        self.assertEqual(sum(data[:36]) % 256, 0)
        self.assertEqual(struct.unpack_from("<Q", data, 24)[0], base + 36)
        self.assertEqual(data[36:40], b"XSDT")
        self.assertEqual(sum(data[36:80]) % 256, 0)
        self.assertEqual(struct.unpack_from("<Q", data, 72)[0], base + 80)
        self.assertEqual(data[80:84], b"APIC")
        self.assertEqual(sum(data[80:]) % 256, 0)
        self.assertEqual(struct.unpack_from("<I", data, 116)[0], 0xfee00000)

    def test_rejects_wrong_elf_format(self):
        with self.assertRaises(ValueError):
            pack.flatten_elf(b"not a kernel")

    def test_cpio_alignment_and_file_data(self):
        entry = pack.cpio_entry("init", 0o100755, b"test")
        self.assertEqual(entry[:6], b"070701")
        self.assertEqual(len(entry) % 4, 0)
        name_length = int(entry[94:102], 16)
        self.assertEqual(entry[110:110 + name_length], b"init\0")
        self.assertEqual(entry[pack.align(110 + name_length, 4):], b"test")


class FirmwareABITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = json.loads((ROOT / "build/payload/layout.json").read_text())
        cls.library = ctypes.CDLL(str(ROOT / "build/libkrunfw.so.5"))
        cls.library.krunfw_get_kernel.argtypes = [ctypes.POINTER(ctypes.c_size_t)] * 3
        cls.library.krunfw_get_kernel.restype = ctypes.c_void_p
        cls.base, cls.entry, cls.size = (ctypes.c_size_t() for _ in range(3))
        cls.pointer = cls.library.krunfw_get_kernel(ctypes.byref(cls.base), ctypes.byref(cls.entry), ctypes.byref(cls.size))

    def test_abi_and_alignment(self):
        self.assertEqual(self.library.krunfw_get_version(), 5)
        self.assertEqual(self.pointer % 65536, 0)
        self.assertEqual(self.size.value % 65536, 0)
        self.assertEqual(self.base.value, self.layout["IMAGE_BASE"])
        self.assertEqual(self.entry.value, self.layout["IMAGE_ENTRY"])
        self.assertLess(self.entry.value, self.base.value + self.size.value)

    def test_payload_matches_generated_image(self):
        generated = (ROOT / "build/payload/firmware.bin").read_bytes()
        self.assertEqual(ctypes.string_at(self.pointer, self.size.value), generated)

    def test_kernel_entry_and_bss_are_preserved(self):
        base, entry, image = pack.flatten_elf((ROOT / "build/asterinas.elf").read_bytes())
        self.assertEqual(entry, self.layout["KERNEL_ENTRY"])
        self.assertNotEqual(entry, struct.unpack_from("<Q", (ROOT / "build/asterinas.elf").read_bytes(), 24)[0])
        self.assertEqual(ctypes.string_at(self.pointer, len(image)), image)
        self.assertEqual(self.layout["BOOT_DATA_BASE"], base + len(image))
        self.assertEqual(self.layout["BOOT_DATA_SIZE"], self.size.value - len(image))


if __name__ == "__main__":
    unittest.main()

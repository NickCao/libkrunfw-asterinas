import ctypes
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / os.environ.get("FIRMWARE_BUILD", "build")
KERNEL = ROOT / os.environ.get("FIRMWARE_KERNEL", "build/asterinas.elf")
sys.path.insert(0, str(ROOT / "tools"))
import pack


class BootDataTests(unittest.TestCase):
    def test_rejects_wrong_elf_format(self):
        with self.assertRaises(ValueError):
            pack.flatten_elf(b"not a kernel")

class FirmwareABITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = json.loads((BUILD / "payload/layout.json").read_text())
        cls.library = ctypes.CDLL(str(BUILD / "libkrunfw.so.5"))
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
        generated = (BUILD / "payload/firmware.bin").read_bytes()
        self.assertEqual(ctypes.string_at(self.pointer, self.size.value), generated)

    def test_kernel_entry_and_bss_are_preserved(self):
        base, entry, image = pack.flatten_elf(KERNEL.read_bytes())
        self.assertEqual(entry, self.layout["KERNEL_ENTRY"])
        self.assertNotEqual(entry, struct.unpack_from("<Q", KERNEL.read_bytes(), 24)[0])
        self.assertEqual(ctypes.string_at(self.pointer, len(image)), image)
        self.assertEqual(self.entry.value, entry)
        self.assertEqual(self.size.value, len(image))

    def test_firmware_has_no_initramfs(self):
        self.assertEqual(self.layout["INITRD_ADDR"], 0)
        self.assertEqual(self.layout["INITRD_SIZE"], 0)
        self.assertNotIn("RSDP_ADDR", self.layout)


if __name__ == "__main__":
    unittest.main()

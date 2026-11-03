#!/usr/bin/python3
"""Flatten Asterinas's ELF for direct entry by stock libkrun."""
import argparse
import json
from pathlib import Path
import struct

ALIGNMENT = 65536


def align(value, boundary=ALIGNMENT):
    return (value + boundary - 1) // boundary * boundary


def flatten_elf(data):
    if data[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("Expected a little-endian ELF64 kernel")
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    phoff, phsize, phnum = header[5], header[9], header[10]
    segments = []
    for i in range(phnum):
        kind, flags, offset, virtual, physical, filesz, memsz, _ = struct.unpack_from("<IIQQQQQQ", data, phoff + i * phsize)
        if kind != 1:
            continue
        if filesz > memsz or offset + filesz > len(data):
            raise ValueError("Malformed ELF load segment")
        segments.append((physical, offset, filesz, memsz, flags))
    if not segments:
        raise ValueError("ELF has no loadable segments")
    segments.sort()
    base = segments[0][0]
    end = max(address + memsz for address, _, _, memsz, _ in segments)
    if base % ALIGNMENT or end >= 1 << 30 or end - base > 128 * 1024 * 1024:
        raise ValueError("Unsupported kernel address range")
    result = bytearray(align(end - base))
    previous_end = base
    for address, offset, filesz, memsz, _ in segments:
        if address < previous_end:
            raise ValueError("Overlapping ELF load segments")
        result[address - base:address - base + filesz] = data[offset:offset + filesz]
        previous_end = address + memsz
    # The ELF's normal entry is 32-bit. Resolve Asterinas's Linux64 symbol instead.
    entry = None
    shoff, shsize, shnum = header[6], header[11], header[12]
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shsize) for i in range(shnum)]
    for section in sections:
        if section[1] != 2:
            continue
        strings = sections[section[6]]
        names = data[strings[4]:strings[4] + strings[5]]
        for pos in range(section[4], section[4] + section[5], section[9]):
            name, _, _, _, value, _ = struct.unpack_from("<IBBHQQ", data, pos)
            if names[name:names.find(b"\0", name)] == b"__linux64_boot":
                entry = value
    if entry is None or not any(addr <= entry < addr + size and flags & 1 for addr, _, size, _, flags in segments):
        raise ValueError("Cannot locate Asterinas's Linux64 boot entry")
    return base, entry, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    base, entry, image = flatten_elf(args.kernel.read_bytes())
    args.output.mkdir(parents=True, exist_ok=True)
    defines = {
        "IMAGE_BASE": base, "IMAGE_SIZE": len(image),
        "KERNEL_ENTRY": entry, "IMAGE_ENTRY": entry,
        "INITRD_ADDR": 0, "INITRD_SIZE": 0,
    }
    (args.output / "firmware.bin").write_bytes(image)
    (args.output / "layout.h").write_text("".join(f"#define {k} {v}UL\n" for k, v in defines.items()))
    (args.output / "layout.json").write_text(json.dumps(defines, indent=2) + "\n")
    (args.output / "image.S").write_text('.data\n.balign 65536\n.global firmware_image\n.hidden firmware_image\nfirmware_image:\n.incbin "' + str((args.output / "firmware.bin").resolve()) + '"\n.section .note.GNU-stack,"",@progbits\n')
    print(json.dumps(defines))


if __name__ == "__main__":
    main()

#!/usr/bin/python3
"""Flatten Asterinas's ELF and append the boot data needed by stock libkrun."""
import argparse
import json
from pathlib import Path
import stat
import struct
import subprocess

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


def checksum(data, offset):
    data[offset] = (-sum(data)) & 255
    return bytes(data)


def table(signature, body):
    header = struct.pack("<4sIBB6s8sI4sI", signature, 36 + len(body), 1, 0, b"ASTER ", b"KRUNPOC ", 1, b"ASTR", 1)
    return checksum(bytearray(header + body), 9)


def acpi(address):
    # A single CPU and the standard KVM local/I/O APIC addresses. No AML is needed.
    madt_address = address + 80
    xsdt = table(b"XSDT", struct.pack("<Q", madt_address))
    madt = table(b"APIC", struct.pack("<II", 0xfee00000, 1)
                 + struct.pack("<BBBBI", 0, 8, 0, 0, 1)
                 + struct.pack("<BBBBII", 1, 12, 0, 0, 0xfec00000, 0))
    rsdp = bytearray(struct.pack("<8sB6sBIIQB3s", b"RSD PTR ", 0, b"ASTER ", 2, 0, 36, address + 36, 0, b"\0" * 3))
    rsdp[8] = (-sum(rsdp[:20])) & 255
    rsdp = checksum(rsdp, 32)
    return rsdp + xsdt + madt


def cpio_entry(name, mode, data=b"", major=0, minor=0):
    name = name.encode() + b"\0"
    fields = [0, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(name), 0]
    header = b"070701" + b"".join(f"{value:08x}".encode() for value in fields)
    result = header + name
    result += bytes(align(len(result), 4) - len(result))
    result += data
    return result + bytes(align(len(data), 4) - len(data))


def initramfs(init_path):
    # Package the helper's Fedora runtime libraries in the bootstrap initramfs.
    # The actual container executable later uses the container's own libraries.
    libraries = set()
    for line in subprocess.check_output(["ldd", str(init_path)], text=True).splitlines():
        for item in line.split():
            if item.startswith("/"):
                libraries.add(Path(item))
    result = (cpio_entry("dev", stat.S_IFDIR | 0o755)
            + cpio_entry("dev/console", stat.S_IFCHR | 0o600, major=5, minor=1)
            + cpio_entry("newroot", stat.S_IFDIR | 0o755)
            + cpio_entry("init", stat.S_IFREG | 0o755, init_path.read_bytes()))
    directories = set()
    for library in sorted(libraries):
        for parent in reversed(library.parents):
            if parent != Path("/") and parent not in directories:
                result += cpio_entry(str(parent).lstrip("/"), stat.S_IFDIR | 0o755)
                directories.add(parent)
        result += cpio_entry(str(library).lstrip("/"), stat.S_IFREG | 0o755, library.read_bytes())
    return result + cpio_entry("TRAILER!!!", 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path)
    parser.add_argument("init", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    base, entry, image = flatten_elf(args.kernel.read_bytes())
    args.output.mkdir(parents=True, exist_ok=True)
    bootstrap_offset = len(image)
    acpi_offset = bootstrap_offset + 4096
    cmdline_offset = acpi_offset + 4096
    initrd_offset = cmdline_offset + 8192
    initrd = initramfs(args.init)
    size = align(initrd_offset + len(initrd))
    defines = {
        "IMAGE_BASE": base, "IMAGE_SIZE": size,
        "KERNEL_ENTRY": entry, "RSDP_ADDR": base + acpi_offset,
        "INITRD_ADDR": base + initrd_offset, "INITRD_SIZE": len(initrd),
        "CMDLINE_ADDR": base + cmdline_offset,
        "BOOT_DATA_BASE": base + bootstrap_offset,
        "BOOT_DATA_SIZE": size - bootstrap_offset,
    }
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["gcc", "-c", "-nostdlib", *[f"-D{k}={v}" for k, v in defines.items()], str(root / "src/entry.S"), "-o", str(args.output / "entry.o")], check=True)
    subprocess.run(["objcopy", "-O", "binary", "-j", ".text", str(args.output / "entry.o"), str(args.output / "entry.bin")], check=True)
    bootstrap = (args.output / "entry.bin").read_bytes()
    if len(bootstrap) > 4096:
        raise ValueError("Boot code exceeds reserved space")
    image += bytes(size - len(image))
    image[bootstrap_offset:bootstrap_offset + len(bootstrap)] = bootstrap
    tables = acpi(base + acpi_offset)
    image[acpi_offset:acpi_offset + len(tables)] = tables
    image[initrd_offset:initrd_offset + len(initrd)] = initrd
    (args.output / "firmware.bin").write_bytes(image)
    defines["IMAGE_ENTRY"] = base + bootstrap_offset
    (args.output / "layout.h").write_text("".join(f"#define {k} {v}UL\n" for k, v in defines.items()))
    (args.output / "layout.json").write_text(json.dumps(defines, indent=2) + "\n")
    (args.output / "image.S").write_text('.data\n.balign 65536\n.global firmware_image\n.hidden firmware_image\nfirmware_image:\n.incbin "' + str((args.output / "firmware.bin").resolve()) + '"\n.section .note.GNU-stack,"",@progbits\n')
    print(json.dumps(defines))


if __name__ == "__main__":
    main()

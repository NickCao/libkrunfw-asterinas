/* SPDX-License-Identifier: MIT */
/* Runs inside the VM, before entering the Asterinas kernel. */
#include <stddef.h>
#include <stdint.h>
#include "layout.h"

static int starts(const char *s, const char *end, const char *prefix)
{
    while (*prefix) {
        if (s == end || *s++ != *prefix++) return 0;
    }
    return 1;
}

static uint64_t mmio_address(const char *s, const char *end)
{
    while (s < end && *s != '@') ++s;
    if (end - s < 4 || s[1] != '0' || s[2] != 'x') return 0;
    s += 3;
    uint64_t value = 0;
    while (s < end && *s != ':') {
        unsigned digit = (unsigned char)*s++;
        if (digit >= '0' && digit <= '9') digit -= '0';
        else if (digit >= 'a' && digit <= 'f') digit -= 'a' - 10;
        else if (digit >= 'A' && digit <= 'F') digit -= 'A' - 10;
        else return 0;
        if (value > 0xffffffffUL / 16) return 0;
        value = value * 16 + digit;
    }
    return value;
}

static int is_console(const char *s, const char *end)
{
    if (!starts(s, end, "virtio_mmio.device=")) return 0;
    uint64_t addr = mmio_address(s, end);
    if (addr < 0xc0000000 || addr > 0xfffff000 || (addr & 4095)) return 0;
    volatile uint32_t *registers = (volatile uint32_t *)addr;
    return registers[0] == 0x74726976 && registers[2] == 3;
}

void boot_prepare(unsigned char *params)
{
    /* libkrun initially maps only the first GiB. Temporarily map its MMIO
     * region so we can identify devices by their standard virtio header. */
    uintptr_t cr3;
    __asm__ volatile("mov %%cr3, %0" : "=r"(cr3));
    uint64_t *pml4 = (uint64_t *)(cr3 & ~4095UL);
    uint64_t *pdpt = (uint64_t *)(pml4[0] & 0x000ffffffffff000UL);
    uint64_t previous = pdpt[3];
    uint64_t *pd = (uint64_t *)MMIO_PD_ADDR;
    for (unsigned i = 0; i < 512; ++i) pd[i] = 0xc0000000UL + (i << 21) + 0x93;
    pdpt[3] = MMIO_PD_ADDR | 3;
    __asm__ volatile("mov %0, %%cr3" :: "r"(cr3) : "memory");

    const char *input = (const char *)(uintptr_t)*(uint32_t *)(params + 0x228);
    size_t limit = *(uint32_t *)(params + 0x238);
    if (limit > 4096) limit = 4096;
    const char *end = input;
    while ((size_t)(end - input) < limit && *end) ++end;
    int virtio_console = 0, serial_console = 0;
    for (const char *s = input; s < end;) {
        while (s < end && *s == ' ') ++s;
        const char *token = s;
        while (s < end && *s != ' ') ++s;
        if (is_console(token, s)) virtio_console = 1;
        if (starts(token, s, "console=ttyS0")) serial_console = 1;
    }
    char *output = (char *)CMDLINE_ADDR;
    const char *prefix = virtio_console && !serial_console ? "loglevel=error console=hvc0 " : "earlycon loglevel=error ";
    while (*prefix) *output++ = *prefix++;
    for (const char *s = input; s < end;) {
        const char *token = s;
        while (s < end && *s != ' ') ++s;
        /* Asterinas has no Linux TSI socket hooks. Do not advertise them to
         * libkrun's init, including on VMs without a virtio-net device. */
        if (!(s - token == 10 && starts(token, s, "tsi_hijack")))
            while (token < s) *output++ = *token++;
        if (s < end) *output++ = *s++;
    }
    *output = 0;
    pdpt[3] = previous;
    __asm__ volatile("mov %0, %%cr3" :: "r"(cr3) : "memory");
    *(uint32_t *)(params + 0x228) = CMDLINE_ADDR;
    *(uint32_t *)(params + 0x238) = output - (char *)CMDLINE_ADDR + 1;
    *(uint64_t *)(params + 0x70) = RSDP_ADDR;
    *(uint32_t *)(params + 0x218) = INITRD_ADDR;
    *(uint32_t *)(params + 0x21c) = INITRD_SIZE;
    unsigned count = params[0x1e8];
    if (count < 128) {
        unsigned char *entry = params + 0x2d0 + count * 20;
        *(uint64_t *)entry = BOOT_DATA_BASE;
        *(uint64_t *)(entry + 8) = BOOT_DATA_SIZE;
        *(uint32_t *)(entry + 16) = 2;
        params[0x1e8] = count + 1;
    }
}

/* SPDX-License-Identifier: MIT */
SECTIONS {
    . = BOOT_BASE;
    .text : { *(.text) *(.text.*) *(.rodata*) }
    /DISCARD/ : { *(.eh_frame*) *(.note*) *(.comment*) }
}

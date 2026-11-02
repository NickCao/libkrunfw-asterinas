/* SPDX-License-Identifier: MIT */
/* libkrun enters in long mode with RSI pointing to Linux boot_params. */
.text
.code64
.global _start
_start:
    cli
    cld
    mov %rsi, %rbx
    mov %rsi, %rdi
    and $-16, %rsp
    call boot_prepare
    mov %rbx, %rsi
    movabs $KERNEL_ENTRY, %rax
    jmp *%rax
.section .note.GNU-stack,"",@progbits

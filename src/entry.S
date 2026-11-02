/* SPDX-License-Identifier: MIT */
/* libkrun enters in long mode with RSI pointing to Linux boot_params. */
.text
.code64
.global _start
_start:
    cli
    cld
    movabs $RSDP_ADDR, %rax
    movq %rax, 0x70(%rsi)
    movl $INITRD_ADDR, 0x218(%rsi)
    movl $INITRD_SIZE, 0x21c(%rsi)

    /* Keep libkrun's device/command arguments and enable the early UART. */
    movq %rsi, %r8
    movl 0x228(%r8), %r10d
    movl 0x238(%r8), %ecx
    cmp $4096, %ecx
    jbe 2f
    mov $4096, %ecx
2:
    mov %ecx, %r11d
    lea prefix_end-prefix+1(%rcx), %r9d
    mov $CMDLINE_ADDR, %edi
    lea prefix(%rip), %rsi
    mov $prefix_end-prefix, %ecx
    rep movsb
    mov %r10d, %esi
    mov %r11d, %ecx
    rep movsb
    movb $0, (%rdi)
    movq %r8, %rsi
    movl $CMDLINE_ADDR, 0x228(%rsi)
    movl %r9d, 0x238(%rsi)

    /* The kernel reserves its own segments; reserve only our appended data. */
    movzbl 0x1e8(%rsi), %eax
    cmp $128, %eax
    jae 1f
    imul $20, %eax, %edi
    lea 0x2d0(%rsi,%rdi), %rdi
    movq $BOOT_DATA_BASE, (%rdi)
    movq $BOOT_DATA_SIZE, 8(%rdi)
    movl $2, 16(%rdi)
    incb 0x1e8(%rsi)
1:
    movabs $KERNEL_ENTRY, %rax
    jmp *%rax
prefix:
    .ascii "earlycon loglevel=error "
prefix_end:
.section .note.GNU-stack,"",@progbits

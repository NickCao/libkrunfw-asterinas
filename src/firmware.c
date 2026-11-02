/* SPDX-License-Identifier: MIT */
#include <stddef.h>
#include "layout.h"

extern unsigned char firmware_image[];

__attribute__((visibility("default")))
char *krunfw_get_kernel(size_t *load_addr, size_t *entry_addr, size_t *size)
{
    *load_addr = IMAGE_BASE;
    *entry_addr = IMAGE_ENTRY;
    *size = IMAGE_SIZE;
    return (char *)firmware_image;
}

__attribute__((visibility("default")))
int krunfw_get_version(void)
{
    return 5;
}

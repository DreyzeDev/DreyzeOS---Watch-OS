/*
 * DreyzeOS — Memory Allocator Header
 * Freestanding — no libc.
 */

#pragma once

#include "types.h"

void *kmalloc(size_t size);
void *kzalloc(size_t size);
void  kfree(void *ptr);
void  mem_stats(void);

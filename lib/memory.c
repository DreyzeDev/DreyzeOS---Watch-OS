/*
 * DreyzeOS — Minimal Memory Allocator
 * Freestanding — no libc. Bump allocator for Phase 1-5.
 */

#include "memory.h"
#include "../include/log.h"

/* ============================================================
 * Bump Allocator
 *
 * Simple linear/bump allocator. Perfect for OS initialization:
 * - Zero overhead
 * - Deterministic
 * - No fragmentation concern
 * - Free is a no-op (can be upgraded later to a real allocator)
 * ============================================================ */

#define HEAP_SIZE       (256 * 1024)  /* 256 KB initial heap */
#define HEAP_ALIGN      16            /* 16-byte alignment (AArch64 ABI) */

/* Heap region — placed in BSS (zero-initialized at boot) */
static uint8_t heap_memory[HEAP_SIZE] __attribute__((aligned(16)));
static size_t  heap_used = 0;
static size_t  heap_alloc_count = 0;

void *kmalloc(size_t size)
{
    if (size == 0) return NULL;

    /* Align up to HEAP_ALIGN */
    size_t aligned_size = (size + HEAP_ALIGN - 1) & ~(size_t)(HEAP_ALIGN - 1);

    if (heap_used + aligned_size > HEAP_SIZE) {
        klog_error("[MEM] kmalloc: heap exhausted!");
        klog_hex("[MEM] requested", size);
        klog_hex("[MEM] heap_used", heap_used);
        klog_hex("[MEM] heap_size", HEAP_SIZE);
        return NULL;
    }

    void *ptr = heap_memory + heap_used;
    heap_used += aligned_size;
    heap_alloc_count++;
    return ptr;
}

void *kzalloc(size_t size)
{
    void *ptr = kmalloc(size);
    if (ptr) {
        /* Zero-initialize */
        uint8_t *p = (uint8_t *)ptr;
        for (size_t i = 0; i < size; i++) p[i] = 0;
    }
    return ptr;
}

/*
 * kfree — no-op in bump allocator.
 * For Phase 1 research builds, we don't need a real free.
 * Will be replaced in Phase 6+ with a proper allocator.
 */
void kfree(void *ptr)
{
    (void)ptr;
    /* Bump allocator: no free */
}

void mem_stats(void)
{
    klog_info("[MEM] Heap statistics:");
    klog_hex("[MEM]   heap_used  (bytes)", heap_used);
    klog_hex("[MEM]   heap_free  (bytes)", HEAP_SIZE - heap_used);
    klog_hex("[MEM]   alloc_count", heap_alloc_count);
}

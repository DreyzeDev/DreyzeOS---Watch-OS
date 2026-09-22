/*
 * DreyzeOS — Host C Unit Tests
 * Tests real C implementations of:
 *   - Boot stage monotonic state machine
 *   - Invalid out-of-order stage transitions
 *   - Failsafe state & last_successful_stage preservation
 *   - Framebuffer mapping interlock & write permission gating
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <setjmp.h>
#include <assert.h>

#include "../include/boot_stage.h"
#include "../include/boot_info.h"
#include "../hal/t8006/device_tree.h"
#include "../hal/t8006/framebuffer.h"
#include "../hal/t8006/mmio_gate.h"
#include "../hal/t8006/handoff_gate.h"
#include "../hal/t8006/uart.h"
#include "../hal/t8006/aic.h"
#include "../hal/t8006/platform.h"
#include "../include/log.h"
#include "pic_stage0_host.h"

/* ============================================================
 * Test Harness Stubs for Host Execution
 * ============================================================ */

static jmp_buf g_failsafe_jmp;
static bool g_intercept_failsafe = false;

void arch_irq_disable(void) {}

static void make_prop(unsigned char *dst, const char *name,
                      const unsigned char *value, unsigned int size)
{
    memset(dst, 0, sizeof(adt_prop_hdr_t) + ((size + 3U) & ~3U));
    memcpy(dst, name, strlen(name) < 32 ? strlen(name) : 32);
    memcpy(dst + 32 + 4, value, size);
    *(unsigned int *)(void *)(dst + 32) = size;
}

/* Override boot_stage_failsafe loop for host test interception */
void __attribute__((noinline)) host_test_halt_intercept(void)
{
    if (g_intercept_failsafe) {
        longjmp(g_failsafe_jmp, 1);
    }
    abort();
}

/* ============================================================
 * Tests: Boot Stage State Machine
 * ============================================================ */

static void test_stage_sequential_progression(void)
{
    printf("[C-TEST] Running: test_stage_sequential_progression... ");
    boot_stage_reset_for_test();

    assert(boot_stage_get() == BOOT_STAGE_ENTRY);
    assert(boot_stage_get_last_successful() == BOOT_STAGE_ENTRY);

    boot_stage_set(BOOT_STAGE_RAM_LOG);
    assert(boot_stage_get() == BOOT_STAGE_RAM_LOG);
    assert(boot_stage_get_last_successful() == BOOT_STAGE_RAM_LOG);

    boot_stage_set(BOOT_STAGE_BOOT_ARGS);
    assert(boot_stage_get() == BOOT_STAGE_BOOT_ARGS);
    assert(boot_stage_get_last_successful() == BOOT_STAGE_BOOT_ARGS);

    boot_stage_set(BOOT_STAGE_MEM_MAP);
    assert(boot_stage_get() == BOOT_STAGE_MEM_MAP);
    assert(boot_stage_get_last_successful() == BOOT_STAGE_MEM_MAP);

    boot_stage_set(BOOT_STAGE_AIC);
    assert(boot_stage_get() == BOOT_STAGE_AIC);
    assert(boot_stage_get_last_successful() == BOOT_STAGE_AIC);

    boot_stage_set(BOOT_STAGE_FB);
    assert(boot_stage_get() == BOOT_STAGE_FB);
    assert(boot_stage_get_last_successful() == BOOT_STAGE_FB);

    boot_stage_set(BOOT_STAGE_IDLE);
    assert(boot_stage_get() == BOOT_STAGE_IDLE);
    assert(boot_stage_get_last_successful() == BOOT_STAGE_IDLE);

    printf("PASS\n");
}

static bool contains_substr(const char *haystack, const char *needle)
{
    if (!haystack || !needle) return false;
    size_t hlen = strlen(haystack);
    size_t nlen = strlen(needle);
    if (nlen > hlen) return false;
    for (size_t i = 0; i <= hlen - nlen; i++) {
        if (strncmp(haystack + i, needle, nlen) == 0) return true;
    }
    return false;
}

static void test_stage_invalid_backward_transition(void)
{
    printf("[C-TEST] Running: test_stage_invalid_backward_transition... ");
    boot_stage_reset_for_test();

    boot_stage_set(BOOT_STAGE_ENTRY);
    boot_stage_set(BOOT_STAGE_RAM_LOG);
    boot_stage_set(BOOT_STAGE_BOOT_ARGS);
    boot_stage_set(BOOT_STAGE_MEM_MAP);
    assert(boot_stage_get() == BOOT_STAGE_MEM_MAP);

    /* Attempt invalid backwards transition (STAGE 3 -> STAGE 1) */
    g_intercept_failsafe = true;
    if (setjmp(g_failsafe_jmp) == 0) {
        boot_stage_set(BOOT_STAGE_RAM_LOG);
        assert(false && "Backward transition should have triggered failsafe!");
    }
    g_intercept_failsafe = false;

    /* Verify failsafe caught it */
    assert(boot_stage_get() == BOOT_STAGE_ERROR);
    /* Verify last successful stage was preserved as STAGE 3 (MEM_MAP) */
    assert(boot_stage_get_last_successful() == BOOT_STAGE_MEM_MAP);
    assert(boot_stage_get_failure_stage() == BOOT_STAGE_MEM_MAP);
    assert(contains_substr(boot_stage_get_failure_reason(), "backward"));

    printf("PASS\n");
}

static void test_stage_failsafe_preserves_last_successful(void)
{
    printf("[C-TEST] Running: test_stage_failsafe_preserves_last_successful... ");
    boot_stage_reset_for_test();

    boot_stage_set(BOOT_STAGE_ENTRY);
    boot_stage_set(BOOT_STAGE_RAM_LOG);
    boot_stage_set(BOOT_STAGE_BOOT_ARGS);

    /* Trigger failsafe at STAGE 2 */
    g_intercept_failsafe = true;
    if (setjmp(g_failsafe_jmp) == 0) {
        boot_stage_failsafe("Simulated hardware error at stage 2");
        assert(false && "failsafe should never return!");
    }
    g_intercept_failsafe = false;

    assert(boot_stage_get() == BOOT_STAGE_ERROR);
    assert(boot_stage_get_last_successful() == BOOT_STAGE_BOOT_ARGS);
    assert(boot_stage_get_failure_stage() == BOOT_STAGE_BOOT_ARGS);
    assert(strcmp(boot_stage_get_failure_reason(), "Simulated hardware error at stage 2") == 0);

    printf("PASS\n");
}

/* ============================================================
 * Tests: Framebuffer Hard Safety Interlock
 * ============================================================ */

static void test_framebuffer_mapping_interlock(void)
{
    printf("[C-TEST] Running: test_framebuffer_mapping_interlock... ");

    /* Allocate dummy buffer for software framebuffer testing */
    uint32_t width = 100;
    uint32_t height = 100;
    uint32_t row_bytes = width * 4;
    size_t buf_size = (size_t)row_bytes * height;
    uint8_t *fb_mem = (uint8_t *)calloc(1, buf_size);
    assert(fb_mem != NULL);

    boot_framebuffer_info_t info = {
        .base_paddr = (uint64_t)(uintptr_t)fb_mem,
        .size       = buf_size,
        .width      = width,
        .height     = height,
        .row_bytes  = row_bytes,
        .depth      = 32,
        .is_valid   = true,
        .source     = "host_test"
    };

    int rc = framebuffer_init(&info);
    assert(rc == 0);
    assert(framebuffer_is_available() == true);

    /* 1. Invariant: mapping_verified must be FALSE by default */
    assert(framebuffer_is_mapping_verified() == false);

    /* 2. Invariant: enable_writes(true) MUST NOT succeed while mapping is unverified! */
    framebuffer_enable_writes(true);
    const framebuffer_t *fb_desc = framebuffer_get_info();
    assert(fb_desc != NULL);
    assert(fb_desc->is_write_allowed == false);

    /* 3. Invariant: Attempting to put_pixel must NOT write anything */
    framebuffer_put_pixel(10, 10, 0x00FF0000);
    uint32_t *pixels = (uint32_t *)fb_mem;
    assert(pixels[10 * width + 10] == 0); /* Still zero! */

    /* 4. A verification bit alone cannot promote PA to VA. */
    framebuffer_set_mapping_verified_for_test(true);
    assert(framebuffer_is_mapping_verified() == false);
    assert(fb_desc->is_write_allowed == false);

    /* Host-only model supplies a concrete VA; production has no such setter. */
    framebuffer_set_virtual_base_for_test((uintptr_t)fb_mem);
    framebuffer_set_mapping_verified_for_test(true);
    assert(framebuffer_is_mapping_verified() == true);

    framebuffer_enable_writes(true);
    assert(fb_desc->is_write_allowed == true);

    /* 5. With mapping verified and writes allowed: put_pixel succeeds */
    framebuffer_put_pixel(10, 10, 0x00FF0000);
    assert(pixels[10 * width + 10] == 0x00FF0000);

    /* 6. Revoking mapping verification immediately revokes write permission */
    framebuffer_set_mapping_verified_for_test(false);
    assert(framebuffer_is_mapping_verified() == false);
    assert(fb_desc->is_write_allowed == false);

    /* 7. Writes blocked again */
    framebuffer_put_pixel(20, 20, 0x0000FF00);
    assert(pixels[20 * width + 20] == 0);

    free(fb_mem);
    printf("PASS\n");
}

static void test_devtree_bounds_and_boot_args(void)
{
    printf("[C-TEST] Running: test_devtree_bounds_and_boot_args... ");

    unsigned char tree[96];
    memset(tree, 0, sizeof(tree));
    *(unsigned int *)(void *)(tree + 0) = 1; /* properties */
    *(unsigned int *)(void *)(tree + 4) = 0; /* children */
    {
        const unsigned char name[] = "root";
        make_prop(tree + 8, "name", name, sizeof(name));
    }

    assert(devtree_validate_header((uintptr_t)tree, sizeof(tree)) == true);
    assert(devtree_validate_header((uintptr_t)tree, 8 + sizeof(adt_prop_hdr_t)) == false);

    /* Truncated property value and excessive child count must be rejected. */
    *(unsigned int *)(void *)(tree + 32 + 8) = 0x7FFFFFFFU;
    assert(devtree_validate_header((uintptr_t)tree, sizeof(tree)) == false);
    memset(tree, 0, sizeof(tree));
    *(unsigned int *)(void *)(tree + 4) = 0xFFFFFFFFU;
    assert(devtree_find_node_by_path((uintptr_t)tree, sizeof(tree), "/missing") == 0);

    /* Unverified x0/x1 are preserved but never dereferenced or parsed. */
    platform_boot_info_init(0xDEAD000000001234ULL, UINT64_MAX);
    const platform_boot_info_t *info = platform_get_boot_info();
    assert(loader_handoff_is_verified() == false);
    assert(info->boot_args_present == false);
    assert(info->devtree_present == false);
    assert(info->metadata_status == BOOT_METADATA_STATIC_FALLBACK);

    /* A direct ADT pointer with unavailable length is never scanned/guessed. */
    unsigned char raw_tree[96];
    memset(raw_tree, 0, sizeof(raw_tree));
    *(unsigned int *)(void *)(raw_tree + 0) = 1;
    {
        const unsigned char name[] = "root";
        make_prop(raw_tree + 8, "name", name, sizeof(name));
    }
    platform_boot_info_init((uint64_t)(uintptr_t)raw_tree, 0);
    info = platform_get_boot_info();
    assert(loader_handoff_is_verified() == false);
    assert(info->devtree_present == false);
    assert(info->metadata_status == BOOT_METADATA_STATIC_FALLBACK);

    printf("PASS\n");
}

static void make_verified_descriptor(loader_handoff_descriptor_t *descriptor,
                                     uintptr_t raw_x0,
                                     uint64_t raw_x1,
                                     uintptr_t boot_args_base,
                                     size_t boot_args_length,
                                     uintptr_t dt_base,
                                     size_t dt_length)
{
    memset(descriptor, 0, sizeof(*descriptor));
    descriptor->magic = DREYZE_HANDOFF_MAGIC;
    descriptor->version = DREYZE_HANDOFF_VERSION;
    descriptor->size = sizeof(*descriptor);
    descriptor->flags = DREYZE_HANDOFF_FLAG_VERIFIED;
    descriptor->raw_x0 = raw_x0;
    descriptor->raw_x1 = raw_x1;
    descriptor->boot_args_range.base = boot_args_base;
    descriptor->boot_args_range.length = boot_args_length;
    descriptor->boot_args_range.flags = DREYZE_HANDOFF_RANGE_FLAG_READABLE;
    descriptor->boot_args_range.reserved = 0;
    descriptor->device_tree_range.base = dt_base;
    descriptor->device_tree_range.length = dt_length;
    descriptor->device_tree_range.flags = DREYZE_HANDOFF_RANGE_FLAG_READABLE;
    descriptor->device_tree_range.reserved = 0;
}

static void test_handoff_descriptor_and_ranges(void)
{
    printf("[C-TEST] Running: test_handoff_descriptor_and_ranges... ");

    /* The wire ABI has exact, reviewable offsets independent of host types. */
    assert(sizeof(loader_handoff_range_v1_t) == 24);
    assert(sizeof(loader_handoff_descriptor_t) == 128);
    assert(offsetof(loader_handoff_descriptor_t, magic) == 0);
    assert(offsetof(loader_handoff_descriptor_t, version) == 8);
    assert(offsetof(loader_handoff_descriptor_t, size) == 12);
    assert(offsetof(loader_handoff_descriptor_t, flags) == 16);
    assert(offsetof(loader_handoff_descriptor_t, entry_el) == 24);
    assert(offsetof(loader_handoff_descriptor_t, payload_pa) == 32);
    assert(offsetof(loader_handoff_descriptor_t, payload_va) == 40);
    assert(offsetof(loader_handoff_descriptor_t, payload_size) == 48);
    assert(offsetof(loader_handoff_descriptor_t, mmu_enabled) == 56);
    assert(offsetof(loader_handoff_descriptor_t, raw_x0) == 64);
    assert(offsetof(loader_handoff_descriptor_t, raw_x1) == 72);
    assert(offsetof(loader_handoff_descriptor_t, boot_args_range) == 80);
    assert(offsetof(loader_handoff_descriptor_t, device_tree_range) == 104);

    uintptr_t converted_base = 0;
    size_t converted_length = 0;
    assert(loader_handoff_u64_to_uintptr(0, &converted_base) == true);
    assert(loader_handoff_u64_to_size(0, &converted_length) == true);
#if UINTPTR_MAX < UINT64_MAX
    assert(loader_handoff_u64_to_uintptr(UINTPTR_MAX + 1ULL,
                                         &converted_base) == false);
#else
    assert(loader_handoff_u64_to_uintptr(UINT64_MAX,
                                         &converted_base) == true);
#endif
#if SIZE_MAX < UINT64_MAX
    assert(loader_handoff_u64_to_size((uint64_t)SIZE_MAX + 1ULL,
                                      &converted_length) == false);
#else
    assert(loader_handoff_u64_to_size(UINT64_MAX,
                                      &converted_length) == true);
#endif

    loader_handoff_range_v1_t wire_range = {
        .base = 0x1000,
        .length = 0x100,
        .flags = DREYZE_HANDOFF_RANGE_FLAG_READABLE,
        .reserved = 0
    };
    verified_range_t native_range;
    assert(loader_handoff_range_to_native(&wire_range, &native_range) == true);
    wire_range.flags = 0;
    assert(loader_handoff_range_to_native(&wire_range, &native_range) == false);
    wire_range.flags = DREYZE_HANDOFF_RANGE_FLAG_READABLE;
    wire_range.length = 0;
    assert(loader_handoff_range_to_native(&wire_range, &native_range) == false);

    /* Generic containment: exact end is valid only for a non-empty fit. */
    verified_range_t range = { 0x1000, 0x100, true };
    assert(verified_range_is_valid(&range) == true);
    assert(verified_range_contains(&range, 0x1000, 1) == true);
    assert(verified_range_contains_object(&range, 0x10FF, 1) == true);
    assert(verified_range_contains(&range, 0x1100, 1) == false);
    assert(verified_range_contains(&range, 0x1000, 0) == false);

    verified_range_t non_readable = { 0x1000, 0x100, false };
    assert(verified_range_is_valid(&non_readable) == false);
    verified_range_t null_range = { 0, 1, true };
    assert(verified_range_is_valid(&null_range) == false);

    verified_range_t max_overflow = { UINTPTR_MAX - 1, 2, true };
    assert(verified_range_is_valid(&max_overflow) == false);
    verified_range_t max_edge = { UINTPTR_MAX - 1, 1, true };
    assert(verified_range_is_valid(&max_edge) == true);
    assert(verified_range_contains(&max_edge, UINTPTR_MAX - 1, 1) == true);
    assert(verified_range_contains(&max_edge, UINTPTR_MAX, 1) == false);

    xnu_arm64_boot_args_t ba;
    memset(&ba, 0, sizeof(ba));
    /* Host fixture only: historical research values, not a runtime map. */
    ba.phys_base = 0x800000000ULL;
    ba.mem_size = 0x40000000ULL;
    ba.virt_base = 0xFFFF000080000000ULL;

    unsigned char nested_tree[96];
    memset(nested_tree, 0, sizeof(nested_tree));
    *(unsigned int *)(void *)(nested_tree + 0) = 1;
    *(unsigned int *)(void *)(nested_tree + 4) = 0;
    {
        const unsigned char name[] = "root";
        make_prop(nested_tree + 8, "name", name, sizeof(name));
    }

    loader_handoff_descriptor_t descriptor;

    /* Structural validation rejects malformed identity/version/size fields. */
    make_verified_descriptor(&descriptor, (uintptr_t)&ba, 0,
                             (uintptr_t)&ba, sizeof(ba),
                             (uintptr_t)nested_tree, sizeof(nested_tree));
    descriptor.magic ^= 1ULL;
    loader_handoff_set_verified_for_test(&descriptor);
    assert(loader_handoff_get()->magic != DREYZE_HANDOFF_MAGIC);
    assert(loader_handoff_is_verified() == false);

    /* V1 rejects contradictory known-state combinations. */
    make_verified_descriptor(&descriptor, (uintptr_t)&ba, 0,
                             (uintptr_t)&ba, sizeof(ba),
                             (uintptr_t)nested_tree, sizeof(nested_tree));
    descriptor.flags |= DREYZE_HANDOFF_FLAG_ENTRY_EL_KNOWN;
    descriptor.entry_el = 0;
    assert(loader_handoff_descriptor_validate(&descriptor) == false);
    descriptor.entry_el = 1;
    assert(loader_handoff_descriptor_validate(&descriptor) == true);

    descriptor.flags |= DREYZE_HANDOFF_FLAG_PAYLOAD_LOCATION_KNOWN;
    /* Host fixture only: payload PA is deliberately illustrative. */
    descriptor.payload_pa = 0x800000000ULL;
    descriptor.payload_va = 0x100000000ULL;
    descriptor.payload_size = 0;
    assert(loader_handoff_descriptor_validate(&descriptor) == false);
    descriptor.payload_size = 0x1000;
    assert(loader_handoff_descriptor_validate(&descriptor) == true);
    descriptor.payload_pa = UINT64_MAX - 0x7FFULL;
    assert(loader_handoff_descriptor_validate(&descriptor) == false);

    make_verified_descriptor(&descriptor, (uintptr_t)&ba, 0,
                             (uintptr_t)&ba, sizeof(ba),
                             (uintptr_t)nested_tree, sizeof(nested_tree));
    descriptor.flags |= DREYZE_HANDOFF_FLAG_MMIO_MAPPING_VALID;
    assert(loader_handoff_descriptor_validate(&descriptor) == false);
    descriptor.flags |= DREYZE_HANDOFF_FLAG_MAPPING_STATE_KNOWN;
    assert(loader_handoff_descriptor_validate(&descriptor) == true);
    descriptor.flags |= DREYZE_HANDOFF_FLAG_UART_MAPPING_VALID;
    assert(loader_handoff_descriptor_validate(&descriptor) == true);
    descriptor.flags &= ~DREYZE_HANDOFF_FLAG_MMIO_MAPPING_VALID;
    assert(loader_handoff_descriptor_validate(&descriptor) == false);

    make_verified_descriptor(&descriptor, (uintptr_t)&ba, 0,
                             (uintptr_t)&ba, sizeof(ba),
                             (uintptr_t)nested_tree, sizeof(nested_tree));
    descriptor.version = DREYZE_HANDOFF_VERSION + 1U;
    assert(loader_handoff_descriptor_validate(&descriptor) == false);
    platform_boot_info_init_verified_for_test(&descriptor, true);
    assert(loader_handoff_is_verified() == false);

    make_verified_descriptor(&descriptor, (uintptr_t)&ba, 0,
                             (uintptr_t)&ba, sizeof(ba),
                             (uintptr_t)nested_tree, sizeof(nested_tree));
    descriptor.size = DREYZE_HANDOFF_V1_SIZE - 1U;
    assert(loader_handoff_descriptor_validate(&descriptor) == false);
    platform_boot_info_init_verified_for_test(&descriptor, true);
    assert(loader_handoff_is_verified() == false);

    /* Full boot_args object is mandatory before any copy. */
    make_verified_descriptor(&descriptor, (uintptr_t)&ba, 0,
                             (uintptr_t)&ba, sizeof(ba) - 1,
                             (uintptr_t)nested_tree, sizeof(nested_tree));
    platform_boot_info_init_verified_for_test(&descriptor, true);
    const platform_boot_info_t *info = platform_get_boot_info();
    assert(loader_handoff_is_verified() == true);
    assert(info->boot_args_present == false);
    assert(info->metadata_status != BOOT_METADATA_RUNTIME_VERIFIED);

    /* An arbitrary untrusted pointer still cannot be dereferenced. */
    make_verified_descriptor(&descriptor, UINTPTR_MAX, 0,
                             (uintptr_t)&ba, sizeof(ba),
                             (uintptr_t)nested_tree, sizeof(nested_tree));
    platform_boot_info_init_verified_for_test(&descriptor, true);
    info = platform_get_boot_info();
    assert(info->boot_args_present == false);

    ba.devicetree_p = (uint64_t)(uintptr_t)nested_tree;
    ba.devicetree_length = sizeof(nested_tree);

    /* Nested pointer outside the independently verified range: reject. */
    make_verified_descriptor(&descriptor, (uintptr_t)&ba, 0,
                             (uintptr_t)&ba, sizeof(ba),
                             (uintptr_t)(nested_tree + sizeof(nested_tree)), 1);
    platform_boot_info_init_verified_for_test(&descriptor, true);
    info = platform_get_boot_info();
    assert(info->boot_args_present == true);
    assert(info->devtree_present == false);

    /* Nested pointer partially overlaps the range: reject the whole object. */
    make_verified_descriptor(&descriptor, (uintptr_t)&ba, 0,
                             (uintptr_t)&ba, sizeof(ba),
                             (uintptr_t)(nested_tree + 1), sizeof(nested_tree) - 1);
    platform_boot_info_init_verified_for_test(&descriptor, true);
    info = platform_get_boot_info();
    assert(info->boot_args_present == true);
    assert(info->devtree_present == false);

    /* Exact nested pointer and exact bounded length: parse is permitted. */
    make_verified_descriptor(&descriptor, (uintptr_t)&ba, 0,
                             (uintptr_t)&ba, sizeof(ba),
                             (uintptr_t)nested_tree, sizeof(nested_tree));
    platform_boot_info_init_verified_for_test(&descriptor, true);
    info = platform_get_boot_info();
    assert(info->boot_args_present == true);
    assert(info->devtree_present == true);
    assert(info->metadata_status == BOOT_METADATA_RUNTIME_VERIFIED);
    assert(info->dram_phys_base == ba.phys_base);
    assert(info->dram_size == ba.mem_size);
    assert(info->dram_virt_base == ba.virt_base);
    assert(info->virt_base_valid == true);

    /* A larger V1-compatible descriptor is accepted without reading its tail. */
    descriptor.size = DREYZE_HANDOFF_V1_SIZE + 64U;
    assert(loader_handoff_descriptor_validate(&descriptor) == true);
    platform_boot_info_init_verified_for_test(&descriptor, true);
    info = platform_get_boot_info();
    assert(loader_handoff_is_verified() == true);
    assert(info->metadata_status == BOOT_METADATA_RUNTIME_VERIFIED);

    /* Direct ADT handoff also requires an explicit x1 length and DT range. */
    make_verified_descriptor(&descriptor, (uintptr_t)nested_tree,
                             sizeof(nested_tree), (uintptr_t)&ba, sizeof(ba),
                             (uintptr_t)nested_tree, sizeof(nested_tree));
    platform_boot_info_init_verified_for_test(&descriptor, false);
    info = platform_get_boot_info();
    assert(info->boot_args_present == false);
    assert(info->devtree_present == true);
    assert(info->devtree_size == sizeof(nested_tree));
    assert(info->metadata_status == BOOT_METADATA_STATIC_FALLBACK);
    assert(info->dram_phys_base == 0);
    assert(info->dram_size == 0);
    assert(info->dram_virt_base == 0);
    assert(info->virt_base_valid == false);

    /* The descriptor, not platform_boot_info_t, is the sole trust state. */
    platform_boot_info_init(UINTPTR_MAX, UINTPTR_MAX);
    assert(loader_handoff_is_verified() == false);
    assert(loader_handoff_get()->raw_x0 == UINTPTR_MAX);
    assert(loader_handoff_get()->raw_x1 == UINTPTR_MAX);
    assert(info->metadata_status == BOOT_METADATA_STATIC_FALLBACK);
    assert(info->dram_phys_base == 0);
    assert(info->dram_size == 0);
    assert(info->dram_virt_base == 0);
    assert(info->virt_base_valid == false);

    printf("PASS\n");
}

static void test_pre_hardware_mmio_gate(void)
{
    printf("[C-TEST] Running: test_pre_hardware_mmio_gate... ");

    mmio_mapping_set_verified_for_test(false);
    uart_reset_mmio_access_count_for_test();
    aic_reset_mmio_access_count_for_test();

    log_init();
    assert(log_is_ram_ready() == true);
    assert(log_is_uart_ready() == false);
    klog_info("RAM logging works without UART MMIO");

    /* Exercise the actual pre-hardware platform and driver paths. */
    platform_init();
    uart_init();
    uart_putc('x');
    uart_diag();
    aic_init();
    aic_diag();
    aic_enable_irq(1);
    aic_mask_all();

    assert(uart_mmio_access_count_for_test() == 0);
    assert(aic_mmio_access_count_for_test() == 0);
    assert(aic_is_initialized() == false);
    assert(log_is_uart_ready() == false);

    uint32_t bytes = 0;
    assert(klog_get_buffer(&bytes, NULL) != NULL && bytes > 0);
    printf("PASS\n");
}

int main(void)
{
    printf("\n==================================================\n");
    printf("DreyzeOS C-Level Host Test Suite\n");
    printf("==================================================\n");

    test_stage_sequential_progression();
    test_stage_invalid_backward_transition();
    test_stage_failsafe_preserves_last_successful();
    test_framebuffer_mapping_interlock();
    test_devtree_bounds_and_boot_args();
    test_handoff_descriptor_and_ranges();
    test_pre_hardware_mmio_gate();
    pic_stage0_host_run_self_tests();

    printf("==================================================\n");
    printf("All C-Level Host Tests PASSED (8/8) ✓\n");
    printf("==================================================\n\n");

    return 0;
}

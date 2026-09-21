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
#include "../hal/t8006/uart.h"
#include "../hal/t8006/aic.h"
#include "../hal/t8006/platform.h"
#include "../include/log.h"

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

    /* 4. When mapping is explicitly verified: writes can be enabled */
    framebuffer_set_mapping_verified(true);
    assert(framebuffer_is_mapping_verified() == true);

    framebuffer_enable_writes(true);
    assert(fb_desc->is_write_allowed == true);

    /* 5. With mapping verified and writes allowed: put_pixel succeeds */
    framebuffer_put_pixel(10, 10, 0x00FF0000);
    assert(pixels[10 * width + 10] == 0x00FF0000);

    /* 6. Revoking mapping verification immediately revokes write permission */
    framebuffer_set_mapping_verified(false);
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

    xnu_arm64_boot_args_t ba;
    memset(&ba, 0, sizeof(ba));
    ba.phys_base = 0x800000000ULL;
    ba.mem_size = 0x40000000ULL;
    ba.virt_base = 0xFFFF000080000000ULL;
    platform_boot_info_init((uint64_t)(uintptr_t)&ba, 0);
    const platform_boot_info_t *info = platform_get_boot_info();
    assert(info->boot_args_present == true);
    assert(info->virt_base_valid == true);
    assert(info->dram_virt_base == ba.virt_base);
    assert(info->dram_virt_base != info->dram_phys_base);

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
    test_pre_hardware_mmio_gate();

    printf("==================================================\n");
    printf("All C-Level Host Tests PASSED (6/6) ✓\n");
    printf("==================================================\n\n");

    return 0;
}

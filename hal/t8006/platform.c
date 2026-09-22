/*
 * DreyzeOS — T8006 Platform Implementation
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Phase 1: All stubs. Hardware registers UNKNOWN.
 * Phase 3+: Real implementations after hardware research.
 */

#include "platform.h"
#include "memory_map.h"
#include "mmio_gate.h"
#include "../../include/log.h"

/* Platform info — populated from DeviceTree in Phase 3 */
static platform_info_t g_platform_info = {
    .model_identifier = "Watch4,?",  /* UNKNOWN until DeviceTree parsed */
    .chip_id          = 0x8006,       /* T8006 chip ID — LIKELY */
    .board_id         = 0xFFFFFFFF,   /* UNKNOWN */
    .display_width    = 0,            /* UNKNOWN until model confirmed */
    .display_height   = 0,            /* UNKNOWN until model confirmed */
    .has_cellular     = false,        /* UNKNOWN */
};

/*
 * platform_early_init — called before logging is available.
 * Must be minimal and safe.
 */
void platform_early_init(void)
{
    /*
     * Phase 1: Nothing safe to do here without confirmed MMIO addresses.
     * Future: could read chip ID register to confirm T8006.
     * Chip ID register base: UNKNOWN_T8006_FUSE_BASE (not defined yet)
     */

    /* Data sync barrier — ensure any prior writes are complete */
#ifndef HOST_TEST
    __asm__ volatile ("dsb sy" ::: "memory");
    __asm__ volatile ("isb" ::: "memory");
#endif
}

#include "uart.h"
#include "aic.h"

/*
 * platform_init — called after RAM logging is available.
 * MMIO subsystems remain untouched until their virtual mapping is proven.
 */
void platform_init(void)
{
    klog_info("  [HAL] T8006 platform_init begin");
    klog_info("  [HAL] Chip: T8006 (Apple S4 SiP / dual-core Tempest)");
    if (!mmio_mapping_is_verified()) {
        klog_info("  [HAL] MMIO mapping: UNVERIFIED; UART/AIC left untouched");
        return;
    }

    klog_info("  [HAL] MMIO mapping verified by loader contract");
    uart_diag();
    aic_init();
    aic_diag();

    klog_info("  [HAL] T8006 platform_init complete");
}

/*
 * timer_init — stub.
 * Phase 6: Initialize Apple PMGR timer or ARM generic timer.
 * CNTFRQ_EL0 is the authoritative runtime frequency source; no static
 * T8006 frequency is asserted here.
 */
void timer_init(void)
{
    klog_info("  [TIMER] timer_init: STUB — awaiting Phase 6");
    /*
     * ARM generic timer is accessible without MMIO:
     *   CNTFRQ_EL0 — counter frequency
     *   CNTPCT_EL0 — physical counter
     * These are available regardless of T8006 MMIO mapping.
     */
    uint64_t cntfrq = 0;
#ifndef HOST_TEST
    __asm__ volatile ("mrs %0, cntfrq_el0" : "=r"(cntfrq));
#endif
    klog_hex("  [TIMER] CNTFRQ_EL0 (ARM generic timer freq)", cntfrq);
}

/*
 * display_init — stub.
 * Phase 7: Initialize display controller and framebuffer.
 * Requires: UNKNOWN_T8006_FRAMEBUFFER_BASE from DeviceTree.
 */
void display_init(void)
{
    klog_info("  [DISP] display_init: STUB — awaiting Phase 7");
    klog_info("  [DISP] Requires UNKNOWN_T8006_FRAMEBUFFER_BASE from DeviceTree");
}

/*
 * touch_init — stub.
 * Phase 9: Initialize touch controller.
 */
void touch_init(void)
{
    klog_info("  [TOUCH] touch_init: STUB — awaiting Phase 9");
}

/*
 * crown_init — stub.
 * Phase 8: Initialize Digital Crown.
 */
void crown_init(void)
{
    klog_info("  [CROWN] crown_init: STUB — awaiting Phase 8");
}

/*
 * button_init — stub.
 * Phase 8: Initialize side button GPIO.
 */
void button_init(void)
{
    klog_info("  [BTN] button_init: STUB — awaiting Phase 8");
}

const platform_info_t *platform_get_info(void)
{
    return &g_platform_info;
}

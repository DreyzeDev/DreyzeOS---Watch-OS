/*
 * DreyzeOS — Boot Stage Tracking & Failsafe Implementation
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Implements monotonic milestone tracking, separate last-successful-stage
 * recording, and emergency failsafe halting.
 */

#include "../include/boot_stage.h"
#include "../include/log.h"
#include "../hal/t8006/framebuffer.h"
#include "../hal/t8006/aic.h"

/* Defined in boot/entry.S as a global assembly function */
extern void arch_irq_disable(void);

static boot_stage_t g_current_stage = BOOT_STAGE_ENTRY;
static boot_stage_t g_last_successful_stage = BOOT_STAGE_ENTRY;

void boot_stage_set(boot_stage_t stage)
{
    g_current_stage = stage;
    if (stage != BOOT_STAGE_ERROR) {
        g_last_successful_stage = stage;
    }
    klog_info("--> [BOOT-STAGE] Reached ");
    klog_info(boot_stage_name(stage));
}

boot_stage_t boot_stage_get(void)
{
    return g_current_stage;
}

boot_stage_t boot_stage_get_last_successful(void)
{
    return g_last_successful_stage;
}

const char *boot_stage_name(boot_stage_t stage)
{
    switch (stage) {
        case BOOT_STAGE_ENTRY:     return "STAGE 0: Entry Reached";
        case BOOT_STAGE_UART:      return "STAGE 1: UART / Early HAL";
        case BOOT_STAGE_BOOT_ARGS: return "STAGE 2: Boot Args & DeviceTree";
        case BOOT_STAGE_MEM_MAP:   return "STAGE 3: Memory Map";
        case BOOT_STAGE_AIC:       return "STAGE 4: AIC Controller";
        case BOOT_STAGE_FB:        return "STAGE 5: Framebuffer Validated";
        case BOOT_STAGE_IDLE:      return "STAGE 6: Safe Idle (WFI)";
        case BOOT_STAGE_ERROR:     return "STAGE ERROR: Failsafe Halted";
        default:                   return "STAGE UNKNOWN";
    }
}

void boot_stage_failsafe(const char *reason)
{
    /* 1. Mark state as error, keeping last successful stage preserved */
    g_current_stage = BOOT_STAGE_ERROR;

    /* 2. Enforce strict safety interlocks */
    framebuffer_enable_writes(false);
    arch_irq_disable();

    /* 3. Diagnostic reporting */
    klog_info("");
    klog_info("**************************************************");
    klog_info("  [FAILSAFE] CRITICAL HARDWARE BRING-UP FAILSAFE  ");
    klog_info("**************************************************");
    if (reason) {
        klog_info("  Reason: ");
        klog_info(reason);
    }
    klog_info("  Last successful stage: ");
    klog_info(boot_stage_name(g_last_successful_stage));
    klog_info("  Safety status:");
    klog_info("    - Framebuffer writes: FORCED OFF");
    klog_info("    - Interrupts: DISABLED");
    klog_info("    - NAND/Flash: UNTOUCHED (Zero writes)");
    klog_info("  Recovery: Crown + Side Button hard reset is the expected hardware reset path.");
    klog_info("            Actual recovery capability confirmed only after controlled hardware test.");
    klog_info("**************************************************");

    log_flush();

    /* 4. Safe infinite halt */
    for (;;) {
        __asm__ volatile("wfi");
    }
}

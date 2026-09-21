/*
 * DreyzeOS — Boot Stage Tracking & Failsafe Implementation
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Implements monotonic milestone tracking, separate last-successful-stage
 * recording, pre-UART / post-UART failsafe halting, and test support.
 */

#include "../include/boot_stage.h"
#include "../include/log.h"
#include "../hal/t8006/framebuffer.h"
#include "../hal/t8006/aic.h"

/* Defined in boot/entry.S as a global assembly function */
extern void arch_irq_disable(void);

static boot_stage_t g_current_stage = BOOT_STAGE_ENTRY;
static boot_stage_t g_last_successful_stage = BOOT_STAGE_ENTRY;
static boot_stage_t g_failure_stage = BOOT_STAGE_ENTRY;
static const char  *g_failure_reason = NULL;

void boot_stage_set(boot_stage_t stage)
{
    if (stage == BOOT_STAGE_ERROR) {
        boot_stage_failsafe("Explicit BOOT_STAGE_ERROR requested");
        return;
    }

    /* Monotonicity check: backwards transitions are illegal in production boot */
    if (stage < g_current_stage) {
        boot_stage_failsafe("Illegal backward boot stage transition");
        return;
    }

    g_current_stage = stage;
    g_last_successful_stage = stage;

    /*
     * Only log stage advance if UART/logging has been reached (STAGE 1+).
     * At STAGE 0, UART is not yet initialized.
     */
    if (stage >= BOOT_STAGE_UART) {
        klog_info("--> [BOOT-STAGE] Reached ");
        klog_info(boot_stage_name(stage));
    }
}

boot_stage_t boot_stage_get(void)
{
    return g_current_stage;
}

boot_stage_t boot_stage_get_last_successful(void)
{
    return g_last_successful_stage;
}

boot_stage_t boot_stage_get_failure_stage(void)
{
    return g_failure_stage;
}

const char *boot_stage_get_failure_reason(void)
{
    return g_failure_reason;
}

const char *boot_stage_name(boot_stage_t stage)
{
    switch (stage) {
        case BOOT_STAGE_ENTRY:     return "STAGE 0: Entry Reached";
        case BOOT_STAGE_UART:      return "STAGE 1: UART / Early HAL";
        case BOOT_STAGE_BOOT_ARGS: return "STAGE 2: Boot Args & DeviceTree";
        case BOOT_STAGE_MEM_MAP:   return "STAGE 3: Memory Map";
        case BOOT_STAGE_AIC:       return "STAGE 4: AIC Controller";
        case BOOT_STAGE_FB:        return "STAGE 5: Framebuffer Evaluated";
        case BOOT_STAGE_IDLE:      return "STAGE 6: Safe Idle (WFI)";
        case BOOT_STAGE_ERROR:     return "STAGE ERROR: Failsafe Halted";
        default:                   return "STAGE UNKNOWN";
    }
}

void boot_stage_failsafe(const char *reason)
{
    /* 1. Record failure details while strictly preserving last successful stage */
    g_failure_stage = g_current_stage;
    g_failure_reason = reason;
    g_current_stage = BOOT_STAGE_ERROR;

    /* 2. Enforce strict hardware safety interlocks */
    framebuffer_enable_writes(false);
    arch_irq_disable();

    /*
     * 3. Pre-UART vs. Post-UART Failsafe:
     * If failure occurred before UART was initialized (pre-Stage 1),
     * we CANNOT call klog_info or log_flush without risking recursive faults.
     * Simply halt safely with WFI.
     */
    if (g_last_successful_stage < BOOT_STAGE_UART) {
#ifdef HOST_TEST
        extern void host_test_halt_intercept(void);
        host_test_halt_intercept();
#else
        for (;;) {
            __asm__ volatile("wfi");
        }
#endif
    }

    /* 4. Post-UART: Diagnostic reporting is safe */
    klog_info("");
    klog_info("**************************************************");
    klog_info("  [FAILSAFE] CRITICAL HARDWARE BRING-UP FAILSAFE  ");
    klog_info("**************************************************");
    if (reason) {
        klog_info("  Reason: ");
        klog_info(reason);
    }
    klog_info("  Failure stage: ");
    klog_info(boot_stage_name(g_failure_stage));
    klog_info("  Last successful stage: ");
    klog_info(boot_stage_name(g_last_successful_stage));
    klog_info("  Safety status:");
    klog_info("    - Framebuffer writes: FORCED OFF");
    klog_info("    - Interrupts: DISABLED");
    klog_info("    - NAND/Flash: UNTOUCHED (Zero writes)");
    klog_info("  Recovery: Crown + Side Button reset is the expected stock hardware reset path,");
    klog_info("            but recovery from an arbitrary experimental state has not yet been");
    klog_info("            validated by a controlled DreyzeOS hardware test.");
    klog_info("**************************************************");

    log_flush();

    /* 5. Safe infinite halt (intercepted during host testing) */
#ifdef HOST_TEST
    extern void host_test_halt_intercept(void);
    host_test_halt_intercept();
#else
    for (;;) {
        __asm__ volatile("wfi");
    }
#endif
}

void boot_stage_reset_for_test(void)
{
    g_current_stage = BOOT_STAGE_ENTRY;
    g_last_successful_stage = BOOT_STAGE_ENTRY;
    g_failure_stage = BOOT_STAGE_ENTRY;
    g_failure_reason = NULL;
}

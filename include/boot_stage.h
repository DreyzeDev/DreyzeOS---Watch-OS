/*
 * DreyzeOS — Boot Stage Tracking & Failsafe Header
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Provides structured monotonic tracking of boot milestones, separate
 * last-successful stage preservation, and pre-UART / post-UART failsafe handling.
 */

#pragma once

#include "types.h"

/*
 * Boot Stages:
 * Strictly monotonically increasing milestones during kernel initialization.
 */
typedef enum {
    BOOT_STAGE_ENTRY     = 0,   /* STAGE 0: entry reached (entry.S -> kernel_main) */
    BOOT_STAGE_UART      = 1,   /* STAGE 1: early platform init & UART0 initialized */
    BOOT_STAGE_BOOT_ARGS = 2,   /* STAGE 2: boot_args / DeviceTree validated */
    BOOT_STAGE_MEM_MAP   = 3,   /* STAGE 3: memory map validated (DRAM & reservations) */
    BOOT_STAGE_AIC       = 4,   /* STAGE 4: AIC initialized & masked */
    BOOT_STAGE_FB        = 5,   /* STAGE 5: framebuffer evaluated */
    BOOT_STAGE_IDLE      = 6,   /* STAGE 6: system safely idle in low-power WFI loop */
    BOOT_STAGE_ERROR     = 0xFF /* Failsafe triggered: execution halted */
} boot_stage_t;

/*
 * Set current boot stage.
 * Enforces strict monotonic progression: rejecting backward transitions.
 */
void boot_stage_set(boot_stage_t stage);

/* Retrieve current boot stage (BOOT_STAGE_ERROR if failsafe triggered) */
boot_stage_t boot_stage_get(void);

/* Retrieve last successfully completed boot stage prior to any error */
boot_stage_t boot_stage_get_last_successful(void);

/* Retrieve stage where failure occurred (if in ERROR state) */
boot_stage_t boot_stage_get_failure_stage(void);

/* Retrieve failure reason string (if in ERROR state) */
const char *boot_stage_get_failure_reason(void);

/* Get human-readable string name for a boot stage */
const char *boot_stage_name(boot_stage_t stage);

/*
 * Failsafe handler:
 * Pre-UART: Disables IRQs, disables FB writes, records failure state in RAM, halts via WFI.
 *           NEVER calls klog/log_flush to avoid recursive exceptions.
 * Post-UART: Logs full diagnostic crash dump, flushes UART, halts via WFI.
 *
 * This function NEVER returns.
 */
void boot_stage_failsafe(const char *reason);

/* Reset boot stage state machine — strictly for unit tests */
void boot_stage_reset_for_test(void);

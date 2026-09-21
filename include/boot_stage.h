/*
 * DreyzeOS — Boot Stage Tracking & Failsafe Header
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Provides structured tracking of boot milestones and emergency failsafe handling.
 */

#pragma once

#include "types.h"

/*
 * Boot Stages:
 * Monotonically increasing milestones during kernel initialization.
 */
typedef enum {
    BOOT_STAGE_ENTRY     = 0, /* STAGE 0: entry reached (entry.S -> kernel_main) */
    BOOT_STAGE_UART      = 1, /* STAGE 1: early platform init & UART0 initialized */
    BOOT_STAGE_BOOT_ARGS = 2, /* STAGE 2: boot_args / DeviceTree validated */
    BOOT_STAGE_MEM_MAP   = 3, /* STAGE 3: memory map validated (DRAM & reservations) */
    BOOT_STAGE_AIC       = 4, /* STAGE 4: AIC initialized & masked */
    BOOT_STAGE_FB        = 5, /* STAGE 5: framebuffer validated (writes disabled) */
    BOOT_STAGE_IDLE      = 6, /* STAGE 6: system safely idle in low-power WFI loop */
    BOOT_STAGE_ERROR     = 0xFF /* Failsafe triggered: execution halted */
} boot_stage_t;

/* Set current boot stage */
void boot_stage_set(boot_stage_t stage);

/* Retrieve current boot stage (may be BOOT_STAGE_ERROR if failsafe triggered) */
boot_stage_t boot_stage_get(void);

/* Retrieve last successfully completed boot stage prior to any error */
boot_stage_t boot_stage_get_last_successful(void);

/* Get human-readable string name for a boot stage */
const char *boot_stage_name(boot_stage_t stage);

/*
 * Failsafe handler:
 * Logs critical error, records last successful stage, disables writes & IRQs,
 * and enters safe infinite WFI halt loop.
 * This function NEVER returns.
 */
void boot_stage_failsafe(const char *reason);

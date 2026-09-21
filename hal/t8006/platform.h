/*
 * DreyzeOS — T8006 Platform HAL
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 */

#pragma once

#include "../../include/types.h"

/*
 * Platform initialization — called very early in kernel_main.
 * Phase 1: All stubs (no real hardware access).
 * Phase 6+: Real implementations when MMIO addresses are confirmed.
 */

/* Early init — called before log_init() */
void platform_early_init(void);

/* Full platform init — called after log_init() */
void platform_init(void);

/* Individual subsystem init stubs */
void timer_init(void);      /* Phase 6 */
void display_init(void);    /* Phase 7 */
void touch_init(void);      /* Phase 9 */
void crown_init(void);      /* Phase 8 */
void button_init(void);     /* Phase 8 */

/* Device info */
typedef struct {
    char     model_identifier[32];  /* e.g. "Watch4,1" */
    uint32_t chip_id;               /* T8006 = 0x8006 LIKELY */
    uint32_t board_id;              /* UNKNOWN */
    uint32_t display_width;
    uint32_t display_height;
    bool     has_cellular;
} platform_info_t;

const platform_info_t *platform_get_info(void);

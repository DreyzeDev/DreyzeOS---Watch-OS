/*
 * DreyzeOS — Boot Framebuffer Header
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Safe abstraction for the video scanout buffer initialized by iBoot.
 * Enforces strict bounds checking, row stride safety, and integer-overflow checks.
 */

#pragma once

#include "../../include/types.h"
#include "../../include/boot_info.h"

/* Compile-time safety switch: default 0 (writes disabled) */
#ifndef DREYZE_FB_TEST_PATTERN
#define DREYZE_FB_TEST_PATTERN 0
#endif

/*
 * Pixel format constants:
 * From watchOS 10.6.1 kernelcache disassembly (0xfffffff00823ea2c):
 * Apple boot console format: "BBBBBBBBGGGGGGGGRRRRRRRR" (BGRA32 / BGRX32)
 *
 * In little-endian 32-bit integer:
 *   Bits  0..7  : Blue
 *   Bits  8..15 : Green
 *   Bits 16..23 : Red
 *   Bits 24..31 : Alpha / Unused
 */
#define FB_COLOR_BLACK      0x00000000U
#define FB_COLOR_WHITE      0x00FFFFFFU
#define FB_COLOR_RED        0x00FF0000U
#define FB_COLOR_GREEN      0x0000FF00U
#define FB_COLOR_BLUE       0x000000FFU
#define FB_COLOR_YELLOW     0x00FFFF00U
#define FB_COLOR_CYAN       0x0000FFFFU
#define FB_COLOR_MAGENTA    0x00FF00FFU
#define FB_COLOR_GRAY       0x00808080U
#define FB_COLOR_DARK_GRAY  0x00404040U

/* Construct a 32-bit BGRA/BGRX pixel value from R, G, B components */
#define FB_RGB(r, g, b) \
    (((uint32_t)((r) & 0xFFU) << 16) | \
     ((uint32_t)((g) & 0xFFU) << 8)  | \
     ((uint32_t)((b) & 0xFFU)))

/* Framebuffer descriptor */
typedef struct {
    uintptr_t base_vaddr;        /* Virtual address of framebuffer buffer */
    uint64_t  base_paddr;        /* Physical address of framebuffer buffer */
    uint64_t  size;              /* Total buffer size in bytes */
    uint32_t  width;             /* Active display width in pixels */
    uint32_t  height;            /* Active display height in pixels */
    uint32_t  row_bytes;         /* Bytes per line / stride (including padding) */
    uint32_t  depth;             /* Color depth in bits per pixel (e.g. 32) */
    uint32_t  bytes_per_pixel;   /* Bytes per pixel (depth / 8) */
    bool      is_configured;     /* True if initialized and validated */
    bool      mapping_verified;  /* Hard safety interlock: false by default */
    bool      is_write_allowed;  /* Safety interlock: false by default */
} framebuffer_t;

/*
 * Initialize the framebuffer subsystem from discovered boot parameters.
 * Validates sanity, strides, bounds, and ensures integer-overflow safety.
 *
 * Returns 0 on success, negative error code on failure.
 */
int framebuffer_init(const boot_framebuffer_info_t *info);

/* Returns true if framebuffer is successfully configured and available */
bool framebuffer_is_available(void);

/* Returns pointer to active framebuffer descriptor (NULL if not configured) */
const framebuffer_t *framebuffer_get_info(void);

/*
 * Hard safety interlock control:
 * Production exposes only the closed-state query and write capability check.
 * A future trusted verifier must be added deliberately before any production
 * mapping can be opened.
 */
bool framebuffer_is_mapping_verified(void);

#ifdef HOST_TEST
/* Test-only mapping injection and gate control; production has no guessed
 * identity mapping or setter that can assert verification. */
void framebuffer_set_virtual_base_for_test(uintptr_t base_vaddr);
void framebuffer_set_mapping_verified_for_test(bool verified);
#endif

/* Explicitly enable or disable hardware writes to the framebuffer */
void framebuffer_enable_writes(bool enable);

/*
 * Safe pixel plotting primitive.
 * Performs clipping and integer overflow-checked bounds validation before every write.
 */
void framebuffer_put_pixel(uint32_t x, uint32_t y, uint32_t color);

/* Fill entire visible framebuffer area with solid color */
void framebuffer_fill(uint32_t color);

/* Clear screen (fill with black FB_COLOR_BLACK) */
void framebuffer_clear(void);

/* Draw a solid filled rectangle with strict bounds clipping */
void framebuffer_draw_rect(uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint32_t color);

/*
 * Diagnostic test pattern:
 * Black background -> white border -> 6 color bars -> center white box.
 * Only executes if is_write_allowed is true.
 */
void framebuffer_draw_test_pattern(void);

/* Output framebuffer diagnostics to kernel log */
void framebuffer_diag(void);

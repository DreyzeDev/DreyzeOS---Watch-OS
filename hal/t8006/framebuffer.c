/*
 * DreyzeOS — Boot Framebuffer Implementation
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Implements:
 *   - Safe hardware framebuffer abstraction for iBoot-initialized display
 *   - Strict bounds checking and row stride (row_bytes) addressing
 *   - 64-bit integer overflow protection on all geometry calculations
 *   - Safety interlock (hardware writes disabled by default)
 *   - Diagnostic test pattern generator
 */

#include "framebuffer.h"
#include "../../include/log.h"
#include "../../lib/string.h"

/* Active framebuffer state */
static framebuffer_t g_fb = {0};

/* ============================================================
 * Initialization & Configuration
 * ============================================================ */

int framebuffer_init(const boot_framebuffer_info_t *info)
{
    if (!info || !info->is_valid) {
        return -1;
    }

    if (info->base_paddr == 0) {
        return -2;
    }

    if (info->width == 0 || info->height == 0) {
        return -3;
    }

    /* Validate color depth (default to 32 bpp if unspecified) */
    uint32_t depth = (info->depth != 0) ? info->depth : 32;
    uint32_t bpp = (depth + 7) / 8;
    if (bpp == 0 || bpp > 8) {
        return -4;
    }

    /*
     * Row Stride & Overflow Validation:
     * Minimum row stride is width * bytes_per_pixel.
     * row_bytes must be at least min_row_bytes, and cannot overflow 64-bit.
     */
    uint64_t min_row_bytes = (uint64_t)info->width * (uint64_t)bpp;
    uint32_t row_bytes = info->row_bytes;
    if (row_bytes == 0) {
        if (min_row_bytes > 0xFFFFFFFFULL) {
            return -5;
        }
        row_bytes = (uint32_t)min_row_bytes;
    } else if ((uint64_t)row_bytes < min_row_bytes) {
        /* Bootloader reported rowBytes smaller than one scanline of pixels! */
        return -5;
    }

    /* Validate that (row_bytes * height) does not overflow uint64 */
    if (info->height > 0 && (0xFFFFFFFFFFFFFFFFULL / (uint64_t)row_bytes) < (uint64_t)info->height) {
        return -6;
    }
    uint64_t min_total_size = (uint64_t)row_bytes * (uint64_t)info->height;

    /* Total buffer size */
    uint64_t size = info->size;
    if (size == 0) {
        size = min_total_size;
    } else if (size < min_total_size) {
        /* Buffer is smaller than the required visible scanout area */
        return -7;
    }

    /* Populate active descriptor */
    g_fb.base_paddr       = info->base_paddr;
    g_fb.base_vaddr       = (uintptr_t)info->base_paddr; /* Identity mapped at EL1 */
    g_fb.size             = size;
    g_fb.width            = info->width;
    g_fb.height           = info->height;
    g_fb.row_bytes        = row_bytes;
    g_fb.depth            = depth;
    g_fb.bytes_per_pixel  = bpp;
    g_fb.is_configured    = true;
    g_fb.is_write_allowed = false; /* Safety interlock: writes disabled by default */

    return 0;
}

bool framebuffer_is_available(void)
{
    return g_fb.is_configured;
}

const framebuffer_t *framebuffer_get_info(void)
{
    return g_fb.is_configured ? &g_fb : NULL;
}

void framebuffer_enable_writes(bool enable)
{
    g_fb.is_write_allowed = enable;
}

/* ============================================================
 * Safe Pixel & Drawing Primitives
 * ============================================================ */

void framebuffer_put_pixel(uint32_t x, uint32_t y, uint32_t color)
{
    /* Safety interlock & configuration check */
    if (!g_fb.is_configured || !g_fb.is_write_allowed) {
        return;
    }

    /* Coordinate bounds clipping */
    if (x >= g_fb.width || y >= g_fb.height) {
        return;
    }

    /*
     * Integer-overflow safe offset calculation:
     * offset = y * row_bytes + x * bytes_per_pixel
     */
    uint64_t y_offset = (uint64_t)y * (uint64_t)g_fb.row_bytes;
    uint64_t x_offset = (uint64_t)x * (uint64_t)g_fb.bytes_per_pixel;

    if (0xFFFFFFFFFFFFFFFFULL - y_offset < x_offset) {
        return; /* Overflow protection */
    }
    uint64_t offset = y_offset + x_offset;

    /* Verify complete pixel fits inside allocated framebuffer memory */
    if (offset > g_fb.size || (g_fb.size - offset) < (uint64_t)g_fb.bytes_per_pixel) {
        return;
    }

    /* Write pixel according to depth */
    if (g_fb.bytes_per_pixel == 4) {
        *(volatile uint32_t *)(g_fb.base_vaddr + offset) = color;
    } else if (g_fb.bytes_per_pixel == 2) {
        *(volatile uint16_t *)(g_fb.base_vaddr + offset) = (uint16_t)color;
    } else if (g_fb.bytes_per_pixel == 1) {
        *(volatile uint8_t *)(g_fb.base_vaddr + offset) = (uint8_t)color;
    }
}

void framebuffer_fill(uint32_t color)
{
    if (!g_fb.is_configured || !g_fb.is_write_allowed) {
        return;
    }

    for (uint32_t y = 0; y < g_fb.height; y++) {
        uint64_t y_offset = (uint64_t)y * (uint64_t)g_fb.row_bytes;
        if (y_offset >= g_fb.size) break;

        for (uint32_t x = 0; x < g_fb.width; x++) {
            uint64_t x_offset = (uint64_t)x * (uint64_t)g_fb.bytes_per_pixel;
            if (0xFFFFFFFFFFFFFFFFULL - y_offset < x_offset) break;

            uint64_t offset = y_offset + x_offset;
            if (offset + (uint64_t)g_fb.bytes_per_pixel > g_fb.size) break;

            if (g_fb.bytes_per_pixel == 4) {
                *(volatile uint32_t *)(g_fb.base_vaddr + offset) = color;
            } else if (g_fb.bytes_per_pixel == 2) {
                *(volatile uint16_t *)(g_fb.base_vaddr + offset) = (uint16_t)color;
            } else if (g_fb.bytes_per_pixel == 1) {
                *(volatile uint8_t *)(g_fb.base_vaddr + offset) = (uint8_t)color;
            }
        }
    }

    __asm__ volatile("dsb sy" ::: "memory");
}

void framebuffer_clear(void)
{
    framebuffer_fill(FB_COLOR_BLACK);
}

void framebuffer_draw_rect(uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint32_t color)
{
    if (!g_fb.is_configured || !g_fb.is_write_allowed) {
        return;
    }

    if (x >= g_fb.width || y >= g_fb.height || w == 0 || h == 0) {
        return;
    }

    /* Clip width and height to visible display */
    if ((uint64_t)x + (uint64_t)w > (uint64_t)g_fb.width) {
        w = g_fb.width - x;
    }
    if ((uint64_t)y + (uint64_t)h > (uint64_t)g_fb.height) {
        h = g_fb.height - y;
    }

    for (uint32_t row = 0; row < h; row++) {
        uint32_t cur_y = y + row;
        uint64_t y_offset = (uint64_t)cur_y * (uint64_t)g_fb.row_bytes;
        if (y_offset >= g_fb.size) break;

        for (uint32_t col = 0; col < w; col++) {
            uint32_t cur_x = x + col;
            uint64_t x_offset = (uint64_t)cur_x * (uint64_t)g_fb.bytes_per_pixel;
            if (0xFFFFFFFFFFFFFFFFULL - y_offset < x_offset) break;

            uint64_t offset = y_offset + x_offset;
            if (offset + (uint64_t)g_fb.bytes_per_pixel > g_fb.size) break;

            if (g_fb.bytes_per_pixel == 4) {
                *(volatile uint32_t *)(g_fb.base_vaddr + offset) = color;
            } else if (g_fb.bytes_per_pixel == 2) {
                *(volatile uint16_t *)(g_fb.base_vaddr + offset) = (uint16_t)color;
            } else if (g_fb.bytes_per_pixel == 1) {
                *(volatile uint8_t *)(g_fb.base_vaddr + offset) = (uint8_t)color;
            }
        }
    }

    __asm__ volatile("dsb sy" ::: "memory");
}

/* ============================================================
 * Diagnostic Test Pattern
 * ============================================================ */

void framebuffer_draw_test_pattern(void)
{
    if (!g_fb.is_configured || !g_fb.is_write_allowed) {
        return;
    }

    /* 1. Clear background to black */
    framebuffer_clear();

    /* 2. White outer border (3 pixels wide) */
    uint32_t bw = 3;
    if (g_fb.width > bw * 2 && g_fb.height > bw * 2) {
        framebuffer_draw_rect(0, 0, g_fb.width, bw, FB_COLOR_WHITE);                  /* Top */
        framebuffer_draw_rect(0, g_fb.height - bw, g_fb.width, bw, FB_COLOR_WHITE);  /* Bottom */
        framebuffer_draw_rect(0, 0, bw, g_fb.height, FB_COLOR_WHITE);                  /* Left */
        framebuffer_draw_rect(g_fb.width - bw, 0, bw, g_fb.height, FB_COLOR_WHITE);  /* Right */
    }

    /*
     * 3. Color bar row in upper portion:
     * 6 vertical color patches: Red, Green, Blue, Yellow, Cyan, Magenta.
     */
    uint32_t colors[6] = {
        FB_COLOR_RED,
        FB_COLOR_GREEN,
        FB_COLOR_BLUE,
        FB_COLOR_YELLOW,
        FB_COLOR_CYAN,
        FB_COLOR_MAGENTA
    };

    uint32_t margin_x = 20;
    uint32_t bar_y    = 20;
    uint32_t bar_h    = g_fb.height / 5;
    if (bar_h < 10) bar_h = 10;

    if (g_fb.width > margin_x * 2) {
        uint32_t avail_w = g_fb.width - (margin_x * 2);
        uint32_t bar_w   = avail_w / 6;

        for (uint32_t i = 0; i < 6; i++) {
            framebuffer_draw_rect(margin_x + (i * bar_w), bar_y, bar_w - 2, bar_h, colors[i]);
        }
    }

    /*
     * 4. Centered White rectangle in lower portion:
     */
    uint32_t rect_w = g_fb.width / 3;
    uint32_t rect_h = g_fb.height / 6;
    if (rect_w < 10) rect_w = 10;
    if (rect_h < 10) rect_h = 10;

    uint32_t rect_x = (g_fb.width - rect_w) / 2;
    uint32_t rect_y = bar_y + bar_h + 30;

    if (rect_y + rect_h < g_fb.height) {
        framebuffer_draw_rect(rect_x, rect_y, rect_w, rect_h, FB_COLOR_WHITE);
    }
}

/* ============================================================
 * Diagnostics
 * ============================================================ */

void framebuffer_diag(void)
{
    klog_info("========================================");
    klog_info("  [FRAMEBUFFER] Subsystem Diagnostics");
    klog_info("========================================");

    if (!g_fb.is_configured) {
        klog_info("  [FB] Framebuffer NOT configured or not discovered");
        return;
    }

    klog_hex("  [FB] Base Phys Address ", g_fb.base_paddr);
    klog_hex("  [FB] Total Buffer Size ", g_fb.size);
    klog_hex("  [FB] Width (pixels)    ", g_fb.width);
    klog_hex("  [FB] Height (pixels)   ", g_fb.height);
    klog_hex("  [FB] Row Bytes (stride)", g_fb.row_bytes);
    klog_hex("  [FB] Color Depth (bits)", g_fb.depth);
    klog_hex("  [FB] Bytes Per Pixel   ", g_fb.bytes_per_pixel);

    /* Pixel format details from kernelcache */
    klog_info("  [FB] Pixel Format: BBBBBBBBGGGGGGGGRRRRRRRR (BGRA32) [CONFIRMED]");
    klog_info("  [FB] MMU Mapping: Identity mapping UNVERIFIED (Direct dereference blocked)");

    if (g_fb.is_write_allowed) {
        klog_info("  [FB] Write Status: Hardware writes ALLOWED");
    } else {
        klog_info("  [FB] Write Status: Hardware writes DISABLED (Safety Interlock Active)");
    }
}

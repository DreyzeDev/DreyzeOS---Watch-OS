/*
 * DreyzeOS — Boot Information & Hardware Discovery Header
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Provides runtime discovered information passed from the boot chain:
 *   - Boot ABI: iBoot boot_args (x0) and/or direct DeviceTree pointer
 *   - Physical memory layout (DRAM base & size)
 *   - Memory-map reserved ranges (/chosen/memory-map)
 *   - Runtime framebuffer parameters (Video / VRAM)
 *   - Device identifiers (model, chip-id, board-id)
 */

#pragma once

#include "types.h"

/* ============================================================
 * Apple XNU ARM64 boot_args ABI Definitions
 * Source: pexpert/pexpert/arm64/boot.h (Apple XNU open-source)
 * Verified against kernelcache.release.watch4 disassembly.
 * ============================================================ */

#define BOOT_LINE_LENGTH_MAX    1024

/* Video parameters passed by iBoot in boot_args (CONFIRMED) */
typedef struct {
    uint64_t v_baseAddr;     /* Base physical address of video memory */
    uint64_t v_display;      /* Display Code / flags */
    uint64_t v_rowBytes;     /* Stride: number of bytes per pixel row */
    uint64_t v_width;        /* Active width in pixels */
    uint64_t v_height;       /* Active height in pixels */
    uint64_t v_depth;        /* Pixel depth / format */
} __packed boot_video_t;

/*
 * struct xnu_arm64_boot_args
 * Standard Apple ARM64 boot argument structure passed in x0 by iBoot.
 */
typedef struct {
    uint16_t     revision;              /* 0x00: Structure revision */
    uint16_t     version;               /* 0x02: Structure version */
    uint32_t     _pad0;                 /* 0x04: Alignment padding */
    uint64_t     virt_base;             /* 0x08: Virtual base address */
    uint64_t     phys_base;             /* 0x10: Physical DRAM base */
    uint64_t     mem_size;              /* 0x18: Total memory size */
    uint64_t     top_of_kernel_data;    /* 0x20: Top of loaded kernel image */
    boot_video_t video;                 /* 0x28: Video console information */
    uint32_t     machine_type;          /* 0x58: Machine Type */
    uint32_t     _pad1;                 /* 0x5C: Alignment padding */
    uint64_t     devicetree_p;          /* 0x60: Physical/virt address of ADT */
    uint32_t     devicetree_length;     /* 0x68: Byte length of ADT */
    char         command_line[BOOT_LINE_LENGTH_MAX]; /* 0x6C: Boot args string */
} __packed xnu_arm64_boot_args_t;

/* ============================================================
 * DreyzeOS Discovered Boot Info Structures
 * ============================================================ */

#define MAX_BOOT_MEMORY_RANGES  32

/* Single physical memory reservation from /chosen/memory-map */
typedef struct {
    char     name[32];       /* Range name (e.g. "Display", "RAMDisk", "KernelText") */
    uint64_t phys_addr;      /* Physical base address */
    uint64_t size;           /* Size in bytes */
    bool     is_valid;       /* Entry is valid */
} memory_range_t;

/* Discovered runtime framebuffer configuration */
typedef struct {
    uint64_t base_paddr;     /* Physical base address of framebuffer */
    uint64_t size;           /* Total framebuffer memory size in bytes */
    uint32_t width;          /* Width in pixels (0 if not supplied by bootloader) */
    uint32_t height;         /* Height in pixels (0 if not supplied by bootloader) */
    uint32_t row_bytes;      /* Bytes per row / stride (0 if not supplied) */
    uint32_t depth;          /* Bits per pixel / format code (0 if not supplied) */
    bool     is_valid;       /* True if framebuffer was discovered */
    const char *source;      /* Discovery source: "boot_args" or "devicetree" */
} boot_framebuffer_info_t;

/* Complete Platform Boot Information */
typedef struct {
    /* Boot ABI source detection */
    bool     boot_args_present;      /* True if valid xnu boot_args was detected in x0 */
    bool     devtree_present;        /* True if valid Apple DeviceTree was detected */
    uintptr_t devtree_base;          /* Address of DeviceTree in memory */
    uint32_t devtree_size;           /* Size of DeviceTree in bytes */

    /* Physical DRAM configuration */
    uint64_t dram_phys_base;         /* Base physical address of DRAM */
    uint64_t dram_size;              /* Total DRAM size in bytes */

    /* Memory regions from /chosen/memory-map */
    memory_range_t memory_ranges[MAX_BOOT_MEMORY_RANGES];
    uint32_t num_memory_ranges;

    /* Framebuffer / Video console */
    boot_framebuffer_info_t fb_info;

    /* Target hardware identifiers from /chosen */
    char     model[32];              /* e.g. "Watch4,2" or "N131bAP" */
    uint32_t chip_id;                /* e.g. 0x8006 for T8006 */
    uint32_t board_id;               /* Target board ID */
    uint64_t unique_chip_id;         /* ECID / Unique chip ID */
} platform_boot_info_t;

/* ============================================================
 * Public Discovery API
 * ============================================================ */

/* Initialize platform boot info from bootloader registers x0 and x1 */
void platform_boot_info_init(uint64_t arg0, uint64_t arg1);

/* Retrieve pointer to global boot info structure */
const platform_boot_info_t *platform_get_boot_info(void);

/* Retrieve pointer to discovered framebuffer info */
const boot_framebuffer_info_t *platform_get_framebuffer(void);

/* Output full discovery diagnostics to klog / serial console */
void platform_boot_info_diag(void);

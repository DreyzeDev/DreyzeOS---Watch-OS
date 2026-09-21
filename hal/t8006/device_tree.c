/*
 * DreyzeOS — Apple DeviceTree (ADT) Dynamic Parser & Boot Hardware Discovery
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Implements:
 *   - Boot ABI auto-detection (iBoot boot_args vs. direct ADT pointer)
 *   - Safe bounds-checked recursive Apple DeviceTree (ADT) traversal
 *   - Dynamic DRAM memory range extraction (/memory, boot_args)
 *   - Memory reservation mapping (/chosen/memory-map)
 *   - Framebuffer discovery (Boot_Video and/or /chosen/memory-map)
 *   - Platform hardware metadata extraction (/chosen)
 */

#include "device_tree.h"
#include "memory_map.h"
#include "../../include/log.h"
#include "../../lib/string.h"

/* Global discovered platform boot information */
static platform_boot_info_t g_boot_info;
static bool g_boot_info_initialized = false;

/* ============================================================
 * Helper: String case-insensitive comparison & search
 * ============================================================ */

static bool str_contains_nocase(const char *haystack, const char *needle)
{
    if (!haystack || !needle) return false;
    size_t hlen = strlen(haystack);
    size_t nlen = strlen(needle);
    if (nlen > hlen) return false;

    for (size_t i = 0; i <= hlen - nlen; i++) {
        bool match = true;
        for (size_t j = 0; j < nlen; j++) {
            char c1 = haystack[i + j];
            char c2 = needle[j];
            if (c1 >= 'A' && c1 <= 'Z') c1 += ('a' - 'A');
            if (c2 >= 'A' && c2 <= 'Z') c2 += ('a' - 'A');
            if (c1 != c2) {
                match = false;
                break;
            }
        }
        if (match) return true;
    }
    return false;
}

/* ============================================================
 * Low-level ADT Parsing Primitives (Bounds-Checked)
 * ============================================================ */

bool devtree_validate_header(uintptr_t base, uint32_t max_size)
{
    if (base == 0 || max_size < (sizeof(adt_node_hdr_t) + sizeof(adt_prop_hdr_t))) {
        return false;
    }

    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)base;
    if (hdr->prop_count == 0 || hdr->prop_count > 512) {
        return false;
    }

    /* First property in an ADT node must be "name" */
    const adt_prop_hdr_t *first_prop = (const adt_prop_hdr_t *)(base + sizeof(adt_node_hdr_t));
    if (strncmp(first_prop->name, "name", 4) != 0) {
        return false;
    }

    return true;
}

const uint8_t *devtree_find_prop(uintptr_t node_ptr, uintptr_t tree_limit,
                                 const char *prop_name, uint32_t *out_size)
{
    if (!node_ptr || !prop_name || (node_ptr + sizeof(adt_node_hdr_t) > tree_limit)) {
        return NULL;
    }

    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)node_ptr;
    uint32_t prop_count = hdr->prop_count;
    uintptr_t offset = node_ptr + sizeof(adt_node_hdr_t);

    for (uint32_t i = 0; i < prop_count; i++) {
        if (offset + sizeof(adt_prop_hdr_t) > tree_limit) {
            return NULL;
        }

        const adt_prop_hdr_t *prop = (const adt_prop_hdr_t *)offset;
        uint32_t size = prop->size & ADT_PROP_SIZE_MASK;
        uint32_t padded = (size + 3) & ~3u;

        if (offset + sizeof(adt_prop_hdr_t) + padded > tree_limit) {
            return NULL;
        }

        if (strncmp(prop->name, prop_name, ADT_PROP_NAME_LEN) == 0) {
            if (out_size) {
                *out_size = size;
            }
            return (const uint8_t *)(offset + sizeof(adt_prop_hdr_t));
        }

        offset += sizeof(adt_prop_hdr_t) + padded;
    }

    return NULL;
}

/*
 * devtree_get_node_size — calculate total byte size of a node and all its children.
 * Returns 0 if truncated or invalid.
 */
static uintptr_t devtree_get_node_size(uintptr_t node_ptr, uintptr_t tree_limit)
{
    if (node_ptr + sizeof(adt_node_hdr_t) > tree_limit) {
        return 0;
    }

    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)node_ptr;
    uint32_t prop_count = hdr->prop_count;
    uint32_t child_count = hdr->child_count;

    uintptr_t offset = node_ptr + sizeof(adt_node_hdr_t);

    /* Skip all properties */
    for (uint32_t i = 0; i < prop_count; i++) {
        if (offset + sizeof(adt_prop_hdr_t) > tree_limit) {
            return 0;
        }
        const adt_prop_hdr_t *prop = (const adt_prop_hdr_t *)offset;
        uint32_t size = prop->size & ADT_PROP_SIZE_MASK;
        uint32_t padded = (size + 3) & ~3u;
        if (offset + sizeof(adt_prop_hdr_t) + padded > tree_limit) {
            return 0;
        }
        offset += sizeof(adt_prop_hdr_t) + padded;
    }

    /* Skip all child subtrees recursively */
    for (uint32_t c = 0; c < child_count; c++) {
        uintptr_t child_size = devtree_get_node_size(offset, tree_limit);
        if (child_size == 0) {
            return 0;
        }
        offset += child_size;
    }

    return offset - node_ptr;
}

/*
 * devtree_find_child_node — find direct child of node by name.
 */
static uintptr_t devtree_find_child_node(uintptr_t node_ptr, uintptr_t tree_limit, const char *child_name)
{
    if (node_ptr + sizeof(adt_node_hdr_t) > tree_limit || !child_name) {
        return 0;
    }

    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)node_ptr;
    uint32_t prop_count = hdr->prop_count;
    uint32_t child_count = hdr->child_count;

    uintptr_t offset = node_ptr + sizeof(adt_node_hdr_t);

    /* Advance past properties */
    for (uint32_t i = 0; i < prop_count; i++) {
        if (offset + sizeof(adt_prop_hdr_t) > tree_limit) {
            return 0;
        }
        const adt_prop_hdr_t *prop = (const adt_prop_hdr_t *)offset;
        uint32_t size = prop->size & ADT_PROP_SIZE_MASK;
        uint32_t padded = (size + 3) & ~3u;
        offset += sizeof(adt_prop_hdr_t) + padded;
    }

    /* Search direct children */
    for (uint32_t c = 0; c < child_count; c++) {
        if (offset + sizeof(adt_node_hdr_t) > tree_limit) {
            return 0;
        }

        uint32_t name_size = 0;
        const uint8_t *name_val = devtree_find_prop(offset, tree_limit, "name", &name_size);
        if (name_val && strncmp((const char *)name_val, child_name, 32) == 0) {
            return offset;
        }

        uintptr_t child_size = devtree_get_node_size(offset, tree_limit);
        if (child_size == 0) {
            return 0;
        }
        offset += child_size;
    }

    return 0;
}

uintptr_t devtree_find_node_by_path(uintptr_t root, uint32_t tree_size, const char *path)
{
    if (!root || !path || tree_size < 8) {
        return 0;
    }

    uintptr_t tree_limit = root + tree_size;
    if (strcmp(path, "/") == 0) {
        return root;
    }

    /* Skip leading '/' */
    if (*path == '/') path++;

    uintptr_t current = root;
    char segment[32];

    while (*path) {
        size_t seg_len = 0;
        while (*path && *path != '/' && seg_len < sizeof(segment) - 1) {
            segment[seg_len++] = *path++;
        }
        segment[seg_len] = '\0';
        if (*path == '/') path++;

        current = devtree_find_child_node(current, tree_limit, segment);
        if (current == 0) {
            return 0;
        }
    }

    return current;
}

/* ============================================================
 * Dynamic DeviceTree Extraction (/chosen, memory-map, /memory)
 * ============================================================ */

int devtree_parse_dynamic(uintptr_t base, uint32_t size, platform_boot_info_t *info)
{
    if (!base || size < 64 || !info) {
        return -1;
    }

    uintptr_t tree_limit = base + size;
    info->devtree_present = true;
    info->devtree_base = base;
    info->devtree_size = size;

    /* 1. Parse /chosen node properties */
    uintptr_t chosen = devtree_find_node_by_path(base, size, "/chosen");
    if (chosen) {
        uint32_t prop_sz;
        const uint8_t *val;

        val = devtree_find_prop(chosen, tree_limit, "chip-id", &prop_sz);
        if (val && prop_sz >= 4) {
            memcpy(&info->chip_id, val, 4);
        }

        val = devtree_find_prop(chosen, tree_limit, "board-id", &prop_sz);
        if (val && prop_sz >= 4) {
            memcpy(&info->board_id, val, 4);
        }

        val = devtree_find_prop(chosen, tree_limit, "unique-chip-id", &prop_sz);
        if (val && prop_sz >= 8) {
            memcpy(&info->unique_chip_id, val, 8);
        }

        val = devtree_find_prop(chosen, tree_limit, "model", &prop_sz);
        if (val && prop_sz > 0) {
            size_t copy_len = prop_sz < sizeof(info->model) ? prop_sz : sizeof(info->model) - 1;
            memcpy(info->model, val, copy_len);
            info->model[copy_len] = '\0';
        }
    }

    /* 2. Parse /memory node for primary DRAM base & size */
    uintptr_t memory_node = devtree_find_node_by_path(base, size, "/memory");
    if (memory_node) {
        uint32_t reg_sz;
        const uint8_t *reg_val = devtree_find_prop(memory_node, tree_limit, "reg", &reg_sz);
        if (reg_val && reg_sz >= 16) {
            uint64_t mem_base, mem_len;
            memcpy(&mem_base, reg_val, 8);
            memcpy(&mem_len, reg_val + 8, 8);
            if (mem_len > 0) {
                info->dram_phys_base = mem_base;
                info->dram_size = mem_len;
            }
        }
    }

    /* 3. Parse /chosen/memory-map for reserved regions and Framebuffer */
    uintptr_t mmap_node = devtree_find_node_by_path(base, size, "/chosen/memory-map");
    if (mmap_node) {
        const adt_node_hdr_t *mmap_hdr = (const adt_node_hdr_t *)mmap_node;
        uintptr_t prop_off = mmap_node + sizeof(adt_node_hdr_t);

        for (uint32_t i = 0; i < mmap_hdr->prop_count && info->num_memory_ranges < MAX_BOOT_MEMORY_RANGES; i++) {
            if (prop_off + sizeof(adt_prop_hdr_t) > tree_limit) {
                break;
            }

            const adt_prop_hdr_t *prop = (const adt_prop_hdr_t *)prop_off;
            uint32_t val_sz = prop->size & ADT_PROP_SIZE_MASK;
            uint32_t padded = (val_sz + 3) & ~3u;

            if (prop_off + sizeof(adt_prop_hdr_t) + padded > tree_limit) {
                break;
            }

            const uint8_t *prop_val = (const uint8_t *)(prop_off + sizeof(adt_prop_hdr_t));

            /* Check if this is an active 16-byte memory map entry: [paddr (8), size (8)] */
            if (val_sz == 16 && strcmp(prop->name, "name") != 0 && strcmp(prop->name, "AAPL,phandle") != 0) {
                uint64_t paddr, rlen;
                memcpy(&paddr, prop_val, 8);
                memcpy(&rlen, prop_val + 8, 8);

                /* Skip unpopulated/zero placeholder ranges */
                if (rlen > 0) {
                    uint32_t idx = info->num_memory_ranges;
                    strncpy(info->memory_ranges[idx].name, prop->name, sizeof(info->memory_ranges[idx].name) - 1);
                    info->memory_ranges[idx].name[sizeof(info->memory_ranges[idx].name) - 1] = '\0';
                    info->memory_ranges[idx].phys_addr = paddr;
                    info->memory_ranges[idx].size = rlen;
                    info->memory_ranges[idx].is_valid = true;
                    info->num_memory_ranges++;

                    /* Check if this range corresponds to the runtime Framebuffer/Display */
                    if (!info->fb_info.is_valid &&
                        (str_contains_nocase(prop->name, "Display") ||
                         str_contains_nocase(prop->name, "Framebuffer") ||
                         str_contains_nocase(prop->name, "VRAM"))) {
                        info->fb_info.base_paddr = paddr;
                        info->fb_info.size = rlen;
                        info->fb_info.is_valid = true;
                        info->fb_info.source = "devicetree";
                    }
                }
            }

            prop_off += sizeof(adt_prop_hdr_t) + padded;
        }
    }

    return 0;
}

/* ============================================================
 * Public Platform Boot Info API
 * ============================================================ */

void platform_boot_info_init(uint64_t arg0, uint64_t arg1)
{
    /* Initialize defaults with confirmed static baseline */
    memset(&g_boot_info, 0, sizeof(g_boot_info));
    g_boot_info.dram_phys_base = T8006_DRAM_BASE;
    g_boot_info.dram_size      = T8006_DRAM_SIZE;
    g_boot_info.chip_id        = 0x8006;
    strncpy(g_boot_info.model, "Watch4,2", sizeof(g_boot_info.model) - 1);

    if (arg0 == 0) {
        /* No boot arguments passed; running standalone or simulator */
        g_boot_info_initialized = true;
        return;
    }

    /*
     * Boot ABI Detection:
     * Check whether arg0 is a direct pointer to raw Apple DeviceTree (ADT)
     * or a pointer to Apple XNU struct boot_args.
     */
    if (devtree_validate_header((uintptr_t)arg0, arg1 ? (uint32_t)arg1 : 0x100000)) {
        /* arg0 is directly an Apple DeviceTree pointer! */
        uint32_t dt_size = arg1 ? (uint32_t)arg1 : (uint32_t)devtree_get_node_size((uintptr_t)arg0, (uintptr_t)arg0 + 0x200000);
        if (dt_size < 64) dt_size = 0x80000; /* 512 KB fallback estimate */
        devtree_parse_dynamic((uintptr_t)arg0, dt_size, &g_boot_info);
    } else {
        /* Check if arg0 is struct xnu_arm64_boot_args */
        const xnu_arm64_boot_args_t *ba = (const xnu_arm64_boot_args_t *)(uintptr_t)arg0;

        /* Validate boot_args sanity */
        if (ba->phys_base >= 0x100000000ULL && ba->mem_size >= 0x1000000ULL && ba->mem_size <= 0x80000000ULL) {
            g_boot_info.boot_args_present = true;
            g_boot_info.dram_phys_base    = ba->phys_base;
            g_boot_info.dram_size         = ba->mem_size;

            /* Extract Video/Framebuffer from boot_args */
            if (ba->video.v_baseAddr != 0) {
                g_boot_info.fb_info.base_paddr = ba->video.v_baseAddr;
                g_boot_info.fb_info.width      = (uint32_t)ba->video.v_width;
                g_boot_info.fb_info.height     = (uint32_t)ba->video.v_height;
                g_boot_info.fb_info.row_bytes  = (uint32_t)ba->video.v_rowBytes;
                g_boot_info.fb_info.depth      = (uint32_t)ba->video.v_depth;
                g_boot_info.fb_info.size       = (uint64_t)ba->video.v_rowBytes * (uint64_t)ba->video.v_height;
                g_boot_info.fb_info.is_valid   = true;
                g_boot_info.fb_info.source     = "boot_args";
            }

            /* Extract DeviceTree pointed to by boot_args */
            if (ba->devicetree_p != 0 && ba->devicetree_length >= 64) {
                if (devtree_validate_header((uintptr_t)ba->devicetree_p, ba->devicetree_length)) {
                    devtree_parse_dynamic((uintptr_t)ba->devicetree_p, ba->devicetree_length, &g_boot_info);
                }
            }
        }
    }

    g_boot_info_initialized = true;
}

const platform_boot_info_t *platform_get_boot_info(void)
{
    return &g_boot_info;
}

const boot_framebuffer_info_t *platform_get_framebuffer(void)
{
    return &g_boot_info.fb_info;
}

void platform_boot_info_diag(void)
{
    klog_info("========================================");
    klog_info("  [BOOT-DISCOVERY] Platform Diagnostics");
    klog_info("========================================");

    if (g_boot_info.boot_args_present) {
        klog_info("  [BOOT] Source: XNU boot_args ABI (CONFIRMED)");
    } else if (g_boot_info.devtree_present) {
        klog_info("  [BOOT] Source: Direct DeviceTree pointer (CONFIRMED)");
    } else {
        klog_info("  [BOOT] Source: Static fallback / standalone execution");
    }

    /* DeviceTree Diagnostics */
    if (g_boot_info.devtree_present) {
        klog_hex("  [ADT] Base Address ", g_boot_info.devtree_base);
        klog_hex("  [ADT] Total Size   ", g_boot_info.devtree_size);
    } else {
        klog_info("  [ADT] Not present / not detected");
    }

    /* Memory Layout */
    klog_hex("  [MEM] DRAM Physical Base", g_boot_info.dram_phys_base);
    klog_hex("  [MEM] DRAM Total Size   ", g_boot_info.dram_size);

    /* Reserved Memory Ranges from /chosen/memory-map */
    klog_hex("  [MEM] Memory-Map Ranges ", g_boot_info.num_memory_ranges);
    for (uint32_t i = 0; i < g_boot_info.num_memory_ranges; i++) {
        const memory_range_t *r = &g_boot_info.memory_ranges[i];
        klog_info(r->name);
        klog_hex("    Base", r->phys_addr);
        klog_hex("    Size", r->size);
    }

    /* Framebuffer / Video Console Diagnostics */
    klog_info("  [FB] Framebuffer Diagnostics:");
    if (g_boot_info.fb_info.is_valid) {
        klog_info("  [FB] Status: DISCOVERED ✓");
        klog_info(g_boot_info.fb_info.source);
        klog_hex("  [FB] Physical Base Address", g_boot_info.fb_info.base_paddr);
        klog_hex("  [FB] Total Size (bytes)   ", g_boot_info.fb_info.size);
        if (g_boot_info.fb_info.width > 0 && g_boot_info.fb_info.height > 0) {
            klog_hex("  [FB] Width (pixels)       ", g_boot_info.fb_info.width);
            klog_hex("  [FB] Height (pixels)      ", g_boot_info.fb_info.height);
            klog_hex("  [FB] Row Bytes (stride)   ", g_boot_info.fb_info.row_bytes);
            klog_hex("  [FB] Depth / Pixel Format ", g_boot_info.fb_info.depth);
        } else {
            klog_info("  [FB] Dimensions: awaiting display initialization (not in boot_args)");
        }
    } else {
        klog_info("  [FB] Status: NOT PRE-ALLOCATED by bootloader");
    }

    /* Device metadata */
    klog_hex("  [DEV] Chip ID    ", g_boot_info.chip_id);
    klog_hex("  [DEV] Board ID   ", g_boot_info.board_id);
    klog_info("  [DEV] Model: ");
    klog_info(g_boot_info.model);
    klog_info("========================================");
}

/*
 * DreyzeOS — Apple DeviceTree (ADT) Dynamic Parser & Boot Hardware Discovery
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Implements:
 *   - Boot metadata parsing only after an explicit verified handoff descriptor
 *   - Safe bounds-checked recursive Apple DeviceTree (ADT) traversal
 *   - Dynamic DRAM memory range extraction (/memory, boot_args)
 *   - Memory reservation mapping (/chosen/memory-map)
 *   - Framebuffer discovery (Boot_Video and/or /chosen/memory-map)
 *   - Platform hardware metadata extraction (/chosen)
 */

#include "device_tree.h"
#include "handoff_gate.h"
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

/* Check ranges by subtraction so attacker-controlled additions cannot wrap. */
static bool adt_range_valid(uintptr_t start, uintptr_t length, uintptr_t limit)
{
    return start <= limit && length <= (limit - start);
}

static bool adt_advance(uintptr_t current, uintptr_t length,
                        uintptr_t limit, uintptr_t *next)
{
    if (!adt_range_valid(current, length, limit)) {
        return false;
    }
    if (next) {
        *next = current + length;
    }
    return true;
}

static bool adt_padded_size(uint32_t size, uintptr_t *out)
{
    uintptr_t padded = (uintptr_t)size;
    if (padded > (uintptr_t)-1 - 3) {
        return false;
    }
    padded = (padded + 3) & ~(uintptr_t)3;
    if (out) {
        *out = padded;
    }
    return true;
}

bool devtree_validate_header(uintptr_t base, uint32_t max_size)
{
    if (base == 0 || max_size < (sizeof(adt_node_hdr_t) + sizeof(adt_prop_hdr_t))) {
        return false;
    }

    uintptr_t limit;
    if (!adt_advance(base, max_size, (uintptr_t)-1, &limit)) {
        return false;
    }

    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)base;
    if (hdr->prop_count == 0 || hdr->prop_count > 512) {
        return false;
    }

    /* First property in an ADT node must be "name" */
    uintptr_t first_prop_addr;
    if (!adt_advance(base, sizeof(adt_node_hdr_t), limit, &first_prop_addr)) {
        return false;
    }
    const adt_prop_hdr_t *first_prop = (const adt_prop_hdr_t *)first_prop_addr;
    if (strncmp(first_prop->name, "name", 4) != 0) {
        return false;
    }

    uintptr_t padded;
    return adt_padded_size(first_prop->size & ADT_PROP_SIZE_MASK, &padded) &&
           adt_advance(first_prop_addr, sizeof(adt_prop_hdr_t), limit, NULL) &&
           adt_advance(first_prop_addr + sizeof(adt_prop_hdr_t), padded, limit, NULL);
}

const uint8_t *devtree_find_prop(uintptr_t node_ptr, uintptr_t tree_limit,
                                 const char *prop_name, uint32_t *out_size)
{
    if (!node_ptr || !prop_name ||
        !adt_range_valid(node_ptr, sizeof(adt_node_hdr_t), tree_limit)) {
        return NULL;
    }

    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)node_ptr;
    uint32_t prop_count = hdr->prop_count;
    uintptr_t offset = node_ptr + sizeof(adt_node_hdr_t);

    for (uint32_t i = 0; i < prop_count; i++) {
        if (!adt_range_valid(offset, sizeof(adt_prop_hdr_t), tree_limit)) {
            return NULL;
        }

        const adt_prop_hdr_t *prop = (const adt_prop_hdr_t *)offset;
        uint32_t size = prop->size & ADT_PROP_SIZE_MASK;
        uintptr_t padded;
        if (!adt_padded_size(size, &padded)) {
            return NULL;
        }

        if (!adt_advance(offset + sizeof(adt_prop_hdr_t), padded, tree_limit, NULL)) {
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

#define MAX_ADT_DEPTH 32

/*
 * devtree_get_node_size_depth — calculate total byte size of a node with depth tracking.
 * Returns 0 if truncated, cyclic, or depth exceeded.
 */
static uintptr_t devtree_get_node_size_depth(uintptr_t node_ptr, uintptr_t tree_limit, uint32_t depth)
{
    if (depth > MAX_ADT_DEPTH ||
        !adt_range_valid(node_ptr, sizeof(adt_node_hdr_t), tree_limit)) {
        return 0;
    }

    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)node_ptr;
    uint32_t prop_count = hdr->prop_count;
    uint32_t child_count = hdr->child_count;

    /* Sanity limits on prop and child counts */
    if (prop_count > 1024 || child_count > 1024) {
        return 0;
    }

    uintptr_t offset = node_ptr + sizeof(adt_node_hdr_t);

    /* Skip all properties */
    for (uint32_t i = 0; i < prop_count; i++) {
        if (!adt_range_valid(offset, sizeof(adt_prop_hdr_t), tree_limit)) {
            return 0;
        }
        const adt_prop_hdr_t *prop = (const adt_prop_hdr_t *)offset;
        uint32_t size = prop->size & ADT_PROP_SIZE_MASK;
        uintptr_t padded;
        if (!adt_padded_size(size, &padded) ||
            !adt_advance(offset + sizeof(adt_prop_hdr_t), padded, tree_limit, NULL)) {
            return 0;
        }
        offset += sizeof(adt_prop_hdr_t) + padded;
    }

    /* Skip all child subtrees recursively */
    for (uint32_t c = 0; c < child_count; c++) {
        uintptr_t child_size = devtree_get_node_size_depth(offset, tree_limit, depth + 1);
        if (child_size == 0) {
            return 0;
        }
        if (!adt_advance(offset, child_size, tree_limit, &offset)) {
            return 0;
        }
    }

    return offset - node_ptr;
}

static uintptr_t devtree_get_node_size(uintptr_t node_ptr, uintptr_t tree_limit)
{
    return devtree_get_node_size_depth(node_ptr, tree_limit, 0);
}

/*
 * devtree_find_child_node — find direct child of node by name.
 */
static uintptr_t devtree_find_child_node(uintptr_t node_ptr, uintptr_t tree_limit, const char *child_name)
{
    if (!adt_range_valid(node_ptr, sizeof(adt_node_hdr_t), tree_limit) || !child_name) {
        return 0;
    }

    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)node_ptr;
    uint32_t prop_count = hdr->prop_count;
    uint32_t child_count = hdr->child_count;

    uintptr_t offset = node_ptr + sizeof(adt_node_hdr_t);

    /* Advance past properties */
    for (uint32_t i = 0; i < prop_count; i++) {
        if (!adt_range_valid(offset, sizeof(adt_prop_hdr_t), tree_limit)) {
            return 0;
        }
        const adt_prop_hdr_t *prop = (const adt_prop_hdr_t *)offset;
        uint32_t size = prop->size & ADT_PROP_SIZE_MASK;
        uintptr_t padded;
        if (!adt_padded_size(size, &padded) ||
            !adt_advance(offset + sizeof(adt_prop_hdr_t), padded, tree_limit, &offset)) {
            return 0;
        }
    }

    /* Search direct children */
    for (uint32_t c = 0; c < child_count; c++) {
        if (!adt_range_valid(offset, sizeof(adt_node_hdr_t), tree_limit)) {
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
        if (!adt_advance(offset, child_size, tree_limit, &offset)) {
            return 0;
        }
    }

    return 0;
}

uintptr_t devtree_find_node_by_path(uintptr_t root, uint32_t tree_size, const char *path)
{
    if (!root || !path || tree_size < 8) {
        return 0;
    }

    uintptr_t tree_limit;
    if (!adt_advance(root, tree_size, (uintptr_t)-1, &tree_limit)) {
        return 0;
    }
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

    uintptr_t tree_limit;
    if (!adt_advance(base, size, (uintptr_t)-1, &tree_limit)) {
        return -1;
    }
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

    /* 2. Parse the candidate /memory report; zero static placeholders
     * are not runtime DRAM-map evidence. */
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
            if (!adt_range_valid(prop_off, sizeof(adt_prop_hdr_t), tree_limit)) {
                break;
            }

            const adt_prop_hdr_t *prop = (const adt_prop_hdr_t *)prop_off;
            uint32_t val_sz = prop->size & ADT_PROP_SIZE_MASK;
            uintptr_t padded;
            if (!adt_padded_size(val_sz, &padded)) {
                break;
            }

            if (!adt_advance(prop_off + sizeof(adt_prop_hdr_t), padded, tree_limit, NULL)) {
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

static void platform_boot_info_reset_fallback(uint64_t arg0, uint64_t arg1)
{
    memset(&g_boot_info, 0, sizeof(g_boot_info));
    loader_handoff_reset_unverified(arg0, arg1);
    /*
     * No runtime DRAM map has been proven on the production path. Keep
     * runtime-authoritative fields zero; historical product-memory quantities
     * are research context only and are not part of platform_boot_info_t.
     */
    g_boot_info.dram_phys_base = 0;
    g_boot_info.dram_size      = 0;
    g_boot_info.dram_virt_base = 0;
    g_boot_info.virt_base_valid = false;
    g_boot_info.metadata_status = BOOT_METADATA_STATIC_FALLBACK;
    g_boot_info.chip_id           = 0x8006;
    strncpy(g_boot_info.model, "Watch4,2", sizeof(g_boot_info.model) - 1);
    g_boot_info_initialized = true;
}

#ifdef HOST_TEST
static void platform_boot_info_apply_video(const boot_video_t *video)
{
    if (!video || video->v_baseAddr == 0) {
        return;
    }

    uint64_t v_row_bytes = video->v_rowBytes;
    uint64_t v_height = video->v_height;
    uint64_t v_size = 0;
    if (v_height == 0 || (0xFFFFFFFFFFFFFFFFULL / v_height) >= v_row_bytes) {
        v_size = v_row_bytes * v_height;
    }

    g_boot_info.fb_info.base_paddr = video->v_baseAddr;
    g_boot_info.fb_info.width      = (uint32_t)video->v_width;
    g_boot_info.fb_info.height     = (uint32_t)video->v_height;
    g_boot_info.fb_info.row_bytes  = (uint32_t)v_row_bytes;
    g_boot_info.fb_info.depth      = (uint32_t)video->v_depth;
    g_boot_info.fb_info.size       = v_size;
    g_boot_info.fb_info.is_valid   = true;
    g_boot_info.fb_info.source     = "boot_args";
}

static void platform_boot_info_apply_verified_boot_args(
    const xnu_arm64_boot_args_t *ba,
    const loader_handoff_descriptor_t *handoff)
{
    verified_range_t device_tree_range;
    uintptr_t device_tree_ptr;

    if (!ba) {
        return;
    }

    if (ba->phys_base < 0x100000000ULL ||
        ba->mem_size < 0x1000000ULL ||
        ba->mem_size > 0x80000000ULL) {
        return;
    }

    g_boot_info.boot_args_present = true;
    g_boot_info.metadata_status   = BOOT_METADATA_RUNTIME_VERIFIED;
    g_boot_info.dram_phys_base    = ba->phys_base;
    g_boot_info.dram_size         = ba->mem_size;

    if (ba->virt_base != 0) {
        g_boot_info.dram_virt_base  = ba->virt_base;
        g_boot_info.virt_base_valid = true;
    }
    platform_boot_info_apply_video(&ba->video);

    /*
     * boot_args->devicetree_p is a second trust boundary.  A verified
     * top-level boot_args buffer does not authorize this pointer.  Only an
     * independently verified nested buffer and its bounded length permit
     * ADT validation/parsing.
     */
    if (!handoff ||
        !loader_handoff_u64_to_uintptr(ba->devicetree_p, &device_tree_ptr) ||
        ba->devicetree_length < 64 ||
        !loader_handoff_range_to_native(&handoff->device_tree_range,
                                        &device_tree_range) ||
        !verified_range_contains_object(&device_tree_range,
                                        device_tree_ptr,
                                        ba->devicetree_length)) {
        return;
    }

    if (devtree_validate_header(device_tree_ptr, ba->devicetree_length)) {
        (void)devtree_parse_dynamic(device_tree_ptr,
                                     ba->devicetree_length, &g_boot_info);
    }
}
#endif

void platform_boot_info_init(uint64_t arg0, uint64_t arg1)
{
    /*
     * x0/x1 are an UNKNOWN/BLOCKED future-loader ABI.  Preserve the raw
     * values for diagnostics, but do not dereference either value, attempt
     * ABI auto-detection, or infer an ADT length.  This is the production
     * path and intentionally cannot open the handoff trust gate.
     */
    platform_boot_info_reset_fallback(arg0, arg1);
}

#ifdef HOST_TEST
void platform_boot_info_init_verified_for_test(
    const loader_handoff_descriptor_t *descriptor,
    bool arg0_is_boot_args)
{
    if (!descriptor) {
        platform_boot_info_reset_fallback(0, 0);
        return;
    }

    platform_boot_info_reset_fallback(descriptor->raw_x0, descriptor->raw_x1);
    loader_handoff_set_verified_for_test(descriptor);
    const loader_handoff_descriptor_t *handoff = loader_handoff_get();
    uintptr_t raw_x0;
    size_t raw_x1;
    verified_range_t boot_args_range;
    verified_range_t device_tree_range;

    if (!loader_handoff_is_verified()) {
        return;
    }

    if (arg0_is_boot_args) {
        if (!loader_handoff_u64_to_uintptr(handoff->raw_x0, &raw_x0) ||
            !loader_handoff_range_to_native(&handoff->boot_args_range,
                                            &boot_args_range) ||
            !verified_range_contains_object(&boot_args_range, raw_x0,
                                            sizeof(xnu_arm64_boot_args_t))) {
            return;
        }

        /* Copy only after the descriptor proves the complete object readable. */
        xnu_arm64_boot_args_t ba;
        memcpy(&ba, (const void *)raw_x0, sizeof(ba));
        platform_boot_info_apply_verified_boot_args(&ba, handoff);
        return;
    }

    /* Direct ADT also requires an explicit exact x1 length and DT range. */
    if (handoff->raw_x1 > 0xFFFFFFFFULL || handoff->raw_x1 < 64 ||
        !loader_handoff_u64_to_uintptr(handoff->raw_x0, &raw_x0) ||
        !loader_handoff_u64_to_size(handoff->raw_x1, &raw_x1) ||
        !loader_handoff_range_to_native(&handoff->device_tree_range,
                                        &device_tree_range) ||
        !verified_range_contains_object(&device_tree_range, raw_x0,
                                        raw_x1)) {
        return;
    }
    if (devtree_validate_header(raw_x0,
                                (uint32_t)handoff->raw_x1) &&
        devtree_parse_dynamic(raw_x0,
                               (uint32_t)handoff->raw_x1,
                               &g_boot_info) == 0) {
        if (g_boot_info.dram_phys_base != 0 &&
            g_boot_info.dram_size != 0) {
            g_boot_info.metadata_status = BOOT_METADATA_RUNTIME_VERIFIED;
        } else {
            /*
             * A valid ADT container without a populated /memory node is
             * still only static metadata; never promote it to a runtime map.
             */
            g_boot_info.dram_phys_base = 0;
            g_boot_info.dram_size = 0;
            g_boot_info.dram_virt_base = 0;
            g_boot_info.virt_base_valid = false;
            g_boot_info.metadata_status = BOOT_METADATA_STATIC_FALLBACK;
        }
    }
}
#endif

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
    const loader_handoff_descriptor_t *handoff = loader_handoff_get();

    klog_info("========================================");
    klog_info("  [BOOT-DISCOVERY] Platform Diagnostics");
    klog_info("========================================");

    klog_hex("  [BOOT] Raw x0          ", handoff->raw_x0);
    klog_hex("  [BOOT] Raw x1          ", handoff->raw_x1);
    if (!loader_handoff_is_verified()) {
        klog_info("  [BOOT] Handoff: UNVERIFIED (x0/x1 preserved; no pointer dereference)");
        klog_info("  [BOOT] Metadata: STATIC FALLBACK / HANDOFF_UNAVAILABLE");
    } else if (g_boot_info.boot_args_present) {
        klog_info("  [BOOT] Source: XNU boot_args ABI (CONFIRMED)");
    } else if (g_boot_info.devtree_present) {
        klog_info("  [BOOT] Source: Direct DeviceTree pointer (CONFIRMED)");
    } else {
        klog_info("  [BOOT] Handoff verified, but metadata parser rejected the supplied buffer");
    }

    /* DeviceTree Diagnostics */
    if (g_boot_info.devtree_present) {
        klog_hex("  [ADT] Base Address ", g_boot_info.devtree_base);
        klog_hex("  [ADT] Total Size   ", g_boot_info.devtree_size);
    } else {
        klog_info("  [ADT] Not present / not detected");
    }

    /* Memory Layout */
    switch (g_boot_info.metadata_status) {
    case BOOT_METADATA_RUNTIME_VERIFIED:
        klog_info("  [MEM] DRAM Data Source: RUNTIME VERIFIED HANDOFF");
        break;
    case BOOT_METADATA_STATIC_FALLBACK:
        klog_info("  [MEM] DRAM Data Source: STATIC FALLBACK (research placeholder - unverified)");
        break;
    default:
        klog_info("  [MEM] DRAM Data Source: UNAVAILABLE");
        break;
    }
    klog_hex("  [MEM] DRAM Physical Base", g_boot_info.dram_phys_base);
    klog_hex("  [MEM] DRAM Total Size   ", g_boot_info.dram_size);
    if (g_boot_info.virt_base_valid) {
        klog_hex("  [MEM] DRAM Virtual Base ", g_boot_info.dram_virt_base);
    } else {
        klog_info("  [MEM] DRAM Virtual Base : UNKNOWN (not supplied by bootloader)");
    }

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

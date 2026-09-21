/*
 * DreyzeOS — Apple DeviceTree Parser (C kernel component)
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * This C implementation runs inside the kernel and parses
 * the Apple DeviceTree passed by iBoot at boot time.
 *
 * For host-side parsing, see tools/device_tree_dump.py
 */

#include "../../include/types.h"
#include "../../include/log.h"
#include "../../lib/string.h"

/* ADT node header */
typedef struct {
    uint32_t prop_count;
    uint32_t child_count;
} __packed adt_node_hdr_t;

/* ADT property */
typedef struct {
    char     name[32];   /* null-terminated, fixed 32 bytes */
    uint32_t size;       /* byte count, high bit = type flag */
    /* value follows immediately, padded to 4 bytes */
} __packed adt_prop_hdr_t;

#define ADT_PROP_SIZE_MASK  0x7FFFFFFF

/* ============================================================
 * Kernel DeviceTree access
 * ============================================================ */

static uintptr_t g_devtree_base = 0;  /* Set at boot from x0 */

/*
 * devtree_init — called from kernel_main with the x0 argument.
 * Validates the DeviceTree pointer before use.
 *
 * Status: EXPERIMENTAL — we don't know if x0 is actually the DT pointer on T8006.
 */
void devtree_init(uint64_t dtree_ptr)
{
    if (dtree_ptr == 0) {
        klog_warn("[ADT] devtree_init: dtree_ptr == 0, DeviceTree unavailable");
        return;
    }

    /* Minimal sanity check: first 8 bytes should be reasonable counts */
    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)(uintptr_t)dtree_ptr;

    if (hdr->prop_count == 0 || hdr->prop_count > 256) {
        klog_warn("[ADT] devtree_init: suspicious prop_count — may not be valid ADT");
        klog_hex("[ADT] ptr", dtree_ptr);
        klog_hex("[ADT] prop_count", hdr->prop_count);
        return;
    }

    g_devtree_base = (uintptr_t)dtree_ptr;
    klog_hex("[ADT] DeviceTree found at", dtree_ptr);
    klog_hex("[ADT] Root prop_count", hdr->prop_count);
    klog_hex("[ADT] Root child_count", hdr->child_count);
}

/*
 * devtree_find_prop — find a property by name in a node.
 * Returns pointer to value bytes, or NULL if not found.
 * out_size receives the property value size.
 *
 * Parameters:
 *   node_ptr   — physical address of the ADT node
 *   prop_name  — property name to search for
 *   out_size   — receives value size in bytes
 */
const uint8_t *devtree_find_prop(uintptr_t node_ptr,
                                  const char *prop_name,
                                  uint32_t *out_size)
{
    if (!node_ptr || !prop_name) return NULL;

    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)node_ptr;
    uint32_t prop_count = hdr->prop_count;

    uintptr_t offset = node_ptr + sizeof(adt_node_hdr_t);

    for (uint32_t i = 0; i < prop_count; i++) {
        const adt_prop_hdr_t *prop = (const adt_prop_hdr_t *)offset;
        uint32_t size = prop->size & ADT_PROP_SIZE_MASK;

        if (strncmp(prop->name, prop_name, 32) == 0) {
            if (out_size) *out_size = size;
            return (const uint8_t *)(offset + sizeof(adt_prop_hdr_t));
        }

        /* Advance past this property (name + size field + value padded to 4) */
        uint32_t padded = (size + 3) & ~3u;
        offset += sizeof(adt_prop_hdr_t) + padded;
    }

    return NULL;
}

/*
 * devtree_log_root — log root DeviceTree node properties.
 * For research/debugging purposes.
 */
void devtree_log_root(void)
{
    if (!g_devtree_base) {
        klog_warn("[ADT] No DeviceTree available");
        return;
    }

    klog_info("[ADT] === Root DeviceTree Properties ===");

    const adt_node_hdr_t *hdr = (const adt_node_hdr_t *)g_devtree_base;
    uint32_t prop_count = hdr->prop_count;

    uintptr_t offset = g_devtree_base + sizeof(adt_node_hdr_t);

    for (uint32_t i = 0; i < prop_count && i < 32; i++) {
        const adt_prop_hdr_t *prop = (const adt_prop_hdr_t *)offset;
        uint32_t size = prop->size & ADT_PROP_SIZE_MASK;
        const uint8_t *val = (const uint8_t *)(offset + sizeof(adt_prop_hdr_t));

        /* Log property name */
        char msg[64] = "[ADT]   ";
        size_t prefix_len = strlen(msg);
        strncpy(msg + prefix_len, prop->name, 32);

        /* For small values, log hex */
        if (size == 4) {
            uint32_t v32 = 0;
            memcpy(&v32, val, 4);
            klog_hex(msg, v32);
        } else if (size == 8) {
            uint64_t v64 = 0;
            memcpy(&v64, val, 8);
            klog_hex(msg, v64);
        } else if (size < 32) {
            /* Try as string */
            klog_info(msg);
        } else {
            klog_hex(msg, size);
        }

        uint32_t padded = (size + 3) & ~3u;
        offset += sizeof(adt_prop_hdr_t) + padded;
    }

    klog_hex("[ADT] Root child_count", hdr->child_count);
}

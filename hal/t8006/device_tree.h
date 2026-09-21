/*
 * DreyzeOS — Apple DeviceTree (ADT) Parser Header
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 */

#pragma once

#include "../../include/types.h"
#include "../../include/boot_info.h"

/* ADT Node Header (8 bytes) */
typedef struct {
    uint32_t prop_count;
    uint32_t child_count;
} __packed adt_node_hdr_t;

/* ADT Property Header (36 bytes + padded value) */
typedef struct {
    char     name[32];   /* fixed 32-byte null-padded string */
    uint32_t size;       /* byte count; high bit (0x80000000) is type flag */
} __packed adt_prop_hdr_t;

#define ADT_PROP_SIZE_MASK      0x7FFFFFFFU
#define ADT_PROP_NAME_LEN       32

/* ============================================================
 * Public DeviceTree API
 * ============================================================ */

/* Validate whether a memory region points to a valid ADT root node */
bool devtree_validate_header(uintptr_t base, uint32_t max_size);

/* Full dynamic parse of DeviceTree into platform_boot_info_t */
int devtree_parse_dynamic(uintptr_t base, uint32_t size, platform_boot_info_t *info);

/* Find a node by full path (e.g. "/chosen/memory-map" or "/memory") */
uintptr_t devtree_find_node_by_path(uintptr_t root, uint32_t tree_size, const char *path);

/* Find a property inside a specific node */
const uint8_t *devtree_find_prop(uintptr_t node_ptr, uintptr_t tree_limit,
                                 const char *prop_name, uint32_t *out_size);

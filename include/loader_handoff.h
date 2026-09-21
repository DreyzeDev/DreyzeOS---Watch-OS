/* DreyzeOS — Loader Handoff Descriptor and Verified Range Primitives */
#pragma once

#include "types.h"

/* A non-empty, overflow-safe readable range proven by a future loader. */
typedef struct {
    uintptr_t base;
    size_t length;
    bool readable;
} verified_range_t;

#define DREYZE_HANDOFF_MAGIC 0x4452595A454F5348ULL /* "DRYZEOSH" */
#define DREYZE_HANDOFF_VERSION 1U

/* Descriptor facts are explicit; no non-zero address is trusted implicitly. */
#define DREYZE_HANDOFF_FLAG_VERIFIED (1ULL << 0)

typedef struct {
    uint64_t magic;
    uint32_t version;
    uint32_t size;
    uint64_t flags;

    uint32_t entry_el;
    bool     entry_el_known;

    uint64_t payload_pa;
    uint64_t payload_va;
    uint64_t payload_size;
    bool     payload_location_known;

    bool     mmu_enabled;
    bool     mmu_state_known;

    /* Raw legacy-register values are diagnostic data, not pointers. */
    uint64_t raw_x0;
    uint64_t raw_x1;

    /* Explicitly proven readable ranges for any future parser. */
    verified_range_t boot_args_range;
    verified_range_t device_tree_range;

    /* Mapping facts are independent of payload and metadata facts. */
    bool mmio_mapping_valid;
    bool uart_mapping_valid;
    bool aic_mapping_valid;
} loader_handoff_descriptor_t;

/* Generic overflow-safe range helpers. */
bool verified_range_is_valid(const verified_range_t *range);
bool verified_range_contains(const verified_range_t *container,
                             uintptr_t base, size_t length);
bool verified_range_contains_object(const verified_range_t *container,
                                    uintptr_t base, size_t object_size);

/* Single authoritative descriptor state. */
const loader_handoff_descriptor_t *loader_handoff_get(void);
bool loader_handoff_is_verified(void);
void loader_handoff_reset_unverified(uint64_t raw_x0, uint64_t raw_x1);

#ifdef HOST_TEST
/* Models an external verifier; no boolean-only gate exists in production. */
void loader_handoff_set_verified_for_test(
    const loader_handoff_descriptor_t *descriptor);
#endif

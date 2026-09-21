/* DreyzeOS — Stable Loader Handoff ABI V1 and Trust Gate */
#pragma once

#include "types.h"

/*
 * Internal/native range representation. This is never serialized or exposed
 * as the loader wire ABI: uintptr_t, size_t, and bool stay out of the
 * externally visible descriptor.
 */
typedef struct {
    uintptr_t base;
    size_t length;
    bool readable;
} verified_range_t;

/* Stable V1 wire range: fixed width on every supported compiler. */
typedef struct __packed {
    uint64_t base;
    uint64_t length;
    uint32_t flags;
    uint32_t reserved;
} loader_handoff_range_v1_t;

#define DREYZE_HANDOFF_RANGE_FLAG_READABLE (1U << 0)

#define DREYZE_HANDOFF_MAGIC   0x4452595A454F5348ULL /* "DRYZEOSH" */
#define DREYZE_HANDOFF_VERSION 1U

/* Descriptor facts are flags, never compiler-dependent bool fields. */
#define DREYZE_HANDOFF_FLAG_VERIFIED               (1ULL << 0)
#define DREYZE_HANDOFF_FLAG_ENTRY_EL_KNOWN         (1ULL << 1)
#define DREYZE_HANDOFF_FLAG_PAYLOAD_LOCATION_KNOWN (1ULL << 2)
#define DREYZE_HANDOFF_FLAG_MMU_STATE_KNOWN        (1ULL << 3)
#define DREYZE_HANDOFF_FLAG_MMIO_MAPPING_VALID     (1ULL << 4)
#define DREYZE_HANDOFF_FLAG_UART_MAPPING_VALID     (1ULL << 5)
#define DREYZE_HANDOFF_FLAG_AIC_MAPPING_VALID      (1ULL << 6)

/*
 * Stable Loader Handoff ABI V1.
 *
 * The first 128 bytes are the complete V1 prefix. A future version may
 * append fields and increase size; V1 consumers ignore the unknown tail after
 * validating the fixed prefix. The memory containing the declared prefix must
 * already be proven readable by the pre-existing loader contract.
 */
typedef struct __packed {
    uint64_t magic;                 /* 0x00 */
    uint32_t version;               /* 0x08 */
    uint32_t size;                  /* 0x0C */
    uint64_t flags;                 /* 0x10 */

    uint32_t entry_el;              /* 0x18 */
    uint32_t reserved0;             /* 0x1C */

    uint64_t payload_pa;            /* 0x20 */
    uint64_t payload_va;            /* 0x28 */
    uint64_t payload_size;          /* 0x30 */

    uint32_t mmu_enabled;           /* 0x38: 0 or 1 */
    uint32_t reserved1;             /* 0x3C */

    uint64_t raw_x0;                /* 0x40: diagnostic only */
    uint64_t raw_x1;                /* 0x48: diagnostic only */

    loader_handoff_range_v1_t boot_args_range;   /* 0x50 */
    loader_handoff_range_v1_t device_tree_range; /* 0x68 */
} loader_handoff_descriptor_t;

#define DREYZE_HANDOFF_V1_SIZE ((uint32_t)128U)

/* ABI layout is part of the contract, not an accidental compiler result. */
_Static_assert(sizeof(loader_handoff_range_v1_t) == 24,
               "loader handoff range V1 size changed");
_Static_assert(offsetof(loader_handoff_range_v1_t, base) == 0,
               "loader handoff range base offset changed");
_Static_assert(offsetof(loader_handoff_range_v1_t, length) == 8,
               "loader handoff range length offset changed");
_Static_assert(offsetof(loader_handoff_range_v1_t, flags) == 16,
               "loader handoff range flags offset changed");
_Static_assert(offsetof(loader_handoff_range_v1_t, reserved) == 20,
               "loader handoff range reserved offset changed");

_Static_assert(sizeof(loader_handoff_descriptor_t) == DREYZE_HANDOFF_V1_SIZE,
               "loader handoff descriptor V1 size changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, magic) == 0,
               "loader handoff magic offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, version) == 8,
               "loader handoff version offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, size) == 12,
               "loader handoff size offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, flags) == 16,
               "loader handoff flags offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, entry_el) == 24,
               "loader handoff entry EL offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, payload_pa) == 32,
               "loader handoff payload PA offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, payload_va) == 40,
               "loader handoff payload VA offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, payload_size) == 48,
               "loader handoff payload size offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, mmu_enabled) == 56,
               "loader handoff MMU offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, raw_x0) == 64,
               "loader handoff raw x0 offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, raw_x1) == 72,
               "loader handoff raw x1 offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, boot_args_range) == 80,
               "loader handoff boot args range offset changed");
_Static_assert(offsetof(loader_handoff_descriptor_t, device_tree_range) == 104,
               "loader handoff device tree range offset changed");

/* Generic overflow-safe native range helpers. */
bool verified_range_is_valid(const verified_range_t *range);
bool verified_range_contains(const verified_range_t *container,
                             uintptr_t base, size_t length);
bool verified_range_contains_object(const verified_range_t *container,
                                    uintptr_t base, size_t object_size);

/* Structural V1 validation and explicit fixed-width-to-native conversions. */
bool loader_handoff_descriptor_validate(
    const loader_handoff_descriptor_t *descriptor);
bool loader_handoff_range_to_native(const loader_handoff_range_v1_t *wire,
                                    verified_range_t *native_range);
bool loader_handoff_u64_to_uintptr(uint64_t value, uintptr_t *out);
bool loader_handoff_u64_to_size(uint64_t value, size_t *out);

/* Single authoritative descriptor state. */
const loader_handoff_descriptor_t *loader_handoff_get(void);
bool loader_handoff_is_verified(void);
void loader_handoff_reset_unverified(uint64_t raw_x0, uint64_t raw_x1);

#ifdef HOST_TEST
/* Models an already-safe external descriptor; it performs no normalization. */
void loader_handoff_set_verified_for_test(
    const loader_handoff_descriptor_t *descriptor);
#endif

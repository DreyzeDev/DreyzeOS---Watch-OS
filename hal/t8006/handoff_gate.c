/* DreyzeOS — Loader Handoff Descriptor and Trust Gate */

#include "handoff_gate.h"

static loader_handoff_descriptor_t g_loader_handoff;

#define DREYZE_HANDOFF_KNOWN_FLAGS \
    (DREYZE_HANDOFF_FLAG_VERIFIED | \
     DREYZE_HANDOFF_FLAG_ENTRY_EL_KNOWN | \
     DREYZE_HANDOFF_FLAG_PAYLOAD_LOCATION_KNOWN | \
     DREYZE_HANDOFF_FLAG_MMU_STATE_KNOWN | \
     DREYZE_HANDOFF_FLAG_MMIO_MAPPING_VALID | \
     DREYZE_HANDOFF_FLAG_UART_MAPPING_VALID | \
     DREYZE_HANDOFF_FLAG_AIC_MAPPING_VALID | \
     DREYZE_HANDOFF_FLAG_MAPPING_STATE_KNOWN)

static bool range_end_is_safe(uintptr_t base, size_t length)
{
    return length != 0 && length <= ((uintptr_t)-1 - base);
}

bool verified_range_is_valid(const verified_range_t *range)
{
    return range != NULL && range->base != 0 && range->readable &&
           range_end_is_safe(range->base, range->length);
}

bool verified_range_contains(const verified_range_t *container,
                             uintptr_t base, size_t length)
{
    if (!verified_range_is_valid(container) ||
        !range_end_is_safe(base, length) ||
        base < container->base) {
        return false;
    }

    return length <= (container->base + container->length) - base;
}

bool verified_range_contains_object(const verified_range_t *container,
                                    uintptr_t base, size_t object_size)
{
    return verified_range_contains(container, base, object_size);
}

bool loader_handoff_u64_to_uintptr(uint64_t value, uintptr_t *out)
{
    if (!out || value > (uint64_t)(uintptr_t)-1) {
        return false;
    }

    *out = (uintptr_t)value;
    return true;
}

bool loader_handoff_u64_to_size(uint64_t value, size_t *out)
{
    if (!out || value > (uint64_t)(size_t)-1) {
        return false;
    }

    *out = (size_t)value;
    return true;
}

bool loader_handoff_range_to_native(const loader_handoff_range_v1_t *wire,
                                    verified_range_t *native_range)
{
    uintptr_t base;
    size_t length;

    if (!wire || !native_range ||
        (wire->flags & DREYZE_HANDOFF_RANGE_FLAG_READABLE) == 0 ||
        (wire->flags & ~DREYZE_HANDOFF_RANGE_FLAG_READABLE) != 0 ||
        wire->reserved != 0 ||
        !loader_handoff_u64_to_uintptr(wire->base, &base) ||
        !loader_handoff_u64_to_size(wire->length, &length)) {
        return false;
    }

    native_range->base = base;
    native_range->length = length;
    native_range->readable = true;
    return verified_range_is_valid(native_range);
}

bool loader_handoff_descriptor_validate(
    const loader_handoff_descriptor_t *descriptor)
{
    uint64_t mapping_valid_flags;

    if (!descriptor || descriptor->magic != DREYZE_HANDOFF_MAGIC ||
        descriptor->version != DREYZE_HANDOFF_VERSION ||
        descriptor->size < DREYZE_HANDOFF_V1_SIZE ||
        (descriptor->flags & ~DREYZE_HANDOFF_KNOWN_FLAGS) != 0 ||
        descriptor->reserved0 != 0 || descriptor->reserved1 != 0 ||
        descriptor->mmu_enabled > 1) {
        return false;
    }

    /* V1 entry is deliberately restricted to the DreyzeOS EL1 contract. */
    if ((descriptor->flags & DREYZE_HANDOFF_FLAG_ENTRY_EL_KNOWN) != 0 &&
        descriptor->entry_el != 1U) {
        return false;
    }

    /* A known payload location must describe two non-wrapping, non-empty
     * address ranges. This is structural consistency, not a mapping proof. */
    if ((descriptor->flags & DREYZE_HANDOFF_FLAG_PAYLOAD_LOCATION_KNOWN) != 0 &&
        (descriptor->payload_pa == 0 || descriptor->payload_va == 0 ||
         descriptor->payload_size == 0 ||
         descriptor->payload_size > (uint64_t)-1 - descriptor->payload_pa ||
         descriptor->payload_size > (uint64_t)-1 - descriptor->payload_va)) {
        return false;
    }

    mapping_valid_flags = descriptor->flags &
        (DREYZE_HANDOFF_FLAG_MMIO_MAPPING_VALID |
         DREYZE_HANDOFF_FLAG_UART_MAPPING_VALID |
         DREYZE_HANDOFF_FLAG_AIC_MAPPING_VALID);

    /* Mapping validity bits cannot be asserted without an explicit mapping
     * assessment. UART/AIC validity also requires the general MMIO range. */
    if ((mapping_valid_flags != 0 &&
         (descriptor->flags & DREYZE_HANDOFF_FLAG_MAPPING_STATE_KNOWN) == 0) ||
        ((descriptor->flags &
          (DREYZE_HANDOFF_FLAG_UART_MAPPING_VALID |
           DREYZE_HANDOFF_FLAG_AIC_MAPPING_VALID)) != 0 &&
         (descriptor->flags & DREYZE_HANDOFF_FLAG_MMIO_MAPPING_VALID) == 0)) {
        return false;
    }

    /* A larger size is forward-compatible; V1 never reads the unknown tail. */
    return true;
}

const loader_handoff_descriptor_t *loader_handoff_get(void)
{
    return &g_loader_handoff;
}

bool loader_handoff_is_verified(void)
{
    return loader_handoff_descriptor_validate(&g_loader_handoff) &&
           (g_loader_handoff.flags & DREYZE_HANDOFF_FLAG_VERIFIED) != 0;
}

void loader_handoff_reset_unverified(uint64_t raw_x0, uint64_t raw_x1)
{
    g_loader_handoff.magic = DREYZE_HANDOFF_MAGIC;
    g_loader_handoff.version = DREYZE_HANDOFF_VERSION;
    g_loader_handoff.size = sizeof(g_loader_handoff);
    g_loader_handoff.flags = 0;
    g_loader_handoff.entry_el = 0;
    g_loader_handoff.reserved0 = 0;
    g_loader_handoff.payload_pa = 0;
    g_loader_handoff.payload_va = 0;
    g_loader_handoff.payload_size = 0;
    g_loader_handoff.mmu_enabled = 0;
    g_loader_handoff.reserved1 = 0;
    g_loader_handoff.raw_x0 = raw_x0;
    g_loader_handoff.raw_x1 = raw_x1;
    g_loader_handoff.boot_args_range.base = 0;
    g_loader_handoff.boot_args_range.length = 0;
    g_loader_handoff.boot_args_range.flags = 0;
    g_loader_handoff.boot_args_range.reserved = 0;
    g_loader_handoff.device_tree_range.base = 0;
    g_loader_handoff.device_tree_range.length = 0;
    g_loader_handoff.device_tree_range.flags = 0;
    g_loader_handoff.device_tree_range.reserved = 0;
}

#ifdef HOST_TEST
void loader_handoff_set_verified_for_test(
    const loader_handoff_descriptor_t *descriptor)
{
    if (!descriptor) {
        loader_handoff_reset_unverified(0, 0);
        return;
    }

    g_loader_handoff = *descriptor;
}
#endif

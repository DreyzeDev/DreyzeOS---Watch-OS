/* DreyzeOS — Loader Handoff Descriptor and Trust Gate */

#include "handoff_gate.h"

static loader_handoff_descriptor_t g_loader_handoff;

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

const loader_handoff_descriptor_t *loader_handoff_get(void)
{
    return &g_loader_handoff;
}

bool loader_handoff_is_verified(void)
{
    return g_loader_handoff.magic == DREYZE_HANDOFF_MAGIC &&
           g_loader_handoff.version == DREYZE_HANDOFF_VERSION &&
           g_loader_handoff.size >= sizeof(g_loader_handoff) &&
           (g_loader_handoff.flags & DREYZE_HANDOFF_FLAG_VERIFIED) != 0;
}

void loader_handoff_reset_unverified(uint64_t raw_x0, uint64_t raw_x1)
{
    g_loader_handoff.magic = DREYZE_HANDOFF_MAGIC;
    g_loader_handoff.version = DREYZE_HANDOFF_VERSION;
    g_loader_handoff.size = sizeof(g_loader_handoff);
    g_loader_handoff.flags = 0;
    g_loader_handoff.entry_el = 0;
    g_loader_handoff.entry_el_known = false;
    g_loader_handoff.payload_pa = 0;
    g_loader_handoff.payload_va = 0;
    g_loader_handoff.payload_size = 0;
    g_loader_handoff.payload_location_known = false;
    g_loader_handoff.mmu_enabled = false;
    g_loader_handoff.mmu_state_known = false;
    g_loader_handoff.raw_x0 = raw_x0;
    g_loader_handoff.raw_x1 = raw_x1;
    g_loader_handoff.boot_args_range.base = 0;
    g_loader_handoff.boot_args_range.length = 0;
    g_loader_handoff.boot_args_range.readable = false;
    g_loader_handoff.device_tree_range.base = 0;
    g_loader_handoff.device_tree_range.length = 0;
    g_loader_handoff.device_tree_range.readable = false;
    g_loader_handoff.mmio_mapping_valid = false;
    g_loader_handoff.uart_mapping_valid = false;
    g_loader_handoff.aic_mapping_valid = false;
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
    g_loader_handoff.magic = DREYZE_HANDOFF_MAGIC;
    g_loader_handoff.version = DREYZE_HANDOFF_VERSION;
    g_loader_handoff.size = sizeof(g_loader_handoff);
    g_loader_handoff.flags |= DREYZE_HANDOFF_FLAG_VERIFIED;
}
#endif

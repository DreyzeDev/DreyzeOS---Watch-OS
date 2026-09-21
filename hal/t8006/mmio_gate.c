/* DreyzeOS — MMIO Mapping Safety Gate */
#include "mmio_gate.h"

static bool g_mmio_mapping_verified = false;

bool mmio_mapping_is_verified(void)
{
    return g_mmio_mapping_verified;
}

/* Test-only plumbing. Production images have no API to open the gate. */
#ifdef HOST_TEST
void mmio_mapping_set_verified_for_test(bool verified)
{
    g_mmio_mapping_verified = verified;
}
#endif

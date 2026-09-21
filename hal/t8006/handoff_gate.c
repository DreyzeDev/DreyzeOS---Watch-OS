/* DreyzeOS — Loader Handoff Trust Gate */

#include "handoff_gate.h"

static bool g_loader_handoff_verified = false;

bool loader_handoff_is_verified(void)
{
    return g_loader_handoff_verified;
}

#ifdef HOST_TEST
void loader_handoff_set_verified_for_test(bool verified)
{
    g_loader_handoff_verified = verified;
}
#endif

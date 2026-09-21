/*
 * DreyzeOS — Loader Handoff Trust Gate
 *
 * The loader ABI for x0/x1 is not established.  Production code therefore
 * starts with this gate closed and has no API that can open it.  The host
 * test-only setter models a future verifier which has already proved pointer
 * ownership and bounds; it is not part of the production image.
 */
#pragma once

#include "../../include/types.h"

bool loader_handoff_is_verified(void);

#ifdef HOST_TEST
void loader_handoff_set_verified_for_test(bool verified);
#endif

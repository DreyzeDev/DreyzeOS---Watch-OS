/* DreyzeOS — MMIO Mapping Safety Gate */
#pragma once

#include "../../include/types.h"

/*
 * False by default.  Only a future loader/MMU contract verifier may set this
 * true after proving that the relevant physical MMIO ranges are mapped at the
 * addresses used by DreyzeOS.  The current pre-hardware path never does.
 */
bool mmio_mapping_is_verified(void);

#ifdef HOST_TEST
void mmio_mapping_set_verified_for_test(bool verified);
#endif

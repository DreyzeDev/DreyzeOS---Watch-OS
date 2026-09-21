/*
 * DreyzeOS — CPU Boot State Snapshot Header
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Captures a read-only snapshot after the entry shim has performed its
 * mandatory setup.  It must not be presented as an untouched loader state.
 */

#pragma once

#include "types.h"

typedef struct {
    uint32_t current_el;
    uint64_t daif;          /* post-entry: entry.S masked DAIF before capture */

    /* Inherited/unmodified by DreyzeOS before this snapshot. */
    uint64_t sctlr_el1;
    uint64_t tcr_el1;
    uint64_t ttbr0_el1;
    uint64_t ttbr1_el1;
    uint64_t mair_el1;

    /* Post-entry values: entry.S installed/modified these before capture. */
    uint64_t vbar_el1;
    uint64_t cpacr_el1;

    bool el1_registers_valid;
} boot_cpu_state_t;

/*
 * Capture CPU register state snapshot.
 * READ-ONLY capture. SCTLR/TCR/TTBR/MAIR are inherited values; DAIF, VBAR,
 * and CPACR are post-entry DreyzeOS values and do not prove incoming state.
 * Only accesses EL1 registers if CurrentEL >= 1.
 */
void boot_cpu_state_capture(void);

/* Retrieve pointer to global captured CPU state */
const boot_cpu_state_t *boot_cpu_state_get(void);

/* Output full CPU state diagnostic report to klog */
void boot_cpu_state_diag(void);

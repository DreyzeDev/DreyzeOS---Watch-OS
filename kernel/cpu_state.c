/*
 * DreyzeOS — CPU Boot State Snapshot Implementation
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Implements read-only capture of hardware state without altering registers.
 * The capture occurs after entry.S has masked DAIF, installed VBAR_EL1, and
 * enabled FP/SIMD through CPACR_EL1.  Those three values are post-entry,
 * while SCTLR/TCR/TTBR/MAIR remain inherited because entry.S leaves them
 * untouched.
 */

#include "../include/cpu_state.h"
#include "../include/log.h"

static boot_cpu_state_t g_boot_cpu_state = {0};
static bool g_boot_cpu_state_captured = false;

/* Linker symbol for vector base comparison */
extern uint8_t _exception_vectors_base[];

void boot_cpu_state_capture(void)
{
    uint64_t el_raw = 0;
    uint64_t daif_raw = 0;

    __asm__ volatile("mrs %0, CurrentEL" : "=r"(el_raw));
    __asm__ volatile("mrs %0, DAIF"      : "=r"(daif_raw));

    g_boot_cpu_state.current_el = (uint32_t)((el_raw >> 2) & 0x3);
    g_boot_cpu_state.daif       = daif_raw;

    if (g_boot_cpu_state.current_el >= 1) {
        g_boot_cpu_state.el1_registers_valid = true;

        __asm__ volatile("mrs %0, sctlr_el1" : "=r"(g_boot_cpu_state.sctlr_el1));
        __asm__ volatile("mrs %0, tcr_el1"   : "=r"(g_boot_cpu_state.tcr_el1));
        __asm__ volatile("mrs %0, ttbr0_el1" : "=r"(g_boot_cpu_state.ttbr0_el1));
        __asm__ volatile("mrs %0, ttbr1_el1" : "=r"(g_boot_cpu_state.ttbr1_el1));
        __asm__ volatile("mrs %0, mair_el1"  : "=r"(g_boot_cpu_state.mair_el1));
        __asm__ volatile("mrs %0, vbar_el1"  : "=r"(g_boot_cpu_state.vbar_el1));
        __asm__ volatile("mrs %0, cpacr_el1" : "=r"(g_boot_cpu_state.cpacr_el1));
    } else {
        g_boot_cpu_state.el1_registers_valid = false;
    }

    g_boot_cpu_state_captured = true;
}

const boot_cpu_state_t *boot_cpu_state_get(void)
{
    return &g_boot_cpu_state;
}

void boot_cpu_state_diag(void)
{
    if (!g_boot_cpu_state_captured) {
        klog_warn("[CPU-DIAG] State not captured yet");
        return;
    }

    klog_info("========================================");
    klog_info("  [CPU-DIAG] Hardware Handover State");
    klog_info("========================================");

    klog_hex("  CurrentEL (raw EL) ", (uint64_t)g_boot_cpu_state.current_el);
    klog_hex("  DAIF (post-entry)   ", g_boot_cpu_state.daif);
    klog_info("    DAIF incoming state: UNKNOWN (entry.S masked before capture)");

    /* Annotate DAIF bits */
    bool d_masked = (g_boot_cpu_state.daif & (1ULL << 9)) != 0;
    bool a_masked = (g_boot_cpu_state.daif & (1ULL << 8)) != 0;
    bool i_masked = (g_boot_cpu_state.daif & (1ULL << 7)) != 0;
    bool f_masked = (g_boot_cpu_state.daif & (1ULL << 6)) != 0;
    if (d_masked && a_masked && i_masked && f_masked) {
        klog_info("    DAIF Status: ALL MASKED (D=1, A=1, I=1, F=1) [SAFE]");
    } else {
        klog_warn("    DAIF Status: SOME UNMASKED! [WARNING]");
    }

    if (!g_boot_cpu_state.el1_registers_valid) {
        klog_warn("  EL1 Registers: INVALID (entered below EL1)");
        return;
    }

    klog_hex("  SCTLR_EL1 (inherited)", g_boot_cpu_state.sctlr_el1);
    /* Interpret SCTLR critical bits */
    bool mmu_enabled    = (g_boot_cpu_state.sctlr_el1 & (1ULL << 0)) != 0;
    bool dcache_enabled = (g_boot_cpu_state.sctlr_el1 & (1ULL << 2)) != 0;
    bool icache_enabled = (g_boot_cpu_state.sctlr_el1 & (1ULL << 12)) != 0;
    klog_info(mmu_enabled    ? "    SCTLR.M  : MMU ENABLED" : "    SCTLR.M  : MMU DISABLED");
    klog_info(dcache_enabled ? "    SCTLR.C  : D-Cache ENABLED" : "    SCTLR.C  : D-Cache DISABLED");
    klog_info(icache_enabled ? "    SCTLR.I  : I-Cache ENABLED" : "    SCTLR.I  : I-Cache DISABLED");

    klog_hex("  TCR_EL1   (inherited)", g_boot_cpu_state.tcr_el1);
    klog_hex("  TTBR0_EL1 (inherited)", g_boot_cpu_state.ttbr0_el1);
    klog_hex("  TTBR1_EL1 (inherited)", g_boot_cpu_state.ttbr1_el1);
    klog_hex("  MAIR_EL1  (inherited)", g_boot_cpu_state.mair_el1);
    klog_hex("  CPACR_EL1 (post-entry)", g_boot_cpu_state.cpacr_el1);
    klog_info("    CPACR incoming state: UNKNOWN (entry.S enabled FP/SIMD before capture)");

    klog_hex("  VBAR_EL1  (post-entry)", g_boot_cpu_state.vbar_el1);
    klog_info("    VBAR incoming state: UNKNOWN (entry.S installed vectors before capture)");
    uint64_t expected_vbar = (uint64_t)(uintptr_t)_exception_vectors_base;
    klog_hex("    Expected VBAR    ", expected_vbar);
    if (g_boot_cpu_state.vbar_el1 == expected_vbar) {
        klog_info("    VBAR_EL1 Match   : CONFIRMED (DreyzeOS vectors installed)");
    } else {
        klog_warn("    VBAR_EL1 Match   : MISMATCH (Vectors not pointing to DreyzeOS!)");
    }
}

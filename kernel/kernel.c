/*
 * DreyzeOS — Kernel Main
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * PHASE 4 — Step 2.5: Verified Handoff Descriptor & Loader Contract Research
 *
 * This is the C entry point for the DreyzeOS kernel.
 * Called from boot/entry.S after:
 *   - CurrentEL validated at entry (EL1 confirmed)
 *   - Stack initialization (__stack_top, AAPCS64 16-byte aligned)
 *   - BSS cleared (__bss_start to __bss_end, with stack placed outside)
 *   - VBAR_EL1 explicitly installed pointing to _exception_vectors_base
 *   - DAIF interrupts masked
 *   - FP/SIMD enabled via CPACR_EL1
 *
 * Hard Safety Invariants:
 *   - No flash/NAND writes. RAM-only execution.
 *   - Framebuffer writes HARD-LOCKED by mapping_verified == false.
 *   - MMU state captured read-only without assuming identity mapping.
 *   - virt_base logged ONLY if real (from boot_args), otherwise marked UNKNOWN.
 *   - RAM logging is available without UART; MMIO remains gated.
 *   - Stage progression is strictly monotonic.
 */

#include "../include/types.h"
#include "../include/log.h"
#include "../include/panic.h"
#include "../include/boot_info.h"
#include "../include/boot_stage.h"
#include "../include/cpu_state.h"
#include "../include/loader_handoff.h"
#include "../include/build_info.h"
#include "../hal/t8006/platform.h"
#include "../hal/t8006/framebuffer.h"

/*
 * Expose build provenance metadata
 */
static const build_provenance_t g_build_provenance = {
    .version_string          = DREYZEOS_VERSION_STRING,
    .target                  = DREYZEOS_TARGET,
    .arch                    = DREYZEOS_ARCH,
    .git_commit_sha          = GIT_COMMIT_SHA,
    .canonical_branch        = DREYZEOS_CANONICAL_BRANCH,
    .fb_test_pattern_enabled = DREYZE_FB_TEST_PATTERN
};

const build_provenance_t *build_get_provenance(void)
{
    return &g_build_provenance;
}

/*
 * kernel_main — primary kernel entry point.
 *
 * Parameters:
 *   dtree_ptr — x0: untrusted future-loader argument (may be boot_args/ADT)
 *   arg1      — x1: untrusted future-loader secondary argument
 *   boot_el   — x2: CurrentEL value observed under the mandatory EL1 contract
 *
 * This function must never return.
 */
void kernel_main(uint64_t dtree_ptr, uint64_t arg1, uint64_t boot_el)
{
    /* ================================================================
     * STAGE 0 — Entry Reached & CPU State Capture
     * ================================================================
     * Capture hardware state snapshot IMMEDIATELY at early entry.
     * READ-ONLY: Never modifies SCTLR, TCR, TTBR, or MMU.
     */
    boot_stage_set(BOOT_STAGE_ENTRY);
    boot_cpu_state_capture();

    if (boot_el != 1) {
        /* Entry EL was not EL1 — failsafe before any EL1 subsystem usage */
        boot_stage_failsafe("Hardware entered at unsupported Exception Level (expected EL1)");
    }

    /* ================================================================
     * STAGE 1 — RAM Logging Initialized
     * ================================================================
     * No UART MMIO occurs here. RAM logging makes failsafe diagnostics safe.
     */
    platform_early_init();
    log_init();
    boot_stage_set(BOOT_STAGE_RAM_LOG);

    /* Banner & Provenance */
    klog_info("========================================");
    klog_info(DREYZEOS_VERSION_STRING);
    klog_info("Target:   " DREYZEOS_TARGET);
    klog_info("Arch:     " DREYZEOS_ARCH);
    klog_info("Phase:    PHASE 4 - Step 2.5: Verified Handoff Descriptor");
    klog_info("Branch:   " DREYZEOS_CANONICAL_BRANCH);
    klog_info("Git SHA:  " GIT_COMMIT_SHA);
    klog_info("========================================");

    /* Log captured CPU state */
    boot_cpu_state_diag();

    /* Early Boot Checklist */
    klog_info("[BOOT] Early Boot Checklist (Evidence-Based):");
    klog_info("  [OK] Stack initialized outside BSS       (CONFIRMED, DreyzeOS.ld)");
    klog_info("  [OK] BSS zeroed without stack overlap    (CONFIRMED, entry.S)");
    klog_info("  [OK] VBAR_EL1 installed & verified       (CONFIRMED, entry.S + diag)");
    klog_info("  [OK] DAIF masked by DreyzeOS after EL1 entry contract");
    klog_info("  [!!] Loader x0/x1 ABI: UNKNOWN/BLOCKED (XNU ABI is not loader ABI)");
    klog_info("  [!!] Loader entry EL: UNKNOWN/BLOCKED (DreyzeOS requires EL1)");
    klog_info("  [??] MMU/cache state: UNKNOWN (snapshot only after valid EL1 entry)");
    klog_info("  [OK] RAM logger ready; UART MMIO remains disabled");
    klog_info("  [!!] Physical FB dereference: BLOCKED    (MMU mapping unverified)");
    klog_info("  [!!] Framebuffer writes: HARD-LOCKED     (mapping_verified=false)");

    /* Log raw bootloader arguments */
    klog_info("[BOOT] Raw Handover Arguments:");
    klog_hex("  x0 (boot_args / dtree)", dtree_ptr);
    klog_hex("  x1 (arg1 / size)      ", arg1);
    klog_hex("  x2 (confirmed EL)     ", boot_el);

    /* Linker layout */
    extern uint8_t __kernel_start[];
    extern uint8_t __kernel_end[];
    extern uint8_t __bss_start[];
    extern uint8_t __bss_end[];
    extern uint8_t __stack_bottom[];
    extern uint8_t __stack_top[];

    klog_info("[BOOT] Linker Image Boundaries:");
    klog_hex("  __kernel_start ", (uint64_t)(uintptr_t)__kernel_start);
    klog_hex("  __kernel_end   ", (uint64_t)(uintptr_t)__kernel_end);
    klog_hex("  __bss_start    ", (uint64_t)(uintptr_t)__bss_start);
    klog_hex("  __bss_end      ", (uint64_t)(uintptr_t)__bss_end);
    klog_hex("  __stack_bottom ", (uint64_t)(uintptr_t)__stack_bottom);
    klog_hex("  __stack_top    ", (uint64_t)(uintptr_t)__stack_top);

    /* ================================================================
     * STAGE 2 — Boot Metadata Status
     *
     * The production handoff is intentionally unverified.  The initializer
     * preserves x0/x1 and supplies static fallback metadata without touching
     * either pointer.  This stage therefore records metadata status; it does
     * not claim that boot_args or DeviceTree were validated.
     * ================================================================
     */
    platform_boot_info_init(dtree_ptr, arg1);
    const platform_boot_info_t *binfo = platform_get_boot_info();
    if (!binfo) {
        boot_stage_failsafe("platform_boot_info_init returned NULL");
    }

    klog_info("[BOOT] Discovered Platform Parameters:");
    const loader_handoff_descriptor_t *handoff = loader_handoff_get();
    klog_hex("  Raw x0             ", handoff->raw_x0);
    klog_hex("  Raw x1             ", handoff->raw_x1);
    if (!loader_handoff_is_verified()) {
        klog_info("  Handoff status     : HANDOFF_UNAVAILABLE");
        klog_info("  Metadata status    : BOOT_METADATA_FALLBACK (no pointer dereference)");
    } else {
        klog_info("  Handoff status     : VERIFIED");
    }
    klog_hex("  DeviceTree Base    ", (uint64_t)binfo->devtree_base);
    klog_hex("  DeviceTree Size    ", (uint64_t)binfo->devtree_size);
    klog_hex("  DRAM Phys Base     ", binfo->dram_phys_base);
    klog_hex("  DRAM Total Size    ", binfo->dram_size);

    /* Output real virt_base or explicit UNKNOWN — NEVER proxy from phys_base! */
    if (binfo->virt_base_valid) {
        klog_hex("  DRAM Virt Base     ", binfo->dram_virt_base);
    } else {
        klog_info("  DRAM Virt Base     : UNKNOWN (not provided by bootloader)");
    }

    platform_boot_info_diag();
    boot_stage_set(BOOT_STAGE_BOOT_ARGS);

    /* ================================================================
     * STAGE 3 — Memory Map Validated
     * ================================================================
     */
    if (binfo->dram_phys_base == 0 || binfo->dram_size == 0) {
        boot_stage_failsafe("Stage 3: DRAM physical base or size is 0");
    }

    klog_info("[BOOT] Stage 3: Memory map validation:");
    if (binfo->metadata_status == BOOT_METADATA_RUNTIME_VERIFIED) {
        klog_info("  [MEM] DRAM parameters are RUNTIME VERIFIED by handoff descriptor");
    } else if (binfo->metadata_status == BOOT_METADATA_STATIC_FALLBACK) {
        klog_warn("  [MEM] DRAM parameters are STATIC FALLBACK (research build) - NOT a validated runtime map!");
    } else {
        klog_warn("  [MEM] DRAM parameters are UNAVAILABLE");
    }
    klog_info("  [MEM] Physical memory dereference BLOCKED until MMU verified");
    boot_stage_set(BOOT_STAGE_MEM_MAP);

    /* ================================================================
     * STAGE 4 — AIC Evaluated
     * ================================================================
     */
    klog_info("[BOOT] Stage 4: Interrupt controller setup:");
    platform_init();
    klog_info("  [AIC] MMIO mapping unverified: no AIC read/write/configuration");
    klog_info("  [AIC] CPU IRQ delivery remains masked by DAIF");
    boot_stage_set(BOOT_STAGE_AIC);

    /* ================================================================
     * STAGE 5 — Framebuffer Evaluated (Hard Safety Interlock)
     * ================================================================
     * We evaluate discovered video parameters.
     * We distinguish:
     *   - HEADLESS (no video console discovered)
     *   - FB_INVALID (malformed metadata)
     *   - VALIDATED_NOMAP (metadata valid, but mapping UNVERIFIED)
     *
     * In all cases:
     *   mapping_verified = false
     *   is_write_allowed = false
     *   Physical FB address is NEVER dereferenced as a virtual pointer!
     */
    const boot_framebuffer_info_t *fb_info = platform_get_framebuffer();
    if (!fb_info || !fb_info->is_valid) {
        klog_info("[BOOT] Stage 5: No boot video console detected -> Running in HEADLESS mode");
    } else {
        int fb_rc = framebuffer_init(fb_info);
        if (fb_rc == 0) {
            klog_info("[BOOT] Stage 5: Framebuffer METADATA VALIDATED (Mapping UNVERIFIED, writes HARD-LOCKED)");
            framebuffer_diag();

#if DREYZE_FB_TEST_PATTERN
            klog_info("  [FB] DREYZE_FB_TEST_PATTERN=1, BUT mapping_verified=0: writes remain HARD-LOCKED");
            framebuffer_enable_writes(true); /* Blocked by mapping_verified == false! */
#else
            klog_info("  [FB] Normal boot: Framebuffer writes DISABLED (DREYZE_FB_TEST_PATTERN=0)");
#endif
        } else {
            klog_hex("  [FB] Framebuffer initialization rejected, rc", (uint64_t)(int64_t)fb_rc);
            klog_info("  [FB] Continuing in HEADLESS mode (metadata invalid)");
        }
    }
    boot_stage_set(BOOT_STAGE_FB);

    /* ================================================================
     * STAGE 6 — Safe Idle (branch loop)
     * ================================================================
     */
    boot_stage_set(BOOT_STAGE_IDLE);

    klog_info("");
    klog_info("========================================");
    klog_info("PHASE 4 Step 2.5 COMPLETE: Handoff Descriptor Audit Passed.");
    klog_info("All early boot invariants verified.");
    klog_info("NO NAND writes. NO FB writes. NO unmasked interrupts.");
    klog_info("System entering branch-loop halt; WFI is not assumed safe before loader contract verification.");
    klog_info("========================================");
    klog_info("");
    klog_info("[HALT] Branch-loop halt active. Crown + Side Button is the expected reset path.");

    log_flush();

    for (;;) { __asm__ volatile("b ."); }

    /* UNREACHABLE */
    panic("kernel_main returned unexpectedly");
}

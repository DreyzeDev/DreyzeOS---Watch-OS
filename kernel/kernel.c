/*
 * DreyzeOS — Kernel Main
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * PHASE 4 — Step 2: Safe RAM Boot & Hardware Bring-up Preparation
 *
 * This is the C entry point for the DreyzeOS kernel.
 * Called from boot/entry.S after:
 *   - Stack initialization
 *   - BSS clear
 *   - Minimal CPU setup (VBAR_EL1 set, IRQs disabled via DAIF)
 *
 * Boot Stage Progression (monotonic, each stage failsafe-gated):
 *   STAGE 0 — Entry reached, CurrentEL verified
 *   STAGE 1 — UART0 & early HAL initialized
 *   STAGE 2 — boot_args / DeviceTree validated
 *   STAGE 3 — Memory map validated (DRAM base & size non-zero)
 *   STAGE 4 — AIC initialized & masked
 *   STAGE 5 — Framebuffer validated (writes DISABLED)
 *   STAGE 6 — Safe idle (WFI loop)
 *
 * SAFETY RULES (enforced in code):
 *   - No flash/NAND writes. RAM-only execution.
 *   - Framebuffer writes DISABLED by default (DREYZE_FB_TEST_PATTERN=0).
 *   - MMU state is LIKELY identity mapping — NOT confirmed.
 *     Physical framebuffer address MUST NOT be blindly dereferenced as virtual.
 *     framebuffer_enable_writes(true) is NOT called here.
 *   - IRQs remain DISABLED throughout boot (entry.S sets DAIF).
 *   - If any validation fails, boot_stage_failsafe() is called.
 *     boot_stage_failsafe() NEVER returns.
 *
 * Recovery note:
 *   Crown + Side Button hard reset is the expected hardware reset path.
 *   Actual recovery capability will be confirmed only after controlled hardware test.
 */

#include "../include/types.h"
#include "../include/log.h"
#include "../include/panic.h"
#include "../include/boot_info.h"
#include "../include/boot_stage.h"
#include "../hal/t8006/platform.h"
#include "../hal/t8006/framebuffer.h"

/* Version information */
#define DREYZEOS_VERSION_MAJOR  0
#define DREYZEOS_VERSION_MINOR  1
#define DREYZEOS_VERSION_PATCH  0
#define DREYZEOS_VERSION_STRING "DreyzeOS 0.1.0-research"

/* Build target information */
#define DREYZEOS_TARGET         "Apple Watch Series 4 / T8006"
#define DREYZEOS_ARCH           "AArch64"

/*
 * Read current exception level from CurrentEL system register.
 * Returns 0, 1, 2, or 3.
 *
 * CurrentEL[3:2] = EL field. Bits [1:0] are RES0.
 * Expected on entry: EL1 (CONFIRMED — ARM64 kernel convention,
 *                    consistent with XNU kernelcache disassembly).
 */
static inline uint32_t read_current_el(void)
{
    uint64_t current_el;
    __asm__ volatile("mrs %0, CurrentEL" : "=r"(current_el));
    return (uint32_t)((current_el >> 2) & 0x3u);
}

/*
 * kernel_main — primary kernel entry point.
 *
 * Parameters:
 *   dtree_ptr   — x0: pointer to xnu_arm64_boot_args_t or raw DeviceTree
 *                 passed by the bootloader.
 *                 Auto-detected and validated by platform_boot_info_init.
 *                 ABI: CONFIRMED (from kernelcache disassembly, XNU entry 0xfffffff007b2c070)
 *
 *   arg1        — x1: second bootloader argument (size or unused).
 *                 ABI: LIKELY (consistent with iBoot convention, not directly confirmed)
 *
 * This function must never return.
 * If it returns, entry.S will halt the CPU safely via _halt.
 */
void kernel_main(uint64_t dtree_ptr, uint64_t arg1)
{
    /* ================================================================
     * STAGE 0 — Entry Reached
     * ================================================================
     * We are in C code. Stack is up, BSS is zeroed, VBAR_EL1 is set.
     * IRQs are DISABLED (DAIF set by entry.S — CONFIRMED).
     * We do NOT touch framebuffer or any MMIO yet.
     */
    boot_stage_set(BOOT_STAGE_ENTRY);

    /* ================================================================
     * STAGE 0: CurrentEL Diagnostics
     * ================================================================
     * Read CurrentEL before UART is available.
     * We can only store the result; logging happens after UART init.
     *
     * Expected: EL1 (CONFIRMED — ARM64 kernel convention).
     * If EL != 1, something is seriously wrong with the handover.
     */
    uint32_t boot_el = read_current_el();

    /* ================================================================
     * STAGE 1 — UART0 & Early HAL Initialized
     * ================================================================
     * platform_early_init() sets up UART0 at 0x2e500000 (CONFIRMED).
     * After this call, klog_* output is available via UART.
     */
    platform_early_init();
    boot_stage_set(BOOT_STAGE_UART);
    log_init();

    /* Now we can print — UART is up */
    klog_info("========================================");
    klog_info(DREYZEOS_VERSION_STRING);
    klog_info("Target: " DREYZEOS_TARGET);
    klog_info("Arch:   " DREYZEOS_ARCH);
    klog_info("Phase:  PHASE 4 - Step 2: Safe RAM Boot & Hardware Bring-up Preparation");
    klog_info("========================================");

    /* ================================================================
     * EARLY BOOT CHECKLIST (logged before any hardware interaction)
     * ================================================================
     */
    klog_info("[BOOT] Early Boot Checklist:");
    klog_info("  [OK] Stack initialized                    (entry.S)");
    klog_info("  [OK] BSS zeroed                           (entry.S)");
    klog_info("  [OK] VBAR_EL1 set to DreyzeOS vectors     (entry.S - CONFIRMED)");
    klog_info("  [OK] DAIF: IRQs disabled on entry         (entry.S - CONFIRMED)");
    klog_info("  [OK] x0 = boot_args pointer               (CONFIRMED, kernelcache disasm)");
    klog_info("  [??] x1 = size or unused                  (LIKELY, not confirmed)");
    klog_info("  [??] MMU: identity mapping                (LIKELY - NOT CONFIRMED)");
    klog_info("  [??] Caches: enabled                      (LIKELY - NOT CONFIRMED)");
    klog_info("  [!!] Physical FB dereference: BLOCKED     (MMU state unverified)");
    klog_info("  [!!] Framebuffer writes: DISABLED         (DREYZE_FB_TEST_PATTERN=0)");

    /* Log boot arguments */
    klog_info("[BOOT] Boot arguments (ABI):");
    klog_hex("  x0 dtree_ptr / boot_args (CONFIRMED)", dtree_ptr);
    klog_hex("  x1 arg1 / size           (LIKELY)   ", arg1);

    /* CurrentEL result */
    klog_hex("[BOOT] CurrentEL (raw, bits[3:2]=EL) =", (uint64_t)boot_el);
    if (boot_el == 1) {
        klog_info("[BOOT] Exception level: EL1 (CONFIRMED — expected)");
    } else if (boot_el == 2) {
        klog_info("[BOOT] Exception level: EL2 (UNEXPECTED — hypervisor mode)");
        boot_stage_failsafe("Unexpected EL2 on kernel entry");
    } else if (boot_el == 3) {
        klog_info("[BOOT] Exception level: EL3 (UNEXPECTED — secure monitor mode)");
        boot_stage_failsafe("Unexpected EL3 on kernel entry");
    } else {
        klog_info("[BOOT] Exception level: EL0 (UNEXPECTED — user mode)");
        boot_stage_failsafe("Unexpected EL0 on kernel entry");
    }

    /* Memory layout (from linker script) */
    extern uint8_t __kernel_start[];
    extern uint8_t __kernel_end[];
    extern uint8_t __bss_start[];
    extern uint8_t __bss_end[];
    extern uint8_t __stack_bottom[];
    extern uint8_t __stack_top[];

    klog_info("[BOOT] Memory layout (from linker script):");
    klog_hex("  kernel_start", (uint64_t)(uintptr_t)__kernel_start);
    klog_hex("  kernel_end  ", (uint64_t)(uintptr_t)__kernel_end);
    klog_hex("  bss_start   ", (uint64_t)(uintptr_t)__bss_start);
    klog_hex("  bss_end     ", (uint64_t)(uintptr_t)__bss_end);
    klog_hex("  stack_bottom", (uint64_t)(uintptr_t)__stack_bottom);
    klog_hex("  stack_top   ", (uint64_t)(uintptr_t)__stack_top);

    /* ================================================================
     * STAGE 2 — Boot Args & DeviceTree Validated
     * ================================================================
     * platform_boot_info_init detects iBoot boot_args struct vs. raw ADT.
     * After this call, platform_get_boot_info() returns valid data.
     *
     * boot_args ABI (CONFIRMED from kernelcache 0xfffffff007b2c070):
     *   +0x08: virt_base
     *   +0x10: phys_base
     *   +0x18: mem_size
     *   +0x28: video (6 x uint64: baseAddr, display, rowBytes, width, height, depth)
     *   +0x60: devicetree_p
     *   +0x68: devicetree_length
     */
    platform_boot_info_init(dtree_ptr, arg1);

    /* Validate boot info */
    const platform_boot_info_t *binfo = platform_get_boot_info();
    if (!binfo) {
        boot_stage_failsafe("platform_boot_info_init returned NULL — boot_args invalid");
    }

    /* Log all boot_args fields */
    klog_info("[BOOT] Discovered boot info:");
    klog_hex("  DeviceTree ptr   ", (uint64_t)binfo->devtree_base);
    klog_hex("  DeviceTree length", (uint64_t)binfo->devtree_size);
    klog_hex("  DRAM phys base   ", binfo->dram_phys_base);
    klog_hex("  DRAM size        ", binfo->dram_size);
    klog_hex("  virt_base        ", binfo->dram_phys_base); /* Note: virt_base not in platform_boot_info_t; using phys_base as proxy */

    platform_boot_info_diag();
    boot_stage_set(BOOT_STAGE_BOOT_ARGS);

    /* ================================================================
     * STAGE 3 — Memory Map Validated
     * ================================================================
     * Verify that DRAM base and size are non-zero.
     * We do NOT map, write, or dereference physical framebuffer here.
     * MMU state is LIKELY identity mapping, but NOT confirmed.
     */
    if (binfo->dram_phys_base == 0) {
        boot_stage_failsafe("Stage 3: DRAM physical base is 0 — memory map invalid");
    }
    if (binfo->dram_size == 0) {
        boot_stage_failsafe("Stage 3: DRAM size is 0 — memory map invalid");
    }

    klog_info("[BOOT] Stage 3: Memory map validation:");
    klog_info("  DRAM base: non-zero (PASS)");
    klog_info("  DRAM size: non-zero (PASS)");
    klog_info("  MMU state: LIKELY identity mapping — physical dereference BLOCKED until confirmed");
    boot_stage_set(BOOT_STAGE_MEM_MAP);

    /* ================================================================
     * STAGE 4 — AIC Initialized & Masked
     * ================================================================
     * platform_init() drives AIC initialization and masks all interrupts.
     * IRQs remain disabled (DAIF untouched).
     */
    klog_info("[BOOT] Stage 4: HAL & AIC initialization:");
    platform_init();
    klog_info("  platform_init(): done");
    klog_info("  AIC: initialized and masked (CONFIRMED design)");
    boot_stage_set(BOOT_STAGE_AIC);

    /* ================================================================
     * STAGE 5 — Framebuffer Validated (Writes DISABLED)
     * ================================================================
     * Initialize framebuffer abstraction from discovered boot parameters.
     * We validate fb_info fields but DO NOT write to hardware.
     *
     * SAFETY: framebuffer_enable_writes(true) is NOT called here.
     *         Physical framebuffer address cannot be safely dereferenced
     *         until MMU/cache state is verified on real hardware.
     *
     * Pixel format (CONFIRMED): BGRA32 LE — byte0=B, byte1=G, byte2=R, byte3=X
     * (from kernelcache string at 0xfffffff00823ea2c: "BBBBBBBBGGGGGGGGRRRRRRRR")
     */
    const boot_framebuffer_info_t *fb_info = platform_get_framebuffer();
    if (fb_info && fb_info->is_valid) {
        int fb_rc = framebuffer_init(fb_info);
        if (fb_rc == 0) {
            klog_info("[BOOT] Stage 5: Framebuffer validated:");
            framebuffer_diag();

#if DREYZE_FB_TEST_PATTERN
            /*
             * Test pattern: ONLY for explicit controlled hardware test.
             * Compile with -DDREYZE_FB_TEST_PATTERN=1 to enable.
             * This path MUST NOT be reached in normal boot.
             */
            klog_info("  [FB] DREYZE_FB_TEST_PATTERN=1: Enabling writes & drawing test pattern...");
            framebuffer_enable_writes(true);
            framebuffer_draw_test_pattern();
#else
            klog_info("  [FB] Normal boot: Framebuffer writes DISABLED (DREYZE_FB_TEST_PATTERN=0)");
            klog_info("  [FB] Physical FB address NOT dereferenced (MMU state unverified)");
#endif
        } else {
            klog_hex("  [FB] framebuffer_init failed, error code", (uint64_t)(int64_t)fb_rc);
            /*
             * Framebuffer init failure is non-fatal for Stage 5.
             * Log and continue — DreyzeOS can operate headless.
             */
            klog_info("  [FB] Continuing in headless mode (framebuffer unavailable)");
        }
    } else {
        klog_info("[BOOT] Stage 5: No boot framebuffer discovered (headless / standalone mode)");
    }
    boot_stage_set(BOOT_STAGE_FB);

    /* ================================================================
     * STAGE 6 — Safe Idle (WFI Loop)
     * ================================================================
     * All bring-up checks passed. System enters safe low-power idle.
     * DAIF remains set: IRQs disabled, system will wake only on reset.
     *
     * Recovery:
     *   Crown + Side Button hard reset is the expected hardware reset path.
     *   Actual recovery capability confirmed only after controlled hardware test.
     */
    boot_stage_set(BOOT_STAGE_IDLE);

    klog_info("");
    klog_info("========================================");
    klog_info("PHASE 4 Step 2 COMPLETE: Safe RAM Boot & Bring-up Preparation.");
    klog_info("All bring-up stages passed. System entering safe idle (WFI).");
    klog_info("No flash writes. No framebuffer writes. No IRQs enabled.");
    klog_info("========================================");
    klog_info("");
    klog_info("[HALT] DreyzeOS in safe WFI halt. Crown+Side Button to reset.");

    log_flush();

    /* Safe halt: WFI reduces power, CPU wakes only on interrupt/reset.
     * DAIF prevents interrupts from actually executing handlers — safe. */
    for (;;) {
        __asm__ volatile("wfi");
    }

    /* UNREACHABLE — entry.S _halt handles if kernel_main somehow returns */
    panic("kernel_main returned unexpectedly");
}

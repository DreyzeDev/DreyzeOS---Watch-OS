/*
 * DreyzeOS — Kernel Main
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * This is the C entry point for the DreyzeOS kernel.
 * Called from boot/entry.S after:
 *   - Stack initialization
 *   - BSS clear
 *   - Minimal CPU setup
 *
 * SAFETY: No flash writes. RAM-only execution.
 */

#include "../include/types.h"
#include "../include/log.h"
#include "../include/panic.h"
#include "../hal/t8006/platform.h"

/* Version information */
#define DREYZEOS_VERSION_MAJOR  0
#define DREYZEOS_VERSION_MINOR  1
#define DREYZEOS_VERSION_PATCH  0
#define DREYZEOS_VERSION_STRING "DreyzeOS 0.1.0-research"

/* Build target information */
#define DREYZEOS_TARGET         "Apple Watch Series 4 / T8006"
#define DREYZEOS_ARCH           "AArch64"

/*
 * Kernel build phase tracking.
 * These constants document what is implemented at each build.
 */
#define PHASE_RESEARCH_BUILD    1  /* Phase 1: Research build — basic boot only */

/*
 * kernel_main — primary kernel entry point.
 *
 * Parameters:
 *   dtree_ptr   — possible pointer to Apple DeviceTree passed by bootloader.
 *                 Status: LIKELY (XNU convention), UNCONFIRMED for T8006 entry.
 *   arg1        — second bootloader argument. UNKNOWN purpose for T8006.
 *
 * This function must never return.
 * If it returns, entry.S will halt the CPU safely.
 */
void kernel_main(uint64_t dtree_ptr, uint64_t arg1)
{
    /*
     * Step 1: Initialize HAL (Hardware Abstraction Layer).
     * This sets up any hardware we know about on T8006.
     * At this phase, most HAL functions are stubs — they exist but don't
     * talk to real hardware yet because MMIO addresses are UNKNOWN.
     */
    platform_early_init();

    /*
     * Step 2: Early log initialization.
     * On T8006: UART base address is UNKNOWN.
     * For now: log_init() sets up a RAM buffer log.
     * Real UART output requires confirmed UART_BASE from DeviceTree.
     */
    log_init();

    /*
     * Step 3: Print banner.
     * At this phase we are not driving a display.
     * Output goes to the internal RAM log buffer (retrievable via debugger).
     */
    klog_info("========================================");
    klog_info(DREYZEOS_VERSION_STRING);
    klog_info("Target: " DREYZEOS_TARGET);
    klog_info("Arch:   " DREYZEOS_ARCH);
    klog_info("Phase:  PHASE 1 — Research Build");
    klog_info("========================================");

    /*
     * Step 4: Log boot arguments.
     * x0 at entry (dtree_ptr) MAY be a DeviceTree pointer.
     * Status: LIKELY based on XNU/PongoOS convention.
     * We log it for research, do NOT dereference yet.
     */
    klog_info("Boot arguments:");
    klog_hex("  x0 (possible dtree_ptr)", dtree_ptr);
    klog_hex("  x1 (unknown arg1)       ", arg1);

    if (dtree_ptr != 0) {
        klog_info("  x0 != 0 — possible DeviceTree present (UNCONFIRMED)");
        klog_info("  DeviceTree parsing: PHASE 3 milestone");
    } else {
        klog_info("  x0 == 0 — no DeviceTree pointer (or different entry convention)");
    }

    /*
     * Step 5: Log memory layout (from linker script).
     * Addresses here come from our linker script, NOT from real T8006 mapping.
     * Real addresses: UNKNOWN_T8006_LOAD_ADDRESS
     */
    extern uint8_t __kernel_start[];
    extern uint8_t __kernel_end[];
    extern uint8_t __bss_start[];
    extern uint8_t __bss_end[];
    extern uint8_t __stack_bottom[];
    extern uint8_t __stack_top[];

    klog_info("Memory layout (from linker script):");
    klog_hex("  kernel_start", (uint64_t)(uintptr_t)__kernel_start);
    klog_hex("  kernel_end  ", (uint64_t)(uintptr_t)__kernel_end);
    klog_hex("  bss_start   ", (uint64_t)(uintptr_t)__bss_start);
    klog_hex("  bss_end     ", (uint64_t)(uintptr_t)__bss_end);
    klog_hex("  stack_bottom", (uint64_t)(uintptr_t)__stack_bottom);
    klog_hex("  stack_top   ", (uint64_t)(uintptr_t)__stack_top);

    /*
     * Step 6: Platform initialization (STUB — no real hardware yet).
     * When MMIO addresses are known, these will initialize real hardware.
     */
    klog_info("HAL initialization (stub):");
    platform_init();
    klog_info("  platform_init(): done (stub)");

    /*
     * Step 7: Research phase complete notice.
     * In later phases:
     *   - Phase 3: timer_init(), DeviceTree parsing
     *   - Phase 7: display_init(), draw framebuffer
     *   - Phase 8: crown_init(), button_init()
     *   - Phase 9: touch_init()
     */
    klog_info("");
    klog_info("PHASE 1 COMPLETE: Research build booted successfully.");
    klog_info("Kernel halting. Waiting for Phase 3 hardware research.");
    klog_info("See docs/RESEARCH.md and docs/HARDWARE.md for T8006 findings.");

    /*
     * Step 8: Safe halt loop.
     * We spin with WFI to reduce power usage.
     * This is safe — no side effects, device wakes on interrupt or reset.
     */
    klog_info("");
    klog_info("[HALT] DreyzeOS entering safe halt. Reboot to recover.");

    /* Flush log buffer if we ever have a UART */
    log_flush();

    /* Halt — entry.S _halt will be called if we return,
     * but we use an explicit loop here too. */
    for (;;) {
        __asm__ volatile ("wfi");
    }

    /* UNREACHABLE */
    panic("kernel_main returned unexpectedly");
}

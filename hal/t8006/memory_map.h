/*
 * DreyzeOS — T8006 Memory Map
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * STATUS LEGEND:
 *   CONFIRMED  — verified from public documentation, DeviceTree dump, or experiment
 *   LIKELY     — strongly inferred from similar Apple SoCs (e.g. T8010, T8015)
 *   UNKNOWN    — not yet determined; placeholder used
 *   EXPERIMENTAL — hypothesis being tested
 *   BLOCKED    — cannot determine without device access or closed-source info
 *
 * ============================================================
 * CRITICAL RULE:
 *   Do NOT use UNKNOWN_T8006_* addresses in code that will execute
 *   on real hardware. They are placeholders for documentation only.
 *   Using a wrong MMIO address can freeze or crash the device.
 * ============================================================
 */

#pragma once

#include "include/types.h"

/* ============================================================
 * CPU Architecture Information
 * ============================================================ */

/*
 * T8006 CPU cores: LIKELY 2x Cortex-A32 derived (ARM64_32)
 * Status: LIKELY — Apple S4 based on published performance data
 *
 * NOTE: Apple Watch Series 4 watchOS userspace uses ARM64_32 (ILP32 ABI):
 *   - 64-bit instruction set (AArch64)
 *   - 32-bit pointers in userspace
 * XNU kernel itself runs full AArch64.
 * Bare-metal code (DreyzeOS) runs full AArch64.
 */
#define T8006_CPU_ARCH_KERNEL   "AArch64"       /* CONFIRMED for XNU on all modern Apple SoCs */
#define T8006_CPU_ARCH_USER     "ARM64_32"      /* CONFIRMED — watchOS userspace ABI */

/* ============================================================
 * RAM Layout
 * Status: UNKNOWN — requires DeviceTree dump or iBoot analysis
 * ============================================================
 *
 * Similar Apple SoCs (for reference only — do NOT assume same for T8006):
 *   T8010 (A10): DRAM base = 0x800000000 (iBoot conventional)
 *   T8015 (A11): DRAM base = 0x800000000
 *   T8006 (S4):  UNKNOWN — Apple Watch has very different memory config
 *
 * Apple Watch Series 4 RAM: 1 GB total (LPDDR3 or LPDDR4)
 * Source: iFixit teardown (CONFIRMED quantity, NOT base address)
 */
#define UNKNOWN_T8006_DRAM_BASE         0xDEADBEEFDEADBEEFULL  /* UNKNOWN */
#define UNKNOWN_T8006_DRAM_SIZE         (1ULL * 1024 * 1024 * 1024)  /* 1GB — CONFIRMED from teardown */
#define UNKNOWN_T8006_LOAD_ADDRESS      0xDEADBEEFDEADBEEFULL  /* UNKNOWN — kernel load addr */

/*
 * For the research build linker script, we use a PLACEHOLDER address.
 * This CANNOT be used on real hardware without confirmation.
 * The placeholder is chosen to be obviously wrong (not a valid ARM64 address
 * that would silently succeed and corrupt memory).
 */
#define DREYZEOS_PLACEHOLDER_LOAD_ADDR  0x0000000100000000ULL  /* Placeholder only */

/* ============================================================
 * UART
 * Status: UNKNOWN — Apple Watch may not have accessible UART
 * ============================================================
 *
 * Notes:
 *   - Apple Watch does NOT have a standard debug UART on external pins
 *   - Internal UART may exist for debug builds (UNKNOWN if exploitable)
 *   - PongoOS uses Apple's "debug UART" on iPhone SoCs via specific MMIO
 *   - T8006 UART MMIO base: UNKNOWN
 *   - Apple Watch development cables with debug UART: UNKNOWN availability
 */
#define UNKNOWN_T8006_UART_BASE         0xDEADBEEFDEADBEEFULL  /* UNKNOWN */
#define UNKNOWN_T8006_UART_SIZE         0x10000                  /* UNKNOWN */

/* Samsung s3c6400 compatible UART offset registers (for reference) */
#define UART_ULCON_OFFSET   0x00  /* Line control */
#define UART_UCON_OFFSET    0x04  /* Control */
#define UART_UFCON_OFFSET   0x08  /* FIFO control */
#define UART_UTXH_OFFSET    0x20  /* TX holding */
#define UART_URXH_OFFSET    0x24  /* RX holding */
#define UART_UTRSTAT_OFFSET 0x10  /* TX/RX status */

/* ============================================================
 * Display / Framebuffer
 * Status: UNKNOWN — needs DeviceTree analysis
 * ============================================================
 *
 * Apple Watch Series 4 display:
 *   - OLED LTPO, 448x368 (44mm) or 394x324 (40mm)
 *   - Display controller: UNKNOWN (Apple custom)
 *   - Framebuffer base: UNKNOWN — allocated by iBoot, passed in DeviceTree
 *   - Bytes per pixel: LIKELY 4 (BGRA8888)
 *
 * Strategy: read framebuffer base from Apple DeviceTree node
 *   "display0" → "reg" property → framebuffer base address
 */
#define UNKNOWN_T8006_FRAMEBUFFER_BASE  0xDEADBEEFDEADBEEFULL  /* UNKNOWN */
#define UNKNOWN_T8006_DISPLAY_WIDTH_44  448  /* CONFIRMED — 44mm model */
#define UNKNOWN_T8006_DISPLAY_HEIGHT_44 368  /* CONFIRMED — 44mm model */
#define UNKNOWN_T8006_DISPLAY_WIDTH_40  394  /* CONFIRMED — 40mm model */
#define UNKNOWN_T8006_DISPLAY_HEIGHT_40 324  /* CONFIRMED — 40mm model */

/* ============================================================
 * Interrupt Controller
 * Status: UNKNOWN — Apple uses custom AIC (Apple Interrupt Controller)
 * ============================================================
 *
 * Apple SoCs use the Apple Interrupt Controller (AIC), NOT standard GIC.
 * AIC MMIO base: UNKNOWN for T8006.
 * AIC is documented partially in XNU source (osfmk/arm/AIC.h in some versions).
 */
#define UNKNOWN_T8006_AIC_BASE          0xDEADBEEFDEADBEEFULL  /* UNKNOWN */
#define UNKNOWN_T8006_AIC_SIZE          0x100000                 /* UNKNOWN */

/* ============================================================
 * Power Management (PMGR)
 * Status: UNKNOWN
 * ============================================================ */
#define UNKNOWN_T8006_PMGR_BASE         0xDEADBEEFDEADBEEFULL  /* UNKNOWN */

/* ============================================================
 * SPI / I2C Controllers
 * Status: UNKNOWN
 * ============================================================
 *
 * Touch controller and Digital Crown likely use SPI or I2C.
 * Bus assignments: UNKNOWN — needs DeviceTree.
 */
#define UNKNOWN_T8006_SPI0_BASE         0xDEADBEEFDEADBEEFULL  /* UNKNOWN */
#define UNKNOWN_T8006_SPI1_BASE         0xDEADBEEFDEADBEEFULL  /* UNKNOWN */
#define UNKNOWN_T8006_I2C0_BASE         0xDEADBEEFDEADBEEFULL  /* UNKNOWN */
#define UNKNOWN_T8006_I2C1_BASE         0xDEADBEEFDEADBEEFULL  /* UNKNOWN */

/* ============================================================
 * GPIO
 * Status: UNKNOWN
 * ============================================================ */
#define UNKNOWN_T8006_GPIO_BASE         0xDEADBEEFDEADBEEFULL  /* UNKNOWN */

/* ============================================================
 * Timer
 * Status: UNKNOWN — Apple uses custom timer, not ARM generic timer only
 * ============================================================
 *
 * ARM64 generic timer (CNTPCT_EL0) is available on all AArch64 CPUs.
 * Apple's PMGR timer: UNKNOWN base for T8006.
 */
#define T8006_ARM_GENERIC_TIMER_FREQ    24000000  /* LIKELY 24MHz — standard for Apple SoCs */

/* ============================================================
 * Touch Controller
 * Status: UNKNOWN — Apple custom or Broadcom/Cirque
 * ============================================================ */
#define UNKNOWN_T8006_TOUCH_CONTROLLER  "UNKNOWN"  /* IC model: UNKNOWN */
#define UNKNOWN_T8006_TOUCH_BUS         "UNKNOWN"  /* SPI or I2C: UNKNOWN */
#define UNKNOWN_T8006_TOUCH_IRQ         0xFF        /* IRQ number: UNKNOWN */

/* ============================================================
 * Digital Crown
 * Status: UNKNOWN
 * ============================================================ */
#define UNKNOWN_T8006_CROWN_BUS         "UNKNOWN"  /* Interface: UNKNOWN */
#define UNKNOWN_T8006_CROWN_IRQ         0xFF        /* IRQ number: UNKNOWN */

/* ============================================================
 * Side Button
 * Status: UNKNOWN
 * ============================================================ */
#define UNKNOWN_T8006_BUTTON_GPIO       0xFF        /* GPIO number: UNKNOWN */
#define UNKNOWN_T8006_BUTTON_IRQ        0xFF        /* IRQ number: UNKNOWN */

/* ============================================================
 * MMIO access macros (for when addresses are known)
 * ============================================================ */
#define MMIO_READ32(addr)       (*((volatile uint32_t *)(uintptr_t)(addr)))
#define MMIO_WRITE32(addr, val) (*((volatile uint32_t *)(uintptr_t)(addr)) = (val))
#define MMIO_READ64(addr)       (*((volatile uint64_t *)(uintptr_t)(addr)))
#define MMIO_WRITE64(addr, val) (*((volatile uint64_t *)(uintptr_t)(addr)) = (val))

/* Safety check — never use these on UNKNOWN addresses */
#define MMIO_ADDR_IS_UNKNOWN(addr)  ((addr) == 0xDEADBEEFDEADBEEFULL)

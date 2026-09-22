/*
 * DreyzeOS — T8006 Memory Map
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * STATUS LEGEND:
 *   CONFIRMED    — verified directly from Apple DeviceTree (DeviceTree.n131bap.adt)
 *   LIKELY       — strongly inferred from similar Apple SoCs or XNU kernelcache
 *   UNKNOWN      — dynamically populated at runtime by iBoot
 *   DESIGN       — research-only input, not a hardware proof
 *   BLOCKED      — requires specialized coprocessor interaction
 *
 * ============================================================
 * Discovered during PHASE 2 from official watchOS 10.6.1 (21U580)
 * DeviceTree (N131bAP) for Apple Watch Series 4 (Watch4,2).
 * ============================================================
 */

#pragma once

#include "include/types.h"

/* ============================================================
 * CPU Architecture Information
 * ============================================================ */

/*
 * T8006 CPU cores: Dual-core "apple,tempest" (A12-generation energy-efficient cores)
 * Status: CONFIRMED from DeviceTree (/cpus/cpu0, /cpus/cpu1 compatible)
 * L2 cache: 2MB (2,097,152 bytes)
 * Coresight debug registers: cpu0=0x208010000, cpu1=0x208110000
 */
#define T8006_CPU_CORE_NAME     "apple,tempest"
#define T8006_CPU_ARCH_KERNEL   "AArch64"       /* CONFIRMED — 64-bit kernel mode */
#define T8006_CPU_ARCH_USER     "ARM64_32"      /* CONFIRMED — watchOS userspace ABI */
#define T8006_CPU_NUM_CORES     2               /* CONFIRMED — dual core */

/* ============================================================
 * RAM Layout
 * ============================================================
 *
 * Apple Watch Series 4 product-memory quantity: 1 GiB (research quantity).
 * Status: static /memory is [0x0+0x0]; live base and usable range are
 * UNKNOWN/BLOCKED. No historical DRAM fallback is compiled into runtime
 * boot-info fields.
 */
#define DREYZEOS_PLACEHOLDER_LOAD_ADDR  0x0000000100000000ULL  /* Linker placeholder */

/* ============================================================
 * Interrupt Controller (AIC)
 * Status: CONFIRMED from /arm-io/aic & kernelcache disassembly
 * ============================================================ */
#define T8006_AIC_BASE                  0x000000002d180000ULL  /* CONFIRMED — 32KB (0x8000) */
#define T8006_AIC_SIZE                  0x00008000ULL
#define T8006_AIC_VERSION               2                      /* aic-version = 2 (AIC2) */

/* AIC Confirmed Registers (Offsets from T8006_AIC_BASE) */
#define AIC_REVISION_OFFSET             0x0000                 /* CONFIRMED */
#define AIC_INFO_OFFSET                 0x0004                 /* CONFIRMED */
#define AIC_CONFIG_OFFSET               0x0010                 /* CONFIRMED */
#define AIC_WHOAMI_OFFSET               0x2000                 /* CONFIRMED */
#define AIC_EVENT_OFFSET                0x2004                 /* CONFIRMED — IACK */
#define AIC_IPI_SEND_OFFSET             0x2008                 /* CONFIRMED */
#define AIC_IPI_ACK_OFFSET              0x200C                 /* CONFIRMED */
#define AIC_MASK_SET_OFFSET             0x4000                 /* CONFIRMED — IRQ Disable */
#define AIC_MASK_CLR_OFFSET             0x4080                 /* CONFIRMED — IRQ Enable / EOI */
#define AIC_HW_STATE_OFFSET             0x4200                 /* CONFIRMED — Line status */

/* AIC Timebase (Timer) */
#define T8006_AIC_TIMEBASE_BASE         0x000000002d188000ULL  /* CONFIRMED — 4KB (0x1000) */
#define T8006_AIC_TIMEBASE_SIZE         0x00001000ULL

/*
 * ARM Generic Timer
 * CNTFRQ_EL0 is the authoritative runtime frequency source. No static T8006
 * frequency is asserted here.
 */

/* ============================================================
 * UART Controllers
 * Status: CONFIRMED from /arm-io/uart*
 * ============================================================ */
/* UART0: Primary boot console (has "boot-console" DT property) */
#define T8006_UART0_BASE                0x000000002e500000ULL  /* CONFIRMED — 16KB (0x4000) */
#define T8006_UART0_SIZE                0x00004000ULL
#define T8006_UART0_IRQ                 262                    /* 0x106 */

/* UART1: GPS interface (BCM4773) */
#define T8006_UART1_BASE                0x000000002e504000ULL  /* CONFIRMED */
#define T8006_UART1_SIZE                0x00004000ULL
#define T8006_UART1_IRQ                 263                    /* 0x107 */

/* UART2: NFC interface (Stockholm) */
#define T8006_UART2_BASE                0x000000002e508000ULL  /* CONFIRMED */
#define T8006_UART2_SIZE                0x00004000ULL
#define T8006_UART2_IRQ                 264                    /* 0x108 */

/* DockChannel UART (Diagnostics) */
#define T8006_DOCKCHANNEL_UART_BASE     0x000000003d128000ULL  /* CONFIRMED — 64KB */
#define T8006_DOCKCHANNEL_UART_SEC_BASE 0x000000003d10c000ULL  /* CONFIRMED — 16KB */
#define T8006_DOCKCHANNEL_UART_IRQ      167                    /* 0xa7 */

/* Samsung s3c6400 compatible UART registers (used by Apple UART) */
#define UART_ULCON_OFFSET               0x00  /* Line control */
#define UART_UCON_OFFSET                0x04  /* Control */
#define UART_UFCON_OFFSET               0x08  /* FIFO control */
#define UART_UMCON_OFFSET               0x0C  /* Modem control */
#define UART_UTRSTAT_OFFSET             0x10  /* TX/RX status */
#define UART_UTXH_OFFSET                0x20  /* TX holding register (byte write) */
#define UART_URXH_OFFSET                0x24  /* RX holding register (byte read) */
#define UART_UTRSTAT_TX_EMPTY           (1 << 1)
#define UART_UTRSTAT_RX_READY           (1 << 0)

/* ============================================================
 * GPIO Controllers
 * Status: CONFIRMED from /arm-io/gpio and /arm-io/aop-gpio
 * ============================================================ */
/* AP GPIO */
#define T8006_GPIO_BASE                 0x000000002d300000ULL  /* CONFIRMED — 8KB (0x2000) */
#define T8006_GPIO_SIZE                 0x00002000ULL
#define T8006_GPIO_PINS                 139                    /* 0x8b pins */

/* AOP GPIO (Always-On Processor GPIO) */
#define T8006_AOP_GPIO_BASE             0x000000004d008000ULL  /* CONFIRMED — 16KB (0x4000) */
#define T8006_AOP_GPIO_SIZE             0x00004000ULL
#define T8006_AOP_GPIO_PINS             114                    /* 0x72 pins */

/* ============================================================
 * Display Subsystem
 * Status: CONFIRMED from /arm-io/disp0 and /arm-io/mipi-dsim
 * ============================================================ */
#define T8006_DISP0_BASE                0x0000000018000000ULL  /* CONFIRMED — 0x2f0000 (~3MB) */
#define T8006_DISP0_SIZE                0x002f0000ULL
#define T8006_MIPI_DSIM_BASE            0x0000000018400000ULL  /* CONFIRMED — 576KB */
#define T8006_MIPI_DSIM_SEC_BASE        0x0000000018490000ULL  /* CONFIRMED — 64KB */
#define T8006_DART_DISP0_BASE           0x0000000018704000ULL  /* CONFIRMED — 16KB */

/* Panel Resolution (Watch4,2 / 44mm) */
#define T8006_DISPLAY_WIDTH_44          368                    /* CONFIRMED — 44mm width */
#define T8006_DISPLAY_HEIGHT_44         448                    /* CONFIRMED — 44mm height */
#define T8006_DISPLAY_WIDTH_40          324                    /* CONFIRMED — 40mm width */
#define T8006_DISPLAY_HEIGHT_40         394                    /* CONFIRMED — 40mm height */

/* Framebuffer base: runtime value is absent from the static ADT snapshot. */
#define UNKNOWN_T8006_FRAMEBUFFER_BASE  0xDEADBEEFDEADBEEFULL  /* UNKNOWN/BLOCKED */

/* ============================================================
 * Multi-Touch & Digital Crown
 * Status: CONFIRMED architecture — BLOCKED for direct AP MMIO
 * ============================================================
 *
 * CRITICAL HARDWARE FACT:
 * Neither Touch nor Digital Crown have direct MMIO registers on the AP!
 * They are connected to the RTP (Real-Time Processor) coprocessor:
 *   - Multi-Touch controller: personality "A3T531B,1" on RTP transport
 *   - Digital Crown: optical rotary encoder on RTP transport
 * Communication happens via DockChannel-RTP IPC.
 */
#define T8006_DOCKCHANNEL_RTP_BASE      0x000000004d080000ULL  /* CONFIRMED — DockChannel to RTP */
#define T8006_DOCKCHANNEL_RTP_IRQ       76                     /* 0x4c */
#define T8006_RTP_MMIO_BASE             0x000000004d400000ULL  /* CONFIRMED — RTP coprocessor */
#define T8006_RTP_ASCWRAP_BASE          0x000000004cc00000ULL  /* CONFIRMED — ASCWrap */

/* ============================================================
 * Hardware Buttons
 * Status: CONFIRMED from /buttons
 * ============================================================
 * - Side Button: designated "help" (power/SOS), routes to SMC/PMU
 * - Digital Crown Click: designated "menu", routes to SMC/PMU
 */
#define T8006_SMC_MMIO_BASE             0x000000003e400000ULL  /* CONFIRMED — Apple SMC */

/* ============================================================
 * Power Management & Watchdog
 * Status: CONFIRMED from /arm-io/pmgr and /arm-io/wdt
 * ============================================================ */
#define T8006_PMGR_PRIMARY_BASE         0x000000002d000000ULL  /* CONFIRMED — 1.5MB */
#define T8006_PMGR_SECONDARY_BASE       0x000000003d200000ULL  /* CONFIRMED — 1MB */
#define T8006_WDT_BASE                  0x000000003d2b0000ULL  /* CONFIRMED — 16KB */
#define T8006_CLPC_BASE                 0x0000000208f44000ULL  /* CONFIRMED — 16KB */

/* ============================================================
 * USB Subsystem
 * Status: CONFIRMED from /arm-io/usb-complex
 * ============================================================ */
#define T8006_USB_COMPLEX_BASE          0x0000000030000000ULL  /* CONFIRMED */
#define T8006_USB_OTGPHY_BASE           0x0000000030000030ULL  /* CONFIRMED */
#define T8006_USB_DEVICE_BASE           0x0000000030100000ULL  /* CONFIRMED — DWC2 dev */
#define T8006_USB_EHCI_BASE             0x0000000030080000ULL  /* CONFIRMED — EHCI host */

/* ============================================================
 * I2C Controllers
 * Status: CONFIRMED from /arm-io/i2c*
 * ============================================================ */
#define T8006_I2C1_BASE                 0x000000002e014000ULL  /* CONFIRMED — Tristar (0x1a) */
#define T8006_I2C3_BASE                 0x000000002e01c000ULL  /* CONFIRMED — Audio/Hall */

/* ============================================================
 * MMIO access macros
 * ============================================================ */
#define MMIO_READ32(addr)       (*((volatile uint32_t *)(uintptr_t)(addr)))
#define MMIO_WRITE32(addr, val) (*((volatile uint32_t *)(uintptr_t)(addr)) = (val))
#define MMIO_READ64(addr)       (*((volatile uint64_t *)(uintptr_t)(addr)))
#define MMIO_WRITE64(addr, val) (*((volatile uint64_t *)(uintptr_t)(addr)) = (val))

#define MMIO_ADDR_IS_UNKNOWN(addr)  ((addr) == 0xDEADBEEFDEADBEEFULL)

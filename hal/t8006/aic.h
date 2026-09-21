/*
 * DreyzeOS — Apple Interrupt Controller (AIC) Driver Header
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Architecture: Apple AIC2 (compatible = "aic,1", aic-version = 2)
 *
 * REGISTER STATUS LEGEND:
 *   CONFIRMED — verified directly from DeviceTree and kernelcache disassembly:
 *               - Base 0x2d180000, Size 0x8000 (/arm-io/aic in DeviceTree)
 *               - Timebase 0x2d188000, Size 0x1000 (/arm-io/aic in DeviceTree)
 *               - Registers 0x0000, 0x0004, 0x0010, 0x2000, 0x2004, 0x2008, 0x200c,
 *                 0x4000, 0x4080, 0x4200 (kernelcache AppleInterruptController disasm)
 *   LIKELY    — inferred from Linux irq-apple-aic.c / m1n1 AIC implementation
 *   UNKNOWN   — not yet verified
 */

#pragma once

#include "../../include/types.h"
#include "memory_map.h"

/* ============================================================
 * AIC Hardware Registers (MMIO Offsets from T8006_AIC_BASE)
 * ============================================================ */

/* Global Control / Status */
#define AIC_REG_REVISION        0x0000  /* CONFIRMED — HW Revision / Version */
#define AIC_REG_INFO            0x0004  /* CONFIRMED — Max IRQs / capabilities */
#define AIC_REG_CONFIG          0x0010  /* CONFIRMED — Global AIC configuration */

/* Per-CPU Registers */
#define AIC_REG_WHOAMI          0x2000  /* CONFIRMED — Core index of reading CPU */
#define AIC_REG_EVENT           0x2004  /* CONFIRMED — Interrupt Ack (IACK) */
#define AIC_REG_IPI_SEND        0x2008  /* CONFIRMED — Send IPI to target CPU */
#define AIC_REG_IPI_ACK         0x200C  /* CONFIRMED — Acknowledge / clear IPI */
#define AIC_REG_IPI_MASK_CLR    0x202C  /* CONFIRMED — Clear IPI mask */

/* IRQ Mask / Status Registers (per 32-IRQ bank: bank = irq / 32) */
#define AIC_REG_MASK_SET_BASE   0x4000  /* CONFIRMED — IRQ Disable: write (1 << bit) */
#define AIC_REG_MASK_CLR_BASE   0x4080  /* CONFIRMED — IRQ Enable / EOI: write (1 << bit) */
#define AIC_REG_HW_STATE_BASE   0x4200  /* CONFIRMED — Hardware line status: read */

/* Maximum number of supported external IRQ lines */
#define AIC_MAX_IRQS            1024
#define AIC_NUM_BANKS           (AIC_MAX_IRQS / 32)

/* ============================================================
 * AIC_EVENT Bitfield Helpers (CONFIRMED from kernelcache)
 * ============================================================
 * In AppleInterruptController::handleInterrupt():
 *   IACK = readRegister(0x2004)
 *   vectorType = ubfx(IACK, 16, 3) -> (IACK >> 16) & 0x7
 *   irqNumber  = IACK & 0x3FF
 */
#define AIC_EVENT_NO_PENDING    0x00000000
#define AIC_EVENT_TYPE_HW_IRQ   0
#define AIC_EVENT_TYPE_IPI      1

#define AIC_EVENT_GET_TYPE(ev)  (((ev) >> 16) & 0x7)
#define AIC_EVENT_GET_IRQ(ev)   ((ev) & 0x3FF)

/* Bank & Bit calculation macros */
#define AIC_IRQ_BANK(irq)       ((irq) >> 5)
#define AIC_IRQ_BIT(irq)        (1U << ((irq) & 0x1F))
#define AIC_REG_MASK_SET(irq)   (AIC_REG_MASK_SET_BASE + (AIC_IRQ_BANK(irq) * 4))
#define AIC_REG_MASK_CLR(irq)   (AIC_REG_MASK_CLR_BASE + (AIC_IRQ_BANK(irq) * 4))
#define AIC_REG_HW_STATE(irq)   (AIC_REG_HW_STATE_BASE + (AIC_IRQ_BANK(irq) * 4))

/* Interrupt Handler Callback Type */
typedef void (*aic_irq_handler_t)(uint32_t irq, void *ctx);

/* ============================================================
 * AIC Public API
 * ============================================================ */

/* Initialize the AIC controller */
void aic_init(void);

/* Enable / Unmask a specific IRQ line */
void aic_enable_irq(uint32_t irq);

/* Disable / Mask a specific IRQ line */
void aic_disable_irq(uint32_t irq);

/* Mask all interrupt lines (disable all) */
void aic_mask_all(void);

/* Acknowledge pending event (reads AIC_EVENT) */
uint32_t aic_ack(void);

/* End of Interrupt (unmasks line in HW after handler finishes) */
void aic_eoi(uint32_t irq);

/* Return the CPU ID of the currently executing core */
uint32_t aic_get_cpu_id(void);

/* Register an IRQ handler callback */
int aic_register_handler(uint32_t irq, aic_irq_handler_t handler, void *ctx);

/* Unregister an IRQ handler callback */
int aic_unregister_handler(uint32_t irq);

/* Main IRQ dispatcher called from ARM64 exception entry */
void aic_handle_irq(void);

/* Print diagnostic info to klog */
void aic_diag(void);
bool aic_is_initialized(void);
uint32_t aic_mmio_access_count_for_test(void);
void aic_reset_mmio_access_count_for_test(void);

/*
 * DreyzeOS — Apple Interrupt Controller (AIC) Driver Implementation
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Architecture: Apple AIC2 (compatible = "aic,1", aic-version = 2)
 * All register offsets verified from kernelcache.release.watch4 disassembly.
 */

#include "aic.h"
#include "mmio_gate.h"
#include "../../include/log.h"

/* Structure to store registered handler info */
typedef struct {
    aic_irq_handler_t handler;
    void *ctx;
} irq_slot_t;

/* Static table of registered handlers */
static irq_slot_t g_irq_table[AIC_MAX_IRQS];
static bool g_aic_initialized = false;
static uint32_t g_aic_mmio_access_count = 0;

/* ============================================================
 * Low-Level MMIO Access Helpers
 * ============================================================ */

static inline uint32_t aic_read32(uint32_t offset)
{
    g_aic_mmio_access_count++;
    volatile uint32_t *reg = (volatile uint32_t *)(uintptr_t)(T8006_AIC_BASE + offset);
    uint32_t val = *reg;
#ifdef __aarch64__
    __asm__ volatile ("dsb sy" ::: "memory");
#endif
    return val;
}

static inline void aic_write32(uint32_t offset, uint32_t val)
{
    g_aic_mmio_access_count++;
    volatile uint32_t *reg = (volatile uint32_t *)(uintptr_t)(T8006_AIC_BASE + offset);
    *reg = val;
#ifdef __aarch64__
    __asm__ volatile ("dsb sy" ::: "memory");
#endif
}

/* ============================================================
 * Public AIC Operations
 * ============================================================ */

uint32_t aic_get_cpu_id(void)
{
    if (!mmio_mapping_is_verified()) return 0;
    return aic_read32(AIC_REG_WHOAMI);
}

void aic_mask_all(void)
{
    if (!mmio_mapping_is_verified()) return;
    /* Mask (disable) all 1024 IRQ lines across all 32 banks */
    for (uint32_t bank = 0; bank < AIC_NUM_BANKS; bank++) {
        aic_write32(AIC_REG_MASK_SET_BASE + (bank * 4), 0xFFFFFFFFU);
    }
}

void aic_enable_irq(uint32_t irq)
{
    if (!mmio_mapping_is_verified()) return;
    if (irq >= AIC_MAX_IRQS) {
        klog_warn("  [AIC] Attempted to enable out-of-range IRQ");
        return;
    }
    /* Writing 1 to MASK_CLR unmasks/enables the interrupt line */
    aic_write32(AIC_REG_MASK_CLR(irq), AIC_IRQ_BIT(irq));
}

void aic_disable_irq(uint32_t irq)
{
    if (!mmio_mapping_is_verified()) return;
    if (irq >= AIC_MAX_IRQS) {
        klog_warn("  [AIC] Attempted to disable out-of-range IRQ");
        return;
    }
    /* Writing 1 to MASK_SET masks/disables the interrupt line */
    aic_write32(AIC_REG_MASK_SET(irq), AIC_IRQ_BIT(irq));
}

uint32_t aic_ack(void)
{
    if (!mmio_mapping_is_verified()) return AIC_EVENT_NO_PENDING;
    return aic_read32(AIC_REG_EVENT);
}

void aic_eoi(uint32_t irq)
{
    if (!mmio_mapping_is_verified()) return;
    if (irq >= AIC_MAX_IRQS) {
        return;
    }
    /*
     * On Apple AIC, the interrupt line is auto-masked on event delivery.
     * End of Interrupt (EOI) unmasks the line by writing to MASK_CLR.
     */
    aic_write32(AIC_REG_MASK_CLR(irq), AIC_IRQ_BIT(irq));
}

int aic_register_handler(uint32_t irq, aic_irq_handler_t handler, void *ctx)
{
    if (irq >= AIC_MAX_IRQS || handler == NULL) {
        return -1;
    }
    g_irq_table[irq].handler = handler;
    g_irq_table[irq].ctx = ctx;
    return 0;
}

int aic_unregister_handler(uint32_t irq)
{
    if (irq >= AIC_MAX_IRQS) {
        return -1;
    }
    aic_disable_irq(irq);
    g_irq_table[irq].handler = NULL;
    g_irq_table[irq].ctx = NULL;
    return 0;
}

void aic_init(void)
{
    if (!mmio_mapping_is_verified()) {
        g_aic_initialized = false;
        klog_info("  [AIC] MMIO mapping unverified: controller left untouched");
        return;
    }
    klog_info("  [AIC] Initializing Apple Interrupt Controller (AIC2)...");

    /* Clear handler table */
    for (uint32_t i = 0; i < AIC_MAX_IRQS; i++) {
        g_irq_table[i].handler = NULL;
        g_irq_table[i].ctx = NULL;
    }

    /* Mask all external IRQs at startup for safety */
    aic_mask_all();

    /* Global config: ensure controller is enabled */
    aic_write32(AIC_REG_CONFIG, 1);

    g_aic_initialized = true;
    klog_info("  [AIC] Initialization complete — all IRQs masked");
}

void aic_diag(void)
{
    if (!mmio_mapping_is_verified()) {
        klog_info("  [AIC] MMIO mapping unverified: diagnostics skipped");
        return;
    }
    klog_info("  [AIC] Hardware Diagnostics:");
    klog_hex("  [AIC] Base Address     ", T8006_AIC_BASE);
    klog_hex("  [AIC] Size             ", T8006_AIC_SIZE);
    klog_hex("  [AIC] Timebase Base    ", T8006_AIC_TIMEBASE_BASE);

    uint32_t rev = aic_read32(AIC_REG_REVISION);
    uint32_t info = aic_read32(AIC_REG_INFO);
    uint32_t cpu = aic_read32(AIC_REG_WHOAMI);

    klog_hex("  [AIC] Revision (0x0000)", rev);
    klog_hex("  [AIC] Info     (0x0004)", info);
    klog_hex("  [AIC] WHOAMI   (0x2000)", cpu);
    klog_info("  [AIC] Status: Ready");
}

bool aic_is_initialized(void)
{
    return g_aic_initialized;
}

uint32_t aic_mmio_access_count_for_test(void)
{
    return g_aic_mmio_access_count;
}

void aic_reset_mmio_access_count_for_test(void)
{
    g_aic_mmio_access_count = 0;
}

/*
 * aic_handle_irq — called from ARM64 exception entry point (_exc_irq_spx)
 */
void aic_handle_irq(void)
{
    if (!g_aic_initialized) {
        return;
    }

    /* Loop reading AIC_EVENT until no more interrupts are pending */
    for (;;) {
        uint32_t event = aic_ack();
        if (event == AIC_EVENT_NO_PENDING) {
            break;
        }

        uint32_t type = AIC_EVENT_GET_TYPE(event);
        uint32_t irq  = AIC_EVENT_GET_IRQ(event);

        if (type == AIC_EVENT_TYPE_HW_IRQ) {
            if (irq < AIC_MAX_IRQS && g_irq_table[irq].handler != NULL) {
                g_irq_table[irq].handler(irq, g_irq_table[irq].ctx);
            }
            /* End of interrupt: unmask hardware line */
            aic_eoi(irq);
        } else if (type == AIC_EVENT_TYPE_IPI) {
            /* Acknowledge and clear per-CPU IPI */
            aic_write32(AIC_REG_IPI_ACK, 1);
        } else {
            /* Other/unknown event types: safely acknowledge */
            aic_eoi(irq);
        }
    }
}

/*
 * DreyzeOS — T8006 UART0 Driver Implementation
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Hardware Information:
 *   Controller: Samsung S3C6400 derivative (compatible: "uart-1,samsung")
 *   Physical MMIO Base: 0x2e500000 (CONFIRMED from DeviceTree /arm-io/uart0)
 *   MMIO Size: 0x4000 (16 KB)
 *   Interrupt ID: 262 (0x106)
 *   DeviceTree Property: boot-console
 *
 * Architecture Notes:
 *   - The bootloader (iBoot) sets up UART0 as the primary boot-console.
 *   - Baud rate (typically 115200) and clock gates (gate 0x17) are already
 *     initialized by iBoot prior to kernel handover.
 *   - The driver safely polls status registers with timeout protection
 *     to prevent hangs if executed in environments without clock/power.
 */

#include "uart.h"
#include "memory_map.h"
#include "mmio_gate.h"
#include "../../include/log.h"

#define UART_TX_TIMEOUT_CYCLES  1000000U

/* Additional Samsung UART status bits */
#ifndef UART_UTRSTAT_TX_EMPTY_SHIFTER
#define UART_UTRSTAT_TX_EMPTY_SHIFTER   (1U << 2)  /* Both FIFO and shift register empty */
#endif

#ifndef UART_UTRSTAT_TX_EMPTY_BUFFER
#define UART_UTRSTAT_TX_EMPTY_BUFFER    (1U << 1)  /* Transmit buffer/FIFO has room */
#endif

#ifndef UART_UTRSTAT_RX_READY
#define UART_UTRSTAT_RX_READY           (1U << 0)  /* Receive buffer has data */
#endif

static bool g_uart_ready = false;
static uint32_t g_uart_mmio_access_count = 0;

static uint32_t uart_mmio_read32(uint64_t address)
{
    g_uart_mmio_access_count++;
    return MMIO_READ32(address);
}

static void uart_mmio_write32(uint64_t address, uint32_t value)
{
    g_uart_mmio_access_count++;
    MMIO_WRITE32(address, value);
}

/*
 * uart_init — Initialize UART0.
 * Verifies registers and marks driver ready.
 */
void uart_init(void)
{
    /* Verify MMIO address is configured and not placeholder */
    if (!mmio_mapping_is_verified() ||
        MMIO_ADDR_IS_UNKNOWN(T8006_UART0_BASE) || T8006_UART0_BASE == 0) {
        g_uart_ready = false;
        return;
    }

    /*
     * We preserve iBoot's line control (ULCON) and baud divisors (UBRDIV/UFRACVAL).
     * We enable TX and RX modes in UCON (bits [3:0] = 0x5: Rx interrupt/polling, Tx interrupt/polling)
     * if not already enabled.
     */
    uint32_t ucon = uart_mmio_read32(T8006_UART0_BASE + UART_UCON_OFFSET);
    if ((ucon & 0x0F) == 0) {
        uart_mmio_write32(T8006_UART0_BASE + UART_UCON_OFFSET, ucon | 0x05);
    }

    g_uart_ready = true;

    /* Output initial newline sequence to flush any line noise */
    uart_putc('\r');
    uart_putc('\n');
}

/*
 * uart_is_ready — Check if UART0 driver is initialized.
 */
bool uart_is_ready(void)
{
    return g_uart_ready;
}

uint32_t uart_mmio_access_count_for_test(void)
{
    return g_uart_mmio_access_count;
}

void uart_reset_mmio_access_count_for_test(void)
{
    g_uart_mmio_access_count = 0;
}

/*
 * uart_putc — Transmit single character over UART0 with timeout protection.
 * Automatically translates '\n' to '\r\n'.
 */
void uart_putc(char c)
{
    if (!g_uart_ready || !mmio_mapping_is_verified()) {
        return;
    }

    /* Standard terminal newline translation */
    if (c == '\n') {
        uart_putc('\r');
    }

    /* Wait until TX buffer/FIFO is empty (or has space) with timeout */
    uint32_t timeout = UART_TX_TIMEOUT_CYCLES;
    while ((uart_mmio_read32(T8006_UART0_BASE + UART_UTRSTAT_OFFSET) & UART_UTRSTAT_TX_EMPTY_BUFFER) == 0) {
        if (--timeout == 0) {
            /* Hardware not responding (possibly clock-gated or halted) */
            return;
        }
    }

    /* Write byte to transmit holding register */
    uart_mmio_write32(T8006_UART0_BASE + UART_UTXH_OFFSET, (uint32_t)(uint8_t)c);
}

/*
 * uart_puts — Transmit null-terminated string over UART0.
 */
void uart_puts(const char *str)
{
    if (!str || !g_uart_ready) {
        return;
    }

    while (*str) {
        uart_putc(*str++);
    }
}

/*
 * uart_getc_nonblocking — Non-blocking read of single character from UART0.
 */
bool uart_getc_nonblocking(char *out_c)
{
    if (!g_uart_ready || !mmio_mapping_is_verified() || !out_c) {
        return false;
    }

    uint32_t stat = uart_mmio_read32(T8006_UART0_BASE + UART_UTRSTAT_OFFSET);
    if (stat & UART_UTRSTAT_RX_READY) {
        uint32_t val = uart_mmio_read32(T8006_UART0_BASE + UART_URXH_OFFSET);
        *out_c = (char)(val & 0xFF);
        return true;
    }

    return false;
}

/*
 * Helper: format 32-bit hex to buffer
 */
static void hex32_to_str(uint32_t val, char *buf)
{
    const char hex_chars[] = "0123456789abcdef";
    buf[0] = '0';
    buf[1] = 'x';
    for (int i = 7; i >= 0; i--) {
        buf[2 + (7 - i)] = hex_chars[(val >> (i * 4)) & 0xF];
    }
    buf[10] = '\0';
}

/*
 * uart_diag — Print diagnostic register status.
 */
void uart_diag(void)
{
    if (!g_uart_ready || !mmio_mapping_is_verified()) {
        klog_warn("[UART0] uart_diag: UART0 not initialized");
        return;
    }

    uint32_t ulcon   = uart_mmio_read32(T8006_UART0_BASE + UART_ULCON_OFFSET);
    uint32_t ucon    = uart_mmio_read32(T8006_UART0_BASE + UART_UCON_OFFSET);
    uint32_t ufcon   = uart_mmio_read32(T8006_UART0_BASE + UART_UFCON_OFFSET);
    uint32_t utrstat = uart_mmio_read32(T8006_UART0_BASE + UART_UTRSTAT_OFFSET);

    char hex_buf[16];

    uart_puts("\r\n--- [DreyzeOS T8006 UART0 Diagnostics] ---\r\n");
    uart_puts("  Base Address: 0x2e500000 [CONFIRMED]\r\n");

    uart_puts("  ULCON:   ");
    hex32_to_str(ulcon, hex_buf);
    uart_puts(hex_buf);
    uart_puts("\r\n");

    uart_puts("  UCON:    ");
    hex32_to_str(ucon, hex_buf);
    uart_puts(hex_buf);
    uart_puts("\r\n");

    uart_puts("  UFCON:   ");
    hex32_to_str(ufcon, hex_buf);
    uart_puts(hex_buf);
    uart_puts("\r\n");

    uart_puts("  UTRSTAT: ");
    hex32_to_str(utrstat, hex_buf);
    uart_puts(hex_buf);
    uart_puts("\r\n");

    uart_puts("--- [End UART0 Diagnostics] ---\r\n\r\n");

    klog_info("[UART0] Diagnostics printed to serial console");
    klog_hex("[UART0] Base", T8006_UART0_BASE);
    klog_hex("[UART0] UTRSTAT", utrstat);
    klog_hex("[UART0] ULCON", ulcon);
}

/*
 * DreyzeOS — Kernel Logging Subsystem
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Phase 1: RAM buffer log only.
 *   - No UART output (UART_BASE is UNKNOWN for T8006)
 *   - Log entries stored in ring buffer in RAM
 *   - Buffer is readable via JTAG / memory dump
 *
 * Phase 6+: Will add real UART output once UART_BASE is confirmed.
 */

#include "../include/types.h"
#include "../include/log.h"
#include "../lib/string.h"
#include "../hal/t8006/uart.h"
#include "../hal/t8006/mmio_gate.h"

/* ============================================================
 * RAM ring buffer log
 * ============================================================
 *
 * This buffer persists in RAM during execution.
 * A JTAG debugger or memory dump tool can read it at offset:
 *   &klog_buffer  (symbol visible in ELF)
 *
 * Magic header allows easy identification in raw memory dumps.
 */

#define KLOG_BUFFER_SIZE    (16 * 1024)  /* 16 KiB ring buffer */
#define KLOG_MAGIC          0x4C474F44   /* "DLOG" in little-endian */
#define KLOG_MAX_ENTRY_LEN  256

typedef struct {
    uint32_t magic;             /* KLOG_MAGIC — identifies buffer in dumps */
    uint32_t entry_count;       /* Total log entries written */
    uint32_t write_offset;      /* Current write position in data[] */
    uint32_t wrap_count;        /* Number of times buffer wrapped */
    uint32_t flags;             /* Reserved */
    uint32_t reserved[3];
    char     data[KLOG_BUFFER_SIZE]; /* Log data — newline-terminated entries */
} klog_buffer_t;

/* Place log buffer in BSS (zero-initialized) with a clear name for dumps */
static klog_buffer_t klog_buffer __attribute__((section(".klog_buffer")));

static bool g_ram_log_ready = false;

/* ============================================================
 * Internal helpers
 * ============================================================ */

static void klog_write_char(char c)
{
    /* Write to RAM buffer */
    klog_buffer.data[klog_buffer.write_offset] = c;
    klog_buffer.write_offset++;

    if (klog_buffer.write_offset >= KLOG_BUFFER_SIZE) {
        klog_buffer.write_offset = 0;
        klog_buffer.wrap_count++;
    }

    /* If UART is available, also output to serial console */
    if (uart_is_ready()) {
        uart_putc(c);
    }
}

static void klog_write_str(const char *s)
{
    if (!s) {
        klog_write_str("(null)");
        return;
    }
    while (*s) {
        klog_write_char(*s++);
    }
}

static void klog_write_newline(void)
{
    klog_write_char('\r');
    klog_write_char('\n');
}

/* Convert uint64_t to hex string — freestanding, no printf */
static void klog_write_hex64(uint64_t val)
{
    static const char hex_chars[] = "0123456789abcdef";
    char buf[18];  /* "0x" + 16 hex digits */
    int i;

    buf[0] = '0';
    buf[1] = 'x';
    for (i = 0; i < 16; i++) {
        buf[17 - i] = hex_chars[val & 0xF];
        val >>= 4;
    }
    /* buf[2..17] = 16 hex digits */
    for (i = 0; i < 18; i++) {
        klog_write_char(buf[i]);
    }
}

/* ============================================================
 * Public API
 * ============================================================ */

void log_init(void)
{
    /* Initialize magic header */
    klog_buffer.magic = KLOG_MAGIC;
    klog_buffer.entry_count = 0;
    klog_buffer.write_offset = 0;
    klog_buffer.wrap_count = 0;
    klog_buffer.flags = 0;

    /* Mark start of log */
    klog_write_str("[DLOG] DreyzeOS kernel log initialized\r\n");
    g_ram_log_ready = true;
}

bool log_is_ram_ready(void)
{
    return g_ram_log_ready;
}

bool log_is_uart_ready(void)
{
    return uart_is_ready();
}

void log_try_enable_uart(void)
{
    if (mmio_mapping_is_verified()) {
        uart_init();
    }
}

void log_flush(void)
{
    /* With RAM buffer: nothing to flush.
     * With UART: would flush TX FIFO.
     * Stub for now.
     */
#ifdef __aarch64__
    __asm__ volatile ("dsb sy" ::: "memory");
#else
    __asm__ volatile ("" ::: "memory");
#endif
}

void klog_info(const char *msg)
{
    klog_buffer.entry_count++;
    klog_write_str("[I] ");
    klog_write_str(msg);
    klog_write_newline();
}

void klog_warn(const char *msg)
{
    klog_buffer.entry_count++;
    klog_write_str("[W] ");
    klog_write_str(msg);
    klog_write_newline();
}

void klog_error(const char *msg)
{
    klog_buffer.entry_count++;
    klog_write_str("[E] ");
    klog_write_str(msg);
    klog_write_newline();
}

void klog_hex(const char *label, uint64_t val)
{
    klog_buffer.entry_count++;
    klog_write_str("[I] ");
    klog_write_str(label);
    klog_write_str(": ");
    klog_write_hex64(val);
    klog_write_newline();
}

/*
 * klog_get_buffer — return pointer to log data for external inspection.
 * Useful for a debugger or memory dump tool.
 */
const char *klog_get_buffer(uint32_t *out_size, uint32_t *out_count)
{
    if (out_size)  *out_size  = klog_buffer.write_offset;
    if (out_count) *out_count = klog_buffer.entry_count;
    return klog_buffer.data;
}

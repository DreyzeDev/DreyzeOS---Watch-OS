/*
 * DreyzeOS — T8006 UART0 Driver
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Hardware Information:
 *   Base Address: 0x2e500000 (CONFIRMED from DeviceTree /arm-io/uart0)
 *   Size:         0x4000 (16 KB)
 *   Compatible:   uart-1,samsung (Samsung S3C6400 derivative)
 *   Interrupt:    262 (0x106)
 *   DT Property:  boot-console
 */

#pragma once

#include "../../include/types.h"

/*
 * Initialize UART0 hardware interface.
 * Preserves baud rate configured by bootloader/iBoot.
 */
void uart_init(void);

/*
 * Transmit a single character over UART0.
 * Automatically translates '\n' to '\r\n'.
 */
void uart_putc(char c);

/*
 * Transmit a null-terminated string over UART0.
 */
void uart_puts(const char *str);

/*
 * Read a single character from UART0 without blocking.
 * Returns true if character read, false if receive buffer empty.
 */
bool uart_getc_nonblocking(char *out_c);

/*
 * Print UART0 register diagnostics over console and klog.
 */
void uart_diag(void);

/*
 * Check if UART0 driver is initialized.
 */
bool uart_is_ready(void);
#ifdef HOST_TEST
uint32_t uart_mmio_access_count_for_test(void);
void uart_reset_mmio_access_count_for_test(void);
#endif

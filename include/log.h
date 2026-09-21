/*
 * DreyzeOS — Logging API
 * Freestanding — no libc.
 */

#pragma once

#include "types.h"

void log_init(void);
void log_flush(void);
bool log_is_ram_ready(void);
bool log_is_uart_ready(void);
void log_try_enable_uart(void);

void klog_info(const char *msg);
void klog_warn(const char *msg);
void klog_error(const char *msg);
void klog_hex(const char *label, uint64_t val);

const char *klog_get_buffer(uint32_t *out_size, uint32_t *out_count);

/*
 * DreyzeOS — Panic API
 * Freestanding — no libc.
 */

#pragma once

#include "types.h"

__noreturn void panic(const char *msg);
__noreturn void panic_assert(const char *expr, const char *file, int line);

#define ASSERT(expr) \
    do { \
        if (!(expr)) { \
            panic_assert(#expr, __FILE__, __LINE__); \
        } \
    } while (0)

/* Called from exception vectors in entry.S */
void _exception_handler(void);

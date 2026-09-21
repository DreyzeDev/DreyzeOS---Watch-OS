/*
 * DreyzeOS — Fundamental types
 * Freestanding — no libc dependency.
 */

#pragma once

#if defined(HOST_TEST) || (defined(__STDC_HOSTED__) && __STDC_HOSTED__ == 1 && !defined(BAREMETAL))
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <sys/types.h>
#else
/* Standard integer types — manually defined, no <stdint.h> from libc */
typedef unsigned char       uint8_t;
typedef unsigned short      uint16_t;
typedef unsigned int        uint32_t;
typedef unsigned long long  uint64_t;

typedef signed char         int8_t;
typedef signed short        int16_t;
typedef signed int          int32_t;
typedef signed long long    int64_t;

/* Pointer-sized types */
typedef uint64_t            uintptr_t;
typedef int64_t             intptr_t;
typedef uint64_t            size_t;
typedef int64_t             ssize_t;
typedef uint64_t            uintmax_t;
typedef int64_t             intmax_t;
#endif

/* Boolean — compatible with C11, C17, and C23 (where bool is a keyword) */
#if !defined(__bool_true_false_are_defined) && __STDC_VERSION__ < 202311L
typedef _Bool               bool;
#define true                1
#define false               0
#define __bool_true_false_are_defined 1
#endif

/* NULL */
#ifndef NULL
#define NULL                ((void *)0)
#endif

/* Useful macros */
#define ARRAY_SIZE(x)       (sizeof(x) / sizeof((x)[0]))
#define ALIGN_UP(val, align)   (((val) + (align) - 1) & ~((align) - 1))
#define ALIGN_DOWN(val, align) ((val) & ~((align) - 1))
#define BIT(n)              (1ULL << (n))
#define BITS(hi, lo)        (((1ULL << ((hi) - (lo) + 1)) - 1) << (lo))
#define MIN(a, b)           ((a) < (b) ? (a) : (b))
#define MAX(a, b)           ((a) > (b) ? (a) : (b))

/* Compiler attributes */
#define __noreturn          __attribute__((noreturn))
#define __packed            __attribute__((packed))
#define __aligned(n)        __attribute__((aligned(n)))
#define __section(s)        __attribute__((section(s)))
#define __unused            __attribute__((unused))
#define __used              __attribute__((used))
#define __weak              __attribute__((weak))
#define __barrier()         __asm__ volatile ("" ::: "memory")

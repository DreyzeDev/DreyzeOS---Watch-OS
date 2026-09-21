/*
 * DreyzeOS — Freestanding String Library
 * No libc dependency. Written for bare-metal AArch64.
 */

#include "string.h"

void *memcpy(void *dst, const void *src, size_t n)
{
    uint8_t *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;

    /* Fast path: 8-byte aligned copy */
    if (((uintptr_t)d & 7) == 0 && ((uintptr_t)s & 7) == 0) {
        size_t words = n / 8;
        size_t rem   = n % 8;
        uint64_t *dw = (uint64_t *)d;
        const uint64_t *sw = (const uint64_t *)s;
        while (words--) *dw++ = *sw++;
        d = (uint8_t *)dw;
        s = (const uint8_t *)sw;
        n = rem;
    }

    while (n--) *d++ = *s++;
    return dst;
}

void *memset(void *dst, int c, size_t n)
{
    uint8_t *d = (uint8_t *)dst;
    uint8_t  val = (uint8_t)c;

    /* Fast path: fill 8 bytes at a time when aligned */
    if (((uintptr_t)d & 7) == 0) {
        uint64_t fill = (uint64_t)val;
        fill |= (fill << 8);
        fill |= (fill << 16);
        fill |= (fill << 32);
        uint64_t *dw = (uint64_t *)d;
        size_t words = n / 8;
        size_t rem   = n % 8;
        while (words--) *dw++ = fill;
        d = (uint8_t *)dw;
        n = rem;
    }

    while (n--) *d++ = val;
    return dst;
}

int memcmp(const void *a, const void *b, size_t n)
{
    const uint8_t *pa = (const uint8_t *)a;
    const uint8_t *pb = (const uint8_t *)b;
    while (n--) {
        if (*pa != *pb) return (int)*pa - (int)*pb;
        pa++; pb++;
    }
    return 0;
}

void *memmove(void *dst, const void *src, size_t n)
{
    uint8_t *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;

    if (d == s || n == 0) return dst;

    if (d < s || d >= s + n) {
        /* No overlap or dst before src — forward copy */
        return memcpy(dst, src, n);
    } else {
        /* Overlap — backward copy */
        d += n;
        s += n;
        while (n--) *--d = *--s;
    }
    return dst;
}

size_t strlen(const char *s)
{
    const char *p = s;
    while (*p) p++;
    return (size_t)(p - s);
}

char *strcpy(char *dst, const char *src)
{
    char *d = dst;
    while ((*d++ = *src++) != '\0');
    return dst;
}

char *strncpy(char *dst, const char *src, size_t n)
{
    char *d = dst;
    while (n > 0 && *src) {
        *d++ = *src++;
        n--;
    }
    while (n-- > 0) *d++ = '\0';
    return dst;
}

int strcmp(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return (int)(unsigned char)*a - (int)(unsigned char)*b;
}

int strncmp(const char *a, const char *b, size_t n)
{
    while (n-- > 0) {
        if (*a != *b) return (int)(unsigned char)*a - (int)(unsigned char)*b;
        if (*a == '\0') return 0;
        a++; b++;
    }
    return 0;
}

char *strcat(char *dst, const char *src)
{
    char *d = dst;
    while (*d) d++;
    while ((*d++ = *src++) != '\0');
    return dst;
}

const char *strchr(const char *s, int c)
{
    while (*s) {
        if (*s == (char)c) return s;
        s++;
    }
    return (c == '\0') ? s : NULL;
}

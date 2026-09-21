/*
 * DreyzeOS — Kernel Panic
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 */

#include "../include/types.h"
#include "../include/log.h"
#include "../include/panic.h"

/*
 * Log buffer for panic messages — we store last panic reason here.
 * This can be read via JTAG / memory dump post-crash.
 */
#define PANIC_BUFFER_SIZE 256

static char panic_buffer[PANIC_BUFFER_SIZE];
static uint32_t panic_count = 0;

/* Sentinel value to detect panic buffer in memory dumps */
static const uint32_t PANIC_MAGIC = 0xDEAD0505;  /* "DREYZ" marker */
static uint32_t panic_magic_check = 0;

/*
 * panic — unrecoverable kernel error.
 *
 * Writes the panic message to the log buffer (readable via debugger/dump),
 * then halts the CPU safely with WFI.
 *
 * This function must never return.
 */
__attribute__((noreturn))
void panic(const char *msg)
{
    /* Mark panic in magic field — detectable in memory dumps */
    panic_magic_check = PANIC_MAGIC;
    panic_count++;

    /* Disable all interrupts */
    __asm__ volatile ("msr daifset, #0xf" ::: "memory");

    /* Log the panic */
    klog_info("========================================");
    klog_info("!!! KERNEL PANIC !!!");
    if (msg) {
        klog_info(msg);
    } else {
        klog_info("(null panic message)");
    }
    klog_info("DreyzeOS is halting. Reboot to recover.");
    klog_info("========================================");

    /* Copy message to panic buffer for memory dump analysis */
    if (msg) {
        size_t i = 0;
        while (msg[i] && i < PANIC_BUFFER_SIZE - 1) {
            panic_buffer[i] = msg[i];
            i++;
        }
        panic_buffer[i] = '\0';
    }

    /* Attempt to flush any pending log output */
    log_flush();

    /* Safe infinite halt — WFI reduces power, device can be reset */
    for (;;) {
        __asm__ volatile ("wfi" ::: "memory");
    }
}

/*
 * panic_assert — called when an assertion fails.
 */
__attribute__((noreturn))
void panic_assert(const char *expr, const char *file, int line)
{
    klog_info("ASSERTION FAILED:");
    klog_info(expr);
    /* We cannot use printf here — no libc. Just halt. */
    (void)file;
    (void)line;
    panic("assertion failed");
}

/*
 * _exception_handler — called from exception vectors in entry.S.
 * Reads ESR_EL1 (Exception Syndrome Register) for diagnostics.
 */
void _exception_handler(void)
{
    uint64_t esr = 0;
    uint64_t elr = 0;
    uint64_t far = 0;
    uint64_t spsr = 0;

    __asm__ volatile (
        "mrs %0, esr_el1\n"
        "mrs %1, elr_el1\n"
        "mrs %2, far_el1\n"
        "mrs %3, spsr_el1\n"
        : "=r"(esr), "=r"(elr), "=r"(far), "=r"(spsr)
    );

    klog_info("EXCEPTION CAUGHT:");
    klog_hex("  ESR_EL1  (syndrome)", esr);
    klog_hex("  ELR_EL1  (link reg)", elr);
    klog_hex("  FAR_EL1  (fault addr)", far);
    klog_hex("  SPSR_EL1 (saved psr)", spsr);

    panic("unhandled exception");
}

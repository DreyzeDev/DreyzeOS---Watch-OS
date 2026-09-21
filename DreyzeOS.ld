/*
 * DreyzeOS Linker Script
 * Target: Apple Watch Series 4 / Apple S4 (T8006) — AArch64
 *
 * ============================================================
 * CRITICAL NOTES ON ADDRESSES & HARDWARE BLOCKER:
 * ============================================================
 *
 * The load address 0x100000000 is a PLACEHOLDER.
 * Real T8006 load address: UNKNOWN_T8006_LOAD_ADDRESS.
 *
 * HARDWARE BLOCKER:
 * This image CANNOT be executed on real hardware until the true
 * RAM delivery load address, entry MMU mapping, and relocation
 * requirements are confirmed by evidence.
 *
 * Safety & Layout Guarantees:
 *   - .text.boot is strictly first at DREYZEOS_LOAD_BASE.
 *   - Exception vectors are 2048-byte aligned per ARMv8-A architecture.
 *   - .stack is strictly placed AFTER and OUTSIDE the .bss section
 *     to ensure that BSS zeroing never overwrites the active stack!
 *   - Stack is 16-byte aligned per AArch64 AAPCS-64 standard.
 *   - Program headers (PHDRS) are explicitly partitioned (R_E, R__, RW_)
 *     preventing RWX segment warnings.
 */

OUTPUT_FORMAT("elf64-littleaarch64")
OUTPUT_ARCH(aarch64)

/*
 * UNKNOWN_T8006_LOAD_ADDRESS placeholder.
 * Replace with real address only when confirmed.
 */
DREYZEOS_LOAD_BASE = 0x0000000100000000;

ENTRY(_start)

/*
 * Explicit ELF Program Headers:
 * Partition into distinct permission segments to avoid RWX warnings
 * and prepare for proper MMU page table attributes.
 */
PHDRS
{
    text   PT_LOAD FLAGS(5);  /* Read + Execute (1 | 4) */
    rodata PT_LOAD FLAGS(4);  /* Read-Only (4) */
    data   PT_LOAD FLAGS(6);  /* Read + Write (2 | 4) */
}

SECTIONS
{
    . = DREYZEOS_LOAD_BASE;

    /*
     * Export kernel start for memory accounting.
     */
    __kernel_start = .;

    /*
     * .text.boot — Must be FIRST in the binary.
     * Contains _start entry point and 2048-byte aligned exception vectors.
     */
    .text.boot : {
        KEEP(*(.text.boot))
    } :text

    /*
     * .text — Main executable code.
     */
    .text : {
        *(.text)
        *(.text.*)
    } :text

    /*
     * Align to page boundary (4KB) before read-only data.
     */
    . = ALIGN(4096);

    /*
     * .rodata — Read-only data (strings, constants).
     */
    .rodata : {
        *(.rodata)
        *(.rodata.*)
    } :rodata

    /*
     * Align to page boundary (4KB) before writable data.
     */
    . = ALIGN(4096);

    /*
     * .data — Initialized read-write data.
     */
    .data : {
        *(.data)
        *(.data.*)
    } :data

    /*
     * Kernel log buffer — placed in named section for dump identification.
     */
    .klog_buffer : {
        *(.klog_buffer)
    } :data

    . = ALIGN(8);

    /*
     * __bss_start and __bss_end — used by entry.S BSS clear loop.
     * CRITICAL: .stack is NOT inside this range!
     */
    __bss_start = .;
    .bss : {
        *(.bss)
        *(.bss.*)
        *(COMMON)
    } :data
    . = ALIGN(8);
    __bss_end = .;

    /*
     * Stack section: 16 KiB, 16-byte aligned.
     * Stack grows DOWN from __stack_top to __stack_bottom.
     * Placed strictly AFTER __bss_end to guarantee BSS clear loop
     * never touches active stack frames!
     */
    . = ALIGN(16);
    .stack : {
        __stack_bottom = .;
        *(.stack)
        . = ALIGN(16);
        __stack_top = .;
    } :data

    . = ALIGN(16);
    __kernel_end = .;

    /*
     * Discard unwanted metadata from binary.
     */
    /DISCARD/ : {
        *(.comment)
        *(.note*)
        *(.ARM.exidx*)
        *(.ARM.extab*)
        *(.gnu.*)
        *(.eh_frame*)
    }
}

/*
 * Linker assertions — verify hardware and safety invariants.
 */

/* Entry point must be placed at the very first byte of load base */
ASSERT(_start == DREYZEOS_LOAD_BASE,
       "ERROR: _start entry point must match DREYZEOS_LOAD_BASE")

/* Exception vector table must be 2048-byte aligned (ARMv8 requirement) */
ASSERT((_exception_vectors_base & 0x7FF) == 0,
       "ERROR: _exception_vectors_base must be 2048-byte aligned")

/* Stack top must be 16-byte aligned (AAPCS64 requirement) */
ASSERT((__stack_top & 0xF) == 0,
       "ERROR: __stack_top must be 16-byte aligned")

/* Stack must be strictly outside and after BSS region */
ASSERT(__stack_bottom >= __bss_end,
       "ERROR: .stack must be placed strictly after __bss_end")

/* Binary must not exceed 64MB */
ASSERT((__kernel_end - __kernel_start) < 0x4000000,
       "ERROR: Kernel image exceeds 64MB")

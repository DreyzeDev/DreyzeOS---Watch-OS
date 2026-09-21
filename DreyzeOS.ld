/*
 * DreyzeOS Linker Script
 * Target: Apple Watch Series 4 / Apple S4 (T8006) — AArch64
 *
 * ============================================================
 * CRITICAL NOTES ON ADDRESSES:
 * ============================================================
 *
 * The load address 0x100000000 is a PLACEHOLDER.
 * Real T8006 load address: UNKNOWN_T8006_LOAD_ADDRESS
 *
 * This placeholder is chosen to:
 *   1. Be a valid AArch64 address (not 32-bit truncated)
 *   2. Be obviously wrong (4GB boundary — unusual, detectable)
 *   3. Allow us to build and inspect the binary before we know real addresses
 *
 * When T8006 DRAM base and kernel load offset are confirmed (Phase 3/4),
 * update LOAD_ADDRESS to the real value.
 *
 * Similar Apple SoC convention (NOT confirmed for T8006):
 *   A10 (T8010): DRAM at 0x800000000, kernel loads at +some_offset
 *   A11 (T8015): DRAM at 0x800000000
 *   S4  (T8006): DRAM base = UNKNOWN
 *
 * For PongoOS reference: Pongo.bin loads at checkm8's payload deposit point.
 */

OUTPUT_FORMAT("elf64-littleaarch64")
OUTPUT_ARCH(aarch64)

/*
 * UNKNOWN_T8006_LOAD_ADDRESS placeholder.
 * Replace with real address when confirmed.
 * Using 0x100000000 (4GB) as placeholder — obviously non-default.
 */
DREYZEOS_LOAD_BASE = 0x0000000100000000;

ENTRY(_start)

SECTIONS
{
    /*
     * Kernel load base.
     * .  = current location counter
     * All sections placed relative to DREYZEOS_LOAD_BASE.
     */
    . = DREYZEOS_LOAD_BASE;

    /*
     * Export kernel start for use in kernel_main memory logging.
     */
    __kernel_start = .;

    /*
     * .text.boot — Must be FIRST in the binary.
     * Contains _start entry point (from boot/entry.S).
     * The boot ROM / iBoot / PongoOS jumps to the very first byte of our image.
     */
    .text.boot : {
        KEEP(*(.text.boot))
    }

    /*
     * .text — Main code section.
     * All compiled C and assembly code.
     */
    .text : {
        *(.text)
        *(.text.*)
    }

    /*
     * Align to 8 bytes before read-only data.
     */
    . = ALIGN(8);

    /*
     * .rodata — Read-only data (string literals, const arrays, etc.)
     */
    .rodata : {
        *(.rodata)
        *(.rodata.*)
    }

    . = ALIGN(8);

    /*
     * .data — Initialized read-write data (initialized globals).
     */
    .data : {
        *(.data)
        *(.data.*)
    }

    . = ALIGN(8);

    /*
     * NOTE: Exception vector table is defined in boot/entry.S
     * within the .text.boot section, 2KB-aligned using .balign 2048.
     * The linker symbol _exception_vectors_base is set by the assembler.
     * No separate .vectors section is needed.
     */

    . = ALIGN(8);

    /*
     * Kernel log buffer — placed in named section for easy identification
     * in memory dumps. Magic value 0x4C474F44 ("DLOG") marks the start.
     */
    .klog_buffer : {
        *(.klog_buffer)
    }

    . = ALIGN(8);

    /*
     * __bss_start and __bss_end — used by entry.S BSS clear loop.
     */
    __bss_start = .;

    /*
     * .bss — Zero-initialized globals.
     * Entry.S clears this region before calling kernel_main().
     */
    .bss : {
        *(.bss)
        *(.bss.*)
        *(COMMON)
    }

    . = ALIGN(8);

    /*
     * Stack section.
     * entry.S defines __stack_bottom and __stack_top symbols here.
     * Stack grows DOWN from __stack_top.
     */
    .stack : {
        *(.stack)
    }

    . = ALIGN(8);
    __bss_end = .;

    /*
     * __kernel_end — total kernel image extent including BSS.
     */
    __kernel_end = .;

    /*
     * Discard DWARF debug, ARM exception tables, and other ELF overhead
     * that should not be present in the final binary image.
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
 * Linker assertions — verify critical requirements.
 */

/* Exception vectors are in .text.boot section (_exception_vectors_base symbol). */

/* Binary must not exceed 64MB (sanity check for Phase 1 research build) */
ASSERT((__kernel_end - __kernel_start) < 0x4000000,
       "ERROR: Kernel image exceeds 64MB — something is wrong")

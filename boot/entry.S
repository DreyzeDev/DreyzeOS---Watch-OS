/*
 * DreyzeOS — AArch64 Entry Point & Exception Vectors
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Safety Invariants:
 *   - CurrentEL is queried IMMEDIATELY before any EL1-specific system register writes!
 *   - If entry EL is unsupported (e.g. EL0), CPU branches to a minimal safe halt
 *     without modifying system registers or touching the stack.
 *   - Interrupts are disabled via DAIF.
 *   - Stack is set up pointing to __stack_top (16-byte aligned).
 *   - BSS is cleared (__bss_start to __bss_end, with .stack placed outside).
 *   - VBAR_EL1 is explicitly configured to point to _exception_vectors_base (2048-byte aligned)
 *     and followed by an ISB.
 *   - No flash/NAND writes. RAM-only execution.
 */

.section .text.boot, "ax"
.global _start
.global _exception_vectors_base
.global _halt
.global _panic_halt
.global arch_irq_enable
.global arch_irq_disable

/*
 * _start — very first instruction executed by the CPU.
 *
 * Parameters passed by bootloader (iBoot / Pongo / shim):
 *   x0: Pointer to struct xnu_arm64_boot_args or Apple DeviceTree (ADT)
 *   x1: Secondary argument (size or unused)
 */
_start:
    /*
     * Step 1: Preserve bootloader arguments in callee-saved registers.
     * Do NOT touch any other system state yet.
     */
    mov     x20, x0             /* x20 = boot_args / dtree pointer */
    mov     x21, x1             /* x21 = arg1 (size or unused) */

    /*
     * Step 2: Query CurrentEL immediately BEFORE any EL1-specific operations.
     * CurrentEL bits [3:2] contain the Exception Level (0, 1, 2, or 3).
     * Reading CurrentEL is architecturally permitted at all Exception Levels.
     */
    mrs     x22, CurrentEL
    lsr     x22, x22, #2
    and     x22, x22, #3        /* x22 = Current Exception Level */

    /*
     * Step 3: Validate Exception Level.
     * DreyzeOS expects to be entered at EL1 (kernel mode).
     * If the loader drops in at an unsupported EL (e.g. EL0 user mode),
     * we CANNOT access EL1 registers (MSR to CPACR_EL1/VBAR_EL1 would trap).
     * In that case, branch immediately to a minimal safe halt loop!
     */
    cmp     x22, #1
    b.ne    _unsupported_el_halt

    /*
     * Step 4: Mask all asynchronous interrupts at EL1 (safe at EL1).
     * D (Debug), A (SError), I (IRQ), F (FIQ).
     */
    msr     daifset, #0xf

    /*
     * Step 5: Initialize Stack Pointer.
     * Stack grows downwards from __stack_top.
     * AAPCS64 requires 16-byte alignment.
     */
    adr     x0, __stack_top
    mov     sp, x0

    /*
     * Step 6: Clear BSS section.
     * Zero-fill memory from __bss_start to __bss_end.
     * Note: .stack is located strictly AFTER __bss_end, so this loop
     * never overwrites the active stack area!
     */
    adr     x0, __bss_start
    adr     x1, __bss_end
    cmp     x0, x1
    b.ge    .bss_clear_done
.bss_clear_loop:
    str     xzr, [x0], #8
    cmp     x0, x1
    b.lt    .bss_clear_loop
.bss_clear_done:

    /*
     * Step 7: Configure Exception Vector Base (VBAR_EL1).
     * Only executed after EL1 is confirmed!
     * _exception_vectors_base is guaranteed 2048-byte aligned by linker assertion.
     */
    adr     x0, _exception_vectors_base
    msr     vbar_el1, x0
    isb

    /*
     * Step 8: Early CPU feature setup (enable FP/SIMD).
     */
    bl      _early_cpu_setup

    /*
     * Step 9: Transfer control to kernel_main(boot_args, arg1, boot_el).
     */
    mov     x0, x20             /* arg0: boot_args or dtree pointer */
    mov     x1, x21             /* arg1: size or unused */
    mov     x2, x22             /* arg2: confirmed entry EL */
    bl      kernel_main

    /*
     * Step 10: kernel_main must never return.
     * If it returns unexpectedly, spin in safe halt.
     */
    b       _halt

/*
 * _unsupported_el_halt — safe minimal halt for invalid entry EL (e.g. EL0).
 * Does not execute any privileged system register instructions.
 * Does not touch memory or stack.
 */
_unsupported_el_halt:
    wfi
    b       _unsupported_el_halt

/*
 * _early_cpu_setup — minimal CPU configuration at confirmed EL1.
 * Enables FP/SIMD access (CPACR_EL1.FPEN = 0b11).
 * Does NOT enable or modify MMU or caches (preserves loader state).
 */
_early_cpu_setup:
    /* Enable FP/SIMD: CPACR_EL1[21:20] = 0b11 (no trap for FP/SIMD) */
    mov     x0, #(3 << 20)
    msr     cpacr_el1, x0
    isb
    dsb     sy
    ret

/*
 * _halt — safe infinite halt loop.
 * Low-power WFI state. Recovers only on hardware reset or interrupt.
 */
_halt:
    wfi
    b       _halt

/*
 * _panic_halt — identical to _halt, symbolically distinguished for crash analysis.
 */
_panic_halt:
    wfi
    b       _panic_halt

/* ============================================================
 * Exception Vector Table (ARMv8-A Standard Layout)
 * Must be aligned to a 2048-byte (2KB) boundary.
 * Each of the 16 slots is exactly 128 bytes (32 instructions).
 * ============================================================ */
.balign 2048
_exception_vectors_base:
    /* Current EL with SP0 */
    .balign 128
    b       _exc_sync_sp0
    .balign 128
    b       _exc_irq_sp0
    .balign 128
    b       _exc_fiq_sp0
    .balign 128
    b       _exc_serror_sp0

    /* Current EL with SPx */
    .balign 128
    b       _exc_sync_spx
    .balign 128
    b       _exc_irq_spx
    .balign 128
    b       _exc_fiq_spx
    .balign 128
    b       _exc_serror_spx

    /* Lower EL using AArch64 */
    .balign 128
    b       _exc_sync_lower64
    .balign 128
    b       _exc_irq_lower64
    .balign 128
    b       _exc_fiq_lower64
    .balign 128
    b       _exc_serror_lower64

    /* Lower EL using AArch32 */
    .balign 128
    b       _exc_sync_lower32
    .balign 128
    b       _exc_irq_lower32
    .balign 128
    b       _exc_fiq_lower32
    .balign 128
    b       _exc_serror_lower32

/* Exception vector stubs */
_exc_sync_sp0:     bl _exception_handler; b _halt
_exc_irq_sp0:      bl _exception_handler; b _halt
_exc_fiq_sp0:      bl _exception_handler; b _halt
_exc_serror_sp0:   bl _exception_handler; b _halt
_exc_sync_spx:     bl _exception_handler; b _halt

/*
 * _exc_irq_spx — IRQ handler for Current EL with SP_EL1.
 * Frame size: 272 bytes (16-byte aligned).
 * Saves x0-x29, x30, ELR_EL1, SPSR_EL1.
 */
_exc_irq_spx:
    /* Allocate stack frame (272 bytes, 16-byte aligned) */
    sub     sp, sp, #272

    /* Save general-purpose registers x0..x29 */
    stp     x0,  x1,  [sp, #0]
    stp     x2,  x3,  [sp, #16]
    stp     x4,  x5,  [sp, #32]
    stp     x6,  x7,  [sp, #48]
    stp     x8,  x9,  [sp, #64]
    stp     x10, x11, [sp, #80]
    stp     x12, x13, [sp, #96]
    stp     x14, x15, [sp, #112]
    stp     x16, x17, [sp, #128]
    stp     x18, x19, [sp, #144]
    stp     x20, x21, [sp, #160]
    stp     x22, x23, [sp, #176]
    stp     x24, x25, [sp, #192]
    stp     x26, x27, [sp, #208]
    stp     x28, x29, [sp, #224]
    str     x30,      [sp, #240]

    /* Save ELR_EL1 and SPSR_EL1 */
    mrs     x0, elr_el1
    mrs     x1, spsr_el1
    stp     x0, x1, [sp, #248]

    /* Call C interrupt dispatcher */
    bl      aic_handle_irq

    /* Restore ELR_EL1 and SPSR_EL1 */
    ldp     x0, x1, [sp, #248]
    msr     elr_el1, x0
    msr     spsr_el1, x1

    /* Restore general-purpose registers x0..x30 */
    ldp     x0,  x1,  [sp, #0]
    ldp     x2,  x3,  [sp, #16]
    ldp     x4,  x5,  [sp, #32]
    ldp     x6,  x7,  [sp, #48]
    ldp     x8,  x9,  [sp, #64]
    ldp     x10, x11, [sp, #80]
    ldp     x12, x13, [sp, #96]
    ldp     x14, x15, [sp, #112]
    ldp     x16, x17, [sp, #128]
    ldp     x18, x19, [sp, #144]
    ldp     x20, x21, [sp, #160]
    ldp     x22, x23, [sp, #176]
    ldp     x24, x25, [sp, #192]
    ldp     x26, x27, [sp, #208]
    ldp     x28, x29, [sp, #224]
    ldr     x30,      [sp, #240]

    /* Deallocate stack frame */
    add     sp, sp, #272

    /* Return from exception */
    eret

_exc_fiq_spx:      bl _exception_handler; b _halt
_exc_serror_spx:   bl _exception_handler; b _halt
_exc_sync_lower64: bl _exception_handler; b _halt
_exc_irq_lower64:  bl _exception_handler; b _halt
_exc_fiq_lower64:  bl _exception_handler; b _halt
_exc_serror_lower64: bl _exception_handler; b _halt
_exc_sync_lower32: bl _exception_handler; b _halt
_exc_irq_lower32:  bl _exception_handler; b _halt
_exc_fiq_lower32:  bl _exception_handler; b _halt
_exc_serror_lower32: bl _exception_handler; b _halt

/*
 * CPU interrupt control helpers
 */
arch_irq_enable:
    msr     daifclr, #2
    isb
    ret

arch_irq_disable:
    msr     daifset, #2
    isb
    ret

/*
 * Stack section: 16 KiB reserved memory.
 * Placed in .stack section, mapped by linker script strictly after BSS.
 */
.section .stack, "aw", @nobits
.align 4
    .space 0x4000           /* 16 KiB stack */

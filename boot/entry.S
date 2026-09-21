/*
 * DreyzeOS — AArch64 Entry Point
 * Target: Apple Watch Series 4 / Apple S4 (T8006)
 *
 * Architecture notes:
 *   - Apple S4 (T8006) kernel executes in AArch64 (64-bit mode)
 *   - watchOS userspace uses ARM64_32 (ILP32 ABI, 32-bit pointers in 64-bit mode)
 *   - This entry point targets bare-metal AArch64 kernel execution
 *   - Load address: UNKNOWN_T8006_LOAD_ADDRESS (placeholder 0x800000)
 *
 * SAFETY: This is designed for RAM-only execution. No flash writes.
 */

.section .text.boot, "ax"
.global _start
.global _exception_vectors_base

/*
 * _start — very first instruction executed by the CPU.
 *
 * At entry:
 *   - CPU is in EL1 or EL3 depending on entry path (UNKNOWN for T8006)
 *   - MMU is off (or minimally configured by iBoot/PongoOS shim)
 *   - Caches may or may not be enabled
 *   - x0 may contain a pointer to Apple DeviceTree (LIKELY, based on XNU convention)
 *   - x1 may contain kernel size or unused (UNKNOWN)
 *
 * This code:
 *   1. Saves x0 (potential DeviceTree pointer) before we trash registers
 *   2. Sets up stack pointer
 *   3. Clears BSS
 *   4. Jumps to kernel_main(dtree_ptr)
 */
_start:
    /* Step 1: Save potential DeviceTree pointer from x0 */
    mov     x20, x0             /* x20 = possible DeviceTree pointer (callee-saved) */
    mov     x21, x1             /* x21 = possible kernel size / unused */

    /* Step 2: Disable interrupts at current EL (safe regardless of EL level) */
    msr     daifset, #0xf       /* Mask Debug, Abort, IRQ, FIQ */

    /* Step 3: Set up stack pointer
     * Stack grows downward. Stack top is defined in linker script as __stack_top.
     * We use 16-byte aligned stack as required by AArch64 ABI.
     */
    adr     x0, __stack_top
    mov     sp, x0

    /* Step 4: Clear BSS section
     * BSS contains zero-initialized globals.
     * We must clear it because we are freestanding (no OS loader to do it).
     */
    adr     x0, __bss_start
    adr     x1, __bss_end
    cmp     x0, x1
    b.ge    .bss_clear_done
.bss_clear_loop:
    str     xzr, [x0], #8      /* Write zero, advance pointer by 8 bytes */
    cmp     x0, x1
    b.lt    .bss_clear_loop
.bss_clear_done:

    /* Step 5: Set up minimal system registers for AArch64 */
    bl      _early_cpu_setup

    /* Step 6: Call kernel_main with DeviceTree pointer */
    mov     x0, x20             /* Restore DeviceTree pointer as first arg */
    mov     x1, x21             /* Second arg */
    bl      kernel_main

    /* Step 7: kernel_main should never return.
     * If it does, spin forever (safe — no side effects).
     */
    b       _halt

/*
 * _early_cpu_setup — minimal CPU register initialization before kernel_main.
 *
 * Sets up:
 *   - SCTLR_EL1: minimal safe configuration
 *   - CPACR_EL1: enable FP/SIMD access
 *
 * NOTE: MMU setup is done in kernel_main/mmu.c AFTER we know memory layout.
 *       We do NOT enable MMU here because load address is UNKNOWN for T8006.
 */
_early_cpu_setup:
    /* Enable FP/SIMD (CPACR_EL1.FPEN = 0b11 = no trap) */
    mov     x0, #(3 << 20)
    msr     cpacr_el1, x0
    isb

    /*
     * SCTLR_EL1: System Control Register
     * We set a minimal safe value:
     *   - Bit 2  (C): Data cache DISABLED (safe, we don't know cache topology yet)
     *   - Bit 12 (I): Instruction cache DISABLED (safe)
     *   - Bit 0  (M): MMU DISABLED
     * We only ensure the register has a known state.
     *
     * IMPORTANT: On T8006 the reset value of SCTLR_EL1 is UNKNOWN.
     * If entered via PongoOS/iBoot, it may already have MMU on.
     * For now: just preserve current value, don't break existing mapping.
     */
    /* mrs x0, sctlr_el1   <- We intentionally do NOT modify SCTLR here */
    /* Future: configure based on confirmed entry path */

    isb
    dsb     sy

    ret

/*
 * _halt — safe infinite halt loop.
 * Uses WFI (Wait For Interrupt) to reduce power consumption.
 * Can be recovered from via hardware reset.
 */
.global _halt
_halt:
    wfi
    b       _halt

/*
 * _panic_halt — called from panic(). Same as halt but symbolically distinct.
 */
.global _panic_halt
_panic_halt:
    wfi
    b       _panic_halt

/*
 * Exception Vector Table — required for AArch64.
 * Must be 2KB-aligned. Each entry is 128 bytes (32 instructions).
 *
 * Layout (per AArch64 spec):
 *   Offset 0x000: Current EL, SP0  — Synchronous
 *   Offset 0x080: Current EL, SP0  — IRQ/vIRQ
 *   Offset 0x100: Current EL, SP0  — FIQ/vFIQ
 *   Offset 0x180: Current EL, SP0  — SError/vSError
 *   Offset 0x200: Current EL, SPx  — Synchronous
 *   Offset 0x280: Current EL, SPx  — IRQ/vIRQ
 *   Offset 0x300: Current EL, SPx  — FIQ/vFIQ
 *   Offset 0x380: Current EL, SPx  — SError/vSError
 *   Offset 0x400: Lower EL, AArch64 — Synchronous
 *   ... etc
 */
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

/* Exception stubs — call into C handler */
_exc_sync_sp0:     bl _exception_handler; b _halt
_exc_irq_sp0:      bl _exception_handler; b _halt
_exc_fiq_sp0:      bl _exception_handler; b _halt
_exc_serror_sp0:   bl _exception_handler; b _halt
_exc_sync_spx:     bl _exception_handler; b _halt

/*
 * _exc_irq_spx — IRQ handler for Current EL with SP_EL1.
 * Saves interrupted context, calls C dispatcher aic_handle_irq(), restores context, and eret.
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

    /* Call C interrupt handler */
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
.global arch_irq_enable
arch_irq_enable:
    msr     daifclr, #2
    isb
    ret

.global arch_irq_disable
arch_irq_disable:
    msr     daifset, #2
    isb
    ret

/* Stack area — placed in BSS by linker script, but we need the symbol here */
.section .stack, "aw", @nobits
.align 4
.global __stack_bottom
__stack_bottom:
    .space 0x4000           /* 16 KiB stack */
.global __stack_top
__stack_top:

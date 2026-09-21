# DreyzeOS — Phase 3 Status Report (Step 1: UART0 & Step 2: AIC)

**Target Device**: Apple Watch Series 4 (44mm GPS) / Model A1978 / Watch4,2 / N131bAP  
**SoC**: Apple S4 / T8006 (dual-core Tempest)  
**Current Milestone**: Phase 3, Step 2 — Minimal Apple Interrupt Controller (AIC) Implementation Complete

---

## 1. Summary of Completed Work

### Step 1: UART0 Driver (COMPLETED)
- Implemented [`hal/t8006/uart.h`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/uart.h) & [`hal/t8006/uart.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/uart.c) at confirmed MMIO base `0x2e500000`.
- Added loop timeout safeguards against unclocked deadlocks.
- Linked to `klog_write_char` and `platform_init`.

### Step 2: AIC (Apple Interrupt Controller) Driver (COMPLETED)
1. **Reverse Engineering & Verification from Official Mach-O**:
   - Analyzed `AppleInterruptController` methods in `kernelcache.release.watch4` / `kernelcache.macho`:
     * `AppleInterruptController::handleInterrupt` (`0xfffffff0088cb8f4` .. `0xfffffff0088cbbe0`):
       - Confirmed read from offset `0x2004` (`AIC_REG_EVENT` / IACK).
       - Confirmed bitfield extraction: `vectorType = (IACK >> 16) & 0x7`, `irq = IACK & 0x3FF`.
       - Confirmed read from offset `0x2000` (`AIC_REG_WHOAMI`).
       - Confirmed write to offset `0x200C` (`AIC_REG_IPI_ACK`).
       - Confirmed EOI / mask clear logic at `0x4080 + (irq / 32) * 4`.
     * `AppleInterruptController::enableInterrupt` / `disableInterrupt`:
       - Confirmed write to `0x4000 + (irq / 32) * 4` (`AIC_REG_MASK_SET_BASE`) for disabling/masking.
       - Confirmed write to `0x4080 + (irq / 32) * 4` (`AIC_REG_MASK_CLR_BASE`) for enabling/unmasking.
       - Confirmed read from `0x4200 + (irq / 32) * 4` (`AIC_REG_HW_STATE_BASE`) for line status.
     * `AppleInterruptController::start`:
       - Confirmed reads from `0x0000` (`AIC_REG_REVISION`) and `0x0004` (`AIC_REG_INFO`).
       - Confirmed global enable write to `0x0010` (`AIC_REG_CONFIG`).

2. **Driver Implementation**:
   - Header [`hal/t8006/aic.h`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/aic.h): Complete definitions of register offsets, bitfield macros, handler prototypes, and API declarations.
   - C Driver [`hal/t8006/aic.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/aic.c):
     * Memory barrier-protected 32-bit MMIO access (`dsb sy`).
     * `aic_init()`: Clears handler table, masks all 1024 IRQ lines across all 32 banks (`0x4000`), enables controller (`0x0010`).
     * `aic_enable_irq(uint32_t irq)`: Unmasks bit in `0x4080 + (irq/32)*4`.
     * `aic_disable_irq(uint32_t irq)`: Masks bit in `0x4000 + (irq/32)*4`.
     * `aic_mask_all()`: Disables all 1024 interrupt lines.
     * `aic_ack()`: Reads `AIC_REG_EVENT` (`0x2004`).
     * `aic_eoi(uint32_t irq)`: Writes bit to `0x4080 + (irq/32)*4`.
     * `aic_get_cpu_id()`: Reads `AIC_REG_WHOAMI` (`0x2000`).
     * `aic_register_handler()` / `aic_unregister_handler()`: IRQ callback registration.
     * `aic_handle_irq()`: Main event dispatch loop handling HW IRQs and IPIs.
     * `aic_diag()`: Reads revision, info, CPU ID and logs to `klog`.

3. **ARM64 Exception / IRQ Entry Path**:
   - Updated [`boot/entry.S`](file:///C:/Users/pc/Desktop/DreyzeOS/boot/entry.S):
     * Replaced stub `_exc_irq_spx` with a real interrupt handler.
     * Allocates a 272-byte 16-byte aligned stack frame.
     * Saves general-purpose registers `x0`–`x29`, `x30` (`lr`), `elr_el1`, and `spsr_el1`.
     * Calls C dispatcher `aic_handle_irq()`.
     * Restores `elr_el1`, `spsr_el1`, and all GPRs.
     * Returns using `eret`.
     * Added `arch_irq_enable` (`msr daifclr, #2`) and `arch_irq_disable` (`msr daifset, #2`).

4. **Integration & Build**:
   - Included in [`hal/t8006/platform.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/platform.c): `platform_init()` invokes `aic_init()` and `aic_diag()`.
   - Added to [`Makefile`](file:///C:/Users/pc/Desktop/DreyzeOS/Makefile): `hal/t8006/aic.c` compiled into `DreyzeOS.elf` and `DreyzeOS.bin`.

---

## 2. Provenance of Hardware Constants

| Constant | Value | Source & Verification Method | Status |
|:---|:---:|:---|:---:|
| `T8006_AIC_BASE` | `0x2d180000` | DeviceTree node `/arm-io/aic` (`reg[0]`) | **CONFIRMED** |
| `T8006_AIC_SIZE` | `0x00008000` (32 KB) | DeviceTree node `/arm-io/aic` (`reg[1]`) | **CONFIRMED** |
| `T8006_AIC_VERSION` | `2` | DeviceTree node `/arm-io/aic` (`aic-version = 2`) | **CONFIRMED** |
| `T8006_AIC_TIMEBASE_BASE` | `0x2d188000` | DeviceTree node `/arm-io/aic-timebase` (`reg[0]`) | **CONFIRMED** |
| `T8006_AIC_TIMEBASE_SIZE` | `0x00001000` (4 KB) | DeviceTree node `/arm-io/aic-timebase` (`reg[1]`) | **CONFIRMED** |
| `AIC_REG_REVISION` | `0x0000` | `kernelcache.macho` disasm (`0x88c97fc`: `mov w1, #0`) | **CONFIRMED** |
| `AIC_REG_INFO` | `0x0004` | `kernelcache.macho` disasm (`0x88c98b8`: `mov w1, #4`) | **CONFIRMED** |
| `AIC_REG_CONFIG` | `0x0010` | `kernelcache.macho` disasm (`0x88ca3fc`: `mov w1, #0x10`) | **CONFIRMED** |
| `AIC_REG_WHOAMI` | `0x2000` | `kernelcache.macho` disasm (`0x88cb9f8`: `mov w1, #0x2000`) | **CONFIRMED** |
| `AIC_REG_EVENT` (IACK) | `0x2004` | `kernelcache.macho` disasm (`0x88cb950`: `mov w1, #0x2004`) | **CONFIRMED** |
| `AIC_REG_IPI_SEND` | `0x2008` | `kernelcache.macho` disasm (`0x88cab24`: `mov w1, #0x2008`) | **CONFIRMED** |
| `AIC_REG_IPI_ACK` | `0x200C` | `kernelcache.macho` disasm (`0x88cbabc`: `mov w1, #0x200c`) | **CONFIRMED** |
| `AIC_REG_IPI_MASK_CLR` | `0x202C` | `kernelcache.macho` disasm (`0x88caae8`: `mov w1, #0x202c`) | **CONFIRMED** |
| `AIC_REG_MASK_SET_BASE` | `0x4000` | `kernelcache.macho` disasm (`0x88caef4`: `mov w1, #0x4000`) | **CONFIRMED** |
| `AIC_REG_MASK_CLR_BASE` (EOI) | `0x4080` | `kernelcache.macho` disasm (`0x88cbad4`: `mov w8, #0x4080`) | **CONFIRMED** |
| `AIC_REG_HW_STATE_BASE` | `0x4200` | `kernelcache.macho` disasm (`0x88cb618`: `mov w8, #0x4200`) | **CONFIRMED** |

---

## 3. Files Created & Modified

| File | Status | Description |
|:---|:---:|:---|
| [`hal/t8006/aic.h`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/aic.h) | **NEW** | AIC driver declarations & confirmed register map |
| [`hal/t8006/aic.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/aic.c) | **NEW** | AIC driver implementation, MMIO handlers, IRQ dispatcher |
| [`boot/entry.S`](file:///C:/Users/pc/Desktop/DreyzeOS/boot/entry.S) | **MODIFIED** | Full register save/restore in `_exc_irq_spx` + DAIF helpers |
| [`hal/t8006/memory_map.h`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/memory_map.h) | **MODIFIED** | Added all confirmed AIC register offsets |
| [`hal/t8006/platform.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/platform.c) | **MODIFIED** | Connected `aic_init()` and `aic_diag()` to platform boot |
| [`Makefile`](file:///C:/Users/pc/Desktop/DreyzeOS/Makefile) | **MODIFIED** | Added `hal/t8006/aic.c` to `HAL_SRCS` |
| [`tests/test_runner.py`](file:///C:/Users/pc/Desktop/DreyzeOS/tests/test_runner.py) | **MODIFIED** | Added 3 AIC unit tests (constants, symbols, DeviceTree) |
| [`docs/PHASE3_REPORT.md`](file:///C:/Users/pc/Desktop/DreyzeOS/docs/PHASE3_REPORT.md) | **MODIFIED** | Complete milestone documentation |

---

## 4. Build & Test Verification Results

### Cross-Compilation (`make clean && make`)
```
[AS] boot/entry.S
[CC] kernel/kernel.c
[CC] kernel/panic.c
[CC] kernel/log.c
[CC] hal/t8006/platform.c
[CC] hal/t8006/device_tree.c
[CC] hal/t8006/uart.c
[CC] hal/t8006/aic.c
[CC] lib/string.c
[CC] lib/memory.c
[LD] build/DreyzeOS.elf
[BIN] build/DreyzeOS.bin (30 KB)
Build: PASS (0 errors)
```

### Binary Inspection (`tools/inspect_binary.py`)
```
Architecture:  AArch64 ✓
Entry point:   0x0000000100000000 ✓
Sections:      19 sections, .text.boot before .text ✓
KLOG buffer:   Found magic DLOG at offset 0x34a0 ✓
RESULT:        ELF=PASS  BIN=PASS ✓
```

### Test Suite (`tests/test_runner.py`)
```
  PASS: ADT parser — basic parse
  PASS: ADT parser — property access
  PASS: ADT parser — child node and MMIO region
  PASS: ADT parser — report generation
  PASS: inspect_binary — exists and is valid Python
  PASS: build/DreyzeOS.elf — exists after build
  PASS: build/DreyzeOS.bin — exists after build
  PASS: UART0 — header hardware constants match DeviceTree
  PASS: UART0 — exported symbols in built ELF
  PASS: UART0 — verified in Watch4,2 DeviceTree binary
  PASS: AIC — hardware constants match DeviceTree and kernelcache
  PASS: AIC — exported symbols in built ELF
  PASS: AIC — verified in Watch4,2 DeviceTree binary

Tests: 13  PASS: 13  FAIL: 0 ✓
```

---

## 5. Architectural Status Tags

- **CONFIRMED**:
  - AIC MMIO Base (`0x2d180000`), Size (`0x8000`), version (`2`).
  - AIC Timebase Base (`0x2d188000`), Size (`0x1000`).
  - Register offsets: `AIC_REG_REVISION` (`0x0000`), `AIC_REG_INFO` (`0x0004`), `AIC_REG_CONFIG` (`0x0010`), `AIC_REG_WHOAMI` (`0x2000`), `AIC_REG_EVENT` (`0x2004`), `AIC_REG_IPI_SEND` (`0x2008`), `AIC_REG_IPI_ACK` (`0x200C`), `AIC_REG_IPI_MASK_CLR` (`0x202C`), `AIC_REG_MASK_SET_BASE` (`0x4000`), `AIC_REG_MASK_CLR_BASE` (`0x4080`), `AIC_REG_HW_STATE_BASE` (`0x4200`).
  - Event structure: 10-bit IRQ number (`0x3FF`), 3-bit vectorType (`(event >> 16) & 0x7`).
  - ARM64 AArch64 exception entry path for EL1h IRQ with full GPR save/restore and `eret`.

- **LIKELY**:
  - Maximum IRQs: 1024 (allocated 32 words of 32 bits, standard for A12/S4 class AIC).

- **UNKNOWN**:
  - Complete mapping of every single peripheral IRQ number outside of those declared in DeviceTree (e.g., UART0 IRQ 262, DockChannel IRQ 167 are confirmed from DeviceTree).

---

## 6. Milestone Checkpoint

> [!IMPORTANT]
> Step 2 (AIC) is **100% COMPLETE**.
> In accordance with the user's explicit instructions:
> *"После завершения AIC ОСТАНОВИСЬ. Не переходи к Dynamic DeviceTree / framebuffer без моей команды."*
> Work is paused and awaiting user instructions.

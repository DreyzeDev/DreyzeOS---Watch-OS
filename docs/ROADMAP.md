# DreyzeOS Development Roadmap

## Overview

DreyzeOS is a research operating system for Apple Watch Series 4 (T8006 / Apple S4).
This document tracks the development phases from initial research to a working GUI.

---

## PHASE 1 — Research + Repository + ARM64 Toolchain
**Status**: 🔄 IN PROGRESS  
**Goal**: Build reproduces successfully. All research documented.

### Tasks
- [x] Create repository structure
- [x] Write initial documentation stubs
- [ ] Complete T8006 hardware research
- [ ] Complete Peepo analysis
- [ ] Complete PongoOS analysis
- [x] Install ARM64 cross-compilation toolchain (WSL2)
- [x] Write entry.S (AArch64 entry point)
- [x] Write kernel_main()
- [x] Write linker script
- [ ] `make` succeeds → `build/DreyzeOS.bin` produced
- [ ] Binary verified: correct sections, symbols, ELF format
- [ ] Initial git commits done

### Deliverables
- `build/DreyzeOS.bin`
- `docs/RESEARCH.md` (T8006 findings)
- `docs/HARDWARE.md`
- `docs/SAFETY.md`

---

## PHASE 2 — Minimal Freestanding Kernel
**Status**: 🔄 IN PROGRESS  
**Goal**: `build/DreyzeOS.bin` is a valid freestanding ARM64 binary.

### Tasks
- [x] `boot/entry.S` — stack init, BSS clear, jump to kernel_main
- [x] `kernel/kernel.c` — kernel_main() implementation
- [x] `kernel/panic.c` — panic() with infinite loop / WFI
- [x] `kernel/log.c` — early logging (UART stub or semihosting)
- [x] `lib/string.c` — memcpy, memset, memcmp, strlen, strcpy
- [x] `lib/memory.c` — bump allocator
- [x] `arch/arm64/exceptions.S` — exception vectors
- [ ] All code compiles without errors
- [ ] Binary analyzed: check entry point, sections, size

### Deliverables
- Freestanding `DreyzeOS.bin` that would execute at a defined load address

---

## PHASE 3 — T8006 Hardware Research
**Status**: 🔄 IN PROGRESS  
**Goal**: HARDWARE.md and RESEARCH.md fully populated from verified sources.

### Tasks
- [ ] Document T8006 die identification
- [ ] Document CPU configuration (cores, cache, clock)
- [ ] Document RAM layout (base address, size) — SOURCE REQUIRED
- [ ] Document MMIO map draft (UNKNOWN where unconfirmed)
- [ ] Document UART (if any) — base address or UNKNOWN
- [ ] Document display controller — type or UNKNOWN
- [ ] Document touch controller — bus, address or UNKNOWN
- [ ] Document Digital Crown interface — GPIO/SPI/I2C or UNKNOWN
- [ ] Document side button GPIO — or UNKNOWN
- [ ] Document interrupt controller — GIC or Apple AIC, base or UNKNOWN
- [ ] Document PMGR (power manager) — base or UNKNOWN
- [ ] Create `hal/t8006/memory_map.h` with all known/unknown addresses
- [ ] Run Peepo on real device (if available) to get DeviceTree dump
- [ ] Parse DeviceTree → document real addresses

### Deliverables
- `docs/HARDWARE.md`
- `docs/RESEARCH.md`
- `hal/t8006/memory_map.h`

---

## PHASE 4 — Safe Execution Path Research
**Status**: ⏳ PENDING (depends on Phase 3)  
**Goal**: Understand and document a viable path: Host → Watch → RAM → DreyzeOS

### Research Questions
- Does checkm8 / checkra1n work on Apple Watch Series 4 / T8006?
- Can PongoOS be adapted for T8006?
- Can Peepo provide a safe code injection path?
- Is there a USB boot mode usable for code loading?
- Can a watchOS app sandbox be escaped safely for research?

### Safety Requirement
- Any proposed path must be reviewed in `docs/SAFETY.md`
- No path is approved until risk is documented and assessed

### Deliverables
- `docs/BOOT.md` — execution path analysis
- Updated `docs/SAFETY.md`

---

## PHASE 5 — First Controlled Execution on T8006
**Status**: ⏳ PENDING (depends on Phase 4)  
**Goal**: DreyzeOS code executes on real Apple Watch Series 4 hardware.

### Minimum Success Criteria
- DreyzeOS entry.S executes
- Stack is initialized
- kernel_main() is reached
- Some form of output is visible (UART, display, or detectable side effect)

### Notes
- This phase requires physical Apple Watch Series 4
- Execution must be RAM-only and not touch flash
- A restore path must be independently confirmed before any experiment; recovery from arbitrary execution state is not guaranteed

---

## PHASE 6 — Timer / Logging / Hardware Discovery
**Status**: ⏳ PENDING  
**Goal**: Working timer, logging over UART or debug channel, live hardware discovery.

### Tasks
- [ ] Implement timer_init() with real T8006 timer registers
- [ ] Implement log output via confirmed UART or debug path
- [ ] Walk DeviceTree from kernel to discover hardware
- [ ] Log device tree nodes to output

---

## PHASE 7 — Display
**Status**: ⏳ PENDING  
**Goal**: Apple Watch display shows "DreyzeOS" on black background.

### Research Required
- Display controller identification (CONFIRMED source required)
- Framebuffer base address (from DeviceTree or experiment)
- Display initialization sequence

### Minimum Output
```
[black background]
   DreyzeOS
```

---

## PHASE 8 — Digital Crown + Side Button
**Status**: ⏳ PENDING  
**Goal**: CROWN_UP, CROWN_DOWN, CROWN_PRESS, BUTTON_PRESS events working.

### Research Required
- Crown controller interface (SPI/I2C/GPIO)
- Interrupt assignment
- Register map

---

## PHASE 9 — Touch
**Status**: ⏳ PENDING  
**Goal**: TOUCH_DOWN, TOUCH_MOVE, TOUCH_UP events working.

### Research Required
- Touch IC identification (from DeviceTree)
- I2C address and protocol
- IRQ line

---

## PHASE 10 — GUI
**Status**: ⏳ PENDING  
**Goal**: Functional minimal GUI on Apple Watch display.

### UI Design
- Black background, minimal aesthetic
- Large elements (optimized for tiny screen)
- Navigation via Digital Crown + touch
- Main screen items:
  - DreyzeOS (title)
  - Clock
  - Apps
  - Settings
  - About

---

## Fact Status Legend

| Tag | Meaning |
|-----|---------|
| CONFIRMED | Verified from documentation, source code, or experiment |
| LIKELY | Strongly inferred from related data, not directly confirmed |
| DESIGN | Host-side proposal, not hardware evidence |
| UNKNOWN | Not yet determined — placeholder used in code |
| BLOCKED | Cannot proceed until dependency is resolved |

---

## Key Principle

> **Never present an assumption as a fact.**  
> All MMIO addresses, memory maps, and hardware configurations are marked  
> `UNKNOWN_T8006_*` until confirmed by documentation, DeviceTree dump, or experiment.

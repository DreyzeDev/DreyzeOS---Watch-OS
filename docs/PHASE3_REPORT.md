# DreyzeOS — Phase 3 Status Report (Step 1: UART0, Step 2: AIC, Step 3: Dynamic DeviceTree)

**Target Device**: Apple Watch Series 4 (44mm GPS) / Model A1978 / Watch4,2 / N131bAP  
**SoC**: Apple S4 / T8006 (dual-core Tempest)  
**Current Milestone**: Phase 3, Step 3 — Dynamic DeviceTree & Boot-time Hardware Discovery Complete

---

## 1. Summary of Completed Work

### Step 1: UART0 Driver (COMPLETED)
- Implemented [`hal/t8006/uart.h`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/uart.h) & [`hal/t8006/uart.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/uart.c) at confirmed MMIO base `0x2e500000`.
- Added loop timeout safeguards against unclocked deadlocks.
- Linked to `klog_write_char` and `platform_init`.

### Step 2: AIC (Apple Interrupt Controller) Driver (COMPLETED)
- Verified all AIC register offsets directly against `kernelcache.macho` disassembly (`0x2004` EVENT, `0x2000` WHOAMI, `0x200C` IPI_ACK, `0x4000` MASK_SET, `0x4080` MASK_CLR, `0x4200` HW_STATE).
- Implemented [`hal/t8006/aic.h`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/aic.h) and [`hal/t8006/aic.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/aic.c).
- Implemented full ARM64 exception frame save/restore in [`boot/entry.S`](file:///C:/Users/pc/Desktop/DreyzeOS/boot/entry.S) for `_exc_irq_spx`.

### Step 3: Dynamic DeviceTree & Boot-Time Hardware Discovery (COMPLETED)
1. **Boot ABI Verification (Mach-O Disassembly)**:
   - Disassembled kernel entry point `start_first_cpu` at VA `0xfffffff007b2c070` in `research/ipsw/21U580/kernelcache.macho`:
     ```asm
     0xfffffff007b2c070:  mov  x20, x0          ; x0 = pointer to struct boot_args
     0xfffffff007b2c074:  ldr  x22, [x20, #8]   ; virtBase
     0xfffffff007b2c078:  ldr  x23, [x20, #0x10]; physBase
     0xfffffff007b2c07c:  ldr  x24, [x20, #0x18]; memSize
     ```
   - Confirmed `x0` ABI parameter conventions between Apple iBoot and XNU.
   - Identified and mapped `struct xnu_arm64_boot_args_t` with its embedded `Boot_Video` framebuffer structure.

2. **Boot Info Data Architecture**:
   - Created [`include/boot_info.h`](file:///C:/Users/pc/Desktop/DreyzeOS/include/boot_info.h):
     * `boot_video_t`: Framebuffer properties passed by iBoot (`v_baseAddr`, `v_display`, `v_rowBytes`, `v_width`, `v_height`, `v_depth`).
     * `xnu_arm64_boot_args_t`: Full 64-bit boot arguments layout matching XNU `pexpert/arm64/boot.h`.
     * `memory_range_t`: Dynamic DRAM and reserved memory descriptors (`base`, `size`, `type`, `name[32]`).
     * `boot_framebuffer_info_t`: Structured runtime framebuffer state (`paddr`, `size`, `width`, `height`, `stride`, `depth`, `pixel_format`, `is_valid`).
     * `platform_boot_info_t`: Global consolidated boot parameters.

3. **Safe Bounds-Checked ADT Parser**:
   - Implemented [`hal/t8006/device_tree.h`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/device_tree.h) and rewritten [`hal/t8006/device_tree.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/device_tree.c):
     * Dual-mode ABI auto-detection (`platform_boot_info_init`):
       1. Validates `arg0` as direct ADT pointer via `devtree_validate_header`.
       2. If not ADT, inspects `arg0` as `xnu_arm64_boot_args_t` pointer (checks valid `phys_base` and `mem_size`, loads ADT pointer from `devicetree_p`).
       3. If neither or invalid, gracefully falls back to research-only S4/T8006
          defaults without crashing; fallback values are not runtime proof.
     * Safe recursive node walking with depth limits (`MAX_NODE_DEPTH = 16`) and pointer bounds checking against `tree_limit`.
     * Dynamic DRAM detection from `/memory` (`reg` property) or `boot_args` (`phys_base`, `mem_size`).
     * Dynamic reservation parsing from `/chosen/memory-map` (16-byte pairs: `uint64_t paddr`, `uint64_t size`).
     * Framebuffer detection from both `boot_args->video` and `/chosen/memory-map` display reservations.
     * Platform metadata extraction (`model`, `target-type`, `chip-id`, `board-id`).
     * Diagnostic logging function `platform_boot_info_diag()`.

4. **Kernel Integration**:
   - Updated [`kernel/kernel.c`](file:///C:/Users/pc/Desktop/DreyzeOS/kernel/kernel.c):
     * Calls `platform_boot_info_init(dtree_ptr, arg1)` before early memory/subsystem initializations.
     * Calls `platform_boot_info_diag()` to log discovered memory topology and framebuffer parameters.

---

## 2. Provenance of Hardware Constants & ABI

| Item | Value / Range | Source & Verification Method | Status |
|:---|:---:|:---|:---:|
| `boot_args` pointer register | `x0` | `kernelcache.macho` disasm (`0x7b2c070: mov x20, x0`) | **CONFIRMED** |
| `boot_args.virt_base` offset | `+0x08` | `kernelcache.macho` disasm (`ldr x22, [x20, #8]`) | **CONFIRMED** |
| `boot_args.phys_base` offset | `+0x10` | `kernelcache.macho` disasm (`ldr x23, [x20, #0x10]`) | **CONFIRMED** |
| `boot_args.mem_size` offset | `+0x18` | `kernelcache.macho` disasm (`ldr x24, [x20, #0x18]`) | **CONFIRMED** |
| `boot_args.video` offset | `+0x28` | XNU `arm64/boot.h` + confirmed struct alignment | **CONFIRMED** |
| `boot_args.devicetree_p` offset | `+0x60` | XNU `arm64/boot.h` (64-bit physical pointer) | **CONFIRMED** |
| `boot_args.devicetree_length` offset | `+0x68` | XNU `arm64/boot.h` (uint32_t length) | **CONFIRMED** |
| `/chosen/memory-map` format | `[u64 paddr, u64 size]` (16 B) | Static ADT inspection + XNU `pe_gen.c` references | **CONFIRMED** |
| Pixel format (Apple boot display) | `BGRA32` / `BGR24` | `kernelcache.macho` string `"BBBBBBBBGGGGGGGGRRRRRRRR"` | **CONFIRMED** |
| T8006 Fallback DRAM Base | `0x800000000` | Research fallback; static `/memory` is `0x0+0x0` | **UNKNOWN/BLOCKED** |
| T8006 Fallback DRAM Size | `0x40000000` (1 GB) | Product/research quantity; live map not established | **UNKNOWN/BLOCKED** |
| Runtime Framebuffer Base | Dynamic | Parser/design path from `boot_args.video` or `/chosen/memory-map`; no hardware run | **UNKNOWN/BLOCKED** |
| Panel Resolution | 368 x 448 | Watch4,2 44mm physical panel spec (not assumed for FB layout) | **CONFIRMED** |

---

## 3. Files Created & Modified

| File | Status | Description |
|:---|:---:|:---|
| [`include/boot_info.h`](file:///C:/Users/pc/Desktop/DreyzeOS/include/boot_info.h) | **NEW** | Boot ABI data structures (`xnu_arm64_boot_args_t`, `boot_framebuffer_info_t`, `platform_boot_info_t`) |
| [`hal/t8006/device_tree.h`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/device_tree.h) | **NEW** | ADT low-level types and discovery API declarations |
| [`hal/t8006/device_tree.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/device_tree.c) | **FULL REWRITE** | Bounds-checked ADT parser, dynamic DRAM/reservation/framebuffer detection |
| [`kernel/kernel.c`](file:///C:/Users/pc/Desktop/DreyzeOS/kernel/kernel.c) | **MODIFIED** | Added `platform_boot_info_init()` and `platform_boot_info_diag()` calls |
| [`tests/test_runner.py`](file:///C:/Users/pc/Desktop/DreyzeOS/tests/test_runner.py) | **MODIFIED** | Added 6 new unit tests for boot-info and dynamic DeviceTree parsing (19 tests total) |
| [`docs/PHASE3_REPORT.md`](file:///C:/Users/pc/Desktop/DreyzeOS/docs/PHASE3_REPORT.md) | **MODIFIED** | Updated with Step 3 documentation |

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
[BIN] build/DreyzeOS.bin (33 KB)
Build: PASS (0 errors, 0 warnings)
```

### Binary Inspection (`tools/inspect_binary.py`)
```
Architecture:  AArch64 ✓
Entry point:   0x0000000100000000 ✓
Sections:      19 sections, .text.boot before .text ✓
KLOG buffer:   Found magic DLOG at offset 0x4070 ✓
RESULT:        ELF=PASS  BIN=PASS ✓
```

### Test Suite (`tests/test_runner.py`)
```
==================================================
DreyzeOS Test Suite
==================================================

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
  PASS: boot-info — valid tree: parse static Watch4,2 ADT
  PASS: boot-info — missing /chosen: synthetic tree without chosen
  PASS: boot-info — truncated tree: parser must not crash
  PASS: boot-info — memory-map parsing: static ADT has zero-filled entries
  PASS: boot-info — framebuffer discovery: synthetic tree with Display entry
  PASS: boot-info — bounds checking: prop_count=0xFFFFFFFF must not crash

==================================================
Tests: 19  PASS: 19  FAIL: 0
==================================================

All tests PASSED ✓
```

---

## 5. Architectural Status Tags

- **CONFIRMED**:
  - Boot argument register conventions (`x0` contains `boot_args` or ADT base).
  - Offsets of `virt_base` (+0x08), `phys_base` (+0x10), `mem_size` (+0x18), `video` (+0x28), `devicetree_p` (+0x60).
  - DeviceTree `/chosen/memory-map` format (16-byte pairs of `uint64_t`).
  - Safe fallback mechanisms when booting in simulator or without iBoot boot_args.

- **LIKELY**:
  - iBoot populates a `/chosen/memory-map` entry labeled `Display` or `Framebuffer` containing the active scanout memory range.

- **UNKNOWN**:
  - Exact framebuffer physical address before boot (must always be resolved dynamically at runtime).
  - Exact row bytes (stride) chosen by iBoot before discovery.

---

## 6. Milestone Checkpoint

> [!IMPORTANT]
> Step 3 (Dynamic DeviceTree / boot-time hardware discovery) is **100% COMPLETE**.
> In accordance with the user's explicit instructions:
> *"После завершения Dynamic DeviceTree ОСТАНОВИСЬ. НЕ переходи к записи пикселей во framebuffer, НЕ реализовывай display driver, НЕ переходи к Touch/Crown."*
> Work is paused and awaiting user instructions.

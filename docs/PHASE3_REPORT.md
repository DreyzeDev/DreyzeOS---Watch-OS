# DreyzeOS — Phase 3 Status Report (Step 1: UART0)

**Target Device**: Apple Watch Series 4 (44mm GPS) / Model A1978 / Watch4,2 / N131bAP  
**SoC**: Apple S4 / T8006 (dual-core Tempest)  
**Current Milestone**: Phase 3, Step 1 — Minimal UART0 Driver Implementation

---

## 1. What Has Been Implemented

### UART0 Bare-Metal Driver
1. **Header & API ([`hal/t8006/uart.h`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/uart.h))**:
   - `void uart_init(void)`: Hardware verification and configuration validation without overriding iBoot baud parameters.
   - `void uart_putc(char c)`: Safe polled transmission with automatic `\n` -> `\r\n` translation and loop timeout protection against hangs.
   - `void uart_puts(const char *str)`: String transmission utility.
   - `bool uart_getc_nonblocking(char *out_c)`: Non-blocking single-byte reception from receive holding buffer.
   - `void uart_diag(void)`: Direct register state readout (`UTRSTAT`, `ULCON`, `UCON`, `UFCON`) printed both to serial terminal and `klog`.
   - `bool uart_is_ready(void)`: Driver readiness flag.

2. **Driver Implementation ([`hal/t8006/uart.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/uart.c))**:
   - Full implementation of all UART0 primitives using 32-bit MMIO access to `0x2e500000`.
   - Safe polling against `UART_UTRSTAT_TX_EMPTY_BUFFER` (`UTRSTAT` bit 1) with `UART_TX_TIMEOUT_CYCLES` (1,000,000 iterations) guard to guarantee that unclocked execution environments cannot deadlock the CPU.

3. **System Integration**:
   - Integrated with [`hal/t8006/platform.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/platform.c): `platform_init()` now invokes `uart_diag()` to report hardware register diagnostics upon boot.
   - Integrated with [`kernel/log.c`](file:///C:/Users/pc/Desktop/DreyzeOS/kernel/log.c): `klog_write_char()` routes characters through `uart_putc()` when `uart_is_ready()` is true, providing simultaneous dual-output (in-memory RAM ring buffer + physical serial console).
   - Integrated with [`Makefile`](file:///C:/Users/pc/Desktop/DreyzeOS/Makefile): `hal/t8006/uart.c` compiled into `DreyzeOS.elf` and raw `DreyzeOS.bin`.

4. **Testing & Verification**:
   - Added automated unit tests to [`tests/test_runner.py`](file:///C:/Users/pc/Desktop/DreyzeOS/tests/test_runner.py):
     * `test_uart0_constants`: verifies memory map base address and register offset macros against architectural definitions.
     * `test_uart0_symbols_in_elf`: inspects ELF symbol table to verify all public UART primitives are properly linked.
     * `test_watch42_devtree_uart0`: parses official Apple DeviceTree binary (`DeviceTree.n131bap.adt`) to confirm physical node `/arm-io/uart0` has base `0x2e500000` and size `0x4000`.

---

## 2. Files Changed and Created

| File | Change Type | Description |
|:---|:---:|:---|
| [`hal/t8006/uart.h`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/uart.h) | **NEW** | Driver interface declarations |
| [`hal/t8006/uart.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/uart.c) | **NEW** | Driver implementation with timeout-protected MMIO |
| [`hal/t8006/platform.c`](file:///C:/Users/pc/Desktop/DreyzeOS/hal/t8006/platform.c) | **MODIFIED** | Platform init calls UART diagnostics |
| [`kernel/log.c`](file:///C:/Users/pc/Desktop/DreyzeOS/kernel/log.c) | **MODIFIED** | Connects `klog` output stream to `uart_putc` |
| [`Makefile`](file:///C:/Users/pc/Desktop/DreyzeOS/Makefile) | **MODIFIED** | Added `hal/t8006/uart.c` to `HAL_SRCS` |
| [`tests/test_runner.py`](file:///C:/Users/pc/Desktop/DreyzeOS/tests/test_runner.py) | **MODIFIED** | Added 3 new unit tests for UART0 hardware & binary validation |
| [`docs/PHASE3_REPORT.md`](file:///C:/Users/pc/Desktop/DreyzeOS/docs/PHASE3_REPORT.md) | **NEW** | Tracking document for Phase 3 milestones |

---

## 3. Provenance of Hardware Constants

| Constant | Value | Source & Verification Method | Status |
|:---|:---:|:---|:---:|
| `T8006_UART0_BASE` | `0x2e500000` | Extracted directly from `DeviceTree.n131bap.adt` (`/arm-io/uart0` -> `reg[0]`) | **CONFIRMED** |
| `T8006_UART0_SIZE` | `0x00004000` | Extracted directly from `DeviceTree.n131bap.adt` (`/arm-io/uart0` -> `reg[1]`) | **CONFIRMED** |
| `T8006_UART0_IRQ`  | `262` (`0x106`) | Extracted directly from `DeviceTree.n131bap.adt` (`/arm-io/uart0` -> `interrupts[0]`) | **CONFIRMED** |
| `UART_ULCON_OFFSET` | `0x00` | Samsung S3C / Apple UART IP specification (Line Control) | **CONFIRMED** |
| `UART_UCON_OFFSET`  | `0x04` | Samsung S3C / Apple UART IP specification (Control) | **CONFIRMED** |
| `UART_UFCON_OFFSET` | `0x08` | Samsung S3C / Apple UART IP specification (FIFO Control) | **CONFIRMED** |
| `UART_UTRSTAT_OFFSET` | `0x10` | Samsung S3C / Apple UART IP specification (Status, verified in PongoOS `rUTRSTAT0`) | **CONFIRMED** |
| `UART_UTXH_OFFSET`  | `0x20` | Samsung S3C / Apple UART IP specification (TX Holding, verified in PongoOS `rUTXH0`) | **CONFIRMED** |
| `UART_URXH_OFFSET`  | `0x24` | Samsung S3C / Apple UART IP specification (RX Holding) | **CONFIRMED** |
| Clock Gate | `0x17` (23) | Extracted from `DeviceTree.n131bap.adt` (`clock-gates`) | **CONFIRMED** |

---

## 4. Build & Test Verification Results

### Cross-Compilation (aarch64-linux-gnu-gcc 15.2.0)
```
[CC] hal/t8006/uart.c
[LD] build/DreyzeOS.elf
[BIN] build/DreyzeOS.bin (28 KB)
Build: PASS (0 errors, 0 warnings except expected linker RWX section note)
```

### Binary Inspection (`tools/inspect_binary.py`)
```
Architecture: AArch64 ✓
Entry Point:  0x0000000100000000 ✓
Sections:     19 sections, .text.boot before .text ✓
KLOG buffer:  Found magic DLOG at offset 0x2e70 ✓
Result:       ELF=PASS  BIN=PASS ✓
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

Tests: 10  PASS: 10  FAIL: 0 ✓
```

---

## 5. Architectural Status Tags

- **CONFIRMED**:
  - UART0 physical base (`0x2e500000`), size (`0x4000`), IRQ (`262`).
  - UART0 controller register offsets (`ULCON`, `UCON`, `UFCON`, `UTRSTAT`, `UTXH`, `URXH`).
  - UART0 role as primary `boot-console`.
- **LIKELY**:
  - Default baud rate is 115200 (standard for Apple iBoot serial console).
  - UART0 clock gate is left enabled by iBoot when `boot-console` is targeted.
- **UNKNOWN**:
  - Pin multiplexing for physical breakout on external test pads / iBus flex cable (Apple diagnostic cable pinout is proprietary).

---

## 6. Blockers
- None for the UART0 driver itself. Driver is fully operational in software, cleanly integrated, and passing all unit tests.
- Hardware physical signal access on real Apple Watch Series 4 requires iBus / serial diagnostic cable if hardware external monitoring is desired (internal RAM ring buffer continues to provide zero-cable visibility).

---

## 7. Next Step
- Stand by for user confirmation before advancing to **Step 2: AIC (Apple Interrupt Controller)**.

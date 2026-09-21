# DreyzeOS — Pre-Hardware Boot Audit & Safety Report

**Target**: Apple Watch Series 4 (44mm GPS), Model A1978, Watch4,2 (N131bAP)  
**SoC**: Apple S4 / T8006, AArch64  
**Firmware Baseline**: watchOS 10.6.1 (21U580)  
**Phase**: 4 — Step 2.1: Pre-Hardware Boot Audit & Safety Hardening  
**Canonical Branch**: `master`  
**Current Baseline Commit**: `4138087`  
**Host Test Status**: 39/39 PASS (Python + Native C Harness)  
**Build Status**: ELF=PASS, BIN=PASS, 0 Compiler Warnings  
**Hardware Execution Gate**: **NOT READY (BLOCKED)**

---

## 1. Exact Target Hardware

- **Device**: Apple Watch Series 4, 44mm, GPS
- **Model Identifier**: `Watch4,2`
- **Internal Board Identifier**: `N131bAP` / `n131bap`
- **SoC Identifier**: Apple S4 / `T8006` (`0x8006`)
- **CPU Architecture**: ARMv8-A AArch64 (64-bit kernel execution)
- **Primary DRAM Physical Base**: `0x800000000` (CONFIRMED from DeviceTree `/memory`)
- **Primary DRAM Size**: 1024 MiB / 1 GiB (`0x40000000`)
- **Display Resolution**: 368 × 448 pixels (OLED scanout)

---

## 2. Canonical Branch & Build Provenance

- **Canonical Development Branch**: `master`
- **Provenance Tagging**: Every build embeds:
  - `GIT_COMMIT_SHA`: Short hash of the commit
  - `DREYZEOS_CANONICAL_BRANCH`: `"master"`
  - `DREYZE_FB_TEST_PATTERN`: Compile-time test switch state (`0` by default)
  - `DREYZEOS_VERSION_STRING`: `"DreyzeOS 0.1.0-research"`
- **Binary Image Size**: 49,240 bytes (48.1 KB)

---

## 3. Confirmed Facts (Evidence-Based)

| Fact | Evidence | Source |
|:---|:---|:---|
| **CPU Architecture** | AArch64 mode confirmed | Kernelcache Mach-O header `0x100000C` (ARM64) |
| **Primary DRAM Base** | `0x800000000` (32GB boundary) | Static ADT node `/memory` `reg` property |
| **Primary DRAM Size** | `0x40000000` (1 GiB) | Static ADT node `/memory` `reg` property |
| **UART0 Physical Base** | `0x2E500000` | Static ADT node `/arm-io/uart0` `reg` property |
| **UART0 Interrupt ID** | 262 (`0x106`) | Static ADT node `/arm-io/uart0` `interrupts` property |
| **AIC Physical Base** | `0x2D180000` | Exact Watch4,2/n131bap ADT `/arm-io/aic` `reg`; `0x2E300000` was a stale report error |
| **AIC Version** | AIC2 (1024 IRQ lines, 32 banks) | Kernelcache disasm + DeviceTree `aic-version` = 2 |
| **boot_args ABI Layout** | `virt_base` (+0x08), `phys_base` (+0x10), `video` (+0x28), `devicetree_p` (+0x60) | XNU kernelcache entry point `0xfffffff007b2c070` |
| **Pixel Color Format** | `"BBBBBBBBGGGGGGGGRRRRRRRR"` (BGRA32) | Kernelcache read-only string at `0xfffffff00823ea2c` |
| **Exception Level** | EL1 on kernel handoff | ARM64 boot convention, XNU kernel vector table |
| **Interrupt Masking on Entry** | DAIF = `0xF` (D, A, I, F masked) | ARM64 kernel entry convention + `boot/entry.S` |
| **Vector Table Alignment** | Must be 2048-byte aligned | ARMv8-A Architectural Reference Manual |
| **Stack Alignment** | Must be 16-byte aligned | AAPCS64 (ARM 64-bit Procedure Call Standard) |

---

## 4. Likely Facts (Pending Hardware Confirmation)

| Fact | Rational Basis | Risk if Incorrect |
|:---|:---|:---|
| **iBoot Flat/Identity Mapping** | Bootloader shims typically leave a 1:1 physical-to-virtual window for low RAM | Dereferencing physical addresses causes synchronous translation faults |
| **Caches Enabled by Loader** | SecureROM and iBoot operate with caches on for boot performance | Inconsistent memory views between CPU and display scanout engine |
| **x1 Register Semantic** | iBoot typically passes kernel size or unused 0 in x1 | Register value ignored or mistaken for address pointer |
| **UART0 Baud Rate = 115200** | Standard Apple development serial console baud rate | Corrupted characters on serial terminal |

---

## 5. Unknown Facts (Must NOT Be Assumed)

| Unknown | Description | Mitigation in DreyzeOS |
|:---|:---|:---|
| **Exact RAM Handover Address** | Address where loader deposits DreyzeOS.bin | `DREYZEOS_LOAD_BASE = 0x100000000` marked as PLACEHOLDER / BLOCKED |
| **Physical TX Routing on Connector** | Which of the 5 pins in the iBUS slot carries UART0 TX | Logic analyzer probe required; no hardware write assumed |
| **usbliter8 S4 Exploit Reliability** | Whether USB DWC2 buffer underflow triggers cleanly on Watch4,2 | Treated strictly as THEORETICAL; exploit not run |
| **Display Panel Initialization** | Whether OLED panel scanout is active at handoff | Writes hard-locked; no MIPI DSI programming attempted |

---

## 6. Hardware Blockers

The following items prevent safe hardware execution today:

1. **Linker Load Address Discrepancy**:
   - `DreyzeOS.ld` links the binary at `0x100000000`.
   - The real RAM delivery mechanism may load the binary at DRAM base (`0x800000000` + offset) or an SRAM buffer.
   - Executing an absolute-addressed image at a differing load address causes immediate invalid branches or data corruptions.
2. **Unverified MMU Mapping**:
   - Until `SCTLR_EL1.M`, `TCR_EL1`, and `TTBR0_EL1` are captured, no virtual mapping can be presumed.
   - Physical framebuffer memory cannot be accessed as a virtual pointer.
3. **Physical Hardware Delivery Interface**:
   - Requires physical iBUS adapter and Raspberry Pi Pico 2 / RP2350 interposer running usbliter8.
   - No confirmed working software-only path exists on watchOS 10.6.1.

---

## 7. Link & Load Model

- **Format**: Statically linked flat binary (`DreyzeOS.bin`) stripped from ELF64 (`DreyzeOS.elf`).
- **Relocations**: **0 dynamic or static relocations** (verified via `readelf -r`).
- **Position Independence**: **NON-PIC**. The generated code relies on page-relative `adrp` and absolute link-time symbol addresses.
- **Section Layout**:
  - `0x100000000`: `.text.boot` (entry point `_start` at offset 0, followed by `_exception_vectors_base` aligned to 2048B)
  - `0x1000010c0`: `.text` (compiled C routines)
  - `0x100005000`: `.rodata` (4KB page-aligned, read-only permissions `R__`)
  - `0x100008000`: `.data` (4KB page-aligned, read-write permissions `RW_`)
  - `0x100008038`: `.klog_buffer` (16KB circular kernel log ring buffer)
  - `0x10000c058`: `.bss` (zeroed at entry)
  - `0x1000508d0`: `.stack` (16KB stack, placed strictly **after** `__bss_end` to eliminate BSS clear corruption)
- **ELF Program Headers**: Explicitly partitioned into `text` (`R_E`), `rodata` (`R__`), and `data` (`RW_`), resulting in **0 linker RWX segment warnings**.

---

## 8. Entry ABI & Early Startup Sequence

DreyzeOS implements the following strict startup sequence:

```
[iBoot / Loader Handover]
  x0: Pointer to xnu_arm64_boot_args_t or Apple DeviceTree
  x1: Secondary size parameter
  CurrentEL: Expected EL1 (kernel mode)
  DAIF: Interrupts masked
       │
       ▼
[boot/entry.S: _start]
  1. Save x0 -> x20, x1 -> x21
  2. Read CurrentEL immediately
     ├── If CurrentEL != 1 (e.g. EL0) ──► _unsupported_el_halt (branch loop, no EL1 writes)
     └── If CurrentEL == 1 (EL1) ────────► Proceed safely
  3. Mask interrupts (msr daifset, #0xf)
  4. Setup stack: sp = __stack_top (16-byte aligned)
  5. Clear BSS (__bss_start to __bss_end, does not touch stack)
  6. Install VBAR_EL1 = _exception_vectors_base (2048-byte aligned) + isb
  7. Enable FP/SIMD via CPACR_EL1
  8. Jump to kernel_main(x0, x1, confirmed_el)
```

---

## 9. CPU Register State Expectations & Diagnostics

Stage 0 captures a complete **read-only snapshot** into `boot_cpu_state_t`:

```c
typedef struct {
    uint32_t current_el;
    uint64_t daif;
    uint64_t sctlr_el1;
    uint64_t tcr_el1;
    uint64_t ttbr0_el1;
    uint64_t ttbr1_el1;
    uint64_t mair_el1;
    uint64_t vbar_el1;
    uint64_t cpacr_el1;
    bool     el1_registers_valid;
} boot_cpu_state_t;
```

**Safety Invariant**:
- The kernel **NEVER writes** to `SCTLR_EL1`, `TCR_EL1`, `TTBR0_EL1`, `TTBR1_EL1`, or `MAIR_EL1`.
- The snapshot enables post-handoff determination of whether MMU was on (`SCTLR.M`), whether D-cache was on (`SCTLR.C`), and whether I-cache was on (`SCTLR.I`).

---

## 10. MMU Status

- **Status**: **UNKNOWN / LIKELY identity mapped**, but **UNVERIFIED**.
- **Rule**: Physical addresses cannot be dereferenced as pointers without proven mapping.
- **Enforcement**: Memory dereferencing of the physical framebuffer buffer is **strictly blocked**.

---

## 11. Framebuffer Status

- **Abstraction**: `framebuffer_t` with BGRA32 pixel primitives.
- **Safety Interlock**:
  - `mapping_verified = false` by default.
  - `is_write_allowed = false` by default.
  - `framebuffer_enable_writes(true)` is rejected unless `mapping_verified == true`.
  - `framebuffer_put_pixel`, `framebuffer_fill`, and `framebuffer_draw_rect` perform 64-bit integer overflow protection and drop writes if mapping is unverified.
- **Stage 5 Semantics**:
  - If no video detected: logs `HEADLESS` mode.
  - If video detected: logs `FB_VALIDATED_NOMAP` (metadata valid, mapping unverified, writes hard-locked).
  - Never falsely declares framebuffer "validated" when headless or failed.

---

## 12. UART0 Status

- **Physical Base**: `0x2E500000` (CONFIRMED from DeviceTree).
- **Controller**: Samsung S3C6400 derivative (Apple UART).
- **Timeout Protection**: `uart_putc` contains a 1,000,000-cycle loop limit to prevent permanent CPU hang if UART clock is disabled or hardware is unresponsive.
- **Evidence Level**: Register offsets CONFIRMED; clock state and physical TX line routing are RUNTIME UNKNOWN.

---

## 13. AIC (Apple Interrupt Controller) Status

- **Physical Base**: `0x2D180000` (CONFIRMED from exact ADT artifact `research/ipsw/21U580/nodes_dump.txt`, `/arm-io/aic`, size `0x8000`).
- **AIC timebase**: separate `/arm-io/aic-timebase` node at `0x2D188000`, size `0x1000`.
- **Discrepancy resolution**: `0x2E300000` does not occur in the exact ADT artifacts and is rejected as a stale report value; the HAL remains at `0x2D180000`.
- **Driver Architecture**: Apple AIC2, 1024 IRQ lines, 32 banks.
- **Safety Status**: `aic_init()` masks all 1024 interrupt lines across all 32 banks.
- **Global IRQ State**: CPU IRQ delivery is globally **DISABLED** (`DAIF=0xF`).
- **No Interrupt Enabling**: `arch_irq_enable()` is **NEVER** called during boot.

---

## 14. Recovery Limitations

- **Expected Hardware Reset**: Holding Digital Crown + Side Button for 10–15 seconds triggers a PMU hardware reset.
- **Recovery Boundary**:
  - DreyzeOS is entirely freestanding and executes out of volatile RAM.
  - It contains **zero routines to write, erase, or modify NAND/NOR flash**.
  - However, hardware reset behavior from an unverified execution state has not yet been experimentally confirmed on this target.
  - Therefore, reset is documented as the **expected recovery path**, NOT a guaranteed recovery mechanism.

---

## 15. RAM Delivery Research Status

- **Firmware**: watchOS 10.6.1 (21U580).
- **Software Jailbreak / kexec**: **NONE** exists publicly for this version.
- **Hardware Exploit (usbliter8)**:
  - Exploits USB buffer underflow in SecureROM DWC2 stack on Apple S4 (T8006).
  - Requires physical connection to the diagnostic port via an iBUS S4/S5 adapter or AWRT tool.
  - Requires an external RP2350 / Raspberry Pi Pico 2 microcontroller acting as a USB host controller interposer.
  - Status for Watch4,2: **THEORETICAL**. No confirmed turnkey deployment script exists for this exact board configuration.

---

## 16. Conditions Required Before First Hardware Execution

Execution on real hardware may only proceed once **ALL** of the following conditions are satisfied:

1. [ ] Hardware load address is confirmed by a working loader or custom shim.
2. [ ] Binary entry point matches loader expectations (or position-independent PIC loader is built).
3. [ ] Handover MMU translation table state is verified.
4. [ ] Physical iBUS diagnostic adapter and RP2350 interposer hardware are built and bench-tested.
5. [ ] UART0 serial output is monitored with an oscilloscope/analyzer to verify baud and clock.
6. [ ] User explicitly authorizes real hardware launch.

---

## 17. First Hardware Test Readiness Gate

| Requirement | Status | Verification / Evidence |
|:---|:---:|:---|
| **Exact RAM load address confirmed** | **BLOCKED** | Placeholder `0x100000000` in linker script |
| **Execution VA/PA mapping** | **BLOCKED** | Loader MMU/translation regime is not identified |
| **Entry point model verified** | **CONFIRMED** | `_start` at image offset 0; delivery entry contract remains UNKNOWN |
| **Loader selected and handoff ABI** | **BLOCKED** | No loader/shim is selected or evidenced; XNU `x0=boot_args` is not a DreyzeOS contract |
| **boot_args / DeviceTree availability** | **UNKNOWN** | Supported parser paths exist, but future loader register/pointer delivery is unproven |
| **MMU/cache state at handoff** | **BLOCKED** | Snapshot is read-only; no loader mapping evidence |
| **Relocation requirements verified** | **BLOCKED** | Non-PIC binary with 0 relocations |
| **CurrentEL validation before EL1 writes** | **CONFIRMED** | `entry.S` queries `CurrentEL` before MSR |
| **Stack isolated from BSS clear** | **CONFIRMED** | `.stack` placed strictly after `__bss_end` |
| **Exception vector table installed** | **CONFIRMED** | 2048-byte aligned, `msr vbar_el1` + `isb` |
| **CPU state captured read-only** | **CONFIRMED** | `boot_cpu_state_capture()` does not modify SCTLR/TCR |
| **virt_base truthfulness** | **CONFIRMED** | Real `virt_base` from boot_args, no phys_base proxy |
| **DeviceTree recursion/overflow safety** | **CONFIRMED** | Max depth 32, fuzz tested |
| **UART timeout protection** | **CONFIRMED** | Cycle timeout in TX loop |
| **Interrupts disabled** | **CONFIRMED** | DAIF=0xF, all 1024 AIC lines masked |
| **Framebuffer writes hard-locked** | **CONFIRMED** | `mapping_verified = false` gate |
| **No NAND writes** | **CONFIRMED** | Freestanding, 0 flash write routines |
| **Expected recovery path documented** | **CONFIRMED** | Crown + Side Button expected reset documented |
| **Build provenance recorded** | **CONFIRMED** | Git SHA + canonical branch embedded |

---

### **VERDICT: FIRST HARDWARE EXECUTION = NOT READY (BLOCKED)**

*Reason: Hardware load address, physical-to-virtual entry mapping, and physical RAM delivery exploit on Watch4,2 remain UNCONFIRMED. DreyzeOS must remain in host research mode until these parameters are validated.*

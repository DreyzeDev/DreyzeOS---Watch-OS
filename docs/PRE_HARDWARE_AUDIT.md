# DreyzeOS — Pre-Hardware Boot Audit & Safety Report

**Target**: Apple Watch Series 4 (44mm GPS), Model A1978, Watch4,2 (N131bAP)  
**SoC**: Apple S4 / T8006, AArch64  
**Firmware Baseline**: watchOS 10.6.1 (21U580)  
**Phase**: 4 — Step 2.6: Stable Loader ABI & T8006 Loader Evidence Research
**Canonical Branch**: `master`  
**Phase-Start Baseline Commit**: `c1ed127f244f28ce6b5570c61cb48f024a17a6d6`
**Host Test Status**: 41/41 PASS (Python + Native C Harness; C harness 7/7)
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
| **boot_args ABI Layout** | `virt_base` (+0x08), `phys_base` (+0x10), `video` (+0x28), `devicetree_p` (+0x60) | XNU kernelcache entry point `0xfffffff007b2c070`; not a DreyzeOS loader contract |
| **Pixel Color Format** | `"BBBBBBBBGGGGGGGGRRRRRRRR"` (BGRA32) | Kernelcache read-only string at `0xfffffff00823ea2c` |
| **XNU boot ABI** | XNU kernelcache consumes its own EL/x0 ABI | Kernelcache evidence; not a DreyzeOS loader ABI |
| **DreyzeOS source contract** | DreyzeOS requires privileged EL1 entry | `boot/entry.S`; future loader state remains BLOCKED |
| **Vector Table Alignment** | Must be 2048-byte aligned | ARMv8-A Architectural Reference Manual |
| **Stack Alignment** | Must be 16-byte aligned | AAPCS64 (ARM 64-bit Procedure Call Standard) |

---

## 4. Research Patterns (Not T8006 Evidence)

| Pattern | Basis | Status |
|:---|:---|:---|
| **iBoot Flat/Identity Mapping** | Common bootloader pattern only | **UNKNOWN/BLOCKED**; no T8006 evidence |
| **Caches Enabled by Loader** | Common bootloader pattern only | **UNKNOWN**; no T8006 evidence |
| **x1 Register Semantic** | Varies by boot ABI | **UNKNOWN/BLOCKED**; never interpreted without descriptor proof |
| **UART0 Baud Rate = 115200** | Common serial-console convention | **UNKNOWN** on T8006 |

---

## 5. Unknown Facts (Must NOT Be Assumed)

| Unknown | Description | Mitigation in DreyzeOS |
|:---|:---|:---|
| **Exact RAM Handover Address** | Address where loader deposits DreyzeOS.bin | `DREYZEOS_LOAD_BASE = 0x100000000` marked as PLACEHOLDER / BLOCKED |
| **Physical TX Routing on Connector** | Which of the 5 pins in the iBUS slot carries UART0 TX | Logic analyzer probe required; no hardware write assumed |
| **usbliter8 S4 Exploit Reliability** | Whether USB DWC2 buffer underflow triggers cleanly on Watch4,2 | **UNKNOWN/BLOCKED**; exploit not run |
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
[DreyzeOS Loader Handover — BLOCKED/UNKNOWN]
  EL1 entry: mandatory contract, not detected from EL0
  x0/x1, SP, DAIF, MMU, TTBR, caches: loader must prove these
       │
       ▼
[boot/entry.S: _start]
  1. Save x0 -> x20, x1 -> x21
  2. Read CurrentEL under the prior EL1 contract
     ├── EL2/EL3 ──► _unsupported_el_halt (branch loop)
     └── EL1 ──────► Proceed safely
     EL0: MRS CurrentEL is UNDEFINED; this path is not an EL0 detector
  3. Mask interrupts (msr daifset, #0xf)
  4. Setup stack: sp = __stack_top (16-byte aligned)
  5. Clear BSS (__bss_start to __bss_end, does not touch stack)
  6. Install VBAR_EL1 = _exception_vectors_base (2048-byte aligned) + isb
  7. Enable FP/SIMD via CPACR_EL1
  8. Jump to kernel_main(x0, x1, confirmed_el)
```

Production boot metadata behavior is deliberately conservative: `kernel_main`
passes raw x0/x1 to `platform_boot_info_init`, which records them in the single
loader handoff descriptor but performs no pointer dereference or ADT scan while
that descriptor is unverified. Stage 2 is therefore `HANDOFF_UNAVAILABLE` /
`BOOT_METADATA_FALLBACK`, not a claim that boot_args or DeviceTree was validated.
Any future verified path must provide an explicit top-level range; no `0x100000`,
`0x200000`, or `0x80000` size estimate is permitted. The nested
`boot_args->devicetree_p` pointer must be fully contained in a separate verified
readable range, including overflow-safe start and end checks.

---

## 9. CPU Register State Expectations & Diagnostics

Stage 0 captures a **read-only post-entry snapshot** into `boot_cpu_state_t`:

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
- `SCTLR_EL1`, `TCR_EL1`, `TTBR0_EL1`, and `MAIR_EL1` are inherited/unmodified values.
- `DAIF`, `VBAR_EL1`, and `CPACR_EL1` are post-entry DreyzeOS values: entry.S masked DAIF, installed VBAR, and enabled FP/SIMD before capture. Their incoming values are UNKNOWN.
- The snapshot enables post-entry determination of MMU/cache bits, not proof of the loader's complete original CPU state.

---

## 10. MMU Status

- **Status**: **UNKNOWN/BLOCKED**; identity mapping is not assumed.
- **Rule**: Physical addresses cannot be dereferenced as pointers without proven mapping.
- **Enforcement**: Memory dereferencing of the physical framebuffer buffer is **strictly blocked**.
- **Precise interpretation**: inherited `SCTLR_EL1`, `TCR_EL1`, `TTBR0_EL1`, `TTBR1_EL1`, and `MAIR_EL1` values are readable only after valid EL1 entry; those values alone do not prove that DreyzeOS virtual addresses or MMIO ranges are mapped.

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
- **Safety Status**: current pre-hardware path leaves AIC MMIO, CONFIG, and mask banks untouched because the mapping gate is false. The fact that the AIC has 1024 lines is confirmed, but their live mask state is UNKNOWN. `aic_init()` would mask all lines only after a future verified-MMIO gate opens.
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
  - Status for Watch4,2: **UNKNOWN/BLOCKED**. Public T8006-related code exists, but no confirmed turnkey DreyzeOS deployment contract exists for this exact board configuration.

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
| **MMU/cache state at handoff** | **UNKNOWN/BLOCKED** | Inherited-register snapshot is read-only; no loader mapping evidence |
| **Relocation requirements verified** | **BLOCKED** | Non-PIC binary with 0 relocations |
| **EL1 loader entry contract** | **BLOCKED** | Source requires EL1; CurrentEL cannot safely detect EL0 |
| **MMIO mapping gate** | **CONFIRMED** | Defaults false; UART/AIC are untouched without verified mapping |
| **Stack isolated from BSS clear** | **CONFIRMED** | `.stack` placed strictly after `__bss_end` |
| **Exception vector table installed** | **CONFIRMED** | 2048-byte aligned, `msr vbar_el1` + `isb` |
| **CPU state captured read-only** | **CONFIRMED** | `boot_cpu_state_capture()` does not modify inherited SCTLR/TCR/TTBR/MAIR; DAIF/VBAR/CPACR are explicitly post-entry |
| **virt_base truthfulness** | **CONFIRMED** | Real `virt_base` from boot_args, no phys_base proxy |
| **DeviceTree recursion/overflow safety** | **CONFIRMED** | Max depth 32, fuzz tested; future handoff ranges add overflow-safe pointer containment |
| **UART timeout protection** | **CONFIRMED** | Cycle timeout in TX loop |
| **CPU interrupt delivery disabled** | **CONFIRMED** | DAIF=0xF after entry.S; AIC line mask state remains UNKNOWN because MMIO is untouched |
| **Framebuffer writes hard-locked** | **CONFIRMED** | `mapping_verified = false` gate |
| **No NAND writes** | **CONFIRMED** | Freestanding, 0 flash write routines |
| **Expected recovery path documented** | **CONFIRMED** | Crown + Side Button expected reset documented |
| **Build provenance recorded** | **CONFIRMED** | Git SHA + canonical branch embedded |

## 18. DreyzeOS Loader ABI — DESIGN / NOT YET HARDWARE VERIFIED

The project now has a host-testable descriptor design, but no real loader or
shim implements it. The descriptor is intended to become the DreyzeOS-owned
handoff ABI (`x0 -> loader_handoff_descriptor_t`) and to translate any
XNU/iBoot-specific inputs before the kernel parses metadata.

| Area | Design representation | Evidence status |
|:---|:---|:---:|
| Descriptor identity | magic, version, size, explicit verified flag | **DESIGN** |
| Payload placement | payload PA, execution VA, size, explicit known bit | **DESIGN** |
| Entry state | EL plus known bit; CPU fields are not inferred | **DESIGN** |
| MMU state | enabled plus known bit; no mapping implied | **DESIGN** |
| boot_args | verified readable range containing the complete object | **DESIGN** |
| DeviceTree | separate verified readable range containing the complete nested object | **DESIGN** |
| Raw x0/x1 | retained for diagnostics only when unverified | **DESIGN** |
| MMIO mappings | separate MMIO/UART/AIC facts | **DESIGN** |
| Payload physical destination | no T8006 loader/shim evidence | **UNKNOWN** |
| Payload execution VA | current `0x100000000` is a linker placeholder | **BLOCKED** |
| Safe maximum payload size | overlap with loader/ADT/framebuffer/reserved RAM unknown | **UNKNOWN** |
| Identity vs non-identity mapping | not established | **UNKNOWN/BLOCKED** |

The fixed V1 wire object is exactly 128 bytes. Its offsets are `magic 0x00`,
`version 0x08`, `size 0x0C`, `flags 0x10`, `entry_el 0x18`, `payload_pa
0x20`, `payload_va 0x28`, `payload_size 0x30`, `mmu_enabled 0x38`, `raw_x0
0x40`, `raw_x1 0x48`, `boot_args_range 0x50`, and `device_tree_range 0x68`.
Each range is 24 bytes: `base u64`, `length u64`, `flags u32`, `reserved u32`.
V1 validation requires the magic, version, `size >= 128`, known flags, zero
reserved fields, and a boolean-valued MMU field. A larger size is accepted but
the unknown tail is ignored. The `VERIFIED` flag is only an assertion from an
already-trusted bootstrap; it is not a root of trust, signature, or proof that
the descriptor pointer is readable. Range conversion and full-object
containment are checked before every host parser copy or scan.

The range helpers reject zero-length or unreadable ranges, addition overflow,
`UINTPTR_MAX` wraparound, outside pointers, and partial overlaps. Exact-end
containment is accepted only when the complete non-empty object fits. A boolean
such as “nested pointer verified” is intentionally not part of the parser API.

Research references are architectural context only: [m1n1](https://github.com/AsahiLinux/m1n1)
documents explicit payload chaining on Apple Silicon, and
[PongoOS](https://github.com/checkra1n/PongoOS) documents a pre-boot AArch64
environment. These sources do not establish a Watch4,2/T8006 load PA, VA,
entry state, or MMU mapping and are not treated as such.

See the evidence matrix and unresolved T8006 loader questions in
[docs/T8006_LOADER_RESEARCH.md](T8006_LOADER_RESEARCH.md).

---

### **VERDICT: FIRST HARDWARE EXECUTION = NOT READY (BLOCKED)**

*Reason: Hardware load address, physical-to-virtual entry mapping, and physical RAM delivery exploit on Watch4,2 remain UNCONFIRMED. DreyzeOS must remain in host research mode until these parameters are validated.*

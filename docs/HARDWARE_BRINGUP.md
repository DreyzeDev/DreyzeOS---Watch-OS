# DreyzeOS — Hardware Bring-up Guide

**Target**: Apple Watch Series 4 (44mm GPS), Model A1978, Watch4,2 (N131bAP)  
**SoC**: Apple S4 / T8006, AArch64  
**watchOS**: 10.6.1 (21U580)  
**Phase**: 4 — Step 2.4: Handoff Pointer Safety & Boot-Argument Trust Boundary
**Status**: Pre-hardware (host-side validation complete, real device test BLOCKED)

---

## ⚠️ Safety Rules — Non-Negotiable

> [!CAUTION]
> **Do NOT write to flash/NAND.** DreyzeOS is RAM-only. Any flash write is a brick risk.
>
> **Do NOT connect the Apple Watch to automated flashing tools without explicit user approval.**
>
> **Do NOT perform any hardware test without reading this entire document and PRE_HARDWARE_AUDIT.md first.**

- All addresses marked **CONFIRMED** are verified from kernelcache disassembly or DeviceTree binary.
- Addresses marked **LIKELY** are architecturally reasonable but unverified on real hardware.
- Addresses marked **UNKNOWN** must not be used in code until confirmed.
- Addresses marked **BLOCKED** represent hardware-critical missing parameters that prevent safe execution.
- The MMU state at kernel entry is **LIKELY identity mapping** — physical framebuffer address **cannot** be blindly dereferenced as a virtual address until confirmed.

---

## 1. Hardware Delivery Blockers

Before DreyzeOS can be safely executed on real hardware, the following blockers must be resolved:

| Property | Value | Evidence | Status |
|:---|:---:|:---|:---:|
| **RAM payload load address** | `0x100000000` | Linker placeholder (4GB boundary) | **BLOCKED** |
| **Physical RAM base (DRAM)** | `0x800000000` | DeviceTree `/memory` node | **CONFIRMED** |
| **Virtual entry address** | UNKNOWN | iBoot entry mapping unverified | **BLOCKED** |
| **Identity mapping at handoff** | UNKNOWN / LIKELY | iBoot flat-map convention | **LIKELY ONLY** |
| **Relocation requirements** | Static / non-PIC | Statically linked at `0x100000000` (0 relocs) | **BLOCKED** |
| **Delivery vector (usbliter8)** | THEORETICAL | BootROM USB DWC2 buffer underflow (requires RP2350 + iBUS) | **THEORETICAL** |
| **Diagnostic UART physical pin** | UNKNOWN | iBUS 5-pin connector TX line | **UNKNOWN** |

> [!IMPORTANT]
> The current load address `0x100000000` in `DreyzeOS.ld` is a placeholder. Loading the binary at any arbitrary physical address without matching link-time VMA will cause faults on absolute address references. Real hardware execution remains **BLOCKED**.

---

## 2. Boot Stage Progression

DreyzeOS enforces a strictly monotonic boot stage machine:

| Stage | Name | What Happens |
|:---:|:---|:---|
| 0 | `BOOT_STAGE_ENTRY` | C entry reached under the mandatory EL1 loader contract; read-only CPU state captured |
| 1 | `BOOT_STAGE_RAM_LOG` | RAM logger initialized; UART MMIO remains disabled unless mapping is verified |
| 2 | `BOOT_STAGE_BOOT_ARGS` | Boot metadata status recorded; unverified handoff uses `BOOT_METADATA_FALLBACK` |
| 3 | `BOOT_STAGE_MEM_MAP` | DRAM non-zero check passed, memory map validated |
| 4 | `BOOT_STAGE_AIC` | AIC evaluated; no MMIO access or CONFIG write without verified mapping |
| 5 | `BOOT_STAGE_FB` | Framebuffer evaluated (HEADLESS vs VALIDATED_NOMAP, writes **hard-locked**) |
| 6 | `BOOT_STAGE_IDLE` | Branch-loop halt — no IRQs, no MMIO, no FB writes, no NAND access |

`BOOT_STAGE_ERROR = 0xFF` — set by `boot_stage_failsafe()`.
- Backward stage transitions trigger immediate failsafe.
- `g_last_successful_stage` is preserved separately from `g_current_stage = ERROR`.
- Before RAM logging, failsafe enters a branch loop silently. After RAM logging, diagnostics go to RAM; UART readiness is separate from boot stages.

---

## 3. XNU ABI vs. DreyzeOS Loader ABI

### XNU ABI — Confirmed for the researched kernelcache only

| Item | Value / Status |
|:---|:---:|
| Exception Level on entry | XNU handoff evidence only; it does **not** prove DreyzeOS loader entry EL |
| `x0` = pointer to `xnu_arm64_boot_args_t` | **CONFIRMED** (kernelcache entry `0xfffffff007b2c070`) |
| `x1` = size or unused | **LIKELY** for XNU; not a DreyzeOS loader contract |
| DAIF: IRQs disabled on entry | DreyzeOS masks DAIF after its EL1 contract is met |
| VBAR_EL1 = DreyzeOS exception vectors | **CONFIRMED** (installed in `boot/entry.S`, verified by readback) |
| Stack initialized before `kernel_main` | **CONFIRMED** (entry.S, outside BSS, 16-byte aligned) |
| BSS zeroed before `kernel_main` | **CONFIRMED** (entry.S, does not touch stack) |

### DreyzeOS loader ABI — UNKNOWN/BLOCKED

The future loader must explicitly prove EL1 entry, x0/x1 semantics, stack state,
DAIF, MMU/TTBR/cache state, payload VA/PA, and DeviceTree/boot_args delivery.
`MRS CurrentEL` is UNDEFINED at EL0, so it cannot be used as a universal EL0 detector.

### Handoff pointer trust boundary

The production `platform_boot_info_init(x0, x1)` path preserves raw x0/x1 for
RAM diagnostics and selects static fallback metadata. It does not dereference
either value, auto-detect an ABI, or guess an ADT size. `loader_handoff_verified`
therefore remains false until a future loader verifier proves both pointer
ownership and bounded lengths. A `boot_args->devicetree_p` value is a separate
trust boundary and requires its own independently verified pointer and length.

### Unconfirmed — Do NOT Assume

| Item | Status | Risk if Wrong |
|:---|:---:|:---|
| MMU: identity mapping (phys == virt) | **LIKELY** | Physical framebuffer dereference crashes/corrupts |
| Caches: enabled on entry | **LIKELY** | Cache coherency issues if assumption wrong |
| Framebuffer physical dereference as virtual | **BLOCKED** | Hardware hang / invalid memory access |

### `boot_args` Structure (CONFIRMED, from kernelcache disassembly)

```c
typedef struct {
    uint16_t revision;              // +0x00
    uint16_t version;               // +0x02
    uint32_t _pad0;                 // +0x04
    uint64_t virt_base;             // +0x08 — virtual base address (REAL, never proxied)
    uint64_t phys_base;             // +0x10 — physical DRAM base
    uint64_t mem_size;              // +0x18 — total memory size
    uint64_t top_of_kernel_data;    // +0x20
    boot_video_t video;             // +0x28 — 6 × uint64 (baseAddr, display, rowBytes, width, height, depth)
    uint32_t machine_type;          // +0x58
    uint32_t _pad1;                 // +0x5C
    uint64_t devicetree_p;          // +0x60 — physical/virt address of ADT
    uint32_t devicetree_length;     // +0x68 — byte length of ADT
    char command_line[1024];        // +0x6C — boot argument string
} xnu_arm64_boot_args_t;
```

---

## 4. Hardware Required for RAM Delivery

> [!IMPORTANT]
> No software-only jailbreak or kexec exists for watchOS 10.6.1. Hardware access is required.

### Option A — usbliter8 (Hardware BootROM Exploit)

- **Exploit**: DWC2 USB buffer underflow in T8006/T8010 SecureROM
- **Hardware**: RP2350 / Raspberry Pi Pico 2 acting as USB host interposer
- **Adapter**: iBUS S4/S5 adapter (5-pin diagnostic connector in Watch band slot)
- **Status**: **THEORETICAL** for this configuration. No publicly confirmed working tool for Watch4,2 + watchOS 10.6.1.
- **Requirement**: Physical iBUS/AWRT adapter + Pico 2 interposer hardware build

### Physical Connector

- 5-pin diagnostic port in the Watch band slot (proprietary Apple iBUS)
- Requires: iBUS S4/S5 adapter **or** AWRT Apple Watch Research Tool adapter
- DFU mode is triggered through adapter pin pull-down

---

## 5. Recovery Path & Safety Boundaries

> [!WARNING]
> **Crown + Side Button reset is the expected stock hardware reset path, but recovery from an arbitrary experimental execution state has not yet been validated by a controlled DreyzeOS hardware test.**
>
> Holding Crown + Side Button for 10–15 seconds triggers a PMU hard reset, which causes iBoot to reboot the device from stock watchOS on NAND.
>
> RAM-only execution significantly reduces persistent-write risk because DreyzeOS makes zero NAND writes, but it does NOT constitute proof of zero risk under all failure conditions.

---

## 6. Framebuffer Safety Interlock

The framebuffer subsystem features a **two-level safety interlock**:

1. **Mapping Gate (`mapping_verified`)**:
   - `mapping_verified = false` by default.
   - `framebuffer_enable_writes(true)` is strictly REJECTED if `mapping_verified != true`.
   - `framebuffer_put_pixel` drops writes silently unless mapping is verified.
2. **Compile-Time Switch (`DREYZE_FB_TEST_PATTERN`)**:
   - Set to `0` by default.
   - Even when `1`, writes remain blocked because `mapping_verified == false`.

```
[WRITE ATTEMPT]
       │
       ▼
is_configured? ──(No)──► BLOCKED
       │ (Yes)
       ▼
mapping_verified? ──(No)──► BLOCKED (Hardware writes HARD-LOCKED)
       │ (Yes)
       ▼
is_write_allowed? ──(No)──► BLOCKED
       │ (Yes)
       ▼
Bounds / overflow check passed? ──(No)──► BLOCKED
       │ (Yes)
       ▼
[WRITE TO FRAMEBUFFER PIXEL]
```

---

## 7. Known Unknowns

| Unknown | Impact | Resolution Path |
|:---|:---|:---|
| RAM delivery load address | Image cannot be loaded at fixed 0x100000000 | Confirm loader deposit address or implement PIC |
| MMU translation table state | Cannot dereference physical FB address | Read SCTLR_EL1.M, TCR_EL1, TTBR0_EL1 on entry |
| Caches enabled/disabled on entry | Cache coherency for MMIO/framebuffer | Read SCTLR_EL1 (C and I bits) at Stage 0 |
| UART0 baud rate on T8006 | May differ from 115200 | Verify against iBoot clock-frequency node |
| usbliter8 exploit reliability on Watch4,2 | May not trigger reliably | Requires hardware experimentation |
| x1 register value from iBoot | Unclear if size or pointer | Captured at Stage 0 and logged |
| Diagnostic connector pinout | TX pin location unknown | Measure with logic analyzer/oscilloscope |

---

## 8. First Hardware Test Readiness Gate

| Requirement | Status | Evidence |
|:---|:---:|:---|
| Exact RAM load address known | **BLOCKED** | `0x100000000` is placeholder |
| Entry point model known | **CONFIRMED** | `_start` at image byte 0 |
| Relocation requirements known | **BLOCKED** | Statically linked at placeholder address |
| Entry EL handled | **CONFIRMED** | `CurrentEL` checked, EL1 required |
| Stack valid & isolated | **CONFIRMED** | 16-byte aligned, placed outside BSS |
| VBAR_EL1 installed | **CONFIRMED** | 2048-byte aligned, set in entry.S |
| MMU state safely handled | **CONFIRMED** | Read-only capture, physical deref blocked |
| Loader -> DreyzeOS handoff ABI | **BLOCKED** | No loader/shim selected; XNU `x0=boot_args` is not sufficient evidence |
| boot_args / DeviceTree availability | **UNKNOWN** | Parser supports both forms, but future loader delivery is unproven |
| DeviceTree bounds-checked | **CONFIRMED** | Recursion limit 32, fuzz tested |
| UART timeout safe | **CONFIRMED** | Non-blocking loop with cycle limit |
| IRQ delivery disabled | **CONFIRMED** | DAIF=0xF after entry.S; AIC MMIO/configuration remains untouched and unknown |
| Framebuffer writes hard-locked | **CONFIRMED** | `mapping_verified = false` gate |
| No NAND writes | **CONFIRMED** | Freestanding, 0 flash write routines |
| Recovery path documented | **CONFIRMED** | Expected path documented, no false claims |
| Build provenance recorded | **CONFIRMED** | Git SHA + canonical branch embedded |

**FIRST HARDWARE EXECUTION: NOT READY**  
*(Execution on real Apple Watch remains BLOCKED until RAM load address and physical delivery vector are confirmed).*

---

*Last updated: Phase 4 Step 2.4 — handoff pointer safety. Build: ELF=PASS BIN=PASS; hardware execution remains blocked.*

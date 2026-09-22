# DreyzeOS — Hardware Bring-up Guide

**Target**: Apple Watch Series 4 (44mm GPS), Model A1978, Watch4,2 (N131bAP)  
**SoC**: Apple S4 / T8006, AArch64  
**watchOS**: 10.6.1 (21U580)  
**Phase**: 4 — Step 2.8: T8006 Loader Evidence / Documentation Truth Audit
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
- The MMU state at kernel entry is **UNKNOWN/BLOCKED** — physical framebuffer address **cannot** be blindly dereferenced as a virtual address until confirmed.

---

## 1. Hardware Delivery Blockers

Before DreyzeOS can be safely executed on real hardware, the following blockers must be resolved:

| Property | Value | Evidence | Status |
|:---|:---:|:---|:---:|
| **RAM payload load address** | `0x100000000` | Linker placeholder (4GB boundary) | **BLOCKED** |
| **Physical RAM base (DRAM)** | UNKNOWN/BLOCKED | Static `/memory` is `base=0,size=0`; no live map | **UNKNOWN/BLOCKED** |
| **Virtual entry address** | UNKNOWN | iBoot entry mapping unverified | **BLOCKED** |
| **Identity mapping at handoff** | UNKNOWN / BLOCKED | No T8006 loader evidence proves a flat map | **UNKNOWN/BLOCKED** |
| **Relocation requirements** | Static / non-PIC | Statically linked at `0x100000000` (0 relocs) | **BLOCKED** |
| **Delivery vector (usbliter8)** | Public T8006-related research exists; exact Watch4,2 path unresolved | BootROM USB DWC2 research, requires external hardware | **UNKNOWN/BLOCKED** |
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
| 3 | `BOOT_STAGE_MEM_MAP` | Memory metadata status evaluated; static fallback is never called a validated runtime map |
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
either value, auto-detect an ABI, or guess an ADT size. A single loader handoff
descriptor is the authoritative trust state; its verified ranges must prove
pointer ownership and bounded lengths. A `boot_args->devicetree_p` value is a
separate trust boundary and requires its own independently verified range.

### DreyzeOS Loader ABI — DESIGN / NOT YET HARDWARE VERIFIED

This is a host-testable ABI design, not a hardware contract:

| Descriptor fact | Representation | Status |
|:---|:---|:---:|
| Descriptor identity | magic, version, size, verified flag | **DESIGN** |
| Raw legacy inputs | `raw_x0`, `raw_x1` retained as diagnostics | **DESIGN** |
| Payload placement | physical address, execution VA, size, explicit known bit | **DESIGN** |
| Entry state | entry EL with explicit known bit | **DESIGN** |
| MMU state | `mmu_enabled` plus `mmu_state_known` | **DESIGN** |
| boot_args buffer | concrete readable `[base, base + length)` range | **DESIGN** |
| DeviceTree buffer | independent concrete readable range | **DESIGN** |
| MMIO mappings | mapping-state-known bit plus general MMIO and UART/AIC validity bits | **DESIGN** |
| T8006 loader implementation | no loader/shim selected or executed | **UNKNOWN/BLOCKED** |

#### Stable wire ABI V1

The externally visible ABI is fixed-width and exactly 128 bytes. It contains no
`bool`, `size_t`, or `uintptr_t`; those types are used only by the internal
native conversion helpers. `offsetof()` and `_Static_assert` enforce the
following layout at compile time:

| Offset | Field | Width |
|---:|---|---:|
| `0x00` | `magic` | `u64` |
| `0x08` | `version` | `u32` |
| `0x0C` | `size` | `u32` |
| `0x10` | `flags` (verified, EL, payload, MMU, MMIO/UART/AIC facts) | `u64` |
| `0x18` | `entry_el` | `u32` |
| `0x1C` | `reserved0` | `u32` |
| `0x20` | `payload_pa` | `u64` |
| `0x28` | `payload_va` | `u64` |
| `0x30` | `payload_size` | `u64` |
| `0x38` | `mmu_enabled` | `u32` |
| `0x3C` | `reserved1` | `u32` |
| `0x40` | `raw_x0` | `u64` |
| `0x48` | `raw_x1` | `u64` |
| `0x50` | `boot_args_range` (`base u64`, `length u64`, `flags u32`, `reserved u32`) | `24` |
| `0x68` | `device_tree_range` (`base u64`, `length u64`, `flags u32`, `reserved u32`) | `24` |

Validation rules are: exact magic, supported version V1, `size >= 128`, no
unknown V1 flags, zero reserved fields, and `mmu_enabled` equal to 0 or 1.
Known entry EL must be EL1; known payload PA/VA ranges must be non-zero,
non-empty, and non-wrapping. MMIO/UART/AIC validity bits require
`MAPPING_STATE_KNOWN`; UART/AIC additionally require general MMIO validity.
These are structural consistency rules, not hardware proofs. An oversized
descriptor is accepted for forward compatibility, but V1 ignores its tail.
Range conversion separately rejects non-readable, zero-length, overflowing,
non-representable, or otherwise invalid ranges. The `VERIFIED` bit is not a
cryptographic root of trust: the memory containing the descriptor must already
be readable under the loader's contract. A real bootstrap must prove the
descriptor prefix, copy it into kernel-owned memory, and only then use
independently validated ranges. The current production path does none of this;
the setter is host-test-only.

`verified_range_contains_object()` rejects zero-length objects, unreadable
ranges, overflow, outside pointers, and partial overlap. Exact-end containment
is accepted only when the complete non-empty object fits. A non-zero address is
never treated as proof of safety.

The intended architecture is `x0 -> loader_handoff_descriptor_t`; a future
loader translates any XNU/iBoot-specific inputs into this DreyzeOS-owned
descriptor. The current kernel does not consume such a hardware descriptor and
does not implement a loader.

Cross-project references are architectural context only, not T8006 evidence:
[m1n1 payload documentation](https://github.com/AsahiLinux/m1n1) describes
explicit payload chaining, while [PongoOS](https://github.com/checkra1n/PongoOS)
documents a pre-boot AArch64 environment. Neither proves DreyzeOS load PA/VA,
entry state, or MMU mappings on Watch4,2.

The complete public-evidence matrix, including the T8006-specific closest
primitive and PIC stage-0 analysis, is maintained in
[T8006_LOADER_RESEARCH.md](T8006_LOADER_RESEARCH.md).

### Unconfirmed — Do NOT Assume

| Item | Status | Risk if Wrong |
|:---|:---:|:---|
| MMU: identity mapping (phys == virt) | **UNKNOWN/BLOCKED** | Physical framebuffer dereference crashes/corrupts |
| Caches: enabled on entry | **UNKNOWN** | Cache coherency issues if assumption wrong |
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
    uint64_t devicetree_p;          // +0x60 — XNU-consumed ADT address; domain at DreyzeOS handoff UNKNOWN
    uint32_t devicetree_length;     // +0x68 — byte length of ADT
    char command_line[1024];        // +0x6C — boot argument string
} xnu_arm64_boot_args_t;
```

---

## 4. Candidate Hardware Paths for RAM Delivery

> [!IMPORTANT]
> The reviewed public evidence does not establish a project-specific software-only/kexec path. This is an evidence gap, not proof that hardware is the only possible path.

### Option A — usbliter8 (Candidate T8006 Research Path)

- **Exploit**: DWC2 USB buffer underflow in T8006/T8010 SecureROM
- **Public setup described by the repository**: RP2350 / Raspberry Pi Pico 2 acting as a USB host interposer
- **Public adapter context**: iBUS S4/S5 adapter (5-pin diagnostic connector in Watch band slot)
- **Status**: **UNKNOWN/BLOCKED** for this configuration. Public T8006-related code exists, but no reproducible Watch4,2 + watchOS 10.6.1 DreyzeOS delivery contract is established.
- **Evidence boundary**: These are candidate research components, not a confirmed mandatory or exclusive DreyzeOS delivery chain.

### Physical Connector

- 5-pin diagnostic port in the Watch band slot (proprietary Apple iBUS)
- Public research references an iBUS S4/S5 adapter **or** AWRT Apple Watch Research Tool adapter; exact Watch4,2 applicability remains UNKNOWN/BLOCKED.
- DFU mode is triggered through adapter pin pull-down

---

## 5. Recovery Path & Safety Boundaries

> [!WARNING]
> **Crown + Side Button reset is the expected stock hardware reset path, but recovery from an arbitrary experimental execution state has not yet been validated by a controlled DreyzeOS hardware test.**
>
> Stock behavior is commonly described as a 10–15 second Crown + Side Button PMU reset; whether it returns an arbitrary experimental state to iBoot/stock watchOS on this target is unverified. Treat recovery as an expected path, not a guarantee.
>
> RAM-only execution significantly reduces persistent-write risk because DreyzeOS makes zero NAND writes, but it does NOT constitute proof of zero risk under all failure conditions.

---

## 6. Framebuffer Safety Interlock

The framebuffer subsystem features a **two-level safety interlock**:

1. **Mapping Gate (`mapping_verified`)**:
   - `mapping_verified = false` by default.
   - A physical framebuffer base is never promoted to `base_vaddr`; a
     concrete virtual base is required before the gate can open.
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
| Dangerous physical dereferences | **CONFIRMED** | Read-only inherited-register capture; framebuffer/MMIO writes and unsafe physical dereferences are gated |
| Actual MMU/TTBR mappings | **UNKNOWN/BLOCKED** | SCTLR/TCR/TTBR/MAIR values alone do not prove a usable mapping |
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

*Last updated: Phase 4 Step 2.8 — T8006 loader evidence/documentation truth audit. Hardware execution remains blocked.*

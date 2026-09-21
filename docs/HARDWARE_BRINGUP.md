# DreyzeOS — Hardware Bring-up Guide

**Target**: Apple Watch Series 4 (44mm GPS), Model A1978, Watch4,2 (N131bAP)  
**SoC**: Apple S4 / T8006, AArch64  
**watchOS**: 10.6.1 (21U580)  
**Phase**: 4 — Step 2: Safe RAM Boot & Hardware Bring-up Preparation  
**Status**: Pre-hardware (host-side validation complete, real device test NOT yet performed)

---

## ⚠️ Safety Rules — Non-Negotiable

> [!CAUTION]
> **Do NOT write to flash/NAND.** DreyzeOS is RAM-only. Any flash write is a brick risk.
>
> **Do NOT connect the Apple Watch to automated flashing tools without explicit user approval.**
>
> **Do NOT perform any hardware test without reading this entire document first.**

- All addresses marked **CONFIRMED** are verified from kernelcache disassembly or DeviceTree binary.
- Addresses marked **LIKELY** are architecturally reasonable but unverified on real hardware.
- Addresses marked **UNKNOWN** must not be used in code until confirmed.
- The MMU state at kernel entry is **LIKELY identity mapping** — physical framebuffer address **cannot** be blindly dereferenced as a virtual address until confirmed.

---

## 1. Boot Stage Progression

DreyzeOS tracks boot milestones through a monotonic stage counter:

| Stage | Name | What Happens |
|:---:|:---|:---|
| 0 | `BOOT_STAGE_ENTRY` | C entry reached, `CurrentEL` read, early boot checklist logged |
| 1 | `BOOT_STAGE_UART` | UART0 at `0x2E500000` initialized, klog active |
| 2 | `BOOT_STAGE_BOOT_ARGS` | `boot_args` / DeviceTree validated, DRAM base & size logged |
| 3 | `BOOT_STAGE_MEM_MAP` | DRAM non-zero check passed, memory map validated |
| 4 | `BOOT_STAGE_AIC` | AIC initialized, all interrupts masked |
| 5 | `BOOT_STAGE_FB` | Framebuffer discovered and validated (writes **disabled**) |
| 6 | `BOOT_STAGE_IDLE` | Safe WFI halt — no IRQs, no FB writes, no NAND access |

`BOOT_STAGE_ERROR = 0xFF` — set by `boot_stage_failsafe()`. Never appears in normal sequence.

`g_last_successful_stage` is a **separate variable** from `g_current_stage`. Failsafe sets `g_current_stage = ERROR` but **preserves** `g_last_successful_stage` for post-mortem diagnostics.

---

## 2. Boot ABI (Handover from iBoot)

### Confirmed Facts

| Item | Value / Status |
|:---|:---:|
| Exception Level on entry | **EL1** — CONFIRMED (ARM64 kernel convention, consistent with XNU kernelcache disasm) |
| `x0` = pointer to `xnu_arm64_boot_args_t` | **CONFIRMED** (kernelcache entry `0xfffffff007b2c070`) |
| `x1` = size or unused | **LIKELY** (iBoot convention, not directly confirmed) |
| DAIF: IRQs disabled on entry | **CONFIRMED** (entry.S + bootloader convention) |
| VBAR_EL1 = DreyzeOS exception vectors | **CONFIRMED** (set in `boot/entry.S`) |
| Stack initialized before `kernel_main` | **CONFIRMED** (entry.S) |
| BSS zeroed before `kernel_main` | **CONFIRMED** (entry.S) |

### Unconfirmed — Do NOT Assume

| Item | Status | Risk if Wrong |
|:---|:---:|:---|
| MMU: identity mapping (phys == virt) | **LIKELY** | Physical framebuffer dereference crashes/corrupts |
| Caches: enabled on entry | **LIKELY** | Cache coherency issues if assumption wrong |
| Framebuffer physical dereference as virtual | **BLOCKED** | Hardware hang / wrong memory access |

### `boot_args` Structure (CONFIRMED, from kernelcache disassembly)

```c
typedef struct {
    uint16_t revision;              // +0x00
    uint16_t version;               // +0x02
    uint32_t _pad0;                 // +0x04
    uint64_t virt_base;             // +0x08 — virtual base address
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

### Pixel Format (CONFIRMED)

`"BBBBBBBBGGGGGGGGRRRRRRRR"` found at kernelcache `0xfffffff00823ea2c` = **BGRA32 LE**:
- Byte 0: Blue, Byte 1: Green, Byte 2: Red, Byte 3: Alpha/X

---

## 3. Hardware Required for RAM Delivery

> [!IMPORTANT]
> No software-only jailbreak or kexec exists for watchOS 10.6.1. Hardware access is required.

### Option A — usbliter8 (Hardware BootROM Exploit)

- **Exploit**: DWC2 USB buffer underflow in T8006/T8010 SecureROM
- **Hardware**: RP2350 / Raspberry Pi Pico 2 acting as USB host interposer
- **Adapter**: iBUS S4/S5 adapter (5-pin diagnostic connector in Watch band slot)
- **Status**: **THEORETICAL** for this configuration. No publicly confirmed working tool for Watch4,2 + watchOS 10.6.1.
- **Requirement**: Physical iBUS/AWRT adapter + Pico 2 interposer hardware build

### Option B — Custom iBoot Payload (Requires Signing Oracle or BootROM Exploit First)

- Not viable without Option A or equivalent

### Physical Connector

- 5-pin diagnostic port in the Watch band slot (proprietary Apple iBUS)
- Requires: iBUS S4/S5 adapter **or** AWRT Apple Watch Research Tool adapter
- This is how DFU mode is accessed programmatically

---

## 4. Execution Path

```
Stock watchOS on NAND
        │
        │  (hardware exploit via usbliter8 over iBUS)
        ▼
BootROM / SecureROM enters DFU
        │
        │  RAM payload delivered over USB
        ▼
iBoot stub (or direct RAM execution)
        │
        │  x0 = boot_args pointer
        │  EL1, DAIF set, VBAR_EL1 = DreyzeOS vectors
        ▼
DreyzeOS kernel_main()
        │
        ├── STAGE 0: CurrentEL verify → EL1 confirmed
        ├── STAGE 1: UART0 init → klog active
        ├── STAGE 2: boot_args parse → DRAM/DeviceTree validated
        ├── STAGE 3: Memory map check → DRAM base/size non-zero
        ├── STAGE 4: AIC init → interrupts masked
        ├── STAGE 5: Framebuffer validated → writes DISABLED
        └── STAGE 6: Safe WFI halt
               │
               │  (if any stage fails → boot_stage_failsafe())
               │       → last successful stage preserved
               │       → FB writes forced off
               │       → IRQs disabled
               │       → infinite WFI
               ▼
        PMU Hard Reset
        (Crown + Side Button, hold 10–15 seconds)
        → Stock watchOS resumes from NAND
```

---

## 5. Recovery Path

> [!WARNING]
> **Crown + Side Button hard reset is the expected hardware reset path.**
>
> Holding Crown + Side Button for 10–15 seconds triggers a PMU hard reset, which causes iBoot to reboot the device from stock watchOS on NAND — since DreyzeOS is RAM-only and makes no NAND changes.
>
> **Actual recovery capability will be confirmed only after a controlled hardware test.**  
> Do not rely on this as a guaranteed recovery mechanism until verified.

Since DreyzeOS **never writes to NAND**, a reset always returns to stock watchOS.

---

## 6. EARLY BOOT Diagnostics Checklist

The following is logged by `kernel_main` before any hardware interaction (UART output via STAGE 1):

```
[BOOT] Early Boot Checklist:
  [OK] Stack initialized                    (entry.S)
  [OK] BSS zeroed                           (entry.S)
  [OK] VBAR_EL1 set to DreyzeOS vectors     (entry.S - CONFIRMED)
  [OK] DAIF: IRQs disabled on entry         (entry.S - CONFIRMED)
  [OK] x0 = boot_args pointer               (CONFIRMED, kernelcache disasm)
  [??] x1 = size or unused                  (LIKELY, not confirmed)
  [??] MMU: identity mapping                (LIKELY - NOT CONFIRMED)
  [??] Caches: enabled                      (LIKELY - NOT CONFIRMED)
  [!!] Physical FB dereference: BLOCKED     (MMU state unverified)
  [!!] Framebuffer writes: DISABLED         (DREYZE_FB_TEST_PATTERN=0)
```

---

## 7. Framebuffer Safety Interlock

The framebuffer safety interlock ensures no accidental hardware writes:

| Setting | Value | Effect |
|:---|:---:|:---|
| `DREYZE_FB_TEST_PATTERN` (compile-time) | `0` | Test pattern call omitted from binary |
| `is_write_allowed` (runtime) | `false` | All `fb_put_pixel` calls silently return |
| `framebuffer_enable_writes(true)` | **NOT called in normal boot** | Hardware pixels never written |

To enable the test pattern for a **future controlled hardware test only**:
```bash
make DREYZE_FB_TEST_PATTERN=1
```
Do **not** do this until MMU mapping is confirmed on real hardware.

---

## 8. Hardware Test Plan (Future — NOT YET EXECUTED)

> [!IMPORTANT]
> The following steps have NOT been performed. They describe the intended future test sequence.

**Pre-conditions:**
- [ ] usbliter8 exploit confirmed working on Watch4,2 + watchOS 10.6.1
- [ ] iBUS S4/S5 or AWRT adapter available
- [ ] RP2350/Pico 2 interposer built and tested
- [ ] Host PC running usbliter8 toolchain

**Step-by-step:**

1. [ ] Put Apple Watch into DFU mode via iBUS adapter
2. [ ] Deliver `DreyzeOS.bin` as RAM payload via usbliter8
3. [ ] Observe UART0 output at 115200 baud (connector pin TBD)
4. [ ] Verify STAGE 0–6 progression in UART log
5. [ ] Verify no NAND writes occurred (stock watchOS still boots after reset)
6. [ ] Verify Crown + Side Button hard reset returns to stock watchOS
7. [ ] **If** STAGE 5 framebuffer address confirmed: rebuild with `DREYZE_FB_TEST_PATTERN=1`
8. [ ] Retest with framebuffer writes enabled — verify display output

**STOP if:**
- Any stage fails to progress → read `boot_stage_failsafe()` output on UART
- UART shows no output → UART0 base address or baud rate assumption wrong
- Device does not reset after Crown + Side Button → escalate, do not retry

---

## 9. Known Unknowns

| Unknown | Impact | Resolution |
|:---|:---|:---|
| MMU identity mapping | Cannot dereference physical FB address | Confirmed only after first UART log shows Stage 5 |
| Caches enabled/disabled on entry | Cache coherency for MMIO | Read SCTLR_EL1 in Stage 0 (future) |
| UART0 baud rate on T8006 | May not be 115200 | Check DeviceTree `clock-frequency` node |
| usbliter8 exploit reliability on Watch4,2 | May not trigger reliably | Requires hardware experimentation |
| x1 register value from iBoot | May be non-zero size or zero | Logged at Stage 0 for future analysis |
| AIC interrupt mapping | Interrupts not yet used | Phase 5+ work |

---

## 10. File Index

| File | Purpose |
|:---|:---|
| `boot/entry.S` | AArch64 entry: stack, BSS, VBAR_EL1, DAIF |
| `kernel/kernel.c` | Boot stage progression (Stage 0–6), failsafe |
| `kernel/boot_stage.c` | Stage tracking, `g_last_successful_stage` |
| `include/boot_stage.h` | `boot_stage_t` enum, API declarations |
| `include/boot_info.h` | `xnu_arm64_boot_args_t`, `platform_boot_info_t` |
| `hal/t8006/uart.c` | UART0 at `0x2E500000` (CONFIRMED) |
| `hal/t8006/aic.c` | AIC driver (all offsets CONFIRMED from kernelcache) |
| `hal/t8006/framebuffer.c` | FB abstraction, safety interlock, BGRA32 |
| `hal/t8006/device_tree.c` | Dual ABI ADT parser |
| `docs/HARDWARE_BRINGUP.md` | This document |

---

*Last updated: Phase 4 Step 2 — All 31 tests PASS. Build: ELF=PASS BIN=PASS. Binary: 39KB.*

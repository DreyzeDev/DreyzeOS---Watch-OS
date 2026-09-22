# DreyzeOS — Research Notes

## T8006 / Apple Watch Series 4 Research Log

**Last updated**: 2026-09-21  
**Phase**: 1 — Research Build

---

## Research Summary

### Peepo — Analysis

**Repository**: https://github.com/datalocaltmp/Peepo  
**Author**: datalocaltmp  
**Purpose**: Kernel read/write primitives for Apple Watch research

#### What it is
Peepo is the **first public kernel-level access tool for watchOS since JelBrekTime (2018)** —
a gap of approximately 8 years. It ports the **DarkSword** exploit chain to watchOS.

#### Exploit Chain
- **Exploit**: DarkSword (CVE-2025-43510, CVE-2025-43520 — XNU kernel memory corruption)
- **Type**: Userspace → Kernel privilege escalation (NOT a bootrom exploit)
- **Method**: Exploits XNU kernel bug to obtain `tfp0` or equivalent kernel R/W primitive
- **NOT persistent**: Requires re-exploitation after every reboot
- **Stability**: Author describes it as "janky" — frequent kernel panics

#### Supported Targets
| Target | Status |
|--------|--------|
| Apple Watch Watch4,1 / T8006 | CONFIRMED in the public project README |
| Apple Watch Watch4,2 / this project target | UNKNOWN/BLOCKED; not claimed or tested by the reviewed README |
| watchOS 10.6.1 | CONFIRMED |
| watchOS 10.6.2 | CONFIRMED |
| Other Watch models (Series 5/6/SE) | LIKELY (same XNU vulnerability) |
| watchOS 11.x | UNKNOWN (likely patched) |

#### What Can Be Extracted Safely
| Data | Extractable? | Risk |
|------|-------------|------|
| Process memory dumps | YES | Low (read-only) |
| Kernel memory (any address) | Public source claims kernel R/W | UNKNOWN/BLOCKED for this target until an authorized run |
| kernelcache from memory | LIKELY | Medium |
| DeviceTree from memory | LIKELY | Medium |
| MMIO register values | Possible through a live kernel VA | UNKNOWN/BLOCKED; no device run performed |
| IOKit device registry | YES | Medium |
| Hardware MMIO base addresses | YES (from IOKit) | Low |

#### Limitations
1. **NOT a permanent jailbreak** — RAM only, reverts on reboot
2. **Frequent panics** — unstable, may need multiple attempts
3. **Version specific** — only watchOS 10.6.1/10.6.2
4. **Secure Enclave** data inaccessible (Health, passcode-protected data)
5. **Cannot permanently modify** watchOS

#### Value for DreyzeOS Project
Peepo is a potentially valuable future research path, but it is not a
DreyzeOS loader and has not been executed in this project:
- With a physical Watch running watchOS 10.6.1/10.6.2, we can:
  - Walk the IOKit registry to find all MMIO base addresses
  - Dump the DeviceTree from kernel memory
  - Verify our memory_map.h values
  - Potentially dump the kernelcache for analysis
- This would provide the "CONFIRMED" data needed for Phases 5-7

Any future, separately authorized research could write a custom Peepo script that:
1. Establishes kernel R/W
2. Finds the IODeviceTree registry root
3. Walks all nodes and extracts `reg` properties (MMIO base + size)
4. Dumps output to a file readable on the Watch's accessible filesystem

---

### PongoOS — Architecture Analysis

**Repository**: https://github.com/checkra1n/PongoOS  
**License**: MIT ✅ (can legally reference/reuse with attribution)

#### Architecture

```
checkm8 (bootrom exploit)
    → PongoOS loaded into DRAM at checkm8's payload area
    → PongoOS _start (entry.S)
        → Stack init
        → BSS clear
        → Exception vector setup
        → MMU setup (identity mapping; PongoOS reference only)
        → DeviceTree location (already in DRAM from iBoot)
        → USB serial init (for pongoterm)
        → pongo_main()
            → Shell loop (reads commands from USB)
            → Module loading (user uploads .bin payloads)
```

#### Key Architectural Insights for DreyzeOS

| Component | PongoOS Approach | DreyzeOS Plan |
|-----------|-----------------|---------------|
| Entry | `_start` in entry.S | Same pattern — ✅ |
| Stack | Static BSS area | Same — ✅ |
| BSS clear | Manual loop in assembly | Same — ✅ |
| Exception vectors | 2KB-aligned, 16 entries | Same — ✅ |
| MMU | Identity mapping + enable (reference pattern only) | Phase 3-4; DreyzeOS/T8006 evidence UNKNOWN/BLOCKED |
| UART | Direct MMIO, chip-detected | Phase 6 (when addr known) |
| DeviceTree | Read from memory (iBoot placed it) | Phase 3-4 |
| Memory mgmt | Bump allocator | Same — Phase 1 ✅ |
| Build output | Raw binary (not ELF/Mach-O) | Same plan |
| Load address | Hardcoded, chip-specific | UNKNOWN_T8006_LOAD_ADDRESS |

#### PongoOS UART Pattern (for reference)
```c
// PongoOS UART pattern (from their driver — MIT licensed):
// #define UART_BASE 0x235200000  // A10 T8010 specific
// volatile uint32_t *reg = (volatile uint32_t *)UART_BASE;
// reg[UTRSTAT/4] → check TX empty
// reg[UTXH/4] = char → write character
```
T8006 UART_BASE: UNKNOWN — must be extracted from DeviceTree.

#### What CAN be Reused from PongoOS (MIT)
1. ARM64 boot assembly patterns (with attribution)
2. Exception vector table structure
3. UART register layout (Samsung S3C-derived — same IP, different base)
4. DeviceTree parsing code (adt.c equivalent)
5. Bump allocator pattern
6. Module loading concept

---

### Boot Chain Research

#### XNU/iBoot Register Convention (CONFIRMED only for the cited XNU path)
Based on the researched XNU source and kernelcache:
- `x0` at kernel entry = physical address of Apple DeviceTree
- `x1` = unclear / unused in some versions
- `sp` = top of initial stack (may be iBoot's own stack)

This is an XNU-specific convention, not a DreyzeOS loader contract. DreyzeOS
saves x0 immediately for diagnostics but does not dereference it while the
handoff descriptor is unverified.

#### KASLR (Kernel Address Space Layout Randomization)
- **CONFIRMED**: watchOS uses KASLR since watchOS 4+
- iBoot randomizes the kernel's virtual base address at each boot
- This makes hardcoded kernel addresses impossible
- PongoOS kpatchfinder (KPF) works around this by pattern-matching opcodes

#### XNU DeviceTree Boot Flow (not a DreyzeOS handoff proof)
```
iBoot:
1. Loads DeviceTree blob (from kernelcache/IPSW)
2. Places it at a determined physical address
3. Sets x0 = physical_address_of_devtree
4. Jumps to kernel entry point

XNU kernel:
1. Receives x0 = devtree_ptr
2. Parses DeviceTree to discover all hardware
3. Initializes IOKit registry from DeviceTree nodes
4. Each device driver finds its MMIO base from devtree `reg` property
```

---

### ARM64_32 vs AArch64 — Critical Differences

This affects how we build DreyzeOS:

| Aspect | AArch64 (DreyzeOS kernel) | ARM64_32 (watchOS userspace) |
|--------|--------------------------|------------------------------|
| Pointer size | 64-bit | 32-bit |
| Register width | 64-bit Xn | 64-bit Xn (truncated ptrs) |
| Stack alignment | 16-byte | 16-byte |
| Function call ABI | AAPCS64 | AAPCS64 with ILP32 |
| Instruction set | AArch64 | AArch64 (same ISA!) |
| Max addressable memory | 2^64 | 2^32 (4 GB) |
| Compiler flag | default aarch64 | `-mabi=ilp32` |

**DreyzeOS kernel must be compiled as standard AArch64** (not ARM64_32).
Any apps running on DreyzeOS would choose their ABI independently.

---

### Similar SoC Reference (A10 / T8010 — for extrapolation only)

> ⚠️ These addresses are for A10 (iPhone 7), NOT T8006 (Apple Watch Series 4).
> Listed for reference only. Do NOT use in T8006 code.

| Peripheral | A10 T8010 Address | T8006 Status |
|-----------|-------------------|--------------|
| UART0 | 0x235200000 | UNKNOWN |
| AIC base | ~0x232000000 | UNKNOWN |
| GPIO | ~0x200F0000 | UNKNOWN |
| PMGR | ~0x231500000 | UNKNOWN |

---

## Phase 4 Execution Path Research

### The Core Question
> Does a viable path exist: Windows PC → Apple Watch Series 4 → RAM execution of DreyzeOS?

### Option Analysis

#### Option A: Peepo-based code injection
- **Requires**: Physical Watch with watchOS 10.6.1/10.6.2
- **Method**: Peepo → kernel R/W → map DreyzeOS code into kernel memory → jump to it
- **Risk**: Medium (kernel panic recoverable via reboot)
- **Completeness**: Partial — runs after watchOS, shares kernel VA space
- **Status**: UNKNOWN/BLOCKED — not confirmed for DreyzeOS specifically
- **Windows path**: Peepo must run FROM the Watch (watchOS app or SSH) — Windows part = prep/build only

#### Option B: T8004 (Series 3) + checkm8 path
- **Requires**: Apple Watch Series 3 (T8004) — DIFFERENT device
- **Method**: checkm8 exploit → PongoOS → bare metal
- **Status**: UNKNOWN/BLOCKED — would need a PongoOS Watch port
- **NOT applicable** to Series 4 (T8006 not checkm8 vulnerable)

#### Option C: iBus + Future BootROM Research
- **Status**: BLOCKED — public usbliter8 T8006-related research exists, but no target-specific DreyzeOS delivery contract or mandatory iBus/RP2350 chain is established
- **Timeline**: Unknown

#### Option D: IPSW DeviceTree + QEMU Emulation
- **Method**: Extract real T8006 DeviceTree from IPSW → build QEMU model → run DreyzeOS in QEMU
- **Status**: DESIGN — QEMU does not currently model T8006
- **Value**: Allows testing kernel code without real hardware
- **Windows path**: Fully possible on WSL2
- **Recommendation**: Pursue this for Phase 5 simulator

---

## Next Research Steps (Phase 3)

1. **Download watchOS IPSW** for watch4,2 (44mm GPS) from ipsw.me
2. **Extract DeviceTree** using img4tool + device_tree_dump.py
3. **Populate HARDWARE.md** with real MMIO addresses from DeviceTree
4. **Update memory_map.h** with confirmed values (replace UNKNOWN_*)
5. **Analyze kernelcache** in Ghidra for additional hardware patterns
6. **If device available**: Run Peepo to get live DeviceTree dump

---

## Key References

| Reference | URL | Relevance |
|-----------|-----|-----------|
| Peepo | https://github.com/datalocaltmp/Peepo | Primary exploit tool for research |
| PongoOS | https://github.com/checkra1n/PongoOS | Architecture reference (MIT) |
| JelBrekTime | https://github.com/tihmstar/JelBrekTime | Historical Watch jailbreak |
| img4tool | https://github.com/tihmstar/img4tool | IPSW/IMG4 extraction |
| devicetree-parse | https://github.com/bazad/devicetree-parse | ADT parser |
| Asahi ADT | https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/m1n1/adt.py | Python ADT parser |
| iFixit teardown | https://www.ifixit.com/Teardown/Apple+Watch+Series+4+Teardown/113044 | Hardware identification |
| Elcomsoft Watch | https://blog.elcomsoft.com/2019/12/checkm8-and-checkra1n-for-apple-watch/ | checkm8 Watch analysis |
| theapplewiki | https://www.theapplewiki.com/ | Apple hardware wiki |
| ipsw.me | https://ipsw.me/ | IPSW downloads |

# DreyzeOS — T8006 Hardware Documentation

## Status Legend

| Tag | Meaning |
|-----|---------|
| **CONFIRMED** | Verified from documentation, teardown, source code, or experiment |
| **LIKELY** | Strongly inferred from related data, not directly confirmed |
| **DESIGN** | Host-side proposal, not hardware evidence |
| **UNKNOWN** | Not yet determined — placeholder used in code |
| **BLOCKED** | Cannot proceed until dependency is resolved |

---

## 1. Device Model Matrix

**Status: CONFIRMED** — Apple product pages, teardowns, GSMArena

| Model ID | Size | Connectivity | Display |
|----------|------|--------------|---------|
| Watch4,1 | 40mm | GPS only | 324 × 394 px, 326 PPI |
| Watch4,2 | 44mm | GPS only | 368 × 448 px, 326 PPI |
| Watch4,3 | 40mm | GPS + Cellular (LTE) | 324 × 394 px, 326 PPI |
| Watch4,4 | 44mm | GPS + Cellular (LTE) | 368 × 448 px, 326 PPI |

All four models share identical SoC, RAM, and storage.  
Differences: case size, cellular modem, display resolution, materials.

---

## 2. Apple S4 SoC — T8006

**Status: CONFIRMED** — Apple teardowns, ipsw.me, theiphonewiki

### 2.1 Identification

| Field | Value | Status |
|-------|-------|--------|
| SoC name | Apple S4 | CONFIRMED |
| Internal chip ID | **T8006** | CONFIRMED |
| Appears in DeviceTree as | `sart-marconi,t8006` | CONFIRMED |
| Used in | Apple Watch Series 4 AND Series 5 | CONFIRMED |
| Die identical to Series 5 | Yes (S5 = same T8006 die) | CONFIRMED |

### 2.2 CPU Configuration

| Field | Value | Status |
|-------|-------|--------|
| Core count | 2 (dual-core) | CONFIRMED |
| Target kernel instruction set | AArch64 | UNKNOWN/BLOCKED — exact 21U580 kernelcache bytes/Mach-O header are absent; see [EV000A static metadata audit](../research/t8006_evidence/EV000A_STATIC_METADATA_AUDIT.md) |
| Target kernel execution mode | AArch64 (full 64-bit) | UNKNOWN/BLOCKED — not established by the currently present package metadata |
| Observed NanoPhotos process ABI | ARM64_32 | CONFIRMED as the IPS cpuType field only; not proof of DreyzeOS loader/kernel architecture |
| DreyzeOS image architecture | AArch64 | CONFIRMED as the project build/ELF target only; not target compatibility evidence |
| Clock frequency | UNKNOWN | UNKNOWN |
| Core type | Likely Tempest/Mistral class (2018 era) | LIKELY |

### 2.3 ARM64_32 (ILP32) Explanation

> The observed ARM64_32 process type is distinct from both ARM64 and ARM32:
> - Uses the **AArch64 (64-bit) instruction set** — NOT Thumb/ARM32 instructions
> - But pointers are **32-bit** (4 bytes, limited to 4GB virtual address space)
> - Registers r0-r30 are 64-bit Xn registers, but addresses are truncated to 32 bits
> - This report does not establish the target kernel's architecture or pointer width.
> - DreyzeOS is built for AArch64, but target execution compatibility remains blocked until exact-target kernel/architecture evidence is available.
> - DreyzeOS apps (if ever built) would use ARM64_32 ABI

### 2.4 Memory

| Field | Value | Status |
|-------|-------|--------|
| RAM total | 1 GB (0x40000000 bytes) | CONFIRMED product quantity only; not a runtime `/memory` map |
| RAM type | LPDDR3 or LPDDR4 | LIKELY |
| RAM physical base | UNKNOWN | UNKNOWN |
| NAND flash | 16 GB | CONFIRMED |

### 2.5 T8006 checkm8 Status

| Field | Value | Status |
|-------|-------|--------|
| checkm8 vulnerable? | **NO** | CONFIRMED |
| Boot ROM research | Public usbliter8 T8006/S4-related code exists; Watch4,2/DreyzeOS applicability is unresolved | UNKNOWN/BLOCKED |
| Related vulnerable Watch | Series 3 (T8004) only | CONFIRMED |

**Source**: checkm8.info, Elcomsoft blog  
> checkm8 affects Apple chips A5–A11 (T8010, T8015, etc.) and Watch T8004 (Series 3).  
> T8006 (Series 4) was released after the checkm8 vulnerability window and is NOT affected.

---

## 3. Boot Chain

**Status: CONFIRMED structure, UNKNOWN addresses**

```
T8006 Boot ROM (SecureROM)
    │  [RSA-4096 + SHA-384 signature verification]
    │  [IMG4 format validation]
    ▼
LLB (Low-Level Bootloader)
    │  [hardware init, power domains]
    │  [verifies iBoot via IMG4]
    ▼
iBoot
    │  [loads DeviceTree, kernelcache, ramdisk]
    │  [applies KASLR slide randomization]
    │  [XNU-specific boot metadata handoff; DreyzeOS semantics unknown]
    ▼
XNU kernel (arm64_32 ABI, AArch64 instructions)
    │
    ▼
launchd → watchOS userspace (ARM64_32)
```

### Boot Registers at Kernel Entry

| Register | Content | Status |
|----------|---------|--------|
| x0 | Physical address of Apple DeviceTree | LIKELY (XNU convention) |
| x1 | Kernel size or unused | UNKNOWN |
| EL level | EL1 (typical) or EL2 | UNKNOWN for T8006 specifically |

### IMG4 Format

| Field | Value | Status |
|-------|-------|--------|
| Container format | ASN.1 DER-encoded | CONFIRMED |
| Compression | LZFSE or LZSS | CONFIRMED |
| Signing | RSA-4096 or ECDSA | CONFIRMED |
| Nonce binding | APTicket / SHSH system | CONFIRMED |
| Downgrade prevention | Yes (epoch-based signing) | CONFIRMED |

---

## 4. Memory Map

**Status: static physical-reg evidence exists for selected MMIO nodes, but
live MMU mappings and the DRAM map remain UNKNOWN/BLOCKED** — Apple does not
publish a T8006 technical reference manual.

```
Physical Address Space — T8006 (generic research sketch, not a live map)
=============================================================
0x0000_0000_0000_0000  Boot ROM / SecureROM         UNKNOWN size/addr
   ...
0x0000_0002_0000_0000  MMIO region START (LIKELY)   UNKNOWN — extrapolated from related SoCs
   ...
0x0000_0008_0000_0000  historical DRAM-base fallback UNKNOWN — not confirmed by static /memory
0x0000_000C_0000_0000  historical 1GB-end sketch     UNKNOWN — not a runtime DRAM boundary
=============================================================

NOTE: The sketch above is not a source for current constants. Static
      DeviceTree evidence is maintained in DEVTREE_REPORT.md; it does not
      prove virtual mappings or live DRAM placement. Do not use the sketch
      for production code.
```

### Known from Teardown (Memory Quantities Only)

| Component | Quantity | Address | Status |
|-----------|----------|---------|--------|
| RAM | 1 GB | UNKNOWN | CONFIRMED qty / UNKNOWN addr |
| NAND | 16 GB | UNKNOWN | CONFIRMED qty / UNKNOWN addr |

### MMIO Peripherals — Address Status

| Peripheral | Base Address | Status |
|-----------|-------------|--------|
| UART0 | 0x2e500000 | CONFIRMED static DeviceTree reg; mapping UNKNOWN |
| Display Controller | 0x18000000 | CONFIRMED static DeviceTree reg; mapping UNKNOWN |
| Framebuffer | Static `/vram` is `0x0+0x0`; runtime value absent | UNKNOWN/BLOCKED |
| Interrupt Controller (AIC) | 0x2d180000 | CONFIRMED static DeviceTree reg; mapping UNKNOWN |
| PMGR (Power Manager) | 0x2d000000 | CONFIRMED static DeviceTree reg; mapping UNKNOWN |
| SPI0 | UNKNOWN_T8006_SPI0_BASE | UNKNOWN |
| SPI1 | UNKNOWN_T8006_SPI1_BASE | UNKNOWN |
| I2C0 | UNKNOWN_T8006_I2C0_BASE | UNKNOWN |
| GPIO | 0x2d300000 | CONFIRMED static DeviceTree reg; mapping UNKNOWN |

---

## 5. Display Subsystem

| Field | Value | Status |
|-------|-------|--------|
| Display type | LTPO OLED | CONFIRMED |
| 44mm resolution | 368 × 448 pixels | CONFIRMED |
| 40mm resolution | 324 × 394 pixels | CONFIRMED |
| PPI | 326 PPI (both sizes) | CONFIRMED |
| Display controller | Apple custom DCP (LIKELY) | LIKELY |
| DCP interface | MIPI-DSI (LIKELY) | LIKELY |
| Framebuffer pixel format | BGRA8888 (LIKELY) | LIKELY |
| Framebuffer base address | Runtime boot metadata if supplied; static `/vram` is zero | UNKNOWN/BLOCKED |
| DCP MMIO base | UNKNOWN | UNKNOWN |

---

## 6. UART

| Field | Value | Status |
|-------|-------|--------|
| UART hardware present? | YES (engineering use) | CONFIRMED |
| Consumer-accessible UART? | No consumer path established; iBUS/diagnostic access is only a candidate research route | UNKNOWN |
| UART IP | Samsung S3C-derived (LIKELY) | LIKELY |
| UART0 base address | 0x2e500000 static DeviceTree value | CONFIRMED static address; runtime mapping UNKNOWN |
| Related SoC reference (A10/T8010) | 0x235200000 | CONFIRMED for A10, NOT T8006 |

---

## 7. Touch Controller

| Field | Value | Status |
|-------|-------|--------|
| Touch IC model | UNKNOWN (possibly Analog Devices AD7166) | LIKELY |
| Communication bus | SPI or I2C | LIKELY |
| Bus address/pin | UNKNOWN | UNKNOWN |
| IRQ GPIO | UNKNOWN | UNKNOWN |

---

## 8. Digital Crown

| Field | Value | Status |
|-------|-------|--------|
| Mechanism type | Optical rotary encoder | CONFIRMED |
| Click button | Mechanical switch | CONFIRMED |
| Interface to SoC | GPIO/serial (LIKELY) | LIKELY |
| GPIO pin | UNKNOWN | UNKNOWN |
| IRQ | UNKNOWN | UNKNOWN |

---

## 9. Side Button

| Field | Value | Status |
|-------|-------|--------|
| Type | Mechanical switch | CONFIRMED |
| Interface | GPIO interrupt | LIKELY |
| GPIO pin | UNKNOWN | UNKNOWN |

---

## 10. Interrupt Controller

| Field | Value | Status |
|-------|-------|--------|
| Type | Apple AIC (Apple Interrupt Controller) | LIKELY |
| NOT GIC? | Correct — Apple uses custom AIC | CONFIRMED for Apple SoCs |
| AIC base address | UNKNOWN | UNKNOWN |
| ARM generic timer | Available through CNTPCT_EL0/CNTFRQ_EL0 | CONFIRMED architectural access |
| ARM timer frequency | Runtime `CNTFRQ_EL0` value | UNKNOWN on T8006; no static 24 MHz confirmation |

---

## 11. Wireless

| Field | Value | Status |
|-------|-------|--------|
| Bluetooth | W3 chip, BT 5.0 | CONFIRMED |
| Wi-Fi | 802.11b/g/n 2.4 GHz (W3) | CONFIRMED |
| Cellular (Watch4,3/4,4) | LTE (Apple custom modem) | CONFIRMED |

---

## 12. DFU Access

| Field | Value | Status |
|-------|-------|--------|
| DFU method | Public documentation describes an iBUS/diagnostic adapter; exact Watch4,2 path unverified | UNKNOWN |
| Port location | Public reports place a diagnostic contact under the bottom strap lug; exact Watch4,2 access was not independently verified | UNKNOWN |
| iBus availability | Public third-party research/listings mention adapters; target compatibility and availability are unverified | UNKNOWN |
| Water resistance after DFU | Seal/service condition after physical access is target- and procedure-dependent; not verified here | UNKNOWN |
| checkm8 via DFU | Public research does not include T8006 in the checkm8 target set; no exploit was executed | LIKELY |
| Restore via DFU | Public stock restore documentation exists, but target accessibility and recovery from arbitrary experimental state are unverified | UNKNOWN/BLOCKED |

> Public stock documentation describes macOS-based Apple restore tooling. This
> audit did not verify current tool support for Watch4,2, and that path must
> not be treated as a recovery guarantee for arbitrary experimental state.

---

## 13. Research Path to T8006 MMIO Discovery

To get real MMIO addresses, the following approaches exist (in order of safety):

### Method 1: IPSW DeviceTree Extraction (SAFEST — no device needed)
1. Download watchOS IPSW from Apple (or ipsw.me)
2. Extract `DeviceTree.img4` from the IPSW
3. Decrypt/decompress with `img4tool`
4. Parse ADT binary with `devicetree-parse` or `adt.py`
5. Extract all `reg` properties → MMIO base addresses

**Status**: POSSIBLE on Windows (Python + img4tool). No device required.

### Method 2: kernelcache Analysis
1. Extract kernelcache from IPSW
2. Decompress and analyze in IDA Pro / Ghidra
3. Find IOKit driver classes, identify MMIO access patterns
4. Cross-reference with DeviceTree node names

**Status**: POSSIBLE on Windows with Ghidra (free) or IDA Pro (paid).

### Method 3: Peepo live-memory research

Public source describes possible dump-related outputs for selected targets,
but the reviewed path is exploit-backed and state-changing. Exact Watch4,2
compatibility, read-only behavior, completeness, provenance, and recovery are
unverified. No live procedure is provided or authorized.

**Status**: UNKNOWN/BLOCKED.

### Method 4: JTAG / Debug Cables
1. Public descriptions reference an Apple internal debug cable (iBus with JTAG capability)
2. Extremely rare, expensive, and potentially requires NDAs

**Status**: BLOCKED — not realistic for this project.

---

## Sources

- Apple product page (Series 4): https://www.apple.com/apple-watch-series-4/specs/
- iFixit Series 4 teardown: https://www.ifixit.com/Teardown/Apple+Watch+Series+4+Teardown/113044
- GSMArena Apple Watch Series 4: https://www.gsmarena.com/apple_watch_series_4-9112.php
- checkm8 info: https://checkm8.info/
- Elcomsoft Watch checkm8 analysis: https://blog.elcomsoft.com/2019/12/checkm8-and-checkra1n-for-apple-watch/
- PongoOS: https://github.com/checkra1n/PongoOS
- Peepo: https://github.com/datalocaltmp/Peepo
- JelBrekTime: https://github.com/tihmstar/JelBrekTime
- devicetree-parse: https://github.com/bazad/devicetree-parse
- Asahi ADT parser: https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/m1n1/adt.py
- img4tool: https://github.com/tihmstar/img4tool

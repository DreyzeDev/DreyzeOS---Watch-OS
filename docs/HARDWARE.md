# DreyzeOS — T8006 Hardware Documentation

## Status Legend

| Tag | Meaning |
|-----|---------|
| **CONFIRMED** | Verified from documentation, teardown, source code, or experiment |
| **LIKELY** | Strongly inferred from related data, not directly confirmed |
| **UNKNOWN** | Not yet determined — placeholder used in code |
| **EXPERIMENTAL** | Hypothesis being tested |
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
| Instruction set | ARMv8-A (AArch64) | CONFIRMED |
| Kernel execution mode | AArch64 (full 64-bit) | CONFIRMED |
| Userspace ABI | **ARM64_32 (ILP32)** | CONFIRMED |
| Pointer size in userspace | 32-bit (4 bytes) | CONFIRMED |
| Pointer size in kernel | 64-bit (8 bytes) | CONFIRMED |
| Clock frequency | UNKNOWN | UNKNOWN |
| Core type | Likely Tempest/Mistral class (2018 era) | LIKELY |

### 2.3 ARM64_32 (ILP32) Explanation

> ARM64_32 is critically different from both ARM64 and ARM32:
> - Uses the **AArch64 (64-bit) instruction set** — NOT Thumb/ARM32 instructions
> - But pointers are **32-bit** (4 bytes, limited to 4GB virtual address space)
> - Registers r0-r30 are 64-bit Xn registers, but addresses are truncated to 32 bits
> - XNU kernel itself runs full AArch64 (64-bit pointers)
> - DreyzeOS kernel code must be full AArch64
> - DreyzeOS apps (if ever built) would use ARM64_32 ABI

### 2.4 Memory

| Field | Value | Status |
|-------|-------|--------|
| RAM total | 1 GB (0x40000000 bytes) | CONFIRMED (iFixit, GSMArena) |
| RAM type | LPDDR3 or LPDDR4 | LIKELY |
| RAM physical base | UNKNOWN | UNKNOWN |
| NAND flash | 16 GB | CONFIRMED |

### 2.5 T8006 checkm8 Status

| Field | Value | Status |
|-------|-------|--------|
| checkm8 vulnerable? | **NO** | CONFIRMED |
| Boot ROM exploitable? | No known public exploit | CONFIRMED |
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
    │  [passes x0 = DeviceTree ptr to kernel]
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

**Status: ALL ADDRESSES UNKNOWN** — Apple does not publish T8006 technical reference manual.

```
Physical Address Space — T8006 (SPECULATIVE, NOT CONFIRMED)
=============================================================
0x0000_0000_0000_0000  Boot ROM / SecureROM         UNKNOWN size/addr
   ...
0x0000_0002_0000_0000  MMIO region START (LIKELY)   UNKNOWN — extrapolated from related SoCs
   ...
0x0000_0008_0000_0000  DRAM base (LIKELY)           UNKNOWN — conventional for Apple SoCs
0x0000_000C_0000_0000  DRAM end (1GB from base)     UNKNOWN
=============================================================

NOTE: All addresses above are SPECULATIVE extrapolations from A10/A11 platforms.
      They must be confirmed from DeviceTree dumps before use.
      DO NOT USE in production code.
```

### Known from Teardown (Memory Quantities Only)

| Component | Quantity | Address | Status |
|-----------|----------|---------|--------|
| RAM | 1 GB | UNKNOWN | CONFIRMED qty / UNKNOWN addr |
| NAND | 16 GB | UNKNOWN | CONFIRMED qty / UNKNOWN addr |

### MMIO Peripherals — Address Status

| Peripheral | Base Address | Status |
|-----------|-------------|--------|
| UART0 | UNKNOWN_T8006_UART_BASE | UNKNOWN |
| Display Controller | UNKNOWN_T8006_DISPLAY_BASE | UNKNOWN |
| Framebuffer | Allocated by iBoot, in DeviceTree `chosen` | CONFIRMED method / UNKNOWN value |
| Interrupt Controller (AIC) | UNKNOWN_T8006_AIC_BASE | UNKNOWN |
| PMGR (Power Manager) | UNKNOWN_T8006_PMGR_BASE | UNKNOWN |
| SPI0 | UNKNOWN_T8006_SPI0_BASE | UNKNOWN |
| SPI1 | UNKNOWN_T8006_SPI1_BASE | UNKNOWN |
| I2C0 | UNKNOWN_T8006_I2C0_BASE | UNKNOWN |
| GPIO | UNKNOWN_T8006_GPIO_BASE | UNKNOWN |

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
| Framebuffer base address | From DeviceTree `chosen/framebuffer` | CONFIRMED method |
| DCP MMIO base | UNKNOWN | UNKNOWN |

---

## 6. UART

| Field | Value | Status |
|-------|-------|--------|
| UART hardware present? | YES (engineering use) | CONFIRMED |
| Consumer-accessible UART? | NO (requires iBus + diagnostic cable) | CONFIRMED |
| UART IP | Samsung S3C-derived (LIKELY) | LIKELY |
| UART0 base address | UNKNOWN | UNKNOWN |
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
| ARM generic timer | Available (CNTPCT_EL0) | CONFIRMED |
| ARM timer frequency | LIKELY 24 MHz | LIKELY (standard Apple SoC) |

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
| DFU method | iBus adapter (diagnostic port) | CONFIRMED |
| Port location | Under bottom strap lug | CONFIRMED |
| iBus availability | Third-party (limited market) | CONFIRMED |
| Water resistance after DFU | Compromised (permanently) | CONFIRMED |
| checkm8 via DFU | NO — T8006 not vulnerable | CONFIRMED |
| Restore via DFU | YES (with valid signed IPSW) | CONFIRMED |

> **MAC REQUIRED**: DFU restore of Apple Watch requires macOS with Apple Configurator 2 or iTunes.  
> Reason: The restore protocol requires signed IPSW loading via Apple servers, and the USB  
> protocol used is only implemented in Apple Configurator 2 / iTunes on macOS.

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

### Method 3: Peepo Live Memory Dump (requires device + watchOS 10.6.1/10.6.2)
1. Run Peepo on Watch with watchOS 10.6.x
2. Get kernel R/W primitive
3. Walk IOKit IODeviceTree registry in kernel memory
4. Extract `reg` values from live device

**Status**: REQUIRES physical Apple Watch Series 4 with specific watchOS version.

### Method 4: JTAG / Debug Cables
1. Requires Apple internal debug cable (iBus with JTAG capability)
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

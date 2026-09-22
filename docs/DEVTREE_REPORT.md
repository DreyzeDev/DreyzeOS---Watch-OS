# DreyzeOS — Hardware Discovery Report (DeviceTree Analysis)
**Target**: Apple Watch Series 4 (44mm GPS) / Model A1978 / Watch4,2 / N131bAP  
**SoC**: Apple S4 / T8006  
**Firmware**: watchOS 10.6.1 (Build 21U580)  
**Source Artifact**: `DeviceTree.n131bap.im4p` (extracted from official Apple OTA `ea0b1ffe1a386549747807fb13cd889d91c36591.zip`)  
**SHA2-256 of OTA**: `f331199e8415ecbc75df0c8a6e1974c4f54acfc5c2ea1555f6daefff92ddcc78`  
**Decompression**: IM4P payload extracted with ASN.1 parser, decompressed with `lzfse` -> 139,400 bytes raw ADT binary.

---

## 1. Executive Summary

This document represents a **static DeviceTree physical-reg evidence report**
for the Apple S4 (T8006), not a live MMU map. All MMIO addresses listed below
were extracted directly from the Apple DeviceTree for the exact board
configuration (`N131bAP`), matching Apple Watch Series 4 44mm GPS (Watch4,2)
running watchOS 10.6.1 (21U580). The report does not prove that these
physical ranges are mapped at DreyzeOS entry, and the static `/memory` node is
zero-filled.

**Key Architectural Revelations**:
1. **CPU Cores**: Dual-core `apple,tempest` (A12-generation energy-efficient cores, 2MB L2 cache, CoreSight debug).
2. **Interrupt Controller**: Apple AIC2 generation (`compatible: "aic,1"`, `aic-version: 2`), base `0x2d180000`.
3. **Primary Boot Console UART**: `/arm-io/uart0` (`uart-1,samsung`), base `0x2e500000`, 16KB.
4. **Display Architecture**: Apple Mobile Display M9 (`disp0,t8006`), base `0x18000000`, with Synopsys MIPI DSI (`0x18400000`) and Summit LTPO OLED panel (`lcd,summit`).
5. **Touch & Crown Architecture**: **Neither Touch nor Digital Crown are directly MMIO-mapped to the Application Processor!** Both the multi-touch controller (`A3T531B,1`) and optical crown encoder (`optical`) are attached to the **RTP (Real-Time Processor)** coprocessor, communicating with the AP over **DockChannel IPC** (`0x4d080000`).

---

## 2. Complete T8006 Discovered Memory Map

Every range is labeled with its verification status:
- **CONFIRMED**: Extracted directly from `DeviceTree.n131bap.adt` `reg` property.
- **LIKELY**: Highly supported by XNU/iBoot convention and adjacent nodes.
- **DESIGN**: Host-side proposal, not hardware evidence.
- **UNKNOWN**: Dynamically populated at boot time by iBoot.
- **BLOCKED**: Cannot be used until the missing runtime contract is proven.

| Subsystem | Node Path | Compatible | Base Address | Size | Status | Notes |
|:---|:---|:---|:---|:---|:---:|:---|
| **Interrupt Controller (AIC)** | `/arm-io/aic` | `aic,1` | `0x000000002d180000` | `0x8000` (32 KB) | **CONFIRMED** | AIC v2, 2 main CPUs, master controller |
| **AIC Timebase (Timer)** | `/arm-io/aic-timebase` | N/A | `0x000000002d188000` | `0x1000` (4 KB) | **CONFIRMED** | Hardware timebase timer |
| **ARM Generic Timer** | Architectural | ARMv8-A | System Regs | N/A | **CONFIRMED** | `cntfrq_el0`, `cntpct_el0` accessible from EL1 |
| **UART 0 (Boot Console)** | `/arm-io/uart0` | `uart-1,samsung` | `0x000000002e500000` | `0x4000` (16 KB) | **CONFIRMED** | Has `boot-console` property! IRQ 262 (`0x106`) |
| **UART 1 (GPS)** | `/arm-io/uart1` | `uart-1,samsung` | `0x000000002e504000` | `0x4000` (16 KB) | **CONFIRMED** | Connected to BCM4773 GPS; IRQ 263 (`0x107`) |
| **UART 2 (NFC)** | `/arm-io/uart2` | `uart-1,samsung` | `0x000000002e508000` | `0x4000` (16 KB) | **CONFIRMED** | Connected to Stockholm NFC; IRQ 264 (`0x108`) |
| **DockChannel UART** | `/arm-io/dockchannel-uart` | N/A | `0x000000003d128000`<br>`0x000000003d10c000` | `0x10000` (64 KB)<br>`0x4000` (16 KB) | **CONFIRMED** | Diagnostic dock channel; IRQ 167 (`0xa7`) |
| **AP GPIO** | `/arm-io/gpio` | `gpio,t8006` | `0x000000002d300000` | `0x2000` (8 KB) | **CONFIRMED** | 139 pins (`0x8b`), 7 interrupt groups |
| **AOP GPIO** | `/arm-io/aop-gpio` | `gpio,t8006` | `0x000000004d008000` | `0x4000` (16 KB) | **CONFIRMED** | Always-On Processor GPIO; 114 pins (`0x72`) |
| **Display Subsystem** | `/arm-io/disp0` | `disp0,t8006` | `0x0000000018000000` | `0x2f0000` (3008 KB)| **CONFIRMED** | Apple Mobile Display M9 controller |
| **MIPI DSI Master** | `/arm-io/mipi-dsim` | `mipi-dsim-1,synopsys` | `0x0000000018400000`<br>`0x0000000018490000` | `0x90000` (576 KB)<br>`0x10000` (64 KB) | **CONFIRMED** | Synopsys DesignWare MIPI DSI controller |
| **LCD / OLED Panel** | `/arm-io/mipi-dsim/lcd` | `lcd,summit` | N/A | N/A | **CONFIRMED** | Summit LTPO OLED panel (command mode) |
| **Display DART (IOMMU)** | `/arm-io/dart-disp0` | `dart,t8020` | `0x0000000018704000`<br>`0x0000000018700000` | `0x4000` (16 KB)<br>`0x4000` (16 KB) | **CONFIRMED** | IOMMU for display DMA engines |
| **Framebuffer Base** | `/vram` | N/A | Static `reg=[0x0+0x0]` | Runtime size/base absent | **UNKNOWN** | The reviewed static ADT does not contain a live framebuffer range; a runtime producer/handoff is still missing |
| **DockChannel RTP (Touch/Crown)** | `/arm-io/dockchannel-rtp` | `dockchannel,t8002` | `0x000000004d080000`<br>`0x000000004d08c000`<br>`0x000000004d0b0000`<br>`0x000000004d0b4000`<br>`0x000000004d0a8000`<br>`0x000000004d0ac000` | `0x1000` (4 KB)<br>`0x1000` (4 KB)<br>`0x1000` (4 KB)<br>`0x1000` (4 KB)<br>`0x1000` (4 KB)<br>`0x1000` (4 KB) | **CONFIRMED** | IPC interface to Real-Time Processor (IRQ 76) |
| **Multi-Touch Controller** | `.../rtp-transport/multi-touch` | `A3T531B,1` | No AP MMIO | N/A | **CONFIRMED** | Managed via RTP coprocessor over DockChannel IPC |
| **Digital Crown Optical Encoder** | `.../rtp-transport/optical` | `optical` | No AP MMIO | N/A | **CONFIRMED** | Managed via RTP coprocessor over DockChannel IPC |
| **Buttons (Side & Crown Click)** | `/buttons` | `buttons` | Routed to PMU/SMC | N/A | **CONFIRMED** | Side button (`help`), Crown click (`menu`) |
| **I2C Controller 1** | `/arm-io/i2c1` | `i2c,t8006` | `0x000000002e014000` | `0x1000` (4 KB) | **CONFIRMED** | Connected to Tristar CBTL1610 (`0x1a`) |
| **I2C Controller 3** | `/arm-io/i2c3` | `i2c,t8006` | `0x000000002e01c000` | `0x1000` (4 KB) | **CONFIRMED** | Connected to Speaker Amp D2481 & Hall sensor AD5860 |
| **Serial I/O (SIO)** | `/arm-io/sio` | `iop,ascwrap-v2` | `0x000000002f400000`<br>`0x000000002f050000` | `0x10000` (64 KB)<br>`0x4000` (16 KB) | **CONFIRMED** | Replaces generic SPI buses; uses SIO DMA |
| **SIO DART (IOMMU)** | `/arm-io/dart-sio` | `dart,t8020` | `0x000000002e008000` | `0x4000` (16 KB) | **CONFIRMED** | IOMMU for Serial I/O and AES DMA |
| **USB Controller (Host/OTG)** | `/arm-io/usb-complex` | `usb-complex,t8006` | `0x0000000030000000` | `0x100` (256 B) | **CONFIRMED** | Top-level USB complex |
| **USB OTG PHY Control** | `/arm-io/otgphyctrl` | `otgphyctrl,t8006` | `0x0000000030000030`<br>`0x0000000030000050` | `0x20` (32 B)<br>`0x10` (16 B) | **CONFIRMED** | USB PHY controller |
| **USB Device Controller** | `.../usb-complex/usb-device`| `usb-device,t8006` | `0x0000000030100000` | `0x10000` (64 KB) | **CONFIRMED** | USB Device controller (DWC2 derivative) |
| **USB EHCI Host** | `.../usb-complex/usb-ehci0` | `usb-ehci,t8006` | `0x0000000030080000` | `0x10000` (64 KB) | **CONFIRMED** | Standard EHCI USB Host controller |
| **USB DART (IOMMU)** | `/arm-io/dart-sue` | `dart,t8020` | `0x0000000033004000` | `0x4000` (16 KB) | **CONFIRMED** | IOMMU for USB device and host DMA |
| **Power Manager (PMGR Primary)**| `/arm-io/pmgr` | `pmgr1,t8006` | `0x000000002d000000` | `0x180000` (1.5 MB) | **CONFIRMED** | Main SoC clock, power gates, resets |
| **Power Manager (PMGR Sec)** | `/arm-io/pmgr` | `pmgr1,t8006` | `0x000000003d200000` | `0x100000` (1 MB) | **CONFIRMED** | Domain power management |
| **CLPC (CPU Power/Perf)** | `/arm-io/pmgr/clpc` | `clpc,t8006` | `0x0000000208f44000` | `0x4000` (16 KB) | **CONFIRMED** | CPU Low Power Controller |
| **Watchdog Timer (WDT)** | `/arm-io/wdt` | `wdt,t8006` | `0x000000003d2b0000`<br>`0x000000003d2b8020` | `0x4000` (16 KB)<br>`0x4` (4 B) | **CONFIRMED** | Hardware watchdog timer |
| **SPMI Bus** | `/arm-io/spmi` | `spmi,gen0` | `0x000000003d1a0400`<br>`0x000000003d1a0d00` | `0x100` (256 B)<br>`0x100` (256 B) | **CONFIRMED** | Power Management Bus to external PMU |
| **SMC / PMU Coprocessor** | `/arm-io/smc` | `iop,ascwrap-v2` | `0x000000003e400000`<br>`0x000000003e050000` | `0x20000` (128 KB)<br>`0x4000` (16 KB) | **CONFIRMED** | Apple SMC IOP |
| **AOP (Always-On Processor)** | `/arm-io/aop` | `iop,ascwrap-v2` | `0x000000004d600000`<br>`0x000000004c400000` | `0x160000` (1408 KB)<br>`0x60000` (384 KB) | **CONFIRMED** | Sensor hub and low-power management |
| **RTP (Real-Time Processor)** | `/arm-io/rtp` | `iop,ascwrap-v2` | `0x000000004d400000`<br>`0x000000004cc00000` | `0x100000` (1 MB)<br>`0x60000` (384 KB) | **CONFIRMED** | Dedicated coprocessor for touch & crown |
| **SEP (Secure Enclave)** | `/arm-io/sep` | `iop,ascwrap-v2` | `0x0000000042400000`<br>`0x0000000042050000` | `0xc000` (48 KB)<br>`0x4000` (16 KB) | **CONFIRMED** | Secure Enclave Processor mailboxes |
| **Main DRAM Base** | `/memory` | N/A | Static `base=0,size=0` | Static size `0` | **BLOCKED** | `0x800000000` and `0x40000000` are historical research fallbacks, not confirmed values from this artifact; runtime population is absent |
| **Reserved Memory Regions** | `/chosen/memory-map` | N/A | All `MemoryMapReserved-*` entries are empty/zero in the static dump | No static ranges | **BLOCKED** | A runtime producer may populate them, but this snapshot does not identify or prove that mechanism for the target |

---

## 3. Subsystem Deep-Dive

### 3.1 Interrupt Controller (AIC)
- **Node**: `/arm-io/aic`
- **Compatible**: `aic,1` (Apple Interrupt Controller v2)
- **Base**: `0x2d180000`, Size: `0x8000`
- **CPUs**: Dual core (`#main-cpus: 2`)
- **Implication for DreyzeOS**: Static register research is available, but production AIC access remains gated. Asahi Linux/PongoOS behavior is architectural context, not Watch4,2 runtime mapping evidence.

### 3.2 Primary UART Console
- **Node**: `/arm-io/uart0`
- **Compatible**: `uart-1,samsung` (Apple Samsung-derived UART)
- **Base**: `0x2e500000`, Size: `0x4000`
- **Interrupt**: 262 (`0x106`)
- **Clock**: `0x00000017` gate
- **Implication for DreyzeOS**: We have the **static physical DeviceTree address** for UART0; its runtime virtual mapping, clock state, and safe handoff remain UNKNOWN.
  - Replacing `UNKNOWN_T8006_UART0_BASE` (`0xDEADBEEF...`) with `0x2e500000` in `hal/t8006/memory_map.h`!
  - Standard Apple UART register layout:
    * `ULCON`: `0x00`
    * `UCON`: `0x04`
    * `UFCON`: `0x08`
    * `UMCON`: `0x0C`
    * `UTRSTAT`: `0x10` (TX empty bit 1, RX ready bit 0)
    * `UTXH`: `0x20` (Transmit buffer byte)
    * `URXH`: `0x24` (Receive buffer byte)

### 3.3 Display & Framebuffer
- **Controller**: Apple Mobile Display M9 (`disp0,t8006`) at `0x18000000`
- **Interface**: MIPI DSI (`mipi-dsim-1,synopsys`) at `0x18400000`
- **Panel**: `lcd,summit` (LTPO OLED panel)
- **Resolution**: 368 x 448 pixels (44mm model)
- **Framebuffer Base**: The static `/vram` entry is zero-filled. A runtime boot handoff may provide a framebuffer through `boot_args` or `/chosen/memory-map`, but that live value and mapping are not present in the reviewed artifact.

### 3.4 Multi-Touch & Digital Crown
- **Critical Finding**: **No direct AP MMIO registers exist for touch or crown.**
- Touch controller: `A3T531B,1`
- Crown encoder: `optical`
- Both devices reside on `/arm-io/dockchannel-rtp/rtp-transport/`
- They are serviced exclusively by the **RTP (Real-Time Processor)** coprocessor (`iop,ascwrap-v2` at `0x4d400000` / `0x4cc00000`).
- To receive touch or crown events in bare-metal:
  1. Bootloader must either leave RTP running and poll the DockChannel FIFO (`0x4d080000`), or
  2. For Phase 1-5, touch and crown should be considered **BLOCKED for direct bare-metal MMIO**, requiring either a reverse-engineered RTP firmware handover or relying on UART/buttons for input.

### 3.5 Hardware Buttons
- **Side Button**: Designated `help` in DeviceTree.
- **Crown Click**: Designated `menu` in DeviceTree.
- Both buttons trigger events through the SMC / PMU coprocessor (`0x5f` phandle) and AOP GPIO (`0x4d008000`).

---

## 4. Updates Applied to DreyzeOS HAL

With this report, the following placeholders in `hal/t8006/memory_map.h` can be transformed from `UNKNOWN_T8006_*` to **CONFIRMED**:
- `T8006_AIC_BASE`: `0x2d180000` (CONFIRMED)
- `T8006_AIC_TIMER_BASE`: `0x2d188000` (CONFIRMED)
- `T8006_UART0_BASE`: `0x2e500000` (CONFIRMED)
- `T8006_UART1_BASE`: `0x2e504000` (CONFIRMED)
- `T8006_UART2_BASE`: `0x2e508000` (CONFIRMED)
- `T8006_GPIO_BASE`: `0x2d300000` (CONFIRMED)
- `T8006_DISP0_BASE`: `0x18000000` (CONFIRMED)
- `T8006_MIPI_DSI_BASE`: `0x18400000` (CONFIRMED)
- `T8006_PMGR_BASE`: `0x2d000000` (CONFIRMED)
- `T8006_WDT_BASE`: `0x3d2b0000` (CONFIRMED)
- `T8006_USB_BASE`: `0x30000000` (CONFIRMED)

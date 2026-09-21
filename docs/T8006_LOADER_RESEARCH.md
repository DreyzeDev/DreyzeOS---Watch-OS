# T8006 Loader / RAM Handoff Contract Research — Phase 4 Step 2.7

**Target**: Apple Watch Series 4 / Watch4,2 / Apple S4 / T8006
**Scope**: static source and public-artifact review only
**Safety boundary**: no Apple Watch execution, DFU, exploit execution, payload delivery, or NAND/NOR write was performed.

## Executive result

Public evidence confirms T8006-related research primitives, but it does not
establish a DreyzeOS-compatible loader contract. The closest public control
primitive is [usbliter8](https://github.com/JoshAtticus/usbliter8): its public
repository identifies a tethered BootROM exploit for Apple A12, S4/S5, and A13,
contains a `t8020_t8006_shellcode` tree, and documents post-exploit raw-iBoot
boot control. That is **CONFIRMED** as public T8006/S4/S5 research, but it is
not evidence for DreyzeOS payload PA/VA, entry EL, MMU state, descriptor
delivery, or a safe arbitrary-RAM handoff.

The static snapshots reviewed for this step are usbliter8
`479dbbf4ad80e4a454e0779d1b4d1ec5eb0d7bd5` and Peepo
`6d20d676f7c2d1620ba4764f7500baa906d67b64`. No device, DFU session, exploit,
USB transfer, payload delivery, or hardware execution was performed.

[Peepo](https://github.com/datalocaltmp/Peepo/blob/main/README.md) is separate
**CONFIRMED** T8006 research: it documents kernel R/W and process-memory dumps
on Watch4,1/T8006 for specific watchOS 10.6.x kernel builds. It is a kernel
post-exploitation primitive, not a preboot loader or DreyzeOS execution proof.

## Evidence matrix

| Question | Exact public evidence | Target applicability | Status |
|---|---|---|:---:|
| Is there public T8006/S4/S5 code with execution control? | usbliter8 README names A12, S4/S5 and A13, and the repository exposes `t8020_t8006_shellcode`. | Shows a relevant research path exists; does not define DreyzeOS handoff. | **CONFIRMED** |
| Does that public project document raw boot control? | usbliter8 documents a control tool that can boot raw iBoot after exploitation. | Relevant to post-exploit boot control; no DreyzeOS payload contract is stated. | **CONFIRMED** |
| Is arbitrary DreyzeOS RAM payload execution proven? | No public artifact reviewed provides DreyzeOS-compatible payload placement, entry registers, or descriptor handoff. | Cannot safely select a load address or jump protocol. | **UNKNOWN/BLOCKED** |
| T8006 physical payload load PA | No exact DreyzeOS payload destination was found in the reviewed public artifacts. | Required before any non-PIC image can be delivered. | **UNKNOWN/BLOCKED** |
| DreyzeOS execution VA | The repository linker script uses `0x100000000` as a placeholder. | A wrong VMA breaks non-PIC absolute references. | **BLOCKED** |
| T8006 entry EL | Public T8006 evidence reviewed does not specify the EL at a DreyzeOS payload entry. | DreyzeOS source requires EL1; EL0 must not be guessed or probed unsafely. | **UNKNOWN/BLOCKED** |
| MMU, TTBR, cache and mapping handoff | No reviewed T8006 loader artifact proves identity mapping, TTBR values, cache state, or usable VA mappings for DreyzeOS. | Physical addresses cannot be dereferenced as virtual addresses. | **UNKNOWN/BLOCKED** |
| Maximum transfer / relocation limit | No T8006/DreyzeOS transfer bound or relocation protocol was found. | Payload size and overlap safety remain unresolved. | **UNKNOWN** |
| iBUS/AWRT delivery vector | The reviewed public evidence does not establish a reproducible Watch4,2 delivery setup or exact adapter wiring for this project. | Hardware delivery remains unselected and unvalidated. | **UNKNOWN/BLOCKED** |
| T8006 kernel R/W primitive | Peepo documents confirmed kernel R/W and memory dumping on a specific T8006 kernel build. | Useful diagnostic/research primitive; not a preboot loader. | **CONFIRMED** |
| Preboot/bare-metal analogy | [PongoOS](https://github.com/checkra1n/PongoOS) documents a preboot environment and a bare-metal binary that can be jumped to. | Checkra1n/other-device architecture; not T8006 evidence. | **LIKELY** |
| Payload chaining analogy | [m1n1](https://github.com/AsahiLinux/m1n1) documents payload concatenation on Apple Silicon. | Demonstrates a design pattern only; no T8006 addresses or state transfer. | **LIKELY** |

The status labels above are deliberately narrower than “works on hardware”:
public code existence is **CONFIRMED** evidence of that artifact, not proof
that its exploit or delivery path is applicable to DreyzeOS.

## DreyzeOS ABI V1 design

The repository now defines one fixed-width wire descriptor. It is exactly 128
bytes and contains no `bool`, `size_t`, or `uintptr_t` fields:

| Offset | Field | Width |
|---:|---|---:|
| `0x00` | `magic` | `u64` |
| `0x08` | `version` | `u32` |
| `0x0C` | `size` | `u32` |
| `0x10` | `flags` | `u64` |
| `0x18` | `entry_el` | `u32` |
| `0x1C` | `reserved0` | `u32` |
| `0x20` | `payload_pa` | `u64` |
| `0x28` | `payload_va` | `u64` |
| `0x30` | `payload_size` | `u64` |
| `0x38` | `mmu_enabled` | `u32` |
| `0x3C` | `reserved1` | `u32` |
| `0x40` | `raw_x0` | `u64` |
| `0x48` | `raw_x1` | `u64` |
| `0x50` | `boot_args_range` | `24` |
| `0x68` | `device_tree_range` | `24` |

Each range is `base u64`, `length u64`, `flags u32`, `reserved u32`; the only
V1 range flag is `READABLE`. Descriptor flags include `VERIFIED`, known-state
bits for EL/payload/MMU, a mapping-state-known bit, and MMIO/UART/AIC validity
facts whose relationships are structurally checked.

V1 flag assignments are: bit 0 VERIFIED, bit 1 ENTRY_EL_KNOWN, bit 2
PAYLOAD_LOCATION_KNOWN, bit 3 MMU_STATE_KNOWN, bit 4 MMIO_MAPPING_VALID, bit 5
UART_MAPPING_VALID, bit 6 AIC_MAPPING_VALID, and bit 7
MAPPING_STATE_KNOWN. The fixed descriptor size remains 128 bytes; adding bit 7
does not change any field offset.

Validation rules:

1. The pointer to the descriptor must already be readable under the loader's
   pre-existing contract; this is the root-of-trust boundary.
2. The fixed prefix must have the exact magic and supported version, with
   `size >= 128`.
3. Unknown V1 flags, non-zero reserved fields, and `mmu_enabled > 1` reject
   the descriptor.
4. A larger size is forward-compatible; V1 reads only the fixed 128-byte
   prefix and ignores the unknown tail.
5. A range is usable only after fixed-width values are representable in native
   types, the READABLE flag is set, length is non-zero, addition cannot wrap,
   and the complete object fits inside the range.
6. If `ENTRY_EL_KNOWN` is set, `entry_el` must be EL1. If
   `PAYLOAD_LOCATION_KNOWN` is set, PA/VA/size must describe non-zero,
   non-empty, non-wrapping ranges.
7. Any MMIO/UART/AIC validity bit requires `MAPPING_STATE_KNOWN`; UART/AIC
   validity additionally requires `MMIO_MAPPING_VALID`. A known negative
   state is representable by setting `MAPPING_STATE_KNOWN` without a validity
   bit.
8. `VERIFIED` is not a signature and does not by itself prove pointer safety.
   The current setter is host-test-only, copies the fixed prefix without
   normalizing bad fields, and production still preserves raw x0/x1 without
   dereferencing them.

## Static source archaeology — usbliter8

The reviewed usbliter8 sources are an exploit-specific SecureROM control path,
not a generic AArch64 payload loader. The exact facts below are CONFIRMED as
source facts; their usefulness as a DreyzeOS handoff is UNKNOWN/BLOCKED.

| Source artifact | Exact fact from source | DreyzeOS interpretation |
|---|---|---|
| [t8020_t8006_shellcode/start.S](https://github.com/JoshAtticus/usbliter8/blob/main/t8020_t8006_shellcode/start.S) | Uses handler_off = 0x3C00 and ret_tramp_off = 0x3F00; clears SCTLR_EL1.M, installs sp = NEW_SP, copies a return trampoline/handler, writes a PTE, executes tlbi vmalle1 and ic iallu, then re-enables SCTLR_EL1.M. | CONFIRMED exploit trampoline behavior; not a DreyzeOS entry contract. |
| [targets/t8006/offsets.h](https://github.com/JoshAtticus/usbliter8/blob/main/t8020_t8006_shellcode/targets/t8006/offsets.h) | T8006 constants include NEW_SP=0x1801D8BC0, TRAMP_BASE=0x1801C8000, ROM_TRAMP=0x100007A00, BOOT_TRAMP_PTEP=0x1801B4390, BOOT_TRAMP_PTE=0x1801C86E3, DMA_BUF_LO=0x801D9600, USB_DMA_DEST=0x230100B14, USB_REQ_HANDLER_CB_ADDR=0x1801C03F8, and RETURN_TO_EL0_ADDR=0x10000C370. | CONFIRMED hardcoded exploit/ROM/heap addresses; no address is a DreyzeOS payload PA or VA. |
| start.S return path | Restores the original ROM trampoline and SCTLR_EL1, sets ELR_EL1=RETURN_TO_EL0_ADDR, SPSR_EL1=0x100, then executes eret. | The target return is a ROM task at EL0; it is not evidence for DreyzeOS EL1 entry. |
| [usb_req_handler/handler.c](https://github.com/JoshAtticus/usbliter8/blob/main/usb_req_handler/handler.c) | Custom boot calls platform_set_remote_boot(), stores JUMP_AWAY/PACIB to MAIN_TASK_STACK_LR, and chains non-custom requests to the original handler. | Raw iBoot control path; no descriptor, stack, or kernel ABI. |
| [exploit.c](https://github.com/JoshAtticus/usbliter8/blob/main/exploit.c) | T8006 setup uses overwrite size 0xB04 bytes and shellcode transfer size 0x400 bytes; generated T8006 shellcode is 816 bytes and handler is 116 bytes. | These are exploit transfer/layout sizes, not a maximum safe DreyzeOS payload or relocation bound. |
| usbliter8ctl DFU path | Raw iBoot is sent with TRANSFER_SIZE=0x800 chunks, followed by custom boot and DFU abort. | CONFIRMED raw-iBoot delivery behavior; it does not define a DreyzeOS RAM deposit address. |

The source therefore establishes a control primitive around a particular
SecureROM heap, ROM trampoline, task stack, and USB callback environment. It
does not expose a stable contract for payload PA, payload VA, entry PC, SP,
DAIF, TTBR0/TTBR1, TCR, MAIR, cache state, executable mappings, or a
readable DreyzeOS descriptor. Running it would cross the explicit hardware
boundary and was not attempted.

## Static source archaeology — Peepo

[Peepo/Peepo Watch App/darksword.m](https://github.com/datalocaltmp/Peepo/blob/main/Peepo%20Watch%20App/darksword.m)
provides a separate kernel post-exploitation research path:

| Source fact | Status | Boundary |
|---|:---:|---|
| DS_PAGE_SHIFT=14 and 16 KiB page-table assumptions | CONFIRMED source fact | Useful architecture context; not a loader ABI. |
| DS_DRAM_LO=0x807000000, DS_DRAM_HI=0x840000000 | CONFIRMED source constants/comments | A runtime-safe physmap window hypothesis for that exploit; not proof of DreyzeOS RAM placement or Watch4,2 applicability. |
| gPhysmapOff = tte - ttep from live translation-table objects | CONFIRMED source algorithm | Runtime-derived and therefore unavailable without the forbidden exploit/device run. |
| peepo_dump_kernelcache cap/fallback 0x2800000 | CONFIRMED source behavior | Kernelcache dump cap/fallback, not a DreyzeOS payload-size limit. |
| README target claim | CONFIRMED public documentation for Watch4,1/T8006 on selected watchOS 10.6.x builds | The project target is Watch4,2; applicability remains UNKNOWN/BLOCKED and was not tested. |

Peepo could potentially provide runtime-derived kernel/physmap observations
after exploit execution, but it cannot be used here as static proof of an
entry mapping. No Peepo code was built, installed, or executed.

## DreyzeOS ELF and flat-image evidence

The current host build at baseline 6dec534db25ebf7df32b7f3c9b9886197bd2381d
was rebuilt and inspected:

| Artifact | Observed value | Status |
|---|---|:---:|
| ELF entry / _start | 0x100000000 | CONFIRMED link-time fact |
| .text.boot | 0x100000000, size 0x10bc, executable | CONFIRMED |
| .text | 0x1000010c0, size 0x4028 | CONFIRMED |
| .rodata / .data | 0x100006000 / 0x100009000 | CONFIRMED |
| .bss / .stack | 0x10000d060 / 0x100051950 | CONFIRMED |
| Program LOAD segments | R-E, R, RW; no RWX segment | CONFIRMED |
| readelf -r | no relocations | CONFIRMED static-link fact |
| objdump -d | adr/adrp link-time references, direct in-image bl, and absolute global addresses | CONFIRMED non-PIC evidence |
| Flat BIN size | 53,336 bytes | CONFIRMED host build fact |

The absence of relocations means the linker already resolved references; it
does not make DreyzeOS.bin position-independent. Moving the flat image without
matching the linked VMA can invalidate entry addresses, C globals, literal
references, and direct branches. The new host test checks the linked
instruction order and this non-PIC property from the disassembly.

## PIC stage-0 analysis

### Option A — fixed-address non-PIC image

The current image is statically linked and intentionally non-PIC. It is valid
only when the loader places it at the exact link-time VMA and supplies an
executable mapping for that address. This leaves all unknown PA/VA, EL, stack,
and MMU questions unresolved. `readelf -r` being empty proves static linking;
it does not prove the placement is usable on T8006. **Status: DESIGN**, with
hardware applicability **BLOCKED**.

### Option B — tiny PIC stage-0

A small position-independent stage-0 could start from the loader's actual PC,
establish a known stack, locate or copy the fixed ABI prefix, validate it, and
relocate/enter a larger kernel at a descriptor-provided VA. The repository now
contains tests/pic_stage0_host.c, a host-only decision model that copies only a
pre-proven 128-byte prefix, validates the V1 descriptor, requires explicit
EL1/stack/DAIF/translation/cache/executable-mapping facts, and computes a
target entry address without executing it. This reduces the dependency on one
preselected image address, but it cannot remove the need for an
executable/readable initial mapping or infer a safe payload PA. **Status:
DESIGN; host model CONFIRMED by host tests; hardware applicability
UNKNOWN/BLOCKED**.

### Option C — fully position-independent kernel

A fully PIC kernel would remove more link-time VA assumptions, but it would
still require a valid entry PC, stack, EL1 state, readable code/data mapping,
translation/cache contract, and a safe way to find the descriptor. It would
also require a larger ABI and test surface. No such implementation is
selected for this step. **Status: DESIGN; hardware applicability
UNKNOWN/BLOCKED**.

### Option comparison

| Option | Main advantage | What remains mandatory | Decision |
|---|---|---|---|
| A — fixed non-PIC | Smallest current image; simple linker contract | Exact load VMA/PA, executable mapping, EL1, SP, MMU/TTBR/cache state | Keep as current research artifact; hardware **BLOCKED** |
| B — PIC stage-0 + fixed kernel | Reduces initial placement dependency; can validate V1 before transition | Initial executable map, descriptor prefix, target PA/VA, entry offset, SP, DAIF, translation/cache state | Preferred future direction; host-only model added |
| C — fully PIC | Minimizes link-time VA assumptions | Same CPU/mapping contract plus a larger relocation/PIC implementation | Not selected; unnecessary before loader evidence |

The smallest useful next artifact is therefore a real loader/shim contract that
matches Option B's input assertions. The host model must not be mistaken for
that artifact.

## Handoff contract completeness matrix

| Contract item | V1 representation or test | Status before hardware |
|---|---|:---:|
| Descriptor prefix readability | External pre-proof plus 128-byte host copy model | DESIGN / UNKNOWN |
| Descriptor identity and version | magic, version, size, reserved fields | DESIGN; structural validator CONFIRMED |
| Payload PA/VA/size | three u64 fields plus known flag and overflow checks | DESIGN; values UNKNOWN/BLOCKED |
| Entry PC | target VA plus host model entry offset; no V1 entry-PC field | DESIGN; hardware UNKNOWN/BLOCKED |
| Entry EL | entry_el plus ENTRY_EL_KNOWN, restricted to EL1 | DESIGN; hardware UNKNOWN/BLOCKED |
| Initial SP | not represented in V1; explicit stage-0 input only | UNKNOWN/BLOCKED |
| DAIF | not represented in V1; explicit stage-0 input only | UNKNOWN/BLOCKED |
| SCTLR/TCR/TTBR0/TTBR1/MAIR | only mmu_enabled in V1; registers are not handed over | UNKNOWN/BLOCKED |
| I/D-cache state | not represented in V1 | UNKNOWN |
| Executable/readable mapping | not represented in V1; explicit stage-0 proof input only | UNKNOWN/BLOCKED |
| boot_args / DeviceTree | separately bounded readable ranges | DESIGN; runtime delivery UNKNOWN |
| MMIO/UART/AIC mapping | mapping-state-known plus validity flags | DESIGN; runtime UNKNOWN/BLOCKED |
| Maximum transfer/payload size | no source proves a DreyzeOS bound | UNKNOWN |
| Physical delivery vector | usbliter8 source exists; exact Watch4,2 deployment unproven | UNKNOWN/BLOCKED |

## Closest primitive and remaining blocker

The closest public primitive is **usbliter8** because it is explicitly tied to
S4/S5-class SecureROM work and exposes T8006-related shellcode. The closest
T8006 memory primitive is **Peepo**'s kernel R/W. Neither is a DreyzeOS loader,
and neither supplies the exact ABI fields required by `loader_handoff_descriptor_t`.

The next research artifact needed before hardware execution is a static,
reproducible loader/shim contract that proves: payload PA and transfer bounds,
entry VA, EL1, stack, MMU/TTBR/cache state, executable mapping, and descriptor
prefix readability. Until then the project remains host-only.

**FIRST HARDWARE EXECUTION = NOT READY**

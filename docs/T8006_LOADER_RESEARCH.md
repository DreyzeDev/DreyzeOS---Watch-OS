# T8006 Loader Evidence Research — Phase 4 Step 2.6

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
bits for EL/payload/MMU, and independent MMIO/UART/AIC mapping facts.

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
6. `VERIFIED` is not a signature and does not by itself prove pointer safety.
   The current setter is host-test-only, copies the fixed prefix without
   normalizing bad fields, and production still preserves raw x0/x1 without
   dereferencing them.

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
relocate/enter a larger kernel at a descriptor-provided VA. This reduces the
dependency on one preselected image address, but it cannot remove the need for
an executable/readable initial mapping, a known entry EL, a usable stack, and a
defined cache/MMU regime. It also cannot infer a safe payload PA or claim that
T8006 supplies the descriptor. **Status: DESIGN**.

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

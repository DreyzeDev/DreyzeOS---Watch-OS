# Target-Side Stage-0 Artifact Specification

Status: **DESIGN / HOST ONLY**
Target artifact built by this step: **NO**
Target execution or device interaction: **NONE**

This document specifies the form and evidence contract for a future AArch64
Stage-0 artifact. It is not source code, a payload, a loader, or a launch
method. No target address, memory map, or device operation is assigned here.

## 1. Decision summary

**Preferred future position policy: strict self-relative PIC, linked as a
statically linked position-independent ELF (PIE/ET_DYN), with no dynamic
dependencies and no runtime relocations.** This is a design choice, not an
implemented artifact or a claim that a launch mechanism exists.

The policy avoids requiring a predetermined link-time target VA. It does not
remove the need for a launcher to place the bytes, establish a valid executable
mapping, make instruction fetch coherent, and transfer control to the runtime
entry. Those target-specific facts remain **UNKNOWN / BLOCKED**.

No target ELF or flat BIN is built in this step. The existing
`stage0_reference.elf` is a native host executable for contract tests; it is
not AArch64 code and is not interchangeable with the future target artifact.
Producing a no-op AArch64 stub would prove only that a cross-toolchain can emit
instructions, not that a useful Stage-0 has a defined entry ABI, safe memory
footprint, evidence interface, or pre-Stage-0 execution contract. Treating
such a stub as the target artifact would be misleading.

## 2. Architecture options

| Option | Requires known target VA? | Relocations | Loader support | Bootstrap complexity / provenance impact | Suitable? |
|---|---|---|---|---|---|
| **A. Fixed-address Stage-0** | **YES** — the actual execution VA must equal the link VMA and have a proven executable fetch mapping. | Static linker resolves addresses; the image is not movable. Final relocation table may be empty without being PIC. | Must place at the exact linked address and prove resident bytes/mapping. | Simple image, but adds an unsupported fixed-placement assumption to the already-blocked pre-Stage-0 gate. | **NO** — no target load/fetch address is proven. |
| **B. Strict PIC/PIE Stage-0** | No fixed link VMA; **YES**, a runtime execution VA/PC and executable fetch mapping are still required. | No runtime/dynamic relocations in the selected policy. All in-image references must be PC-relative and statically resolved. | Must place/map the image and enter its runtime-relative entry; it need not implement a relocation engine if the final ELF truly has no runtime relocations. | Removes the fixed-link-VA assumption, but does not prove placement, ownership, mapping, cache visibility, or control transfer. Artifact hash/session provenance remains separately required. | **YES as DESIGN** — lowest of these three placement assumptions; not ready to build or launch. |
| **C. Relocatable object processed by external loader** | The loader chooses a base, but the runtime execution VA/mapping is still required. | Requires supported relocation types, symbol resolution, relocation bounds, and post-relocation validation. | **YES**, including a relocation engine and a policy for its memory writes and cache effects. | Adds a trusted relocation processor and more mutable state before observation; provenance must bind both source bytes and relocated result. | **NO** — unnecessary complexity and no reviewed loader exists. |

“PIC/PIE” is not synonymous with “address-free” or “safe to execute”. Option B
still depends on a specific runtime PC, readable/executable bytes, an allowed
instruction-fetch regime, and any data/stack ranges that the implementation
uses. A numeric address or nonzero TTBR cannot provide those proofs.

## 3. Position-independence policy

If a target artifact is implemented later, all reachable Stage-0 code and its
referenced data must satisfy these constraints:

- Use only PC-relative in-image code/data references. Audit the final linked
  instructions; compiler flags alone do not prove PIC.
- Do not embed target PA/VA constants, absolute pointers, guessed DRAM bounds,
  or identity-map assumptions.
- Do not rely on GOT/PLT, TLS, dynamic linking, an interpreter, unresolved
  symbols, or loader-applied dynamic relocations.
- The final linked ELF must contain no unresolved symbols and no remaining
  static or dynamic relocation entries. `readelf -r` alone is insufficient:
  disassembly and relocation/linker-map review must also establish that
  references are position-relative rather than absolute values resolved at
  one fixed link address.
- Keep the contiguous image span **strictly below 1 MiB** as a project design
  cap, then have the linker and static audit reject any out-of-range
  PC-relative reference. The cap is chosen to keep local ADR-sized references
  within their architectural reach; it is not a T8006 memory limit, safe load
  size, or hardware fact. Branch veneers and all compiler/linker-generated
  references must still be inspected.
- The final image must be deterministic for a fixed source revision and
  toolchain. The manifest records the exact inputs rather than asserting
  authenticity or target residency.

Arm documents ADR/PC-relative reach and the distinction between static and
dynamic ELF relocations; the exact generated artifact must still be audited
with the selected toolchain [1][2].

## 4. Proposed target artifact and outputs

The future artifact name is `stage0_target.elf`; its entry symbol is proposed
as `_stage0_entry`. These are **DESIGN names only**: neither target source nor
that symbol exists in the current tree. The ELF should be AArch64, ELF64,
little-endian, freestanding, with no libc, no dynamic dependencies, and no
undefined symbols.

When a real artifact can be built from a reviewed target source/ABI, preserve
these outputs together:

| Output | Required contents |
|---|---|
| `stage0_target.elf` | Exact linked target bytes and ELF metadata. |
| Linker map | Input objects, symbol placement, segment/section bounds, and discarded sections. |
| Symbol inventory | Sorted symbols including `_stage0_entry`, section bounds, BSS bounds, and any explicit scratch/data symbols. |
| ELF report | `readelf -h -l -S -r -d`; machine/type, entry, segments, sections, relocations, and dynamic tags. |
| Disassembly | Linked target instructions for all executable sections, including entry and any linker veneers. |
| Undefined/relocation audit | Machine-readable empty undefined-symbol and relocation sets, or a failed build. |
| SHA-256 and size | Exact local ELF identity only. |
| Build manifest | Source commit, source/dependency hashes, compiler/linker versions, exact flags/commands, ELF hash/size, audit-output hashes, and explicit `target_resident=false`, `launch_method=UNRESOLVED`. |

A flat BIN is **not justified by the current evidence**. It discards ELF entry,
segment, permission-intent, and bounds metadata and can obscure whether
relocations were required. Emit one only if a later reviewed consumer requires
it; preserve the ELF and bind the BIN hash/size to the same build manifest.
Neither format's hash proves that bytes were placed on or fetched by the Watch.

Do not create `stage0_target_manifest.json` until an actual target artifact
exists. A template may not fill in a fabricated hash, entry, or source identity.

## 5. Linker and section contract

The following is the proposed future contract, not a current linker script:

- **Entry:** `_stage0_entry`, an A64 instruction address aligned to 4 bytes.
  Runtime entry VA/PC is supplied only by a separately reviewed launch
  contract; no numeric value is assigned here.
- **Image span:** strictly less than 1 MiB, enforced by a linker assertion and
  independently checked from ELF loadable segments.
- **Section ordering:** entry/text, remaining text, read-only data, initialized
  writable data, then optional BSS. Keep executable and writable sections in
  separate ELF load segments; no segment may be both writable and executable.
- **Alignment:** instruction-entry alignment is 4 bytes. Segment and mapping
  alignment must be compatible with the actual ELF load layout and the
  independently established runtime translation granule. The granule is not
  assumed to be 4 KiB, 16 KiB, or 64 KiB here.
- **Permissions:** intended ELF flags are R-X for code, R-- for read-only
  data, and RW- for writable data/BSS. ELF flags express image intent; they do
  not create or prove hardware page-table permissions.
- **BSS:** absent unless needed. If present, its zeroing interval, write
  permission, exclusive ownership, and non-collision must be proven before
  clearing it. The artifact must not clear arbitrary or unproven memory.
- **Stack:** do not assume the incoming SP is valid. The entry prefix must be
  stackless until a separately proven, aligned, writable, exclusively owned
  Stage-0 stack is established. The stack is external runtime input, not a
  guessed linker-reserved target address.
- **Relocations:** final target ELF has no runtime relocations, GOT/PLT,
  interpreter, or undefined imports. Any deviation fails the proposed strict
  PIC policy and requires a separately reviewed design.
- **CPU state:** the source must declare every required incoming state and
  instruction privilege. Reading EL1 system registers requires an independently
  proven EL1 precondition. DAIF, translation state, caches, exception routing,
  and output access cannot be inferred from a successful ELF build.
- **Side effects:** target implementation must not write MMIO, page tables,
  persistent storage, firmware, or flash as part of this artifact contract.
  Any RAM writes must have explicit bounded ranges and independently proven
  ownership/permissions. This specification implements no such writes.

## 6. External inputs intentionally unresolved

These values must come from a separately reviewed, target-specific launch and
evidence contract. None may be filled from historical research constants or
from this document:

| Input | Required before a useful target artifact can be finalized/entered | Current status |
|---|---|---|
| Stage-0 physical deposit range and byte ownership | Exact PA interval, capacity, exclusive ownership, collision coverage, and binding to the reviewed ELF bytes. | **UNKNOWN / BLOCKED** |
| Runtime execution VA/PC | Actual entry address and address-space regime; for PIC, the load bias/runtime base and exact entry offset. | **UNKNOWN / BLOCKED** |
| Initial instruction-fetch proof | Resident-byte identity, executable mapping or justified alternative regime, translation details where applicable, and I-cache visibility/coherency. | **BLOCKED** |
| Incoming CPU/exception state | EL/A64 state and all privilege/trap/exception assumptions used before Stage-0 can safely observe or normalize them. | **UNKNOWN / BLOCKED** |
| Stage-0 stack | Proven bounds, alignment, writability, ownership, and collision-free interval—or a reviewed stackless prefix up to a separately proven stack switch. | **UNKNOWN / BLOCKED** |
| Scratch/evidence-output buffer | Bounded address/range, writable authority, ownership, capacity, and a reviewed way to retrieve its contents. | **UNKNOWN / BLOCKED** |
| MMU evidence buffer/table bytes | Independently bounded readable source and sufficient capacity/coverage. Stage-0 cannot assume it may read arbitrary table pages. | **UNKNOWN / BLOCKED** |
| Descriptor destination | If a descriptor is prepared, separately proven writable storage and later kernel-readable 128-byte prefix. V1 remains unchanged. | **UNKNOWN / BLOCKED** |
| Capture/session provenance | Capture ID, bounded timestamps, producer/source, image/artifact hashes, complete coverage, and same-session binding. | **BLOCKED** (EV-000B) |
| Launch method and stop/failure behavior | Exact target/build compatibility, all RAM/CPU/cache/control-flow effects, persistence review, bounded abort behavior, and recovery uncertainty. | **BLOCKED** |

The unavailable stage-0 *behavioral ABI* is also a build blocker: there is no
approved target entry contract specifying which incoming registers carry
inputs, what can be observed without dereference, how runtime evidence is
serialized, or how the result is retained. The host reference defines record
shapes and gate semantics; it does not define target instructions or a safe
output interface. Writing a placeholder loop or invented register/output ABI
would not close this gap.

## 7. What this step does and does not close

This specification records a preferred **DESIGN** for a future target
artifact. It does not create target source, an AArch64 ELF/BIN, a target hash,
or a launch recipe.

| Requirement | Result |
|---|---|
| Compare fixed, PIC/PIE, and external-relocation strategies | **DESIGN — completed in this document** |
| Preferred position policy | **DESIGN — strict PIC/PIE; no final runtime relocations** |
| Target AArch64 artifact existence/hash | **NOT CLOSED** — no meaningful target implementation/build |
| Target entry symbol/section bounds/permissions audit | **NOT CLOSED** — proposed contract only |
| Target placement, execution VA, fetch mapping, ownership | **BLOCKED** |
| Incoming EL/stack/CPU/MMU/cache state | **UNKNOWN / BLOCKED** |
| Evidence output/session binding and EV-000B | **BLOCKED** |
| Pre-Stage-0 launch method/effects/recovery review | **BLOCKED** |
| First Stage-0 execution | **NOT READY** |
| First DreyzeOS kernel entry | **NOT READY** |
| Loader contract / first hardware execution | **BLOCKED / NOT READY** |

The next useful dependency is an independently reviewable pre-Stage-0
execution window and launch/effects contract for one exact artifact. This
document intentionally does not propose an acquisition or launch mechanism.

## References

1. Arm, *Armv8-A Instruction Set Overview* — PC-relative `ADR`/`ADRP` reach:
   <https://developer.arm.com/-/media/Files/pdf/graphics-and-multimedia/ARMv8_InstructionSetOverview.pdf>
2. Arm, *ELF for the Arm 64-bit Architecture (AAELF64)* — static versus
   dynamic relocation model:
   <https://github.com/ARM-software/abi-aa/blob/main/aaelf64/aaelf64.rst>
3. Repository evidence/design: `docs/LOADER_ENTRY_CONTRACT.md`,
   `research/t8006_evidence/STAGE0_BOOTSTRAP_CONTRACT.md`,
   `research/t8006_evidence/STAGE0_REFERENCE_ARTIFACT_AUDIT.md`,
   `DreyzeOS.ld`, and `Makefile`.

## Final gate

```text
TARGET STAGE0 SPEC DEFINED = DESIGN
TARGET STAGE0 ARTIFACT BUILT = NO
TARGET ADDRESSES ASSIGNED = NO
FIRST_STAGE0_EXECUTION = NOT READY / BLOCKED
FIRST_DREYZEOS_KERNEL_ENTRY = NOT READY
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

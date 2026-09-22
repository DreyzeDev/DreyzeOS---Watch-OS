# DreyzeOS Loader Entry Contract — Phase 4 Step 2.9

**Target**: Watch4,2 / N131bAP / Apple S4 T8006 / watchOS 10.6.1 (21U580)
**Status**: DESIGN / HOST ONLY
**Safety boundary**: no device execution, exploit execution, payload delivery,
MMIO, UART/AIC access, framebuffer write, flash write, or control transfer was
performed.

## Purpose

The Step 2.9 model turns the current loader unknowns into an explicit,
machine-checkable precondition set. It is not a loader and it does not make
the target READY. The implementation is in
**tests/loader_entry_contract.h** and
**tests/loader_entry_contract.c** and is exercised by the native host C
harness.

A numeric address is a fact candidate only. It is never permission to read,
write, execute, or treat a physical address as a pointer.

## V1 remains unchanged

Loader Handoff ABI V1 remains exactly 128 bytes. The host contract is native
state and is not appended to, overlaid on, or serialized as V1.

V1 still carries only:

| Offset | Field |
|---:|---|
| 0x00 | magic |
| 0x08 | version |
| 0x0C | size |
| 0x10 | flags |
| 0x18 | entry_el |
| 0x20 | payload_pa |
| 0x28 | payload_va |
| 0x30 | payload_size |
| 0x38 | mmu_enabled |
| 0x40 | raw_x0 |
| 0x48 | raw_x1 |
| 0x50 | boot_args_range |
| 0x68 | device_tree_range |

The existing compile-time size and offset assertions remain authoritative.
The V1 VERIFIED flag is an assertion from an already trusted bootstrap; it is
not a readable-pointer proof, signature, mapping proof, or authority grant.

## Trust bootstrap sequence

The contract requires this sequence:

1. A future loader proves that the fixed 128-byte descriptor prefix is
   readable.
2. A minimal stage-0 copies exactly that prefix into trusted writable storage.
3. V1 structural validation runs only on the copy.
4. The native contract records the independently proven ranges and normalized
   CPU state.
5. The payload PA/VA intervals are derived from V1 and checked against those
   proven facts.
6. Collision checks cover loader-owned, descriptor, boot_args, DeviceTree,
   framebuffer, reserved, stage-0, and DreyzeOS stack ranges.
7. Only a future implementation may use the resulting READY decision. This
   host model never dereferences a nested pointer and never transfers control.

This is DESIGN until a target-specific loader proves step 1 and all later
facts in one internally consistent environment.

## Fact versus authority

The native range object has separate fields for:

- PRESENT and BOUNDS_PROVEN: the interval is claimed and its arithmetic is
  non-wrapping;
- READABLE, WRITABLE, and EXECUTABLE: the relevant access mapping is proven;
- OWNERSHIP_PROVEN: the loader has established that the interval is available
  for the claimed handoff.

The validator rejects zero-length and wrapping ranges, partial containment,
entry at the exclusive end, unaligned SP, and any permission request whose
authority flags are absent. The range helpers use [base, end) semantics:
adjacent intervals do not overlap and a one-byte boundary intersection does.

## Required native contract facts

| Contract area | Required proof | Current target status |
|---|---|:---:|
| Descriptor prefix | readable before copy, copied, structurally valid | BLOCKED |
| Entry EL | proven and normalized to EL1 | BLOCKED |
| Initial SP | proven, 16-byte aligned, inside writable stack interval | BLOCKED |
| DAIF | normalized/proven before handoff | BLOCKED |
| SCTLR/MMU | regime and enabled state known; policy normalized | BLOCKED |
| TTBR0/TTBR1/TCR/MAIR | roots and attribute policy proven or normalized | BLOCKED |
| I-cache/D-cache | state and maintenance policy known | BLOCKED |
| VBAR/FP-SIMD | handoff assumptions proven | DESIGN |
| Stage-0 mapping | executable virtual interval proven | BLOCKED |
| Kernel mappings | executable, readable, writable data/BSS/stack intervals proven | BLOCKED |
| Payload PA/VA/size | fixed-width facts converted without truncation and owned | BLOCKED |
| Entry PC | representable and strictly inside executable payload interval | BLOCKED |
| Runtime DRAM | provenance is RUNTIME_VERIFIED, not static fallback | BLOCKED |
| boot_args/DeviceTree | complete independently readable bounded intervals when used | BLOCKED |
| Framebuffer | reservation present/absent is known; range excluded if present | BLOCKED |
| Reserved memory | complete interval list and ownership are proven | BLOCKED |
| Collision audit | all relevant same-address-space protected intervals excluded | BLOCKED |
| Control transfer | bounded transfer to the agreed DreyzeOS entry is proven | BLOCKED |
| Persistence | no persistent-storage write is required | DESIGN only |

The status of a native field does not override the target evidence status.
For example, a host fixture may set RUNTIME_VERIFIED to exercise the
validator, but that does not prove the Watch runtime map.

## Validator rejection model

The validator returns a specific status rather than a bool. Important classes
are:

- descriptor unreadable, not copied, not trusted, or structurally invalid;
- wrong or unproven entry EL;
- missing stack, DAIF, translation, cache, or mapping proof;
- payload PA/VA/size representation, overflow, or DRAM containment failure;
- entry outside the payload or at its exclusive end;
- missing boot_args or DeviceTree bounds;
- missing or overlapping protected/reserved intervals;
- non-runtime memory provenance;
- persistent-write requirement;
- missing control-transfer proof.

It performs no raw pointer probing, no untrusted memcpy, no MMIO, no inline
assembly, no function-pointer invocation, and no branch to a payload address.

## Range and collision model

The validator handles separate physical and virtual address spaces. A proposed
payload must be excluded from every protected interval in the matching space:

- stage-0 executable mapping;
- loader code, loader stack, and optional loader heap;
- descriptor source and descriptor copy storage;
- boot_args and DeviceTree;
- framebuffer reservation;
- reserved-memory intervals;
- DreyzeOS kernel stack.

Kernel executable/readable/writable mappings are mapping witnesses, not
collision exclusions: the payload is expected to be contained by the kernel
executable and readable virtual mappings, while its stack and BSS must be
contained by the writable mapping.

The model deliberately does not contain a T8006 “safe load address”. The
valid host fixture uses synthetic addresses only.

## CPU normalization decision

The preferred DESIGN is for a future loader/shim to normalize the state before
handoff:

- enter at EL1;
- establish a known aligned writable stack;
- define DAIF behavior;
- define SCTLR/MMU and translation policy;
- provide owned TTBR0/TTBR1/TCR/MAIR policy or a documented disabled-MMU
  state;
- perform the required I-cache/D-cache maintenance;
- provide executable stage-0 and kernel mappings;
- leave VBAR/FP-SIMD assumptions explicit.

V1 can remain stable if the loader performs this normalization externally.
Raw register values in a larger descriptor would still not prove mappings or
ownership. Therefore **ABI V2 NEEDED NOW = NO**. A V2 proposal remains a
documentation option only if a future loader cannot normalize the state; V1
must not be silently changed.

## Architecture comparison

| Architecture | Current evidence | Unknowns introduced | Decision |
|---|---|---|---|
| A. Fixed non-PIC kernel | Current AArch64 flags include no-pie/no-pic; linker VMA is 0x100000000; ADR/ADRP and direct in-image references are resolved at link time; relocations are zero | exact PA/VMA mapping and loader placement must match | Retain as current kernel; hardware use BLOCKED |
| B. Tiny PIC stage-0 plus fixed kernel | A bounded host model can compute a runtime delta and target entry after explicit mapping/range proofs; the fixed kernel remains simple and auditable | a real stage-0 still needs executable mapping, writable storage, CPU normalization, payload placement, and a control-transfer proof | Preferred future architecture DESIGN; current implementation HOST ONLY |
| C. Fully PIC kernel | Could reduce VMA dependence | requires PIC-safe assembly, global/static access audit, BSS/stack/vector relocation policy, mapping policy, and a new validation surface | Not selected; no evidence justifies the larger change |

The current objdump proves link-time instruction placement, not arbitrary
relocation. Zero relocations means the static linker resolved references; it
does not mean PIC.

## Current hardware evidence

The exact static ADT artifact records /memory as base 0 and size 0. Product
RAM quantity is separate research context. Historical values such as
0x800000000 and 1 GiB are not runtime DRAM evidence and cannot satisfy the
contract's runtime memory provenance or payload placement proof.

Static MMIO reg values are physical-register evidence only. They do not prove
a current virtual mapping. The production MMIO gate and framebuffer mapping
gate remain closed, and the production framebuffer virtual base remains zero.

The XNU boot_args layout is evidence about the researched XNU consumer. It is
not the DreyzeOS loader ABI. A future descriptor must provide independent
bounded ranges before any nested boot_args or DeviceTree object can be read.

## Exact next evidence

To change the readiness state, one target-specific, reproducible loader/shim
artifact must close all of these together:

1. payload deposit PA, alignment, bounded size, and ownership;
2. payload execution VA and entry PC, or a genuinely PIC initial stage;
3. EL1, SP, DAIF, SCTLR/MMU, TTBR0/TTBR1/TCR/MAIR, and cache policy;
4. executable/readable/writable mappings for stage-0, descriptor, payload, and
   DreyzeOS data/stack;
5. descriptor prefix readability and copy location;
6. runtime boot_args/DeviceTree bounds;
7. framebuffer and reserved-memory intervals;
8. collision exclusion in both relevant address spaces;
9. a bounded control-flow transfer to the agreed entry;
10. no persistent-write requirement.

Public usbliter8 and Peepo artifacts remain static research evidence only.
Neither is a DreyzeOS loader contract.

## Readiness result

The validator and its negative tests are **DESIGN / HOST ONLY**. They reduce
ambiguity but do not close target hardware evidence. Any missing hardware
critical fact keeps the gate closed.

**LOADER CONTRACT = BLOCKED**

**FIRST HARDWARE EXECUTION = NOT READY**

## Step 2.10 offline translation evidence

The host-only `tools/mmu_snapshot_analyzer.py` can decode a future local
AArch64 translation-table snapshot and report mapping facts for this native
contract. It does not change the contract state automatically.

A complete mapping report may support a future review of:

- kernel executable/readable/writable intervals;
- the entry PC and stack VA;
- descriptor, boot_args, DeviceTree, framebuffer, and protected ranges.

The report remains evidence from a supplied snapshot. It does not prove that the
snapshot is live, that the loader owns the interval, that a descriptor is
trusted, that a payload was deposited, or that control can transfer safely.
The bridge therefore leaves ownership, descriptor trust, collision completion,
entry proof, and control-transfer proof false.

The snapshot format is documented in
[research/mmu_snapshots/FORMAT.md](../research/mmu_snapshots/FORMAT.md).
The current Watch4,2 static artifacts contain no runtime table snapshot, so the
analyzer reduces future evidence ambiguity but does not move any hardware gate.

## Step 2.11 unified evidence verification

`tools/handoff_evidence_verifier.py` now orchestrates the V1 descriptor audit,
CPU/MMU consistency checks, the Step 2.10 snapshot walker, ELF interval audit,
bounded object parsing, and physical/virtual collision analysis. Its graph
keeps mapping facts separate from ownership, descriptor trust, collision
completeness, and control-transfer authority. The bundle format is documented
in [research/handoff_evidence/FORMAT.md](../research/handoff_evidence/FORMAT.md)
and the verifier behavior in
[HANDOFF_EVIDENCE_VERIFIER.md](HANDOFF_EVIDENCE_VERIFIER.md).

A synthetic bundle may validate the offline model, but it is DESIGN evidence
only. The Watch4,2 target remains `LOADER CONTRACT = BLOCKED` and
`FIRST HARDWARE EXECUTION = NOT READY`.

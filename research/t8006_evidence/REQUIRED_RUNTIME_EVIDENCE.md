# T8006 required runtime evidence

Phase 4 — Step 2.12, target-specific evidence gap inventory.

This document is the human-readable companion to
[`requirements.json`](requirements.json). It describes the evidence that is
still missing before a future, target-bound loader/shim can be evaluated. It
does not describe an exploit, a USB/DFU operation, a memory writer, or a
hardware capture procedure.

## Current conclusion

The repository contains offline verification infrastructure and one sanitized
extraction from a user-reported, pre-existing watchOS Analytics diagnostic
report. The raw file's local SHA-256 and size were verified before parsing.
Its contents identify Watch4,2 / Watch OS 10.6.1 (21U580) / ARM64_32 and
include AppleT8006CLPC, AppleT8006IO, and AppleT8006PMGR symbols in a
stackshot. The sanitized record is
[`observed_watchos_report.json`](observed_watchos_report.json); the raw IPS and
private correlation values are not committed.

This report is **not** an independently attested target-bound runtime capture:
its export origin is user-reported, its model/build fields do not prove the
physical Watch identity, and it contains no DreyzeOS CPU/MMU/RAM/loader
evidence. EV-000 therefore remains **BLOCKED**. Existing synthetic MMU and
handoff bundles remain repository-owned `DESIGN` fixtures only.

The exact static ADT evidence remains:

```text
/memory:      base = 0, size = 0
/vram:        zero-filled placeholder
/chosen/memory-map: no runtime DRAM values in the static artifact
```

Therefore product RAM quantity, static physical-device ranges, and a runtime
DRAM map remain different facts. Runtime DRAM base/size is **BLOCKED**. The
fixed kernel VMA `0x100000000` is a linker placeholder for the current
non-PIC image, not a proven target load address.

## Evidence groups

The minimum future evidence set is grouped so that a capture can be checked
for completeness without guessing a preferred acquisition path:

| Group | Required contents | Current state |
|---|---|---|
| `TARGET_PROVENANCE` | target-bound identity/provenance for all artifacts | BLOCKED |
| `CPU_STATE` | EL1, SP, DAIF, translation/cache/vector/FP normalization facts | BLOCKED / UNKNOWN |
| `MMU_STATE` | proven TCR/TTBR/MAIR/SCTLR plus complete table-page bytes | BLOCKED |
| `RUNTIME_MEMORY` | runtime-authoritative DRAM interval and provenance | BLOCKED |
| `PAYLOAD_PLACEMENT` | payload PA/VA/size, ownership, alignment/limit | BLOCKED / UNKNOWN |
| `MMU_MAPPINGS` | executable/readable/writable mapping evidence for image and stack | BLOCKED |
| `DESCRIPTOR_TRUST` | readable 128-byte prefix and trusted copy proof | BLOCKED |
| `BOOT_METADATA` | bounded, complete boot_args/DeviceTree evidence when consumed | BLOCKED |
| `FRAMEBUFFER` | explicit runtime framebuffer reservation or proven absence | BLOCKED |
| `COLLISION_AUDIT` | complete protected/reserved intervals and collision result | BLOCKED |
| `LOADER_TRANSFER` | target-specific control-transfer contract | BLOCKED |
| `SAFETY_POLICY` | explicit no-persistent-write fact for the actual path | DESIGN |
| `BUNDLE_COMPLETENESS` | one consistent, hashed, target-bound evidence bundle | BLOCKED |

## Requirement matrix

`[base, base + length)` is the interval convention. `PROVEN` means an
independent evidence fact is present; a non-zero address, matching string,
SHA-256 match, descriptor `VERIFIED` bit, or synthetic translation does not
create proof or access authority.

| ID | NAME | CURRENT STATUS | CURRENT EVIDENCE | MISSING EVIDENCE | SOURCE NEEDED | VERIFIER NODE | CRITICAL FOR FIRST HANDOFF? | CLOSURE CONDITION |
|---|---|---|---|---|---|---|---|---|
| EV-000 | Target identity provenance | BLOCKED | User-observed metadata plus a sanitized pre-existing report describing Watch4,2 / 21U580; report origin and physical identity are not independently attested | Independent identity attestation and per-artifact binding for the required image, descriptor, and MMU snapshot | Target-bound provenance record | `target_identity_proven` | YES | Metadata matches and identity is explicitly attested; synthetic remains DESIGN |
| EV-001 | Loader transfer protocol | BLOCKED | No selected DreyzeOS loader/shim | Non-persistent handoff protocol and control-transfer proof | Future loader/shim contract | `control_transfer` | YES | Bounded entry, documented transfer, no guessed branch primitive |
| EV-002 | Runtime DRAM base/size | BLOCKED | Static `/memory` is `0,0`; historical 1 GiB is research context only | Runtime-authoritative base, size, provenance | Runtime memory-map capture | `runtime_memory_provenance` | YES | Both facts proven with `RUNTIME_VERIFIED` provenance |
| EV-003 | Payload physical placement | BLOCKED | No target payload deposit record | PA, size, RAM containment, collision result | Loader placement record | `payload_pa_proven` | YES | Proven interval inside proven runtime RAM |
| EV-004 | Payload alignment/maximum | UNKNOWN | ELF size is locally measurable; copy primitive limit is not known | Target-specific alignment and maximum transfer size | Copy primitive contract | `payload_size_bound` | YES | Actual image satisfies explicit limit/alignment |
| EV-005 | Payload VA/entry PC | BLOCKED | Fixed non-PIC linked VMA only | Canonical executable VA and entry PC under one regime | MMU snapshot plus loader record | `payload_va_proven` | YES | VA/PC agree with ELF and executable walk |
| EV-006 | Entry EL1 | BLOCKED | Source requires external EL1 precondition | Target-specific incoming EL proof | CPU-state record | `entry_el1` | YES | Current EL and descriptor both prove EL1 |
| EV-007 | Initial SP/stack | BLOCKED | Linker symbols describe a design range only | Incoming aligned SP, writable mapping, ownership | CPU/stack record plus MMU snapshot | `initial_sp`, `stack_mapping` | YES | Full stack is proven writable/readable and collision-free |
| EV-008 | DAIF normalization | BLOCKED | Entry code masks DAIF after valid EL1 entry | Incoming/normalized DAIF evidence | CPU-state record | `daif_normalized` | YES | Normalization explicitly proven |
| EV-009 | MMU register state | BLOCKED | No live target register snapshot | SCTLR/TCR/TTBR0/TTBR1/MAIR and policy | CPU register snapshot | `translation_policy`, `mmu_register_provenance` | YES | All registers proven and sources agree |
| EV-010 | Cache/vector/FP state | UNKNOWN | Architecture design notes only | I/D-cache, VBAR, FP/SIMD normalization | Loader normalization record | `cache_policy` | YES | Each policy is explicit and consistent |
| EV-011 | Executable/readable mappings | BLOCKED | Synthetic analyzer fixtures only | Complete table bytes and walks for stage-0, entry, text, vectors | MMU snapshot | `stage0_executable_mapping`, `kernel_executable_mapping` | YES | Whole intervals mapped with required permissions |
| EV-012 | Writable kernel/stack mappings | BLOCKED | ELF intent only | Complete writable data/BSS/stack walks | MMU snapshot | `kernel_writable_mapping`, `stack_mapping` | YES | Whole intervals map writable/readable |
| EV-013 | Descriptor prefix/trusted copy | BLOCKED | V1 structural model; no live readable address | Independent 128-byte readability and copy proof | Loader descriptor record | `descriptor_root_of_trust` | YES | Readability precedes validation; exact prefix is copied |
| EV-014 | boot_args/DT bounds | BLOCKED | Static artifacts and bounded parser only | Runtime ranges, complete bytes, nested bounds | Runtime metadata capture | `boot_args_bounds`, `device_tree_bounds` | YES if consumed | Ranges/bytes are complete and independently bounded |
| EV-015 | UART/AIC VA mapping | UNKNOWN | Static ADT gives physical registers only | Snapshot VA-to-PA evidence, if ever needed | MMU snapshot | Optional, no access authority | NO for current closed path | Mapping proven separately from permission to access |
| EV-016 | Framebuffer reservation/mapping | BLOCKED | Static `/vram` is zero-filled | Explicit runtime reservation/absence and optional mapping | Runtime reservation record | `framebuffer_reservation` | YES | No guessed address; reservation and collisions proven |
| EV-017 | Reserved-memory completeness | BLOCKED | Known ranges are incomplete without capture | Complete protected/reserved interval set | Reservation capture | `reserved_memory_completeness` | YES | Completeness explicitly proven |
| EV-018 | Payload collision audit | BLOCKED | Host range helpers and synthetic fixtures | Actual payload vs every protected range | Placement + reservation records | `collision_audit` | YES | No overlap, no wrap, complete inputs |
| EV-019 | Payload ownership | BLOCKED | Mapping does not imply ownership | Ownership/lifetime after transfer | Loader ownership record | `payload_ownership` | YES | Loader will not reclaim/overwrite interval |
| EV-020 | Descriptor access authority | BLOCKED | `VERIFIED` is assertion only | Bootstrap readable mapping independent of descriptor | Loader proof record | `descriptor_root_of_trust` | YES | No raw pointer is trusted from the prefix |
| EV-021 | Translation/payload consistency | BLOCKED | No target snapshot | PA/VA/PC agreement and MMU-enabled consistency | Descriptor + MMU snapshot | `payload_translation_consistency` | YES | Same proven regime translates the declared image |
| EV-022 | Control-flow proof | BLOCKED | No loader exists | Exact non-persistent transfer contract | Future loader/shim record | `control_transfer` | YES | Entry PC and transfer mechanism are proven |
| EV-023 | No persistent write | DESIGN | DreyzeOS design forbids flash/NAND/NOR writes | Explicit false fact for actual future path | Loader safety record | `no_persistent_write` | YES | `persistent_write_required=false` is proven |
| EV-024 | Snapshot target binding | BLOCKED | Synthetic manifest target is DESIGN | Snapshot target fields must match bundle | Snapshot manifest | `mmu_snapshot_target_match` | YES | No internal target conflict |
| EV-025 | Table-byte coverage | BLOCKED | Synthetic table bytes only | Complete bytes for every walked table page | Physical-memory dump manifest | `mmu_snapshot_present` plus mapping nodes | YES | No missing/truncated table page |
| EV-026 | Runtime boot metadata capture | BLOCKED | Static DT is not runtime bounds | Complete runtime boot_args/DT when used | Runtime metadata capture | `boot_args_bounds`, `device_tree_bounds` | YES if consumed | Independent bounded object evidence |
| EV-027 | Complete evidence bundle | BLOCKED | Repository synthetic bundles only | Consistent target-bound bundle covering all critical artifacts | Bundle manifest and hashes | `bundle_integrity`, `cpu_consistency` | YES | All critical facts proven with no conflicts |

## What would close the current gap

The next useful evidence is not another architectural analogy or another
synthetic fixture. It is one internally consistent, target-bound, offline
bundle containing the artifacts named by the groups above: independently
attested target metadata; CPU state; complete page-table pages for every
required walk; runtime DRAM and reservation ranges; descriptor/boot metadata
copies with bounds; payload placement/ownership; and a documented control
transfer contract. The bundle must be analyzable without dereferencing any
captured pointer.

No acquisition or delivery procedure is specified here. The safety boundary
remains host/offline-only.

## Readiness gate

Until every critical dependency is proven in the same internally consistent
environment:

```text
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

The evidence-gap tool can report that the offline infrastructure is complete
and that the pipeline is ready to consume evidence. That is a tooling status,
not target readiness.

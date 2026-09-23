# Unified Offline Handoff Evidence Verifier

Phase 4 Step 2.11 adds `tools/handoff_evidence_verifier.py`. It is a
deterministic host/offline orchestration layer for a local evidence bundle.
It connects the fixed Loader Handoff ABI V1 checks, the Step 2.9 entry
contract model, the Step 2.10 MMU snapshot analyzer, DreyzeOS ELF analysis,
bounded boot_args/DeviceTree parsing, and physical/virtual collision checks.

It is not a loader. It cannot deliver bytes, open a mapping, execute a
payload, branch to an evidence-provided address, read device memory, write
MMIO, access UART/AIC/framebuffer, run DFU, or invoke usbliter8/Peepo.

## Invocation

The input is a local JSON bundle in the format documented at
[research/handoff_evidence/FORMAT.md](../research/handoff_evidence/FORMAT.md):

```sh
python3 tools/handoff_evidence_verifier.py --help
python3 tools/handoff_evidence_verifier.py --bundle /path/to/bundle.json --json
python3 tools/handoff_evidence_verifier.py --bundle /path/to/bundle.json --human
python3 tools/handoff_evidence_verifier.py --bundle /path/to/bundle.json --human --strict
```

A syntactically valid bundle returns exit code 0 even when the loader contract
is BLOCKED. `--strict` returns 1 when the offline contract is blocked. A
malformed bundle, unsafe path, unsupported schema, or unrecoverable local
artifact error returns 1. Neither exit code means that hardware is safe.

The JSON report is the authoritative machine-readable result. The human
report is a concise view of the same evidence graph and blockers.

## Verification pipeline

The verifier uses one deterministic sequence:

1. validate schema and AArch64 architecture;
2. resolve only relative paths inside the bundle directory;
3. compare SHA-256 declarations for the ELF, MMU manifest, and V1 descriptor;
4. compare target metadata with Watch4,2/N131bAP/T8006/21U580 expectations;
5. parse and structurally validate exactly the 128-byte V1 descriptor prefix;
6. load the existing MMU snapshot analyzer, including its TCR/MAIR and table
   walk logic;
7. parse the ELF and compare its linked intervals with supplied translations;
8. compare independently proven CPU facts with snapshot registers;
9. validate bounded runtime memory, boot_args, DeviceTree, and range facts;
10. perform separate physical and virtual collision audits;
11. require explicit control-transfer and no-persistent-write facts;
12. emit dependency nodes, provenance, warnings, and exact blockers.

The verifier exposes `TARGET_METADATA_STATUS` (EV-000A),
`SAME_SESSION_PROVENANCE_STATUS` (EV-000B), `PHYSICAL_IDENTITY_STATUS`
(EV-000C), and `TECHNICAL_TARGET_PROVENANCE_READY` (A+B). Physical identity
does not gate first technical bring-up.

No stage dereferences a pointer from the bundle. All address arithmetic is
checked before it is used as an offline integer interval.

## Evidence graph and trust boundaries

Every important result is a node with:

- `status`: `CONFIRMED`, `LIKELY`, `DESIGN`, `UNKNOWN`, or `BLOCKED`;
- `proof_state`: `PRESENT`, `PROVEN`, `NOT_PROVEN`, or `NOT_APPLICABLE`;
- `reason`: the decision explanation;
- `evidence_sources`: machine-readable source labels;
- `depends_on`: prerequisite node names.

The graph deliberately separates facts from authority:

| Evidence | Can prove | Cannot prove by itself |
|---|---|---|
| SHA-256 | local bytes match a declaration | genuine Watch provenance |
| V1 `VERIFIED` bit | descriptor assertion is set | readable prefix, trusted copy, ownership |
| MMU translation | a supplied snapshot maps a VA to a PA | live state, ownership, safe access |
| ELF interval | intended linked image bounds/permissions | hardware page-table permissions |
| non-zero address | a numeric value exists | readable or executable memory |
| target strings | metadata matches expected target | capture identity |
| same-session artifact relationships | artifacts share one declared capture context | persistent identity or capture authenticity |
| no known collision | supplied intervals are disjoint | completeness of the protected list |

A conflict between two independently proven values is a hard
`EVIDENCE_CONFLICT` condition. The verifier never chooses the convenient
source. Unproven hints may remain `UNKNOWN` when they are not used as
authority.

## Descriptor and CPU checks

V1 remains unchanged at 128 bytes and its offsets are decoded directly from
the wire layout. The verifier checks magic/version/size, unknown flags,
reserved fields, entry EL, MMU value, payload PA/VA overflow, range bounds,
and mapping-flag dependencies. The `VERIFIED` bit is reported as
`verified_flag_is_assertion_only`.

The entry model requires separately proven EL1, 16-byte aligned SP, normalized
DAIF, a normalized translation policy, and cache/vector/FP-SIMD policy. A
descriptor MMU bit is compared with `SCTLR_EL1.M`; disagreement is a blocker.
The bundle's TCR/TTBR/MAIR facts are also compared with the MMU manifest when
both sides mark them proven.

V1 is intentionally not expanded to carry every CPU register. A future loader
may normalize CPU state externally and provide those facts in the evidence
bundle; the stable wire ABI remains a minimal handoff descriptor.

## MMU and ELF integration

The verifier imports `tools/mmu_snapshot_analyzer.py`; it does not implement a
second page-table walker. It asks that analyzer to walk the entry PC and all
required ELF section/symbol intervals. It reports partial/unmapped ranges,
PXN/UXN/AP permission failures, incomplete physical table bytes, physical
continuity, and ELF-intent mismatches. Writable `.rodata` is a security or
quality warning unless the future loader contract explicitly makes it a
blocker; an unmapped entry or non-writable stack is a blocker.

The linked kernel remains the current fixed non-PIC image at
`0x100000000`. A synthetic snapshot may show a complete mapping for tests,
but that result is `DESIGN` evidence. The current repository has no live
Watch translation snapshot, so no real load address is established.

## Object and collision checks

Local boot_args and DeviceTree files are optional. If required, their ranges
must match the V1 descriptor ranges. The known XNU ARM64 boot_args layout is
used only for bounded object consistency; it is not treated as the DreyzeOS
loader ABI. The nested DeviceTree pointer/length must fit the independent
DeviceTree range. The existing bounded ADT parser is loaded as a host module.

The collision engine uses `[base,end)` semantics and keeps physical and
virtual spaces separate. It checks the payload against stage-0, loader code,
loader stack/heap, descriptor source/copy, boot_args, DeviceTree, framebuffer,
kernel stack, reserved intervals, and explicit protected intervals. Adjacent
ranges do not overlap; one-byte overlap does. If the producer has not proven
the protected/reserved list complete, `collision_audit` stays BLOCKED.

Mapping proof is never converted into payload ownership, descriptor trust,
control transfer, or collision completeness.

## Readiness semantics

The report has two intentionally different outcomes:

- `offline_contract_result`: whether every critical *local evidence*
  dependency in this bundle is proven;
- `loader_contract` / `first_hardware_execution`: the target-facing gate,
  which additionally requires `CONFIRMED` source evidence, EV-000A metadata
  consistency, EV-000B same-session provenance, and every CPU/MMU/RAM/mapping/
  ownership/collision/descriptor/transfer/persistence gate. EV-000C physical
  identity is reported but does not gate first bring-up.

A complete repository-owned synthetic fixture may therefore report:

```text
OFFLINE CONTRACT RESULT = READY
HARDWARE EVIDENCE STATUS = DESIGN
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT_READY
```

For the current Watch4,2 research state, the exact static `/memory` artifact
still says `base=0,size=0`; runtime DRAM, a payload deposit, execution mapping,
EL1/SP/DAIF, live TTBR/TCR/MAIR/cache state, runtime object bounds, ownership,
and control transfer remain absent. The real target gate therefore remains:

```text
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

## Tests and limitations

`tests/test_handoff_evidence_verifier.py` builds repository-owned synthetic
bundles (no Apple firmware bytes) and checks a complete offline model plus
missing TTBR proof, register conflict, unmapped/PXN entry, read-only stack,
unaligned SP, DRAM containment, loader/DeviceTree overlap, incomplete
reservations, malformed/VERIFIED-only descriptors, nested object bounds,
incomplete snapshot, hash/target mismatch, MMU contradiction, missing control
transfer, persistence requirement, CLI exit behavior, and path traversal.

This suite validates the verifier's logic only. It cannot prove that a future
capture is genuine, that a mapping is live, or that any address is safe to
access. The provenance suite covers the A/B/C split and legacy v1 acceptance.
No QEMU, USB, DFU, exploit, or hardware dependency is required.

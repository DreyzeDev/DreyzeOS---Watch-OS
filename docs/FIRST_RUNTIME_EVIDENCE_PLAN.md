# First T8006 runtime evidence plan

Phase 4 — Step 2.13, Target Runtime Evidence Acquisition Gate.

This is a planning gate only. It is not a capture procedure, loader, exploit
plan, or authorization to interact with an Apple Watch.

## Accepted repository state

```text
Repository: DreyzeDev/DreyzeOS---Watch-OS
Branch:     master
Accepted:   e07b8cb04b2c337bbb43a5ab8d36ffc2a07e1cb9
Target:     Watch4,2 / N131bAP / T8006 / watchOS 10.6.1 / 21U580 / AArch64
```

Current static facts remain `/memory = base 0, size 0`, zero-filled `/vram`,
unknown runtime DRAM, and a fixed non-PIC kernel VMA of `0x100000000` that is
still only a linker placeholder.

```text
OFFLINE INFRASTRUCTURE = COMPLETE
EVIDENCE PIPELINE READY = YES
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

## Rules and dependency order

The 28 IDs in `research/t8006_evidence/requirements.json` are authoritative.
This plan reuses `dreyzeos.handoff_evidence.v1`, the Step 2.10 MMU snapshot
format, `tools/handoff_evidence_verifier.py`, and
`tools/t8006_evidence_gap.py`. No new verifier or capture tool is required.

Presence is not proof. SHA-256 proves local file equality, not Watch
authenticity. Target strings are not identity proof. A mapping is not ownership
or access authority. The V1 `VERIFIED` bit is not a root of trust. A partial
physical dump cannot prove complete table coverage or collision absence.

The dependency-first order is:

```text
target-bound provenance envelope
    -> CPU state and normalization
    -> MMU manifest and complete table pages
    -> runtime DRAM and reservation ranges
    -> descriptor and loader-contract record
    -> bounded boot_args/DeviceTree objects, when consumed
    -> control-transfer and persistence-safety record
    -> one hashed, conflict-free evidence bundle
```

The provenance envelope is first because every later artifact must be bound to
the same target and capture context. Preparing it is host-only; filling it
with target identity evidence requires a separately approved capture.

## Minimum future artifact set

One `bundle.json` may carry declarations and fact wrappers for all artifacts,
but it does not replace independent byte files. The minimum logical set is:

### 1. Provenance envelope and bundle manifest

IDs: `EV-000`, `EV-027`.

Required fields are schema, exact model/board/SoC/firmware/build/architecture,
source status, producer, capture ID/timestamp, a provenance relationship for
every artifact, relative paths, SHA-256 values, and explicit boolean
`metadata_match` and `identity_proven` facts. For a non-synthetic target
bundle, `provenance_envelope.coverage.coverage_complete` must be proven and
its per-artifact target-binding facts must cover at least `image`,
`handoff_descriptor`, and `mmu_snapshot`. Declare the ELF, exact 128-byte
descriptor, MMU manifest, all table blobs, and optional object copies.

The host-only preparation schema is now
`dreyzeos.target_provenance_envelope.v1`, embedded as
`bundle.provenance_envelope` or validated alone with
`tools/handoff_evidence_verifier.py --provenance-envelope`. Its per-artifact
presence, hash, target-binding, and runtime-proof facts are independent. The
legacy `target_provenance` fields are compatibility summaries only. The
sanitized template and synthetic/blocked mutation fixtures live under
`research/handoff_evidence/`; none contains target runtime evidence.

Completeness means every critical artifact is declared, hashed, present, and
covered by the same provenance record. Local validation is
`NO_DEVICE_INTERACTION`; real target binding is
`PRIVILEGED_RESEARCH_REQUIRED` until independently reviewed.

### 2. CPU-state and normalization record

IDs: `EV-006`, `EV-008`, `EV-009`, `EV-010`; contributes to `EV-021` and
`EV-024`.

Required independently proven or normalized facts:

```text
current_el, sp, daif
sctlr_el1, tcr_el1, ttbr0_el1, ttbr1_el1, mair_el1
vbar_el1, cpacr_el1
EL1, SP alignment/ownership, DAIF, translation, I-cache, D-cache,
VBAR, and FP/SIMD policies
```

Every value needs `value_present`, `value_proven`, and `source` semantics.
Proven disagreement with the MMU manifest or descriptor is
`EVIDENCE_CONFLICT`. The verifier consumes `bundle.cpu_state` and produces
`entry_el1`, `initial_sp`, `daif_normalized`, `translation_policy`,
`cache_policy`, and `cpu_consistency`.

Obtaining target state is `PRIVILEGED_RESEARCH_REQUIRED`. It may only be called
`READ_ONLY_DEVICE_INTERACTION` after a separate review proves that the method
cannot change device state.

### 3. MMU manifest and complete table-page evidence

IDs: `EV-009`, `EV-011`, `EV-012`, `EV-021`, `EV-024`, `EV-025`; optional
`EV-015` if UART/AIC mapping is later relevant.

Reuse the Step 2.10 manifest with proven SCTLR/TCR/TTBR0/TTBR1/MAIR facts,
target metadata, and physical-memory regions containing physical base, file,
offset, and length. Every table region used by every required walk must have
`memory_bytes_present=true` and `memory_range_complete=true`.

Required walks cover `_start`, `.text`, `.rodata`, `.data`, `.bss`, stack,
vectors, descriptor/metadata mappings, and any explicitly declared framebuffer
or MMIO query. Every level and descriptor page used by a walk must be present;
missing or truncated bytes remain `PHYSICAL_DUMP_INCOMPLETE`.

The existing verifier references this artifact through `bundle.mmu_snapshot`
and uses the existing analyzer. Local checking is `NO_DEVICE_INTERACTION`;
obtaining a target snapshot is `PRIVILEGED_RESEARCH_REQUIRED`.

### 4. Runtime memory, reservations, and ownership record

IDs: `EV-002`, `EV-003`, `EV-016`, `EV-017`, `EV-018`, `EV-019`; contributes
to `EV-007`, `EV-012`, and `EV-021`.

Required facts are runtime DRAM base/size with provenance exactly
`RUNTIME_VERIFIED`; payload PA/VA/size/alignment/limit; loader code/stack/heap;
stage-0; descriptor source/copy; boot_args; DeviceTree; framebuffer; kernel
stack; protected and reserved ranges; explicit physical/virtual address space;
ownership; and completeness of the protected/reserved list.

Use `[base, base + length)` with overflow checks. Adjacent ranges are allowed;
wrap, one-byte overlap, or incomplete protected ranges blocks the collision
audit. The verifier consumes `bundle.runtime_memory` and `bundle.ranges` and
produces `runtime_memory_provenance`, `payload_pa_proven`,
`payload_ownership`, `framebuffer_reservation`,
`reserved_memory_completeness`, and `collision_audit`.

Local preparation is `NO_DEVICE_INTERACTION`. Target runtime memory or
ownership evidence is `PRIVILEGED_RESEARCH_REQUIRED`; any method that writes,
reserves, or overwrites RAM is `POTENTIALLY_STATE_CHANGING` and stops here.

### 5. V1 descriptor and loader-contract record

IDs: `EV-001`, `EV-003`, `EV-004`, `EV-005`, `EV-006`, `EV-007`, `EV-008`,
`EV-013`, `EV-019`, `EV-020`, `EV-021`, `EV-022`, `EV-023`.

Required byte artifact and separate evidence fields:

* hashed `handoff_descriptor.bin`, exactly 128 bytes, with unchanged V1 wire
  layout;
* validated magic/version/size/flags/reserved fields, entry EL, MMU state,
  payload PA/VA/size, and bounded ranges;
* independent proof that the prefix was readable before validation and exactly
  128 bytes were copied to trusted storage;
* payload alignment/maximum bound, ELF `_start` agreement, ownership, and
  descriptor source/copy ranges;
* target-specific loader protocol, entry PC, and no-persistent-write facts
  outside the V1 layout.

`VERIFIED` remains assertion-only. It cannot prove readability, ownership,
identity, mapping, or control transfer. Any live action that creates or uses a
loader handoff is `UNKNOWN` until reviewed; deposit, CPU alteration, or branch
is `POTENTIALLY_STATE_CHANGING`, and storage writes are
`PERSISTENT_WRITE_RISK`.

### 6. Bounded boot_args and DeviceTree copies

IDs: `EV-014`, `EV-026` when either object is consumed.

Provide complete local `boot_args.bin` and `device_tree.bin` as needed, with
independent bounded ranges, declared lengths, completeness, readable proof,
and nested DeviceTree containment. Existing host parsers may check object
consistency; XNU `boot_args` is not the DreyzeOS loader ABI. Local validation is
`NO_DEVICE_INTERACTION`; obtaining target copies is
`PRIVILEGED_RESEARCH_REQUIRED` or `UNKNOWN` until the read path is reviewed.

### 7. Control-transfer and persistence-safety record

IDs: `EV-001`, `EV-022`, `EV-023`; contributes to `EV-005` and `EV-027`.

Required fields are bounded `entry_pc` agreeing with ELF `_start`, a
target-specific future handoff contract, independently proven
`control_transfer.proven`, and proven boolean
`persistent_write_required=false`. This record is data only. Any live control
transfer is `POTENTIALLY_STATE_CHANGING`; any persistent-write possibility is
`PERSISTENT_WRITE_RISK`; neither is authorized here.

## Safety classification matrix

| Future activity | Classification | Boundary |
|---|---|---|
| Hash local files, parse manifests, run verifier/gap tool | `NO_DEVICE_INTERACTION` | Permitted host-only work |
| Review static ADT, ELF, and repository artifacts | `NO_DEVICE_INTERACTION` | Does not access target state |
| Bind runtime files to exact target identity | `PRIVILEGED_RESEARCH_REQUIRED` | Strings and filenames are insufficient |
| Obtain CPU registers, page tables, RAM map, or boot metadata | `PRIVILEGED_RESEARCH_REQUIRED` | Runtime read method is not approved |
| Reviewed method proven strictly read-only | `READ_ONLY_DEVICE_INTERACTION` | Still requires explicit user approval |
| Deposit/overwrite RAM, alter CPU state, or transfer control | `POTENTIALLY_STATE_CHANGING` | RAM-only is not zero risk |
| Write flash/NAND/NOR or persistent state | `PERSISTENT_WRITE_RISK` | Immediate hard stop |
| Unknown capture or delivery mechanism | `UNKNOWN` | No safety claim may be inferred |

Every class other than `NO_DEVICE_INTERACTION` requires explicit user approval.

## Partial-artifact results

| Available artifact | It may establish | It cannot close |
|---|---|---|
| Provenance only | `EV-000` if independently attested | All CPU/MMU/RAM/placement/trust/mapping/collision/transfer gaps |
| CPU record only | EL1, SP, DAIF, register and policy facts | Table bytes, mappings, RAM ownership, descriptor authority, transfer |
| MMU snapshot only | Covered mapping and register facts; `EV-009/011/012/021/024/025` can progress | Live provenance, DRAM, ownership, descriptor trust, metadata, collisions, transfer |
| Memory/reservation record only | DRAM, reservations, ranges, and collision inputs | CPU/MMU state, mappings, descriptor trust, transfer |
| Descriptor/loader record only | V1 structure and declarations | Initial read authority, live mapping, RAM, ownership, identity, transfer proof |
| boot_args/DT copies only | Bounded object consistency | Every other critical requirement |
| Control/persistence record only | Safety assertions | Every physical, CPU, MMU, mapping, ownership, and provenance dependency |
| Complete conflict-free bundle | Offline verifier may report `OFFLINE CONTRACT RESULT = READY` | It still does not authorize hardware execution in this step |

`EV-015` is optional for the current closed path. If supplied, it remains
VA-to-PA mapping evidence and never opens UART/AIC gates.

## Existing processing commands

```bash
python3 tools/handoff_evidence_verifier.py \
  --bundle /path/to/bundle.json --json > verification.json
python3 tools/handoff_evidence_verifier.py \
  --bundle /path/to/bundle.json --human
python3 tools/t8006_evidence_gap.py \
  --verification verification.json \
  --requirements research/t8006_evidence/requirements.json --json \
  > evidence_gap.json
python3 tools/t8006_evidence_gap.py \
  --verification verification.json \
  --requirements research/t8006_evidence/requirements.json --human
```

Blocked evidence is a completed verification result, not a parser failure.
`--strict` is the optional non-zero gate for a blocked contract. These
commands never access a device, follow a captured pointer, execute a payload,
or open a production gate.

## Stop conditions

Stop immediately if the next step requires a real Watch connection, a method
not demonstrably read-only, RAM/CPU/MMIO/framebuffer/page-table/flash/USB/DFU
state change, payload delivery, or control transfer. Also stop on missing
target provenance, incomplete table bytes, proven-value conflict, incomplete
protected-range coverage, use of `VERIFIED` as read authority, or a proposed
schema/capture tool that has not had a separate host-only review.

Preserve the bundle as incomplete and report the exact requirement ID. Do not
advance statuses to create progress. Any action beyond
`NO_DEVICE_INTERACTION` requires explicit user approval that has not been
given in this step.

## Gate conclusion

This is the smallest dependency-complete plan. It performs no acquisition and
does not create a fake Step 2.14.

```text
OFFLINE INFRASTRUCTURE = COMPLETE
EVIDENCE PIPELINE READY = YES
NEXT ACTION REQUIRES TARGET-SPECIFIC DEVICE EVIDENCE
USER_APPROVAL_REQUIRED
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

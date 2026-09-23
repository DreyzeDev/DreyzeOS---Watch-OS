# Minimum Stage-0 Bootstrap Contract

Baseline: `7131fa3c774d04996d58b869e1161f4ed5fd6006` (`master`).
Status: **DESIGN / HOST ONLY**.

This document specifies a future, minimal bootstrap/observer boundary. It is
not stage-0 source or a launch method, does not authorize hardware activity,
and is not evidence that any proposed code is safe.

```text
EV-000A = CONFIRMED
EV-000B = BLOCKED
EV-000C = UNKNOWN / non-critical
PRE-STAGE0 GATE = BLOCKED
FIRST_STAGE0_EXECUTION = NOT READY
FIRST_DREYZEOS_KERNEL_ENTRY = NOT READY
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

No Watch or iPhone interaction, target-code execution, RAM/MMIO/register/page-
table write, control transfer, DFU/recovery, or persistent write was performed.
No actual target address or mapping is specified here.

## 1. Role and trust boundary

Stage-0 is a small, temporary bootstrap/observer. Its sole purpose is to
establish a bounded set of facts and, if every later gate passes, prepare the
DreyzeOS kernel-entry contract. It is not the kernel, not a general-purpose
loader, and not trusted merely because DreyzeOS authors produced it.

The phases are distinct:

1. **PRE-STAGE0 GATE:** independently justify the exact code, its first
   instruction fetch, its minimum memory footprint, required incoming CPU
   state, launch-method effects, and stop behavior.
2. **STAGE-0 OBSERVATION / PREPARATION:** stage-0 may collect runtime facts,
   construct bounded records, and perform only explicitly specified
   normalization.
3. **PRE-KERNEL-TRANSFER GATE:** all existing critical DreyzeOS kernel-entry
   requirements must be satisfied before any transfer to `_start`.
4. **POST-ENTRY VALIDATION:** separately establish whether the intended kernel
   entry actually occurred. A declaration or offline mapping report is not an
   observation of successful execution.

The current verifier's `first_stage0_execution` is deliberately NOT_READY
because the evidence bundle does not model or prove an independent
pre-stage-0 launch contract. Its kernel-entry gate remains separate and
unchanged in substance. A host-side verifier run after a capture cannot
retroactively prevent a transfer that has already happened. Before a future
transfer, either a reviewed in-stage-0 gate must enforce the contract or a
separately reviewed hold/validation boundary must ensure no transfer occurs
until the evidence is accepted. Neither mechanism currently exists.

### Evidence language

* **PRESENT** means a value or bytes were supplied.
* **PROVEN** means the stated source and method justify that fact for the
  claimed phase and target.
* **AUTHORITY** is separate: a proven number does not grant permission to
  access the addressed memory.
* A local SHA-256 establishes equality with declared local bytes only. It
  does not prove authorship, target residency, execution, or authenticity.
* A stage-0 self-report is evidence to review, not an independent trust root.
* A complete kernel MMU snapshot and a real V1 descriptor may be created
  after stage-0 starts. Neither is required to authorize stage-0's first
  instruction. The much smaller stage-0 entry window must be proven
  independently.

## 2. A — Inputs required before stage-0

The gate must be evaluated for one exact stage-0 artifact and one exact
target-specific launch proposal. An unknown effect or an unproven required
fact means **DO NOT START**.

| Input | Minimum acceptable evidence | Why it precedes stage-0 | Current status |
|---|---|---|---|
| Exact stage-0 identity | Source revision, complete source/dependency set, architecture, build toolchain/flags, linker inputs, binary length and digest; independent source-to-binary/build review. The bytes expected at the execution range must be bound to that artifact. | The first instruction cannot validate the identity of the code already being executed. A source hash alone does not bind bytes resident on target. | **BLOCKED** — no stage-0 source or binary exists. |
| Exact launch method and effects | A named, target/build-specific method reviewed for code delivery, memory writes, CPU/MMU/cache changes, control-flow effect, persistence, failure behavior, and all dependencies. No unknown side effect may be treated as harmless. | The method can change state before stage-0 has an opportunity to observe it. | **BLOCKED** — no method has been selected or approved. |
| Entry PC and address regime | Bounded stage-0 code interval; entry PC strictly inside it; address-space meaning explicit (PA, VA, or other documented regime); translation/fetch rules sufficient to explain how the first instruction is reached. | Nonzero or matching-looking addresses do not establish that an instruction fetch is valid. | **UNKNOWN / BLOCKED** — no target placement or entry fact. |
| Resident code-byte binding | Independent evidence that bytes at the exact execution interval are the reviewed stage-0 image, with fetch-visible contents consistent with the declared image. Cache/coherency assumptions must be explicit. | A host binary digest does not prove the target will fetch those bytes. | **BLOCKED**. |
| Code fetch permission | Independently justified readable/executable mapping or an explicitly documented alternative execution regime for every stage-0 instruction reachable before its own evidence is collected. Include applicable translation geometry/attributes and instruction-cache visibility. | Stage-0 cannot use a later snapshot of its own mapping as the sole proof authorizing its first fetch. | **BLOCKED** — live translation state is unknown. |
| Stage-0 memory footprint | Exact bounded code, data/BSS (if any), stack, scratch/output, and descriptor/table-buffer intervals. Address space is explicit; arithmetic is non-wrapping; all required read/write permissions and ownership are independently established. | Stage-0 must not discover whether its own stores are safe by attempting them. | **BLOCKED** — no intervals or ownership evidence. |
| Stack strategy | Either a proven writable, exclusively owned, correctly aligned initial stack before first stack use, or a source/binary-reviewed stackless prefix that does not read/use the incoming SP before switching to a proven private stack. Any ABI alignment requirement is checked before calls. | Unknown incoming SP cannot be treated as usable memory. | **BLOCKED** — no code or stack. |
| Incoming EL and privilege | Exact incoming EL and proof that every instruction/register access used by the stage-0 is permitted at that EL and is not unexpectedly trapped. A stage-0 that reads EL1 system registers must have an explicit, proven privilege contract. Do not rely on `CurrentEL` as a safe EL0 detector. | Privileged reads/writes can be undefined or trapped at an unsupported level; a guessed transition is not a contract. | **BLOCKED** — no runtime CPU-state evidence. |
| Minimal CPU/exception assumptions | Only state actually used by the reviewed code must be specified, but this includes interrupt/SError/debug behavior before any masking, required register availability, and exception handling if an exception can arrive. Either the incoming state prevents an unsafe asynchronous exception window or a valid, mapped handler/stack is established independently. | “Mask interrupts as the first instruction” is not proof of the state before that instruction executes. | **BLOCKED** — DAIF, vector, and trap state are unknown. |
| Translation and memory access | An explicit incoming MMU/translation policy. If translation is active, provide sufficient independently proven walks/permissions for stage-0 code and each used stack/scratch/output range; if not, prove the disabled regime rather than assuming it. No identity-map assumption. | Stage-0 requires a valid fetch and data-access model, but not a dump of all RAM. | **BLOCKED** — SCTLR/TCR/TTBR/MAIR and mappings are not target-proven. |
| Exclusive memory ownership | An upstream exclusive reservation/ownership proof for every stage-0 write interval, plus collision checks against all known protected intervals; alternatively, a complete applicable reservation set. A partial list alone cannot prove no overlap. | The stage-0 cannot claim a range by selecting a numeric address. | **BLOCKED** — runtime DRAM/reservations and loader ownership are unknown. |
| Failure/abort and output path | Deterministic fail-closed result categories, a bounded means to preserve the result if possible, and a known behavior when that path is unavailable. The abort path itself must use only already-proven code/memory. | A failed observation must not fall through into the kernel or an unknown operation. | **DESIGN only** — specification below; no implementation/output path. |
| Persistence policy | Static review of the exact stage-0 and launch method (including dependencies) showing no required flash/NAND/NOR/settings/firmware writes. Volatile owned scratch writes and CPU-state changes must still be declared; “RAM-only” is not “no risk.” | Persistent effects cannot be inferred after the first target-side action. | **DESIGN only** — no exact code/method to audit. |
| Specific authorization | Explicit user approval for the exact reviewed experiment/method and expected effects, after its risks and stop conditions are presented. | General project authorization is not approval for a materially different target action. | **NOT GRANTED for any live experiment in this task.** |

The exact-target metadata result EV-000A is useful compatibility context, not a
stage-0 execution proof. EV-000C physical identity is not required by the
technical first-bring-up model. Neither fact fills any blocked runtime row
above.

## 3. Minimum stage-0 memory model

No physical or virtual base is assigned. Every future interval is represented
as a half-open range `[base, base + length)` with an explicit address space,
nonzero length where used, overflow-checked end, source, bounds proof,
permissions, and independent ownership proof.

| Region | Minimum contract |
|---|---|
| Code | Exact byte length and image digest; entry PC lies strictly inside; the required code interval is readable and executable under the proven incoming translation/fetch regime; bytes are visible to instruction fetch; stage-0 does not self-modify it. |
| Data/BSS | May be omitted only if the exact linked image has none that stage-0 uses. Otherwise every accessed interval is bounded, mapped writable/readable as required, and exclusively owned. |
| Stack | May be avoided only by a verified stackless prefix. Before the first stack access/call, switch to a proven writable owned range and satisfy the calling convention alignment. Never adopt an unverified incoming SP. |
| Scratch/evidence buffer | Bounded, readable/writable as used, exclusively reserved, and large enough for the declared output or able to fail closed on truncation. A buffer write is a volatile target-state change and must be declared. |
| Descriptor storage | A future 128-byte V1 descriptor, if passed to the kernel, resides in independently proven readable storage; its producer must also have safe write authority. It is not required before stage-0 starts. |
| Page-table evidence buffer | Only the table pages needed for each required translation walk need be captured. Each source physical interval and each copied byte count must be explicit and bounded; a partial capture remains incomplete. It is not a full-RAM snapshot and is not required before stage-0 starts. |
| Kernel image and kernel stack | Separate from stage-0 ranges. Before transfer, the kernel image PA/VA/size/entry and mappings/ownership are proven; the kernel stack is separately proven under the unchanged kernel-entry contract. |

For initial stage-0 safety, the full kernel reserved-memory inventory is not a
prerequisite if an independent upstream source grants exclusive ownership of
the exact stage-0 code/stack/scratch intervals and the relevant known
protected ranges are checked. Without such an exclusive reservation, a
complete applicable protected-range set is required. “No overlap with ranges
we happened to observe” is not sufficient when the list is incomplete.

The minimum initial mapping evidence is limited to the stage-0 code and the
data/stack/scratch ranges it actually touches, plus the applicable translation
path and fetch/data attributes. It must come from an independent pre-stage-0
source. The TCR granule is not guessed; the existing offline analyzer must
either support the captured configuration or report it unsupported. No
physical-equals-virtual or identity mapping is assumed.

## 4. B — Facts stage-0 may observe

Observation means reading a fact without deliberately normalizing that fact.
It does not make the whole stage-0 operation read-only: code execution
advances PC and changes transient CPU state, stack/scratch use writes volatile
RAM, and a capture/output interface may have additional effects. A future
review must classify the entire method, not only an individual read.

Subject to the pre-stage-0 access contract, the observer may collect:

* an entry-phase CPU record: observed EL, SP before any stage-0 stack switch,
  DAIF, PC, and only the system registers the method is permitted to read;
* separate raw-before-normalization and post-normalization values for
  `SCTLR_EL1`, `TCR_EL1`, `TTBR0_EL1`, `TTBR1_EL1`, `MAIR_EL1`,
  `VBAR_EL1`, `CPACR_EL1`, and DAIF/SP as applicable;
* the bounded page-table bytes required to walk stage-0/kernel entry, stack,
  and any descriptor/object mappings; page bytes are observation data, not
  permission to dereference arbitrary addresses;
* runtime DRAM/reservation/framebuffer facts only from an identified,
  target-specific source with explicit completeness and provenance;
* the exact DreyzeOS image identity and descriptor/object facts only where
  their source and range authority are established; and
* deterministic failure/result codes and a capture/session identifier.

Each output value records phase, source, width/encoding, `value_present`, and
`value_proven` separately. A register value emitted by stage-0 remains a
producer claim until its capture path and session provenance are reviewed.
Reading a page-table page does not prove that it is complete, current, owned,
or safe to modify. Static `/memory = 0,0` remains a static placeholder, not a
runtime map.

## 5. C — Facts stage-0 may normalize

Normalization is an explicit state change, never an observation. It is
allowed only when the incoming state, exact operation, destination range,
architectural effects, and failure behavior have been reviewed for the exact
method. The record must preserve pre-change and post-change facts separately.

| Candidate normalization | Contract boundary |
|---|---|
| SP/stack | A switch is allowed only to a pre-proven, writable, exclusively owned stack. The incoming SP is recorded first if it is a required evidence fact. |
| DAIF | Masking/setting bits is a CPU-state change. Define which bits and when; prove exception behavior during the interval before the change. Record both states if the original state is evidence. |
| Translation/MMU registers | The minimum design is pass-through: stage-0 records and validates the regime and aborts if it cannot support it. Any SCTLR/TCR/TTBR/MAIR change or page-table construction is outside this minimal contract and requires a separate design, table ownership proof, architecture-specific transition audit, and explicit approval. |
| Caches | Any cache maintenance or policy change is a CPU/cache-state change. Define exact scope and ordering; do not infer that a memory copy is automatically instruction-fetch coherent. A missing/unsupported cache proof blocks transfer. |
| VBAR/exception policy | Configure only if the exact code uses exceptions or the kernel contract requires it, and only after handler code/stack mappings are proven. No unknown-vector reliance. |
| FP/SIMD/CPACR | Do not use FP/SIMD until its access policy is established. If stage-0 changes CPACR, record and review it; the current DreyzeOS entry has its own CPACR setup, which does not prove stage-0's incoming state. |
| Page tables or MMIO | **Not permitted by this minimal contract.** Table rewrites, MMIO, UART/AIC, framebuffer, and device-register access are not “normalization.” |

The preferred minimal behavior is to observe, validate, and pass through the
existing translation regime; normalize only those CPU-entry fields that are
strictly necessary and have an independently proven destination/policy. If
the required kernel mappings do not already exist, the result is ABORT, not an
implicit page-table rewrite or guessed mapping.

## 6. D — Artifacts stage-0 may produce

“Must” below means required for the corresponding current evidence/kernel
gate, not that such an artifact exists today. Any target-side buffer or copy
is a volatile write. Host-generated hashes and envelope fields must be
computed/verified by the host; stage-0 cannot authenticate its own claims.

| Output | Must produce? | Can the evidence be obtained without modifying target state? | Normalization dependency | Used by | Missing/invalid result |
|---|---|---|---|---|---|
| Session header | Yes for EV-000B; the host may preassign the capture ID and bounded UTC session. Stage-0 may echo the ID and phase markers. | The metadata can be prepared on the host; target-side emission needs a bounded output path and may write RAM or use an interface. | None for the ID; timestamps and producer/interface provenance must not be fabricated by stage-0. | Same-session binding of image, descriptor, MMU and any consumed artifacts. | EV-000B remains BLOCKED; no kernel transfer. |
| Selected image identity | Yes for EV-000B. Freeze the exact ELF/image bytes and host SHA-256 before the session; bind the used image to the same session. | Host hashing is offline. Proving the bytes used at target requires the reviewed method or independent target-bound evidence. | None. | ELF entry/size/segment comparison and bundle integrity. | Image/session binding incomplete; no kernel transfer. |
| CPU-state record | Required for current CPU/entry consistency gates. Capture entry state before relevant normalization, then record post-normalization state separately. | Individual register reads need not rewrite the read register, but stage-0 execution and record storage do change CPU/RAM state. | Needed only for fields explicitly normalized; keep raw and normalized records distinct. | EL1, SP, DAIF, translation/cache policy, verifier consistency. | Corresponding CPU requirements stay BLOCKED; no kernel transfer. |
| MMU register snapshot | Required when page-table translations are used to prove entry/mappings. Include present/proven flags for TCR/TTBR/MAIR and applicable SCTLR state. | Reads can be observational; execution and output-buffer writes still change target state. | If any register is normalized, snapshot both before and after. | Granule/geometry selection, TTBR choice, snapshot/register consistency. | Mapping claims remain UNKNOWN/BLOCKED; no transfer. |
| Required page-table bytes | Required for each claimed translation walk and for completeness of EV-025. Capture only all table pages needed for the declared walks; mark exact regions and coverage. | RAM reads are observational only under a proven readable-RAM mapping; copying bytes to scratch/output is a volatile write. | Must correspond to the register state whose mappings are claimed. Table writes are forbidden here. | Offline MMU analyzer; executable/readable/writable and collision/range evidence. | Missing/truncated/unsupported pages make affected mapping unproven; no transfer. |
| Runtime memory/reservation record | Required for runtime DRAM containment, ownership, and complete collision checks. Include provenance and completeness; framebuffer may be absent only if its absence is proven or its use is excluded under the applicable requirements. | Only if a safe, bounded source is independently available; staging the record may write scratch. No fallback constants. | No normalization can turn static placeholders into runtime facts. | Payload placement, stage-0/kernel ownership, reserved-range and collision checks. | Runtime memory/ownership/collision gates remain BLOCKED. |
| Loader Handoff ABI V1 descriptor | Required by current EV-000B and kernel handoff model. Exactly the fixed 128-byte V1 prefix; construct only in owned writable storage, then separately prove the kernel-readable copy/range and validate structure. | **No** for construction/copy: these write volatile target memory. | Populate only facts already supported by evidence; never set VERIFIED as a substitute for trust. | Kernel entry inputs and bounded optional object ranges. | Descriptor trust/structure gate remains BLOCKED; no transfer. |
| boot_args / DeviceTree copies | Conditional: only if the selected kernel entry consumes them. Bounded source/destination ranges and independent object bounds are required. | **No** for copies; copying writes volatile memory. | Not a CPU normalization. | Bounded host parser and descriptor range validation. | If required, corresponding EV-014/026 gate blocks; otherwise leave absent and unclaimed. |
| Transfer-intent/result record | Record the proposed target/entry and the gate decision. A post-entry arrival record is separate and only exists if arrival is actually observed. | A record needs an output buffer/interface; transfer itself changes control flow. | Depends on final normalized entry state. | EV-022 declared bounded transfer contract; post-entry validation. | Missing intent blocks transfer proof. Missing arrival means execution success is unproven, not inferred. |
| Provenance envelope and hashes | The v2 host envelope is the authoritative local wrapper. Stage-0 may emit session/artifact references, but host must hash actual collected bytes and verify relationships after collection. | Envelope creation and hashing can be host-only; target-produced bytes still require an output path. | None; do not upgrade producer claims to proof. | EV-000B and the unified verifier. | EV-000B remains BLOCKED on missing/partial/conflicting data. |

The current repository has no target-side record producer or output
interface. Therefore the “may produce” entries are **DESIGN**, not present
artifacts or a proposed acquisition procedure.

## 7. E — PRE-KERNEL-TRANSFER gate

The gate must fail closed. No kernel branch/transfer may occur unless all
applicable existing critical requirements are proven in one internally
consistent capture/session and the gate consumer has checked them **before**
transfer. At minimum it must establish:

1. EV-000A target metadata consistency and EV-000B same-session provenance;
   EV-000C may remain NOT_PROVEN for technical first bring-up.
2. Exact DreyzeOS image identity, size, supported architecture, and agreement
   between ELF `_start`, declared entry, descriptor payload bounds, and the
   proposed transfer PC.
3. Structurally valid ABI V1 descriptor; independently proven readable
   128-byte prefix and trusted copy. Its VERIFIED flag is only an assertion.
4. EL1 entry precondition, required SP/stack proof, DAIF policy, explicit
   translation regime and relevant SCTLR/TCR/TTBR/MAIR consistency, cache
   policy, and any VBAR/FP/SIMD assumptions required by the actual entry.
5. Executable/readable stage-0 and kernel mappings plus readable/writable
   kernel data/BSS/stack mappings as required; complete table bytes for every
   claimed walk; supported translation configuration. No mapping is inferred
   from a nonzero address or register value.
6. Runtime-proven DRAM interval, payload PA/VA/size/alignment and ownership,
   plus exclusive ownership of descriptor, stage-0, and scratch ranges.
7. A complete applicable protected/reserved-range set or an equivalent
   independently proven exclusive reservation, with overflow-safe collision
   exclusion in the correct PA/VA spaces. Unknown framebuffer/reservation
   facts cannot be silently treated as absent where collision completeness
   requires them.
8. Bounded boot_args/DeviceTree facts if and only if the selected kernel path
   consumes them; otherwise they remain absent/untrusted and are not read.
9. A bounded transfer contract to the exact entry, a deterministic abort
   route, and a proven false `persistent_write_required` fact. No MMIO,
   framebuffer, UART/AIC, page-table write, or persistent write is introduced
   by this minimal stage-0 contract.
10. A pre-transfer decision mechanism that has actually consumed the same
    evidence the host verifier will later check. An after-the-fact host PASS
    alone is not a pre-transfer gate.

The existing kernel-entry gate and its critical requirements are not reduced
by this document. The current `boot/entry.S` independently shows that DreyzeOS
expects EL1, masks DAIF, installs its own stack, clears BSS, installs
`VBAR_EL1`, and sets the FP/SIMD access policy; it does not configure the MMU
or caches. This is source-level evidence about DreyzeOS code, not proof that a
target stage-0 can satisfy those requirements. Existing loader-contract
requirements such as SP/stack evidence remain in force unless changed by a
separate reviewed requirement audit.

## 8. F — Abort contract

Specification-level behavior only; no abort routine is implemented here.

* Any missing, malformed, unsupported, contradictory, incomplete, or
  unproven required fact produces a deterministic failure category and **no
  kernel transfer**.
* Do not substitute a historical DRAM address, guessed mapping, identity
  mapping, default TTBR/granule, or guessed descriptor/object bound.
* Do not probe speculative MMIO, UART/AIC, framebuffer, page tables outside
  the bounded readable evidence plan, or persistent storage.
* Do not rewrite page tables, perform a hardware jump to another address, or
  claim a reset/recovery path. A halt/return path is valid only if its
  execution state and effects are independently specified; no universal safe
  reset is assumed.
* Preserve evidence only through an already-proven bounded owned buffer or
  reviewed output interface. If output cannot be preserved safely, report
  that limitation and stop; do not improvise another channel.
* Keep the result code stable and phase-specific, for example:
  `ABORT_CODE_IDENTITY`, `ABORT_ENTRY_WINDOW`, `ABORT_CPU_PRECONDITION`,
  `ABORT_MEMORY_OWNERSHIP`, `ABORT_TRANSLATION_UNSUPPORTED`,
  `ABORT_EVIDENCE_INCOMPLETE`, `ABORT_CONFLICT`,
  `ABORT_OUTPUT_UNAVAILABLE`, or `ABORT_PERSISTENCE_POLICY`. These names are
  DESIGN labels, not implemented ABI values.

## 9. ABI V1 sufficiency

**Loader Handoff ABI V1 is sufficient for the current role; no V2 is needed.**
Keep its exact 128-byte layout unchanged. It provides the kernel handoff's
fixed-width structural facts, payload interval, entry EL/MMU flags, diagnostic
x0/x1, and bounded optional boot_args/DeviceTree ranges. It intentionally does
not carry all raw CPU registers, session IDs, artifact hashes, table bytes,
memory ownership, cache proof, or collision completeness.

Those missing facts belong in separate CPU-state, MMU-snapshot, runtime-memory,
and provenance/session artifacts already represented by the host evidence
pipeline. Stage-0 must normalize or prove the agreed entry policy separately;
raw values in V1 would not prove access authority. Do not mutate V1 or set its
VERIFIED flag as a trust shortcut. A future ABI redesign is justified only if
a concrete kernel-consumer requirement cannot be expressed by the separate
evidence record plus V1's existing handoff facts.

## 10. Current blockers and next dependency

| Fact | Static/runtime | Current evidence | Blocks stage-0? |
|---|---|---|:---:|
| Target profile Watch4,2 / N131bAP / T8006 / watchOS 10.6.1 / 21U580 / AArch64 | Static target metadata | EV-000A **CONFIRMED** from current exact-target evidence chain. Not physical identity or runtime launch proof. | Compatibility context only |
| Stage-0 source, build recipe, binary, bytes/hash | Static artifact | None | **YES** |
| Stage-0 target entry PC and PA/VA regime | Target-specific | None | **YES** |
| Stage-0 memory ownership, code/data/stack/scratch bounds | Target-specific | None | **YES** |
| Initial executable/readable mapping and fetch-visible byte binding | Target-specific | None; no target MMU snapshot | **YES** |
| Incoming EL/required CPU/exception state | Runtime | None | **YES** |
| Minimal translation/cache/access assumptions | Runtime | None | **YES** |
| Independent conflict/ownership proof for stage-0 intervals | Target-specific | None; runtime DRAM and reservation state blocked | **YES** |
| Exact launch method and full side-effect/persistence review | Method-specific | None selected or approved | **YES** |
| Bounded evidence-output and provenance path | Session-specific | None reviewed | **YES** to an evidence-producing stage-0 |
| Deterministic abort behavior/recovery expectations | Method-specific | DESIGN only; arbitrary-state recovery is not proven | **YES** if failure effects remain unknown |
| Specific user approval | Per experiment | Not granted by this host-only task | **YES** before any live action |

The minimum-memory proposal reduces what must be known before stage-0 from a
complete kernel MMU/RAM snapshot to independently justified execution of the
exact code and its actual stack/scratch accesses. It does not make any of
those facts currently available. The first remaining dependency is not EV-000B
or a full page-table dump; it is a concrete stage-0 artifact plus a
target-specific, independently evidenced initial execution window and reviewed
launch/effects contract. No such artifact or method currently exists.

```text
STAGE0 CONTRACT DEFINED = DESIGN
PRE-STAGE0 FACTS CURRENTLY PROVEN = exact target metadata only (EV-000A);
                                  no stage-0 execution fact
FIRST_STAGE0_EXECUTION = NOT READY / BLOCKED
FIRST_DREYZEOS_KERNEL_ENTRY = NOT READY
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

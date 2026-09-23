# First-execution bootstrap dependency audit

Audit baseline: `a4b32593342cd10b9f0095f34d453ace231c17b2` (`master`).
Scope: host-side requirements, verifier, source, and documentation review only.
No Watch/iPhone interaction, target-code execution, payload, loader, DFU,
recovery, RAM/register/MMIO/page-table write, or control transfer was done.

## Findings

```text
EV-000A = CONFIRMED
EV-000B = BLOCKED
EV-000C = UNKNOWN / non-critical
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

There is a **temporal cycle if `FIRST HARDWARE EXECUTION` means the first
execution of any target-side code**: the aggregate verifier requires runtime
session/MMU/descriptor evidence and a stage-0 mapping proof, while the proposed
stage-0 is the component that could produce much of that evidence. Running
stage-0 to create the evidence would already be a first hardware execution.

There is **not an inherent cycle for first DreyzeOS kernel entry** if a
separately authorized and independently safe bootstrap executes first. Such a
stage-0 can observe/normalize state and assemble the evidence before
transferring to the DreyzeOS kernel. That bootstrap does not currently exist
as target code or as a reviewed acquisition method, and its own entry gate is
not represented by the present requirements.

This is not a Python `depends_on` graph cycle: the verifier has an ordered set
of critical nodes and a few directed dependencies (for example, collision
audit depends on reserved-range completeness), but no stage/temporal model.
The defect is that the single readiness label does not distinguish the first
stage-0 instruction from first DreyzeOS kernel entry. The verifier now reports
those gates separately; the legacy `first_hardware_execution` field remains a
backward-compatible alias for the DreyzeOS kernel-entry gate, never stage-0
authorization.

## Audit basis

The requirements inventory marks `EV-000B`, the real descriptor, and the MMU
snapshot/table-byte requirements as critical. The v2 provenance envelope
requires the image, descriptor, and MMU snapshot to share one proven capture
session. The current verifier's `CRITICAL_ORDER` also includes
`same_session_provenance`, `stage0_executable_mapping`, descriptor trust,
mapping, collision, control-transfer, and no-persistent-write nodes. Its
`first_hardware_execution` field was derived from the entire critical graph,
without a separate pre-stage-0 contract.

The existing `control_transfer` node checks a declared bounded `entry_pc`,
target `DreyzeOS`, agreement with ELF `_start`/descriptor payload bounds, and
an explicit `proven` claim. The offline verifier does not itself observe an
instruction branch or prove that the kernel actually began executing. The
current closure text also says offline verification does not imply hardware
execution. Accordingly, that node is a pre-transfer contract assertion; an
actual successful kernel-arrival observation is a distinct post-entry fact
and is not presently represented as a separate EV requirement.

`FIRST_RUNTIME_EVIDENCE_PLAN.md` orders runtime evidence through CPU state,
MMU/table bytes, runtime memory, descriptor, bounded objects, and a complete
bundle. `LOADER_ENTRY_CONTRACT.md` describes a minimal stage-0 that copies and
validates the descriptor before kernel entry. Those documents already imply
that some required evidence may be produced by stage-0. The missing part is an
independent, evidence-backed authorization boundary for executing that
stage-0.

## Classification semantics

Each inventory item below receives exactly one requested phase. For an
aggregate requirement containing multiple facts, its phase is the earliest
safe gate relevant to its current closure contract; the row calls out any
subset that belongs to another phase.

* `PRE_EXECUTION_REQUIRED`: independently establish before executing any new
  target-side bootstrap/observer code.
* `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER`: stage-0 may collect,
  validate, or normalize this fact before the DreyzeOS kernel is entered. This
  does **not** authorize starting stage-0.
* `MAY_BE_VERIFIED_DURING_FIRST_CONTROLLED_EXECUTION`: a fact whose first
  legitimate observation requires the controlled kernel entry. No present EV
  closure condition is exclusively in this category; actual entry observation
  is not an existing EV.
* `POST_EXECUTION_VALIDATION`: checks on artifacts/results after a controlled
  entry attempt. This is not a first-entry precondition. No present EV is
  exclusively in this category; final host-side verification can happen after
  a capture without implying that target execution occurred.
* `NOT_REQUIRED_FOR_FIRST_BRINGUP`: may remain absent only if the first
  bring-up explicitly does not consume/use the corresponding facility.

`Can exist without target code execution` answers whether the required fact
could be available independently before the proposed stage-0. “Potentially”
does not mean that a source is present or proven in this repository.

## EV-000 through EV-027 phase matrix

| ID | Requirement | Current status | Phase | Why | Can exist without target code execution? | Dependencies |
|---|---|---|---|---|---|---|
| EV-000 | Technical target provenance (A+B) | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | EV-000A is already independently proven; stage-0 can create/bind its runtime artifacts into EV-000B before kernel transfer. | PARTIAL: A and a session shell/image hash can; complete B cannot without a runtime producer. | EV-000A; session/source, image, real descriptor, real MMU snapshot, hashes, complete coverage, same-session links, no conflicts. |
| EV-000A | Target metadata consistency | CONFIRMED | `PRE_EXECUTION_REQUIRED` | Select and review a target-compatible bootstrap using the exact model/board/SoC/OS/build/architecture evidence before any target code. | YES: exact static package and kernelcache evidence already satisfy the metadata profile; this does not bind a physical session. | Six target fields, explicit metadata match, conflict-free proven sources. |
| EV-000B | Same-session artifact provenance | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | The whole artifact set need not pre-exist stage-0; stage-0 could produce descriptor/MMU artifacts and bind them to a session before kernel transfer. | PARTIAL: capture ID/time and frozen image can be prepared; real target artifacts and their session links cannot currently be proven. | Proven source and producer; capture ID/bounds; image + real descriptor + MMU/table bytes; hashes; complete coverage; session relationships; no conflicts. |
| EV-000C | Physical identity / cross-session continuity | UNKNOWN, non-critical | `NOT_REQUIRED_FOR_FIRST_BRINGUP` | Persistent serial-level identity is not a technical kernel-entry dependency. | YES for absence; optional identity source is not available/proven. | Required only for claims about a persistent physical Watch or cross-session continuity. |
| EV-001 | Loader transfer protocol | BLOCKED | `PRE_EXECUTION_REQUIRED` | Review the exact proposed bootstrap/transfer protocol and its state effects before running any target code. | YES in principle as a source/design review; no target-specific DreyzeOS protocol currently exists. | Named implementation/source, target/build compatibility, bounded image/descriptor/PC/CPU contract, transfer semantics, no persistence, failure/stop analysis. |
| EV-002 | Runtime DRAM base and size | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | A privileged stage-0 may read/validate runtime-authoritative memory bounds before handing control to the kernel. | Only if an independent existing artifact exists; none is present. | Stage-0 can safely execute/read its observation source; runtime provenance and bounded nonzero region. |
| EV-003 | Payload physical placement | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 can select or validate the DreyzeOS image interval before kernel entry. | The ELF can be inspected offline, but the target PA/placement cannot. | EV-002, image size/alignment, ownership, range and collision evidence. |
| EV-004 | Payload alignment and maximum size | UNKNOWN | `PRE_EXECUTION_REQUIRED` | Image byte size/alignment and the intended copy bound must be known before bootstrap code may copy/accept it. | PARTIAL: ELF facts yes; target-specific loader limits are absent. | Frozen image hash/size; reviewed loader limits and alignment; target buffer bounds. |
| EV-005 | Payload VA and entry PC | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 can establish the kernel VA/entry and prove `_start` lies in the mapped image before transfer. | Static ELF link VMA/entry yes; runtime mapping/entry relation no. | EV-003/004; translation regime; canonical VA; ELF `_start`; executable/readable mapping. |
| EV-006 | Entry EL1 | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 may observe/normalize the DreyzeOS entry EL to EL1 before transfer. Its own incoming EL is a separate pre-stage-0 condition. | Static kernel requirement yes; runtime value no. | Stage-0 privilege needed to observe/control state; descriptor consistency; no guessed EL transition. |
| EV-007 | Initial stack and SP | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 may define the kernel stack and aligned SP before the kernel call. Its own stack must already be safe before stage-0. | ELF stack interval yes; target VA mapping, writable authority, ownership no. | Kernel stack bounds/mapping/ownership, 16-byte SP alignment, collision exclusion. |
| EV-008 | DAIF normalization | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 may normalize DAIF for kernel entry. DreyzeOS entry masks it, so post-entry reads cannot recover the original value. | Policy can be specified offline; incoming runtime value no. | Stage-0 current privilege, explicit policy, descriptor/CPU consistency. |
| EV-009 | Translation regime and MMU registers | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 may read and record SCTLR/TCR/TTBR0/TTBR1/MAIR and normalize the regime before kernel transfer. | Register policy can be designed offline; exact target values/table roots cannot. | Safe stage-0 entry; captured registers; supported TCR geometry; register/snapshot consistency. |
| EV-010 | I/D-cache, vectors, FP/SIMD state | UNKNOWN | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 must establish cache policy before kernel fetch/data access and define vector/FP assumptions. | Desired policy yes; live state/maintenance result no. | Safe stage-0 entry; cache policy/maintenance; VBAR and CPACR/SIMD contract. |
| EV-011 | Stage-0 and kernel executable mappings | BLOCKED | `PRE_EXECUTION_REQUIRED` | The stage-0 portion includes its own initial instruction mapping; that cannot authorize its first fetch if the only proof is a snapshot stage-0 itself will capture. Stage-0 may separately prove the kernel mapping. | Potentially from an independent existing loader/snapshot; none is currently available. | Stage-0 PA/VA/size/ownership; independent executable mapping and incoming translation/cache facts; later kernel mapping proof. |
| EV-012 | Writable kernel data/BSS/stack mappings | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 may verify these complete ranges before transferring; stage-0's own writable stack/storage is part of its pre-entry gate. | ELF section boundaries yes; runtime permission/ownership no. | MMU snapshot/table pages, ELF intervals, stack/data ownership and collisions. |
| EV-013 | Descriptor prefix readability and trusted copy | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 can construct the descriptor in its own bounded storage and establish the kernel's readable 128-byte copy before transfer. | Layout rules yes; real descriptor/ranges/readability no. | Stage-0 writable owned storage; exact prefix; independent readable proof; copy-before-parse. |
| EV-014 | boot_args/DeviceTree runtime bounds | BLOCKED | `NOT_REQUIRED_FOR_FIRST_BRINGUP` | This is required when consumed. Current production code preserves raw x0/x1 and does not dereference them while metadata is unverified; a minimal headless entry can omit both. | YES to omit; any runtime objects would need stage-0 capture. | If enabled: independent ranges, complete bytes, bounded nested DT, EV-013/descriptor authority. |
| EV-015 | UART/AIC virtual mappings | UNKNOWN, non-critical | `NOT_REQUIRED_FOR_FIRST_BRINGUP` | Production UART/AIC remain untouched behind closed gates; console/MMIO mapping is not needed for a minimal no-MMIO entry. | Static PAs exist; live mapping does not, but the feature can remain unused. | If used: MMU evidence plus separate access authority and gate review. |
| EV-016 | Framebuffer reservation and mapping | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Framebuffer access can remain disabled, but its presence/range must be known for complete payload collision safety; stage-0 can collect that before transfer. | Static `/vram` placeholder only; runtime reservation is absent. | Runtime memory/reservation source; if used, VA mapping/attributes; payload collision analysis. |
| EV-017 | Reserved-memory completeness | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 may collect the complete protected interval set for the DreyzeOS payload. Its own initial interval must be independently protected before stage-0. | Not from current static zero-filled runtime placeholders. | Runtime reservations plus loader/descriptor/metadata/FB/kernel ranges; completeness proof; distinct PA/VA spaces. |
| EV-018 | Payload collision audit | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 can audit the kernel payload against a complete protected list before transfer. The stage-0's own collision check is a separate pre-stage-0 gate. | Range algorithm yes; target intervals no. | EV-003, EV-016/017, all loader/descriptor/DT/stack/reserved ranges, overflow-safe interval checks. |
| EV-019 | Payload ownership | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | The producer may prove the kernel image is relinquished/owned for the handoff before transfer; stage-0 ownership itself must pre-exist its execution. | Ownership policy can be written offline; actual intervals/lifetime no. | Loader/source ownership facts, payload PA/size, no later overwrite, collision completeness. |
| EV-020 | Descriptor access authority | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 can create/copy the descriptor and prove kernel-readable storage before transfer; the descriptor's flag cannot authorize its own read. | Contract sequence yes; real range/storage proof no. | Stage-0 owned writable location; independently readable 128-byte prefix; copy before nested fields. |
| EV-021 | Translation-to-payload consistency | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 can compare PA/VA/entry against its captured MMU snapshot before the kernel transfer. | Static ELF relation partly; live VA→PA translation no. | EV-005, EV-009, EV-011/012, complete relevant table bytes. |
| EV-022 | Control-flow transfer proof | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | As written, closure is a documented, bounded transfer contract to ELF `_start`; stage-0 can establish that contract before issuing it. Actual arrival observation is separate and post-entry. | Static/source proof could exist; no exact target implementation currently exists. | EV-001, EV-005, descriptor and mapping consistency; explicit non-persistent transfer semantics. |
| EV-023 | No persistent storage write | DESIGN | `PRE_EXECUTION_REQUIRED` | The selected code path must be source-reviewed to exclude persistent writes before any execution; an after-the-fact assertion is insufficient. | Yes for a specific reviewed source path; no target-specific path has been selected. | Exact stage-0/loader source and all called code, storage side-effect audit, stop/failure review. |
| EV-024 | MMU snapshot target binding | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 may bind captured MMU registers/table bytes to the target/session facts before kernel transfer. | Exact static profile yes; target runtime snapshot no. | EV-000A, actual session source, register/table artifacts, conflict-free target metadata. |
| EV-025 | Complete table-byte coverage | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 may gather all pages needed for kernel/descriptor/stack walks before transfer. The stage-0's own initial mapping still needs an independent pre-entry proof. | Only from an independent complete dump; none is present. | EV-009, all descriptor-table pages used by required walks, complete-range declarations, no missing bytes. |
| EV-026 | Runtime boot metadata capture | BLOCKED | `NOT_REQUIRED_FOR_FIRST_BRINGUP` | Closure is conditional on DreyzeOS consuming boot_args/DT; current minimal path can avoid them. | YES to omit; otherwise stage-0 may capture bounded local copies. | If enabled: EV-014, descriptor ranges, complete bounded artifacts and independent readability. |
| EV-027 | Runtime handoff evidence bundle | BLOCKED | `MAY_BE_ESTABLISHED_BY_STAGE0_BEFORE_KERNEL_TRANSFER` | Stage-0 can assemble the pre-transfer runtime facts and session artifacts; host tools can validate them. This says nothing about successful kernel arrival. | No, not for actual runtime bytes with current sources; hypothetical only from another producer. | EV-000A/B, image/descriptor/MMU bytes, all critical nodes, conflicts absent, full verifier/gap checks. |

### Subrequirement assignment

`EV-000A` is a pre-execution target-profile fact. `EV-000B` is not wholly a
pre-stage-0 requirement: session ID/bounds and the frozen image hash may be
prepared beforehand, while descriptor/MMU artifacts and their proven
same-session links may be generated by stage-0 before kernel transfer.
`EV-000C` remains non-critical and does not block first technical bring-up.

The MMU snapshot must **not** be required to pre-exist stage-0 in full. What
must pre-exist is an independent, sufficient proof that stage-0 itself can be
entered and fetch its first instructions safely: its location/ownership,
initial executable mapping or other explicitly proven execution regime,
current EL and required stack/translation/cache assumptions. Stage-0 cannot
use a later snapshot of its own mapping as the sole authority for its first
fetch. No identity mapping or MMU-disabled state is assumed.

A real V1 handoff descriptor likewise need **not** pre-exist stage-0. A future
stage-0 can create it after observing/normalizing the kernel-entry facts, then
establish the trusted readable prefix and copy before transfer. No such real
producer exists now.

## Dependency graph and cycle analysis

```text
PRE-STAGE0 GATE (independent evidence; currently BLOCKED)
  target-compatible code/source + exact image/hash
  reviewed launch mechanism, effects, no-persistent-write policy
  stage-0 PA/VA/size/ownership + initial executable mapping
  stage-0 entry EL/SP/DAIF/translation/cache/exception assumptions
  bounded capture-output/source plan + explicit method approval
       |
       v
STAGE0 EXECUTION (not implemented or authorized)
  observe runtime DRAM + CPU/MMU registers + required table bytes
  establish kernel placement/ownership, ranges, mappings and collisions
  create/copy/validate handoff descriptor
  bind image + descriptor + MMU evidence to one capture session
       |
       v
PRE-KERNEL-TRANSFER GATE (current EV graph; BLOCKED)
  EV-000A + EV-000B + CPU state + DRAM/payload + mappings + trust
  complete reservations/collision + documented bounded transfer
  no-persistent-write proof + full bundle validation
       |
       v
FIRST DREYZEOS KERNEL ENTRY (NOT READY)
       |
       v
POST-ENTRY VALIDATION (not separately represented by current EV IDs)
  confirm observed kernel arrival and compare actual post-entry state;
  never substitute post-entry DAIF/SP/VBAR/CPACR values for their incoming
  pre-transfer values, because entry code changes those states.
```

The **semantic cycle** under the literal “first target code” meaning is:

```text
FIRST HARDWARE EXECUTION READY
  -> requires same-session runtime artifacts + stage-0 mapping proof
  -> stage-0 is the proposed producer of those facts
  -> running stage-0 is itself target-code execution
  -> FIRST HARDWARE EXECUTION
```

There is no equivalent cycle for the **kernel-entry** gate if the first two
graph phases are kept distinct. The stage-0's initial execution permission
must be justified separately; the full EV-000B set can then be generated
before kernel transfer. The current repository has neither that gate nor a
specific stage-0 producer, so this is a design model, not a readiness claim.

## Required before any target code runs

At minimum, a future stage-0 must not bootstrap its own initial authority.
Before any stage-0/observer code runs, independent reviewed evidence must
identify:

1. Exact stage-0 bytes, source/revision, architecture, size, and intended
   entry, with a static review of every operation and dependency.
2. The named acquisition/launch method and its exact target/build support,
   memory/CPU/control-flow effects, persistent-write behavior, stop condition,
   and recovery uncertainty. Any unknown effect remains a blocker.
3. The stage-0 initial PC/EL, physical/virtual interval, ownership, alignment,
   executable/readable mapping or another explicit execution regime, and
   non-collision with already protected memory.
4. The incoming stack, privilege, translation, cache, and exception behavior
   actually needed by that stage-0. Do not infer identity mapping, MMU-off, or
   register state from nonzero addresses or related Apple models.
5. A bounded plan for how emitted evidence becomes local files and obtains
   source/session provenance. No reviewed output path exists now.
6. Proof that the reviewed initial path requires no persistent storage write,
   plus an explicit user approval naming that exact experiment. Recovery from
   arbitrary state remains unproven.

The current repo has no target stage-0 binary or loader, no real stage-0
placement/mapping proof, no approved producer, and no reviewed output path.
Thus **FIRST_STAGE0_EXECUTION = BLOCKED**. EV-000B is not the blocker to
starting stage-0 as such; the absent pre-stage0 launch contract and source are.

## Stage-0 responsibilities before kernel transfer

Only after a separate pre-stage0 gate is satisfied could a reviewed stage-0
potentially establish the following before entering DreyzeOS:

* runtime DRAM bounds and payload PA/VA/size/alignment/ownership;
* current EL and normalized kernel EL1/SP/DAIF contract;
* SCTLR/TCR/TTBR0/TTBR1/MAIR and cache policy, plus complete relevant page
  table bytes and executable/readable/writable walks;
* a newly constructed 128-byte V1 descriptor, independently readable prefix,
  trusted copy, and structural validation;
* runtime framebuffer presence/reservation and a complete protected/reserved
  range list, followed by PA/VA collision analysis;
* bounded boot_args/DeviceTree evidence only if the kernel will consume it;
* source, producer, UTC interval, image hash, artifact hashes, complete
  coverage, and same-session relationships for EV-000B; and
* a bounded, target-specific transfer contract and explicit no-persistent-write
  proof.

Some of these operations may themselves modify CPU state or RAM (for example,
normalization or descriptor storage). They are not thereby “read-only”; a
future exact method requires a separate risk review and explicit approval.

## Smallest non-circular readiness model

1. **PRE-STAGE0 GATE:** prove only the independent conditions needed to execute
   the exact reviewed stage-0 safely, including its own code, entry, memory
   ownership/mapping, CPU assumptions, method effects, no-persistence review,
   stop/failure handling, and specific approval. No full MMU snapshot or
   DreyzeOS descriptor is demanded here if stage-0 is their reviewed producer.
2. **STAGE0 RESPONSIBILITIES:** capture/normalize evidence and create the V1
   descriptor plus required MMU/table artifacts; bind them to one session.
3. **PRE-KERNEL-TRANSFER GATE:** run the existing evidence pipeline on the
   complete stage-0 output. Require every kernel-entry blocker and collision
   proof; any absent or conflicting critical fact means no kernel transfer.
4. **FIRST DREYZEOS KERNEL ENTRY:** allowed only after that gate. This is the
   scope meant by the existing full kernel-entry readiness calculation.
5. **POST-ENTRY VALIDATION:** separately record whether the intended entry
   actually occurred and validate post-entry evidence. Such observation does
   not retroactively authorize stage-0 or replace incoming-state evidence.

This model does not make stage-0 safe or available. It merely avoids requiring
stage-0-produced evidence before stage-0 can begin, while keeping an
independent, strict pre-stage0 gate and the existing full pre-kernel gate.

## Status terminology correction

The machine/human reports now expose:

```text
PRE_STAGE0_GATE = BLOCKED
FIRST_STAGE0_EXECUTION = NOT_READY
PRE_KERNEL_TRANSFER_GATE = BLOCKED | READY
FIRST_DREYZEOS_KERNEL_ENTRY = NOT_READY | READY
FIRST HARDWARE EXECUTION = legacy alias of FIRST_DREYZEOS_KERNEL_ENTRY
```

The pre-stage0 gate is deliberately always blocked by current tooling because
the bundle has no independent stage-0 launch-contract schema or target
producer. The kernel-entry status continues to require the full existing
critical evidence graph and confirmed non-synthetic source. No EV closure
condition, MMIO gate, or hardware safety requirement was weakened. The
existing readiness output should no longer be read as permission to execute
any stage-0.

```text
CURRENT TARGET:
FIRST_STAGE0_EXECUTION = BLOCKED
FIRST_DREYZEOS_KERNEL_ENTRY = NOT READY
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

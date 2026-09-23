# EV-000B first target acquisition-path review

Review baseline: `330fec13f26d6d712dc4c56fe6034711b9848272` (`master`).
Scope: repository, already-saved host artifacts, and static public-source
review only. No Watch/iPhone interaction, capture, exploit, payload, loader,
DFU/recovery action, or device-state change was performed.

## Decision

```text
EV-000A = CONFIRMED
EV-000B = BLOCKED
EV-000 = BLOCKED
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

**No presently reviewed method is suitable for the first EV-000B session.**
The repository already has sufficient host-side formats and validators; the
missing element is a reviewed producer of target-bound runtime bytes. The
repository contains no real handoff descriptor and no real MMU register/table
snapshot. Files under `research/handoff_evidence/fixtures/provenance/` are
synthetic test inputs, not target evidence.

“No reviewed method” is the result of this bounded review, not a claim that no
future supported method could exist. An unverified method remains `UNKNOWN`,
not read-only by assumption.

## EV-000B data requirements

The current `EV-000B` closure conditions in
`research/t8006_evidence/requirements.json` require one proven capture session
containing the selected DreyzeOS image, a real `handoff_descriptor`, and a
real `mmu_snapshot` with all table bytes needed for the claimed walks/ranges.
The session must have a proven `capture_id`, bounded ordered UTC start/end,
producer, and actual source/interface provenance. Every required and covered
artifact must exist, match its local SHA-256, be included in explicitly
complete coverage, and have an evidence-backed relationship to the same
session. Conflicting proven session/source facts block closure.

The envelope v2, provenance validator, bundle verifier, MMU analyzer, and
evidence-gap tool are sufficient for later local processing. SHA-256 proves
local byte equality only; it does not authenticate the producer or device.
This review adds no format or capture tool.

## Candidate path matrix

`SUITABLE = NO` means the path either cannot supply the required evidence or
its effects/provenance are not established. `UNKNOWN` is not a read-only
finding.

| Path | What it can provide | Descriptor possible | MMU registers / table bytes | Source provenance / same-session binding | Target code execution | Memory write | CPU state change | Persistent write | Read-only confidence | Known / unknown effects | Suitable for first EV-000B session |
|---|---|---|---|---|---|---|---|---|---|---|
| Existing DreyzeOS repository, exact static IPSW/ADT/kernelcache, offline tools | Static target/build facts, image structure, analysis of supplied bytes | No runtime descriptor | No live registers or table bytes | Static artifact provenance only; no live session | No | No | No | No | `SAFE_HOST_ONLY` | Local reads only; no runtime source | **NO** — cannot produce target-session descriptor/MMU evidence |
| Existing local NanoPhotos `.ips` and saved PC/device-observation files | Report metadata and facts present in saved host files | No | No | Their historical provenance only; not bound to a future DreyzeOS session | No new execution | No new write | No new change | No new write | `SAFE_HOST_ONLY` for re-reading; acquisition origin remains as recorded | The report is not a handoff/MMU capture; saved host observations did not expose Watch runtime state | **NO** — prior context, not the required artifact set |
| Hypothetical pre-existing complete target-bound dump/manifest | Only registers, descriptor and table bytes actually included | Conditional | Conditional on fields and complete bytes being present | Only if original source/session provenance is independently reviewable | Acquisition unknown | Acquisition unknown | Acquisition unknown | Acquisition unknown | `SAFE_HOST_ONLY` for local analysis; acquisition `UNKNOWN` | No such complete target-bound bundle is in the reviewed repository inventory | **NO** — hypothetical input, not an available path |
| Normal Windows/Apple companion metadata or ordinary device query | At most model/product/pairing/service metadata exposed by the interface | No known descriptor field | No known EL1 translation-register/table-byte interface | May describe a host/companion connection, not runtime artifact origin | No known code execution for metadata alone | Not established for every query | Not established for every query | Unknown | `UNCERTAIN` for a new live query; saved files are host-only | Existing enumeration did not expose Watch runtime facts; absent/generic entries prove nothing | **NO** — neither required data nor all query effects are established |
| Apple/Xcode existing crash reports and diagnostic logs | Crash/report fields and textual diagnostics | No documented DreyzeOS descriptor | No documented raw EL1 registers or page-table-byte dump | Report may describe its event, but does not bind future image/descriptor/MMU artifacts to one session | Existing-file analysis: no; generating new logs may require reproducing an issue | Offline analysis: no; live collection effects differ | Reproduction changes runtime activity | No persistent firmware write documented for ordinary logs; not a zero-risk guarantee | `SAFE_HOST_ONLY` for existing files; live console-log setup is `STATE_CHANGING` | Apple’s watchOS console workflow requires a logging profile on paired iPhone and reproducing the issue; it does not provide raw MMU tables | **NO** — existing reports lack required fields; live log setup changes diagnostics and still lacks them |
| Peepo / DarkSword research path | Exploit-backed kernel read/write and memory/process inspection; some page-table-related analysis | No DreyzeOS descriptor in reviewed path | Potential partial memory/page-table observations; no demonstrated complete handoff-time register + table snapshot for this target | App/source context alone does not prove one DreyzeOS handoff session | Yes | Yes; kernel-write operations are present in source | Other state effects not fully characterized here | Unknown | `STATE_CHANGING` | Public compatibility evidence names `Watch4,1`, not this project’s `Watch4,2`; exact target support is unproven | **NO** — exploit/write path, target mismatch and evidence gaps |
| usbliter8 T8006 exploit research path | Exploit-specific shellcode/handler/return behavior and fixed boot-environment observations | No DreyzeOS descriptor | Source changes translation/cache state; not a passive table-dump interface | No DreyzeOS session bundle | Yes | Yes | Yes | Unknown; absence not proven | `STATE_CHANGING` | Pinned T8006 `start.S` writes `SCTLR_EL1` and a page-table entry, changes stack/cache/TLB state, and uses its own return path; exact Watch4,2/21U580 support is unestablished | **NO** — state-changing and does not produce the required evidence bundle |
| iBUS / diagnostic cable / DFU-related candidate | Candidate transport/service access only | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | `UNCERTAIN` | Exact target support, read-only semantics and descriptor/MMU export are not established; DFU/recovery is excluded | **NO** — capability and effects unknown; no probing performed |
| UART / boot-log route | Possible text output if a supported route exists | No demonstrated descriptor | No demonstrated register/table-byte export | No session binding demonstrated | Unknown | Unknown | Unknown | Unknown | `UNCERTAIN` | Route, target output and effects are not established; text logs are not page-table bytes | **NO** — at most hints, no required artifacts |
| JTAG/SWD/external debugger | Theoretical register or memory observation if a debug interface is implemented and accessible | Unknown | Theoretical only; no complete target capture path proven | Could be instrumented, but no verified session method exists | Debug interaction/behavior unknown | Write capability unknown | Halt/step would change execution state; exact behavior unknown | Unknown | `UNCERTAIN` / privileged research | Availability, authorization, side effects and exact Watch4,2 path are unproven | **NO** — read-only behavior and capability unestablished |
| DreyzeOS early-entry self-capture | State only after control has reached DreyzeOS | Could consume a descriptor, not prove its original source | Could record post-entry state if implemented; not an unmodified pre-handoff snapshot | Cannot prove the source/session relationship that enabled its own entry | Yes, DreyzeOS must already execute | Writes its BSS/stack | Entry masks DAIF and sets SP/VBAR/CPACR | No flash write intended; not zero risk | `STATE_CHANGING` | Circular for first handoff evidence; observes state after changing it | **NO** — requires the blocked handoff and changes state |

### Source-specific boundaries

* **Peepo:** pinned public README describes exploit-backed kernel R/W for
  `Watch4,1` on its listed watchOS 10.6.1/10.6.2 environment; this is not
  `Watch4,2` compatibility proof. Pinned `darksword.m` includes
  `early_kwrite64` operations. It is not treated as a descriptor exporter or
  complete table-snapshot producer.
* **usbliter8:** pinned T8006 assembly is a state-changing exploit trampoline,
  not a passive observer. It modifies `SCTLR_EL1`, a page-table entry, stack
  and cache/TLB state, then returns through the exploit’s control-flow
  environment. It does not define the DreyzeOS V1 descriptor or provide the
  required complete snapshot/provenance bundle.
* **Apple diagnostics:** Apple documents that existing watchOS crash reports
  are available through the paired iPhone. Its watchOS console-log workflow
  calls for a logging profile on that iPhone and reproducing an issue. This
  may produce diagnostics, not raw EL1/MMU/table evidence, and is not a
  read-only first-session method under this project’s criteria.
* **Local DreyzeOS analysis:** `tools/provenance_envelope.py`,
  `tools/handoff_evidence_verifier.py`, `tools/mmu_snapshot_analyzer.py`, and
  `tools/t8006_evidence_gap.py` consume local files. No capture interface or
  target transport is implemented in those tools.

Pinned public references:

* [Peepo revision `6d20d676f7c2d1620ba4764f7500baa906d67b64`](https://github.com/datalocaltmp/Peepo/tree/6d20d676f7c2d1620ba4764f7500baa906d67b64), especially `README.md` and `Peepo Watch App/darksword.m`.
* [usbliter8 revision `479dbbf4ad80e4a454e0779d1b4d1ec5eb0d7bd5`](https://github.com/JoshAtticus/usbliter8/tree/479dbbf4ad80e4a454e0779d1b4d1ec5eb0d7bd5), especially `t8020_t8006_shellcode/start.S`, `exploit.c`, and T8006 target files.
* Apple, [Acquiring crash reports and diagnostic logs](https://developer.apple.com/documentation/xcode/acquiring-crash-reports-and-diagnostic-logs).

These sources establish only the cited source/documentation behavior. They do
not prove current Watch runtime state, exact-target compatibility beyond what
is explicitly stated, or recovery from arbitrary experimental state.

## Can a real descriptor precede handoff?

**Yes, in principle — before the control transfer itself.** A future loader or
shim can construct a V1 descriptor after it establishes or observes its
handoff facts and before it transfers control to DreyzeOS. This is the natural
producer/consumer ordering. The descriptor must already reside at a proven
readable location when DreyzeOS consumes it. This is a design possibility,
not evidence that such a loader exists or can truthfully populate this target’s
fields.

**No real descriptor is currently available.** No reviewed producer or
capture path in this repository supplies one from a real Watch4,2 session. A
planned, hand-written, synthetic, or reconstructed descriptor is not
EV-000B evidence.

## Can MMU evidence precede the descriptor in one session?

**Logically, yes.** The envelope binds artifacts to a bounded session; it does
not require MMU data to be acquired after the descriptor. An earlier snapshot
can belong to the session if its source, time bounds, hashes, and relationship
to the same `capture_id` are proven.

Session membership does **not** prove that the snapshot describes the
descriptor’s handoff epoch. The evidence must connect TCR/TTBR/MAIR and the
captured table pages to the state relevant at transfer, and account for any
intervening register or page-table changes. Session ID equality is provenance,
not atomicity or state-stability proof. V1 does not carry every translation
register; separate CPU-state evidence may be needed. No such real snapshot is
present now.

## Smallest defensible session dataflow (not an acquisition procedure)

This is a conditional record/evidence ordering only. It gives no transport,
exploit, trigger, command, or device operation and authorizes nothing.

```text
SESSION START
  -> assign capture_id and establish evidence-backed UTC bounds, producer,
     and actual source/interface provenance
  -> freeze selected DreyzeOS image bytes and register their SHA-256
  -> establish a target-bound observation source (currently no reviewed path)
  -> include a real descriptor only if a real producer emitted it
  -> include MMU registers and all required table bytes related to the same
     handoff-relevant state/epoch
SESSION END
  -> hash every artifact; declare complete coverage and per-artifact links
  -> run provenance validator, handoff bundle verifier, then evidence-gap tool
```

The image can be built, frozen, and hashed offline beforehand, but its use in
the session still needs a truthful proven relationship. Coverage cannot be
complete while the descriptor, MMU snapshot, source provenance, or required
table bytes are missing.

## First live action and approval boundary

The first live action would be **establishing or using a target-bound runtime
observation source for a bounded session**. Its interface and effects are
not established, so classification is `UNKNOWN`; it is not approved and must
not be attempted. Any candidate involving exploit execution, a logging
profile, debug-setting changes, execution halt/redirection, RAM/page-table
writes, or CPU-state changes requires its own method-specific review and
explicit user approval.

Before any approval request, a proposal would need to identify what the source
can emit (descriptor, CPU/MMU state, and complete table bytes), how those bytes
relate to one handoff epoch, all state changes, and failure/recovery limits.
This review cannot supply those facts. No user action is requested here.

## What can be done without approval

* Preserve existing static and already-saved host evidence.
* Build, freeze, and hash a selected ELF locally; this alone does not close
  EV-000B.
* Validate a future independently obtained bundle with the existing tools;
  local validation cannot repair missing acquisition provenance.
* Continue static review of a specifically identified public/documented
  candidate without executing it.

No Watch/iPhone acquisition, new diagnostic generation, pairing/service
query, or device setting change is included here.

## Result

```text
BEST CANDIDATE = NONE
REAL DESCRIPTOR AVAILABLE NOW = NO
DESCRIPTOR CAN BE PRODUCED BEFORE CONTROL TRANSFER = YES, IN PRINCIPLE
REAL MMU SNAPSHOT FEASIBLE THROUGH A CURRENTLY REVIEWED PATH = NO
SAME-SESSION PROVENANCE REPRESENTABLE = YES
SAME-SESSION PROVENANCE FOR REAL REQUIRED ARTIFACTS = NOT YET
FIRST LIVE ACTION = ESTABLISH A TARGET-BOUND OBSERVATION SOURCE
FIRST LIVE ACTION CLASSIFICATION = UNKNOWN / USER_APPROVAL_REQUIRED
EV-000B = BLOCKED
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

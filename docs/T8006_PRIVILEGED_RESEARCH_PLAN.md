# T8006 Privileged Research Safety & Evidence Acquisition Plan

Phase 4 — Step 2.15, **Privileged Research Safety & Evidence Acquisition
Plan**.

This is a plan and review artifact only. It does not authorize, describe, or
implement a live acquisition procedure. No Apple Watch was connected, no
exploit or DFU path was run, and no device memory or persistent storage was
accessed while preparing this document.

## 1. Accepted state and scope

| Field | Value |
|---|---|
| Repository | `DreyzeDev/DreyzeOS---Watch-OS` |
| Branch | `master` |
| Accepted baseline | `ff619bdb0770cf49cb1fd8d17979b1aac5856b44` |
| Target | `Watch4,2` / `N131bAP` / `T8006` / watchOS `10.6.1` / `21U580` / AArch64 |
| User authorization | Planning of privileged research only |
| Live execution authorized | **NO** |
| Device actions performed | **NO** |
| Current read-only path | **NOT FOUND** |
| Current loader contract | **BLOCKED** |

The accepted Step 2.14 result found no target-specific method whose source
evidence proves that runtime acquisition is simultaneously memory-read-only,
CPU-state-neutral, non-exploitative, non-persistent, and target-bound. Step
2.15 therefore compares risks and dependencies without selecting an action for
execution.

## 2. Authorization boundary

The explicit authorization for this step covers only static comparison,
source inspection, host-side planning, and preparation of a non-operational
preflight record. It does not cover:

- running Peepo, usbliter8, DFU, USB, iBUS, UART, JTAG, or diagnostic tooling;
- entering a device mode or connecting to the Watch for research;
- writing RAM, page tables, MMIO, flash, NAND, NOR, or other persistent state;
- changing CPU/MMU state, installing handlers, injecting code, or changing
  control flow;
- collecting a live artifact, executing DreyzeOS, or attempting recovery.

No later method is `READ_ONLY_DEVICE_INTERACTION` unless exact source or
authoritative documentation proves all of the following: no device-memory or
page-table write, no CPU execution-state change, no injected code or control
flow hijack, no persistent write, and no patching of iBoot, SecureROM, the
kernel, or a loader. “RAM-only” does not satisfy that definition.

## 3. Evidence and recovery vocabulary

Acquisition review uses the project statuses `CONFIRMED`, `LIKELY`, `DESIGN`,
`UNKNOWN`, and `BLOCKED`. Evidence coverage uses a separate three-way meaning:

- **OBSERVABLE** — a method could expose a value or artifact of this type;
- **POTENTIALLY_CLOSABLE** — the value could contribute to an EV requirement
  after provenance, completeness, and consistency checks;
- **PROVEN** — the requirement has been acquired and independently accepted by
  the existing verifier. No live EV is `PROVEN` in this step.

Recovery is recorded as:

- `RECOVERY_PROVEN` — only bounded local/offline analysis in this plan;
- `RECOVERY_EXPECTED` — documented or commonly expected behavior, not validated
  from an arbitrary experimental target state;
- `RECOVERY_UNKNOWN` — the relevant target behavior is not established;
- `PERSISTENCE_RISK` — a persistent write is possible or has not been excluded.

## 4. Candidate method comparison

The machine-readable version of this table is
`research/t8006_evidence/privileged_risk_matrix.json`. `EV IDs` are raw
requirements that an artifact might contain; they are not closures.

| Method | Target / firmware evidence | State-changing facts | Possible evidence | Safety class | First experiment? |
|---|---|---|---|---|---|
| DreyzeOS static repository/IPSW/ADT/ELF analysis | Exact repository artifacts; no live target state | None on a device | Static facts, format integrity, EV-024/027 context | `LOWER_PRIVILEGED_RISK` / no device interaction | NO |
| Pre-existing target-bound artifact, analyzed locally | Depends on an artifact not present in the accepted repository | Acquisition history is unknown; local analysis itself is reversible | Conditional raw inputs to EV-000, 002, 011, 012, 014, 016, 017, 024–027; completeness and ownership remain separate | `UNKNOWN` for acquisition; local analysis is host-only | UNKNOWN |
| Normal model/UDID/recovery metadata query | Static libirecovery context includes Watch4,2-related metadata; runtime query contract not proven | Query side effects and provenance are not established | At most a target metadata hint for EV-000 | `UNKNOWN` | UNKNOWN |
| Peepo DarkSword path | Public source explicitly covers Watch4,1/T8006 and watchOS 10.6.1/10.6.2; Watch4,2 is not established | Kernel R/W and dump operations are present; exploit and target recovery are not proven safe | Potential partial artifacts for EV-002, 011, 012, 014, 016, 017, 025, 026; no direct initial CPU/MMU-register capture is shown | `HIGH_RISK_STATE_CHANGING` | NO |
| usbliter8 T8006 SecureROM path | T8006-related source; exact Watch4,2/21U580 applicability is not established | RAM writes, PTE/MMU/cache changes, handlers, and control-flow state changes are present in source | No DreyzeOS EV is closed by the reviewed source | `PERSISTENT_WRITE_RISK` and high-risk state changing | NO |
| iBUS / diagnostic adapter / DFU research | Candidate transport only; exact target read semantics are not proven | Device mode, transport, write, and reset behavior are unknown | No EV is proven; hypothetical transport input only | `UNKNOWN` | NO |
| UART or exposed boot-log capture | Candidate text observation; route and target behavior are unverified | Enabling path may require MMIO or CPU state changes; no read-only contract | Untrusted hints only; no critical EV closure | `PRIVILEGED_STATE_CHANGING` / `UNKNOWN` | NO |
| JTAG/SWD/external debugger | Generic debugger concept, not target-bound evidence | Halt, register access, writes, reset, and debug authorization are unresolved | Potential EV-006–012, 014–017, 024–026; EV-018 remains unproven without a complete protected-range record | `PRIVILEGED_STATE_CHANGING` | NO |
| DreyzeOS early-entry self-capture | Current entry code executes before any capture and changes its own state | BSS/stack writes, DAIF/SP/VBAR/CPACR changes, and control transfer occur first | Post-entry observations only; not initial EV-006–010 or delivery proof | `PRIVILEGED_STATE_CHANGING` | NO |
| Existing crash/sysdiagnose artifact | No current target-bound artifact is present | Acquisition provenance and device effects are unknown | Conditional bounded boot metadata or runtime hints | `UNKNOWN` | UNKNOWN |

There is no affirmative `YES` in the first-experiment column. A method that
can expose a useful byte but cannot prove how that byte was acquired does not
meet the first-artifact gate.

## 5. Exact public-source evidence

### Peepo

Source: [datalocaltmp/Peepo](https://github.com/datalocaltmp/Peepo), pinned
revision `6d20d676f7c2d1620ba4764f7500baa906d67b64`.

Relevant files and symbols reviewed:

- `README.md` — target table names Watch4,1/T8006 and watchOS 10.6.1/10.6.2;
- `Peepo Watch App/darksword.m` — `early_kread64`, `early_kwrite64`,
  `ds_pmap_of`, `ds_setup_physmap`, `ds_va_to_phys`,
  `peepo_dump_kernelcache`, and `peepo_dump_process`.

The source supports the conclusion that Peepo is an exploit-backed kernel
read/write research path with partial page-table/physmap-oriented research
capabilities. It does not prove Watch4,2 compatibility, a read-only first
access, complete translation-table coverage, initial CPU-register capture,
runtime DRAM bounds, ownership, or arbitrary-state recovery. Its potential
artifact value is therefore `POTENTIALLY_CLOSABLE`, never `PROVEN` here.

### usbliter8

Source: [JoshAtticus/usbliter8](https://github.com/JoshAtticus/usbliter8), pinned
revision `479dbbf4ad80e4a454e0779d1b4d1ec5eb0d7bd5`.

Relevant files and symbols reviewed:

- `exploit.c` — `t8006_create_overwrite` and
  `t8020_t8006_exploit_run`;
- `t8020_t8006_shellcode/start.S`;
- `t8020_t8006_shellcode/targets/t8006/offsets.h`;
- `usb_req_handler/handler.c` and
  `usb_req_handler/targets/t8006/offsets.h`;
- `t8006_create_shellcode` and related target handlers.

The source demonstrates an exploit-specific T8006-related path with RAM
operations, PTE/MMU/cache manipulation, handler/callback state, and control
flow changes. Exact Watch4,2/21U580 support, read-only behavior, persistent
state behavior, and recovery are not proven. This plan intentionally does not
reproduce transfer sequences, payload layout, exploit addresses, or commands.

### Other public context

XNU, IPSW/ADT parsers, `libirecovery`, `iometa`, PongoOS, and m1n1 provide
architecture or static-analysis context. They do not provide target-bound
runtime CPU state, page-table bytes, ownership, or a read-only Watch4,2/
21U580 acquisition path. Watch4,1 evidence is not promoted to Watch4,2.

## 6. Recovery and failure truth

| Method | Recovery status | What is known | What remains unknown |
|---|---|---|---|
| Host/offline analysis | `RECOVERY_PROVEN` for local files only | No device state is touched by analysis | How any source artifact was originally obtained |
| Pre-existing capture | `RECOVERY_UNKNOWN` | Local inspection is reversible | Device state, acquisition side effects, and provenance |
| Model/UDID query | `RECOVERY_UNKNOWN` | Static device-table context exists | Runtime query side effects and arbitrary-state recovery |
| Peepo | `RECOVERY_UNKNOWN` + `PERSISTENCE_RISK` not excluded | Source describes unstable exploit-backed research and dump outputs | Panic/hang/reset behavior, bootloop risk, exact-target recovery, persistent state |
| usbliter8 | `RECOVERY_UNKNOWN` + `PERSISTENCE_RISK` | Source changes volatile execution/MMU/PTE state | Device-specific failure, reset, bootloop, restore, and persistent side effects |
| iBUS/DFU/diagnostic | `RECOVERY_UNKNOWN` | Public stock/research context only | Exact target accessibility, write behavior, restore from arbitrary state |
| UART/JTAG/debug | `RECOVERY_UNKNOWN` | Generic observation concepts | Halt/reset/write semantics and target recovery |
| DreyzeOS self-capture | `RECOVERY_UNKNOWN` | Current source is host/build audited | Hardware entry and post-entry failure behavior |

The expected Crown + Side Button stock reset path is not a guarantee for an
arbitrary experimental state. Exact DFU availability and successful restore
for Watch4,2/21U580 are also `UNKNOWN`/`BLOCKED`. “RAM-only” reduces the
intended persistent-write surface but does not make the experiment
brick-proof.

## 7. Minimum first-experiment candidates

The dependency-first candidates below are designs, not procedures. None is
approved or executable from this commit.

| Candidate | Intended output | Required state changes | Potential EVs | Decision |
|---|---|---|---|---|
| Target provenance envelope | Model/board/firmware record tied to one artifact | Live identity query semantics and provenance source are unresolved | EV-000, possibly EV-027 | BLOCKED; metadata alone is insufficient |
| CPU register snapshot | Initial EL, SP, DAIF, SCTLR/TCR/TTBR/MAIR/VBAR/CPACR | External capture/halt semantics and initial-state access are unproven | EV-006–010 | BLOCKED |
| Bounded boot metadata copy | Runtime `boot_args`/DeviceTree bytes and ranges | Read path, complete-copy proof, and target bounds are unproven | EV-002, EV-014, EV-026 | BLOCKED |
| Translation-table evidence | Table pages plus governing registers | Complete physical coverage and access method are unproven; exploit paths mutate state | EV-009, EV-011, EV-012, EV-021, EV-024, EV-025 | BLOCKED |
| Runtime memory-map record | DRAM interval and payload/reservation context | Runtime observation and provenance are unproven | EV-002, EV-003, EV-016–019 | BLOCKED |
| Passive local analysis of an already captured artifact | Verify an artifact without touching a device | No device action during analysis; original capture still unknown | Depends on artifact | Allowed only after independently reviewed artifact exists |

The smallest useful *live* experiment is not selected. A provenance-only
record cannot close runtime requirements; a single register or table page
cannot prove a consistent translation regime; and a memory/metadata dump is
not read-only merely because its intended output is a file. The evidence and
recovery dependencies therefore force:

```text
FIRST PRIVILEGED EXPERIMENT CANDIDATE = NONE
```

## 8. Evidence coverage decision

The 28 requirements remain governed by
`research/t8006_evidence/requirements.json`. The candidate methods can at
most make raw inputs observable. No requirement becomes `PROVEN` until an
actual artifact has:

1. target-bound provenance;
2. complete and bounded bytes/fields;
3. integrity hashes matching its declaration;
4. no conflicting duplicate values;
5. independent review by the existing offline verifier; and
6. no unreviewed authority or ownership assumption.

The unresolved critical groups are target provenance (`EV-000`), transfer and
placement (`EV-001`–`EV-005`), CPU/MMU state (`EV-006`–`EV-012`), descriptor
trust (`EV-013`), boot metadata (`EV-014`), framebuffer/reservations/collision
(`EV-016`–`EV-019`), control and persistence (`EV-020`–`EV-023`), and complete
artifact consistency (`EV-024`–`EV-027`).

## 9. Host and hardware inventory for a separately approved future study

This is inventory-level planning only. It is not a connection or acquisition
instruction.

### Required or conditionally required

- WSL2/Ubuntu, Python 3, Make, AArch64 cross-compiler/binutils, and LLVM for
  offline validation — `CONFIRMED` in the repository environment.
- Exact model, board, SoC, firmware, build, and device provenance record —
  `REQUIRED`, currently `UNKNOWN` for a live device.
- Host-side logging, immutable raw-artifact retention, capture ID, timestamp,
  producer, repository SHA, and SHA-256 relationships — `DESIGN`/`REQUIRED`.
- Power/battery condition and production-data backup status recorded before
  any separately approved experiment — `REQUIRED`, currently absent.
- A recovery assessment for the exact target and proposed state changes —
  `REQUIRED`, currently `UNKNOWN`.
- macOS restore tooling or equivalent only if a future approved study proves
  that recovery is available; current exact-target support is `UNKNOWN`.

### Optional or unverified

- UART/serial analyzer: only if a target-specific route and non-invasive
  observation contract are proven; routing, levels, clock, and baud are
  `UNKNOWN`.
- JTAG/debug equipment: target authorization, connector, halt/write behavior,
  and recovery are `UNKNOWN`/`BLOCKED`.
- iBUS/AWRT adapter, RP2350/Pico, USB interposer, or special cable: candidate
  categories only; none is proven mandatory by the reviewed evidence.
- QEMU: host-only synthetic testing, not target evidence.

No inventory item authorizes connection, mode changes, exploit execution, or
device writes.

## 10. Preflight and approval boundary

The non-operational checklist is maintained in
`docs/T8006_PRIVILEGED_PREFLIGHT.md`. Before any future live proposal, every
required item must be complete and the user must approve the *specific named
experiment*, its expected artifact, allowed state changes, and recovery
assessment. A generic authorization to research does not satisfy that gate.

Immediate stop conditions:

- target identity or firmware is not independently recorded;
- source/revision does not establish exact target applicability;
- any RAM, page-table, CPU-state, control-flow, or persistent effect is
  unbounded;
- recovery is presented as guaranteed when it is only expected or unknown;
- the artifact cannot be represented and checked by the existing pipeline;
- the experiment requires an exploit, DFU, USB, payload, or arbitrary write;
- the user has not approved the exact experiment after reviewing its risks.

## 11. Step result

```text
PRIVILEGED RESEARCH PLAN = COMPLETE
FIRST PRIVILEGED EXPERIMENT CANDIDATE = NONE
LIVE EXECUTION AUTHORIZED = NO
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

## 12. Independent review record

The required subagent review roles were completed without device interaction:

- **A — Privileged Method Comparator:** compared DreyzeOS static analysis,
  Peepo, usbliter8, iBUS/diagnostic/DFU, UART, JTAG, self-capture, and local
  artifact paths.
- **B — Failure/Recovery Analyst:** separated `RECOVERY_PROVEN`,
  `RECOVERY_EXPECTED`, `RECOVERY_UNKNOWN`, and `PERSISTENCE_RISK`; no
  arbitrary-state recovery guarantee was accepted.
- **C — Minimum First Experiment Designer:** evaluated provenance, CPU-state,
  boot metadata, memory-map, and translation-table artifact candidates and
  selected `NONE`.
- **D — Hardware/Host Setup Reviewer:** produced a non-operational inventory
  and confirmed that iBUS/AWRT/RP2350, UART, JTAG, and restore assumptions are
  not proven mandatory or available.
- **E — Independent Safety Reviewer:** **ACCEPTED**. The final review found no
  operational exploit guidance, no target promotion, no unqualified recovery
  claim, no inconsistent EV coverage, and no production/runtime change.

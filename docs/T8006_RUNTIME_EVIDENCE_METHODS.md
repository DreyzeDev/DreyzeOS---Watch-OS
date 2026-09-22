# T8006 Runtime Evidence Acquisition Methods

Phase 4 — Step 2.14, **Read-Only Target Evidence Acquisition Method Review**.

This document is a static review of possible ways to obtain the runtime
evidence listed in `research/t8006_evidence/requirements.json`. It is not a
capture procedure, an exploit plan, a loader design, or authorization to
interact with an Apple Watch.

## Accepted state and scope

| Field | Value |
|---|---|
| Repository | `DreyzeDev/DreyzeOS---Watch-OS` |
| Branch | `master` |
| Accepted review baseline | `e73fdeff82ebbf26bd80b140256ae2602b596ee0` |
| Target | `Watch4,2` / `N131bAP` / `T8006` / watchOS `10.6.1` / `21U580` / AArch64 |
| Device actions performed | **NO** |
| Peepo/usbliter8/DFU/USB execution | **NO** |

The review uses the existing DreyzeOS evidence plan, verifier, MMU analyzer,
static IPSW/ADT artifacts, and pinned public source revisions. No real device
was connected or queried.

## Decision

**READ_ONLY TARGET EVIDENCE PATH = NOT_FOUND**

The review found host-only/offline methods and several privileged or
state-changing research paths. It did not find a method whose source evidence
proves all of the following for this exact target: no device-memory write, no
page-table modification, no CPU-state modification, no injected-code
execution, no control-flow hijack, no persistent write, and production-quality
provenance for the resulting runtime artifacts.

This is a conservative `NOT_FOUND`, not a claim that no future Apple or
research interface could ever be read-only. A future method must be reviewed
from its exact source and target behavior before receiving the
`READ_ONLY_DEVICE_INTERACTION` label.

## Strict safety rule

`READ_ONLY_DEVICE_INTERACTION` is assigned only when source or authoritative
documentation proves that the acquisition path:

1. does not write device RAM or page tables;
2. does not modify CPU execution state;
3. does not execute injected code or use a control-flow hijack;
4. does not write flash, NAND, NOR, or another persistent device state; and
5. does not require patching iBoot, SecureROM, the kernel, or a loader.

If any one of these properties is not proven, the classification remains
`UNKNOWN`, `PRIVILEGED_RESEARCH_REQUIRED`, or
`POTENTIALLY_STATE_CHANGING`. “RAM-only” is not evidence of zero risk.

`NO_DEVICE_INTERACTION` below applies only to local source/artifact analysis.
It does not certify how a runtime artifact was originally acquired.

## Method matrix

`EV IDs potentially observable` means that an artifact could contain a raw
input for that requirement. It does **not** mean that the requirement is
closed. `EV IDs not closed` lists the important dependencies that the method
cannot prove by itself.

| Method | Target / evidence | Requires exploit | Memory writes | CPU-state changes | Persistent writes | EV IDs potentially observable | Safety class | Recommended for first capture? |
|---|---|---:|---:|---:|---:|---|---|---|
| DreyzeOS repository, IPSW, ADT, ELF and offline tools | Exact static files and host-side model behavior; no live state | NO | NO | NO | NO | `EV-024`, `EV-027` format/metadata checks only | `NO_DEVICE_INTERACTION` | NO |
| Pre-existing target-bound dump, manifest, or report analyzed locally | Only bytes already present on the host; acquisition history must be separately attested | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Conditional: `EV-000`, `EV-002`, `EV-009`, `EV-011`, `EV-012`, `EV-014`, `EV-016`, `EV-017`, `EV-024`, `EV-025`, `EV-026`, `EV-027` | `NO_DEVICE_INTERACTION` for analysis; acquisition `UNKNOWN` | UNKNOWN |
| Normal model/UDID or recovery metadata query | Device identity metadata at most; not runtime registers or RAM | NO | UNKNOWN | UNKNOWN | UNKNOWN | At most an input to `EV-000`; identity provenance remains open | `UNKNOWN` | UNKNOWN |
| Peepo `darksword` path | Watch4,1/T8006 kernel R/W and partial page-table/physmap-backed dumps | YES | YES | UNKNOWN | UNKNOWN | Potential raw inputs to `EV-002`, `EV-014`, `EV-016`, `EV-017`, `EV-025`, `EV-026`; possibly partial `EV-011/012/021` | `POTENTIALLY_STATE_CHANGING` | NO |
| usbliter8 T8006 SecureROM path | Exploit-specific USB, shellcode, handler, MMU/PTE and control-flow state | YES | YES | YES | UNKNOWN | No DreyzeOS runtime requirement is closed by the reviewed source | `POTENTIALLY_STATE_CHANGING` | NO |
| iBUS / diagnostic adapter / DFU research path | Candidate transport; exact Watch4,2 and 21U580 read semantics are not proven | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | None proven; hypothetical transport inputs only | `UNKNOWN` | NO |
| UART or exposed boot-log capture | Possible text/log observations; setup and routing are unverified | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | At most untrusted hints for CPU or boot metadata; no critical EV is closed | `UNKNOWN` | NO |
| JTAG/SWD/external debugger or memory dump | Potential register and memory observation, but halt/write behavior must be ruled out | NO/UNKNOWN | UNKNOWN | YES/UNKNOWN | UNKNOWN | Potential raw inputs to `EV-006`–`EV-012`, `EV-014`–`EV-018`, `EV-024`–`EV-026` | `PRIVILEGED_RESEARCH_REQUIRED` | NO |
| DreyzeOS early-entry self-capture | Post-entry values after DreyzeOS has already changed its entry state | NO | YES to its own BSS/stack | YES | UNKNOWN | Post-entry observations only; does not close initial `EV-006`–`EV-010` or delivery requirements | `POTENTIALLY_STATE_CHANGING` | NO |
| Existing crash/sysdiagnose artifact | Host analysis of a local artifact; no current target-bound artifact is present | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Conditional bounded `EV-014/026` or metadata inputs | `NO_DEVICE_INTERACTION` for analysis; acquisition `UNKNOWN` | UNKNOWN |
| XNU / `ipsw` / `libirecovery` / `iometa` static tooling | Architecture, ABI, device-table and firmware-analysis context | NO | NO | NO | NO | Static context only; no target runtime EV is closed | `NO_DEVICE_INTERACTION` | NO |

There is no `YES` in the final column because no reviewed method meets the
strict read-only definition for target-specific runtime acquisition.

## Exact source audit

### Peepo

Source: [datalocaltmp/Peepo](https://github.com/datalocaltmp/Peepo), pinned
revision `6d20d676f7c2d1620ba4764f7500baa906d67b64`.

Target evidence in `README.md` is for Series 4 `Watch4,1`, T8006, and
watchOS 10.6.1/10.6.2. The compatibility table does not establish
`Watch4,2`. In `Peepo Watch App/darksword.m`, the reviewed symbols include
the physical OOB read/write primitive, `early_kread64`, `early_kwrite64`,
`ds_pmap_of`, `ds_setup_physmap`, `ds_va_to_phys`,
`peepo_dump_kernelcache`, and `peepo_dump_process`.

The source proves a kernel R/W exploit path and partial page-table/physmap
reads. It also writes exploit state and dump files. It does not provide a
CPU-register snapshot, complete table-byte coverage, target-bound
Watch4,2/21U580 provenance, complete runtime DRAM bounds, ownership, or a
DreyzeOS handoff. Therefore the method is not read-only and is not a first
artifact candidate.

### usbliter8

Source: [JoshAtticus/usbliter8](https://github.com/JoshAtticus/usbliter8),
pinned revision `479dbbf4ad80e4a454e0779d1b4d1ec5eb0d7bd5`, already cited by
the repository's T8006 loader research.

The relevant static evidence is in `exploit.c`,
`t8020_t8006_shellcode/start.S`,
`t8020_t8006_shellcode/targets/t8006/offsets.h`,
`usb_req_handler/handler.c`, and
`usb_req_handler/targets/t8006/offsets.h`. The source contains an exploit
overwrite path, T8006 shellcode, MMU/cache and PTE changes, handler/callback
installation, and control-flow state changes. The source does not provide a
read-only runtime evidence capture or a DreyzeOS loader contract.

This document deliberately records only capability and evidence boundaries;
it does not reproduce exploit commands, transfer sequences, payload layout,
or device addresses.

### DreyzeOS and public static context

| Source | Revision / files | What is proven | What is not proven |
|---|---|---|---|
| DreyzeOS | `e73fdeff82ebbf26bd80b140256ae2602b596ee0`; `tools/`, `research/t8006_evidence/`, `docs/` | Offline verifier, bounded parsers, static ADT facts, and closed production gates exist | No live target capture, runtime DRAM, live table bytes, or acquisition path |
| Apple XNU | `apple/darwin-xnu` revision `2ff845c2e033bd0ff64b5b6aa6063a1f8f65aa32`, `pexpert/pexpert/arm64/boot.h` | Generic ARM64 `boot_args` layout context | Watch4,2 iBoot values, runtime pointer bounds, or DreyzeOS ABI |
| `blacktop/ipsw` | revision `be86fee0bab49c011e74dc34f723c4dd1ffdaf51` | Offline IPSW/DT/kernelcache/Mach-O analysis context | Live device state |
| `libimobiledevice/libirecovery` | revision `93c117c29b1f6669bc4ceca8b84e1df06449fe33` | Static device-table context includes Watch4,2/CPID information | A read-only runtime memory/register interface |
| `Siguza/iometa` | revision `9a893d9167144468d8d22b543e434136239cd04c` | Static Watch/S4 symbol metadata context | Runtime target state or safe capture |

## Evidence coverage and remaining requirements

The authoritative inventory is `EV-000` through `EV-027` in
`research/t8006_evidence/requirements.json`. No reviewed acquisition method
closes the critical runtime requirements. The main gaps are:

- `EV-000`: target-bound provenance independently binding every artifact to
  Watch4,2/T8006/21U580;
- `EV-002`–`EV-005`: runtime DRAM, payload placement, bounds, VA and entry;
- `EV-006`–`EV-010`: initial EL1/SP/DAIF and normalized translation/cache/vector
  state;
- `EV-011`–`EV-012`, `EV-021`, `EV-024`–`EV-025`: complete table bytes and
  consistent mapping evidence;
- `EV-013`, `EV-020`: descriptor prefix readability and independent authority;
- `EV-014`, `EV-026`: bounded runtime boot_args/DeviceTree copies;
- `EV-016`–`EV-019`: framebuffer, complete reservations, collision and
  ownership proof;
- `EV-001`, `EV-022`–`EV-023`: transfer and no-persistent-write proof; and
- `EV-027`: one complete, conflict-free, target-bound bundle.

The static `/memory` artifact remains `base=0,size=0`; it does not provide
`EV-002`. Peepo's Watch4,1 evidence does not promote to Watch4,2. A non-zero
address, a page-table read, or a descriptor `VERIFIED` bit does not provide
authority or ownership.

## First artifact decision

**FIRST ARTIFACT ACQUISITION = BLOCKED**.

The dependency-first artifact would be a target-bound provenance envelope for
the first runtime artifact, but filling that envelope requires an acquisition
method that has not been shown to be read-only. No Peepo, usbliter8, DFU, USB,
JTAG, UART, or diagnostic action is authorized or performed in this step.

Host-only preparation remains allowed:

```bash
python3 tools/handoff_evidence_verifier.py --help
python3 tools/t8006_evidence_gap.py --help
```

These commands validate local evidence only. They cannot acquire target state.

## Stop conditions

Stop and request explicit user approval before any method classified other
than `NO_DEVICE_INTERACTION` is considered. Stop permanently for this step if
the proposed method can write RAM/page tables, alter CPU state, execute
injected code, change control flow, write persistent storage, or lacks exact
Watch4,2/21U580 provenance. Do not convert a blocked acquisition into an
exploit path.

```text
OFFLINE INFRASTRUCTURE = COMPLETE
EVIDENCE PIPELINE READY = YES
NEXT ACTION REQUIRES TARGET-SPECIFIC DEVICE EVIDENCE
USER_APPROVAL_REQUIRED
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

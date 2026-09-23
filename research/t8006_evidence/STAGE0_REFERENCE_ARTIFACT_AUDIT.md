# Stage-0 Reference Artifact Audit

Status: **DESIGN / HOST ONLY**
Target execution: **NOT IMPLEMENTED**
Hardware interaction: **NONE**

This audit freezes one concrete, reproducible host reference for the minimum
Stage-0 record and pre-kernel gate. It is not Watch firmware, an AArch64
payload, a loader, or an operational launch method. No Apple Watch/iPhone
interaction, target transfer, exploit, DFU/recovery, MMIO, target memory access,
or persistent device write was performed.

## What this step closes

- A concrete host-only Stage-0 reference source and executable now exist.
- The host ELF has a reproducible SHA-256 and byte size, with its source
  revision and source-input hashes recorded by the build-generated manifest.
- The session, CPU, MMU, memory, result, and existing Loader Handoff ABI V1
  layouts are frozen by fixed-width fields and compile-time size/offset checks.
- The failure precedence and pre-kernel gate behavior are exercised by C tests.
- Static checks confirm that the reference has no target address literals in
  its executable code, no transfer implementation, and no MMIO or persistent
  writer imports.

These are host/static facts only. In particular, the SHA authenticates neither
the producer nor target residency; it identifies the local ELF bytes produced
by the recorded build.

## Artifact and build

Build with:

```sh
make stage0-reference
```

The build tool is `tools/build_stage0_reference.py`. It uses the native host C
compiler, refuses ARM/AArch64 compiler triples, defines
`STAGE0_HOST_REFERENCE`, and builds only the files under
`research/t8006_evidence/stage0_reference/`. The header also rejects ARM target
compilation. The default output directory is ignored `build/stage0_reference/`
and contains:

- `stage0_reference.elf` — host-native test/reference executable;
- `stage0_reference.o`, `main.o` — deterministic host link inputs;
- `stage0_reference.map` — host linker map;
- `stage0_reference.readelf.txt` — ELF header, program headers, and sections;
- `stage0_reference.nm.txt` — symbol inventory;
- `stage0_reference.objdump.txt` — disassembly;
- `stage0_reference_manifest.json` — generated manifest with artifact/source
  hashes, source commit, host machine/compiler, host ELF entry, sidecar hashes,
  and local SHA-256/size references for the DreyzeOS ELF and flat BIN.

The tracked `research/t8006_evidence/stage0_reference_manifest.template.json`
defines stable manifest fields. The generated manifest is intentionally a
build output: its exact `source_commit` is known only when building a committed
checkout. Build outputs are not committed. Reproducibility tests build into
two different temporary directories and compare the resulting ELF bytes and
SHA-256, normalized build commands, and sidecar hashes. Output paths in the
recorded build commands and sidecar text are normalized as
`<repo>`/`<output>` placeholders; fixed object names avoid nondeterministic
compiler temporary-object names in the linker map.

The DreyzeOS ELF and flat BIN hashes identify exact local build outputs only;
they do not prove target residency, authenticity, ownership, or which image a
future launch method would use. Both are recorded separately; this reference
does not select a hardware payload representation.

The reported ELF `_start` and entry address belong to the host process runtime;
they are not a DreyzeOS entry point or a Watch address. `target_entry_symbol`
and `required_alignment` remain null, and `target_addresses_assigned`,
`target_executable`, and `transfer_implementation_present` remain false.

## Frozen record interface

All records are packed, use fixed-width integer fields, and are host reference
formats. Scalar byte order is little-endian; the header rejects hosts that do
not declare little-endian byte order. Magic tags are fixed eight-byte ASCII
values (`D0SES001`, `D0CPU001`, `D0CPU002`, `D0MMU001`, `D0MEM001`,
`D0RES001`). `present_mask` records supplied values and
`proven_mask` records separately asserted evidence; presence never implies
proof or access authority.

| Record | Size | Purpose |
|---|---:|---|
| `stage0_session_header_t` | 244 bytes | Capture ID, bounded UTC text, producer/interface, and frozen DreyzeOS/stage-0 image SHA-256 values. |
| `stage0_raw_cpu_record_t` | 120 bytes | CPU state observed before any optional normalization. |
| `stage0_post_normalization_cpu_record_t` | 120 bytes | Same field layout, distinguished by record phase; no normalization is implemented here. |
| `stage0_mmu_record_t` | 128 bytes | Relevant translation registers, declared geometry, independent present/proven masks, table-page counts, and table-bytes hash. |
| `stage0_range_t` | 24 bytes | 64-bit base/length, explicit physical/virtual/unknown address space, and independent presence/bounds/permission/ownership flags. |
| `stage0_memory_record_t` | 568 bytes | Runtime DRAM, Stage-0 code/stack, scratch output, kernel payload, framebuffer, and bounded reserved-range inventory/completeness. |
| `stage0_result_t` | 36 bytes | Deterministic status, phase, pre-kernel gate result, and `transfer_performed`. |
| `stage0_handoff_descriptor_v1_t` | 128 bytes | Alias of the existing V1 wire type; it does not define or alter V2. |

For session-header fields, `flags` uses adjacent PRESENT/PROVEN bits per field
as named in the header; unused bits are reserved and must be zero. CPU, MMU,
and memory `present_mask`/`proven_mask` bits are defined by their
`STAGE0_*_FACT_*` constants. Range flags independently distinguish presence,
bounds, permissions, and ownership. A PROVEN bit is a producer assertion to
be independently reviewed; it does not grant access authority. Reserved flags
and result fields must be zero. The raw and post-normalization CPU records use
the corresponding CPU magic and phase. The MMU record now has separate masks;
its fixed offsets are `present_mask=16`, `proven_mask=24`, `SCTLR_EL1=32`, and
table hash `=96`.

The CPU and MMU values are records only: this reference does not read system
registers, inspect addresses, walk page tables, or validate that supplied
bytes came from a target. The V1 descriptor is frozen by compile-time checks,
including its 128-byte size and existing field offsets. The reference has no
descriptor producer that can turn untrusted values into trusted facts.

## Phases and statuses

The phase IDs are stable: `OBSERVE_ONLY=1`,
`NORMALIZE_IF_APPROVED=2`, `PRODUCE_EVIDENCE=3`, `PREPARE_DESCRIPTOR=4`,
`TRANSFER=5`, and `PRE_KERNEL_GATE=6`. They label a future contract boundary;
this executable performs none of the target-side phase actions. In particular,
the `TRANSFER` phase is vocabulary only.

Status values are stable and deterministic:

| Value | Status |
|---:|---|
| 0 | `OK_TO_EVALUATE_TRANSFER` |
| 1 | `ABORT_UNKNOWN_EL` |
| 2 | `ABORT_BAD_STACK` |
| 3 | `ABORT_TRANSLATION_UNKNOWN` |
| 4 | `ABORT_MAPPING_UNPROVEN` |
| 5 | `ABORT_MEMORY_OWNERSHIP_UNPROVEN` |
| 6 | `ABORT_COLLISION` |
| 7 | `ABORT_DESCRIPTOR_INVALID` |
| 8 | `ABORT_OUTPUT_BUFFER_INVALID` |
| 9 | `ABORT_PERSISTENCE_POLICY` |
| 10 | `ABORT_TRANSFER_GATE_BLOCKED` |

The evaluator rejects in the listed order: EL; stack; translation; mappings;
ownership; complete and collision-free range audit; trusted descriptor prefix
and structural validity; output buffer; proven no-persistent-write policy; and
finally the separately evaluated pre-kernel gate. Any missing or non-canonical
proof input fails closed. A positive result means only
**OK_TO_EVALUATE_TRANSFER in this host model**. It is not permission to transfer
and does not invoke a function pointer, branch to a payload, or transfer
control. `transfer_performed` is always zero, including for the positive test
case.

## Static safety boundary

The reference accepts only Boolean gate facts, not evidence-provided pointers
or target addresses. It does not dereference any such data. Source and linked
ELF audits check that it has no MMIO/UART/AIC/framebuffer writer symbols, no
persistent storage writer imports, no indirect payload call/jump, and no
guessed T8006 address constants in source or executable `.text`. The separate
production DreyzeOS ELF remains built by the existing AArch64 Makefile path;
the host reference sources are not linked into it.

The host compiler/build tool writes local files under `build/`; this ordinary
host build output is not a persistent write to the Watch. No such build action
is part of the reference executable's runtime behavior.

## Readiness impact

| Fact | Result after this step |
|---|---|
| Concrete Stage-0 contract source/reference exists | **CONFIRMED — host source only** |
| Reproducible local reference ELF identity/hash | **CONFIRMED — host build only** |
| Loader Handoff ABI V1 layout | **CONFIRMED unchanged at 128 bytes** |
| Target Stage-0 address/placement and resident bytes | **BLOCKED** |
| Target entry PC and executable mapping | **BLOCKED** |
| Stage-0 stack/scratch bounds, ownership, and collision freedom | **BLOCKED** |
| Live EL/DAIF/MMU/cache state and required table bytes | **UNKNOWN / BLOCKED** |
| Reviewed target launch/output method and failure/recovery behavior | **BLOCKED** |
| Real descriptor, target-bound runtime artifacts, and EV-000B | **BLOCKED** |
| First Stage-0 execution | **NOT READY** |
| First DreyzeOS kernel entry | **NOT READY** |
| Loader contract / first hardware execution | **BLOCKED / NOT READY** |

No runtime CPU/MMU/RAM fact, payload ownership, mapping, control-transfer
capability, or target execution readiness is established by synthetic tests
or a host ELF. EV-000A remains confirmed; EV-000B remains blocked; EV-000C
remains unknown and non-critical. The next technical prerequisite is an
independently reviewed pre-Stage-0 proof for one exact artifact and launch
proposal, including its initial fetch mapping/EL/stack assumptions, ownership,
side effects, bounded stop behavior, and required user authorization. This
document does not specify an operational launch method.

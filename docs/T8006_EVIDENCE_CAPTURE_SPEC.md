# T8006 runtime evidence capture specification

Phase 4 — Step 2.12 defines the data contract for a future, offline evidence
bundle. It does **not** define how to exploit, attach to, deliver bytes to, or
execute anything on an Apple Watch. No field in this specification grants
memory, MMIO, USB, DFU, flash, or control-flow authority.

## Purpose and status

The specification describes the minimum facts needed to evaluate the existing
Loader Entry Contract for the exact research target:

```text
Watch4,2 / N131bAP / n131bap / T8006
watchOS 10.6.1 / 21U580 / AArch64
```

The current repository has no target-bound runtime bundle. Consequently the
target remains:

```text
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

Repository-owned synthetic bundles are useful for testing the verifier, but
their evidence status is `DESIGN` and their identity is never proven.

## Bundle layout

The manifest is `dreyzeos.handoff_evidence.v1` and all artifact paths are
relative to the manifest directory. A consumer must reject absolute paths,
`..` escapes, duplicate/conflicting declarations, missing files, and hash
mismatches.

```text
bundle.json
DreyzeOS.elf
handoff_descriptor.bin
mmu_snapshot.json
physical-memory-*.bin       # only files referenced by the MMU manifest
boot_args.bin               # required only when boot_args is consumed
device_tree.bin             # required only when DeviceTree is consumed
```

Every referenced file carries SHA-256. The hash proves only that local bytes
match the bundle declaration. It is not authenticity, provenance, or proof
that the bytes came from a genuine Watch.

The existing Step 2.10 snapshot format remains authoritative for translation
tables. This bundle references it; it does not create a second page-table
schema.

## Fact and proof encoding

Presence and proof are independent. Numeric values use:

```json
{
  "value": "0x1234",
  "value_present": true,
  "value_proven": false,
  "source": "capture.cpu_state.ttbr0_el1"
}
```

All `*_present`, `*_proven`, `complete`, `normalized`, and `proven` fields
must be JSON booleans. A string such as `"false"` is malformed evidence and
must not be truth-tested as true.

Ranges use `[base, base + length)` and contain an explicit `address_space` of
`physical` or `virtual`:

```json
{
  "base": "0x100000000",
  "length": "0x20000",
  "address_space": "virtual",
  "present": true,
  "bounds_proven": true,
  "ownership_proven": false,
  "mapping_proven": false,
  "readable": true,
  "writable": false,
  "executable": true,
  "source": "capture.loader_contract.kernel_text"
}
```

The verifier performs overflow-safe arithmetic. A numeric PA/VA, a complete
file, or an MMU descriptor never independently grants authority to access that
range.

## Target metadata and provenance

The manifest records model, board, SoC, firmware, build, and architecture.
The verifier reports two separate results:

* `TARGET_METADATA_MATCH`: strings agree with the expected project target;
* `TARGET_IDENTITY_PROVEN`: an explicit, externally attested provenance claim
  binds the artifact set to that target.

Matching strings are not identity proof. A synthetic fixture must set
`identity_proven` to `false`. The source evidence status must be `CONFIRMED`
before a target-facing result can be considered, and even then the complete
critical graph is required.

For a non-synthetic target-facing bundle, add
`provenance_envelope: {"schema":"dreyzeos.target_provenance_envelope.v1"}`.
The exact schema is documented in
[docs/TARGET_PROVENANCE_ENVELOPE.md](TARGET_PROVENANCE_ENVELOPE.md). It
separately records metadata match, identity proof, local artifact presence/hash,
target binding, and runtime proof. EV-000 coverage must include `image`,
`handoff_descriptor`, and `mmu_snapshot`; optional CPU, runtime-memory,
boot_args, DeviceTree, and transfer artifacts need not exist yet.

The older top-level `target_provenance` object is only a compatibility summary;
it is not sufficient to prove EV-000. SHA-256 is local-byte integrity only,
not cryptographic authenticity. The verifier rejects promotion of a synthetic
`DESIGN` bundle to hardware readiness even if status strings are manually
changed.

Record capture provenance, producer, timestamp, firmware/build context, and
the relationship between every artifact and the provenance record. Do not
claim cryptographic authenticity merely because the manifest has SHA-256.
The current user-observed Watch metadata record is contextual only and must not
be copied into a runtime identity claim.

## Required artifacts

### Image

`DreyzeOS.elf` is a local, hashed AArch64 ELF. The manifest may state the
expected entry, but the verifier compares it with `_start` and does not treat
the declaration as proof. The current image remains fixed non-PIC at linked
VMA `0x100000000`; that is a placeholder until a target mapping is proven.

### Loader Handoff ABI V1 descriptor

`handoff_descriptor.bin` must provide exactly the 128-byte V1 prefix. Its
magic, version, size, flags, reserved fields, entry EL, payload PA/VA/size,
MMU state, and bounded ranges are validated. The `VERIFIED` bit is an
assertion only.

Before any nested field can be used, the evidence must separately state:

1. the descriptor prefix is readable under a mapping already proven by the
   loader;
2. exactly 128 bytes were copied into trusted storage;
3. nested ranges are independently validated before use.

An inline JSON hex descriptor is not an acceptable substitute for a hashed
local artifact in the reference verifier.

### CPU state

Provide independently marked facts for:

```text
current_el, sp, daif
sctlr_el1, tcr_el1, ttbr0_el1, ttbr1_el1, mair_el1
vbar_el1, cpacr_el1
```

Also provide explicit normalization records for EL1, DAIF, translation policy,
I-cache, D-cache, VBAR, and FP/SIMD state. The verifier compares these values
with the MMU snapshot. If two independently proven values disagree, the
result is `EVIDENCE_CONFLICT` and the graph is blocked; the verifier never
chooses the convenient source.

### MMU snapshot

Reference the Step 2.10 manifest and its SHA-256. The manifest must include
proven TCR/TTBR/MAIR/SCTLR values when mapping evidence is used, and its own
target object must match the bundle target. For every required VA walk, every
physical page containing a table descriptor must be included in a supplied
physical-memory region with both:

```text
memory_bytes_present = true
memory_range_complete = true
```

A partial dump is not a complete RAM map. Missing or truncated table pages
make the corresponding result `TABLE_BYTES_MISSING` or
`PHYSICAL_DUMP_INCOMPLETE`, never “probably mapped”.

### Runtime memory and protected ranges

Provide independently proven runtime DRAM `base` and `size` with provenance
exactly `RUNTIME_VERIFIED`. The static ADT `/memory = 0,0`, a product RAM
quantity, and historical `0x800000000 / 1 GiB` values do not satisfy this
requirement.

Declare bounded ranges for, as applicable:

```text
payload physical and virtual intervals
stage-0, loader code, loader stack, loader heap
descriptor source and descriptor copy
boot_args, DeviceTree, framebuffer
kernel stack and all reserved/protected intervals
```

Physical and virtual spaces must remain separate. The producer must explicitly
prove that the protected/reserved list is complete. Without that claim,
`COLLISION_AUDIT_COMPLETE` remains false even when all listed intervals are
disjoint.

## Objects and control transfer

If boot_args or DeviceTree are consumed, provide local complete copies, bounded
lengths, and independently proven readable ranges. The verifier uses the
known XNU ARM64 layout only for object consistency. It does not turn XNU
`boot_args` into the DreyzeOS loader ABI. DeviceTree nested ranges must remain
inside the independently declared DeviceTree interval.

Provide `control_transfer.entry_pc`, target, and an explicit proof of the
future handoff operation. A mapping cannot synthesize a branch or a jump.
Provide `persistent_write_required` as a separately proven boolean `false`.

## Acceptance graph

The first handoff gate requires all critical facts in one internally
consistent environment:

* target provenance;
* payload PA/VA/size/alignment and ownership;
* EL1, aligned SP, DAIF, translation/cache policy;
* TCR/TTBR/MAIR/SCTLR consistency;
* complete executable/readable/writable mappings;
* descriptor bootstrap/readability and trusted copy;
* runtime DRAM and protected-range completeness;
* boot_args/DeviceTree bounds when used;
* collision audit;
* control transfer;
* no persistent write.

The offline verifier can report a synthetic `OFFLINE CONTRACT RESULT = READY`
when its graph is complete. That is a logic-test result. It does not change
`HARDWARE EVIDENCE STATUS = DESIGN`, and it never changes the real target
status to READY.

## Safety boundary

This specification is data-only. It authorizes no operation. In particular it
does not define USB/DFU delivery, exploit steps, arbitrary RAM writes, payload
execution, control-flow primitives, MMIO access, framebuffer writes, IRQ
enablement, page-table writes, or persistent storage changes.

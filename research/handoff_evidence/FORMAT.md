# DreyzeOS offline handoff evidence bundle format

Schema identifier: `dreyzeos.handoff_evidence.v1`.

This format is a local, host-only container for evidence produced by static
analysis or a future captured snapshot. It is not a loader protocol and it
does not authenticate a Watch capture. The verifier never opens device memory,
follows a supplied pointer, executes a payload, or writes hardware.

Target identity and artifact provenance use the nested
`dreyzeos.target_provenance_envelope.v1` schema described in
[docs/TARGET_PROVENANCE_ENVELOPE.md](../../docs/TARGET_PROVENANCE_ENVELOPE.md).
It is validated by this same offline verifier and is not a second evidence
pipeline.

## Bundle layout

The bundle is one JSON file plus local files referenced by relative paths. All
paths are relative to the directory containing the JSON file. Absolute paths,
`..` escapes, duplicate artifact aliases, and missing declared files are
rejected. A typical directory is:

```text
bundle.json
DreyzeOS.elf
mmu_snapshot.json
descriptor.bin
boot_args.bin             # optional, only if supplied
device_tree.bin           # optional, only if supplied
physical-memory-*.bin     # referenced by mmu_snapshot.json, optional
```

The bundle references the existing Step 2.10 snapshot format; it does not
copy page-table blobs into a second schema. See
[research/mmu_snapshots/FORMAT.md](../mmu_snapshots/FORMAT.md).

## Evidence vocabulary

`source.evidence_status` is one of `CONFIRMED`, `LIKELY`, `DESIGN`,
`UNKNOWN`, or `BLOCKED`. Repository-owned fixtures use `DESIGN`. It describes
the evidence source, not verifier success.

Numeric facts use this object shape:

```json
{
  "value": "0x100000000",
  "value_present": true,
  "value_proven": false,
  "source": "capture.cpu_state.pc"
}
```

`value_present` means bytes or a declaration contain a value. It never implies
that the value is proven. `value_proven` must be set independently by the
producer and is not inferred from a non-zero value, a hash, or a descriptor
flag.

A range has the following form:

```json
{
  "name": "kernel-stack",
  "base": "0x100010000",
  "length": "0x10000",
  "address_space": "virtual",
  "present": true,
  "bounds_proven": true,
  "ownership_proven": false,
  "readable": true,
  "writable": true,
  "executable": false,
  "mapping_proven": false,
  "source": "capture.loader_contract.stack"
}
```

Ranges use `[base, base + length)` semantics. Bounds are overflow-checked;
zero-length intervals are not valid proof ranges. Physical and virtual ranges
never collide with each other in the verifier.

## Required top-level fields

```json
{
  "schema": "dreyzeos.handoff_evidence.v1",
  "architecture": "aarch64",
  "target": { ... },
  "source": { "kind": "synthetic", "evidence_status": "DESIGN" },
  "provenance_envelope": { "schema": "dreyzeos.target_provenance_envelope.v1" },
  "image": { ... },
  "handoff_descriptor": { ... },
  "mmu_snapshot": { ... }
}
```

The verifier requires the image, descriptor, and MMU manifest to be local
artifacts with SHA-256 declarations. SHA-256 means only “the local file
matches the bundle declaration”; it is not cryptographic authenticity and it
does not prove that the file came from a genuine Watch.

### `target`

The expected project metadata is:

```json
{
  "model": "Watch4,2",
  "board": "N131bAP",
  "soc": "T8006",
  "firmware": "watchOS 10.6.1",
  "build": "21U580",
  "architecture": "aarch64",
  "identity_proven": false
}
```

Metadata matching and identity proof are separate results. Matching strings
are not proof of capture identity. A synthetic bundle must leave
`identity_proven` false.

For a non-synthetic target-specific result, the manifest carries
`provenance_envelope`, with independent facts for metadata match, identity,
artifact presence, local hash verification, target binding, and runtime proof.
The legacy `target_provenance` summary may remain for compatibility, but is
checked against the envelope when supplied and is not sufficient by itself.

```json
{
  "coverage_proven": true,
  "covered_artifacts": ["image", "handoff_descriptor", "mmu_snapshot"]
}
```

This summary is not cryptographic authenticity and cannot replace per-artifact
provenance. A bundle whose `source.kind` is `synthetic` remains `DESIGN` and
cannot be promoted to hardware `READY` by changing status strings.

### Artifact references

Each artifact contains a relative `path` and lowercase or uppercase
hexadecimal `sha256`. The image additionally has `expected_arch` and
`expected_entry`. Optional bounded byte artifacts (`boot_args` and
`device_tree`) may add `length` and `complete`. `complete: true` means the
local file length must equal the declared object length; a partial object is
never silently extended.

### `handoff_descriptor`

The binary is the stable Loader Handoff ABI V1 prefix, exactly 128 bytes for
validation. The verifier checks the V1 magic, version, size, flags, reserved
fields, entry EL, MMU value, payload interval, mapping-flag dependencies, and
bounded boot_args/DeviceTree ranges. `prefix_readable_proven` and
`copied_to_trusted_storage_proven` are explicit, separate claims. The V1
`VERIFIED` flag is an assertion only and is never a root of trust.

### `cpu_state`

Register facts may include `current_el`, `sp`, `daif`, `sctlr_el1`,
`tcr_el1`, `ttbr0_el1`, `ttbr1_el1`, `mair_el1`, `vbar_el1`, `cpacr_el1`, and
`pc`. `translation_policy` and `cache_policy` contain explicit normalized
proof fields. The verifier compares independently proven register values with
the MMU manifest and reports a conflict instead of selecting one silently.

### `runtime_memory`

`dram_phys_base` and `dram_size` are independent facts. They authorize a
payload physical containment check only when both are proven and
`provenance` is exactly `RUNTIME_VERIFIED`. Static ADT `/memory = 0,0`, a
historical 1 GiB fixture, or a non-zero address does not satisfy this rule.

### `ranges`

The verifier understands `payload_physical`, `payload_virtual`,
`stage0_executable`, `loader_code`, `loader_stack`, `loader_heap`,
`descriptor_source`, `descriptor_copy`, `boot_args`, `device_tree`,
`framebuffer`, and `kernel_stack`. `protected_ranges` and `reserved_ranges`
extend the collision set. `protected_ranges_complete` and its
`*_proven` companion are required before `collision_audit` can be proven.
The framebuffer has a separate `framebuffer_reservation_known` proof; no
address is inferred from the static zero-filled `/vram` node.

### Optional object and transfer fields

If `ranges.boot_args_required` or `ranges.device_tree_required` is true, the
corresponding range must match the V1 descriptor range. Local copies are
parsed with bounded host logic only. `boot_args` uses the known XNU ARM64
layout as an object-consistency check; that layout is not the DreyzeOS loader
ABI. The nested DeviceTree pointer/length must fit the independently declared
range.

`control_transfer.entry_pc` is a fact and `control_transfer.proven` is an
explicit claim. Mapping evidence cannot synthesize a branch or control-flow
proof. `persistence.persistent_write_required` must be a proven boolean
false for the corresponding readiness node.

## Verifier result

The verifier emits an evidence graph. Each node contains `status`,
`proof_state`, `reason`, `evidence_sources`, and `depends_on`. A final
`blocking_requirements` array contains the exact node names and reasons that
prevent an offline contract result from being READY. A synthetic offline
READY result still has `hardware_evidence_status = DESIGN`,
`LOADER CONTRACT = BLOCKED`, and `FIRST HARDWARE EXECUTION = NOT_READY`.

Envelope-only preflight uses the same verifier implementation:

```sh
python3 tools/handoff_evidence_verifier.py \
  --provenance-envelope path/to/provenance_envelope.json --json
```

This mode cannot close EV-027; the full `--bundle` mode owns the complete
critical artifact graph.

A target-specific result cannot be READY unless every critical dependency is
PROVEN, the source status is `CONFIRMED`, and target identity is separately
proven. This is a fail-closed policy, not a claim that the data is genuine.

## Safety boundary

This schema is intentionally evidence-only. It has no fields that authorize
MMIO, UART, AIC, framebuffer, page-table, flash, USB, DFU, exploit, payload,
or control-flow operations. A translation result is a mapping fact; it is not
access authority or ownership.

# Target provenance envelope (host-only preparation)

Schema: `dreyzeos.target_provenance_envelope.v1`.

This is a provenance sub-schema for the existing
`dreyzeos.handoff_evidence.v1` bundle, not a new loader ABI and not a capture
tool. It supports host-side preparation and validation only. No Watch or iPhone
is queried, no pointer is dereferenced, and no device state is changed.

The envelope is the first artifact in the dependency order for **EV-000** and
contributes to **EV-027**. An envelope can be structurally complete while both
requirements remain unproven. The standalone CLI validates only the envelope;
the ordinary bundle mode remains the authority for ELF, ABI V1, MMU, object,
range, and complete readiness checks.

## Evidence facts are independent

Fact wrappers use strict JSON booleans:

```json
{"value":"Watch4,2","value_present":true,"value_proven":false,"source":"user_observed_record"}
```

The schema keeps these separate:

* `metadata_match`: whether declared metadata agrees with the project target;
* `identity_proven`: an explicit external identity-attestation claim;
* `artifact_present`: whether the relative local file exists;
* `artifact_hash_verified`: whether its bytes match the declared SHA-256;
* `artifact_target_bound`: whether an independently supported provenance
  relationship binds that artifact to the named target/session;
* `artifact_runtime_proven`: whether the artifact's relevant contents are
  proven to describe runtime state.

The verifier computes local presence and hash equality. It does not infer
target binding or runtime proof from either result. Target metadata strings,
the user-observed metadata record, filenames, non-zero addresses, and the V1
`VERIFIED` flag cannot set `identity_proven=true`. A true identity claim also
requires a separately declared, present, hashed
`TARGET_IDENTITY_ATTESTATION` artifact plus explicit authority and method
fields. This is structural validation of an external claim, not cryptographic
authentication of the attestor or capture.

SHA-256 means only that local bytes match the bundle declaration. It does not
prove the bytes originated from an Apple Watch. Keep real device identifiers,
pairing material, certificates, private keys, and unsanitized capture data out
of Git.

## Envelope fields

The top-level object contains:

* `source`: kind and project evidence status (`CONFIRMED`, `LIKELY`, `DESIGN`,
  `UNKNOWN`, or `BLOCKED`);
* `capture`: a canonical UUID session ID and start/end RFC3339 UTC facts;
* `target`: expected project metadata, independently sourced metadata facts,
  metadata comparison, identity proof, optional identity-attestation reference,
  and additional source assertions used for conflict detection;
* `producer`: name, version, and host/tool environment facts;
* `source_interface`: description, interface, and a safety-classification fact;
* `coverage`: required, declared, and covered artifact IDs plus an explicit
  completeness fact;
* `artifacts`: typed, relative-path records with SHA-256, the six independent
  presence/hash/binding/runtime facts, and a relationship to the capture ID;
* `conflict_detection`: declared conflict notes and the fields that the
  validator compares. The validator independently detects contradictory
  proven target assertions, duplicate artifact IDs/paths, metadata mismatch,
  bundle-reference disagreement, and inconsistent coverage.

Supported artifact types include the DreyzeOS ELF, fixed 128-byte Loader
Handoff ABI V1 descriptor, MMU manifest, CPU-state record, runtime
memory/reservation record, boot_args copy, DeviceTree copy, control-transfer
record, target identity attestation, and `OTHER`. Only image, descriptor, and
MMU snapshot are the minimum EV-000 coverage set. The remaining types are
optional declarations until their evidence is actually available.

Missing artifacts use `path: null`, no digest, and `value_present: false`; do
not fill absent values with guesses. Partial coverage stays partial. A proven
fact conflict yields `BLOCKED` and is not resolved by choosing a preferred
source. The envelope validator checks UUID syntax, but global uniqueness across
separate sessions remains the producer's responsibility.

## Readiness mapping

EV-000 can be reported proven only when the source is `CONFIRMED`, target
metadata facts and their comparison are proven and matching, the identity
attestation is structurally present and hashed, the capture ID/timestamps and
producer/interface are present and proven, required artifacts exist and hash
correctly, coverage is complete, and each required artifact is separately
target-bound. No one of these facts implies another.

The standalone envelope cannot close EV-027. The complete handoff verifier
must still validate the full critical artifact graph, all hashes, CPU/MMU
consistency, ranges, collision completeness, and conflicts.

The sanitized template is `research/handoff_evidence/provenance_envelope.template.json`.
The `research/handoff_evidence/fixtures/provenance/` directory contains one
synthetic structurally complete envelope and blocked mutations for absent
target binding, missing/mismatched SHA-256, incomplete coverage, metadata
mismatch, and conflicting proven target facts. The marker files referenced by
the synthetic fixture are not device captures or valid ELF/descriptor/MMU
artifacts.

An envelope with `source.kind = "synthetic"` or `evidence_status = "DESIGN"`
can validate its structure and local fixture hashes, but can never prove a
target identity or runtime capture. The repository's “synthetic complete”
fixture contains small marker files solely to test envelope handling; they are
not ELF, descriptor, or MMU data.

## CLI

Validate only an envelope:

```sh
python3 tools/handoff_evidence_verifier.py \
  --provenance-envelope path/to/provenance_envelope.json --json
python3 tools/handoff_evidence_verifier.py \
  --provenance-envelope path/to/provenance_envelope.json --human
```

This mode returns zero when validation completes, even if EV-000 is blocked;
`--strict` returns nonzero unless EV-000 is proven. It always reports that
hardware readiness is unaffected. For a complete evidence bundle, use the
existing `--bundle` mode and then `tools/t8006_evidence_gap.py`.

Current project metadata remains `USER_OBSERVED / METADATA_CONFIRMED` as
recorded in `research/t8006_evidence/user_observed_target_metadata.json`.
It is not runtime target identity. A sanitized extraction of a user-reported,
pre-existing NanoPhotos watchOS diagnostic report is now recorded in
`research/t8006_evidence/observed_watchos_report.json` and referenced by
`research/t8006_evidence/watchos_report_provenance_envelope.json`. The report
bytes identify Watch4,2 / Watch OS 10.6.1 / 21U580 / ARM64_32 and contain
AppleT8006-related stackshot symbols. The raw IPS and its private correlation
values are not in Git. Its recorded SHA-256 verifies local byte equality only;
the export origin is user-reported and not independently attested.

The envelope hashes only the sanitized derivative and deliberately leaves
`artifact_target_bound`, `artifact_runtime_proven`, and
`identity_proven` false/unproven. The report does not establish current pairing,
physical serial identity, future-capture identity, CPU/MMU/RAM state, payload
ownership, or control transfer. No CPU-register, page-table, runtime-memory,
mapping, or loader evidence is added by this report.

```text
EV-000 = BLOCKED
EV-027 = BLOCKED
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

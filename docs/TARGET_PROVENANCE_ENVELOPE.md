# Target provenance envelope (host-only preparation)

Current schema: `dreyzeos.target_provenance_envelope.v2`.
The validator also accepts v1 envelopes with explicitly legacy semantics.

The version bump is necessary because v1's single `identity_proven` field and
aggregate EV-000 could not distinguish metadata consistency, same-session
artifact provenance, and persistent physical identity. Requirements use
`dreyzeos.t8006_evidence_requirements.v2` for the same split. The outer
`dreyzeos.handoff_evidence.v1` bundle and Loader Handoff ABI V1 are unchanged.

This is a provenance sub-schema for the existing
`dreyzeos.handoff_evidence.v1` bundle, not a new loader ABI and not a capture
tool. It supports host-side preparation and validation only. No Watch or iPhone
is queried, no pointer is dereferenced, and no device state is changed.

The envelope is the first artifact in the dependency order for **EV-000A** and
**EV-000B**, and contributes to **EV-027**. **EV-000C** is reported separately
and is not a first-bring-up gate. An envelope can be structurally complete
while target/session provenance is still only DESIGN. The standalone CLI validates only the envelope;
the ordinary bundle mode remains the authority for ELF, ABI V1, MMU, object,
range, and complete readiness checks.

## Evidence facts are independent

Fact wrappers use strict JSON booleans:

```json
{"value":"Watch4,2","value_present":true,"value_proven":false,"source":"user_observed_record"}
```

The schema keeps these separate:

* `metadata_match`: whether declared metadata agrees with the project target;
* `physical_identity`: an optional v2 fact about persistent device identity;
* `same_session_provenance`: computed from capture fields and per-artifact
  relationships; no user-set boolean can create this result;
* `artifact_present`: whether the relative local file exists;
* `artifact_hash_verified`: whether its bytes match the declared SHA-256;
* `artifact_session_bound`: computed from local presence/hash and a proven
  relationship to the same `capture_id`;
* `artifact_target_bound`: computed only when target metadata and session
  provenance are both proven for a non-synthetic confirmed source;
* `artifact_runtime_proven`: whether the artifact's relevant contents are
  proven to describe runtime state.

The verifier computes local presence and hash equality. It does not infer
session binding or runtime proof from either result. Metadata strings,
user-observed records, filenames, non-zero addresses, and the V1 `VERIFIED`
flag cannot prove physical identity. In v2, a true `physical_identity` claim
requires a present, hashed `TARGET_IDENTITY_ATTESTATION`, authority, method,
and `identity_scope = PERSISTENT_PHYSICAL_DEVICE`; even then the host tool only
checks structure and hashes, not the attestor's authenticity. Synthetic
attestations can never prove physical identity.

## EV-000 split

* **EV-000A — target metadata consistency:** all currently required target
  metadata facts and their comparison must match the fixed project target.
  Board and architecture values are not inferred from model strings or
  watchOS process `cpuType`; if applicable values are unavailable, A stays
  partial. A mismatch between proven facts is BLOCKED.
* **EV-000B — same-session artifact provenance:** the capture ID, bounded UTC
  interval, producer/interface provenance, required artifact hashes/coverage,
  and each artifact's proven relationship must identify the same capture
  session. It does not require serial/UDID identity.
* **EV-000C — physical identity/cross-session continuity:** optional for
  technical first bring-up; required only for claims that independent sessions
  or reports belong to the same persistent physical Watch. It is NOT_PROVEN in
  the current evidence. A CrashReporter Key match may support pseudonymous
  correlation but is not serial-level identity or authenticity.

EV-000 is the aggregate technical provenance gate: **A + B**, not C. This
does not weaken any runtime CPU, MMU, RAM, ownership, mapping, collision,
descriptor-trust, boot-metadata, transfer, or no-persistent-write requirement.
Machine results expose `TARGET_METADATA_STATUS`,
`SAME_SESSION_PROVENANCE_STATUS`, `PHYSICAL_IDENTITY_STATUS`, and
`TECHNICAL_TARGET_PROVENANCE_READY` separately.

V1 compatibility is conservative and explicit. V1 `target.identity_proven` is
reported only as a legacy claim and is never silently migrated into EV-000C.
The validator may derive B from v1's own proven capture ID and per-artifact
session relationships, but physical identity remains NOT_PROVEN. The bundle
schema and Loader Handoff ABI V1 are unchanged; only the nested provenance and
requirements schemas are versioned forward.

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
  metadata comparison, optional physical-identity fact/attestation, and
  additional source assertions used for conflict detection;
* `producer`: name, version, and host/tool environment facts;
* `source_interface`: description, interface, and a safety-classification fact;
* `coverage`: required, declared, and covered artifact IDs plus an explicit
  completeness fact;
* `artifacts`: typed, relative-path records with SHA-256, presence/hash/binding/
  runtime facts, and a relationship to the capture ID;
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

EV-000A can be reported proven only when all required metadata facts and their
comparison are proven and matching, with no conflicting proven metadata. The
envelope-wide `source.evidence_status` is not an EV-000A prerequisite: source
attribution for a capture belongs to EV-000B and aggregate EV-000 readiness.
Thus an UNKNOWN source status must remain UNKNOWN for session provenance but
must not demote independently proven target-profile metadata. Synthetic/design
metadata remains DESIGN. EV-000B additionally requires a confirmed source,
capture ID/timestamps, producer/interface provenance, complete coverage,
verified required artifact bytes, and a proven per-artifact relationship to
that same capture ID. EV-000C requires its own scoped persistent-identity
attestation. C is not a dependency of A, B, or technical EV-000 readiness.
No one of these facts implies another.

The standalone envelope cannot close EV-027. The complete handoff verifier
must still validate the full critical artifact graph, all hashes, CPU/MMU
consistency, ranges, collision completeness, and conflicts.

The sanitized v2 template is `research/handoff_evidence/provenance_envelope.template.json`.
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
`physical_identity` false/unproven. The report does not establish current pairing,
physical serial identity, future-capture identity, CPU/MMU/RAM state, payload
ownership, or control transfer. No CPU-register, page-table, runtime-memory,
mapping, or loader evidence is added by this report.

```text
EV-000 = BLOCKED
EV-027 = BLOCKED
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

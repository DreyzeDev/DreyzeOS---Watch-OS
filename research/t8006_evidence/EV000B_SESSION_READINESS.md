# EV-000B same-session provenance readiness audit

Audit baseline: `6ecf29d53e51dbfd3e5a7041ab80dc58341a0cb9` (`master`).
Scope: repository and local host artifacts only. No Watch/iPhone interaction,
capture, payload, loader, or device-state change was performed.

## Result

The existing `dreyzeos.target_provenance_envelope.v2` and offline verifier are
sufficient to represent and validate EV-000B. No new schema, template, or
capture utility is needed. The existing
`research/handoff_evidence/provenance_envelope.template.json` is the host-side
starting point; copy it to a private session directory when a separately
reviewed capture is authorized. Do not edit the repository template into a
claim about a real session.

Current states:

```text
EV-000A = CONFIRMED
EV-000B = BLOCKED in the requirements inventory
EV-000C = UNKNOWN / non-critical
EV-000 = BLOCKED
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

The standalone provenance validator reports EV-000B as `UNKNOWN` with
`proof_state = NOT_PROVEN` for the present envelope because required facts are
absent, not contradictory. The requirements inventory and aggregate technical
gate classify this unresolved critical requirement as `BLOCKED`. A detected
conflict would instead produce an explicit EV-000B `BLOCKED` result.

## EV-000B closure dependencies

The closure conditions are defined in
`research/t8006_evidence/requirements.json` and enforced by
`tools/provenance_envelope.py`. A valid-looking declaration is not itself
attestation: for a non-synthetic session, source provenance must be reviewed
and `source.evidence_status` must be `CONFIRMED` on the basis of that evidence.
The validator checks structure, consistency, local paths, and hashes; it does
not authenticate a producer or acquisition method.

| Dependency | Required representation | Offline work possible now | What remains unproven |
|---|---|---|---|
| Session identity | Canonical UUID `capture.capture_id`, present and proven | A UUID can be generated and syntax-checked locally | That it names an actual target-bound capture session |
| Bounded time | Proven `started_at_utc` and `ended_at_utc`, RFC3339 UTC, ordered | UTC formatting/order validation | That the bounds describe the real capture interval and its source |
| Producer | Proven producer name, version, and host facts | Tool/host version can be recorded locally | That this producer generated the target evidence in this session |
| Source/interface | Proven description, interface, and interaction-class facts; source status `CONFIRMED` | Schema validation and safety classification | Actual source/interface use and target relationship; no approved acquisition path is established |
| Required artifacts | `image`, `handoff_descriptor`, `mmu_snapshot` declared and covered | A selected local ELF can be built, frozen, and hashed; verifier can hash local bytes | Real descriptor and MMU snapshot are absent; no artifact is yet proven to belong to a target session |
| Artifact integrity | Each present file has a relative path and SHA-256 matching local bytes | Recompute/check local SHA-256 | Hash equality does not prove origin, target, or session membership |
| Coverage | `required_artifact_ids`, `declared_artifact_ids`, `covered_artifact_ids` agree; `coverage_complete` is explicitly present and proven true | Lists and declaration consistency are validated | Complete real evidence set does not exist |
| Same-session relationship | Every required and every covered artifact has the same `capture_id` and a proven relationship | Relationship fields and conflicts can be validated | No actual capture session or runtime artifacts are available to support the relationships |
| Conflict handling | No conflicting proven session/source declarations | The existing validator detects the supported conflicts | Any future conflict must be resolved from evidence, never by preferring a convenient source |

The minimum EV-000B coverage is exactly `image`, `handoff_descriptor`, and
`mmu_snapshot`. Any additional artifact consumed together in a handoff
analysis must also be declared, covered, hashed, and related to the same
session. Optional CPU-state, runtime-memory, boot_args, DeviceTree, reservation,
and transfer records may be absent from the envelope only while they are not
claimed as covered evidence; their absence still blocks their corresponding
technical requirements elsewhere in the readiness graph.

## Existing local evidence audit

The current sanitized report envelope is
`research/t8006_evidence/watchos_report_provenance_envelope.json`.
Validation with the existing tool confirms:

* target metadata is `CONFIRMED` (EV-000A); the report's export/source
  attribution remains `UNKNOWN`;
* no proven `capture_id` or bounded session timestamps are supplied;
* producer facts are absent; source/interface descriptions are present but
  unproven, with interaction class `UNKNOWN`;
* only `watchos_report_record` is listed as covered; this is a sanitized
  derivative, not one of the three required EV-000 artifacts;
* `image`, `handoff_descriptor`, and `mmu_snapshot` are not present in that
  envelope's coverage and have no proven same-session relationship;
* the envelope explicitly describes coverage as incomplete. Its local hash
  verification for the sanitized report does not bind that report to a future
  DreyzeOS capture.

At audit time a local `build/DreyzeOS.elf` existed and had a computable
SHA-256. That build output is not recorded as an artifact in a capture
envelope, and its local presence/hash does not establish that those exact
bytes were selected for, or used in, any target session. Rebuilds can change
the bytes; freeze the chosen ELF and record its actual digest before using it
as the session's `image` artifact.

No real target descriptor or MMU snapshot is present in the repository's
evidence set. Repository-owned marker fixtures under
`research/handoff_evidence/fixtures/provenance/` are synthetic `DESIGN` data;
they validate verifier behavior only and must not be relabeled as captured
artifacts. The pre-existing NanoPhotos report may support report-content
metadata but does not satisfy EV-000B's required artifact set or same-session
relationships.

| Required artifact | Local presence at audit | Hash state | Target/session binding | Existing validation | Exact gap |
|---|---|---|---|---|---|
| `image` | `build/DreyzeOS.elf` was present after the host build; the real-report envelope does not reference it | Locally hashable, but no declared envelope digest is currently being checked for it | Neither target-bound nor linked to a capture ID | Envelope mode can check the declared relative path/digest and relation; bundle mode additionally validates the ELF and bundle reference | Freeze the exact ELF intended for a future session, declare its path/digest, and later prove that exact image's session relationship |
| `handoff_descriptor` | No real session descriptor found; marker fixture only is synthetic | No real artifact digest | Not bound | Envelope mode can check existence/hash/relation; bundle mode validates the V1 structure and trust evidence | Obtain a real artifact from a separately reviewed target-bound session, then bind it to that session; presence alone will not prove descriptor readability/trust |
| `mmu_snapshot` | No real target snapshot/table-byte artifact found; synthetic test data is not target evidence | No real artifact digest | Not bound | Envelope mode can check the manifest's existence/hash/relation; bundle mode invokes the existing MMU analyzer and checks required references | Obtain a complete target snapshot and every table-page byte required by analysis, then bind the manifest and its referenced blobs to that same session |

## Image hash versus session membership

The DreyzeOS ELF is a host-built input and can be prepared before any future
session: build it, select the exact output, compute SHA-256, and retain those
bytes unchanged in the private bundle. The hash proves only local byte
equality. Before the session exists, the verifier cannot prove that this image
was the one selected or consumed during that session. That requires a proven
per-artifact relationship to its `capture_id`; any rebuild or substitution
requires a new digest and a truthful session record.

The same distinction applies to all files: **present and hash-verified** is
not the same as **target-bound**, **runtime-proven**, or **same-session-bound**.
The envelope validator computes local file presence and hash equality and
checks declared facts against those results. It does not infer source
authenticity from a hash, a filename, a model string, or a descriptor's
`VERIFIED` flag.

## Future evidence dataflow (not an acquisition procedure)

This is a record-order/data-dependency description only; it gives no device
interaction instructions and authorizes no acquisition.

1. Prepare a private copy of the existing v2 template and the selected,
   hashed ELF. Leave every unobserved runtime fact absent or unproven.
2. If a separately reviewed and specifically approved session ever occurs,
   bind its canonical ID, UTC bounds, producer, and actual source/interface to
   evidence from that session. A planned UUID or locally written timestamp is
   not proof that a target capture occurred.
3. Record the exact ELF bytes used, then add the real V1 descriptor and MMU
   manifest/table-byte artifacts only if they are actually obtained in that
   same session. Record each relative path, SHA-256, artifact ID/type, and
   evidence-backed relationship to that one capture ID.
4. Declare the exact covered set, prove its completeness, and validate the
   standalone envelope. For the full technical analysis, validate the
   `dreyzeos.handoff_evidence.v1` bundle and pass its report to the evidence
   gap tool. Conflicts, missing bytes, or partial coverage remain blockers.

The first transition that cannot be completed host-only is establishing a
proven relationship between a real target session/source and its first
target-runtime artifact. The first concrete required runtime artifact in the
current schema is `handoff_descriptor`; the required `mmu_snapshot` and its
table bytes must also be acquired and bound before EV-000B closes. A host can
prepare the manifest fields and hash an ELF now, but it cannot fabricate those
runtime facts. No approved read-only acquisition path or live capture is part
of this audit.

## Existing validation commands

Reuse the v2 template and existing tools. The placeholder template is
expected to report UNKNOWN/BLOCKED; that is a successful validation of an
incomplete template, not a failed capture.

```bash
# Validate an envelope only; resolves artifact paths relative to the JSON file.
python3 tools/handoff_evidence_verifier.py \
  --provenance-envelope /private/session/provenance_envelope.json --json

# Validate the complete bundle after its local artifacts are assembled.
python3 tools/handoff_evidence_verifier.py \
  --bundle /private/session/bundle.json --json \
  > /private/session/verification.json

# Map the full verification report to EV requirements.
python3 tools/t8006_evidence_gap.py \
  --verification /private/session/verification.json \
  --requirements research/t8006_evidence/requirements.json --json \
  > /private/session/evidence_gap.json
```

The standalone command validates EV-000A/B/C envelope semantics and local
artifact integrity. The bundle command additionally checks ELF, descriptor,
CPU/MMU consistency, mappings, ranges, and the complete technical graph. The
gap command reports which EV requirements remain unresolved. These are local
file operations only. `--strict` changes the exit status for blocked readiness;
without it, a structurally processed but blocked result is a completed
verification, not a tool failure.

## Gate

```text
HOST-ONLY ENVELOPE PREPARATION = READY
REAL EV-000B SESSION EVIDENCE = NOT PRESENT
EV-000B = BLOCKED
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

Any future live acquisition requires its own reviewed method and explicit
user approval. This audit performed none.

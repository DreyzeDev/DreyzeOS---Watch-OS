# EV-000 feasibility audit: identity scope vs. bring-up safety

Audit baseline: this document first recorded the pre-split verifier behavior.
The implementation outcome is updated at the end; v2 is now authoritative.

Phase 4 host-only audit. No Watch/iPhone interaction, capture, installation,
payload, loader, or device-state change was performed.

## Decision

**EV-000 is over-scoped for first-bring-up evaluation if its `identity_proven`
condition is interpreted as persistent physical-identity attestation.** Target
provenance is not optional: the evidence must identify the relevant target
configuration and bind critical CPU/MMU/memory artifacts to one coherent,
independently described acquisition session. A serial, UDID, or equivalent
proof that this is the same real-world Watch across separate sessions is not a
technical prerequisite.

There is also a specification ambiguity: the envelope defines
`identity_proven` as an external identity-attestation claim binding an artifact
set to the target, but does not say that it must identify a persistent unique
unit. The validator checks the attestation artifact's declared type, local
presence/hash, authority/method strings, and claim consistency; it does not
validate an issuer signature or establish physical identity. Thus the current
gate conflates distinct claims and does not itself prove the strongest
physical-identity interpretation.

This is a scope finding, not a readiness promotion. The current evidence does
not satisfy the full target-metadata or same-session requirements, and the
current schema/verifier requires an external target-attestation claim whose
meaning is not precise enough to distinguish B from C. No schema or code was
changed by this audit. The loader remains blocked for many independent
technical reasons.

## Three distinct claims

| Claim | Meaning | Current evidence |
|---|---|---|
| **A. TARGET_METADATA_MATCH** | The observed target configuration agrees with the project target: Watch4,2, N131bAP, T8006, watchOS 10.6.1, build 21U580. This is about model/platform/software, not a unique unit. | **Partial.** The IPS content confirms Watch4,2, Watch OS 10.6.1 / 21U580, ARM64_32, and T8006-related symbols at its report time. The board/SoC mapping is not independently established by that IPS. User-observed metadata is recorded separately. The current bundle does not have a proven complete `metadata_match`. |
| **B. SAME_DEVICE_CORRELATION / SAME_SESSION_PROVENANCE** | Evidence items are linked either to one pseudonymous CrashReporter identity epoch or, more importantly for live state, to one well-defined acquisition session on the selected target. These are related but not identical claims. | **Not proven.** Only one Watch IPS is available, so its private CrashReporter Key cannot be compared to another report. No CPU/MMU/runtime-memory capture is present, and no acquisition session binds such artifacts together. |
| **C. PHYSICAL_IDENTITY_ATTESTATION** | An authoritative source links the evidence to one persistent real-world hardware identity, such as a serial/UDID-backed attestation. | **Not proven.** No independent identity bridge from the IPS to a unique physical Watch exists in the inspected evidence. The existing schema does not explicitly require a serial/UDID, so its `identity_proven` flag must not be read as proof of C without additional evidence. |

The single IPS proves report contents, not the authenticity of the report's
origin. Its hash proves local byte equality only. A CrashReporter Key present
in one file cannot demonstrate equality with another source, identify a
serial, or bind future runtime artifacts to that source. See
[`TARGET_IDENTITY_CORRELATION_REVIEW.md`](TARGET_IDENTITY_CORRELATION_REVIEW.md)
and [`observed_watchos_report.json`](observed_watchos_report.json).

## What each claim is needed for

| Activity / claim | A: metadata match | B: same session/device correlation | C: persistent physical identity |
|---|---|---|---|
| Parse an IPS or offline snapshot and describe its contents | Not required to parse; needed to classify content as relevant to this project target. | Not required to parse one artifact. | Not required. |
| Validate CPU/MMU/RAM consistency | Needed to know which target configuration the evidence is intended to describe. | **Needed:** CPU state, translation snapshot, runtime map, and other live facts must be coherent and bound to the same capture session. | Not a technical dependency if A and B are proven for the selected target/session. |
| Validate payload placement | Needed for target-specific interpretation. | **Needed:** runtime RAM, mappings, reservations, ownership, and collision inputs must describe the same state/session. | Not a technical dependency; physical identity does not prove RAM bounds or ownership. |
| Validate the loader contract | Needed, plus every concrete entry, stack, mapping, cache, descriptor, and transfer condition. | **Needed:** mutually consistent evidence and per-artifact provenance are required. | Not a technical dependency. |
| Evaluate a first non-persistent research execution | Needed, along with explicit confirmation that the selected device is the intended target. | **Needed:** all runtime facts used to justify the operation must be tied to the same target/session. | Not a memory-safety or loader-correctness dependency. It may be needed for a separate claim that this is the same physical unit across time. |
| Claim “this is the user's particular physical Watch” or continuity across sessions | Insufficient by itself. | Same-session provenance alone is insufficient for persistent cross-session identity. | **Needed**, or an equivalent authoritative identity bridge. |

Here “not technically required” does **not** mean that a device can be selected
or acted upon without user authorization. At any later live operation, the user
must explicitly authorize that specific operation and confirm the intended
physical target. That operational authorization is distinct from storing a
serial/UDID attestation in the evidence bundle. A physical identifier would
also not mitigate volatile RAM corruption, an unexpected reset, incorrect
MMU assumptions, or an unsafe control transfer.

## Review of every current EV-000 closure condition

“Needed only for strong provenance” means the condition does not itself
establish technical memory/CPU safety, though it may be important for the
strength and auditability of the evidence claim.

| CONDITION (current requirement wording) | NEEDED FOR TECHNICAL CORRECTNESS | NEEDED FOR SAFETY | NEEDED ONLY FOR STRONG PROVENANCE | CURRENTLY SATISFIABLE | WHY |
|---|---|---|---|---|---|
| Target metadata values match the fixed target and their sources are proven | YES | YES | NO | NO | Target/model/build mismatch invalidates target-specific interpretation. The IPS supplies only some fields; it does not independently establish the full board/SoC mapping or bind itself to the selected physical unit. |
| `metadata_match` is explicitly proven and true | YES, as an auditable result of the preceding condition | YES, to prevent using an unchecked target assertion | NO | NO | This is a required machine-readable conclusion, not independent evidence. Current target metadata in the bundle is not fully proven. |
| `identity_proven` is explicitly true and references a hashed external identity-attestation artifact with authority and method | NO, if A and B plus the required runtime facts are proven | NO, for memory/loader safety; there is no serial-dependent safety check in the contract | YES only if this is intended to mean C; otherwise it overlaps A/B | NO | The requirement names an external identity attestation but does not define whether it proves a session-to-target binding (B) or persistent unit identity (C). The validator checks structure, hash, and declared authority/method; it does not validate the attester or physical identity. A single present-day IPS cannot supply either missing cross-artifact binding or a physical identity bridge. |
| Capture ID and UTC start/end timestamps are present and proven | YES for establishing the scope and temporal coherence of a multi-artifact capture | YES where mutable CPU/MMU/memory state could otherwise be mixed across times | NO | NO | The report timestamp is present, but it is not a capture-session interval for a future CPU/MMU/runtime-memory evidence set. |
| Producer and source/interface provenance are present and proven | YES | YES | NO | NO | The acquisition method determines what values mean and whether the resulting artifact is observational or changes state. IPS export history is user-reported and does not define a future runtime capture producer/interface. |
| Image, handoff descriptor, and MMU snapshot are present and their local SHA-256 values verify | YES for the current EV-000’s chosen coverage and downstream bundle comparison | YES for the later descriptor/mapping analysis, but hashes alone are not proof of device origin | NO | NO | These artifacts are not present in the current report envelope. Their hashes would establish local integrity only. Runtime memory/register requirements remain separate. |
| Required-artifact coverage is explicitly complete | YES for the completeness claim made by this EV-000 bundle | YES if “complete” means every artifact needed for the safety decision is included; completeness must not be inferred from a fixed list that omits safety inputs | NO | NO | Current coverage contains only a sanitized report. The present EV-000 list also overlaps the broader bundle-completeness purpose of EV-027. |
| Each required artifact has a separately proven target/session provenance relationship and target binding | YES | YES | NO | NO | This is the essential B requirement, distinct from C. No current runtime artifact set or acquisition record exists to establish it. |
| No conflicting proven target facts or artifact declarations exist | YES | YES | NO | NO, not for the eventual complete bundle | No conflict is reported among the small current records, but an incomplete set cannot establish conflict-free consistency for artifacts not yet supplied. The verifier correctly blocks proven-value conflicts. |
| SHA-256 equality is treated only as local byte integrity, not device authenticity | YES, as an evidence interpretation rule | YES | NO | YES | This rule is already stated in the envelope/verifier. The sanitized report records the raw-file hash without promoting it to source authentication. |

### Which conditions are genuinely necessary for bring-up?

Conditions 1–2 (A), 4–5, and 8 (B) have direct correctness/safety roles when
they are applied to the evidence actually used for a bring-up. Conditions 6–7
are useful only when their artifact set accurately represents the complete
inputs needed for the decision; the full CPU/MMU/RAM/ownership/collision graph
is not made safe just by the current three-file minimum. Condition 9 is
necessary for consistency. Condition 10 is an essential interpretation rule.

Condition 3 is ambiguous rather than a well-defined proof of C. If interpreted
as C, it supports stronger attribution and continuity claims, but no concrete
dependency in the loader contract requires a serial/UDID or persistent
physical identity. A unique physical identifier does not establish that a
descriptor is readable, a page is writable, RAM is safe, a payload is owned,
or a transfer is non-persistent. If it is intended to prove B instead, the
schema should name and validate that session-binding claim directly rather
than call it physical identity.

## Is EV-000 one requirement or three?

The current EV-000 combines at least three independently meaningful assertions
and also includes artifact-set completeness that overlaps EV-027. It should be
split conceptually as follows:

| Proposed requirement | Meaning | Gate use |
|---|---|---|
| **EV-000A — target metadata consistency** | Proven target model/board/SoC/OS/build metadata for the evidence being interpreted; strings from unrelated sources do not count as a binding. | Required for target-specific runtime interpretation and any bring-up evaluation. |
| **EV-000B — same-session evidence provenance** | Independently described capture/session, times, producer/interface, and per-artifact links showing that CPU/MMU/memory/descriptor evidence belongs to the same selected target session. Conflicts block. This does not require a persistent serial identity if the acquisition method binds the session adequately. | Required for runtime consistency and safety evaluation. |
| **EV-000C — physical identity attestation** | Authoritative binding to a persistent unique physical Watch, suitable for “same physical unit” or cross-session claims. | Required only when making that stronger claim or when a separately reviewed procedure depends on continuity across sessions. Not a generic first-bring-up gate. |

The full bundle-completeness requirement should remain explicit in EV-027 or a
dedicated completeness node, rather than being used to make A, B, and C
indistinguishable. This audit does not alter `requirements.json`, the envelope
schema, or verifier behavior. The current format/verifier requires a proven
external-attestation claim under the ambiguous name `identity_proven`; it does
not verify C itself. A separately reviewed host-only change should define the
meanings and gates explicitly before any status promotion.

## Can A + B support first bring-up evaluation while C stays unproven?

**Yes, as a technical evidence policy**, provided all of the following hold:

1. A is proven from authoritative target metadata for the selected target,
   rather than inferred solely from project documentation or user-entered
   strings.
2. B is proven by the acquisition method and binds every runtime artifact
   relied on to the same target/session; a capture ID or matching hashes alone
   are insufficient.
3. The complete independent hardware requirements are proven: EL1, stack and
   DAIF contract, normalized/known translation and cache policy, readable and
   executable mappings, writable safe RAM, runtime DRAM provenance, ownership,
   descriptor trust bootstrap, reservations, collision analysis, control
   transfer, and no persistent-write requirement.
4. Conflicts are absent, and a user explicitly approves the specific live
   operation after confirming the intended device.

There is no technical dependency in the loader contract that requires a
persistent physical identifier once A+B and all other safety requirements are
met. At this audit's original baseline, the verifier still coupled readiness to
the ambiguous `identity_proven` field. Step 2.16 below removes that coupling
without changing any runtime safety gate.

## Step 2.16 implementation outcome

- **EV-000A:** LIKELY / PARTIAL. The sanitized report contains proven report
  content for Watch4,2, watchOS 10.6.1, build 21U580, and T8006-consistent
  symbols. It does not provide N131bAP or DreyzeOS-relevant AArch64 target
  evidence, and the export origin remains user-reported.
- **EV-000B:** BLOCKED / NOT_PROVEN. No complete DreyzeOS capture session binds
  image, descriptor, MMU snapshot, and any other consumed artifacts together.
- **EV-000C:** NOT_PROVEN. The one private correlation field has no matching
  second report and is not serial-level identity.
- **EV-000:** remains BLOCKED because A and B are not both proven. C is not a
  first-bring-up dependency.
- **Schemas:** nested provenance is now
  `dreyzeos.target_provenance_envelope.v2`; requirements inventory is
  `dreyzeos.t8006_evidence_requirements.v2`. Handoff bundle v1 and Loader ABI
  V1 remain unchanged. V1 envelope inputs are accepted explicitly as legacy;
  their ambiguous `identity_proven` claim is never promoted to EV-000C.
- **Readiness:** technical target provenance requires A+B, and the complete
  pre-existing EV-001/CPU/MMU/RAM/mapping/ownership/collision/descriptor/boot
  metadata/transfer/no-persistent-write graph remains critical. Physical
  identity is reported but does not gate first bring-up.
- **Next minimal evidence:** complete target metadata for A, then one
  target-bound session artifact set for B. Runtime CPU/MMU/RAM and all other
  hardware blockers remain unchanged; no live acquisition is authorized here.

## Sources inspected

- `research/t8006_evidence/requirements.json` — EV-000 and dependent EVs.
- `docs/TARGET_PROVENANCE_ENVELOPE.md` and
  `docs/T8006_EVIDENCE_CAPTURE_SPEC.md` — current metadata/identity semantics.
- `docs/FIRST_RUNTIME_EVIDENCE_PLAN.md` — evidence dependency order.
- `research/t8006_evidence/TARGET_IDENTITY_CORRELATION_REVIEW.md` —
  CrashReporter Key semantics and limitations.
- `research/t8006_evidence/observed_watchos_report.json` and
  `watchos_report_provenance_envelope.json` — sanitized IPS facts and current
  provenance state.
- `research/t8006_evidence/NEXT_TARGET_BOUND_CAPTURE_REVIEW.md` and
  `docs/T8006_RUNTIME_EVIDENCE_METHODS.md` — acquisition-path status.
- `tools/handoff_evidence_verifier.py` — `verify_target`,
  `verify_provenance`, and the `hardware_ready` predicate.
- `tools/t8006_evidence_gap.py` — EV evaluation predicate requiring both
  metadata match and identity proof.

**No runtime hardware fact was promoted by this audit.** The single IPS remains
report-content evidence only; no target identity, runtime CPU/MMU/RAM, loader,
or control-transfer claim is added.


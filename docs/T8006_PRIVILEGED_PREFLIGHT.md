# T8006 Privileged Research Preflight

Phase 4 — Step 2.15.

This checklist is a non-operational review gate. It is not a command
sequence, capture procedure, DFU procedure, exploit guide, or authorization
to connect to an Apple Watch. It records what must be known before a future,
separately approved experiment can even be considered.

## Gate rule

If any required item is missing, the future proposal is **DO NOT PROCEED**.
The current result is:

```text
PREFLIGHT RESULT = BLOCKED
SPECIFIC EXPERIMENT = NONE SELECTED
LIVE EXECUTION AUTHORIZED = NO
```

## A. Exact target and provenance

- [ ] Device model independently recorded as `Watch4,2`.
- [ ] Board identifier independently recorded as `N131bAP` / `n131bap`.
- [ ] SoC recorded as `T8006`.
- [ ] watchOS version recorded as `10.6.1`.
- [ ] Build recorded as `21U580`.
- [ ] A target-bound identity record covers every artifact that the proposal
      will use.
- [ ] It is explicitly understood that matching strings are metadata, not
      proof that a capture came from this device.

Current status: **UNKNOWN/BLOCKED**. No live target evidence is present in the
accepted repository.

## B. Host, logging, and artifact controls

- [ ] Host OS and required analysis-tool versions recorded.
- [ ] Current DreyzeOS branch and full repository SHA recorded.
- [ ] A unique experiment/capture identifier is assigned.
- [ ] Timestamp, operator, source method, and artifact relationships are
      recorded.
- [ ] Raw artifacts are retained without in-place modification.
- [ ] SHA-256 hashes are recorded for each artifact and checked locally.
- [ ] The evidence bundle declares whether values are present and whether they
      are proven.
- [ ] Partial memory bytes are explicitly marked incomplete.
- [ ] No hash is represented as cryptographic proof of device provenance.

Current host baseline: `ff619bdb0770cf49cb1fd8d17979b1aac5856b44`.

## C. Device condition and state-change declaration

- [ ] Current battery/power condition is recorded.
- [ ] Production data backup status is verified rather than assumed.
- [ ] The proposed method has a written list of every possible RAM write.
- [ ] The proposed method has a written list of every possible page-table,
      CPU-state, MMIO, reset, and control-flow effect.
- [ ] Persistent writes are either proven impossible or the proposal is
      rejected by this project.
- [ ] No payload, arbitrary RAM writer, arbitrary branch, loader, or exploit
      component is part of the proposal.
- [ ] The expected artifact is defined before any live action is considered.
- [ ] The artifact can be represented by the existing handoff/MMU evidence
      formats without trusting raw pointers.

Current status: **NOT APPLICABLE** because no experiment is selected. Any
future non-empty state-change declaration requires a new specific approval.

## D. Failure and recovery truth

- [ ] Hang, panic, watchdog reset, bootloop, volatile corruption, and
      incomplete-artifact outcomes are listed.
- [ ] Recovery status is labelled `RECOVERY_PROVEN`, `RECOVERY_EXPECTED`, or
      `RECOVERY_UNKNOWN` for each failure mode.
- [ ] Any possible persistent side effect is labelled `PERSISTENCE_RISK` even
      when the intended artifact is RAM-only.
- [ ] Crown + Side Button behavior is treated as an expected stock path, not
      a guarantee for arbitrary experimental state.
- [ ] DFU access and restore support for this exact target/build are separately
      verified or remain `UNKNOWN/BLOCKED`.
- [ ] A recovery assessment does not rely on “RAM-only” as a zero-risk claim.
- [ ] The proposal has an explicit stop condition for any unexpected state.

Current status: **RECOVERY_UNKNOWN** for all live privileged methods reviewed
in Step 2.15.

## E. Specific approval gate

- [ ] The proposal names exactly one experiment and one method.
- [ ] The proposal names the target and firmware it applies to.
- [ ] The proposal names the exact expected artifact and EV IDs it might
      contribute to.
- [ ] The proposal states whether it is `READ_ONLY`,
      `PRIVILEGED_STATE_CHANGING`, `HIGH_RISK`, or `UNKNOWN`, with source
      evidence for that label.
- [ ] The proposal states all allowed state changes and rejects all others.
- [ ] The proposal states recovery evidence and unresolved risks.
- [ ] The user gives explicit approval for this specific proposal after the
      above information is reviewed.

Generic permission to plan research does not check these boxes. No box in
this section is checked for Step 2.15.

## Blank future experiment record

The following is a data-record template only; it contains no operational
steps:

```text
experiment_id: <not assigned>
method: <not selected>
target: Watch4,2 / N131bAP / T8006 / 21U580
repository_sha: <required>
expected_artifact: <required>
ev_ids_potentially_closable: []
classification: <required>
allowed_state_changes: []
persistent_write_required: <must be false or reject>
recovery_status: <required>
abort_condition: <required>
specific_user_approval: NO
```

## Final preflight status

```text
NO LIVE COMMANDS AUTHORIZED
NO DEVICE INTERACTION PERFORMED
PREFLIGHT RESULT = BLOCKED
```

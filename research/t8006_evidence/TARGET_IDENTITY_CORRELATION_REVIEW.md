# Target identity / correlation review

Phase 4 — EV-000 identity/correlation bridge research. This is host-only
research; no Apple Watch or iPhone was queried or changed.

> Historical note: this review predates the EV-000A/B/C split. Its references
> to the old identity portion of EV-000 now apply only to EV-000C. Technical
> target provenance is EV-000A + EV-000B; see
> [the current feasibility audit](EV000_FEASIBILITY_AUDIT.md).

## Result

| Item | Finding | Status |
|---|---|---|
| Reviewed branch / HEAD | `master` / `288024edb2b6c6846243762cdb593a000d3a024d` | CONFIRMED |
| `crashReporterKey` in the existing NanoPhotos IPS | Present in the locally available raw report; raw value is intentionally omitted | CONFIRMED |
| Apple-documented semantics | An anonymized per-device crash-report identifier; same-device reports use the same value; erasing the device resets it | CONFIRMED for Apple's documented crash-report field semantics |
| Exact Watch4,2 / 21U580 implementation behavior | No second Watch report is available here to independently compare | UNKNOWN |
| Same-report-source correlation | Possible by comparing two distinct, trustworthy report artifacts locally, within one key epoch | LIKELY until a second report is checked |
| Physical target identity from the key alone | Not established; the key is not a serial, attestation, signature, or proof of report origin | BLOCKED |
| EV-000 | Remains BLOCKED | BLOCKED |

The original file was found outside the repository at the previously specified
Downloads path. Its local SHA-256 and byte size match the already recorded
sanitized evidence record. No identifier value was emitted, copied into this
document, or committed. The reviewed Downloads root contained no second `.ips`
file; the repository's existing Windows/companion observation record also
contains no Watch-to-report identity bridge. This is a bounded inventory, not
a claim that no such artifact exists elsewhere.

## What Apple's field means

Apple's crash-report documentation describes **CrashReporter Key** as an
anonymized per-device identifier: two reports from the same device contain an
identical value, and the identifier is reset when the device is erased. Apple's
crash-report acquisition documentation says watchOS crash reports are
available on the paired iPhone. Sources:

* [Examining the fields in a crash report — Apple Developer Documentation](https://developer.apple.com/documentation/xcode/examining-the-fields-in-a-crash-report)
* [Acquiring crash reports and diagnostic logs — Apple Developer Documentation](https://developer.apple.com/documentation/xcode/acquiring-crash-reports-and-diagnostic-logs)

Therefore the appropriate interpretation is a **pseudonymous correlation key
for a CrashReporter identity epoch**, not an immutable hardware serial. Equality
across two separate reports can support that Apple CrashReporter associated the
reports with the same device identity epoch, provided the reports and fields
are authentic and unaltered. A device erase can break continuity for the same
physical unit. The documentation does not make the report cryptographically
self-authenticating, and a copied or edited report can copy the field too.

For this exact watchOS build, the key's presence in the NanoPhotos IPS is
CONFIRMED, and generic Apple semantics are CONFIRMED by documentation. A
second Watch4,2 report has not been checked, so exact-target repeatability is
not independently demonstrated. Do not infer a match, identity, or authenticity
from one value merely being present.

### What a matching key can and cannot establish

With two distinct, provenance-preserved Apple reports whose keys compare equal
locally, the content-level conclusion can be:

> Both report files carry the same CrashReporter per-device identifier for the
> same identifier epoch.

It cannot, by itself, establish:

* that either file genuinely came from Apple's reporting pipeline;
* that the report source is the particular physical Watch owned or selected by
  the user, rather than another Watch with the same model/software;
* a serial number, UDID, current pairing, or continuity across an erase or
  device replacement;
* that a later capture, ELF, descriptor, MMU dump, or other artifact came from
  that same Watch/session;
* any CPU, MMU, RAM, loader, ownership, or control-transfer fact.

It must never set `identity_proven=true` by itself. It can be one correlation
edge in provenance, not the authority/root of trust for EV-000.

## Candidate second evidence sources

“Stable” below means the property documented or reasonably supported by the
source; it does not imply cryptographic authenticity. No candidate was
acquired in this task.

| Candidate | Identifier / field | Authority | Stable per device? | Can match the existing IPS? | Can bind to the physical Watch? | Privacy risk | Device interaction needed? | EV-000 value |
|---|---|---|---|---|---|---|---|---|
| A second, already-existing watchOS analytics/crash `.ips` | `crashReporterKey`, plus distinct report timestamp/content | Apple documents the field's per-device cross-report semantics; an exported file itself is not signed by that documentation | Yes, within an identity epoch; reset on erase | **Yes**, by local equality comparison | Correlates report source, but not the report stream to the user's serial/selected physical unit | High: raw value is a stable pseudonymous identifier; keep raw private | **No** if already on host; otherwise obtaining it from Analytics Data involves iPhone/Watch interaction and is out of scope | Best next correlation artifact; partial provenance only, does not close EV-000 |
| Watch serial shown by Apple's Watch app on the paired iPhone | Hardware serial | Apple Support documents the serial in Watch app > General > About | Identifies a unit as represented by Apple's UI; replacement/service continuity is separate | **No**: the observed IPS has no serial field documented in its sanitized record | Can identify the paired Watch in that UI, but does not link the IPS's crash key to it | Very high; never commit or print it | **Yes**, iPhone UI interaction | Target metadata input only; no report/artifact binding by itself |
| Existing local Windows Lockdown/pairing record | Host/iPhone pairing-record fields | Existing host record; the repository's safe extraction reports iPhone pairing metadata, not a Watch pairing object | Not shown to identify the Watch | **No**: no crash key or Watch identity bridge present | **No** based on inspected safe fields | High if raw record or secrets are exposed; current artifact is whitelisted | **No** to re-read existing host file; no further parsing performed | No Watch EV-000 advance |
| Already-existing Apple support/Xcode diagnostic bundle | Potential Watch serial/model and report/log metadata; exact field set varies | Apple documents diagnostic acquisition and watchOS report availability, but does not document a bundle that co-binds serial and `crashReporterKey` | UNKNOWN for a cross-field binding | UNKNOWN; only if it contains the same key or an authoritative linkage | UNKNOWN until an exact artifact schema/source demonstrates the link | High; diagnostics can contain private identifiers and user data | **No** if already saved; creating/collecting one may involve device/paired-iPhone interaction | Potentially useful only if an authoritative, integrity-preserved bridge is documented; not currently established |
| Existing iPhone backup / Watch backup metadata | Backup manifest/device identity fields | Apple documents automatic Watch backup to the paired iPhone, not a crash-key-to-serial mapping in the backup | UNKNOWN for the required relationship | No known field linking it to this IPS | UNKNOWN | Very high; backups contain sensitive user/device data | Host-only if an existing backup is already available, but its contents may be protected/inaccessible | No demonstrated value; do not inspect private backup contents for this plan |

Apple Support says the Watch serial can be viewed in the paired iPhone's Watch
app, but that is a separate identifier and does not correlate to
`crashReporterKey` unless a trusted artifact explicitly contains both or an
authoritative service attests the relationship:
[How to find the serial number or IMEI for your Apple Watch — Apple Support](https://support.apple.com/en-us/108040).

The current local observation files confirm only an iPhone-side Windows/Apple
host record, not a Watch pairing object or a serial-to-crash-key link. The
previous Step 2.14 review also classifies normal companion metadata as
unverified for runtime/identity purposes.

## Privacy-preserving local correlation design

If a second pre-existing report is later supplied, compare the raw keys only
inside a local process. Do not log, print, paste, or commit either raw value.
For a durable pseudonymous result, a host can compute a domain-separated
HMAC-SHA-256 using a random secret held outside the repository (for example, in
the OS-protected credential store):

```text
HMAC-SHA-256(secret,
  "DreyzeOS/crashReporterKey/v1" || 0x00 || normalized_key_bytes)
```

The key normalization must be strict and documented; invalid encodings are
rejected rather than silently canonicalized. The secret is never committed.
The HMAC output is still a stable, linkable pseudonym within the project and
must be handled as sensitive metadata. If a public repository record is not
necessary, keep the fingerprint local and commit only a reviewed boolean
correlation result plus the method/version. If a fingerprint is committed,
include no secret and understand that repository readers can link all records
sharing it.

Neither HMAC nor a plain hash authenticates the report. It only protects the
raw identifier from direct disclosure and enables repeatable local equality
checks. Preserve per-report hashes, timestamps, and provenance separately;
never use a matching pseudonym as the sole identity attestation.

## Minimum evidence pairs and current decision

### A. `SAME_DEVICE_CORRELATION_PROVEN`

Minimum pair: the existing NanoPhotos IPS plus a **different** pre-existing
Apple Watch crash/analytics report, each with a locally verified file hash,
separately recorded source/provenance, WatchOS context, and `crashReporterKey`
compared equal locally. Check locally that the two artifacts are distinct
(different file hash and report event metadata); do not store incident IDs or
the raw key. Record whether an erase/replacement between reports is ruled out
or unknown. If report origin cannot be independently trusted, label the result
as **content-level key match**, not proof that Apple produced the artifacts.

This can establish cross-report correlation for the same CrashReporter key
epoch under the stated provenance assumptions. It does not establish the
physical serial identity or close EV-000.

### B. `TARGET_IDENTITY_PROVEN`

The IPS plus a second matching-key IPS is insufficient. In addition, require an
independent, authoritative identity-attestation artifact that binds the
CrashReporter key epoch (or the exact report hash/session) to a unique hardware
identity for the selected physical Watch, and states its issuer, method, and
integrity/provenance. No public Apple source reviewed here establishes that a
standard Windows/iPhone export exposes such a bridge. Availability is
**UNKNOWN**. Do not substitute user-entered strings, a model/build match, a
pairing filename, or a raw serial stored in Git.

Even that identity bridge would satisfy only the identity part of EV-000. Full
EV-000 still requires the requirement's target/session provenance for the
image, handoff descriptor, and MMU snapshot; capture ID/timestamps; producer
and interface; complete required-artifact coverage; verified local hashes; and
no proven conflicts.

### C. `STILL_NOT_PROVABLE_WITH_AVAILABLE_ARTIFACTS`

**Current result.** Only one report with a present key is available in the
reviewed locations. No second report and no authoritative serial-to-key or
report-to-physical-unit attestation were found. Consequently no same-device
comparison has yet occurred, `identity_proven` remains false, and EV-000
remains BLOCKED.

## Next minimal step and approval boundary

First, if one already exists on the host, provide a second distinct
watchOS-originated diagnostic report as a private local file. Offline analysis
of a user-supplied file requires no device interaction; the raw report and raw
correlation field stay out of Git. This is the smallest step that can test the
documented same-key correlation behavior and add a provenance edge.

If no second report already exists, stop. Retrieving one from the iPhone/Watch,
opening a device UI, or generating a new diagnostic requires separate,
explicit user approval for that specific interaction. Do not collect it
automatically. A subsequent identity-attestation source must be independently
reviewed before EV-000 can advance to identity-proven.

```text
SAME-DEVICE CORRELATION = POSSIBLE, NOT YET OBSERVED
TARGET IDENTITY PROVEN = NO
EV-000 = BLOCKED
LOADER CONTRACT = BLOCKED
FIRST HARDWARE EXECUTION = NOT READY
```

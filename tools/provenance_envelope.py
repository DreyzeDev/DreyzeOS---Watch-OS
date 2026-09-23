"""Host-only validation for the provenance sub-schema of handoff bundles.

This module validates declarations and local bytes. It cannot authenticate a
capture source or turn metadata strings into target identity proof.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


SCHEMA = "dreyzeos.target_provenance_envelope.v2"
LEGACY_SCHEMA = "dreyzeos.target_provenance_envelope.v1"
SUPPORTED_SCHEMAS = {SCHEMA, LEGACY_SCHEMA}
REQUIRED_EV000_ARTIFACTS = ("image", "handoff_descriptor", "mmu_snapshot")
ARTIFACT_TYPES = {
    "DREYZEOS_ELF",
    "HANDOFF_DESCRIPTOR_V1",
    "MMU_SNAPSHOT_MANIFEST",
    "CPU_STATE_RECORD",
    "RUNTIME_MEMORY_RECORD",
    "BOOT_ARGS_COPY",
    "DEVICETREE_COPY",
    "CONTROL_TRANSFER_RECORD",
    "TARGET_IDENTITY_ATTESTATION",
    "OTHER",
}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
RFC3339_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_fact(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and type(value.get("value_present")) is bool
        and type(value.get("value_proven")) is bool
        and (not value["value_proven"] or value["value_present"])
        and (value["value_present"] or value.get("value") is None)
        and (not value["value_proven"] or isinstance(value.get("source"), str) and bool(value["source"].strip()))
    )


def _same_target_value(field: str, actual: Any, expected: Any) -> bool:
    if field == "board":
        values = actual if isinstance(actual, list) else [actual]
        expected_values = expected if isinstance(expected, (list, tuple, set)) else [expected]
        normalized_actual = {str(x).strip().lower() for x in values}
        normalized_expected = {str(x).strip().lower() for x in expected_values}
        return bool(normalized_actual) and normalized_actual.issubset(normalized_expected)
    return str(actual).casefold() == str(expected).casefold()


def _resolve_local(base_dir: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("artifact path must be relative and cannot contain '..'")
    resolved = (base_dir / candidate).resolve()
    if not resolved.is_relative_to(base_dir.resolve()):
        raise ValueError("artifact path escapes the envelope directory")
    return resolved


def _timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not RFC3339_UTC_RE.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed


def validate_envelope(
    envelope: Any,
    base_dir: str | Path,
    expected_target: Dict[str, Any],
    *,
    bundle: Optional[Dict[str, Any]] = None,
    artifact_cache: Optional[Dict[str, Dict[str, Any]]] = None,
    path_resolver: Optional[Callable[[Path, Any, str], Path]] = None,
    file_hasher: Optional[Callable[[Path], str]] = None,
) -> Dict[str, Any]:
    """Validate one envelope; all claims remain distinguishable from computed facts."""
    base = Path(base_dir).resolve()
    cache = artifact_cache or {}
    resolver = path_resolver or (lambda root, value, _field: _resolve_local(root, value))
    hasher = file_hasher or _hash_file
    errors: List[str] = []
    conflicts: List[Dict[str, Any]] = []
    blockers: List[str] = []

    def problem(code: str, detail: str, *, conflict: bool = False) -> None:
        item = {
            "name": code,
            "code": code,
            "detail": detail,
            "status": "BLOCKED" if conflict else "UNKNOWN",
            "reason": detail,
        }
        errors.append(code)
        if conflict:
            conflicts.append(item)
        blockers.append(code)

    if not isinstance(envelope, dict):
        return {
            "schema": None,
            "status": "BLOCKED",
            "errors": ["ENVELOPE_NOT_OBJECT"],
            "conflicts": [],
            "blockers": ["ENVELOPE_NOT_OBJECT"],
            "requirements": {
                "EV-000": {"status": "BLOCKED", "proof_state": "NOT_PROVEN"},
                "EV-027": {"status": "BLOCKED", "proof_state": "NOT_PROVEN"},
            },
        }

    schema = envelope.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        problem("ENVELOPE_SCHEMA_UNSUPPORTED", f"schema must be {SCHEMA} or {LEGACY_SCHEMA}")
    legacy_schema = schema == LEGACY_SCHEMA

    source = envelope.get("source")
    source = source if isinstance(source, dict) else {}
    evidence_status = source.get("evidence_status", "UNKNOWN")
    source_kind = source.get("kind", "UNKNOWN")
    synthetic = source_kind == "synthetic" or evidence_status == "DESIGN"
    if evidence_status not in {"CONFIRMED", "LIKELY", "DESIGN", "UNKNOWN", "BLOCKED"}:
        problem("SOURCE_STATUS_INVALID", "source.evidence_status is outside the project vocabulary")
    if bundle is not None:
        bundle_source = bundle.get("source")
        if not isinstance(bundle_source, dict):
            problem("BUNDLE_SOURCE_MISSING", "embedded bundle.source is absent")
        elif bundle_source.get("kind") != source_kind or bundle_source.get("evidence_status") != evidence_status:
            problem("ENVELOPE_SOURCE_CONFLICT", "envelope source declarations disagree with bundle.source", conflict=True)

    capture = envelope.get("capture")
    capture = capture if isinstance(capture, dict) else {}
    capture_id_fact = capture.get("capture_id")
    capture_id = None
    capture_id_proven = False
    if not _is_fact(capture_id_fact):
        problem("CAPTURE_ID_FACT_INVALID", "capture.capture_id must use the explicit fact shape")
    elif capture_id_fact["value_present"]:
        capture_id = capture_id_fact["value"]
        capture_id_proven = capture_id_fact["value_proven"]
        try:
            if not isinstance(capture_id, str):
                raise ValueError("non-string capture ID")
            parsed_id = uuid.UUID(str(capture_id))
            if str(parsed_id) != capture_id:
                raise ValueError("non-canonical UUID")
        except (ValueError, AttributeError):
            problem("CAPTURE_ID_INVALID", "capture_id must be a canonical UUID")
            capture_id = None
    else:
        blockers.append("CAPTURE_ID_MISSING")

    capture_times: Dict[str, Optional[datetime]] = {}
    capture_times_proven = True
    for name in ("started_at_utc", "ended_at_utc"):
        item = capture.get(name)
        if not _is_fact(item):
            problem(f"{name.upper()}_FACT_INVALID", f"capture.{name} must use the explicit fact shape")
            capture_times[name] = None
            capture_times_proven = False
        elif item["value_present"]:
            capture_times[name] = _timestamp(item["value"])
            if capture_times[name] is None:
                problem(f"{name.upper()}_INVALID", f"capture.{name} must be an RFC3339 UTC timestamp")
                capture_times_proven = False
            capture_times_proven = capture_times_proven and item["value_proven"]
        else:
            capture_times[name] = None
            capture_times_proven = False
            blockers.append(f"{name.upper()}_UNKNOWN")
    if all(capture_times.values()) and capture_times["ended_at_utc"] < capture_times["started_at_utc"]:
        problem("CAPTURE_TIME_ORDER_INVALID", "capture end precedes capture start", conflict=True)

    target = envelope.get("target")
    target = target if isinstance(target, dict) else {}
    identity_issues: List[str] = []
    expected_metadata = target.get("expected_metadata")
    if not isinstance(expected_metadata, dict) or any(
        field not in expected_metadata or not _same_target_value(field, expected_metadata.get(field), value)
        for field, value in expected_target.items()
    ):
        problem("EXPECTED_TARGET_METADATA_MISMATCH", "target.expected_metadata does not match the verifier's fixed project target")
    metadata = target.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    metadata_values: Dict[str, Any] = {}
    metadata_sources: Dict[str, str] = {}
    metadata_mismatch_fields: List[str] = []
    metadata_complete = True
    metadata_facts_proven = True
    for field, expected in expected_target.items():
        fact = metadata.get(field)
        if not _is_fact(fact):
            metadata_complete = False
            metadata_facts_proven = False
            blockers.append(f"TARGET_METADATA_{field.upper()}_UNKNOWN")
            continue
        if not fact["value_present"]:
            metadata_complete = False
            metadata_facts_proven = False
            blockers.append(f"TARGET_METADATA_{field.upper()}_MISSING")
            continue
        metadata_values[field] = fact["value"]
        metadata_sources[field] = str(fact.get("source") or "unspecified")
        metadata_facts_proven = metadata_facts_proven and fact["value_proven"]
        if not _same_target_value(field, fact["value"], expected):
            metadata_mismatch_fields.append(field)
    computed_match = (
        metadata_complete
        and all(_same_target_value(field, metadata_values[field], expected) for field, expected in expected_target.items())
    )
    if metadata_mismatch_fields:
        mismatch_is_proven = any(
            _is_fact(metadata.get(field)) and metadata[field].get("value_proven")
            for field in metadata_mismatch_fields
        )
        problem(
            "TARGET_METADATA_MISMATCH",
            "target metadata fields disagree with the fixed project target: " + ", ".join(metadata_mismatch_fields),
            conflict=mismatch_is_proven,
        )
    metadata_match_fact = target.get("metadata_match")
    if not _is_fact(metadata_match_fact):
        problem("METADATA_MATCH_FACT_INVALID", "target.metadata_match must be an explicit boolean fact")
        metadata_match_proven = False
    elif not metadata_match_fact["value_present"]:
        metadata_match_proven = False
        blockers.append("METADATA_MATCH_UNKNOWN")
    elif type(metadata_match_fact["value"]) is not bool:
        problem("METADATA_MATCH_FACT_INVALID", "target.metadata_match.value must be boolean")
        metadata_match_proven = False
    else:
        metadata_match_proven = metadata_match_fact["value_proven"]
        if metadata_complete and metadata_match_fact["value"] != computed_match:
            problem("METADATA_MATCH_CONFLICT", "metadata_match disagrees with local target metadata comparison", conflict=True)
        elif metadata_complete and not computed_match:
            problem("TARGET_METADATA_MISMATCH", "declared target metadata does not match expected target")
    if bundle is not None:
        bundle_target = bundle.get("target")
        if not isinstance(bundle_target, dict):
            problem("BUNDLE_TARGET_MISSING", "embedded bundle.target is absent")
        else:
            for field, value in metadata_values.items():
                if field in bundle_target and not _same_target_value(field, value, bundle_target[field]):
                    problem("ENVELOPE_BUNDLE_TARGET_CONFLICT", f"target.{field} differs from bundle.target.{field}", conflict=True)

    producer = envelope.get("producer")
    producer = producer if isinstance(producer, dict) else {}
    producer_complete = True
    for field in ("name", "version", "host"):
        fact = producer.get(field)
        if not _is_fact(fact) or not fact["value_present"] or not fact["value_proven"] or not isinstance(fact.get("value"), str) or not fact["value"].strip():
            producer_complete = False
            blockers.append(f"PRODUCER_{field.upper()}_UNKNOWN")
    interface = envelope.get("source_interface")
    interface = interface if isinstance(interface, dict) else {}
    interface_complete = True
    for field in ("description", "interface"):
        fact = interface.get(field)
        if not _is_fact(fact) or not fact["value_present"] or not fact["value_proven"] or not isinstance(fact.get("value"), str) or not fact["value"].strip():
            interface_complete = False
            blockers.append(f"SOURCE_INTERFACE_{field.upper()}_UNKNOWN")
    interaction_class = interface.get("interaction_class")
    allowed_interaction = {
        "NO_DEVICE_INTERACTION",
        "READ_ONLY_DEVICE_INTERACTION",
        "PRIVILEGED_RESEARCH_REQUIRED",
        "POTENTIALLY_STATE_CHANGING",
        "PERSISTENT_WRITE_RISK",
        "UNKNOWN",
    }
    if not _is_fact(interaction_class) or not interaction_class["value_present"] or not interaction_class["value_proven"] or interaction_class.get("value") not in allowed_interaction:
        interface_complete = False
        blockers.append("SOURCE_INTERFACE_CLASS_UNKNOWN")

    assertions = target.get("assertions", [])
    proven_facts: Dict[str, List[tuple[Any, str]]] = {}
    for field, fact in metadata.items():
        if _is_fact(fact) and fact["value_present"] and fact["value_proven"]:
            proven_facts.setdefault(field, []).append((fact["value"], str(fact.get("source") or "target.metadata")))
    if not isinstance(assertions, list):
        problem("TARGET_ASSERTIONS_INVALID", "target.assertions must be an array")
        assertions = []
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict) or not isinstance(assertion.get("field"), str) or not _is_fact(assertion):
            problem("TARGET_ASSERTION_INVALID", f"target.assertions[{index}] is malformed")
            continue
        if assertion["value_present"] and assertion["value_proven"]:
            proven_facts.setdefault(assertion["field"], []).append(
                (assertion["value"], str(assertion.get("source") or f"target.assertions[{index}]"))
            )
    for field, facts in proven_facts.items():
        for left_index, (left_value, left_source) in enumerate(facts):
            for right_value, right_source in facts[left_index + 1:]:
                if not _same_target_value(field, left_value, right_value):
                    problem(
                        "PROVEN_TARGET_FACT_CONFLICT",
                        f"proven target {field} values disagree ({left_source} vs {right_source})",
                        conflict=True,
                    )

    legacy_identity_fact = target.get("identity_proven") if legacy_schema else None
    physical_identity_fact = target.get("physical_identity") if not legacy_schema else None
    if legacy_schema:
        if legacy_identity_fact is not None and (
            not _is_fact(legacy_identity_fact)
            or not legacy_identity_fact["value_present"]
            or type(legacy_identity_fact["value"]) is not bool
        ):
            identity_issues.append("LEGACY_IDENTITY_FACT_INVALID")
        physical_identity_value = False
        physical_identity_claim_proven = False
    else:
        if "identity_proven" in target:
            identity_issues.append("LEGACY_IDENTITY_FIELD_IGNORED_IN_V2")
        if (
            not _is_fact(physical_identity_fact)
            or not physical_identity_fact["value_present"]
            or type(physical_identity_fact["value"]) is not bool
        ):
            identity_issues.append("PHYSICAL_IDENTITY_FACT_MISSING_OR_INVALID")
            physical_identity_value = False
            physical_identity_claim_proven = False
        else:
            physical_identity_value = physical_identity_fact["value"]
            physical_identity_claim_proven = physical_identity_fact["value_proven"]

    identity_attestation = target.get("identity_attestation")
    attestation_id = identity_attestation.get("artifact_id") if isinstance(identity_attestation, dict) else None

    artifacts_raw = envelope.get("artifacts")
    if not isinstance(artifacts_raw, list):
        problem("ARTIFACTS_INVALID", "artifacts must be an array")
        artifacts_raw = []
    artifacts: Dict[str, Dict[str, Any]] = {}
    used_paths: Dict[str, str] = {}
    for index, entry in enumerate(artifacts_raw):
        if not isinstance(entry, dict):
            problem("ARTIFACT_ENTRY_INVALID", f"artifacts[{index}] must be an object")
            continue
        artifact_id = entry.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id:
            problem("ARTIFACT_ID_INVALID", f"artifacts[{index}].artifact_id is missing")
            continue
        if artifact_id in artifacts:
            problem("ARTIFACT_ID_DUPLICATE", f"artifact_id {artifact_id} is declared more than once", conflict=True)
            continue
        artifact_type = entry.get("artifact_type")
        if artifact_type not in ARTIFACT_TYPES:
            problem("ARTIFACT_TYPE_UNSUPPORTED", f"{artifact_id} has unsupported artifact_type")
        path_value = entry.get("path")
        digest = entry.get("sha256")
        actual_path: Optional[Path] = None
        path_error: Optional[str] = None
        present_actual = False
        actual_hash: Optional[str] = None
        if path_value is not None:
            if not isinstance(path_value, str) or not path_value:
                path_error = "path must be a non-empty relative path or null"
            else:
                try:
                    actual_path = resolver(base, path_value, f"provenance_envelope.artifacts[{artifact_id}].path")
                    present_actual = actual_path.is_file()
                    if present_actual:
                        cache_item = cache.get(entry.get("bundle_ref")) if isinstance(entry.get("bundle_ref"), str) else None
                        if cache_item and cache_item.get("sha256_actual"):
                            actual_hash = str(cache_item["sha256_actual"])
                        else:
                            actual_hash = hasher(actual_path)
                except Exception as exc:
                    # Safe path helpers may raise a project-specific input error.
                    path_error = str(getattr(exc, "code", None) or exc)
        for key, actual_value in (
            ("artifact_present", present_actual),
            ("artifact_hash_verified", bool(present_actual and SHA256_RE.fullmatch(str(digest or "")) and actual_hash == str(digest).lower())),
        ):
            declared_fact = entry.get(key)
            if not _is_fact(declared_fact):
                problem(f"{key.upper()}_FACT_INVALID", f"{artifact_id}.{key} must use the explicit fact shape")
                declared_value = None
            elif not declared_fact["value_present"]:
                declared_value = None
                if actual_value:
                    problem(f"{key.upper()}_FACT_UNKNOWN", f"{artifact_id}.{key} is not declared although local validation found true")
            elif type(declared_fact["value"]) is not bool:
                problem(f"{key.upper()}_FACT_INVALID", f"{artifact_id}.{key}.value must be boolean")
                declared_value = None
            else:
                declared_value = declared_fact["value"]
                if declared_value != actual_value:
                    problem(
                        f"{key.upper()}_DECLARATION_CONFLICT",
                        f"{artifact_id}.{key} declaration disagrees with local validation",
                        conflict=True,
                    )
        if path_error:
            problem("ARTIFACT_PATH_INVALID", f"{artifact_id}: {path_error}")
        presence_declaration = entry.get("artifact_present")
        if path_value is None and _is_fact(presence_declaration) and presence_declaration.get("value_present"):
            if presence_declaration.get("value") is True:
                problem("ARTIFACT_PATH_MISSING", f"{artifact_id} claims presence without a path", conflict=True)
        if present_actual and not SHA256_RE.fullmatch(str(digest or "")):
            problem("ARTIFACT_HASH_MISSING", f"{artifact_id} is present but has no valid SHA-256 declaration")
        hash_ok = bool(present_actual and actual_hash and SHA256_RE.fullmatch(str(digest or "")) and actual_hash == str(digest).lower())
        if present_actual and actual_hash is not None and SHA256_RE.fullmatch(str(digest or "")) and not hash_ok:
            problem("ARTIFACT_HASH_MISMATCH", f"{artifact_id} SHA-256 does not match local bytes", conflict=True)
        if isinstance(path_value, str) and actual_path is not None:
            normalized_path = str(actual_path)
            if normalized_path in used_paths:
                problem("ARTIFACT_PATH_ALIAS", f"{artifact_id} and {used_paths[normalized_path]} refer to the same file", conflict=True)
            used_paths[normalized_path] = artifact_id
        relationship = entry.get("provenance_relationship")
        relationship_ok = (
            isinstance(relationship, dict)
            and relationship.get("capture_id") == capture_id
            and isinstance(relationship.get("relationship"), str)
            and bool(relationship.get("relationship"))
            and _is_fact(relationship.get("relationship_proven"))
            and relationship["relationship_proven"].get("value_present") is True
            and relationship["relationship_proven"].get("value") is True
            and relationship["relationship_proven"].get("value_proven") is True
        )
        for field in ("artifact_target_bound", "artifact_runtime_proven"):
            fact = entry.get(field)
            if not _is_fact(fact) or not fact["value_present"] or type(fact["value"]) is not bool:
                problem(f"{field.upper()}_FACT_INVALID", f"{artifact_id}.{field} must be an explicit boolean fact")
        target_bound_fact = entry.get("artifact_target_bound")
        runtime_fact = entry.get("artifact_runtime_proven")
        target_bound = bool(_is_fact(target_bound_fact) and target_bound_fact.get("value") is True and target_bound_fact.get("value_proven") is True)
        runtime_proven = bool(_is_fact(runtime_fact) and runtime_fact.get("value") is True and runtime_fact.get("value_proven") is True)
        if target_bound and not relationship_ok:
            problem("ARTIFACT_TARGET_BINDING_UNSUPPORTED", f"{artifact_id} target binding lacks a proven same-session relationship")
        if (
            isinstance(relationship, dict)
            and relationship.get("capture_id") != capture_id
            and _is_fact(relationship.get("relationship_proven"))
            and relationship["relationship_proven"].get("value") is True
            and relationship["relationship_proven"].get("value_proven") is True
        ):
            problem("ARTIFACT_SESSION_CONFLICT", f"{artifact_id} declares a proven relationship to a different capture ID", conflict=True)
        if runtime_proven and (not target_bound or not source.get("runtime_evidence_source")):
            problem("ARTIFACT_RUNTIME_PROOF_UNSUPPORTED", f"{artifact_id} runtime proof lacks target binding or runtime source")
        bundle_ref = entry.get("bundle_ref")
        if bundle is not None and bundle_ref is not None:
            root_spec = bundle.get(bundle_ref) if isinstance(bundle_ref, str) else None
            if not isinstance(root_spec, dict):
                problem("BUNDLE_ARTIFACT_REFERENCE_MISSING", f"{artifact_id} bundle_ref does not name a bundle artifact")
            elif root_spec.get("path", root_spec.get("file")) != path_value or str(root_spec.get("sha256", "")).lower() != str(digest or "").lower():
                problem("BUNDLE_ARTIFACT_REFERENCE_CONFLICT", f"{artifact_id} path/hash disagrees with bundle.{bundle_ref}", conflict=True)
        artifacts[artifact_id] = {
            "artifact_type": artifact_type,
            "bundle_ref": bundle_ref,
            "path": path_value,
            "sha256_expected": digest,
            "sha256_actual": actual_hash,
            "artifact_present": present_actual,
            "artifact_hash_verified": hash_ok,
            "artifact_target_bound": False,
            "artifact_session_bound": bool(present_actual and hash_ok and relationship_ok),
            "artifact_runtime_proven": False,
            "artifact_target_bound_claimed": target_bound,
            "artifact_runtime_proven_claimed": runtime_proven,
            "provenance_relationship_proven": relationship_ok,
            "provenance_relationship": relationship.get("relationship") if isinstance(relationship, dict) else None,
            "provenance_relationship_claim": relationship.get("relationship_proven") if isinstance(relationship, dict) else None,
            "claims": {
                key: entry.get(key)
                for key in (
                    "artifact_present",
                    "artifact_hash_verified",
                    "artifact_target_bound",
                    "artifact_runtime_proven",
                )
            },
            "status": "CONFIRMED" if present_actual and hash_ok else ("UNKNOWN" if not present_actual else "BLOCKED"),
        }

    coverage = envelope.get("coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    required_ids = coverage.get("required_artifact_ids")
    declared_ids = coverage.get("declared_artifact_ids")
    covered_ids = coverage.get("covered_artifact_ids")
    lists_valid = all(isinstance(value, list) and all(isinstance(item, str) for item in value) for value in (required_ids, declared_ids, covered_ids))
    if not lists_valid:
        problem("COVERAGE_LIST_INVALID", "coverage artifact ID lists must be arrays of strings")
        required_ids, declared_ids, covered_ids = [], [], []
    if set(REQUIRED_EV000_ARTIFACTS) - set(required_ids):
        problem("COVERAGE_REQUIRED_SET_INVALID", "coverage must name image, handoff_descriptor, and mmu_snapshot for EV-000")
    if set(declared_ids) != set(artifacts):
        problem("COVERAGE_DECLARATION_MISMATCH", "declared_artifact_ids must match artifact entries", conflict=True)
    if not set(covered_ids).issubset(set(declared_ids)):
        problem("COVERAGE_UNKNOWN_ARTIFACT", "coverage names an undeclared artifact", conflict=True)
    coverage_fact = coverage.get("coverage_complete")
    complete_by_list = set(REQUIRED_EV000_ARTIFACTS).issubset(set(covered_ids)) and set(REQUIRED_EV000_ARTIFACTS).issubset(set(artifacts))
    coverage_claim_proven = bool(_is_fact(coverage_fact) and coverage_fact.get("value_present") and coverage_fact.get("value") is True and coverage_fact.get("value_proven") is True)
    if _is_fact(coverage_fact) and coverage_fact.get("value_present") and coverage_fact.get("value") is True and not complete_by_list:
        problem("COVERAGE_COMPLETENESS_CONFLICT", "coverage_complete=true but required artifact coverage is incomplete", conflict=True)
    coverage_complete = complete_by_list and coverage_claim_proven
    if bundle is not None and isinstance(bundle.get("target_provenance"), dict):
        legacy = bundle["target_provenance"]
        legacy_covered = legacy.get("covered_artifacts")
        if "coverage_proven" in legacy and type(legacy.get("coverage_proven")) is bool:
            if legacy["coverage_proven"] != bool(_is_fact(coverage_fact) and coverage_fact.get("value") is True):
                problem("LEGACY_COVERAGE_CONFLICT", "legacy target_provenance.coverage_proven disagrees with envelope", conflict=True)
        if legacy_covered is not None and (
            not isinstance(legacy_covered, list)
            or set(legacy_covered) != set(covered_ids)
        ):
            problem("LEGACY_COVERED_ARTIFACTS_CONFLICT", "legacy target_provenance.covered_artifacts disagrees with envelope", conflict=True)
    for artifact_id, artifact_result in artifacts.items():
        if artifact_result["artifact_target_bound"] and artifact_id not in covered_ids:
            problem("TARGET_BOUND_ARTIFACT_NOT_COVERED", f"{artifact_id} is target-bound but absent from covered_artifact_ids", conflict=True)

    required_artifacts_valid = all(
        artifact_id in artifacts
        and artifacts[artifact_id]["artifact_present"]
        and artifacts[artifact_id]["artifact_hash_verified"]
        and artifacts[artifact_id]["provenance_relationship_proven"]
        for artifact_id in REQUIRED_EV000_ARTIFACTS
    )
    attestation_valid = False
    if isinstance(attestation_id, str) and attestation_id in artifacts:
        attestation_artifact = artifacts[attestation_id]
        attestation_valid = (
            attestation_artifact["artifact_type"] == "TARGET_IDENTITY_ATTESTATION"
            and attestation_artifact["artifact_present"]
            and attestation_artifact["artifact_hash_verified"]
            and isinstance(identity_attestation.get("authority"), str)
            and bool(identity_attestation.get("authority").strip())
            and isinstance(identity_attestation.get("method"), str)
            and bool(identity_attestation.get("method").strip())
            and identity_attestation.get("identity_scope") == "PERSISTENT_PHYSICAL_DEVICE"
            and not attestation_artifact["artifact_target_bound"]
        )
    if legacy_schema:
        # A v1 identity claim was ambiguous between target/session binding and
        # persistent physical identity. Keep accepting the file, but never
        # migrate that claim into EV-000C without an explicit v2 scope.
        legacy_identity_claim = legacy_identity_fact if _is_fact(legacy_identity_fact) else None
        if isinstance(legacy_identity_claim, dict) and legacy_identity_claim.get("value") is True:
            identity_issues.append("LEGACY_IDENTITY_CLAIM_NOT_MIGRATED_TO_PHYSICAL_IDENTITY")
        physical_identity_proven = False
        physical_identity_status = "NOT_PROVEN"
    else:
        legacy_identity_claim = None
        if physical_identity_value and (
            not physical_identity_claim_proven or not attestation_valid or synthetic
        ):
            identity_issues.append("PHYSICAL_IDENTITY_PROOF_UNSUPPORTED")
        physical_identity_proven = bool(
            physical_identity_value
            and physical_identity_claim_proven
            and attestation_valid
            and not synthetic
            and evidence_status == "CONFIRMED"
            and not conflicts
            and not errors
        )
        physical_identity_status = (
            "CONFIRMED" if physical_identity_proven else
            "DESIGN" if synthetic and physical_identity_value else
            "BLOCKED" if physical_identity_value and identity_issues else
            "NOT_PROVEN"
        )

    metadata_conflict_codes = {
        "METADATA_MATCH_CONFLICT",
        "TARGET_METADATA_MISMATCH",
        "PROVEN_TARGET_FACT_CONFLICT",
        "ENVELOPE_BUNDLE_TARGET_CONFLICT",
    }
    metadata_conflict = (
        any(item.get("code") in metadata_conflict_codes for item in conflicts)
        or "TARGET_METADATA_MISMATCH" in errors
    )
    metadata_proven = bool(
        computed_match
        and metadata_facts_proven
        and metadata_match_proven
        and isinstance(metadata_match_fact, dict)
        and metadata_match_fact.get("value") is True
        and not metadata_conflict
    )
    required_relations_proven = all(
        artifact_id in artifacts and artifacts[artifact_id]["artifact_session_bound"]
        for artifact_id in REQUIRED_EV000_ARTIFACTS
    )
    covered_relations_proven = all(
        artifact_id in artifacts and artifacts[artifact_id]["artifact_session_bound"]
        for artifact_id in covered_ids
    )
    session_conflict_codes = {
        "ARTIFACT_SESSION_CONFLICT",
        "ENVELOPE_SOURCE_CONFLICT",
        "COVERAGE_DECLARATION_MISMATCH",
        "COVERAGE_UNKNOWN_ARTIFACT",
        "COVERAGE_COMPLETENESS_CONFLICT",
        "ARTIFACT_ID_DUPLICATE",
        "ARTIFACT_PATH_ALIAS",
    }
    session_conflict = any(item.get("code") in session_conflict_codes for item in conflicts)
    session_error_prefixes = (
        "CAPTURE_", "STARTED_AT_", "ENDED_AT_", "PRODUCER_", "SOURCE_INTERFACE_",
        "ARTIFACT_", "COVERAGE_", "BUNDLE_ARTIFACT_",
    )
    session_errors = any(code.startswith(session_error_prefixes) or code == "BUNDLE_SOURCE_MISSING" for code in errors)
    session_structure_proven = bool(
        capture_id is not None
        and capture_id_proven
        and capture_times_proven
        and producer_complete
        and interface_complete
        and coverage_complete
        and required_artifacts_valid
        and required_relations_proven
        and covered_relations_proven
        and not session_conflict
        and not session_errors
    )
    same_session_proven = session_structure_proven and (synthetic or evidence_status == "CONFIRMED")
    same_session_status = (
        "CONFIRMED" if same_session_proven and not synthetic else
        "DESIGN" if same_session_proven and synthetic else
        "BLOCKED" if session_conflict else
        "UNKNOWN"
    )
    metadata_status = (
        "BLOCKED" if metadata_conflict or (computed_match is False and metadata_complete) else
        "CONFIRMED" if metadata_proven and evidence_status == "CONFIRMED" and not synthetic else
        "DESIGN" if metadata_proven and synthetic else
        "LIKELY" if any(fact.get("value_present") for fact in metadata.values() if isinstance(fact, dict)) else
        "UNKNOWN"
    )
    metadata_proof_state = "PROVEN" if metadata_proven else "NOT_PROVEN"
    technical_target_provenance_ready = bool(
        metadata_proven
        and same_session_proven
        and evidence_status == "CONFIRMED"
        and not synthetic
        and not conflicts
        and not errors
    )
    for artifact_id, artifact_result in artifacts.items():
        artifact_result["artifact_target_bound"] = bool(
            metadata_proven
            and same_session_proven
            and evidence_status == "CONFIRMED"
            and not synthetic
        )
        if artifact_result["artifact_target_bound_claimed"] and not artifact_result["artifact_target_bound"]:
            if not legacy_schema:
                problem("ARTIFACT_TARGET_BINDING_UNSUPPORTED", f"{artifact_id} claims target binding without proven target metadata and same-session provenance")
        artifact_result["artifact_runtime_proven"] = bool(
            artifact_result["artifact_runtime_proven_claimed"]
            and artifact_result["artifact_target_bound"]
            and bool(source.get("runtime_evidence_source"))
        )
    required_target_bound = all(
        artifact_id in artifacts
        and artifacts[artifact_id]["artifact_session_bound"]
        and artifacts[artifact_id]["artifact_target_bound"]
        and metadata_proven
        and same_session_proven
        for artifact_id in REQUIRED_EV000_ARTIFACTS
    )
    if not required_target_bound:
        blockers.append("REQUIRED_ARTIFACT_TARGET_BINDING_MISSING")
    ev000_ok = (
        evidence_status == "CONFIRMED"
        and metadata_proven
        and same_session_proven
        and coverage_complete
        and capture_id is not None
        and capture_id_proven
        and capture_times_proven
        and producer_complete
        and interface_complete
        and required_artifacts_valid
        and required_target_bound
        and not conflicts
        and not errors
    )
    ev000_status = "CONFIRMED" if ev000_ok else ("DESIGN" if synthetic else "BLOCKED")
    ev027_ok = False  # The full handoff verifier owns EV-027 bundle completeness.
    ev000_reasons: List[str] = []
    if evidence_status != "CONFIRMED":
        ev000_reasons.append("source evidence status is not CONFIRMED")
    if not metadata_proven:
        ev000_reasons.append("target metadata comparison is absent, mismatched, or unproven")
    if not same_session_proven:
        ev000_reasons.append("required artifacts are not proven members of one complete capture session")
    if not coverage_complete:
        ev000_reasons.append("required artifact coverage is absent, partial, or unproven")
    if not required_artifacts_valid:
        ev000_reasons.append("required local artifacts are missing or their declared hashes do not verify")
    if not required_target_bound:
        ev000_reasons.append("one or more required artifacts are not independently target-bound")
    if not (capture_id is not None and capture_id_proven and capture_times_proven):
        ev000_reasons.append("capture ID or UTC timestamps are missing/unproven")
    if not producer_complete or not interface_complete:
        ev000_reasons.append("producer or acquisition-interface provenance is incomplete")
    if conflicts:
        ev000_reasons.append("conflicting proven target facts block closure")
    if errors:
        ev000_reasons.append("envelope validation errors must be resolved")
    report_status = (
        "BLOCKED"
        if conflicts or errors or evidence_status == "BLOCKED"
        else "DESIGN"
        if synthetic
        else "CONFIRMED"
        if ev000_ok
        else "LIKELY"
        if evidence_status == "LIKELY"
        else "UNKNOWN"
    )
    return {
        "schema": SCHEMA,
        "input_schema": schema,
        "status": report_status,
        "source_kind": source_kind,
        "evidence_status": evidence_status,
        "capture": {
            "capture_id_present": capture_id is not None,
            "capture_id": capture_id,
            "started_at_utc_present": bool(capture_times.get("started_at_utc")),
            "ended_at_utc_present": bool(capture_times.get("ended_at_utc")),
            "started_at_utc": capture.get("started_at_utc", {}).get("value") if isinstance(capture.get("started_at_utc"), dict) else None,
            "ended_at_utc": capture.get("ended_at_utc", {}).get("value") if isinstance(capture.get("ended_at_utc"), dict) else None,
            "claims": {
                name: capture.get(name)
                for name in ("capture_id", "started_at_utc", "ended_at_utc")
            },
        },
        "target": {
            "metadata_match": computed_match if metadata_complete else None,
            "metadata_match_proven": metadata_proven,
            "metadata_status": metadata_status,
            "metadata_completeness": "COMPLETE" if metadata_complete else "PARTIAL",
            "metadata_facts_proven": metadata_facts_proven,
            "metadata_sources": metadata_sources,
            "metadata_facts": {field: metadata.get(field) for field in expected_target},
            "metadata_match_claim": metadata_match_fact,
            "same_session_provenance": same_session_proven,
            "same_session_provenance_status": same_session_status,
            "physical_identity_proven": physical_identity_proven,
            "physical_identity_status": physical_identity_status,
            "identity_proven": physical_identity_proven,
            "legacy_identity_claim": legacy_identity_claim,
            "identity_claim": physical_identity_fact if not legacy_schema else legacy_identity_fact,
            "identity_attestation_valid": attestation_valid,
            "identity_attestation": identity_attestation,
            "technical_target_provenance_ready": technical_target_provenance_ready,
        },
        "producer": producer,
        "source_interface": interface,
        "coverage": {
            "required_artifact_ids": list(required_ids),
            "declared_artifact_ids": list(declared_ids),
            "covered_artifact_ids": list(covered_ids),
            "coverage_complete_claimed_and_consistent": coverage_complete,
        },
        "artifacts": artifacts,
        "identity_issues": identity_issues,
        "schema_compatibility": "LEGACY_V1_ACCEPTED_WITHOUT_PHYSICAL_IDENTITY_MIGRATION" if legacy_schema else "CURRENT_V2",
        "conflicts": conflicts,
        "errors": errors,
        "blockers": sorted(set(blockers + ([] if metadata_proven else ["EV-000A"]) + ([] if same_session_proven else ["EV-000B"]) + ([] if ev000_ok else ["EV-000"]) + ["EV-027"])),
        "requirements": {
            "EV-000": {
                "status": ev000_status,
                "proof_state": "PROVEN" if ev000_ok else "NOT_PROVEN",
                "reason": "target metadata and complete same-session artifact provenance are independently proven; physical identity is not a prerequisite" if ev000_ok else "; ".join(ev000_reasons),
                "evidence_sources": ["provenance_envelope.target", "provenance_envelope.coverage", "provenance_envelope.artifacts"],
            },
            "EV-000A": {
                "status": metadata_status,
                "proof_state": metadata_proof_state,
                "reason": "all expected target metadata fields match and are proven" if metadata_proven else "target metadata is partial, unproven, or conflicting",
                "evidence_sources": ["provenance_envelope.target.metadata", "provenance_envelope.target.metadata_match"],
            },
            "EV-000B": {
                "status": same_session_status,
                "proof_state": "PROVEN" if same_session_proven else "NOT_PROVEN",
                "reason": "all required and covered artifacts have verified bytes and proven relationships to one capture session" if same_session_proven else "capture/session provenance, artifact coverage, or per-artifact relationships are incomplete",
                "evidence_sources": ["provenance_envelope.capture", "provenance_envelope.coverage", "provenance_envelope.artifacts[].provenance_relationship"],
            },
            "EV-000C": {
                "status": "CONFIRMED" if physical_identity_proven else physical_identity_status,
                "proof_state": "PROVEN" if physical_identity_proven else "NOT_PROVEN",
                "critical": False,
                "readiness_effect": "NONE_FOR_FIRST_TECHNICAL_BRINGUP",
                "reason": "persistent physical-device identity is independently attested" if physical_identity_proven else "physical identity/cross-session continuity is not proven and is not required for first technical bring-up",
                "evidence_sources": ["provenance_envelope.target.physical_identity", "provenance_envelope.target.identity_attestation"],
            },
            "EV-027": {
                "status": "BLOCKED" if not ev027_ok else "CONFIRMED",
                "proof_state": "PROVEN" if ev027_ok else "NOT_PROVEN",
                "reason": "EV-027 requires the full handoff verifier's complete critical artifact graph; an envelope alone cannot close it",
                "evidence_sources": ["handoff_evidence_verifier.bundle_integrity", "handoff_evidence_verifier.cpu_consistency"],
            },
        },
        "sha256_scope": "local byte equality only; not capture authenticity",
        "hardware_readiness_effect": "NONE",
    }

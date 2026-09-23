#!/usr/bin/env python3
"""Offline T8006 runtime-evidence gap analysis.

This tool consumes only two local JSON files: a Step 2.11 verifier report and
the repository-owned Step 2.12 requirements inventory.  It never opens device
memory, follows pointers, imports a page-table walker, executes a payload, or
performs network/USB/DFU operations.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


SCHEMA = "dreyzeos.t8006_evidence_requirements.v2"
LEGACY_SCHEMA = "dreyzeos.t8006_evidence_requirements.v1"
VERIFICATION_SCHEMA = "dreyzeos.handoff_evidence.v1"
STATUS_VALUES = {"CONFIRMED", "LIKELY", "DESIGN", "UNKNOWN", "BLOCKED"}
PROOF_VALUES = {"PRESENT", "PROVEN", "NOT_PROVEN", "NOT_APPLICABLE"}
EXPECTED_TARGET = {
    "model": "Watch4,2",
    "board": "N131bAP",
    "soc": "T8006",
    "firmware": "watchOS 10.6.1",
    "build": "21U580",
    "architecture": "aarch64",
}
REQUIRED_GROUPS = {
    "TARGET_PROVENANCE",
    "CPU_STATE",
    "MMU_STATE",
    "RUNTIME_MEMORY",
    "PAYLOAD_PLACEMENT",
    "MMU_MAPPINGS",
    "DESCRIPTOR_TRUST",
    "BOOT_METADATA",
    "COLLISION_AUDIT",
    "LOADER_TRANSFER",
    "SAFETY_POLICY",
    "BUNDLE_COMPLETENESS",
}


class GapInputError(Exception):
    """Deterministic malformed-input error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def load_json(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GapInputError("FILE_ERROR", f"cannot read {label}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GapInputError("MALFORMED_JSON", f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise GapInputError("OBJECT_REQUIRED", f"{label} must contain a JSON object")
    return value


def require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise GapInputError("BOOLEAN_REQUIRED", f"{name} must be a JSON boolean")
    return value


def normalize_board(value: Any) -> Set[str]:
    values = value if isinstance(value, list) else [value]
    return {str(item).lower() for item in values if item is not None}


def validate_requirements(document: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Set[str]]:
    if document.get("schema") not in {SCHEMA, LEGACY_SCHEMA}:
        raise GapInputError("SCHEMA_MISMATCH", f"requirements schema must be {SCHEMA} or {LEGACY_SCHEMA}")
    target = document.get("target")
    if not isinstance(target, dict):
        raise GapInputError("TARGET_REQUIRED", "requirements target metadata is missing")
    target_mismatches: Dict[str, Any] = {}
    for field, expected in EXPECTED_TARGET.items():
        actual = target.get(field)
        if field == "board":
            if normalize_board(actual) != normalize_board(expected):
                target_mismatches[field] = {"expected": expected, "actual": actual}
        elif str(actual).lower() != str(expected).lower():
            target_mismatches[field] = {"expected": expected, "actual": actual}
    if target_mismatches:
        raise GapInputError("REQUIREMENTS_TARGET_MISMATCH", json.dumps(target_mismatches, sort_keys=True))
    requirements = document.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise GapInputError("REQUIREMENTS_REQUIRED", "requirements must be a non-empty array")
    ids: Set[str] = set()
    groups: Set[str] = set()
    for index, item in enumerate(requirements):
        name = f"requirements[{index}]"
        if not isinstance(item, dict):
            raise GapInputError("REQUIREMENT_OBJECT_REQUIRED", f"{name} must be an object")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise GapInputError("REQUIREMENT_ID_REQUIRED", f"{name}.id is required")
        if identifier in ids:
            raise GapInputError("DUPLICATE_REQUIREMENT_ID", identifier)
        ids.add(identifier)
        if item.get("status") not in STATUS_VALUES:
            raise GapInputError("INVALID_STATUS", f"{identifier}.status is invalid")
        if not isinstance(item.get("critical"), bool):
            raise GapInputError("BOOLEAN_REQUIRED", f"{identifier}.critical must be boolean")
        group = item.get("evidence_group")
        if not isinstance(group, str) or not group:
            raise GapInputError("EVIDENCE_GROUP_REQUIRED", f"{identifier}.evidence_group is required")
        groups.add(group)
        closure = item.get("closure_conditions")
        if not isinstance(closure, list) or not closure or not all(
            isinstance(condition, str) and condition.strip() for condition in closure
        ):
            raise GapInputError("CLOSURE_CONDITIONS_REQUIRED", f"{identifier} has no closure conditions")
        nodes = item.get("verifier_requirements")
        if not isinstance(nodes, list) or not all(isinstance(node, str) and node for node in nodes):
            raise GapInputError("VERIFIER_NODES_REQUIRED", f"{identifier}.verifier_requirements is invalid")
        mapping_optional = item.get("verifier_mapping_optional", False)
        if not isinstance(mapping_optional, bool):
            raise GapInputError("BOOLEAN_REQUIRED", f"{identifier}.verifier_mapping_optional must be boolean")
        if not nodes and not mapping_optional:
            raise GapInputError("VERIFIER_NODES_REQUIRED", f"{identifier} has no verifier node mapping")
        if not isinstance(item.get("evidence_sources"), list):
            raise GapInputError("EVIDENCE_SOURCES_REQUIRED", f"{identifier}.evidence_sources is invalid")
        if not isinstance(item.get("missing"), str) or not item["missing"].strip():
            raise GapInputError("MISSING_EVIDENCE_REQUIRED", f"{identifier}.missing is required")
    missing_groups = REQUIRED_GROUPS - groups
    if missing_groups:
        raise GapInputError(
            "REQUIRED_GROUPS_MISSING",
            "requirements omit groups: " + ", ".join(sorted(missing_groups)),
        )
    return requirements, groups


def validate_report(report: Dict[str, Any]) -> Dict[str, Any]:
    if report.get("schema") != VERIFICATION_SCHEMA:
        raise GapInputError("VERIFICATION_SCHEMA_MISMATCH", f"verification schema must be {VERIFICATION_SCHEMA}")
    if not isinstance(report.get("evidence_graph"), dict):
        raise GapInputError("GRAPH_REQUIRED", "verification report has no evidence_graph")
    nodes = report["evidence_graph"].get("nodes")
    if not isinstance(nodes, dict):
        raise GapInputError("NODES_REQUIRED", "verification report has no evidence_graph.nodes")
    for name, node in nodes.items():
        if not isinstance(name, str) or not isinstance(node, dict):
            raise GapInputError("MALFORMED_NODE", "every evidence graph node must be an object")
        if node.get("status") not in STATUS_VALUES:
            raise GapInputError("INVALID_NODE_STATUS", f"node {name} has invalid status")
        if node.get("proof_state") not in PROOF_VALUES:
            raise GapInputError("INVALID_PROOF_STATE", f"node {name} has invalid proof_state")
    bundle = report.get("bundle")
    if not isinstance(bundle, dict):
        raise GapInputError("BUNDLE_RESULT_REQUIRED", "verification report has no bundle result")
    evidence_status = bundle.get("evidence_status")
    if evidence_status not in STATUS_VALUES:
        raise GapInputError("INVALID_EVIDENCE_STATUS", "verification bundle evidence_status is invalid")
    target = report.get("target")
    if not isinstance(target, dict):
        raise GapInputError("TARGET_RESULT_REQUIRED", "verification report has no target result")
    return nodes


def node_state(node: Optional[Dict[str, Any]]) -> Tuple[str, bool, bool, str, List[str]]:
    if node is None:
        return "BLOCKED", False, False, "verifier node is absent", []
    status = node["status"]
    proof = node["proof_state"]
    target_proven = status == "CONFIRMED" and proof == "PROVEN"
    offline_proven = status in {"CONFIRMED", "DESIGN"} and proof == "PROVEN"
    if target_proven:
        observed = "CONFIRMED"
    elif status == "BLOCKED":
        observed = "BLOCKED"
    elif status == "UNKNOWN":
        observed = "UNKNOWN"
    elif status == "LIKELY":
        observed = "LIKELY"
    else:
        observed = "DESIGN"
    return observed, target_proven, offline_proven, str(node.get("reason", "")), list(node.get("evidence_sources", []))


def evaluate_requirement(
    requirement: Dict[str, Any],
    nodes: Dict[str, Any],
    source_status: str,
    metadata_match: bool,
    technical_target_provenance_ready: bool,
    physical_identity_proven: bool,
    *,
    legacy_requirements: bool = False,
) -> Dict[str, Any]:
    node_names = requirement["verifier_requirements"]
    observations: List[Dict[str, Any]] = []
    for name in node_names:
        node = nodes.get(name)
        observed, target_proven, offline_proven, reason, sources = node_state(node)
        observations.append(
            {
                "node": name,
                "observed_status": observed,
                "proof_state": node.get("proof_state") if node else "NOT_PROVEN",
                "proven": target_proven,
                "offline_proven": offline_proven,
                "reason": reason,
                "evidence_sources": sources,
            }
        )
    missing = [item for item in observations if not item["proven"]]
    any_blocked = any(item["observed_status"] == "BLOCKED" for item in observations)
    any_unknown = any(item["observed_status"] == "UNKNOWN" for item in observations)
    any_design = any(item["observed_status"] == "DESIGN" for item in observations)
    all_proven_locally = bool(observations) and all(item["offline_proven"] for item in observations)
    nodes_proven = bool(observations) and all(item["proven"] for item in observations)
    if legacy_requirements:
        # Requirements v1 explicitly coupled technical readiness to the
        # ambiguous identity flag. Preserve that old interpretation only when
        # a caller explicitly supplies the old requirements schema.
        target_proven = nodes_proven and source_status == "CONFIRMED" and metadata_match and physical_identity_proven
    elif requirement["id"] == "EV-000C":
        target_proven = nodes_proven and source_status == "CONFIRMED" and physical_identity_proven
    elif requirement["id"] == "EV-000B":
        target_proven = nodes_proven and source_status == "CONFIRMED"
    elif requirement["id"] == "EV-000A":
        # EV-000A is the independently proven target-profile comparison.
        # Source/session attribution is evaluated by EV-000B and aggregate
        # readiness, so it must not downgrade metadata consistency by itself.
        target_proven = nodes_proven and metadata_match
    else:
        target_proven = (
            nodes_proven
            and source_status == "CONFIRMED"
            and metadata_match
            and technical_target_provenance_ready
        )
    if not metadata_match and requirement["id"] in {"EV-000", "EV-000A"}:
        observed_status = "BLOCKED"
        result_class = "BLOCKED"
    elif target_proven:
        observed_status = "CONFIRMED"
        result_class = "PROVEN"
    elif any_blocked or not observations:
        observed_status = "BLOCKED" if requirement["critical"] else "UNKNOWN"
        result_class = "BLOCKED" if requirement["critical"] or any_blocked else "UNPROVEN"
    elif any_unknown:
        observed_status = "UNKNOWN"
        result_class = "UNPROVEN"
    elif any_design:
        observed_status = "DESIGN"
        result_class = "UNPROVEN"
    else:
        observed_status = "LIKELY"
        result_class = "UNPROVEN"
    return {
        "id": requirement["id"],
        "name": requirement.get("name", requirement["id"]),
        "critical": requirement["critical"],
        "evidence_group": requirement["evidence_group"],
        "current_status": requirement["status"],
        "observed_status": observed_status,
        "result": result_class,
        "target_proven": target_proven,
        "offline_nodes_proven": all_proven_locally,
        "verifier_requirements": node_names,
        "observations": observations,
        "evidence_sources": requirement["evidence_sources"],
        "missing": requirement["missing"],
        "closure_conditions": requirement["closure_conditions"],
    }


def verify_gap(report: Dict[str, Any], requirements_document: Dict[str, Any]) -> Dict[str, Any]:
    requirements, groups = validate_requirements(requirements_document)
    nodes = validate_report(report)
    # A valid verifier report may omit nodes whose inputs were unavailable
    # (for example, MMU-dependent nodes when no snapshot was supplied).
    # node_state() treats each absent node as BLOCKED; this is fail-closed and
    # lets the gap report explain missing evidence instead of rejecting it.
    source_status = report["bundle"]["evidence_status"]
    target_result = report["target"]
    metadata_match = require_bool(target_result.get("metadata_match"), "target.metadata_match")
    physical_identity_proven = require_bool(
        target_result.get("physical_identity_proven", target_result.get("identity_proven", False)),
        "target.physical_identity_proven",
    )
    technical_target_provenance_ready = require_bool(
        target_result.get("technical_target_provenance_ready", False),
        "target.technical_target_provenance_ready",
    )
    legacy_requirements = requirements_document.get("schema") == LEGACY_SCHEMA
    results = [
        evaluate_requirement(
            item,
            nodes,
            source_status,
            metadata_match,
            technical_target_provenance_ready,
            physical_identity_proven,
            legacy_requirements=legacy_requirements,
        )
        for item in requirements
    ]
    proven = [item for item in results if item["target_proven"]]
    blocked = [item for item in results if item["observed_status"] == "BLOCKED"]
    unknown = [item for item in results if item["observed_status"] == "UNKNOWN"]
    unproven = [item for item in results if not item["target_proven"] and item not in blocked and item not in unknown]
    artifacts = report.get("artifacts", {})
    missing_artifacts: List[str] = []
    if isinstance(artifacts, dict):
        for name, artifact in artifacts.items():
            if not isinstance(artifact, dict) or artifact.get("proof_state") != "PROVEN":
                missing_artifacts.append(name)
    group_map: Dict[str, List[Dict[str, Any]]] = {group: [] for group in sorted(groups)}
    for item in results:
        if not item["target_proven"]:
            group_map.setdefault(item["evidence_group"], []).append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "critical": item["critical"],
                    "observed_status": item["observed_status"],
                    "missing": item["missing"],
                    "closure_conditions": item["closure_conditions"],
                }
            )
    pipeline_ready = REQUIRED_GROUPS.issubset(groups) and metadata_match
    return {
        "ok": True,
        "schema": SCHEMA,
        "verification_source_status": source_status,
        "target_metadata_match": metadata_match,
        "target_metadata_status": target_result.get("metadata_status", "UNKNOWN"),
        "same_session_provenance_status": target_result.get("same_session_provenance_status", "UNKNOWN"),
        "physical_identity_status": target_result.get("physical_identity_status", "NOT_PROVEN"),
        "technical_target_provenance_ready": technical_target_provenance_ready,
        "physical_identity_proven": physical_identity_proven,
        "target_identity_proven": physical_identity_proven,
        "proven_requirements": [item["id"] for item in proven],
        "offline_proven_requirements": [item["id"] for item in results if item["offline_nodes_proven"]],
        "unproven_requirements": [item["id"] for item in unproven],
        "blocked_requirements": [item["id"] for item in blocked],
        "unknown_requirements": [item["id"] for item in unknown],
        "requirements": results,
        "missing_artifacts": sorted(missing_artifacts),
        "minimum_next_evidence_set": {
            "groups": group_map,
            "required_groups": sorted(REQUIRED_GROUPS),
        },
        "evidence_pipeline_ready": pipeline_ready,
        "hardware_status": {
            "offline_infrastructure": "COMPLETE" if pipeline_ready else "BLOCKED",
            "evidence_pipeline_ready": "YES" if pipeline_ready else "NO",
            "loader_contract": "BLOCKED",
            "first_hardware_execution": "NOT READY",
            "reason": "offline mapping/provenance evidence is not target hardware readiness",
        },
    }


def human_report(result: Dict[str, Any]) -> str:
    requirements = result["requirements"]
    proven = len(result["proven_requirements"])
    blocked = len(result["blocked_requirements"])
    unknown = len(result["unknown_requirements"])
    unproven = len(result["unproven_requirements"])
    lines = [
        "DreyzeOS T8006 Evidence Gap",
        "",
        f"Requirements ................ {len(requirements)}",
        f"Target metadata match ....... {'YES' if result['target_metadata_match'] else 'NO'}",
        f"TARGET_METADATA_STATUS = {result['target_metadata_status']}",
        f"SAME_SESSION_PROVENANCE_STATUS = {result['same_session_provenance_status']}",
        f"PHYSICAL_IDENTITY_STATUS = {result['physical_identity_status']}",
        f"TECHNICAL_TARGET_PROVENANCE_READY = {str(result['technical_target_provenance_ready']).lower()}",
        f"Target-proven requirements . {proven}",
        f"Unproven requirements ....... {unproven}",
        f"Unknown requirements ........ {unknown}",
        f"Blocked requirements ........ {blocked}",
        f"Missing artifacts ........... {', '.join(result['missing_artifacts']) or 'none reported'}",
        "",
        "Minimum next evidence groups:",
    ]
    for group, items in result["minimum_next_evidence_set"]["groups"].items():
        if items:
            lines.append(f"  {group}: " + ", ".join(item["id"] for item in items))
    lines.extend(
        [
            "",
            "OFFLINE INFRASTRUCTURE = " + result["hardware_status"]["offline_infrastructure"],
            "EVIDENCE PIPELINE READY = " + result["hardware_status"]["evidence_pipeline_ready"],
            "LOADER CONTRACT = BLOCKED",
            "FIRST HARDWARE EXECUTION = NOT READY",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze T8006 runtime evidence gaps offline")
    parser.add_argument("--verification", required=True, type=Path, help="Step 2.11 verifier JSON report")
    parser.add_argument("--requirements", required=True, type=Path, help="Step 2.12 requirements JSON")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--human", action="store_true", help="emit concise human-readable report")
    parser.add_argument("--strict", action="store_true", help="return 1 when any target requirement is not proven")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = load_json(args.verification, "verification report")
        requirements = load_json(args.requirements, "requirements document")
        result = verify_gap(report, requirements)
    except GapInputError as exc:
        output = {"ok": False, "tool_error": exc.code, "error": exc.message}
        print(json.dumps(output, indent=2, sort_keys=True) if not args.human else f"ERROR {exc.code}: {exc.message}")
        return 1
    if args.human and not args.json:
        print(human_report(result))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    if args.strict and (result["blocked_requirements"] or result["unknown_requirements"] or result["unproven_requirements"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

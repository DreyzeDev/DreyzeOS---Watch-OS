#!/usr/bin/env python3
"""Unit tests for the offline Step 2.12 evidence-gap tool."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.t8006_evidence_gap import (
    GapInputError,
    human_report,
    load_json,
    main,
    verify_gap,
)


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = ROOT / "research" / "t8006_evidence" / "requirements.json"


def requirements_document() -> dict:
    return json.loads(REQUIREMENTS_PATH.read_text(encoding="utf-8"))


def synthetic_report(status: str = "DESIGN", identity: bool = False, technical: bool | None = None) -> dict:
    document = requirements_document()
    node_names = {
        name
        for item in document["requirements"]
        for name in item["verifier_requirements"]
    }
    nodes = {
        name: {
            "status": status,
            "proof_state": "PROVEN",
            "reason": "repository-owned synthetic evidence fixture",
            "evidence_sources": [f"synthetic:{name}"],
            "depends_on": [],
            "critical": True,
        }
        for name in node_names
    }
    if not identity and "physical_identity_provenance" in nodes:
        nodes["physical_identity_provenance"].update(
            status="UNKNOWN", proof_state="NOT_PROVEN", reason="physical identity intentionally absent"
        )
    if technical is None:
        technical = status == "CONFIRMED"
    return {
        "ok": True,
        "schema": "dreyzeos.handoff_evidence.v1",
        "bundle": {"evidence_status": status},
        "target": {
            "metadata_match": True,
            "metadata_status": "CONFIRMED" if status == "CONFIRMED" else status,
            "same_session_provenance_status": "CONFIRMED" if status == "CONFIRMED" else status,
            "physical_identity_status": "CONFIRMED" if identity else "NOT_PROVEN",
            "physical_identity_proven": identity,
            "identity_proven": identity,
            "technical_target_provenance_ready": technical,
        },
        "artifacts": {
            "image": {"status": status, "proof_state": "PROVEN"},
            "mmu_snapshot": {"status": status, "proof_state": "PROVEN"},
            "handoff_descriptor": {"status": status, "proof_state": "PROVEN"},
        },
        "evidence_graph": {"nodes": nodes},
    }


class T8006EvidenceGapTests(unittest.TestCase):
    def test_unknown_global_source_does_not_demote_proven_metadata(self) -> None:
        report = synthetic_report(status="UNKNOWN", technical=False)
        report["evidence_graph"]["nodes"]["target_metadata_provenance"].update(
            status="CONFIRMED", proof_state="PROVEN"
        )

        result = verify_gap(report, requirements_document())
        metadata = next(item for item in result["requirements"] if item["id"] == "EV-000A")

        self.assertEqual(metadata["observed_status"], "CONFIRMED")
        self.assertTrue(metadata["target_proven"])

    def test_proven_a_with_blocked_b_keeps_ev000_blocked(self) -> None:
        report = synthetic_report(status="CONFIRMED", technical=False)
        nodes = report["evidence_graph"]["nodes"]
        nodes["same_session_provenance"].update(
            status="BLOCKED", proof_state="NOT_PROVEN"
        )
        nodes["target_provenance"].update(
            status="BLOCKED", proof_state="NOT_PROVEN"
        )

        result = verify_gap(report, requirements_document())
        by_id = {item["id"]: item for item in result["requirements"]}

        self.assertTrue(by_id["EV-000A"]["target_proven"])
        self.assertEqual(by_id["EV-000B"]["observed_status"], "BLOCKED")
        self.assertFalse(by_id["EV-000"]["target_proven"])
        self.assertEqual(by_id["EV-000"]["observed_status"], "BLOCKED")

    def test_unknown_ev000c_does_not_block_a_plus_b_provenance(self) -> None:
        report = synthetic_report(status="CONFIRMED", identity=False, technical=True)
        result = verify_gap(report, requirements_document())
        by_id = {item["id"]: item for item in result["requirements"]}

        self.assertTrue(by_id["EV-000A"]["target_proven"])
        self.assertTrue(by_id["EV-000B"]["target_proven"])
        self.assertTrue(by_id["EV-000"]["target_proven"])
        self.assertFalse(by_id["EV-000C"]["target_proven"])

    def test_all_requirements_missing_are_fail_closed(self) -> None:
        report = synthetic_report()
        report["evidence_graph"]["nodes"] = {}
        result = verify_gap(report, requirements_document())
        self.assertEqual(result["proven_requirements"], [])
        self.assertIn("EV-000", result["blocked_requirements"])
        self.assertIn("EV-002", result["blocked_requirements"])
        self.assertIn("EV-015", result["unknown_requirements"])
        self.assertEqual(result["hardware_status"]["loader_contract"], "BLOCKED")

    def test_partial_confirmed_report_identifies_exact_missing_node(self) -> None:
        report = synthetic_report(status="CONFIRMED", identity=True)
        report["evidence_graph"]["nodes"]["payload_pa_proven"]["status"] = "BLOCKED"
        result = verify_gap(report, requirements_document())
        self.assertNotIn("EV-000", result["blocked_requirements"])
        self.assertIn("EV-003", result["blocked_requirements"])
        requirement = next(item for item in result["requirements"] if item["id"] == "EV-003")
        self.assertEqual(requirement["observations"][0]["node"], "payload_pa_proven")
        self.assertFalse(requirement["target_proven"])

    def test_requirement_reference_absent_from_nonempty_graph_is_blocked(self) -> None:
        report = synthetic_report()
        document = requirements_document()
        document["requirements"][0]["verifier_requirements"] = ["phantom_node"]
        result = verify_gap(report, document)
        requirement = result["requirements"][0]
        self.assertEqual(requirement["observed_status"], "BLOCKED")
        self.assertEqual(requirement["observations"][0]["node"], "phantom_node")
        self.assertEqual(requirement["observations"][0]["reason"], "verifier node is absent")

    def test_partial_verifier_graph_reports_absent_mmu_nodes_as_blockers(self) -> None:
        report = synthetic_report(status="UNKNOWN")
        nodes = report["evidence_graph"]["nodes"]
        for name in ("mmu_register_provenance", "mmu_snapshot_target_match", "payload_translation_consistency"):
            nodes.pop(name)

        result = verify_gap(report, requirements_document())
        by_id = {item["id"]: item for item in result["requirements"]}
        for identifier in ("EV-009", "EV-021", "EV-024"):
            self.assertEqual(by_id[identifier]["observed_status"], "BLOCKED")
            missing = [item for item in by_id[identifier]["observations"] if item["reason"] == "verifier node is absent"]
            self.assertTrue(missing, identifier)

    def test_synthetic_full_model_is_not_hardware_proof(self) -> None:
        result = verify_gap(synthetic_report(), requirements_document())
        self.assertEqual(result["offline_proven_requirements"], [
            item["id"] for item in requirements_document()["requirements"]
            if item["verifier_requirements"] and item["id"] != "EV-000C"
        ])
        self.assertEqual(result["proven_requirements"], [])
        self.assertEqual(result["hardware_status"]["offline_infrastructure"], "COMPLETE")
        self.assertEqual(result["hardware_status"]["evidence_pipeline_ready"], "YES")
        self.assertEqual(result["hardware_status"]["first_hardware_execution"], "NOT READY")

    def test_critical_blocker_is_separated_from_design_warning(self) -> None:
        report = synthetic_report(status="DESIGN")
        report["evidence_graph"]["nodes"]["runtime_memory_provenance"]["status"] = "BLOCKED"
        result = verify_gap(report, requirements_document())
        self.assertTrue(result["blocked_requirements"])
        self.assertIn("EV-000", result["unproven_requirements"])
        self.assertTrue(any(item["critical"] for item in result["requirements"]))

    def test_noncritical_missing_mapping_is_unknown_not_hardware_blocker(self) -> None:
        report = synthetic_report(status="CONFIRMED", identity=True)
        result = verify_gap(report, requirements_document())
        self.assertIn("EV-015", result["unknown_requirements"])
        self.assertNotIn("EV-015", result["blocked_requirements"])
        self.assertEqual(result["hardware_status"]["loader_contract"], "BLOCKED")

    def test_unknown_node_is_reported_with_missing_reason(self) -> None:
        report = synthetic_report(status="CONFIRMED", identity=True)
        report["evidence_graph"]["nodes"]["runtime_memory_provenance"]["status"] = "UNKNOWN"
        result = verify_gap(report, requirements_document())
        item = next(item for item in result["requirements"] if item["id"] == "EV-002")
        self.assertEqual(item["observed_status"], "UNKNOWN")
        self.assertFalse(item["target_proven"])
        self.assertTrue(item["observations"][0]["reason"])

    def test_malformed_requirements_schema_is_rejected(self) -> None:
        document = requirements_document()
        document["schema"] = "wrong.schema"
        with self.assertRaises(GapInputError) as context:
            verify_gap(synthetic_report(), document)
        self.assertEqual(context.exception.code, "SCHEMA_MISMATCH")

    def test_foreign_requirements_target_is_rejected(self) -> None:
        document = requirements_document()
        document["target"]["model"] = "Watch4,1"
        with self.assertRaises(GapInputError) as context:
            verify_gap(synthetic_report(), document)
        self.assertEqual(context.exception.code, "REQUIREMENTS_TARGET_MISMATCH")

    def test_malformed_verifier_result_is_rejected(self) -> None:
        report = synthetic_report()
        del report["evidence_graph"]["nodes"]
        with self.assertRaises(GapInputError) as context:
            verify_gap(report, requirements_document())
        self.assertEqual(context.exception.code, "NODES_REQUIRED")

    def test_duplicate_requirement_ids_are_rejected(self) -> None:
        document = requirements_document()
        document["requirements"].append(copy.deepcopy(document["requirements"][0]))
        with self.assertRaises(GapInputError) as context:
            verify_gap(synthetic_report(), document)
        self.assertEqual(context.exception.code, "DUPLICATE_REQUIREMENT_ID")

    def test_missing_closure_condition_is_rejected(self) -> None:
        document = requirements_document()
        document["requirements"][0]["closure_conditions"] = []
        with self.assertRaises(GapInputError) as context:
            verify_gap(synthetic_report(), document)
        self.assertEqual(context.exception.code, "CLOSURE_CONDITIONS_REQUIRED")

    def test_synthetic_ready_never_sets_identity_or_hardware_ready(self) -> None:
        report = synthetic_report(status="DESIGN", identity=False)
        result = verify_gap(report, requirements_document())
        self.assertFalse(result["target_identity_proven"])
        self.assertEqual(result["hardware_status"]["loader_contract"], "BLOCKED")
        self.assertEqual(result["hardware_status"]["first_hardware_execution"], "NOT READY")

    def test_physical_identity_missing_does_not_block_technical_a_plus_b(self) -> None:
        report = synthetic_report(status="CONFIRMED", identity=False, technical=True)
        result = verify_gap(report, requirements_document())
        by_id = {item["id"]: item for item in result["requirements"]}
        self.assertTrue(by_id["EV-000A"]["target_proven"])
        self.assertTrue(by_id["EV-000B"]["target_proven"])
        self.assertFalse(by_id["EV-000C"]["target_proven"])
        self.assertTrue(by_id["EV-000"]["target_proven"])
        self.assertTrue(result["technical_target_provenance_ready"])
        self.assertFalse(result["physical_identity_proven"])
        self.assertNotIn("EV-000C", result["blocked_requirements"])

    def test_a_satisfied_b_missing_c_missing_blocks_aggregate_only(self) -> None:
        report = synthetic_report(status="CONFIRMED", identity=False, technical=False)
        nodes = report["evidence_graph"]["nodes"]
        nodes["same_session_provenance"].update(
            status="BLOCKED", proof_state="NOT_PROVEN", reason="session binding absent"
        )
        result = verify_gap(report, requirements_document())
        by_id = {item["id"]: item for item in result["requirements"]}
        self.assertTrue(by_id["EV-000A"]["target_proven"])
        self.assertFalse(by_id["EV-000B"]["target_proven"])
        self.assertFalse(by_id["EV-000C"]["target_proven"])
        self.assertFalse(by_id["EV-000"]["target_proven"])
        self.assertIn("EV-000B", result["blocked_requirements"])
        self.assertNotIn("EV-000C", result["blocked_requirements"])

    def test_physical_identity_does_not_compensate_for_missing_a_or_b(self) -> None:
        report = synthetic_report(status="CONFIRMED", identity=True, technical=False)
        nodes = report["evidence_graph"]["nodes"]
        nodes["target_metadata_provenance"].update(status="BLOCKED", proof_state="NOT_PROVEN")
        nodes["same_session_provenance"].update(status="BLOCKED", proof_state="NOT_PROVEN")
        result = verify_gap(report, requirements_document())
        by_id = {item["id"]: item for item in result["requirements"]}
        self.assertTrue(by_id["EV-000C"]["target_proven"])
        self.assertFalse(by_id["EV-000A"]["target_proven"])
        self.assertFalse(by_id["EV-000B"]["target_proven"])
        self.assertFalse(by_id["EV-000"]["target_proven"])
        self.assertFalse(result["technical_target_provenance_ready"])

    def test_requirements_v1_keeps_legacy_identity_gate(self) -> None:
        document = requirements_document()
        document["schema"] = "dreyzeos.t8006_evidence_requirements.v1"
        document["requirements"] = [item for item in document["requirements"] if item["id"] not in {"EV-000A", "EV-000B", "EV-000C"}]
        report = synthetic_report(status="CONFIRMED", identity=False, technical=True)
        result = verify_gap(report, document)
        self.assertNotIn("EV-000", result["proven_requirements"])
        requirement = next(item for item in result["requirements"] if item["id"] == "EV-000")
        self.assertFalse(requirement["target_proven"])

    def test_incomplete_reserved_list_is_an_exact_blocker(self) -> None:
        report = synthetic_report(status="CONFIRMED", identity=True)
        report["evidence_graph"]["nodes"]["reserved_memory_completeness"]["status"] = "BLOCKED"
        result = verify_gap(report, requirements_document())
        self.assertIn("EV-017", result["blocked_requirements"])
        self.assertIn("EV-018", result["blocked_requirements"])

    def test_human_output_keeps_readiness_lines_explicit(self) -> None:
        output = human_report(verify_gap(synthetic_report(), requirements_document()))
        self.assertIn("DreyzeOS T8006 Evidence Gap", output)
        self.assertIn("OFFLINE INFRASTRUCTURE = COMPLETE", output)
        self.assertIn("EVIDENCE PIPELINE READY = YES", output)
        self.assertIn("LOADER CONTRACT = BLOCKED", output)
        self.assertIn("FIRST HARDWARE EXECUTION = NOT READY", output)

    def test_cli_returns_zero_for_blocked_report_by_default(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dreyzeos-gap-") as directory:
            root = Path(directory)
            report_path = root / "report.json"
            req_path = root / "requirements.json"
            report_path.write_text(json.dumps(synthetic_report()), encoding="utf-8")
            req_path.write_text(json.dumps(requirements_document()), encoding="utf-8")
            self.assertEqual(
                main(["--verification", str(report_path), "--requirements", str(req_path), "--json"]),
                0,
            )

    def test_cli_strict_returns_one_for_unproven_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="dreyzeos-gap-") as directory:
            root = Path(directory)
            report_path = root / "report.json"
            req_path = root / "requirements.json"
            report_path.write_text(json.dumps(synthetic_report()), encoding="utf-8")
            req_path.write_text(json.dumps(requirements_document()), encoding="utf-8")
            self.assertEqual(
                main(["--verification", str(report_path), "--requirements", str(req_path), "--strict", "--json"]),
                1,
            )

    def test_target_mismatch_does_not_disappear_inside_group_result(self) -> None:
        report = synthetic_report(status="CONFIRMED", identity=True)
        report["target"]["metadata_match"] = False
        result = verify_gap(report, requirements_document())
        self.assertFalse(result["target_metadata_match"])
        self.assertIn("EV-000", result["blocked_requirements"])

    def test_missing_artifact_is_preserved_in_machine_report(self) -> None:
        report = synthetic_report()
        report["artifacts"]["mmu_snapshot"]["proof_state"] = "NOT_PROVEN"
        result = verify_gap(report, requirements_document())
        self.assertEqual(result["missing_artifacts"], ["mmu_snapshot"])


if __name__ == "__main__":
    unittest.main()

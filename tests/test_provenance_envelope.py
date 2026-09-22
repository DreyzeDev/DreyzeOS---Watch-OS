"""Host-only tests for target provenance-envelope preparation and validation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "research" / "handoff_evidence" / "fixtures" / "provenance"
sys.path.insert(0, str(ROOT / "tools"))

from provenance_envelope import validate_envelope  # noqa: E402


EXPECTED_TARGET = {
    "model": "Watch4,2",
    "board": {"n131bap"},
    "soc": "T8006",
    "firmware": "watchOS 10.6.1",
    "build": "21U580",
    "architecture": "aarch64",
}


def set_path(root: Any, path: str, value: Any, *, append: bool = False) -> None:
    tokens = re.findall(r"[^.\[\]]+|\[\d+\]", path)
    current = root
    for token in tokens[:-1]:
        current = current[int(token[1:-1])] if token.startswith("[") else current[token]
    last = tokens[-1]
    if append:
        target = current[int(last[1:-1])] if last.startswith("[") else current[last]
        target.append(value)
    elif last.startswith("["):
        current[int(last[1:-1])] = value
    else:
        current[last] = value


class ProvenanceEnvelopeTests(unittest.TestCase):
    def load_base(self) -> Dict[str, Any]:
        return json.loads((FIXTURES / "synthetic_complete.json").read_text(encoding="utf-8"))

    def validate(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        return validate_envelope(envelope, FIXTURES, EXPECTED_TARGET)

    def apply_case(self, case_name: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
        case = json.loads((FIXTURES / f"blocked_{case_name}.json").read_text(encoding="utf-8"))
        envelope = self.load_base()
        for operation in case["operations"]:
            set_path(
                envelope,
                operation["path"],
                operation["value"],
                append=operation["op"] == "append",
            )
        return case, self.validate(envelope)

    def test_synthetic_complete_envelope_is_design_not_identity(self) -> None:
        report = self.validate(self.load_base())
        self.assertEqual(report["status"], "DESIGN")
        self.assertTrue(report["target"]["metadata_match"])
        self.assertFalse(report["target"]["identity_proven"])
        self.assertTrue(report["coverage"]["coverage_complete_claimed_and_consistent"])
        self.assertTrue(all(item["artifact_present"] for item in report["artifacts"].values()))
        self.assertTrue(all(item["artifact_hash_verified"] for item in report["artifacts"].values()))
        self.assertTrue(all(not item["artifact_target_bound"] for item in report["artifacts"].values()))
        self.assertEqual(report["requirements"]["EV-000"]["proof_state"], "NOT_PROVEN")
        self.assertEqual(report["requirements"]["EV-027"]["proof_state"], "NOT_PROVEN")
        self.assertEqual(report["hardware_readiness_effect"], "NONE")

    def test_missing_target_binding_fixture(self) -> None:
        case, report = self.apply_case("missing_target_binding")
        self.assertEqual(report["requirements"][case["expected_requirement"]]["proof_state"], case["expected_proof_state"])
        self.assertIn(case["expected_blocker"], report["blockers"])
        self.assertFalse(any(report["artifacts"][name]["artifact_target_bound"] for name in ("image", "handoff_descriptor", "mmu_snapshot")))
        self.assertFalse(report["target"]["identity_proven"])

    def test_missing_hash_fixture(self) -> None:
        case, report = self.apply_case("missing_hash")
        self.assertEqual(report["requirements"][case["expected_requirement"]]["proof_state"], case["expected_proof_state"])
        self.assertIn(case["expected_blocker"], report["errors"])
        self.assertTrue(report["artifacts"]["image"]["sha256_actual"])
        self.assertFalse(report["artifacts"]["image"]["artifact_hash_verified"])

    def test_mismatched_hash_fixture(self) -> None:
        case, report = self.apply_case("mismatched_hash")
        self.assertEqual(report["requirements"][case["expected_requirement"]]["proof_state"], case["expected_proof_state"])
        self.assertTrue(any(item["code"] == case["expected_blocker"] for item in report["conflicts"]))

    def test_incomplete_coverage_fixture(self) -> None:
        case, report = self.apply_case("incomplete_coverage")
        self.assertEqual(report["requirements"][case["expected_requirement"]]["proof_state"], case["expected_proof_state"])
        self.assertIn(case["expected_blocker"], report["blockers"])
        self.assertFalse(report["coverage"]["coverage_complete_claimed_and_consistent"])

    def test_metadata_mismatch_fixture(self) -> None:
        case, report = self.apply_case("metadata_mismatch")
        self.assertEqual(report["requirements"][case["expected_requirement"]]["proof_state"], case["expected_proof_state"])
        self.assertIn(case["expected_blocker"], report["errors"])
        self.assertFalse(report["target"]["metadata_match"])

    def test_conflicting_proven_target_facts_fixture(self) -> None:
        case, report = self.apply_case("conflicting_proven_facts")
        self.assertEqual(report["requirements"][case["expected_requirement"]]["proof_state"], case["expected_proof_state"])
        self.assertTrue(any(item["code"] == case["expected_blocker"] for item in report["conflicts"]))

    def test_invalid_relative_path_fails_closed(self) -> None:
        envelope = self.load_base()
        envelope["artifacts"][0]["path"] = "../../escape"
        report = self.validate(envelope)
        self.assertIn("ARTIFACT_PATH_INVALID", report["errors"])
        self.assertEqual(report["requirements"]["EV-000"]["proof_state"], "NOT_PROVEN")

    def test_boolean_string_is_not_accepted_as_fact(self) -> None:
        envelope = self.load_base()
        envelope["target"]["identity_proven"]["value"] = "false"
        report = self.validate(envelope)
        self.assertIn("IDENTITY_PROOF_FACT_INVALID", report["errors"])

    def test_noncanonical_capture_uuid_is_rejected(self) -> None:
        envelope = self.load_base()
        envelope["capture"]["capture_id"]["value"] = "ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF"
        report = self.validate(envelope)
        self.assertIn("CAPTURE_ID_INVALID", report["errors"])

    def test_unknown_or_non_utc_timestamp_is_rejected(self) -> None:
        for timestamp in ("2026-01-01 00:00:00+00:00", "2026-01-01T00:00:00-00:00"):
            with self.subTest(timestamp=timestamp):
                envelope = self.load_base()
                envelope["capture"]["started_at_utc"]["value"] = timestamp
                report = self.validate(envelope)
                self.assertIn("STARTED_AT_UTC_INVALID", report["errors"])

    def test_malformed_metadata_match_does_not_crash(self) -> None:
        envelope = self.load_base()
        envelope["target"]["metadata_match"] = None
        report = self.validate(envelope)
        self.assertIn("METADATA_MATCH_FACT_INVALID", report["errors"])
        self.assertEqual(report["requirements"]["EV-000"]["proof_state"], "NOT_PROVEN")

    def test_template_keeps_absence_unknown(self) -> None:
        template_path = ROOT / "research" / "handoff_evidence" / "provenance_envelope.template.json"
        template = json.loads(template_path.read_text(encoding="utf-8"))
        report = validate_envelope(template, template_path.parent, EXPECTED_TARGET)
        self.assertFalse(template["target"]["identity_proven"]["value"])
        self.assertFalse(template["target"]["identity_proven"]["value_proven"])
        self.assertFalse(template["capture"]["capture_id"]["value_present"])
        self.assertTrue(all(item["path"] is None for item in template["artifacts"]))
        self.assertFalse(template["coverage"]["coverage_complete"]["value_proven"])
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertEqual(report["errors"], [])
        self.assertNotIn("ARTIFACT_RUNTIME_PROVEN_FACT_INVALID", report["errors"])
        self.assertEqual(report["requirements"]["EV-000"]["proof_state"], "NOT_PROVEN")

    def test_existing_verifier_cli_provenance_mode_exit_semantics(self) -> None:
        tool = ROOT / "tools" / "handoff_evidence_verifier.py"
        fixture = FIXTURES / "synthetic_complete.json"
        normal = subprocess.run(
            [sys.executable, str(tool), "--provenance-envelope", str(fixture), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(normal.returncode, 0, normal.stderr)
        decoded = json.loads(normal.stdout)
        self.assertEqual(decoded["requirements"]["EV-000"]["proof_state"], "NOT_PROVEN")
        strict = subprocess.run(
            [sys.executable, str(tool), "--provenance-envelope", str(fixture), "--human", "--strict"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(strict.returncode, 1)
        self.assertIn("FIRST HARDWARE EXECUTION = NOT READY", strict.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

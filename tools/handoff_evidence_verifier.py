#!/usr/bin/env python3
"""
DreyzeOS unified offline handoff evidence verifier.

This is a host-only orchestration layer.  It reads a local evidence bundle,
reuses the Step 2.10 MMU analyzer, validates the fixed Loader Handoff ABI V1
prefix, and emits a dependency/provenance report.  It never opens device
memory, follows evidence-provided pointers, executes a payload, writes MMIO,
or transfers control.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from mmu_snapshot_analyzer import (
        Snapshot,
        SnapshotError,
        ElfImage,
        analyze_elf,
        analyze_range,
    )
    from provenance_envelope import validate_envelope
except ModuleNotFoundError:  # pragma: no cover - used when imported from tests
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mmu_snapshot_analyzer import (
        Snapshot,
        SnapshotError,
        ElfImage,
        analyze_elf,
        analyze_range,
    )
    from provenance_envelope import validate_envelope


U64_MAX = (1 << 64) - 1
U64_LIMIT = 1 << 64
SCHEMA = "dreyzeos.handoff_evidence.v1"
ABI_SIZE = 128
ABI_MAGIC = 0x4452595A454F5348
ABI_VERSION = 1
RANGE_READABLE = 1
FLAG_VERIFIED = 1 << 0
FLAG_ENTRY_EL_KNOWN = 1 << 1
FLAG_PAYLOAD_LOCATION_KNOWN = 1 << 2
FLAG_MMU_STATE_KNOWN = 1 << 3
FLAG_MMIO_MAPPING_VALID = 1 << 4
FLAG_UART_MAPPING_VALID = 1 << 5
FLAG_AIC_MAPPING_VALID = 1 << 6
FLAG_MAPPING_STATE_KNOWN = 1 << 7
KNOWN_FLAGS = (
    FLAG_VERIFIED
    | FLAG_ENTRY_EL_KNOWN
    | FLAG_PAYLOAD_LOCATION_KNOWN
    | FLAG_MMU_STATE_KNOWN
    | FLAG_MMIO_MAPPING_VALID
    | FLAG_UART_MAPPING_VALID
    | FLAG_AIC_MAPPING_VALID
    | FLAG_MAPPING_STATE_KNOWN
)
STATUS_VALUES = {"CONFIRMED", "LIKELY", "DESIGN", "UNKNOWN", "BLOCKED"}
PROOF_VALUES = {"PRESENT", "PROVEN", "NOT_PROVEN", "NOT_APPLICABLE"}
EXPECTED_TARGET = {
    "model": "Watch4,2",
    "board": {"n131bap"},
    "soc": "T8006",
    "firmware": "watchOS 10.6.1",
    "build": "21U580",
    "architecture": "aarch64",
}
REQUIRED_SNAPSHOT_REGISTERS = (
    "sctlr_el1",
    "tcr_el1",
    "ttbr0_el1",
    "ttbr1_el1",
    "mair_el1",
)
CRITICAL_ORDER = (
    "bundle_integrity",
    "artifact_aliases",
    "target_metadata_match",
    "target_metadata_provenance",
    "same_session_provenance",
    "mmu_snapshot_target_match",
    "image_integrity",
    "image_shape",
    "descriptor_structure",
    "descriptor_root_of_trust",
    "entry_el1",
    "initial_sp",
    "daif_normalized",
    "cpu_consistency",
    "translation_policy",
    "cache_policy",
    "stage0_executable_mapping",
    "entry_executable_mapping",
    "kernel_executable_mapping",
    "kernel_readable_mapping",
    "kernel_writable_mapping",
    "stack_mapping",
    "payload_pa_proven",
    "payload_va_proven",
    "payload_size_bound",
    "payload_translation_consistency",
    "runtime_memory_provenance",
    "payload_ownership",
    "framebuffer_reservation",
    "reserved_memory_completeness",
    "range_definition_integrity",
    "collision_audit",
    "control_transfer",
    "no_persistent_write",
)


class VerificationInputError(Exception):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "ok": False,
            "tool_error": self.code,
            "error": self.message,
        }
        result.update(self.details)
        return result


def parse_u64(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise VerificationInputError("INVALID_VALUE", f"{name} must be unsigned")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value.strip(), 0)
        except ValueError as exc:
            raise VerificationInputError(
                "INVALID_VALUE", f"{name} is not an integer"
            ) from exc
    else:
        raise VerificationInputError("INVALID_VALUE", f"{name} is not an integer")
    if parsed < 0 or parsed > U64_MAX:
        raise VerificationInputError(
            "ADDRESS_OUT_OF_RANGE", f"{name} is outside uint64", value=parsed
        )
    return parsed


def checked_add_local(base: int, length: int, name: str) -> int:
    if base < 0 or length < 0 or base > U64_MAX or length > U64_MAX:
        raise VerificationInputError("ADDRESS_OUT_OF_RANGE", f"{name} operand invalid")
    result = base + length
    if result > U64_LIMIT:
        raise VerificationInputError("UINT64_OVERFLOW", f"{name} wraps uint64")
    return result


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def valid_hash(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def safe_bundle_path(root: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise VerificationInputError("PATH_INVALID", f"{field} must be a relative path")
    if value.startswith(("/", "\\")) or (len(value) > 1 and value[1] == ":"):
        raise VerificationInputError("PATH_TRAVERSAL", f"{field} must be relative")
    candidate = (root / Path(value)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise VerificationInputError(
            "PATH_TRAVERSAL", f"{field} escapes the bundle directory"
        ) from exc
    return candidate


def source_status(root: Dict[str, Any]) -> str:
    source = root.get("source", {})
    status = source.get("evidence_status") if isinstance(source, dict) else None
    return status if status in STATUS_VALUES else "UNKNOWN"


def status_for_evidence(evidence: str) -> str:
    if evidence in STATUS_VALUES:
        return evidence
    return "UNKNOWN"


def strict_bool(raw: Dict[str, Any], key: str, default: bool, name: str) -> Optional[bool]:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        return None
    return value


def normalize_board(value: Any) -> set[str]:
    values = value if isinstance(value, list) else [value]
    return {str(item).lower() for item in values if item is not None}


def present_fact(raw: Any, name: str) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "value": None,
            "value_present": False,
            "value_proven": False,
            "source": name,
        }
    present = strict_bool(raw, "value_present", "value" in raw, f"{name}.value_present")
    proven = strict_bool(raw, "value_proven", False, f"{name}.value_proven")
    value: Optional[int] = None
    error: Optional[str] = None
    if present is None or proven is None:
        error = "BOOLEAN_REQUIRED"
        present = present is True
        proven = False
    if present and "value" in raw:
        try:
            value = parse_u64(raw["value"], name)
        except VerificationInputError as exc:
            error = exc.code
    elif present:
        error = "VALUE_MISSING"
    return {
        "value": value,
        "value_present": present,
        "value_proven": bool(proven) and present is True and error is None,
        "source": name,
        "error": error,
    }


def bool_fact(raw: Any, name: str) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "value": None,
            "value_present": False,
            "value_proven": False,
            "source": name,
        }
    present = strict_bool(raw, "value_present", "value" in raw, f"{name}.value_present")
    proven = strict_bool(raw, "value_proven", False, f"{name}.value_proven")
    value = raw.get("value")
    if present is None or proven is None:
        return {
            "value": None,
            "value_present": present is True,
            "value_proven": False,
            "source": name,
            "error": "BOOLEAN_REQUIRED",
        }
    if present and not isinstance(value, bool):
        return {
            "value": None,
            "value_present": True,
            "value_proven": False,
            "source": name,
            "error": "BOOLEAN_REQUIRED",
        }
    return {
        "value": value if present else None,
        "value_present": present,
        "value_proven": proven and present is True,
        "source": name,
    }


def range_fact(raw: Any, name: str, default_space: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "name": name,
            "present": False,
            "bounds_proven": False,
            "ownership_proven": False,
            "valid": False,
            "reason": "range not supplied",
        }
    try:
        base = parse_u64(raw.get("base", raw.get("physical_base")), f"{name}.base")
        length = parse_u64(raw.get("length", raw.get("size")), f"{name}.length")
    except VerificationInputError as exc:
        return {
            "name": name,
            "present": raw.get("present", True) is True,
            "bounds_proven": False,
            "ownership_proven": False,
            "valid": False,
            "reason": exc.code,
        }
    address_space = raw.get("address_space", default_space)
    present = strict_bool(raw, "present", True, f"{name}.present")
    bounds_proven = strict_bool(
        raw, "bounds_proven", raw.get("proven", False), f"{name}.bounds_proven"
    )
    ownership_proven = strict_bool(raw, "ownership_proven", False, f"{name}.ownership_proven")
    readable = strict_bool(raw, "readable", False, f"{name}.readable")
    writable = strict_bool(raw, "writable", False, f"{name}.writable")
    executable = strict_bool(raw, "executable", False, f"{name}.executable")
    mapping_proven = strict_bool(raw, "mapping_proven", False, f"{name}.mapping_proven")
    if any(value is None for value in (
        present, bounds_proven, ownership_proven, readable, writable,
        executable, mapping_proven,
    )):
        return {
            "name": str(raw.get("name", name)),
            "base": base,
            "length": length,
            "end": None,
            "address_space": address_space,
            "present": present is True,
            "bounds_proven": False,
            "ownership_proven": False,
            "valid": False,
            "reason": "BOOLEAN_REQUIRED",
            "source": str(raw.get("source", name)),
        }
    valid_space = address_space in {"physical", "virtual"}
    valid = (
        present
        and bounds_proven
        and length != 0
        and valid_space
    )
    if valid:
        try:
            checked_add_local(base, length, name)
        except VerificationInputError:
            valid = False
    return {
        "name": str(raw.get("name", name)),
        "base": base,
        "length": length,
        "end": base + length if valid else None,
        "address_space": address_space,
        "present": present,
        "bounds_proven": bounds_proven,
        "ownership_proven": ownership_proven,
        "readable": readable,
        "writable": writable,
        "executable": executable,
        "mapping_proven": mapping_proven,
        "valid": valid,
        "reason": "valid" if valid else "invalid or unproven range",
        "source": str(raw.get("source", name)),
    }


def range_contains(container: Dict[str, Any], base: int, length: int) -> bool:
    if not container.get("valid"):
        return False
    try:
        end = checked_add_local(base, length, "contained range")
    except VerificationInputError:
        return False
    return (
        container["base"] <= base
        and end <= container["end"]
        and length != 0
    )


def range_overlaps(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    if not left.get("valid") or not right.get("valid"):
        return False
    if left.get("address_space") != right.get("address_space"):
        return False
    return left["base"] < right["end"] and right["base"] < left["end"]


def fact_summary(fact: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "value": fact.get("value"),
        "value_present": bool(fact.get("value_present")),
        "value_proven": bool(fact.get("value_proven")),
        "source": fact.get("source"),
        **({"error": fact["error"]} if fact.get("error") else {}),
    }


def parse_descriptor(raw: bytes) -> Dict[str, Any]:
    if len(raw) < ABI_SIZE:
        raise VerificationInputError(
            "DESCRIPTOR_TRUNCATED",
            "descriptor source contains fewer than the fixed V1 prefix",
            available=len(raw),
            required=ABI_SIZE,
        )
    values = struct.unpack_from("<QIIQIIQQQI IQQ", raw, 0)
    (
        magic,
        version,
        size,
        flags,
        entry_el,
        reserved0,
        payload_pa,
        payload_va,
        payload_size,
        mmu_enabled,
        reserved1,
        raw_x0,
        raw_x1,
    ) = values
    ranges: Dict[str, Dict[str, int]] = {}
    for name, offset in (("boot_args", 80), ("device_tree", 104)):
        base, length, range_flags, reserved = struct.unpack_from("<QQII", raw, offset)
        ranges[name] = {
            "base": base,
            "length": length,
            "flags": range_flags,
            "reserved": reserved,
        }
    return {
        "magic": magic,
        "version": version,
        "size": size,
        "flags": flags,
        "entry_el": entry_el,
        "reserved0": reserved0,
        "payload_pa": payload_pa,
        "payload_va": payload_va,
        "payload_size": payload_size,
        "mmu_enabled": mmu_enabled,
        "reserved1": reserved1,
        "raw_x0": raw_x0,
        "raw_x1": raw_x1,
        "ranges": ranges,
        "raw_sha256": hash_bytes(raw[:ABI_SIZE]),
    }


def descriptor_errors(descriptor: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if descriptor["magic"] != ABI_MAGIC:
        errors.append("MAGIC")
    if descriptor["version"] != ABI_VERSION:
        errors.append("VERSION")
    if descriptor["size"] < ABI_SIZE:
        errors.append("SIZE")
    if descriptor["flags"] & ~KNOWN_FLAGS:
        errors.append("UNKNOWN_FLAGS")
    if descriptor["reserved0"] != 0 or descriptor["reserved1"] != 0:
        errors.append("RESERVED_NONZERO")
    if descriptor["mmu_enabled"] > 1:
        errors.append("MMU_VALUE")
    if descriptor["flags"] & FLAG_ENTRY_EL_KNOWN and descriptor["entry_el"] != 1:
        errors.append("ENTRY_EL")
    if descriptor["flags"] & FLAG_PAYLOAD_LOCATION_KNOWN:
        if (
            descriptor["payload_pa"] == 0
            or descriptor["payload_va"] == 0
            or descriptor["payload_size"] == 0
        ):
            errors.append("PAYLOAD_EMPTY")
        else:
            try:
                checked_add_local(
                    descriptor["payload_pa"], descriptor["payload_size"], "payload PA"
                )
                checked_add_local(
                    descriptor["payload_va"], descriptor["payload_size"], "payload VA"
                )
            except VerificationInputError:
                errors.append("PAYLOAD_WRAP")
    mapping_flags = descriptor["flags"] & (
        FLAG_MMIO_MAPPING_VALID | FLAG_UART_MAPPING_VALID | FLAG_AIC_MAPPING_VALID
    )
    if mapping_flags and not (descriptor["flags"] & FLAG_MAPPING_STATE_KNOWN):
        errors.append("MAPPING_STATE")
    if descriptor["flags"] & (FLAG_UART_MAPPING_VALID | FLAG_AIC_MAPPING_VALID):
        if not (descriptor["flags"] & FLAG_MMIO_MAPPING_VALID):
            errors.append("MMIO_PARENT")
    for name, item in descriptor["ranges"].items():
        if item["reserved"] != 0:
            errors.append(f"{name.upper()}_RESERVED")
        if item["flags"] & ~RANGE_READABLE:
            errors.append(f"{name.upper()}_FLAGS")
        if item["length"] != 0 or item["base"] != 0:
            if item["base"] == 0 or item["length"] == 0:
                errors.append(f"{name.upper()}_EMPTY")
            if not (item["flags"] & RANGE_READABLE):
                errors.append(f"{name.upper()}_NOT_READABLE")
            try:
                checked_add_local(item["base"], item["length"], f"{name} range")
            except VerificationInputError:
                errors.append(f"{name.upper()}_WRAP")
    return errors


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except OSError as exc:
        raise VerificationInputError("BUNDLE_READ_ERROR", str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise VerificationInputError("BUNDLE_INVALID", str(exc)) from exc
    if not isinstance(value, dict):
        raise VerificationInputError("BUNDLE_INVALID", "bundle root must be an object")
    return value


class BundleVerifier:
    def __init__(self, bundle_path: str | Path):
        self.bundle_path = Path(bundle_path).resolve()
        self.bundle_dir = self.bundle_path.parent
        self.root = load_json(self.bundle_path)
        self.evidence_status = source_status(self.root)
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.conflicts: List[Dict[str, Any]] = []
        self.artifacts: Dict[str, Dict[str, Any]] = {}
        self.snapshot: Optional[Snapshot] = None
        self.snapshot_path: Optional[Path] = None
        self.elf: Optional[ElfImage] = None
        self.elf_path: Optional[Path] = None
        self.elf_audit: Optional[Dict[str, Any]] = None
        self.descriptor: Optional[Dict[str, Any]] = None
        self.target_match = False
        self.identity_proven = False
        self.same_session_provenance_proven = False
        self.technical_target_provenance_ready = False
        self.metadata_status = "UNKNOWN"
        self.same_session_status = "UNKNOWN"
        self.physical_identity_status = "NOT_PROVEN"
        self.legacy_identity_claim: Any = None
        self.target_provenance_proven = False
        self.provenance_envelope_report: Optional[Dict[str, Any]] = None
        self.ranges: Dict[str, Dict[str, Any]] = {}
        self.protected_ranges: List[Dict[str, Any]] = []
        self.security_warnings: List[Dict[str, Any]] = []

    def add_node(
        self,
        name: str,
        status: str,
        proof_state: str,
        reason: str,
        sources: Iterable[str] = (),
        depends_on: Iterable[str] = (),
        critical: bool = False,
        **details: Any,
    ) -> Dict[str, Any]:
        if status not in STATUS_VALUES:
            status = "UNKNOWN"
        if proof_state not in PROOF_VALUES:
            proof_state = "NOT_PROVEN"
        if proof_state == "PROVEN" and status not in {"CONFIRMED", "DESIGN"}:
            proof_state = "NOT_PROVEN"
        node = {
            "status": status,
            "proof_state": proof_state,
            "reason": reason,
            "evidence_sources": list(sources),
            "depends_on": list(depends_on),
            "critical": critical,
        }
        node.update(details)
        self.nodes[name] = node
        return node

    def artifact_status(self, name: str, spec: Any, required: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "name": name,
            "required": required,
            "path": None,
            "sha256_expected": None,
            "sha256_actual": None,
            "status": "UNKNOWN",
            "proof_state": "NOT_PROVEN",
            "error": None,
        }
        if not isinstance(spec, dict):
            result["error"] = "artifact specification is absent"
            result["status"] = "BLOCKED" if required else "UNKNOWN"
            return result
        path_value = spec.get("path", spec.get("file"))
        if path_value is None:
            result["error"] = "artifact path is absent"
            result["status"] = "BLOCKED" if required else "UNKNOWN"
            return result
        try:
            path = safe_bundle_path(self.bundle_dir, path_value, f"{name}.path")
        except VerificationInputError as exc:
            result["error"] = exc.code
            result["status"] = "BLOCKED"
            return result
        result["path"] = str(path_value)
        expected = spec.get("sha256")
        result["sha256_expected"] = expected
        if not path.is_file():
            result["error"] = "file is missing"
            result["status"] = "BLOCKED"
            return result
        actual = hash_file(path)
        result["sha256_actual"] = actual
        if not valid_hash(expected):
            result["error"] = "sha256 declaration is absent or malformed"
            result["status"] = "UNKNOWN"
            result["proof_state"] = "PRESENT"
            self.artifacts[name] = result
            return result
        if actual.lower() != str(expected).lower():
            result["error"] = "sha256 mismatch"
            result["status"] = "BLOCKED"
            self.artifacts[name] = result
            return result
        result["status"] = "CONFIRMED"
        result["proof_state"] = "PROVEN"
        self.artifacts[name] = result
        return result

    def artifact_bytes(
        self, name: str, spec: Any, required: bool = True
    ) -> Tuple[Optional[bytes], Dict[str, Any]]:
        result = self.artifact_status(name, spec, required=required)
        if result["path"] is None:
            return None, result
        path = safe_bundle_path(self.bundle_dir, result["path"], f"{name}.path")
        if result["status"] == "BLOCKED":
            return None, result
        try:
            data = path.read_bytes()
        except OSError as exc:
            result["status"] = "BLOCKED"
            result["proof_state"] = "NOT_PROVEN"
            result["error"] = str(exc)
            return None, result
        declared_length = spec.get("length")
        if declared_length is not None:
            try:
                length = parse_u64(declared_length, f"{name}.length")
            except VerificationInputError as exc:
                result["status"] = "BLOCKED"
                result["proof_state"] = "NOT_PROVEN"
                result["error"] = exc.code
                return None, result
            if len(data) < length:
                result["status"] = "BLOCKED"
                result["proof_state"] = "NOT_PROVEN"
                result["error"] = "local bytes are shorter than declared length"
                return None, result
            complete = strict_bool(spec, "complete", False, f"{name}.complete")
            if complete is None:
                result["status"] = "BLOCKED"
                result["proof_state"] = "NOT_PROVEN"
                result["error"] = "complete must be a JSON boolean"
                return None, result
            if complete and len(data) != length:
                result["status"] = "BLOCKED"
                result["proof_state"] = "NOT_PROVEN"
                result["error"] = "complete artifact has extra or missing bytes"
                return None, result
        return data, result

    def _status_for_mapping(self) -> str:
        return status_for_evidence(
            self.snapshot.evidence_status if self.snapshot is not None else "UNKNOWN"
        )

    def _add_conflict(
        self,
        name: str,
        left_source: str,
        left_value: Any,
        right_source: str,
        right_value: Any,
    ) -> None:
        if left_value == right_value:
            return
        self.conflicts.append(
            {
                "name": name,
                "left": {"source": left_source, "value": left_value},
                "right": {"source": right_source, "value": right_value},
                "status": "BLOCKED",
                "reason": "two independently proven values disagree",
            }
        )

    def _compare_snapshot_registers(self, name: str, bundle_fact: Dict[str, Any]) -> None:
        if self.snapshot is None or not bundle_fact.get("value_proven"):
            return
        item = self.snapshot.register(name, required=False)
        if not item.get("value_present") or not item.get("value_proven"):
            return
        self._add_conflict(
            f"REGISTER_CONFLICT_{name.upper()}",
            bundle_fact["source"],
            bundle_fact["value"],
            f"mmu_snapshot:{self.snapshot_path}:{name}",
            item["value"],
        )

    def verify_target(self) -> None:
        target = self.root.get("target")
        if not isinstance(target, dict):
            self.add_node(
                "target_metadata_match",
                "BLOCKED",
                "NOT_PROVEN",
                "target metadata object is missing",
                ("bundle.target",),
                critical=True,
            )
            return
        mismatches: Dict[str, Any] = {}
        for field, expected in EXPECTED_TARGET.items():
            actual = target.get(field)
            if field == "board":
                values = actual if isinstance(actual, list) else [actual]
                normalized = {str(value).lower() for value in values if value is not None}
                if not (normalized & expected):
                    mismatches[field] = {"expected": sorted(expected), "actual": actual}
            elif str(actual).lower() != str(expected).lower():
                mismatches[field] = {"expected": expected, "actual": actual}
        self.target_match = not mismatches
        target_status = self.evidence_status if self.target_match else "BLOCKED"
        self.add_node(
            "target_metadata_match",
            target_status,
            "PROVEN" if self.target_match else "NOT_PROVEN",
            "bundle target metadata matches expected project target"
            if self.target_match
            else "bundle target metadata does not match expected target",
            ("bundle.target",),
            critical=True,
            match=self.target_match,
            mismatches=mismatches,
        )
        # Legacy bundle.target.identity_proven is retained only as a hint for
        # compatibility. It cannot prove persistent identity or technical
        # target/session provenance; the v2 nested envelope owns those facts.
        self.legacy_identity_claim = target.get("identity_proven")

    def verify_integrity(self) -> None:
        image_spec = self.root.get("image")
        mmu_spec = self.root.get("mmu_snapshot")
        descriptor_spec = self.root.get("handoff_descriptor")
        image_artifact = self.artifact_status("image", image_spec)
        mmu_artifact = self.artifact_status("mmu_snapshot", mmu_spec)
        descriptor_artifact = self.artifact_status(
            "handoff_descriptor", descriptor_spec
        )
        self.artifacts["image"] = image_artifact
        self.artifacts["mmu_snapshot"] = mmu_artifact
        self.artifacts["handoff_descriptor"] = descriptor_artifact
        all_ok = all(
            item["proof_state"] == "PROVEN"
            for item in (image_artifact, mmu_artifact, descriptor_artifact)
        )
        self.add_node(
            "bundle_integrity",
            "CONFIRMED" if all_ok else (
                "BLOCKED" if any(item["status"] == "BLOCKED" for item in (
                    image_artifact, mmu_artifact, descriptor_artifact
                )) else "UNKNOWN"
            ),
            "PROVEN" if all_ok else "NOT_PROVEN",
            "all required local artifacts match declared SHA-256"
            if all_ok
            else "one or more required artifacts are missing, unhashed, or mismatched",
            tuple(
                f"bundle.{name}" for name in (
                    "image", "mmu_snapshot", "handoff_descriptor"
                )
            ),
            critical=True,
            artifacts=self.artifacts,
            sha256_meaning=(
                "local file matches the bundle declaration; this is not proof of "
                "genuine Watch provenance"
            ),
        )

    def verify_provenance(self) -> None:
        source = self.root.get("source", {})
        source_kind = source.get("kind") if isinstance(source, dict) else None
        envelope = self.root.get("provenance_envelope")
        if isinstance(envelope, dict):
            self.provenance_envelope_report = validate_envelope(
                envelope,
                self.bundle_dir,
                EXPECTED_TARGET,
                bundle=self.root,
                artifact_cache=self.artifacts,
                path_resolver=safe_bundle_path,
                file_hasher=hash_file,
            )
            for conflict in self.provenance_envelope_report.get("conflicts", []):
                self.conflicts.append(conflict)
            envelope_target = self.provenance_envelope_report.get("target", {})
            envelope_requirements = self.provenance_envelope_report.get("requirements", {})
            metadata_requirement = envelope_requirements.get("EV-000A", {})
            session_requirement = envelope_requirements.get("EV-000B", {})
            physical_requirement = envelope_requirements.get("EV-000C", {})
            envelope_status = self.provenance_envelope_report.get("status", "UNKNOWN")
            envelope_checked = (
                envelope_status in {"CONFIRMED", "DESIGN"}
                and not self.provenance_envelope_report.get("errors")
                and not self.provenance_envelope_report.get("conflicts")
            )
            self.add_node(
                "provenance_envelope",
                envelope_status,
                "PROVEN" if envelope_checked else "NOT_PROVEN",
                "envelope declarations and local bytes were checked; external authenticity is not established",
                ("bundle.provenance_envelope",),
                critical=False,
                validation=self.provenance_envelope_report,
            )
        else:
            self.provenance_envelope_report = None
            envelope_target = {}
            metadata_requirement = {}
            session_requirement = {}
            physical_requirement = {}
            envelope_checked = False
            self.add_node(
                "provenance_envelope",
                "BLOCKED" if self.evidence_status == "CONFIRMED" else "UNKNOWN",
                "NOT_PROVEN",
                "target-bound provenance envelope is absent",
                ("bundle.provenance_envelope",),
                critical=False,
            )

        self.metadata_status = str(metadata_requirement.get("status", envelope_target.get("metadata_status", "UNKNOWN")))
        self.same_session_status = str(session_requirement.get("status", envelope_target.get("same_session_provenance_status", "UNKNOWN")))
        metadata_proven = metadata_requirement.get("proof_state") == "PROVEN" and self.target_match
        session_proven = session_requirement.get("proof_state") == "PROVEN"
        self.same_session_provenance_proven = bool(session_proven)
        physical_identity_proven = bool(envelope_target.get("physical_identity_proven"))
        self.identity_proven = physical_identity_proven
        self.physical_identity_status = str(
            envelope_target.get("physical_identity_status", "NOT_PROVEN")
        )
        self.technical_target_provenance_ready = bool(
            metadata_proven
            and session_proven
            and self.evidence_status == "CONFIRMED"
            and source_kind != "synthetic"
            and envelope_checked
            and not self.conflicts
        )
        self.add_node(
            "target_metadata_provenance",
            metadata_requirement.get("status", "BLOCKED" if self.evidence_status == "CONFIRMED" else "UNKNOWN"),
            metadata_requirement.get("proof_state", "NOT_PROVEN"),
            metadata_requirement.get("reason", "provenance envelope target metadata is absent"),
            metadata_requirement.get("evidence_sources", ("bundle.provenance_envelope.target.metadata",)),
            critical=True,
            metadata_status=self.metadata_status,
        )
        self.add_node(
            "same_session_provenance",
            session_requirement.get("status", "BLOCKED" if self.evidence_status == "CONFIRMED" else "UNKNOWN"),
            session_requirement.get("proof_state", "NOT_PROVEN"),
            session_requirement.get("reason", "provenance envelope does not prove a common capture session"),
            session_requirement.get("evidence_sources", ("bundle.provenance_envelope.capture", "bundle.provenance_envelope.artifacts")),
            critical=True,
            same_session_status=self.same_session_status,
        )
        self.add_node(
            "physical_identity_provenance",
            physical_requirement.get("status", "UNKNOWN"),
            physical_requirement.get("proof_state", "NOT_PROVEN"),
            physical_requirement.get("reason", "persistent physical-device identity is not proven"),
            physical_requirement.get("evidence_sources", ("bundle.provenance_envelope.target.physical_identity",)),
            critical=False,
            readiness_effect="NONE_FOR_FIRST_TECHNICAL_BRINGUP",
        )
        self.add_node(
            "target_identity_proven",
            "CONFIRMED" if physical_identity_proven else self.physical_identity_status,
            "PROVEN" if physical_identity_proven else "NOT_PROVEN",
            "deprecated compatibility node; physical identity is separate from technical target/session provenance",
            ("bundle.provenance_envelope.target.physical_identity", "bundle.provenance_envelope.target.identity_attestation"),
            critical=False,
            value=physical_identity_proven,
        )
        if source_kind == "synthetic":
            safe_synthetic = (
                self.evidence_status == "DESIGN"
                and self.legacy_identity_claim is not True
                and not physical_identity_proven
            )
            covered = (
                self.provenance_envelope_report.get("coverage", {}).get("covered_artifact_ids", [])
                if self.provenance_envelope_report else []
            )
            self.add_node(
                "target_provenance",
                "DESIGN",
                "NOT_PROVEN",
                "synthetic evidence models A+B only and is never target-bound hardware provenance",
                ("bundle.source", "bundle.provenance_envelope"),
                critical=False,
                covered_artifacts=covered,
            )
            self.add_node(
                "synthetic_evidence_guard",
                "DESIGN" if safe_synthetic else "BLOCKED",
                "PROVEN" if safe_synthetic else "NOT_PROVEN",
                "synthetic source is explicitly DESIGN and identity is not proven"
                if safe_synthetic
                else "synthetic evidence cannot claim CONFIRMED status or target identity",
                ("bundle.source.kind", "bundle.source.evidence_status", "bundle.target.identity_proven", "bundle.provenance_envelope.target.physical_identity"),
                critical=not safe_synthetic,
                source_kind=source_kind,
            )
            return
        valid = bool(
            source_kind
            and self.evidence_status == "CONFIRMED"
            and self.target_match
            and metadata_proven
            and session_proven
            and envelope_checked
            and not self.conflicts
        )
        self.target_provenance_proven = valid
        self.technical_target_provenance_ready = valid
        covered = (
            self.provenance_envelope_report.get("coverage", {}).get("covered_artifact_ids", [])
            if self.provenance_envelope_report else []
        )
        self.add_node(
            "target_provenance",
            "CONFIRMED" if valid else (
                "BLOCKED" if self.evidence_status == "CONFIRMED" or self.conflicts else "UNKNOWN"
            ),
            "PROVEN" if valid else "NOT_PROVEN",
            "provenance explicitly covers all required bundle artifacts"
            if valid
            else "technical target provenance requires EV-000A metadata consistency and EV-000B same-session artifact provenance; EV-000C physical identity is optional",
            ("bundle.source", "bundle.provenance_envelope", "bundle.image", "bundle.handoff_descriptor", "bundle.mmu_snapshot"),
            critical=True,
            source_kind=source_kind,
            covered_artifacts=covered if isinstance(covered, list) else [],
        )

    def verify_artifact_aliases(self) -> None:
        owners: Dict[str, List[str]] = {}
        for name, artifact in self.artifacts.items():
            path_value = artifact.get("path")
            if path_value is None:
                continue
            try:
                resolved = str(safe_bundle_path(self.bundle_dir, path_value, f"{name}.path"))
            except VerificationInputError:
                continue
            owners.setdefault(resolved, []).append(name)
        duplicates = [
            {"path": path, "artifacts": names}
            for path, names in owners.items()
            if len(names) > 1
        ]
        self.add_node(
            "artifact_aliases",
            "BLOCKED" if duplicates else "CONFIRMED",
            "NOT_PROVEN" if duplicates else "PROVEN",
            "artifact paths are unique after canonicalization"
            if not duplicates
            else "multiple artifact declarations resolve to the same local file",
            ("bundle.artifacts",),
            critical=True,
            duplicates=duplicates,
        )

    def verify_descriptor(self) -> None:
        spec = self.root.get("handoff_descriptor")
        data: Optional[bytes] = None
        artifact = self.artifacts.get("handoff_descriptor", {})
        if isinstance(spec, dict) and "bytes_hex" in spec:
            data = None
            artifact = {
                "name": "handoff_descriptor",
                "status": "BLOCKED",
                "proof_state": "NOT_PROVEN",
                "path": None,
                "sha256_actual": None,
                "sha256_expected": spec.get("sha256"),
                "error": "inline descriptor bytes are not accepted; provide a hashed local file",
            }
            self.artifacts["handoff_descriptor"] = artifact
        elif artifact.get("path") is not None and artifact.get("status") != "BLOCKED":
            try:
                data = safe_bundle_path(
                    self.bundle_dir, artifact["path"], "handoff_descriptor.path"
                ).read_bytes()
            except OSError:
                data = None
        if data is None:
            self.add_node(
                "descriptor_structure",
                "BLOCKED",
                "NOT_PROVEN",
                "descriptor bytes are unavailable",
                ("bundle.handoff_descriptor",),
                critical=True,
            )
            self.add_node(
                "descriptor_root_of_trust",
                "BLOCKED",
                "NOT_PROVEN",
                "the 128-byte prefix was not available for independent validation",
                ("bundle.handoff_descriptor",),
                depends_on=("descriptor_structure",),
                critical=True,
            )
            return
        try:
            descriptor = parse_descriptor(data)
            errors = descriptor_errors(descriptor)
        except VerificationInputError as exc:
            descriptor = None
            errors = [exc.code]
        self.descriptor = descriptor
        structure_ok = descriptor is not None and not errors
        evidence = "DESIGN" if structure_ok and self.evidence_status == "DESIGN" else (
            "CONFIRMED" if structure_ok else "BLOCKED"
        )
        self.add_node(
            "descriptor_structure",
            evidence,
            "PROVEN" if structure_ok else "NOT_PROVEN",
            "V1 prefix has valid magic, version, size, flags, ranges, and overflow checks"
            if structure_ok
            else "V1 structural validation failed",
            ("handoff_descriptor:128-byte-prefix",),
            critical=True,
            errors=errors,
            descriptor=descriptor,
            abi_size=ABI_SIZE,
            verified_flag_asserted=bool(
                descriptor and descriptor.get("flags", 0) & FLAG_VERIFIED
            ),
        )
        prefix = (
            strict_bool(
                spec,
                "prefix_readable_proven",
                False,
                "handoff_descriptor.prefix_readable_proven",
            )
            if isinstance(spec, dict)
            else False
        )
        copied = (
            strict_bool(
                spec,
                "copied_to_trusted_storage_proven",
                False,
                "handoff_descriptor.copied_to_trusted_storage_proven",
            )
            if isinstance(spec, dict)
            else False
        )
        root_ok = structure_ok and prefix is True and copied is True
        self.add_node(
            "descriptor_root_of_trust",
            evidence if root_ok else "BLOCKED",
            "PROVEN" if root_ok else "NOT_PROVEN",
            "prefix readability and trusted-copy proof are independent of VERIFIED bit"
            if root_ok
            else "descriptor VERIFIED assertion cannot replace readable-prefix and trusted-copy proof",
            (
                "handoff_descriptor.prefix_readable_proven",
                "handoff_descriptor.copied_to_trusted_storage_proven",
                "handoff_descriptor:128-byte-prefix",
            ),
            depends_on=("descriptor_structure",),
            critical=True,
            prefix_readable_proven=prefix,
            copied_to_trusted_storage_proven=copied,
            verified_flag_asserted=bool(
                descriptor and descriptor.get("flags", 0) & FLAG_VERIFIED
            ),
        )

    def verify_mmu(self) -> None:
        spec = self.root.get("mmu_snapshot")
        artifact = self.artifacts.get("mmu_snapshot", {})
        if not isinstance(spec, dict) or artifact.get("path") is None:
            self.add_node(
                "mmu_snapshot_present",
                "BLOCKED",
                "NOT_PROVEN",
                "MMU snapshot manifest is not available",
                ("bundle.mmu_snapshot",),
                critical=True,
            )
            return
        try:
            self.snapshot_path = safe_bundle_path(
                self.bundle_dir, artifact["path"], "mmu_snapshot.path"
            )
            self.snapshot = Snapshot.load(self.snapshot_path)
        except (VerificationInputError, SnapshotError) as exc:
            self.add_node(
                "mmu_snapshot_present",
                "BLOCKED",
                "NOT_PROVEN",
                f"MMU snapshot could not be loaded: {getattr(exc, 'code', str(exc))}",
                ("bundle.mmu_snapshot",),
                critical=True,
            )
            return
        snapshot_target = self.snapshot.manifest.get("target")
        bundle_target = self.root.get("target")
        target_mismatches: Dict[str, Any] = {}
        if not isinstance(bundle_target, dict):
            target_mismatches["bundle_target"] = "bundle target metadata is missing"
        elif not isinstance(snapshot_target, dict):
            target_mismatches["snapshot_target"] = "snapshot target metadata is missing"
        else:
            for field in EXPECTED_TARGET:
                expected = bundle_target.get(field)
                actual = snapshot_target.get(field)
                if field == "board":
                    expected_values = normalize_board(expected)
                    actual_values = normalize_board(actual)
                    if not expected_values or expected_values != actual_values:
                        target_mismatches[field] = {
                            "bundle": expected,
                            "snapshot": actual,
                        }
                elif str(actual).lower() != str(expected).lower():
                    target_mismatches[field] = {
                        "bundle": expected,
                        "snapshot": actual,
                    }
        snapshot_target_ok = not target_mismatches
        self.add_node(
            "mmu_snapshot_target_match",
            self._status_for_mapping() if snapshot_target_ok else "BLOCKED",
            "PROVEN" if snapshot_target_ok else "NOT_PROVEN",
            "MMU snapshot target metadata matches the bundle target"
            if snapshot_target_ok
            else "MMU snapshot target metadata is missing or conflicts with the bundle target",
            (f"mmu_snapshot:{self.snapshot_path}:target", "bundle.target"),
            critical=True,
            mismatches=target_mismatches,
        )
        self.add_node(
            "mmu_snapshot_present",
            self._status_for_mapping(),
            "PROVEN",
            "local snapshot manifest is syntactically valid and loaded offline",
            (f"mmu_snapshot:{self.snapshot_path}",),
            critical=True,
            source=self.snapshot.source,
        )
        proven = True
        register_report: Dict[str, Any] = {}
        for name in REQUIRED_SNAPSHOT_REGISTERS:
            item = self.snapshot.register(name, required=False)
            register_report[name] = {
                "value": item.get("value"),
                "value_present": bool(item.get("value_present")),
                "value_proven": bool(item.get("value_proven")),
            }
            proven = proven and bool(item.get("value_present")) and bool(
                item.get("value_proven")
            )
        self.add_node(
            "mmu_register_provenance",
            self._status_for_mapping() if proven else "BLOCKED",
            "PROVEN" if proven else "NOT_PROVEN",
            "TCR, TTBR, MAIR, and SCTLR snapshot values are separately marked proven"
            if proven
            else "MMU translation-critical register provenance is incomplete",
            tuple(f"mmu_snapshot:{self.snapshot_path}:{name}" for name in REQUIRED_SNAPSHOT_REGISTERS),
            depends_on=("mmu_snapshot_present",),
            critical=True,
            registers=register_report,
        )

    def verify_image(self) -> None:
        spec = self.root.get("image")
        artifact = self.artifacts.get("image", {})
        if artifact.get("path") is None or artifact.get("status") == "BLOCKED":
            self.add_node(
                "image_integrity",
                "BLOCKED",
                "NOT_PROVEN",
                "DreyzeOS ELF is unavailable or its SHA-256 is not valid",
                ("bundle.image",),
                critical=True,
            )
            self.add_node(
                "image_shape",
                "BLOCKED",
                "NOT_PROVEN",
                "ELF architecture and entry cannot be checked",
                ("bundle.image",),
                depends_on=("image_integrity",),
                critical=True,
            )
            return
        try:
            self.elf_path = safe_bundle_path(
                self.bundle_dir, artifact["path"], "image.path"
            )
            self.elf = ElfImage(self.elf_path)
        except (VerificationInputError, SnapshotError) as exc:
            self.add_node(
                "image_integrity",
                "BLOCKED",
                "NOT_PROVEN",
                f"ELF could not be parsed: {getattr(exc, 'code', str(exc))}",
                ("bundle.image",),
                critical=True,
            )
            self.add_node(
                "image_shape",
                "BLOCKED",
                "NOT_PROVEN",
                "ELF architecture and entry cannot be checked",
                ("bundle.image",),
                depends_on=("image_integrity",),
                critical=True,
            )
            return
        expected_arch = spec.get("expected_arch") if isinstance(spec, dict) else None
        expected_entry = spec.get("expected_entry") if isinstance(spec, dict) else None
        entry_ok = expected_entry is not None
        expected_entry_value: Optional[int] = None
        if expected_entry is not None:
            try:
                expected_entry_value = parse_u64(expected_entry, "image.expected_entry")
                entry_ok = self.elf.header["entry"] == expected_entry_value
            except VerificationInputError:
                entry_ok = False
        arch_ok = self.elf.header.get("machine") == 183 and expected_arch == "aarch64"
        image_ok = artifact.get("proof_state") == "PROVEN"
        self.add_node(
            "image_integrity",
            "CONFIRMED" if image_ok else "UNKNOWN",
            "PROVEN" if image_ok else "NOT_PROVEN",
            "ELF SHA-256 matches the bundle declaration"
            if image_ok
            else "ELF is present but local integrity is not fully declared",
            ("bundle.image",),
            critical=True,
            artifact=artifact,
        )
        shape_ok = image_ok and arch_ok and entry_ok
        self.add_node(
            "image_shape",
            "CONFIRMED" if shape_ok else "BLOCKED",
            "PROVEN" if shape_ok else "NOT_PROVEN",
            "ELF is AArch64 and matches the declared entry"
            if shape_ok
            else "ELF architecture or declared entry mismatch",
            ("ELF:e_machine", "ELF:e_entry", "bundle.image.expected_entry"),
            depends_on=("image_integrity",),
            critical=True,
            actual_arch="aarch64" if self.elf.header.get("machine") == 183 else "unknown",
            actual_entry=self.elf.header.get("entry"),
            expected_entry=expected_entry_value,
        )
        if self.snapshot is not None:
            try:
                self.elf_audit = analyze_elf(self.elf_path, self.snapshot)
            except (SnapshotError, OSError) as exc:
                self.security_warnings.append(
                    {
                        "name": "ELF_AUDIT_ERROR",
                        "status": "BLOCKED",
                        "reason": str(exc),
                    }
                )
        else:
            try:
                self.elf_audit = analyze_elf(self.elf_path, None)
            except (SnapshotError, OSError):
                self.elf_audit = None

    def verify_cpu(self) -> None:
        state = self.root.get("cpu_state", {})
        if not isinstance(state, dict):
            state = {}
        self.cpu: Dict[str, Dict[str, Any]] = {}
        for name in (
            "current_el",
            "sp",
            "daif",
            "sctlr_el1",
            "tcr_el1",
            "ttbr0_el1",
            "ttbr1_el1",
            "mair_el1",
            "vbar_el1",
            "cpacr_el1",
            "pc",
        ):
            self.cpu[name] = present_fact(state.get(name), f"bundle.cpu_state.{name}")
            self._compare_snapshot_registers(name, self.cpu[name])
        descriptor_el = (
            self.descriptor.get("entry_el")
            if self.descriptor is not None
            and self.descriptor.get("flags", 0) & FLAG_ENTRY_EL_KNOWN
            else None
        )
        entry_ok = (
            self.cpu["current_el"].get("value_proven")
            and self.cpu["current_el"].get("value") == 1
            and descriptor_el == 1
        )
        self.add_node(
            "entry_el1",
            "DESIGN" if entry_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if entry_ok else "BLOCKED"
            ),
            "PROVEN" if entry_ok else "NOT_PROVEN",
            "bundle CPU state and V1 descriptor both prove EL1"
            if entry_ok
            else "EL1 is absent, unproven, or contradicts the descriptor",
            (
                "bundle.cpu_state.current_el",
                "handoff_descriptor.entry_el",
            ),
            critical=True,
            current_el=fact_summary(self.cpu["current_el"]),
            descriptor_entry_el=descriptor_el,
        )
        sp_ok = (
            self.cpu["sp"].get("value_proven")
            and self.cpu["sp"].get("value") is not None
            and self.cpu["sp"]["value"] % 16 == 0
        )
        self.add_node(
            "initial_sp",
            "DESIGN" if sp_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if sp_ok else "BLOCKED"
            ),
            "PROVEN" if sp_ok else "NOT_PROVEN",
            "SP is explicitly proven and 16-byte aligned"
            if sp_ok
            else "SP is missing, unproven, or unaligned",
            ("bundle.cpu_state.sp",),
            critical=True,
            sp=fact_summary(self.cpu["sp"]),
        )
        daif_raw = state.get("daif", {})
        daif_fact = self.cpu["daif"]
        daif_normalized = (
            strict_bool(
                daif_raw,
                "normalized",
                False,
                "bundle.cpu_state.daif.normalized",
            )
            if isinstance(daif_raw, dict)
            else None
        )
        daif_normalized_proven = (
            strict_bool(
                daif_raw,
                "normalized_proven",
                daif_fact.get("value_proven", False),
                "bundle.cpu_state.daif.normalized_proven",
            )
            if isinstance(daif_raw, dict)
            else None
        )
        daif_ok = (
            daif_fact.get("value_proven")
            and daif_normalized is True
            and daif_normalized_proven is True
        )
        self.add_node(
            "daif_normalized",
            "DESIGN" if daif_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if daif_ok else "BLOCKED"
            ),
            "PROVEN" if daif_ok else "NOT_PROVEN",
            "DAIF normalization is an explicit loader fact"
            if daif_ok
            else "DAIF state is not proven normalized",
            ("bundle.cpu_state.daif",),
            critical=True,
            daif=fact_summary(daif_fact),
        )
        policy = state.get("translation_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        policy_proven = strict_bool(
            policy,
            "normalized_proven",
            False,
            "bundle.cpu_state.translation_policy.normalized_proven",
        )
        translation_ok = (
            policy_proven is True
            and self.cpu["sctlr_el1"].get("value_proven")
            and self.cpu["tcr_el1"].get("value_proven")
            and self.cpu["ttbr0_el1"].get("value_proven")
            and self.cpu["ttbr1_el1"].get("value_proven")
            and self.cpu["mair_el1"].get("value_proven")
            and self.descriptor is not None
            and bool(self.descriptor.get("flags", 0) & FLAG_MMU_STATE_KNOWN)
        )
        descriptor_mmu = self.descriptor.get("mmu_enabled") if self.descriptor else None
        sctlr_m = (
            (self.cpu["sctlr_el1"].get("value", 0) & 1)
            if self.cpu["sctlr_el1"].get("value") is not None
            else None
        )
        if (
            self.cpu["sctlr_el1"].get("value_proven")
            and descriptor_mmu is not None
            and sctlr_m is not None
        ):
            self._add_conflict(
                "MMU_ENABLED_CONFLICT",
                "handoff_descriptor.mmu_enabled",
                descriptor_mmu,
                "bundle.cpu_state.sctlr_el1.M",
                sctlr_m,
            )
        self.add_node(
            "translation_policy",
            "DESIGN" if translation_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if translation_ok else "BLOCKED"
            ),
            "PROVEN" if translation_ok else "NOT_PROVEN",
            "translation regime, MMU state, roots, TCR and MAIR are explicitly normalized"
            if translation_ok
            else "translation policy is incomplete or descriptor/CPU state is contradictory",
            (
                "bundle.cpu_state.translation_policy",
                "bundle.cpu_state.sctlr_el1",
                "bundle.cpu_state.tcr_el1",
                "bundle.cpu_state.ttbr0_el1",
                "bundle.cpu_state.ttbr1_el1",
                "bundle.cpu_state.mair_el1",
            ),
            critical=True,
            sctlr_m=sctlr_m,
        )
        cache = state.get("cache_policy", {})
        if not isinstance(cache, dict):
            cache = {}
        icache = cache.get("icache", {})
        dcache = cache.get("dcache", {})
        icache_proven = (
            strict_bool(
                icache,
                "normalized_proven",
                False,
                "bundle.cpu_state.cache_policy.icache.normalized_proven",
            )
            if isinstance(icache, dict)
            else None
        )
        dcache_proven = (
            strict_bool(
                dcache,
                "normalized_proven",
                False,
                "bundle.cpu_state.cache_policy.dcache.normalized_proven",
            )
            if isinstance(dcache, dict)
            else None
        )
        cache_ok = (
            icache_proven is True
            and dcache_proven is True
            and self.cpu["vbar_el1"].get("value_proven")
            and self.cpu["cpacr_el1"].get("value_proven")
        )
        self.add_node(
            "cache_policy",
            "DESIGN" if cache_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if cache_ok else "BLOCKED"
            ),
            "PROVEN" if cache_ok else "NOT_PROVEN",
            "I-cache, D-cache, VBAR and FP/SIMD policy are explicitly proven"
            if cache_ok
            else "cache/vector/FP-SIMD normalization proof is incomplete",
            (
                "bundle.cpu_state.cache_policy",
                "bundle.cpu_state.vbar_el1",
                "bundle.cpu_state.cpacr_el1",
            ),
            critical=True,
            cache_policy=cache,
        )
        conflict_ok = not self.conflicts
        self.add_node(
            "cpu_consistency",
            "DESIGN" if conflict_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if conflict_ok else "BLOCKED"
            ),
            "PROVEN" if conflict_ok else "NOT_PROVEN",
            "independently proven CPU/MMU facts agree"
            if conflict_ok
            else "proven evidence values conflict",
            tuple(item["name"] for item in self.conflicts),
            critical=True,
            conflicts=self.conflicts,
        )

    def _elf_symbol(self, name: str) -> Optional[int]:
        if self.elf is None:
            return None
        item = self.elf.symbols.get(name)
        return item["value"] if item else None

    def _elf_loaded_end(self) -> Optional[int]:
        if self.elf is None:
            return None
        ends: List[int] = []
        for section in self.elf.sections:
            if (
                section.get("flags", 0) & 0x2
                and section.get("size", 0) != 0
                and section.get("type") != 8
            ):
                try:
                    ends.append(
                        checked_add_local(
                            int(section["address"]),
                            int(section["size"]),
                            f"ELF section {section.get('name')}",
                        )
                    )
                except VerificationInputError:
                    return None
        return max(ends) if ends else None

    def verify_ranges(self) -> None:
        raw = self.root.get("ranges", {})
        if not isinstance(raw, dict):
            raw = {}
        self.ranges = {}
        for name, item in raw.items():
            if isinstance(item, dict) and (
                "base" in item or "physical_base" in item
            ):
                self.ranges[name] = range_fact(item, f"bundle.ranges.{name}")
        for name in (
            "payload_physical",
            "payload_virtual",
            "stage0_executable",
            "loader_code",
            "loader_stack",
            "loader_heap",
            "descriptor_source",
            "descriptor_copy",
            "boot_args",
            "device_tree",
            "framebuffer",
            "kernel_stack",
        ):
            if name not in self.ranges:
                self.ranges[name] = range_fact(
                    raw.get(name), f"bundle.ranges.{name}"
                )
        descriptor_payload = self.descriptor or {}
        pa = self.ranges["payload_physical"]
        va = self.ranges["payload_virtual"]
        descriptor_pa = descriptor_payload.get("payload_pa")
        descriptor_va = descriptor_payload.get("payload_va")
        descriptor_size = descriptor_payload.get("payload_size")
        pa_ok = (
            descriptor_pa is not None
            and pa.get("valid")
            and pa.get("base") == descriptor_pa
            and pa.get("length") == descriptor_size
        )
        va_ok = (
            descriptor_va is not None
            and va.get("valid")
            and va.get("base") == descriptor_va
            and va.get("length") == descriptor_size
        )
        native_max = (1 << (struct.calcsize("P") * 8)) - 1
        native_ok = (
            descriptor_pa is not None
            and descriptor_va is not None
            and descriptor_pa <= native_max
            and descriptor_va <= native_max
        )
        self.add_node(
            "payload_pa_proven",
            "DESIGN" if pa_ok and native_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if pa_ok and native_ok else "BLOCKED"
            ),
            "PROVEN" if pa_ok and native_ok else "NOT_PROVEN",
            "descriptor PA matches an owned, bounded physical range"
            if pa_ok and native_ok
            else "payload PA is absent, mismatched, wrapping, or not representable",
            (
                "handoff_descriptor.payload_pa",
                "bundle.ranges.payload_physical",
            ),
            critical=True,
            range=pa,
        )
        self.add_node(
            "payload_va_proven",
            "DESIGN" if va_ok and native_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if va_ok and native_ok else "BLOCKED"
            ),
            "PROVEN" if va_ok and native_ok else "NOT_PROVEN",
            "descriptor VA matches an owned, bounded virtual range"
            if va_ok and native_ok
            else "payload VA is absent, mismatched, wrapping, or not representable",
            (
                "handoff_descriptor.payload_va",
                "bundle.ranges.payload_virtual",
            ),
            critical=True,
            range=va,
        )
        loaded_end = self._elf_loaded_end()
        image_base = self._elf_symbol("_start")
        size_ok = (
            descriptor_size is not None
            and descriptor_size != 0
            and descriptor_va is not None
            and loaded_end is not None
            and image_base is not None
            and descriptor_va == image_base
            and range_contains(va, image_base, loaded_end - image_base)
        )
        self.add_node(
            "payload_size_bound",
            "DESIGN" if size_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if size_ok else "BLOCKED"
            ),
            "PROVEN" if size_ok else "NOT_PROVEN",
            "payload bound contains all loadable non-NOBITS ELF bytes"
            if size_ok
            else "payload size does not contain the linked loadable image",
            (
                "handoff_descriptor.payload_size",
                "ELF:_start",
                "ELF:allocated-PROGBITS-end",
                "bundle.ranges.payload_virtual",
            ),
            critical=True,
            loaded_image_end=loaded_end,
            image_base=image_base,
        )
        runtime = self.root.get("runtime_memory", {})
        if not isinstance(runtime, dict):
            runtime = {}
        dram_base_fact = present_fact(
            runtime.get("dram_phys_base"), "bundle.runtime_memory.dram_phys_base"
        )
        dram_size_fact = present_fact(
            runtime.get("dram_size"), "bundle.runtime_memory.dram_size"
        )
        provenance = runtime.get("provenance", "UNKNOWN")
        dram_ok = (
            provenance == "RUNTIME_VERIFIED"
            and dram_base_fact.get("value_proven")
            and dram_size_fact.get("value_proven")
            and dram_base_fact.get("value", 0) != 0
            and dram_size_fact.get("value", 0) != 0
        )
        if dram_ok:
            try:
                checked_add_local(
                    dram_base_fact["value"], dram_size_fact["value"], "runtime DRAM"
                )
            except VerificationInputError:
                dram_ok = False
        self.runtime_memory = {
            "dram_phys_base": fact_summary(dram_base_fact),
            "dram_size": fact_summary(dram_size_fact),
            "provenance": provenance,
        }
        self.add_node(
            "runtime_memory_provenance",
            "DESIGN" if dram_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if dram_ok else "BLOCKED"
            ),
            "PROVEN" if dram_ok else "NOT_PROVEN",
            "runtime DRAM range is explicitly proven with runtime provenance"
            if dram_ok
            else "static/fallback/absent DRAM metadata cannot authorize payload placement",
            (
                "bundle.runtime_memory.dram_phys_base",
                "bundle.runtime_memory.dram_size",
                "bundle.runtime_memory.provenance",
            ),
            critical=True,
            runtime_memory=self.runtime_memory,
        )
        payload_owner = pa.get("ownership_proven") and va.get("ownership_proven")
        self.add_node(
            "payload_ownership",
            "DESIGN" if payload_owner and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if payload_owner else "BLOCKED"
            ),
            "PROVEN" if payload_owner else "NOT_PROVEN",
            "both physical deposit and virtual payload ownership are explicit"
            if payload_owner
            else "mapping or numeric range does not prove payload ownership",
            (
                "bundle.ranges.payload_physical.ownership_proven",
                "bundle.ranges.payload_virtual.ownership_proven",
            ),
            critical=True,
        )
        in_dram = False
        if dram_ok and pa.get("valid"):
            dram = {
                "base": dram_base_fact["value"],
                "length": dram_size_fact["value"],
                "end": dram_base_fact["value"] + dram_size_fact["value"],
                "valid": True,
            }
            in_dram = range_contains(dram, pa["base"], pa["length"])
        self.add_node(
            "payload_in_runtime_dram",
            "DESIGN" if in_dram and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if in_dram else "BLOCKED"
            ),
            "PROVEN" if in_dram else "NOT_PROVEN",
            "payload physical interval is wholly inside verified runtime DRAM"
            if in_dram
            else "payload PA is outside or not proven inside runtime DRAM",
            ("bundle.runtime_memory", "bundle.ranges.payload_physical"),
            depends_on=("payload_pa_proven", "runtime_memory_provenance"),
            critical=True,
        )
        if self.nodes.get("payload_pa_proven", {}).get("proof_state") != "PROVEN":
            self.nodes["payload_in_runtime_dram"]["depends_on"].append("payload_pa_proven")
        # Loader/descriptor ranges are consumed by the trust and collision checks.
        trust_names = ("loader_code", "loader_stack", "descriptor_source", "descriptor_copy")
        trust_ok = True
        for name in trust_names:
            item = self.ranges[name]
            required_permission = {
                "loader_code": "executable",
                "loader_stack": "writable",
                "descriptor_source": "readable",
                "descriptor_copy": "writable",
            }[name]
            trust_ok = trust_ok and item.get("valid") and item.get("ownership_proven")
            trust_ok = trust_ok and bool(item.get(required_permission, False))
        source_ok = self.ranges["descriptor_source"].get("valid") and range_contains(
            self.ranges["descriptor_source"], self.ranges["descriptor_source"].get("base", 0), ABI_SIZE
        )
        copy_ok = self.ranges["descriptor_copy"].get("valid") and range_contains(
            self.ranges["descriptor_copy"], self.ranges["descriptor_copy"].get("base", 0), ABI_SIZE
        )
        trust_ok = trust_ok and source_ok and copy_ok
        self.add_node(
            "descriptor_access_authority",
            "DESIGN" if trust_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if trust_ok else "BLOCKED"
            ),
            "PROVEN" if trust_ok else "NOT_PROVEN",
            "loader code/stack and descriptor source/copy authority are explicit"
            if trust_ok
            else "descriptor VERIFIED bit cannot replace source/copy range authority",
            tuple(f"bundle.ranges.{name}" for name in trust_names),
            depends_on=("descriptor_root_of_trust",),
            critical=True,
        )
        # Kernel stack range is a protected interval and must agree with ELF.
        stack = self.ranges["kernel_stack"]
        elf_stack_base = self._elf_symbol("__stack_bottom")
        elf_stack_top = self._elf_symbol("__stack_top")
        stack_ok = (
            stack.get("valid")
            and stack.get("address_space") == "virtual"
            and stack.get("readable")
            and stack.get("writable")
            and stack.get("ownership_proven")
            and elf_stack_base is not None
            and elf_stack_top is not None
            and stack.get("base") == elf_stack_base
            and stack.get("length") == elf_stack_top - elf_stack_base
        )
        self.add_node(
            "kernel_stack_range",
            "DESIGN" if stack_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if stack_ok else "BLOCKED"
            ),
            "PROVEN" if stack_ok else "NOT_PROVEN",
            "kernel stack range is bounded, owned, and agrees with ELF symbols"
            if stack_ok
            else "kernel stack range is missing or inconsistent with ELF",
            ("bundle.ranges.kernel_stack", "ELF:__stack_bottom", "ELF:__stack_top"),
            critical=True,
        )
        framebuffer_known = strict_bool(
            raw,
            "framebuffer_reservation_known",
            False,
            "bundle.ranges.framebuffer_reservation_known",
        )
        framebuffer_known_proven = strict_bool(
            raw,
            "framebuffer_reservation_known_proven",
            False,
            "bundle.ranges.framebuffer_reservation_known_proven",
        )
        fb = self.ranges["framebuffer"]
        framebuffer_ok = framebuffer_known is True and framebuffer_known_proven is True and (
            not fb.get("present") or (
                fb.get("valid") and fb.get("ownership_proven")
            )
        )
        self.add_node(
            "framebuffer_reservation",
            "DESIGN" if framebuffer_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if framebuffer_ok else "BLOCKED"
            ),
            "PROVEN" if framebuffer_ok else "NOT_PROVEN",
            "framebuffer reservation presence/absence is explicitly known"
            if framebuffer_ok
            else "framebuffer reservation is not independently proven",
            (
                "bundle.ranges.framebuffer_reservation_known",
                "bundle.ranges.framebuffer",
            ),
            critical=True,
        )
        protected_complete_value = strict_bool(
            raw,
            "protected_ranges_complete",
            False,
            "bundle.ranges.protected_ranges_complete",
        )
        protected_complete_proven = strict_bool(
            raw,
            "protected_ranges_complete_proven",
            False,
            "bundle.ranges.protected_ranges_complete_proven",
        )
        protected_complete = (
            protected_complete_value is True and protected_complete_proven is True
        )
        self.protected_ranges = []
        seen_names: set[str] = set()
        required_protected_names = [
            "stage0_executable", "loader_code", "loader_stack",
            "descriptor_source", "descriptor_copy", "kernel_stack",
        ]
        if raw.get("boot_args_required"):
            required_protected_names.append("boot_args")
        if raw.get("device_tree_required"):
            required_protected_names.append("device_tree")
        if self.ranges["loader_heap"].get("present"):
            required_protected_names.append("loader_heap")
        if framebuffer_known and fb.get("present"):
            required_protected_names.append("framebuffer")
        protected_complete = protected_complete and all(
            self.ranges[name].get("valid")
            and self.ranges[name].get("ownership_proven")
            for name in required_protected_names
        )
        for name in (
            "stage0_executable",
            "loader_code",
            "loader_stack",
            "loader_heap",
            "descriptor_source",
            "descriptor_copy",
            "boot_args",
            "device_tree",
            "framebuffer",
            "kernel_stack",
        ):
            item = self.ranges[name]
            if item.get("present"):
                if item["name"] not in seen_names:
                    self.protected_ranges.append(item)
                    seen_names.add(item["name"])
        explicit_protected = raw.get("protected_ranges", [])
        explicit_reserved = raw.get("reserved_ranges", [])
        if not isinstance(explicit_protected, list):
            protected_complete = False
            explicit_protected = []
        if not isinstance(explicit_reserved, list):
            protected_complete = False
            explicit_reserved = []
        for index, item in enumerate(explicit_protected):
            parsed = range_fact(item, f"bundle.ranges.protected_ranges[{index}]")
            self.protected_ranges.append(parsed)
            protected_complete = protected_complete and parsed.get("valid") and parsed.get("ownership_proven")
        for index, item in enumerate(explicit_reserved):
            parsed = range_fact(item, f"bundle.ranges.reserved_ranges[{index}]")
            self.protected_ranges.append(parsed)
            protected_complete = protected_complete and parsed.get("valid") and parsed.get("ownership_proven")
        definition_errors: List[str] = []
        seen_definitions: Dict[str, Tuple[Any, ...]] = {}
        for item in self.protected_ranges:
            if item.get("present") and not item.get("valid"):
                definition_errors.append(f"{item.get('name')}:INVALID")
                continue
            if not item.get("present"):
                continue
            name = str(item.get("name"))
            identity = (item.get("address_space"), item.get("base"), item.get("length"))
            previous = seen_definitions.get(name)
            if previous is not None:
                error_kind = "CONFLICT" if previous != identity else "DUPLICATE"
                definition_errors.append(f"{name}:{error_kind}")
            else:
                seen_definitions[name] = identity
        definitions_ok = not definition_errors
        self.add_node(
            "range_definition_integrity",
            "DESIGN" if definitions_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if definitions_ok else "BLOCKED"
            ),
            "PROVEN" if definitions_ok else "NOT_PROVEN",
            "protected and reserved ranges have unique, valid definitions"
            if definitions_ok
            else "protected/reserved range definitions are invalid or duplicated",
            ("bundle.ranges",),
            critical=True,
            errors=definition_errors,
        )
        protected_complete = protected_complete and definitions_ok
        self.protected_complete = protected_complete
        self.add_node(
            "reserved_memory_completeness",
            "DESIGN" if protected_complete and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if protected_complete else "BLOCKED"
            ),
            "PROVEN" if protected_complete else "NOT_PROVEN",
            "all explicitly protected/reserved interval declarations are complete and bounded"
            if protected_complete
            else "reserved/protected interval list is absent, incomplete, or unproven",
            ("bundle.ranges.protected_ranges_complete", "bundle.ranges.reserved_ranges"),
            critical=True,
            protected_range_count=len(self.protected_ranges),
        )

    def _mapping_ok(
        self, mapping: Optional[Dict[str, Any]], permissions: Sequence[str]
    ) -> Tuple[bool, str]:
        if not isinstance(mapping, dict):
            return False, "mapping result absent"
        if mapping.get("status") != "fully_mapped":
            return False, f"mapping status is {mapping.get('status')}"
        if any(not segment.get("physical_dump_complete", False) for segment in mapping.get("segments", [])):
            return False, "physical table evidence is incomplete"
        for permission in permissions:
            if mapping.get(permission) is not True:
                return False, f"{permission} permission is not proven"
        return True, "complete mapping and requested permissions are proven"

    def _mapping_matches_physical(
        self,
        mapping: Optional[Dict[str, Any]],
        virtual_range: Dict[str, Any],
        physical_range: Dict[str, Any],
    ) -> Tuple[bool, str]:
        if not virtual_range.get("valid") or not physical_range.get("valid"):
            return False, "payload interval is invalid or unproven"
        if virtual_range.get("length") != physical_range.get("length"):
            return False, "payload VA/PA lengths differ"
        ok, reason = self._mapping_ok(mapping, ("readable",))
        if not ok:
            return False, reason
        for segment in mapping.get("segments", []):
            try:
                delta = segment["virtual_base"] - virtual_range["base"]
                expected_pa = checked_add_local(
                    physical_range["base"], delta, "payload translated PA"
                )
            except (KeyError, TypeError, VerificationInputError):
                return False, "payload translation interval is not representable"
            if segment.get("physical_base") != expected_pa:
                return False, "payload VA does not translate to declared payload PA"
        return True, "complete payload VA mapping translates to declared payload PA"
    def _find_elf_check(self, name: str) -> Optional[Dict[str, Any]]:
        if not self.elf_audit:
            return None
        for check in self.elf_audit.get("checks", []):
            if check.get("name") == name:
                return check
        return None

    def verify_mappings(self) -> None:
        if self.snapshot is None or self.elf is None:
            for name in (
                "stage0_executable_mapping",
                "entry_executable_mapping",
                "kernel_executable_mapping",
                "kernel_readable_mapping",
                "kernel_writable_mapping",
                "stack_mapping",
            ):
                self.add_node(
                    name,
                    "BLOCKED",
                    "NOT_PROVEN",
                    "image mapping cannot be checked without a local MMU snapshot",
                    ("mmu_snapshot", "image"),
                    critical=True,
                )
            return
        stage0 = self.ranges.get("stage0_executable", {})
        stage0_ok = (
            stage0.get("valid")
            and stage0.get("mapping_proven")
            and stage0.get("executable")
            and stage0.get("ownership_proven")
        )
        self.add_node(
            "stage0_executable_mapping",
            "DESIGN" if stage0_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if stage0_ok else "BLOCKED"
            ),
            "PROVEN" if stage0_ok else "NOT_PROVEN",
            "stage-0 executable mapping is an explicit bounded fact"
            if stage0_ok
            else "stage-0 mapping proof is not supplied",
            ("bundle.ranges.stage0_executable",),
            critical=True,
        )
        checks = {
            "section:.text.boot": (("readable", "executable"), "text.boot"),
            "section:.text": (("readable", "executable"), "text"),
            "section:.rodata": (("readable",), "rodata"),
            "section:.data": (("readable", "writable"), "data"),
            "section:.klog_buffer": (("readable", "writable"), "klog"),
            "section:.bss": (("readable", "writable"), "bss"),
            "section:.stack": (("readable", "writable"), "stack"),
            "symbol:stack": (("readable", "writable"), "stack"),
            "symbol:exception_vectors": (("readable", "executable"), "vectors"),
        }
        evaluated: Dict[str, Tuple[bool, str]] = {}
        for check_name, (permissions, _) in checks.items():
            check = self._find_elf_check(check_name)
            mapping = check.get("mapping_fact") if check else None
            evaluated[check_name] = self._mapping_ok(mapping, permissions)
            if check and check.get("permission_comparison", {}).get("mismatches"):
                self.security_warnings.append(
                    {
                        "name": "ELF_PERMISSION_MISMATCH",
                        "status": "UNKNOWN",
                        "section": check_name,
                        "mismatches": check["permission_comparison"]["mismatches"],
                        "reason": "ELF intent differs from supplied page-table permissions",
                    }
                )
        exec_ok = evaluated["section:.text.boot"][0] and evaluated["section:.text"][0]
        read_names = (
            "section:.text.boot",
            "section:.text",
            "section:.rodata",
            "section:.data",
            "section:.klog_buffer",
            "section:.bss",
            "section:.stack",
        )
        write_names = (
            "section:.data",
            "section:.klog_buffer",
            "section:.bss",
            "section:.stack",
        )
        read_ok = all(evaluated[name][0] for name in read_names)
        write_ok = all(evaluated[name][0] for name in write_names)
        stack_range = self.ranges.get("kernel_stack", {})
        sp_value = self.cpu.get("sp", {}).get("value")
        sp_in_range = (
            sp_value is not None
            and stack_range.get("valid")
            and stack_range["base"] <= sp_value <= stack_range["end"]
        )
        stack_ok = (
            evaluated["symbol:stack"][0]
            and evaluated["symbol:stack"][1] == "complete mapping and requested permissions are proven"
            and sp_in_range
        )
        evidence = self._status_for_mapping()
        for node_name, ok, reason, sources in (
            (
                "kernel_executable_mapping",
                exec_ok,
                "text and text.boot are readable and executable" if exec_ok else "kernel executable mapping is incomplete",
                ("ELF:section:.text.boot", "ELF:section:.text", "mmu_snapshot"),
            ),
            (
                "kernel_readable_mapping",
                read_ok,
                "all allocated DreyzeOS sections are readable" if read_ok else "one or more required readable sections are not mapped",
                tuple(f"ELF:{name}" for name in read_names),
            ),
            (
                "kernel_writable_mapping",
                write_ok,
                "data, klog, BSS, and stack are writable/readable" if write_ok else "one or more required writable sections are not writable",
                tuple(f"ELF:{name}" for name in write_names),
            ),
            (
                "stack_mapping",
                stack_ok,
                "entire ELF stack interval is readable/writable" if stack_ok else "stack interval is not fully writable/readable",
                ("ELF:symbol:stack", "bundle.cpu_state.sp", "bundle.ranges.kernel_stack"),
            ),
        ):
            self.add_node(
                node_name,
                evidence if ok else "BLOCKED",
                "PROVEN" if ok else "NOT_PROVEN",
                reason,
                sources,
                critical=True,
            )
        payload_virtual = self.ranges.get("payload_virtual", {})
        payload_physical = self.ranges.get("payload_physical", {})
        payload_mapping: Optional[Dict[str, Any]] = None
        payload_mapping_ok = False
        payload_mapping_reason = "payload translation proof is unavailable"
        if (
            payload_virtual.get("valid")
            and payload_physical.get("valid")
            and payload_virtual.get("length") == payload_physical.get("length")
        ):
            payload_mapping = analyze_range(
                self.snapshot,
                payload_virtual["base"],
                payload_virtual["length"],
            )
            payload_mapping_ok, payload_mapping_reason = (
                self._mapping_matches_physical(
                    payload_mapping, payload_virtual, payload_physical
                )
            )
        self.add_node(
            "payload_translation_consistency",
            evidence if payload_mapping_ok else "BLOCKED",
            "PROVEN" if payload_mapping_ok else "NOT_PROVEN",
            payload_mapping_reason,
            (
                "bundle.ranges.payload_virtual",
                "bundle.ranges.payload_physical",
                "mmu_snapshot:payload-walk",
            ),
            critical=True,
            mapping=payload_mapping,
        )
        entry_fact = self.root.get("control_transfer", {})
        entry_value = None
        if isinstance(entry_fact, dict):
            raw_entry = entry_fact.get("entry_pc")
            parsed_entry = present_fact(raw_entry, "control_transfer.entry_pc")
            if parsed_entry.get("value_proven"):
                entry_value = parsed_entry.get("value")
        entry_mapping: Optional[Dict[str, Any]] = None
        if entry_value is not None:
            entry_mapping = analyze_range(self.snapshot, entry_value, 4)
        entry_ok, entry_reason = self._mapping_ok(entry_mapping, ("readable", "executable"))
        self.entry_mapping = entry_mapping
        self.add_node(
            "entry_executable_mapping",
            evidence if entry_ok else "BLOCKED",
            "PROVEN" if entry_ok else "NOT_PROVEN",
            entry_reason,
            ("control_transfer.entry_pc", "mmu_snapshot:entry-walk"),
            critical=True,
            mapping=entry_mapping,
        )
        # A complete vector mapping is useful evidence but is not a new hardware write.
        vector_ok = evaluated["symbol:exception_vectors"][0]
        self.add_node(
            "exception_vector_mapping",
            evidence if vector_ok else "BLOCKED",
            "PROVEN" if vector_ok else "NOT_PROVEN",
            "exception vector span is readable/executable" if vector_ok else "vector span mapping is incomplete",
            ("ELF:_exception_vectors_base", "mmu_snapshot"),
            critical=False,
        )

    def verify_objects(self) -> None:
        raw_ranges = self.root.get("ranges", {})
        if not isinstance(raw_ranges, dict):
            raw_ranges = {}
        boot_required = strict_bool(
            raw_ranges,
            "boot_args_required",
            False,
            "bundle.ranges.boot_args_required",
        ) is True
        dt_required = strict_bool(
            raw_ranges,
            "device_tree_required",
            False,
            "bundle.ranges.device_tree_required",
        ) is True
        boot_range = self.ranges.get("boot_args", {})
        dt_range = self.ranges.get("device_tree", {})
        descriptor_ranges = self.descriptor.get("ranges", {}) if self.descriptor else {}
        descriptor_boot = descriptor_ranges.get("boot_args", {})
        descriptor_dt = descriptor_ranges.get("device_tree", {})
        boot_range_match = (
            not boot_required
            or (
                boot_range.get("valid")
                and descriptor_boot.get("base") == boot_range.get("base")
                and descriptor_boot.get("length") == boot_range.get("length")
            )
        )
        dt_range_match = (
            not dt_required
            or (
                dt_range.get("valid")
                and descriptor_dt.get("base") == dt_range.get("base")
                and descriptor_dt.get("length") == dt_range.get("length")
            )
        )
        boot_spec = self.root.get("boot_args")
        dt_spec = self.root.get("device_tree")
        boot_data, boot_artifact = self.artifact_bytes(
            "boot_args", boot_spec, required=False
        )
        dt_data, dt_artifact = self.artifact_bytes(
            "device_tree", dt_spec, required=False
        )
        def complete_required_object(spec: Any, artifact: Dict[str, Any], data: Optional[bytes]) -> bool:
            if not isinstance(spec, dict):
                return False
            if artifact.get("proof_state") != "PROVEN" or data is None:
                return False
            if not valid_hash(spec.get("sha256")):
                return False
            try:
                declared_length = parse_u64(spec.get("length"), "object.length")
            except VerificationInputError:
                return False
            complete = strict_bool(spec, "complete", False, "object.complete")
            return complete is True and len(data) == declared_length

        boot_complete = (
            complete_required_object(boot_spec, boot_artifact, boot_data)
            if boot_required
            else True
        )
        dt_complete = (
            complete_required_object(dt_spec, dt_artifact, dt_data)
            if dt_required
            else True
        )
        boot_ok = boot_range_match
        boot_details: Dict[str, Any] = {}
        if boot_data is not None:
            boot_ok = boot_ok and len(boot_data) >= 0x46C
            if len(boot_data) >= 0x6C:
                values = struct.unpack_from("<HHI" + "Q" * 10 + "IIQI", boot_data, 0)
                boot_details = {
                    "revision": values[0],
                    "version": values[1],
                    "virt_base": values[3],
                    "phys_base": values[4],
                    "mem_size": values[5],
                    "device_tree_p": values[15],
                    "device_tree_length": values[16],
                    "layout_basis": "XNU ARM64 boot_args layout; not DreyzeOS loader ABI",
                }
                if values[15] != 0 or values[16] != 0:
                    nested_ok = (
                        dt_data is not None
                        and dt_range.get("valid")
                        and range_contains(
                            dt_range, values[15], values[16]
                        )
                    )
                    boot_ok = boot_ok and nested_ok
                    boot_details["nested_device_tree_bounds"] = nested_ok
        elif boot_spec is not None or boot_required:
            boot_ok = False
        boot_ok = boot_ok and boot_complete
        self.add_node(
            "boot_args_bounds",
            "DESIGN" if boot_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if boot_ok else "BLOCKED"
            ),
            "PROVEN" if boot_ok else "NOT_PROVEN",
            "boot_args range is independently bounded; local XNU object is validated when supplied"
            if boot_ok
            else "boot_args range/object is missing, malformed, or nested DeviceTree bounds fail",
            ("bundle.ranges.boot_args", "bundle.boot_args"),
            critical=boot_required,
            **boot_details,
        )
        dt_ok = dt_range_match
        dt_details: Dict[str, Any] = {}
        if dt_data is not None:
            if not dt_range.get("valid") or len(dt_data) > dt_range.get("length", 0):
                dt_ok = False
            else:
                try:
                    parser_path = Path(__file__).resolve().parent / "device_tree_dump.py"
                    spec = importlib.util.spec_from_file_location(
                        "dreyzeos_device_tree_dump", parser_path
                    )
                    module = importlib.util.module_from_spec(spec)
                    assert spec and spec.loader
                    spec.loader.exec_module(module)
                    root, end = module.parse_adt(dt_data)
                    dt_ok = dt_ok and end <= len(dt_data)
                    dt_details = {
                        "parsed": True,
                        "consumed_bytes": end,
                        "local_length": len(dt_data),
                        "layout_basis": "bounded host ADT parser",
                    }
                except (OSError, ValueError, RecursionError, struct.error) as exc:
                    dt_ok = False
                    dt_details = {"parsed": False, "error": str(exc)}
        elif dt_spec is not None or dt_required:
            dt_ok = False
        dt_ok = dt_ok and dt_complete
        self.add_node(
            "device_tree_bounds",
            "DESIGN" if dt_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if dt_ok else "BLOCKED"
            ),
            "PROVEN" if dt_ok else "NOT_PROVEN",
            "DeviceTree interval is independent and bounded; bytes are parsed only locally"
            if dt_ok
            else "DeviceTree range/object is missing, malformed, or out of bounds",
            ("bundle.ranges.device_tree", "bundle.device_tree"),
            critical=dt_required,
            **dt_details,
        )

    def verify_collisions(self) -> None:
        pa = self.ranges.get("payload_physical", {})
        va = self.ranges.get("payload_virtual", {})
        collisions: List[Dict[str, Any]] = []
        if self.protected_complete and pa.get("valid") and va.get("valid"):
            for protected in self.protected_ranges:
                payload = pa if protected.get("address_space") == "physical" else va
                if range_overlaps(payload, protected):
                    collisions.append(
                        {
                            "payload": payload.get("name"),
                            "protected": protected.get("name"),
                            "address_space": protected.get("address_space"),
                            "payload_base": payload.get("base"),
                            "protected_base": protected.get("base"),
                        }
                    )
        collision_ok = (
            self.protected_complete
            and pa.get("valid")
            and va.get("valid")
            and not collisions
        )
        self.add_node(
            "collision_audit",
            "DESIGN" if collision_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if collision_ok else "BLOCKED"
            ),
            "PROVEN" if collision_ok else "NOT_PROVEN",
            "physical and virtual payload intervals avoid every complete protected range"
            if collision_ok
            else "collision audit is incomplete or an interval overlaps",
            (
                "bundle.ranges.payload_physical",
                "bundle.ranges.payload_virtual",
                "bundle.ranges.protected_ranges",
                "bundle.ranges.reserved_ranges",
            ),
            depends_on=("reserved_memory_completeness",),
            critical=True,
            collisions=collisions,
            protected_range_count=len(self.protected_ranges),
        )

    def verify_control_and_persistence(self) -> None:
        control = self.root.get("control_transfer", {})
        if not isinstance(control, dict):
            control = {}
        entry_fact = present_fact(control.get("entry_pc"), "bundle.control_transfer.entry_pc")
        target_ok = control.get("target") == "DreyzeOS"
        entry_end: Optional[int] = None
        if self.descriptor is not None:
            try:
                entry_end = checked_add_local(
                    self.descriptor.get("payload_va", 0),
                    self.descriptor.get("payload_size", 0),
                    "descriptor payload VA",
                )
            except VerificationInputError:
                entry_end = None
        control_ok = (
            entry_fact.get("value_proven")
            and strict_bool(control, "proven", False, "bundle.control_transfer.proven") is True
            and target_ok
            and self.descriptor is not None
            and entry_fact.get("value") is not None
            and self.descriptor.get("payload_va") is not None
            and self.descriptor["payload_va"] <= entry_fact["value"]
            and entry_end is not None
            and entry_fact["value"] < entry_end
            and self._elf_symbol("_start") == entry_fact.get("value")
        )
        self.add_node(
            "control_transfer",
            "DESIGN" if control_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if control_ok else "BLOCKED"
            ),
            "PROVEN" if control_ok else "NOT_PROVEN",
            "bounded entry PC and explicit DreyzeOS control-transfer proof are supplied"
            if control_ok
            else "mapping evidence cannot substitute for a control-transfer proof",
            ("bundle.control_transfer", "ELF:_start", "handoff_descriptor.payload_va"),
            critical=True,
            entry_pc=fact_summary(entry_fact),
            target=control.get("target"),
            proven=strict_bool(control, "proven", False, "bundle.control_transfer.proven") is True,
        )
        persistence = self.root.get("persistence", {})
        required_fact = bool_fact(
            persistence.get("persistent_write_required")
            if isinstance(persistence, dict)
            else None,
            "bundle.persistence.persistent_write_required",
        )
        persistence_ok = (
            required_fact.get("value_proven")
            and required_fact.get("value") is False
        )
        self.add_node(
            "no_persistent_write",
            "DESIGN" if persistence_ok and self.evidence_status == "DESIGN" else (
                "CONFIRMED" if persistence_ok else "BLOCKED"
            ),
            "PROVEN" if persistence_ok else "NOT_PROVEN",
            "persistent write is explicitly proven unnecessary"
            if persistence_ok
            else "persistent-write requirement is absent, unproven, or true",
            ("bundle.persistence.persistent_write_required",),
            critical=True,
            persistent_write_required=fact_summary(required_fact),
        )

    def finalize(self) -> Dict[str, Any]:
        # A conflict is itself a critical blocker even if another node happened
        # to be marked proven.
        if self.conflicts:
            self.add_node(
                "evidence_conflicts",
                "BLOCKED",
                "NOT_PROVEN",
                "proven evidence values disagree; verifier never chooses silently",
                tuple(item["name"] for item in self.conflicts),
                critical=True,
                conflicts=self.conflicts,
            )
        requirements: Dict[str, Dict[str, Any]] = {}
        for name in CRITICAL_ORDER:
            if name in self.nodes:
                requirements[name] = self.nodes[name]
        for name, node in self.nodes.items():
            if node.get("critical") and name not in requirements:
                requirements[name] = node
        blockers = [
            {
                "requirement": name,
                "status": node["status"],
                "reason": node["reason"],
                "evidence_sources": node["evidence_sources"],
                "depends_on": node["depends_on"],
            }
            for name, node in requirements.items()
            if node.get("proof_state") != "PROVEN"
        ]
        offline_ready = not blockers
        hardware_ready = (
            offline_ready
            and self.evidence_status == "CONFIRMED"
            and self.target_provenance_proven
            and (
                self.root.get("source", {}).get("kind")
                if isinstance(self.root.get("source"), dict)
                else None
            ) != "synthetic"
        )
        report: Dict[str, Any] = {
            "ok": True,
            "schema": SCHEMA,
            "verifier": {
                "mode": "HOST_OFFLINE_ONLY",
                "hardware_access": False,
                "pointer_dereference": False,
                "payload_execution": False,
                "control_transfer_execution": False,
            },
            "bundle": {
                "path": str(self.bundle_path),
                "source": self.root.get("source", {}),
                "evidence_status": self.evidence_status,
            },
            "bundle_integrity": self.nodes.get("bundle_integrity"),
            "provenance_envelope": self.nodes.get("provenance_envelope"),
            "target": {
                "metadata_match": self.target_match,
                "metadata_status": self.metadata_status,
                "same_session_provenance_status": self.same_session_status,
                "physical_identity_status": self.physical_identity_status,
                "physical_identity_proven": self.identity_proven,
                "technical_target_provenance_ready": self.technical_target_provenance_ready,
                "identity_proven": self.identity_proven,
                "legacy_identity_claim": self.legacy_identity_claim,
                "node": self.nodes.get("target_metadata_match"),
                "identity_node": self.nodes.get("physical_identity_provenance"),
                "provenance_node": self.nodes.get("target_provenance"),
                "provenance_envelope": self.provenance_envelope_report,
            },
            "artifacts": self.artifacts,
            "descriptor": {
                "value": self.descriptor,
                "structure": self.nodes.get("descriptor_structure"),
                "root_of_trust": self.nodes.get("descriptor_root_of_trust"),
                "verified_flag_is_assertion_only": True,
            },
            "cpu_state": {
                "facts": {
                    name: fact_summary(value)
                    for name, value in getattr(self, "cpu", {}).items()
                },
                "nodes": {
                    name: self.nodes.get(name)
                    for name in (
                        "entry_el1",
                        "initial_sp",
                        "daif_normalized",
                        "translation_policy",
                        "cache_policy",
                        "cpu_consistency",
                    )
                    if name in self.nodes
                },
            },
            "mmu": {
                "manifest": str(self.snapshot_path) if self.snapshot_path else None,
                "snapshot_source": self.snapshot.source if self.snapshot else None,
                "register_provenance": self.nodes.get("mmu_register_provenance"),
                "mapping_evidence_status": self._status_for_mapping(),
            },
            "image": {
                "path": str(self.elf_path) if self.elf_path else None,
                "elf_header": self.elf.header if self.elf else None,
                "audit": self.elf_audit,
                "nodes": {
                    name: self.nodes.get(name)
                    for name in (
                        "image_integrity",
                        "image_shape",
                        "kernel_executable_mapping",
                        "kernel_readable_mapping",
                        "kernel_writable_mapping",
                        "stack_mapping",
                        "entry_executable_mapping",
                        "payload_translation_consistency",
                        "exception_vector_mapping",
                    )
                    if name in self.nodes
                },
            },
            "runtime_memory": getattr(self, "runtime_memory", {}),
            "ranges": {
                name: value
                for name, value in self.ranges.items()
            },
            "objects": {
                "boot_args": self.nodes.get("boot_args_bounds"),
                "device_tree": self.nodes.get("device_tree_bounds"),
            },
            "collision": self.nodes.get("collision_audit"),
            "warnings": self.security_warnings,
            "evidence_graph": {
                "nodes": self.nodes,
                "conflicts": self.conflicts,
            },
            "readiness": {
                "offline_contract_result": "READY" if offline_ready else "BLOCKED",
                "hardware_evidence_status": self.evidence_status,
                "loader_contract": "READY" if hardware_ready else "BLOCKED",
                "first_hardware_execution": "READY" if hardware_ready else "NOT_READY",
                "requirements": requirements,
                "blocking_requirements": blockers,
                "reason": (
                    "all offline dependencies are proven; hardware readiness still "
                    "depends on confirmed target metadata/session provenance and target evidence status"
                    if offline_ready and not hardware_ready
                    else "one or more critical evidence dependencies are not proven"
                    if not offline_ready
                    else "target metadata consistency, same-session provenance, and all hardware evidence are proven"
                ),
            },
            "control_transfer": self.nodes.get("control_transfer"),
            "persistence": self.nodes.get("no_persistent_write"),
        }
        return report

    def verify(self) -> Dict[str, Any]:
        if self.root.get("schema") != SCHEMA:
            raise VerificationInputError(
                "BUNDLE_SCHEMA_UNSUPPORTED",
                f"schema must be {SCHEMA}",
            )
        if self.root.get("architecture") != "aarch64":
            raise VerificationInputError(
                "UNSUPPORTED_ARCHITECTURE",
                "bundle architecture must be aarch64",
            )
        self.verify_target()
        self.verify_integrity()
        self.verify_provenance()
        self.verify_descriptor()
        self.verify_mmu()
        self.verify_image()
        self.verify_cpu()
        self.verify_ranges()
        self.verify_objects()
        self.verify_artifact_aliases()
        self.verify_mappings()
        self.verify_control_and_persistence()
        self.verify_collisions()
        return self.finalize()


def verify_bundle(path: str | Path) -> Dict[str, Any]:
    return BundleVerifier(path).verify()


def human_report(report: Dict[str, Any]) -> str:
    readiness = report.get("readiness", {})
    lines = ["DreyzeOS Offline Handoff Verification", ""]
    display = (
        ("Image integrity", "image_integrity"),
        ("Descriptor structure", "descriptor_structure"),
        ("Descriptor root of trust", "descriptor_root_of_trust"),
        ("Entry EL1", "entry_el1"),
        ("Initial SP", "initial_sp"),
        ("DAIF normalized", "daif_normalized"),
        ("Translation policy", "translation_policy"),
        ("Cache policy", "cache_policy"),
        ("Runtime DRAM", "runtime_memory_provenance"),
        ("Entry mapping", "entry_executable_mapping"),
        ("Payload PA mapping", "payload_translation_consistency"),
        ("Kernel mapping", "kernel_readable_mapping"),
        ("Stack mapping", "stack_mapping"),
        ("Collision audit", "collision_audit"),
        ("Control transfer", "control_transfer"),
        ("Persistent write", "no_persistent_write"),
    )
    nodes = report.get("evidence_graph", {}).get("nodes", {})
    for label, name in display:
        node = nodes.get(name)
        status = node.get("status", "UNKNOWN") if node else "UNKNOWN"
        proof = node.get("proof_state", "NOT_PROVEN") if node else "NOT_PROVEN"
        lines.append(f"{label:<30} {status:<10} [{proof}]")
    lines.extend(
        [
            "",
        f"Offline contract result ...... {readiness.get('offline_contract_result', 'BLOCKED')}",
        f"Hardware evidence status ..... {readiness.get('hardware_evidence_status', 'UNKNOWN')}",
        f"TARGET_METADATA_STATUS = {report.get('target', {}).get('metadata_status', 'UNKNOWN')}",
        f"SAME_SESSION_PROVENANCE_STATUS = {report.get('target', {}).get('same_session_provenance_status', 'UNKNOWN')}",
        f"PHYSICAL_IDENTITY_STATUS = {report.get('target', {}).get('physical_identity_status', 'NOT_PROVEN')}",
        f"TECHNICAL_TARGET_PROVENANCE_READY = {str(report.get('target', {}).get('technical_target_provenance_ready', False)).lower()}",
        f"LOADER CONTRACT .............. {readiness.get('loader_contract', 'BLOCKED')}",
            f"FIRST HARDWARE EXECUTION ..... {readiness.get('first_hardware_execution', 'NOT_READY')}",
        ]
    )
    blockers = readiness.get("blocking_requirements", [])
    if blockers:
        lines.append("")
        lines.append("Blocking requirements:")
        for item in blockers:
            lines.append(f"- {item['requirement']}: {item['reason']}")
    return "\n".join(lines)


def provenance_human_report(report: Dict[str, Any]) -> str:
    target = report.get("target", {})
    requirements = report.get("requirements", {})
    lines = [
        "DreyzeOS Provenance Envelope Validation",
        "",
        f"Envelope ...................... {report.get('status', 'UNKNOWN')}",
        f"Metadata match ................ {target.get('metadata_match')}",
        f"TARGET_METADATA_STATUS = {target.get('metadata_status', 'UNKNOWN')}",
        f"SAME_SESSION_PROVENANCE_STATUS = {target.get('same_session_provenance_status', 'UNKNOWN')}",
        f"PHYSICAL_IDENTITY_STATUS = {target.get('physical_identity_status', 'NOT_PROVEN')}",
        f"TECHNICAL_TARGET_PROVENANCE_READY = {str(target.get('technical_target_provenance_ready', False)).lower()}",
        f"EV-000A = {requirements.get('EV-000A', {}).get('status', 'BLOCKED')}",
        f"EV-000B = {requirements.get('EV-000B', {}).get('status', 'BLOCKED')}",
        f"EV-000C = {requirements.get('EV-000C', {}).get('status', 'NOT_PROVEN')}",
        f"Artifact coverage complete .... {report.get('coverage', {}).get('coverage_complete_claimed_and_consistent')}",
        f"EV-000 ......................... {requirements.get('EV-000', {}).get('status', 'BLOCKED')}",
        f"EV-027 ......................... {requirements.get('EV-027', {}).get('status', 'BLOCKED')}",
        "",
        "SHA-256 proves local byte equality only; it does not authenticate a capture.",
        "PHYSICAL DEVICE IDENTITY = " + ("PROVEN" if target.get("physical_identity_proven") else "NOT_PROVEN"),
        "LOADER CONTRACT = BLOCKED",
        "FIRST HARDWARE EXECUTION = NOT READY",
    ]
    for item in report.get("conflicts", []):
        lines.append(f"CONFLICT: {item.get('code')}: {item.get('detail')}")
    for item in report.get("errors", []):
        lines.append(f"BLOCKER: {item}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a local DreyzeOS handoff evidence bundle offline. "
            "No hardware or payload execution is performed."
        )
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--bundle", help="local evidence bundle JSON")
    input_group.add_argument(
        "--provenance-envelope",
        help="validate a standalone host-only provenance envelope without a full bundle",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    output.add_argument("--human", action="store_true", help="emit concise human report")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return exit 1 when the offline contract is blocked",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        provenance_only = args.provenance_envelope is not None
        if provenance_only:
            envelope_path = Path(args.provenance_envelope).resolve()
            envelope = load_json(envelope_path)
            report = validate_envelope(
                envelope,
                envelope_path.parent,
                EXPECTED_TARGET,
                path_resolver=safe_bundle_path,
                file_hasher=hash_file,
            )
        else:
            report = verify_bundle(args.bundle)
    except VerificationInputError as exc:
        output = exc.as_dict()
        if args.json:
            print(json.dumps(output, indent=2, sort_keys=True))
        else:
            print(f"DreyzeOS Offline Handoff Verification\nTOOL ERROR: {exc.code}: {exc.message}")
        return 1
    except (OSError, SnapshotError, ValueError, TypeError, KeyError, struct.error, RecursionError) as exc:
        code = getattr(exc, "code", "VERIFIER_ERROR")
        output = {"ok": False, "tool_error": code, "error": str(exc)}
        if args.json:
            print(json.dumps(output, indent=2, sort_keys=True))
        else:
            print(f"DreyzeOS Offline Handoff Verification\nTOOL ERROR: {code}: {exc}")
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif provenance_only:
        print(provenance_human_report(report))
    else:
        print(human_report(report))
    if args.strict:
        if provenance_only:
            if report.get("requirements", {}).get("EV-000", {}).get("proof_state") != "PROVEN":
                return 1
        elif report["readiness"]["offline_contract_result"] != "READY":
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

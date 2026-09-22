#!/usr/bin/env python3
"""Host-only end-to-end tests for the unified handoff evidence verifier."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from handoff_evidence_verifier import (  # noqa: E402
    ABI_MAGIC,
    ABI_SIZE,
    ABI_VERSION,
    FLAG_ENTRY_EL_KNOWN,
    FLAG_MMU_STATE_KNOWN,
    FLAG_PAYLOAD_LOCATION_KNOWN,
    FLAG_VERIFIED,
    ElfImage,
    bool_fact as parse_bool_fact,
    human_report,
    present_fact,
    verify_bundle,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fact(value: Any, proven: bool = True) -> Dict[str, Any]:
    return {
        "value": value,
        "value_present": True,
        "value_proven": proven,
    }


def bool_fact(value: bool, proven: bool = True) -> Dict[str, Any]:
    return {
        "value": value,
        "value_present": True,
        "value_proven": proven,
    }


def range_fact(
    name: str,
    base: int,
    length: int,
    address_space: str,
    *,
    readable: bool = False,
    writable: bool = False,
    executable: bool = False,
    ownership: bool = True,
    mapping: bool = False,
) -> Dict[str, Any]:
    return {
        "name": name,
        "base": hex(base),
        "length": hex(length),
        "address_space": address_space,
        "present": True,
        "bounds_proven": True,
        "ownership_proven": ownership,
        "readable": readable,
        "writable": writable,
        "executable": executable,
        "mapping_proven": mapping,
    }


def make_adt() -> bytes:
    name = b"synthetic\x00"
    prop = name.ljust(32, b"\x00") + struct.pack("<I", len(name)) + name
    prop += b"\x00" * ((-len(name)) & 3)
    return struct.pack("<II", 1, 0) + prop


def make_boot_args(device_tree_base: int, device_tree_length: int) -> bytes:
    data = bytearray(0x500)
    struct.pack_into("<HHI", data, 0, 1, 1, 0)
    struct.pack_into("<Q", data, 0x08, 0)
    struct.pack_into("<Q", data, 0x10, 0x90000000)
    struct.pack_into("<Q", data, 0x18, 0x00200000)
    struct.pack_into("<Q", data, 0x20, 0x10000C058)
    struct.pack_into("<Q", data, 0x60, device_tree_base)
    struct.pack_into("<I", data, 0x68, device_tree_length)
    return bytes(data)


def page_descriptor(
    physical_base: int,
    *,
    executable: bool,
    writable: bool,
    pxn: bool = False,
) -> int:
    value = physical_base | 0x3 | (1 << 10)  # valid page + AF
    if not writable:
        value |= 2 << 6  # AP[2:1] = read-only at EL1
    if not executable or pxn:
        value |= 1 << 53
    value |= 1 << 54  # UXN
    return value


def write_snapshot(
    directory: Path,
    elf_path: Path,
    *,
    entry_pxn: bool = False,
    stack_read_only: bool = False,
    incomplete: bool = False,
    tcr_value: int | None = None,
    ttbr0_proven: bool = True,
) -> Tuple[Path, int, int, int]:
    elf = ElfImage(elf_path)
    image_base = elf.symbols["_start"]["value"]
    stack_bottom = elf.symbols["__stack_bottom"]["value"]
    stack_top = elf.symbols["__stack_top"]["value"]
    map_end = (stack_top + 0xFFF) & ~0xFFF
    payload_pa = 0x90000000
    tcr = (
        (16)
        | (16 << 16)
        | (2 << 30)  # TTBR1 TG1 = 4 KiB
        | (5 << 32)  # IPS = 48 bit
    )
    if tcr_value is not None:
        tcr = tcr_value
    mair = 0x00000000000000FF
    ttbr0 = 0x1000
    ttbr1 = 0x8000
    words = [
        {"offset": "0x0", "value": "0x2003"},
        {"offset": "0x1020", "value": "0x3003"},
        {"offset": "0x2000", "value": "0x4003"},
    ]
    # One L3 table covers the complete synthetic image, which stays below 2 MiB.
    l3_physical = 0x4000
    page = image_base & ~0xFFF
    while page < map_end:
        executable = page < 0x100005000
        writable = page >= 0x100008000
        if stack_read_only and page >= (stack_bottom & ~0xFFF):
            writable = False
        pxn = entry_pxn and page == image_base
        physical = payload_pa + (page - image_base)
        words.append(
            {
                "offset": hex(0x3000 + (page - image_base) // 0x1000 * 8),
                "value": hex(
                    page_descriptor(
                        physical,
                        executable=executable,
                        writable=writable,
                        pxn=pxn,
                    )
                ),
            }
        )
        page += 0x1000
    manifest = {
        "schema": "dreyzeos.mmu_snapshot.v1",
        "architecture": "aarch64",
        "target": {
            "model": "Watch4,2",
            "board": "N131bAP",
            "soc": "T8006",
            "firmware": "watchOS 10.6.1",
            "build": "21U580",
            "architecture": "aarch64",
        },
        "source": {
            "kind": "synthetic",
            "description": "repository-owned end-to-end fixture",
        },
        "evidence_status": "DESIGN",
        "registers": {
            "current_el": fact(1),
            "sctlr_el1": fact(1),
            "tcr_el1": fact(tcr),
            "ttbr0_el1": fact(ttbr0, ttbr0_proven),
            "ttbr1_el1": fact(ttbr1),
            "mair_el1": fact(mair),
            "vbar_el1": fact(0x100000800),
            "daif": fact(0xF),
            "sp": fact(stack_top),
        },
        "physical_memory_regions": [
            {
                "physical_base": "0x1000",
                "length": "0x5000",
                "memory_bytes_present": True,
                "memory_range_complete": not incomplete,
                "data_words": words,
            }
        ],
    }
    path = directory / "mmu.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    loaded_end = max(
        section["address"] + section["size"]
        for section in elf.sections
        if section["flags"] & 0x2 and section["size"] and section["type"] != 8
    )
    return path, tcr, ttbr0, loaded_end - image_base


def pack_descriptor(
    path: Path,
    *,
    payload_pa: int,
    payload_va: int,
    payload_size: int,
    boot_base: int,
    boot_length: int,
    dt_base: int,
    dt_length: int,
    magic: int = ABI_MAGIC,
) -> None:
    flags = (
        FLAG_VERIFIED
        | FLAG_ENTRY_EL_KNOWN
        | FLAG_PAYLOAD_LOCATION_KNOWN
        | FLAG_MMU_STATE_KNOWN
    )
    data = bytearray(
        struct.pack(
            "<QIIQIIQQQIIQQ",
            magic,
            ABI_VERSION,
            ABI_SIZE,
            flags,
            1,
            0,
            payload_pa,
            payload_va,
            payload_size,
            1,
            0,
            0,
            0,
        )
    )
    data += struct.pack("<QQII", boot_base, boot_length, 1, 0)
    data += struct.pack("<QQII", dt_base, dt_length, 1, 0)
    assert len(data) == ABI_SIZE
    path.write_bytes(data)


def build_ready_bundle(root: Path, **snapshot_options: Any) -> Path:
    image_source = ROOT / "build" / "DreyzeOS.elf"
    image_path = root / "DreyzeOS.elf"
    shutil.copyfile(image_source, image_path)
    elf = ElfImage(image_path)
    image_base = elf.symbols["_start"]["value"]
    stack_bottom = elf.symbols["__stack_bottom"]["value"]
    stack_top = elf.symbols["__stack_top"]["value"]
    snapshot_path, tcr, ttbr0, payload_size = write_snapshot(
        root, image_path, **snapshot_options
    )
    dt_base = 0x90105000
    dt = make_adt()
    dt_path = root / "device_tree.bin"
    dt_path.write_bytes(dt)
    boot_base = 0x90104000
    boot_path = root / "boot_args.bin"
    boot_path.write_bytes(make_boot_args(dt_base, len(dt)))
    descriptor_path = root / "descriptor.bin"
    pack_descriptor(
        descriptor_path,
        payload_pa=0x90000000,
        payload_va=image_base,
        payload_size=payload_size,
        boot_base=boot_base,
        boot_length=0x500,
        dt_base=dt_base,
        dt_length=0x1000,
    )
    ranges: Dict[str, Any] = {
        "payload_physical": range_fact(
            "payload-pa", 0x90000000, payload_size, "physical",
            readable=True, ownership=True,
        ),
        "payload_virtual": range_fact(
            "payload-va", image_base, payload_size, "virtual",
            readable=True, executable=True, ownership=True,
        ),
        "stage0_executable": range_fact(
            "stage0", 0x40000000, 0x1000, "virtual",
            readable=True, executable=True, ownership=True, mapping=True,
        ),
        "loader_code": range_fact(
            "loader-code", 0x90100000, 0x1000, "physical",
            readable=True, executable=True,
        ),
        "loader_stack": range_fact(
            "loader-stack", 0x90101000, 0x1000, "physical",
            writable=True,
        ),
        "loader_heap": range_fact(
            "loader-heap", 0x90102000, 0x1000, "physical",
            writable=True,
        ),
        "descriptor_source": range_fact(
            "descriptor-source", 0x90103000, 0x1000, "physical",
            readable=True,
        ),
        "descriptor_copy": range_fact(
            "descriptor-copy", 0x90103800, 0x1000, "physical",
            writable=True,
        ),
        "boot_args": range_fact(
            "boot_args", boot_base, 0x500, "physical",
            readable=True,
        ),
        "device_tree": range_fact(
            "device_tree", dt_base, 0x1000, "physical",
            readable=True,
        ),
        "framebuffer": range_fact(
            "framebuffer", 0x90106000, 0x1000, "physical",
        ),
        "kernel_stack": range_fact(
            "kernel-stack", stack_bottom, stack_top - stack_bottom, "virtual",
            readable=True, writable=True,
        ),
        "boot_args_required": True,
        "device_tree_required": True,
        "framebuffer_reservation_known": True,
        "framebuffer_reservation_known_proven": True,
        "protected_ranges_complete": True,
        "protected_ranges_complete_proven": True,
        "reserved_ranges": [
            range_fact("reserved", 0x90107000, 0x1000, "physical")
        ],
    }
    bundle = {
        "schema": "dreyzeos.handoff_evidence.v1",
        "architecture": "aarch64",
        "target": {
            "model": "Watch4,2",
            "board": "N131bAP",
            "soc": "T8006",
            "firmware": "watchOS 10.6.1",
            "build": "21U580",
            "architecture": "aarch64",
            "identity_proven": False,
        },
        "source": {
            "kind": "synthetic",
            "description": "repository-owned synthetic complete contract model",
            "evidence_status": "DESIGN",
        },
        "image": {
            "path": image_path.name,
            "sha256": sha256(image_path),
            "expected_arch": "aarch64",
            "expected_entry": hex(image_base),
        },
        "handoff_descriptor": {
            "path": descriptor_path.name,
            "sha256": sha256(descriptor_path),
            "prefix_readable_proven": True,
            "copied_to_trusted_storage_proven": True,
        },
        "cpu_state": {
            "current_el": fact(1),
            "sp": fact(stack_top),
            "daif": {**fact(0xF), "normalized": True, "normalized_proven": True},
            "sctlr_el1": fact(1),
            "tcr_el1": fact(tcr),
            "ttbr0_el1": fact(ttbr0),
            "ttbr1_el1": fact(0x8000),
            "mair_el1": fact(0xFF),
            "vbar_el1": fact(0x100000800),
            "cpacr_el1": fact(0x300000),
            "translation_policy": {"normalized_proven": True},
            "cache_policy": {
                "icache": {"normalized_proven": True},
                "dcache": {"normalized_proven": True},
            },
        },
        "mmu_snapshot": {
            "path": snapshot_path.name,
            "sha256": sha256(snapshot_path),
        },
        "runtime_memory": {
            "dram_phys_base": fact("0x90000000"),
            "dram_size": fact("0x00200000"),
            "provenance": "RUNTIME_VERIFIED",
        },
        "ranges": ranges,
        "boot_args": {
            "path": boot_path.name,
            "sha256": sha256(boot_path),
            "length": "0x500",
            "complete": True,
        },
        "device_tree": {
            "path": dt_path.name,
            "sha256": sha256(dt_path),
            "length": hex(len(dt)),
            "complete": True,
        },
        "control_transfer": {
            "entry_pc": fact(image_base),
            "target": "DreyzeOS",
            "proven": True,
        },
        "persistence": {
            "persistent_write_required": bool_fact(False),
        },
    }
    bundle_path = root / "ready_bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle_path


def blocking_names(report: Dict[str, Any]) -> set[str]:
    return {
        item["requirement"]
        for item in report["readiness"]["blocking_requirements"]
    }


def mutate_bundle(bundle_path: Path, mutate: Callable[[Dict[str, Any], Path], None]) -> None:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    mutate(bundle, bundle_path.parent)
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")


class HandoffEvidenceVerifierTests(unittest.TestCase):
    def make_bundle(self, **options: Any) -> Tuple[Path, Path]:
        directory = Path(tempfile.mkdtemp(prefix="dreyzeos-handoff-"))
        return directory, build_ready_bundle(directory, **options)

    def verify_mutated(
        self,
        mutate: Callable[[Dict[str, Any], Path], None],
        **options: Any,
    ) -> Dict[str, Any]:
        directory, path = self.make_bundle(**options)
        try:
            mutate_bundle(path, mutate)
            return verify_bundle(path)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_complete_synthetic_model_is_offline_ready_only(self) -> None:
        directory, path = self.make_bundle()
        try:
            report = verify_bundle(path)
            self.assertEqual(
                report["readiness"]["offline_contract_result"], "READY",
                report["readiness"]["blocking_requirements"],
            )
            self.assertEqual(report["readiness"]["hardware_evidence_status"], "DESIGN")
            self.assertEqual(report["readiness"]["loader_contract"], "BLOCKED")
            self.assertEqual(
                report["readiness"]["first_hardware_execution"], "NOT_READY"
            )
            self.assertFalse(report["target"]["identity_proven"])
            human = human_report(report)
            self.assertIn("LOADER CONTRACT", human)
            self.assertIn("NOT_READY", human)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_synthetic_status_cannot_be_promoted_to_hardware_ready(self) -> None:
        directory, path = self.make_bundle()
        try:
            mutate_bundle(
                path,
                lambda bundle, _: (
                    bundle["source"].update(evidence_status="CONFIRMED"),
                    bundle["target"].update(identity_proven=True),
                ),
            )
            report = verify_bundle(path)
            self.assertEqual(report["readiness"]["loader_contract"], "BLOCKED")
            self.assertEqual(
                report["readiness"]["first_hardware_execution"], "NOT_READY"
            )
            self.assertIn("synthetic_evidence_guard", blocking_names(report))
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_proven_fact_requires_present_value(self) -> None:
        numeric = present_fact(
            {"value_present": False, "value_proven": True}, "test.numeric"
        )
        boolean = parse_bool_fact(
            {"value_present": False, "value_proven": True}, "test.boolean"
        )
        self.assertFalse(numeric["value_proven"])
        self.assertFalse(boolean["value_proven"])

    def test_non_synthetic_bundle_requires_target_provenance_coverage(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["source"].update({"kind": "capture", "evidence_status": "CONFIRMED"})
            bundle["target"]["identity_proven"] = True

        report = self.verify_mutated(mutate)
        self.assertIn("target_provenance", blocking_names(report))
        self.assertEqual(report["readiness"]["loader_contract"], "BLOCKED")

    def test_missing_expected_entry_blocks_image_shape(self) -> None:
        report = self.verify_mutated(
            lambda bundle, directory: bundle["image"].pop("expected_entry")
        )
        self.assertIn("image_shape", blocking_names(report))

    def test_required_object_must_be_complete(self) -> None:
        report = self.verify_mutated(
            lambda bundle, directory: bundle["boot_args"].update({"complete": False})
        )
        self.assertIn("boot_args_bounds", blocking_names(report))

    def test_duplicate_artifact_path_is_blocked(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["device_tree"]["path"] = bundle["image"]["path"]
            bundle["device_tree"]["sha256"] = bundle["image"]["sha256"]

        report = self.verify_mutated(mutate)
        self.assertIn("artifact_aliases", blocking_names(report))

    def test_missing_ttbr_proof(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["cpu_state"]["ttbr0_el1"]["value_proven"] = False
            snapshot = json.loads((directory / "mmu.json").read_text())
            snapshot["registers"]["ttbr0_el1"]["value_proven"] = False
            (directory / "mmu.json").write_text(json.dumps(snapshot, indent=2))
            bundle["mmu_snapshot"]["sha256"] = sha256(directory / "mmu.json")

        report = self.verify_mutated(mutate)
        self.assertIn("mmu_register_provenance", blocking_names(report))

    def test_tcr_conflict(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            current = bundle["cpu_state"]["tcr_el1"]["value"]
            current_value = int(current, 0) if isinstance(current, str) else int(current)
            bundle["cpu_state"]["tcr_el1"]["value"] = hex(current_value ^ (1 << 7))

        report = self.verify_mutated(mutate)
        self.assertTrue(report["evidence_graph"]["conflicts"])
        self.assertIn("cpu_consistency", blocking_names(report))

    def test_payload_translation_pa_mismatch(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            snapshot = json.loads((directory / "mmu.json").read_text())
            first = snapshot["physical_memory_regions"][0]["data_words"][3]
            first["value"] = hex(int(first["value"], 0) + 0x1000)
            (directory / "mmu.json").write_text(json.dumps(snapshot, indent=2))
            bundle["mmu_snapshot"]["sha256"] = sha256(directory / "mmu.json")

        report = self.verify_mutated(mutate)
        self.assertIn("payload_translation_consistency", blocking_names(report))

    def test_duplicate_protected_range_definition(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["ranges"]["protected_ranges"] = [
                range_fact("duplicate", 0x90108000, 0x1000, "physical"),
                range_fact("duplicate", 0x90108000, 0x1000, "physical"),
            ]

        report = self.verify_mutated(mutate)
        self.assertIn("range_definition_integrity", blocking_names(report))

    def test_entry_unmapped(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["control_transfer"]["entry_pc"] = fact(0x200000000)

        report = self.verify_mutated(mutate)
        self.assertIn("entry_executable_mapping", blocking_names(report))

    def test_entry_pxn(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            snapshot = json.loads((directory / "mmu.json").read_text())
            first = snapshot["physical_memory_regions"][0]["data_words"][3]
            first["value"] = hex(int(first["value"], 0) | (1 << 53))
            (directory / "mmu.json").write_text(json.dumps(snapshot, indent=2))
            bundle["mmu_snapshot"]["sha256"] = sha256(directory / "mmu.json")

        report = self.verify_mutated(mutate, entry_pxn=True)
        self.assertIn("entry_executable_mapping", blocking_names(report))

    def test_stack_read_only(self) -> None:
        report = self.verify_mutated(lambda b, d: None, stack_read_only=True)
        self.assertIn("stack_mapping", blocking_names(report))

    def test_unaligned_sp(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            raw_value = bundle["cpu_state"]["sp"]["value"]
            value = (int(raw_value, 0) if isinstance(raw_value, str) else int(raw_value)) + 1
            bundle["cpu_state"]["sp"]["value"] = hex(value)
            bundle["control_transfer"]["entry_pc"] = bundle["control_transfer"]["entry_pc"]

        report = self.verify_mutated(mutate)
        self.assertIn("initial_sp", blocking_names(report))

    def test_payload_outside_runtime_ram(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["runtime_memory"]["dram_phys_base"]["value"] = "0xA0000000"

        report = self.verify_mutated(mutate)
        self.assertIn("payload_in_runtime_dram", blocking_names(report))

    def test_payload_overlaps_loader(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["ranges"]["loader_code"]["base"] = "0x90000010"

        report = self.verify_mutated(mutate)
        self.assertIn("collision_audit", blocking_names(report))

    def test_payload_overlaps_device_tree(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["ranges"]["protected_ranges"] = [
                range_fact("DeviceTree", 0x90000010, 0x1000, "physical")
            ]

        report = self.verify_mutated(mutate)
        self.assertIn("collision_audit", blocking_names(report))

    def test_incomplete_reserved_list(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["ranges"]["protected_ranges_complete"] = False

        report = self.verify_mutated(mutate)
        self.assertIn(
            "reserved_memory_completeness",
            blocking_names(report),
        )

    def test_malformed_descriptor(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            descriptor = bytearray((directory / "descriptor.bin").read_bytes())
            descriptor[0] ^= 0x01
            (directory / "descriptor.bin").write_bytes(descriptor)
            bundle["handoff_descriptor"]["sha256"] = sha256(directory / "descriptor.bin")

        report = self.verify_mutated(mutate)
        self.assertIn("descriptor_structure", blocking_names(report))

    def test_verified_bit_does_not_prove_pointer_trust(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["handoff_descriptor"]["prefix_readable_proven"] = False

        report = self.verify_mutated(mutate)
        self.assertIn(
            "descriptor_root_of_trust",
            blocking_names(report),
        )

    def test_inline_descriptor_bytes_do_not_bypass_artifact_integrity(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            descriptor_path = directory / bundle["handoff_descriptor"]["path"]
            descriptor = descriptor_path.read_bytes()
            bundle["handoff_descriptor"] = {
                "bytes_hex": descriptor.hex(),
                "sha256": sha256(descriptor_path),
                "prefix_readable_proven": True,
                "copied_to_trusted_storage_proven": True,
            }

        report = self.verify_mutated(mutate)
        self.assertIn("bundle_integrity", blocking_names(report))
        self.assertIn("descriptor_structure", blocking_names(report))

    def test_boot_args_nested_device_tree_bounds(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            boot = bytearray((directory / "boot_args.bin").read_bytes())
            struct.pack_into("<Q", boot, 0x60, 0xDEADBEEF)
            (directory / "boot_args.bin").write_bytes(boot)
            bundle["boot_args"]["sha256"] = sha256(directory / "boot_args.bin")

        report = self.verify_mutated(mutate)
        self.assertIn("boot_args_bounds", blocking_names(report))

    def test_incomplete_snapshot(self) -> None:
        report = self.verify_mutated(lambda b, d: None, incomplete=True)
        self.assertIn(
            "entry_executable_mapping",
            blocking_names(report),
        )

    def test_image_hash_mismatch(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            path = directory / "DreyzeOS.elf"
            data = bytearray(path.read_bytes())
            data[-1] ^= 0x01
            path.write_bytes(data)

        report = self.verify_mutated(mutate)
        self.assertIn("bundle_integrity", blocking_names(report))

    def test_target_metadata_mismatch(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["target"]["model"] = "Watch4,1"

        report = self.verify_mutated(mutate)
        self.assertIn(
            "target_metadata_match",
            blocking_names(report),
        )

    def test_mmu_snapshot_target_mismatch_is_blocked(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            snapshot_path = directory / bundle["mmu_snapshot"]["path"]
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot["target"]["model"] = "Watch4,1"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            bundle["mmu_snapshot"]["sha256"] = sha256(snapshot_path)

        report = self.verify_mutated(mutate)
        self.assertIn("mmu_snapshot_target_match", blocking_names(report))

    def test_string_identity_boolean_cannot_prove_target(self) -> None:
        report = self.verify_mutated(
            lambda bundle, directory: bundle["target"].update({"identity_proven": "false"})
        )
        self.assertFalse(report["target"]["identity_proven"])
        self.assertEqual(report["target"]["identity_node"]["proof_state"], "NOT_PROVEN")

    def test_mmu_disabled_contradiction(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["cpu_state"]["sctlr_el1"]["value"] = "0"

        report = self.verify_mutated(mutate)
        self.assertTrue(any(
            item["name"] == "MMU_ENABLED_CONFLICT"
            for item in report["evidence_graph"]["conflicts"]
        ))

    def test_control_transfer_missing(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["control_transfer"]["proven"] = False

        report = self.verify_mutated(mutate)
        self.assertIn("control_transfer", blocking_names(report))

    def test_persistent_write_required(self) -> None:
        def mutate(bundle: Dict[str, Any], directory: Path) -> None:
            bundle["persistence"]["persistent_write_required"]["value"] = True

        report = self.verify_mutated(mutate)
        self.assertIn("no_persistent_write", blocking_names(report))

    def test_cli_help_and_exit_semantics(self) -> None:
        tool = ROOT / "tools" / "handoff_evidence_verifier.py"
        help_result = subprocess.run(
            [sys.executable, str(tool), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0)
        directory, path = self.make_bundle()
        try:
            blocked = subprocess.run(
                [sys.executable, str(tool), "--bundle", str(path), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(blocked.returncode, 0)
            decoded = json.loads(blocked.stdout)
            self.assertEqual(decoded["readiness"]["offline_contract_result"], "READY")
            strict = subprocess.run(
                [sys.executable, str(tool), "--bundle", str(path), "--human", "--strict"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(strict.returncode, 0)
            self.assertIn("LOADER CONTRACT", strict.stdout)
            mutate_bundle(
                path,
                lambda bundle, _: bundle["control_transfer"].update(proven=False),
            )
            blocked_json = subprocess.run(
                [sys.executable, str(tool), "--bundle", str(path), "--json"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(blocked_json.returncode, 0)
            blocked_report = json.loads(blocked_json.stdout)
            self.assertEqual(blocked_report["readiness"]["offline_contract_result"], "BLOCKED")
            strict_blocked = subprocess.run(
                [sys.executable, str(tool), "--bundle", str(path), "--json", "--strict"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(strict_blocked.returncode, 1)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_cli_malformed_input_is_tool_error(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="dreyzeos-cli-bad-"))
        try:
            path = directory / "bad.json"
            path.write_text("{", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "handoff_evidence_verifier.py"),
                 "--bundle", str(path), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertEqual(report["tool_error"], "BUNDLE_INVALID")
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_path_traversal_is_tool_error(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="dreyzeos-bad-bundle-"))
        try:
            bundle = {
                "schema": "dreyzeos.handoff_evidence.v1",
                "architecture": "aarch64",
                "target": {
                    "model": "Watch4,2",
                    "board": "N131bAP",
                    "soc": "T8006",
                    "firmware": "watchOS 10.6.1",
                    "build": "21U580",
                    "architecture": "aarch64",
                },
                "source": {"kind": "synthetic", "evidence_status": "DESIGN"},
                "image": {"path": "../outside", "sha256": "0" * 64},
            }
            path = directory / "bad.json"
            path.write_text(json.dumps(bundle), encoding="utf-8")
            report = verify_bundle(path)
            self.assertIn("bundle_integrity", blocking_names(report))
        finally:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

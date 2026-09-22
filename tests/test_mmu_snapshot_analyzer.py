#!/usr/bin/env python3
"""Host-only unit tests for the offline MMU snapshot analyzer."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.mmu_snapshot_analyzer import (  # noqa: E402
    Snapshot,
    SnapshotError,
    analyze_elf,
    analyze_framebuffer,
    analyze_mmio_query,
    analyze_range,
    decode_mair,
    decode_tcr,
    find_pa_mappings,
    interval_overlap,
    loader_contract_bridge,
    walk_va,
)


def reg(value: int, proven: bool = False) -> Dict[str, Any]:
    return {
        "value": value,
        "value_present": True,
        "value_proven": proven,
    }


def make_tcr(granule: int, va_bits: int = 48) -> int:
    tg0 = {4096: 0b00, 16384: 0b10, 65536: 0b01}[granule]
    tg1 = {4096: 0b10, 16384: 0b01, 65536: 0b11}[granule]
    tnsz = 64 - va_bits
    return (
        tnsz
        | (0b01 << 8)
        | (0b01 << 10)
        | (0b11 << 12)
        | (tg0 << 14)
        | (tnsz << 16)
        | (0b01 << 24)
        | (0b01 << 26)
        | (0b11 << 28)
        | (tg1 << 30)
        | (0b101 << 32)
    )


def make_page_raw(
    physical_base: int,
    ap: int = 0,
    attr_index: int = 0,
    af: bool = True,
    pxn: bool = False,
    uxn: bool = False,
) -> int:
    raw = physical_base | 0x3 | (ap << 6) | (0b11 << 8) | (attr_index << 2)
    if af:
        raw |= 1 << 10
    if pxn:
        raw |= 1 << 53
    if uxn:
        raw |= 1 << 54
    return raw


def make_pages_snapshot(
    pages: Sequence[Tuple[int, int, Dict[str, Any]]],
    *,
    granule: int = 4096,
    role: str = "ttbr0",
    va_bits: int = 48,
    mair: int = 0xFF,
    complete: bool = True,
    source_kind: str = "synthetic",
) -> Snapshot:
    tcr = make_tcr(granule, va_bits)
    decoded = decode_tcr(tcr)
    regime = decoded["regimes"][role]
    levels = regime["levels"]
    index_bits = regime["index_bits"]
    page_shift = regime["page_shift"]
    table_base = 0x100000
    allocated_pages = 1
    table_for_prefix: Dict[Tuple[int, ...], int] = {(): table_base}
    words: Dict[int, int] = {}

    for virtual_address, physical_address, attrs in pages:
        current_table = table_base
        indices = [
            (virtual_address >> (page_shift + index_bits * (levels - 1 - level)))
            & ((1 << bits) - 1)
            for level, bits in enumerate(regime["level_index_bits"])
        ]
        for level in range(levels - 1):
            prefix = tuple(indices[: level + 1])
            child = table_for_prefix.get(prefix)
            if child is None:
                child = table_base + allocated_pages * granule
                allocated_pages += 1
                table_for_prefix[prefix] = child
            descriptor_address = current_table + indices[level] * 8
            words[descriptor_address - table_base] = child | 0x3
            current_table = child
        leaf_address = current_table + indices[-1] * 8
        words[leaf_address - table_base] = make_page_raw(
            physical_address,
            ap=int(attrs.get("ap", 0)),
            attr_index=int(attrs.get("attr_index", 0)),
            af=bool(attrs.get("af", True)),
            pxn=bool(attrs.get("pxn", False)),
            uxn=bool(attrs.get("uxn", False)),
        )

    registers = {
        "tcr_el1": reg(tcr),
        "ttbr0_el1": reg(table_base if role == "ttbr0" else 0x400000),
        "ttbr1_el1": reg(table_base if role == "ttbr1" else 0x400000),
        "mair_el1": reg(mair),
    }
    manifest = {
        "schema": "dreyzeos.mmu_snapshot.v1",
        "architecture": "aarch64",
        "target": {"name": "unit-test-fixture"},
        "source": {"kind": source_kind, "status": "DESIGN"},
        "evidence_status": "DESIGN",
        "registers": registers,
        "physical_memory_regions": [
            {
                "physical_base": table_base,
                "length": allocated_pages * granule,
                "memory_bytes_present": True,
                "memory_range_complete": complete,
                "data_words": [
                    {"offset": offset, "value": value}
                    for offset, value in sorted(words.items())
                ],
            }
        ],
    }
    return Snapshot.from_manifest(manifest, ROOT)


class OfflineMmuAnalyzerTests(unittest.TestCase):
    def load_fixture(self, name: str) -> Snapshot:
        return Snapshot.load(ROOT / "tests" / "fixtures" / "mmu" / name)

    def test_valid_4k_ttbr0_page_translation(self) -> None:
        snapshot = self.load_fixture("valid_4k_ttbr0.json")
        result = walk_va(snapshot, 0x40123456)
        self.assertEqual(result["status"], "MAPPED")
        self.assertEqual(result["selected_ttbr"], "ttbr0")
        self.assertEqual(result["descriptor_type"], "page")
        self.assertEqual(result["page_or_block_size"], 0x1000)
        self.assertEqual(result["output_pa"], 0x80000456)
        self.assertTrue(result["attributes"]["readable"])
        self.assertTrue(result["attributes"]["writable"])
        self.assertTrue(result["attributes"]["executable"])
        self.assertEqual(result["attributes"]["mair"]["category"], "Normal")

    def test_valid_16k_ttbr1_page_translation(self) -> None:
        snapshot = self.load_fixture("valid_16k_ttbr1.json")
        result = walk_va(snapshot, 0xFFFF800000001234)
        self.assertEqual(result["status"], "MAPPED")
        self.assertEqual(result["selected_ttbr"], "ttbr1")
        self.assertEqual(result["page_or_block_size"], 0x4000)
        self.assertEqual(result["output_pa"], 0x90001234)
        self.assertFalse(result["attributes"]["writable"])
        self.assertTrue(result["attributes"]["executable_el1"])
        self.assertTrue(result["attributes"]["uxn"])

    def test_valid_64k_page_translation(self) -> None:
        va = 0x12345678
        snapshot = make_pages_snapshot(
            [(va, 0xA0000000, {"ap": 0})],
            granule=65536,
            va_bits=48,
        )
        result = walk_va(snapshot, va)
        self.assertEqual(result["status"], "MAPPED")
        self.assertEqual(result["page_or_block_size"], 0x10000)
        self.assertEqual(result["output_pa"], 0xA0005678)

    def test_tcr_decodes_all_required_geometry_fields(self) -> None:
        tcr = make_tcr(16384, 47)
        decoded = decode_tcr(tcr)
        self.assertEqual(decoded["status"], "SUPPORTED")
        self.assertEqual(decoded["physical_address_bits"], 48)
        regime = decoded["regimes"]["ttbr0"]
        self.assertEqual(regime["tnsz"], 17)
        self.assertEqual(regime["va_bits"], 47)
        self.assertEqual(regime["granule_name"], "16K")
        self.assertEqual(regime["page_shift"], 14)
        self.assertEqual(regime["shareability"], "inner-shareable")
        self.assertEqual(regime["cacheability"], "write-back-write-allocate")
        self.assertEqual(regime["levels"], 3)
        self.assertEqual(regime["level_sizes"][-1], 0x4000)

    def test_tcr_reserved_granule_fails_closed(self) -> None:
        decoded = decode_tcr(0x3 << 14)
        self.assertEqual(decoded["regimes"]["ttbr0"]["status"], "UNSUPPORTED_GRANULE")
        self.assertEqual(decoded["status"], "UNSUPPORTED")

    def test_mair_device_normal_and_unknown_categories(self) -> None:
        self.assertEqual(decode_mair(0xFF, 0)["category"], "Normal")
        self.assertEqual(decode_mair(0x00, 0)["category"], "Device")
        self.assertEqual(decode_mair(0x12, 0)["category"], "Unknown/implementation-specific")
        self.assertEqual(decode_mair(0x0000, 1)["raw"], 0)

    def test_block_descriptor_is_supported(self) -> None:
        tcr = make_tcr(4096, 48)
        table = 0x2000
        next_table = 0x3000
        block_raw = (0x40000000 | 0x1 | (0b11 << 8) | (1 << 10))
        manifest = {
            "schema": "dreyzeos.mmu_snapshot.v1",
            "architecture": "aarch64",
            "target": {},
            "source": {"kind": "synthetic", "status": "DESIGN"},
            "evidence_status": "DESIGN",
            "registers": {
                "tcr_el1": reg(tcr),
                "ttbr0_el1": reg(table),
                "ttbr1_el1": reg(0x8000),
                "mair_el1": reg(0xFF),
            },
            "physical_memory_regions": [
                {
                    "physical_base": table,
                    "length": 0x2000,
                    "memory_bytes_present": True,
                    "memory_range_complete": True,
                    "data_words": [
                        {"offset": 0, "value": next_table | 0x3},
                        {"offset": 0x1000, "value": block_raw},
                    ],
                }
            ],
        }
        result = walk_va(Snapshot.from_manifest(manifest), 0x123456)
        self.assertEqual(result["status"], "MAPPED")
        self.assertEqual(result["descriptor_type"], "block")
        self.assertEqual(result["page_or_block_size"], 1 << 30)
        self.assertEqual(result["output_pa"], 0x40123456)

    def test_ttbr1_is_selected_only_for_canonical_upper_va(self) -> None:
        va = 0xFFFF800000002000
        result = walk_va(
            make_pages_snapshot([(va, 0xB0000000, {})], role="ttbr1", va_bits=47),
            va,
        )
        self.assertEqual(result["selected_ttbr"], "ttbr1")
        self.assertEqual(result["status"], "MAPPED")

    def test_noncanonical_va_is_rejected(self) -> None:
        result = walk_va(self.load_fixture("valid_4k_ttbr0.json"), 1 << 48)
        self.assertEqual(result["status"], "NON_CANONICAL_VA")

    def test_ttbr_selection_mismatch_is_rejected(self) -> None:
        snapshot = self.load_fixture("valid_4k_ttbr0.json")
        result = walk_va(snapshot, 0x40123456, "ttbr1")
        self.assertEqual(result["status"], "TTBR_SELECTION_MISMATCH")

    def test_translation_disable_is_reported(self) -> None:
        manifest = json.loads(
            (ROOT / "tests/fixtures/mmu/valid_4k_ttbr0.json").read_text()
        )
        manifest["registers"]["tcr_el1"]["value"] = int(manifest["registers"]["tcr_el1"]["value"], 0) | (1 << 7)
        result = walk_va(Snapshot.from_manifest(manifest), 0x40123456)
        self.assertEqual(result["status"], "TRANSLATION_DISABLED")

    def test_unmapped_descriptor_is_not_a_mapping(self) -> None:
        manifest = json.loads(
            (ROOT / "tests/fixtures/mmu/valid_4k_ttbr0.json").read_text()
        )
        manifest["physical_memory_regions"][0]["data_words"][0]["value"] = 0
        result = walk_va(Snapshot.from_manifest(manifest), 0x40123456)
        self.assertEqual(result["status"], "UNMAPPED")
        self.assertFalse(result["mapped"])

    def test_missing_table_page_is_explicit(self) -> None:
        manifest = json.loads(
            (ROOT / "tests/fixtures/mmu/valid_4k_ttbr0.json").read_text()
        )
        manifest["physical_memory_regions"][0]["length"] = 8
        manifest["physical_memory_regions"][0]["data_words"] = [
            {"offset": 0, "value": 0x2003}
        ]
        snapshot = Snapshot.from_manifest(manifest)
        result = walk_va(snapshot, 0x40123456)
        self.assertIn(result["status"], {"TABLE_BYTES_MISSING", "PHYSICAL_DUMP_INCOMPLETE"})

    def test_cyclic_table_path_is_rejected(self) -> None:
        tcr = make_tcr(4096, 48)
        manifest = {
            "schema": "dreyzeos.mmu_snapshot.v1",
            "architecture": "aarch64",
            "target": {},
            "source": {"kind": "synthetic", "status": "DESIGN"},
            "evidence_status": "DESIGN",
            "registers": {
                "tcr_el1": reg(tcr),
                "ttbr0_el1": reg(0x1000),
                "ttbr1_el1": reg(0x8000),
                "mair_el1": reg(0xFF),
            },
            "physical_memory_regions": [
                {
                    "physical_base": 0x1000,
                    "length": 0x4000,
                    "memory_bytes_present": True,
                    "memory_range_complete": True,
                    "data_words": [{"offset": 0, "value": 0x1003}],
                }
            ],
        }
        result = walk_va(Snapshot.from_manifest(manifest), 0x4000)
        self.assertEqual(result["status"], "CYCLIC_TABLE")
    def test_invalid_final_descriptor_is_rejected(self) -> None:
        manifest = json.loads(
            (ROOT / "tests/fixtures/mmu/valid_4k_ttbr0.json").read_text()
        )
        manifest["physical_memory_regions"][0]["data_words"][-1]["value"] = 0x1
        result = walk_va(Snapshot.from_manifest(manifest), 0x40123456)
        self.assertEqual(result["status"], "INVALID_DESCRIPTOR")

    def test_pa_width_violation_is_rejected(self) -> None:
        snapshot = make_pages_snapshot([(0x4000, 1 << 48, {})])
        result = walk_va(snapshot, 0x4000)
        self.assertEqual(result["status"], "PHYSICAL_ADDRESS_WIDTH")

    def test_access_flag_unset_does_not_grant_permissions(self) -> None:
        snapshot = make_pages_snapshot([(0x4000, 0x90000000, {"af": False})])
        result = walk_va(snapshot, 0x4000)
        self.assertEqual(result["status"], "MAPPED")
        self.assertIsNone(result["attributes"]["readable"])
        self.assertTrue(result["attributes"]["access_fault_possible"])

    def test_device_attribute_is_reported_from_mair(self) -> None:
        snapshot = make_pages_snapshot(
            [(0x4000, 0x90000000, {"attr_index": 1})],
            mair=0x0000000000000000,
        )
        result = walk_va(snapshot, 0x4000)
        self.assertEqual(result["attributes"]["mair"]["category"], "Device")

    def test_pxn_and_uxn_are_reported_separately(self) -> None:
        snapshot = make_pages_snapshot(
            [(0x4000, 0x90000000, {"pxn": True, "uxn": True})]
        )
        attrs = walk_va(snapshot, 0x4000)["attributes"]
        self.assertFalse(attrs["executable_el1"])
        self.assertFalse(attrs["executable_el0"])
        self.assertTrue(attrs["pxn"])
        self.assertTrue(attrs["uxn"])

    def test_range_crosses_permission_boundary(self) -> None:
        snapshot = make_pages_snapshot(
            [
                (0x400000, 0x80000000, {"ap": 0}),
                (0x401000, 0x80001000, {"ap": 2}),
            ]
        )
        result = analyze_range(snapshot, 0x400000, 0x2000)
        self.assertEqual(result["status"], "fully_mapped")
        self.assertFalse(result["writable"])
        self.assertTrue(result["readable"])
        self.assertTrue(result["permission_changes"])
        self.assertTrue(result["physical_contiguous"])

    def test_range_partially_unmapped_reports_first_failure(self) -> None:
        snapshot = make_pages_snapshot([(0x400000, 0x80000000, {})])
        result = analyze_range(snapshot, 0x400000, 0x2000)
        self.assertEqual(result["status"], "partially_mapped")
        self.assertEqual(result["first_failure"]["status"], "UNMAPPED")

    def test_range_detects_noncontiguous_physical_pages(self) -> None:
        snapshot = make_pages_snapshot(
            [
                (0x400000, 0x80000000, {}),
                (0x401000, 0x90000000, {}),
            ]
        )
        result = analyze_range(snapshot, 0x400000, 0x2000)
        self.assertFalse(result["physical_contiguous"])

    def test_range_overflow_is_rejected(self) -> None:
        result = analyze_range(
            self.load_fixture("valid_4k_ttbr0.json"), (1 << 64) - 1, 2
        )
        self.assertEqual(result["status"], "UINT64_OVERFLOW")

    def test_adjacent_ranges_do_not_overlap(self) -> None:
        self.assertFalse(interval_overlap(0x1000, 0x1000, 0x2000, 0x1000))
        self.assertTrue(interval_overlap(0x1000, 0x1000, 0x1FFF, 1))

    def test_partial_dump_is_not_complete(self) -> None:
        snapshot = make_pages_snapshot(
            [(0x4000, 0x90000000, {})], complete=False
        )
        result = walk_va(snapshot, 0x4000)
        self.assertEqual(result["status"], "MAPPED")
        self.assertFalse(result["physical_dump_complete"])

    def test_manifest_rejects_zero_length_region(self) -> None:
        manifest = {
            "schema": "dreyzeos.mmu_snapshot.v1",
            "architecture": "aarch64",
            "target": {},
            "source": {"kind": "synthetic", "status": "DESIGN"},
            "physical_memory_regions": [
                {
                    "physical_base": 0,
                    "length": 0,
                    "memory_bytes_present": False,
                    "memory_range_complete": False,
                }
            ],
        }
        with self.assertRaises(SnapshotError) as context:
            Snapshot.from_manifest(manifest)
        self.assertEqual(context.exception.code, "MANIFEST_INVALID")

    def test_elf_audit_without_snapshot_is_blocked(self) -> None:
        report = analyze_elf(ROOT / "build" / "DreyzeOS.elf")
        self.assertEqual(report["status"], "DESIGN")
        self.assertEqual(report["evidence_status"], "UNKNOWN")
        self.assertFalse(report["loader_contract_bridge"]["loader_authority"]["ownership_proven"])

    def test_partial_binary_blob_is_accepted_and_reported_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            blob_path = Path(temporary) / "partial.bin"
            blob_path.write_bytes((0x2003).to_bytes(8, "little"))
            manifest = {
                "schema": "dreyzeos.mmu_snapshot.v1",
                "architecture": "aarch64",
                "target": {},
                "source": {"kind": "captured", "status": "UNKNOWN"},
                "evidence_status": "UNKNOWN",
                "registers": {
                    "tcr_el1": reg(make_tcr(4096, 48)),
                    "ttbr0_el1": reg(0x1000),
                    "ttbr1_el1": reg(0x8000),
                    "mair_el1": reg(0xFF),
                },
                "physical_memory_regions": [
                    {
                        "physical_base": 0x1000,
                        "length": 0x4000,
                        "file": "partial.bin",
                        "memory_bytes_present": True,
                        "memory_range_complete": False,
                    }
                ],
            }
            snapshot = Snapshot.from_manifest(manifest, temporary)
            result = walk_va(snapshot, 0x40123456)
            self.assertEqual(result["status"], "PHYSICAL_DUMP_INCOMPLETE")
    def test_elf_audit_reports_required_symbols(self) -> None:

        report = analyze_elf(ROOT / "build" / "DreyzeOS.elf")
        symbols = report["required_symbols"]
        for name in (
            "_start",
            "__kernel_start",
            "__kernel_end",
            "__bss_start",
            "__bss_end",
            "__stack_bottom",
            "__stack_top",
            "_exception_vectors_base",
        ):
            self.assertIsNotNone(symbols[name], name)

    def test_loader_bridge_never_promotes_mapping_to_authority(self) -> None:
        bridge = loader_contract_bridge(
            [{"name": "kernel.text", "mapping_fact": {"status": "fully_mapped"}}]
        )
        self.assertFalse(bridge["loader_authority"]["ownership_proven"])
        self.assertFalse(bridge["loader_authority"]["descriptor_trusted"])
        self.assertFalse(bridge["loader_entry_contract_fields"]["entry_pc_proven"])

    def test_mmio_without_va_search_is_unknown(self) -> None:
        report = analyze_mmio_query(None, "uart0")
        self.assertEqual(report["physical_device_address"]["status"], "CONFIRMED")
        self.assertEqual(report["translation"]["status"], "UNKNOWN")
        self.assertEqual(report["access_authority"]["value"], "NOT_PROVEN")

    def test_mmio_query_can_find_synthetic_va_mapping(self) -> None:
        snapshot = make_pages_snapshot(
            [(0x500000, 0x2E500000, {"attr_index": 1})]
        )
        report = analyze_mmio_query(
            snapshot,
            "uart0",
            {
                "base": 0x500000,
                "length": 0x1000,
                "address_space": "virtual",
                "ttbr": "ttbr0",
            },
        )
        self.assertEqual(report["physical_device_address"]["status"], "CONFIRMED")
        self.assertEqual(report["translation"]["status"], "DESIGN")
        self.assertTrue(report["translation"]["matches"])
        self.assertEqual(report["access_authority"]["value"], "NOT_PROVEN")

    def test_framebuffer_without_runtime_range_is_blocked(self) -> None:
        report = analyze_framebuffer(None)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["mapping"], "UNKNOWN")

    def test_framebuffer_mapping_keeps_authority_separate(self) -> None:
        snapshot = make_pages_snapshot([(0x600000, 0x70000000, {})])
        manifest = copy.deepcopy(snapshot.manifest)
        manifest["framebuffer"] = {
            "physical_base": "0x70000000",
            "size": "0x1000",
            "provenance": "DESIGN",
        }
        snapshot = Snapshot.from_manifest(manifest)
        snapshot.virtual_search_ranges.append(
            {
                "base": 0x600000,
                "length": 0x1000,
                "address_space": "virtual",
                "ttbr": "ttbr0",
                "name": "synthetic",
            }
        )
        report = analyze_framebuffer(snapshot)
        self.assertEqual(report["mapping"]["status"], "DESIGN")
        self.assertEqual(report["access_authority"], "NOT_PROVEN")

    def test_descriptor_outside_supplied_blob_is_explicit(self) -> None:
        snapshot = make_pages_snapshot([(0x4000, 0x90000000, {})])
        manifest = copy.deepcopy(snapshot.manifest)
        manifest["registers"]["ttbr0_el1"]["value"] = 0xDE000000
        result = walk_va(Snapshot.from_manifest(manifest), 0x4000)
        self.assertIn(result["status"], {"TABLE_BYTES_MISSING", "PHYSICAL_DUMP_INCOMPLETE"})

    def test_unsupported_tcr_is_reported_by_walk(self) -> None:
        manifest = json.loads(
            (ROOT / "tests/fixtures/mmu/valid_4k_ttbr0.json").read_text()
        )
        manifest["registers"]["tcr_el1"]["value"] = 0x3 << 14
        result = walk_va(Snapshot.from_manifest(manifest), 0x40123456)
        self.assertIn(result["status"], {"UNSUPPORTED", "UNSUPPORTED_GRANULE"})

    def test_snapshot_summary_exposes_completeness_flags(self) -> None:
        snapshot = self.load_fixture("valid_4k_ttbr0.json")
        self.assertTrue(snapshot.regions[0].memory_bytes_present)
        self.assertTrue(snapshot.regions[0].memory_range_complete)
        self.assertEqual(snapshot.evidence_status, "DESIGN")

    def test_find_pa_mappings_is_not_exhaustive_without_search_ranges(self) -> None:
        snapshot = self.load_fixture("valid_4k_ttbr0.json")
        self.assertEqual(find_pa_mappings(snapshot, 0x80000000, 0x1000, []), [])

    def test_cli_help_is_available(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "mmu_snapshot_analyzer.py"), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Offline AArch64", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)

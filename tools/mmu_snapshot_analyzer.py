#!/usr/bin/env python3
"""
DreyzeOS offline AArch64 MMU evidence analyzer.

This module is deliberately host-only. It reads a JSON snapshot manifest and
local physical-memory blobs, decodes architectural translation metadata, and
returns evidence reports. It never opens device memory, writes memory, probes
pointers, executes payloads, or treats a mapping as loader authority.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


U64_LIMIT = 1 << 64
U64_MAX = U64_LIMIT - 1
STATUS_VALUES = {"CONFIRMED", "LIKELY", "DESIGN", "UNKNOWN", "BLOCKED"}

TCR_TG0 = {0b00: (4096, "4K"), 0b10: (16384, "16K"), 0b01: (65536, "64K")}
TCR_TG1 = {0b10: (4096, "4K"), 0b01: (16384, "16K"), 0b11: (65536, "64K")}
IPS_BITS = {
    0b000: 32,
    0b001: 36,
    0b010: 40,
    0b011: 42,
    0b100: 44,
    0b101: 48,
    0b110: 52,
}
MAIR_DEVICE_VALUES = {
    0x00: "Device-nGnRnE",
    0x04: "Device-nGnRE",
    0x08: "Device-nGRE",
    0x0C: "Device-GRE",
}
MAIR_NORMAL_NIBBLES = {0x0, 0x4, 0x8, 0xB, 0xC, 0xF}

MMIO_TARGETS: Dict[str, Dict[str, Any]] = {
    "uart0": {
        "physical_base": 0x2E500000,
        "size": 0x4000,
        "source": "Watch4,2 static DeviceTree /arm-io/uart0",
    },
    "aic": {
        "physical_base": 0x2D180000,
        "size": 0x8000,
        "source": "Watch4,2 static DeviceTree /arm-io/aic",
    },
    "aic-timebase": {
        "physical_base": 0x2D188000,
        "size": 0x1000,
        "source": "Watch4,2 static DeviceTree /arm-io/aic-timebase",
    },
    "display": {
        "physical_base": 0x18000000,
        "size": 0x2F0000,
        "source": "Watch4,2 static DeviceTree /arm-io/disp0",
    },
    "mipi": {
        "physical_base": 0x18400000,
        "size": 0x90000,
        "source": "Watch4,2 static DeviceTree /arm-io/mipi-dsim",
    },
    "mipi-sec": {
        "physical_base": 0x18490000,
        "size": 0x10000,
        "source": "Watch4,2 static DeviceTree /arm-io/mipi-dsim-sec",
    },
}


class SnapshotError(Exception):
    """Structured, non-crashing error for malformed or incomplete evidence."""

    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "ok": False,
            "status": self.code,
            "error": self.message,
        }
        result.update(self.details)
        return result


def parse_uint(value: Any, name: str, maximum: int = U64_MAX) -> int:
    if isinstance(value, bool):
        raise SnapshotError("INVALID_VALUE", f"{name} must be an integer")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str):
        try:
            result = int(value.strip(), 0)
        except ValueError as exc:
            raise SnapshotError("INVALID_VALUE", f"{name} is not an integer") from exc
    else:
        raise SnapshotError("INVALID_VALUE", f"{name} is not an integer")
    if result < 0 or result > maximum:
        raise SnapshotError(
            "ADDRESS_OUT_OF_RANGE",
            f"{name} is outside the supported unsigned range",
            value=result,
        )
    return result


def checked_add(base: int, length: int, name: str = "interval") -> int:
    if base < 0 or length < 0 or base > U64_MAX or length > U64_MAX:
        raise SnapshotError("ADDRESS_OUT_OF_RANGE", f"{name} has an invalid operand")
    end = base + length
    if end > U64_LIMIT:
        raise SnapshotError("UINT64_OVERFLOW", f"{name} wraps UINT64")
    return end


def checked_mul(left: int, right: int, name: str = "multiplication") -> int:
    if left < 0 or right < 0 or left > U64_MAX or right > U64_MAX:
        raise SnapshotError("ADDRESS_OUT_OF_RANGE", f"{name} has an invalid operand")
    value = left * right
    if value > U64_MAX:
        raise SnapshotError("UINT64_OVERFLOW", f"{name} overflows UINT64")
    return value


def interval_overlap(
    left_base: int, left_length: int, right_base: int, right_length: int
) -> bool:
    left_end = checked_add(left_base, left_length)
    right_end = checked_add(right_base, right_length)
    return left_base < right_end and right_base < left_end


def _status_or_unknown(value: Any) -> str:
    if isinstance(value, str) and value in STATUS_VALUES:
        return value
    return "UNKNOWN"


@dataclass
class MemoryRegion:
    physical_base: int
    declared_length: int
    data: bytes
    memory_bytes_present: bool
    memory_range_complete: bool
    label: str = ""

    @property
    def declared_end(self) -> int:
        return self.physical_base + self.declared_length

    @property
    def data_end(self) -> int:
        return self.physical_base + len(self.data)

    def declared_contains(self, address: int) -> bool:
        return self.physical_base <= address < self.declared_end

    def data_contains(self, address: int) -> bool:
        return self.physical_base <= address < self.data_end


class Snapshot:
    """Validated snapshot manifest plus local physical bytes."""

    def __init__(
        self,
        manifest: Dict[str, Any],
        manifest_path: Optional[Path] = None,
        base_dir: Optional[Path] = None,
    ):
        self.manifest = manifest
        self.manifest_path = manifest_path
        self.base_dir = (base_dir or Path.cwd()).resolve()
        self.evidence_status = _status_or_unknown(
            manifest.get("evidence_status", "UNKNOWN")
        )
        self.source = manifest.get("source", {})
        if not isinstance(self.source, dict):
            raise SnapshotError("MANIFEST_INVALID", "source must be an object")
        self.registers: Dict[str, Dict[str, Any]] = {}
        self.regions: List[MemoryRegion] = []
        self.protected_regions: List[Dict[str, Any]] = []
        self.virtual_search_ranges: List[Dict[str, Any]] = []
        self.framebuffer: Optional[Dict[str, Any]] = None
        self._validate_manifest()

    @classmethod
    def load(cls, path: str | Path) -> "Snapshot":
        snapshot_path = Path(path).resolve()
        try:
            with snapshot_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except OSError as exc:
            raise SnapshotError("MANIFEST_READ_ERROR", str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise SnapshotError("MANIFEST_INVALID", str(exc)) from exc
        if not isinstance(manifest, dict):
            raise SnapshotError("MANIFEST_INVALID", "manifest root must be an object")
        return cls(manifest, snapshot_path, snapshot_path.parent)

    @classmethod
    def from_manifest(
        cls, manifest: Dict[str, Any], base_dir: Optional[str | Path] = None
    ) -> "Snapshot":
        return cls(manifest, None, Path(base_dir or Path.cwd()))

    def _validate_manifest(self) -> None:
        if self.manifest.get("schema") != "dreyzeos.mmu_snapshot.v1":
            raise SnapshotError(
                "MANIFEST_INVALID",
                "schema must be dreyzeos.mmu_snapshot.v1",
            )
        if self.manifest.get("architecture") != "aarch64":
            raise SnapshotError(
                "UNSUPPORTED_CONFIGURATION",
                "only architecture=aarch64 is supported",
            )
        if not isinstance(self.manifest.get("target", {}), dict):
            raise SnapshotError("MANIFEST_INVALID", "target must be an object")
        registers = self.manifest.get("registers", {})
        if not isinstance(registers, dict):
            raise SnapshotError("MANIFEST_INVALID", "registers must be an object")
        for name, entry in registers.items():
            if not isinstance(entry, dict):
                raise SnapshotError(
                    "MANIFEST_INVALID", f"register {name} must be an object"
                )
            present = bool(entry.get("value_present", False))
            proven = bool(entry.get("value_proven", False))
            value: Optional[int] = None
            if present:
                if "value" not in entry:
                    raise SnapshotError(
                        "MANIFEST_INVALID",
                        f"register {name} is present without value",
                    )
                value = parse_uint(entry["value"], f"register {name}")
            self.registers[name] = {
                "value": value,
                "value_present": present,
                "value_proven": proven,
            }

        raw_regions = self.manifest.get("physical_memory_regions", [])
        if not isinstance(raw_regions, list):
            raise SnapshotError(
                "MANIFEST_INVALID", "physical_memory_regions must be an array"
            )
        for index, raw_region in enumerate(raw_regions):
            self.regions.append(self._load_region(raw_region, index))
        loaded_ranges: List[Tuple[int, int]] = []
        for region in self.regions:
            if not region.data:
                continue
            for old_base, old_end in loaded_ranges:
                if region.physical_base < old_end and old_base < region.data_end:
                    raise SnapshotError(
                        "MANIFEST_INVALID",
                        "loaded physical regions overlap ambiguously",
                    )
            loaded_ranges.append((region.physical_base, region.data_end))

        raw_protected = self.manifest.get("protected_regions", [])
        if not isinstance(raw_protected, list):
            raise SnapshotError("MANIFEST_INVALID", "protected_regions must be an array")
        for index, item in enumerate(raw_protected):
            self.protected_regions.append(
                self._load_named_range(item, f"protected_regions[{index}]")
            )

        raw_search = self.manifest.get("virtual_search_ranges", [])
        if not isinstance(raw_search, list):
            raise SnapshotError(
                "MANIFEST_INVALID", "virtual_search_ranges must be an array"
            )
        for index, item in enumerate(raw_search):
            parsed = self._load_named_range(
                item, f"virtual_search_ranges[{index}", default_space="virtual"
            )
            parsed["ttbr"] = str(item.get("ttbr", "auto"))
            if parsed["ttbr"] not in {"auto", "ttbr0", "ttbr1"}:
                raise SnapshotError(
                    "MANIFEST_INVALID",
                    f"virtual_search_ranges[{index}] has invalid ttbr",
                )
            self.virtual_search_ranges.append(parsed)

        if "framebuffer" in self.manifest:
            item = self.manifest["framebuffer"]
            if not isinstance(item, dict):
                raise SnapshotError("MANIFEST_INVALID", "framebuffer must be an object")
            if "physical_base" not in item or "size" not in item:
                raise SnapshotError(
                    "MANIFEST_INVALID",
                    "framebuffer requires physical_base and size",
                )
            self.framebuffer = {
                "physical_base": parse_uint(
                    item["physical_base"], "framebuffer.physical_base"
                ),
                "size": parse_uint(item["size"], "framebuffer.size"),
                "provenance": _status_or_unknown(item.get("provenance", "UNKNOWN")),
                "description": str(item.get("description", "")),
            }
            if self.framebuffer["size"] == 0:
                raise SnapshotError(
                    "MANIFEST_INVALID", "framebuffer.size must not be zero"
                )
            checked_add(
                self.framebuffer["physical_base"],
                self.framebuffer["size"],
                "framebuffer",
            )

    def _load_named_range(
        self,
        item: Any,
        name: str,
        default_space: str = "physical",
    ) -> Dict[str, Any]:
        if not isinstance(item, dict):
            raise SnapshotError("MANIFEST_INVALID", f"{name} must be an object")
        if "base" in item:
            base_value = item["base"]
        elif "physical_base" in item:
            base_value = item["physical_base"]
        else:
            raise SnapshotError("MANIFEST_INVALID", f"{name} has no base")
        if "length" in item:
            length_value = item["length"]
        elif "size" in item:
            length_value = item["size"]
        else:
            raise SnapshotError("MANIFEST_INVALID", f"{name} has no length")
        base = parse_uint(base_value, f"{name}.base")
        length = parse_uint(length_value, f"{name}.length")
        if length == 0:
            raise SnapshotError("MANIFEST_INVALID", f"{name}.length is zero")
        checked_add(base, length, name)
        address_space = str(item.get("address_space", default_space))
        if address_space not in {"physical", "virtual"}:
            raise SnapshotError(
                "MANIFEST_INVALID", f"{name}.address_space is invalid"
            )
        return {
            "name": str(item.get("name", name)),
            "base": base,
            "length": length,
            "address_space": address_space,
            "provenance": _status_or_unknown(item.get("provenance", "UNKNOWN")),
        }

    def _load_region(self, item: Any, index: int) -> MemoryRegion:
        name = f"physical_memory_regions[{index}]"
        if not isinstance(item, dict):
            raise SnapshotError("MANIFEST_INVALID", f"{name} must be an object")
        if "physical_base" not in item or "length" not in item:
            raise SnapshotError(
                "MANIFEST_INVALID", f"{name} requires physical_base and length"
            )
        base = parse_uint(item["physical_base"], f"{name}.physical_base")
        length = parse_uint(item["length"], f"{name}.length")
        if length == 0:
            raise SnapshotError("MANIFEST_INVALID", f"{name}.length is zero")
        checked_add(base, length, name)
        has_data_source = any(
            key in item for key in ("file", "data_hex", "data_words")
        )
        bytes_present = bool(item.get("memory_bytes_present", has_data_source))
        complete = bool(item.get("memory_range_complete", bytes_present))
        data = b""
        if bytes_present:
            sources = sum(1 for key in ("file", "data_hex", "data_words") if key in item)
            if sources != 1:
                raise SnapshotError(
                    "MANIFEST_INVALID",
                    f"{name} needs exactly one local data source",
                )
            if "file" in item:
                relative = Path(str(item["file"]))
                if relative.is_absolute():
                    raise SnapshotError(
                        "MANIFEST_INVALID", f"{name}.file must be relative"
                    )
                candidate = (self.base_dir / relative).resolve()
                try:
                    candidate.relative_to(self.base_dir)
                except ValueError as exc:
                    raise SnapshotError(
                        "MANIFEST_INVALID", f"{name}.file escapes manifest directory"
                    ) from exc
                try:
                    with candidate.open("rb") as handle:
                        offset = parse_uint(
                            item.get("file_offset", 0),
                            f"{name}.file_offset",
                            maximum=U64_MAX,
                        )
                        handle.seek(offset)
                        data = handle.read(length)
                except OSError as exc:
                    raise SnapshotError("MEMORY_BLOB_READ_ERROR", str(exc)) from exc
                if complete and len(data) != length:
                    raise SnapshotError(
                        "PHYSICAL_DUMP_INCOMPLETE",
                        f"{name}.file is shorter than declared length",
                        available=len(data),
                        declared=length,
                    )
            elif "data_hex" in item:
                try:
                    data = bytes.fromhex(str(item["data_hex"]))
                except ValueError as exc:
                    raise SnapshotError(
                        "MANIFEST_INVALID", f"{name}.data_hex is invalid"
                    ) from exc
            else:
                if self.source.get("kind") != "synthetic":
                    raise SnapshotError(
                        "MANIFEST_INVALID",
                        f"{name}.data_words is reserved for synthetic fixtures",
                    )
                data = bytearray(length)
                words = item["data_words"]
                if not isinstance(words, list):
                    raise SnapshotError(
                        "MANIFEST_INVALID", f"{name}.data_words must be an array"
                    )
                for word_index, word in enumerate(words):
                    if not isinstance(word, dict):
                        raise SnapshotError(
                            "MANIFEST_INVALID",
                            f"{name}.data_words[{word_index}] must be an object",
                        )
                    offset = parse_uint(
                        word.get("offset"),
                        f"{name}.data_words[{word_index}].offset",
                    )
                    value = parse_uint(
                        word.get("value"),
                        f"{name}.data_words[{word_index}].value",
                    )
                    if offset % 8 != 0 or offset + 8 > length:
                        raise SnapshotError(
                            "MANIFEST_INVALID",
                            f"{name}.data_words[{word_index}] is outside region",
                        )
                    data[offset : offset + 8] = value.to_bytes(8, "little")
                data = bytes(data)
        if len(data) > length:
            raise SnapshotError(
                "MANIFEST_INVALID",
                f"{name} data exceeds declared length",
            )
        if complete and len(data) != length:
            raise SnapshotError(
                "PHYSICAL_DUMP_INCOMPLETE",
                f"{name} is marked complete but bytes are missing",
                available=len(data),
                declared=length,
            )
        return MemoryRegion(
            physical_base=base,
            declared_length=length,
            data=data,
            memory_bytes_present=bytes_present and bool(data),
            memory_range_complete=complete and len(data) == length,
            label=str(item.get("label", item.get("file", name))),
        )

    def register(self, name: str, required: bool = True) -> Dict[str, Any]:
        item = self.registers.get(name)
        if item is None or not item["value_present"]:
            if required:
                raise SnapshotError(
                    "REGISTER_MISSING", f"register {name} is not present"
                )
            return {"value_present": False, "value_proven": False, "value": None}
        return dict(item)

    def register_value(self, name: str, required: bool = True) -> int:
        item = self.register(name, required=required)
        value = item.get("value")
        if value is None:
            raise SnapshotError("REGISTER_MISSING", f"register {name} is not present")
        return int(value)

    def read_physical(self, address: int, length: int) -> Tuple[bytes, bool]:
        """Read only supplied local bytes; never falls back to a host pointer."""
        address = parse_uint(address, "physical address")
        length = parse_uint(length, "read length")
        if length == 0:
            return b"", True
        end = checked_add(address, length, "physical read")
        cursor = address
        result = bytearray()
        complete = True
        while cursor < end:
            candidate: Optional[MemoryRegion] = None
            for region in self.regions:
                if region.data_contains(cursor):
                    candidate = region
                    break
            if candidate is None:
                declared = any(region.declared_contains(cursor) for region in self.regions)
                code = "PHYSICAL_DUMP_INCOMPLETE" if declared else "TABLE_BYTES_MISSING"
                raise SnapshotError(
                    code,
                    "requested physical bytes are not present in supplied snapshot",
                    address=cursor,
                    length=end - cursor,
                )
            chunk_end = min(end, candidate.data_end)
            offset = cursor - candidate.physical_base
            result.extend(candidate.data[offset : offset + (chunk_end - cursor)])
            complete = complete and candidate.memory_range_complete
            cursor = chunk_end
        return bytes(result), complete


def _decode_granule(role: str, code: int) -> Tuple[Optional[int], Optional[str]]:
    table = TCR_TG0 if role == "ttbr0" else TCR_TG1
    return table.get(code, (None, None))


def _decode_regime(
    role: str,
    tnsz: int,
    tg_code: int,
    epd: bool,
    sh: int,
    orgn: int,
    irgn: int,
) -> Dict[str, Any]:
    page_size, granule_name = _decode_granule(role, tg_code)
    regime: Dict[str, Any] = {
        "ttbr": role,
        "tnsz": tnsz,
        "va_bits": 64 - tnsz,
        "tg_code": tg_code,
        "granule": page_size,
        "granule_name": granule_name,
        "page_shift": page_size.bit_length() - 1 if page_size else None,
        "epd": epd,
        "sh": sh,
        "shareability": {0: "non-shareable", 2: "outer-shareable", 3: "inner-shareable"}.get(
            sh, "reserved"
        ),
        "orgn": orgn,
        "irgn": irgn,
        "cacheability": {
            0: "normal-non-cacheable",
            1: "write-back-write-allocate",
            2: "write-through",
            3: "write-back-no-write-allocate",
        }.get(irgn, "reserved"),
        "supported": True,
        "status": "SUPPORTED",
    }
    if page_size is None:
        regime.update(
            supported=False,
            status="UNSUPPORTED_GRANULE",
            reason="TCR granule encoding is reserved for this TTBR",
        )
        return regime
    va_bits = regime["va_bits"]
    page_shift = regime["page_shift"]
    index_bits = {4096: 9, 16384: 11, 65536: 13}[page_size]
    regime["index_bits"] = index_bits
    if va_bits < page_shift + 1 or va_bits > 52:
        regime.update(
            supported=False,
            status="UNSUPPORTED_CONFIGURATION",
            reason="VA width is outside the offline walker's supported range",
        )
        return regime
    levels = (va_bits - page_shift + index_bits - 1) // index_bits
    first_level_bits = va_bits - page_shift - index_bits * (levels - 1)
    if levels < 1 or levels > 4 or not (1 <= first_level_bits <= index_bits):
        regime.update(
            supported=False,
            status="UNSUPPORTED_CONFIGURATION",
            reason="translation geometry does not fit supported levels",
        )
        return regime
    regime["levels"] = levels
    regime["first_level_bits"] = first_level_bits
    regime["level_sizes"] = [
        1 << (page_shift + index_bits * (levels - 1 - level))
        for level in range(levels)
    ]
    regime["level_index_bits"] = [
        first_level_bits if level == 0 else index_bits for level in range(levels)
    ]
    return regime


def decode_tcr(tcr: int) -> Dict[str, Any]:
    """Decode TCR_EL1 without assuming a granule or VA width."""
    tcr = parse_uint(tcr, "TCR_EL1")
    ips_code = (tcr >> 32) & 0x7
    result: Dict[str, Any] = {
        "raw": tcr,
        "raw_hex": f"0x{tcr:016x}",
        "ips_code": ips_code,
        "physical_address_bits": IPS_BITS.get(ips_code),
        "a1": bool((tcr >> 22) & 1),
        "as": (tcr >> 36) & 0x3,
        "ha": bool((tcr >> 39) & 1),
        "hd": bool((tcr >> 40) & 1),
        "physical_address_status": (
            "SUPPORTED" if ips_code in IPS_BITS else "UNSUPPORTED_IPS"
        ),
    }
    result["regimes"] = {
        "ttbr0": _decode_regime(
            "ttbr0",
            tcr & 0x3F,
            (tcr >> 14) & 0x3,
            bool((tcr >> 7) & 1),
            (tcr >> 12) & 0x3,
            (tcr >> 10) & 0x3,
            (tcr >> 8) & 0x3,
        ),
        "ttbr1": _decode_regime(
            "ttbr1",
            (tcr >> 16) & 0x3F,
            (tcr >> 30) & 0x3,
            bool((tcr >> 23) & 1),
            (tcr >> 28) & 0x3,
            (tcr >> 26) & 0x3,
            (tcr >> 24) & 0x3,
        ),
    }
    result["supported"] = (
        ips_code in IPS_BITS
        and result["regimes"]["ttbr0"]["supported"]
        and result["regimes"]["ttbr1"]["supported"]
    )
    result["status"] = "SUPPORTED" if result["supported"] else "UNSUPPORTED"
    return result


def decode_mair(mair: int, attr_index: int) -> Dict[str, Any]:
    """Decode one MAIR slot conservatively; raw encoding remains authoritative."""
    mair = parse_uint(mair, "MAIR_EL1")
    if attr_index < 0 or attr_index > 7:
        raise SnapshotError("INVALID_VALUE", "AttrIndx must be in the range 0..7")
    raw = (mair >> (attr_index * 8)) & 0xFF
    if raw in MAIR_DEVICE_VALUES:
        category = "Device"
        detail = MAIR_DEVICE_VALUES[raw]
    elif (raw >> 4) in MAIR_NORMAL_NIBBLES and (raw & 0xF) in MAIR_NORMAL_NIBBLES:
        category = "Normal"
        detail = "architecturally recognised Normal encoding"
    else:
        category = "Unknown/implementation-specific"
        detail = "raw MAIR byte retained; no stronger category asserted"
    return {
        "attr_index": attr_index,
        "raw": raw,
        "raw_hex": f"0x{raw:02x}",
        "category": category,
        "detail": detail,
    }


def _error_result(code: str, message: str, **details: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {"ok": False, "status": code, "error": message}
    result.update(details)
    return result


def _canonical_region(
    va: int, tcr: Dict[str, Any]
) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    candidates: List[Tuple[str, Dict[str, Any]]] = []
    if not tcr.get("supported"):
        return None, None, "TCR_UNSUPPORTED"
    for role in ("ttbr0", "ttbr1"):
        regime = tcr["regimes"][role]
        if not regime["supported"]:
            continue
        width = regime["va_bits"]
        if role == "ttbr0":
            if va < (1 << width):
                candidates.append((role, regime))
        else:
            high_base = U64_LIMIT - (1 << width)
            if va >= high_base:
                candidates.append((role, regime))
    if len(candidates) == 1:
        return candidates[0][0], candidates[0][1], None
    if len(candidates) > 1:
        return None, None, "UNSUPPORTED_CONFIGURATION"
    return None, None, "NON_CANONICAL_VA"


def _ttbr_base(value: int, page_size: int, pa_bits: int) -> int:
    base = value & ~(page_size - 1)
    pa_limit = 1 << pa_bits
    if base >= pa_limit or base % page_size != 0:
        raise SnapshotError(
            "PHYSICAL_ADDRESS_WIDTH",
            "TTBR base is outside the configured physical address width",
            base=base,
            physical_address_bits=pa_bits,
        )
    return base


def _table_pointer(raw: int, page_size: int, pa_bits: int) -> int:
    low_reserved = raw & ((page_size - 1) & ~0x3)
    if low_reserved:
        raise SnapshotError(
            "INVALID_DESCRIPTOR",
            "table descriptor contains non-zero low reserved bits",
            reserved=low_reserved,
        )
    pa_mask = (1 << pa_bits) - 1
    base = raw & pa_mask & ~(page_size - 1)
    if base >= (1 << pa_bits):
        raise SnapshotError(
            "PHYSICAL_ADDRESS_WIDTH",
            "table descriptor points outside configured PA width",
        )
    return base


def _leaf_attributes(
    snapshot: Snapshot, raw: int, table_restrictions: bool
) -> Dict[str, Any]:
    attr_index = (raw >> 2) & 0x7
    mair_info: Dict[str, Any]
    mair_item = snapshot.register("mair_el1", required=False)
    if mair_item["value_present"]:
        mair_info = decode_mair(int(mair_item["value"]), attr_index)
    else:
        mair_info = {
            "attr_index": attr_index,
            "raw": None,
            "raw_hex": None,
            "category": "Unknown/implementation-specific",
            "detail": "MAIR_EL1 is not present in the snapshot",
        }
    ap = (raw >> 6) & 0x3
    sh = (raw >> 8) & 0x3
    af = bool((raw >> 10) & 1)
    contiguous = bool((raw >> 52) & 1)
    pxn = bool((raw >> 53) & 1)
    uxn = bool((raw >> 54) & 1)
    permission_reason = "descriptor AP/PXN/UXN with AF set"
    if table_restrictions:
        permission_reason = (
            "table permission/XN restrictions are non-zero and not promoted "
            "to loader authority"
        )
    if not af or table_restrictions:
        readable: Optional[bool] = None
        writable: Optional[bool] = None
        executable_el1: Optional[bool] = None
        executable_el0: Optional[bool] = None
    else:
        readable = True
        writable = ap in (0, 1)
        executable_el1 = not pxn
        executable_el0 = not uxn
    return {
        "attr_index": attr_index,
        "mair": mair_info,
        "ap": ap,
        "ap_description": {
            0: "EL1 read-write, EL0 no access",
            1: "EL1 read-write, EL0 read-write",
            2: "EL1 read-only, EL0 no access",
            3: "EL1 read-only, EL0 read-only",
        }.get(ap, "reserved"),
        "shareability": {0: "non-shareable", 2: "outer-shareable", 3: "inner-shareable"}.get(
            sh, "reserved"
        ),
        "shareability_raw": sh,
        "access_flag": af,
        "access_fault_possible": not af,
        "contiguous": contiguous,
        "pxn": pxn,
        "uxn": uxn,
        "readable": readable,
        "writable": writable,
        "executable": executable_el1,
        "executable_el1": executable_el1,
        "executable_el0": executable_el0,
        "permission_evidence": permission_reason,
    }


def walk_va(
    snapshot: Snapshot,
    virtual_address: int,
    ttbr: str = "auto",
) -> Dict[str, Any]:
    """Walk one VA using only descriptor bytes supplied by Snapshot."""
    try:
        va = parse_uint(virtual_address, "virtual address")
        if ttbr not in {"auto", "ttbr0", "ttbr1"}:
            return _error_result("INVALID_VALUE", "ttbr must be auto, ttbr0, or ttbr1")
        tcr_value = snapshot.register_value("tcr_el1")
        tcr = decode_tcr(tcr_value)
        if not tcr["supported"]:
            return _error_result(
                tcr["status"],
                "TCR configuration is not supported by the offline walker",
                tcr=tcr,
            )
        selected, regime, selection_error = _canonical_region(va, tcr)
        if selection_error:
            return _error_result(selection_error, "VA is not canonical for TCR_EL1", tcr=tcr)
        if ttbr != "auto" and selected != ttbr:
            return _error_result(
                "TTBR_SELECTION_MISMATCH",
                "explicit TTBR does not own this canonical VA",
                selected_ttbr=selected,
            )
        assert selected is not None
        assert regime is not None
        if regime["epd"]:
            return _error_result(
                "TRANSLATION_DISABLED",
                f"{selected} translation is disabled by TCR_EL1",
                selected_ttbr=selected,
            )
        pa_bits = tcr["physical_address_bits"]
        if pa_bits is None:
            return _error_result("UNSUPPORTED_IPS", "TCR IPS is reserved")
        ttbr_value = snapshot.register_value(f"{selected}_el1")
        table_base = _ttbr_base(ttbr_value, regime["granule"], pa_bits)
        indexes: List[int] = []
        for level, bits in enumerate(regime["level_index_bits"]):
            shift = regime["page_shift"] + regime["index_bits"] * (
                regime["levels"] - 1 - level
            )
            indexes.append((va >> shift) & ((1 << bits) - 1))

        path: List[Dict[str, Any]] = []
        dump_complete = True
        table_restrictions = False
        visited_tables: set[int] = set()
        for level, index in enumerate(indexes):
            if table_base in visited_tables:
                return _error_result(
                    "CYCLIC_TABLE", "translation path revisits a table page"
                )
            visited_tables.add(table_base)
            offset = checked_mul(index, 8, "descriptor offset")
            descriptor_pa = checked_add(table_base, offset, "descriptor physical address")
            descriptor_bytes, region_complete = snapshot.read_physical(descriptor_pa, 8)
            dump_complete = dump_complete and region_complete
            raw = int.from_bytes(descriptor_bytes, "little")
            last = level == regime["levels"] - 1
            descriptor: Dict[str, Any] = {
                "level": level,
                "index": index,
                "descriptor_physical_address": descriptor_pa,
                "descriptor_raw": raw,
                "descriptor_raw_hex": f"0x{raw:016x}",
            }
            path.append(descriptor)
            if (raw & 1) == 0:
                return {
                    "ok": False,
                    "mapped": False,
                    "status": "UNMAPPED",
                    "input_va": va,
                    "selected_ttbr": selected,
                    "translation_level": level,
                    "translation_path": path,
                    "physical_dump_complete": dump_complete,
                }
            is_table = bool(raw & 0x2) and not last
            is_page = bool(raw & 0x2) and last
            is_block = not bool(raw & 0x2) and not last
            if is_table:
                descriptor["descriptor_type"] = "table"
                try:
                    table_base = _table_pointer(raw, regime["granule"], pa_bits)
                except SnapshotError as exc:
                    return exc.as_dict() | {
                        "input_va": va,
                        "selected_ttbr": selected,
                        "translation_path": path,
                    }
                descriptor["next_table_physical_base"] = table_base
                table_restrictions = table_restrictions or bool(
                    ((raw >> 61) & 0x3) or ((raw >> 59) & 0x3)
                )
                continue
            if not (is_page or is_block):
                descriptor["descriptor_type"] = "invalid"
                return {
                    "ok": False,
                    "mapped": False,
                    "status": "INVALID_DESCRIPTOR",
                    "error": "descriptor type is reserved at this level",
                    "input_va": va,
                    "selected_ttbr": selected,
                    "translation_path": path,
                }
            descriptor_type = "page" if is_page else "block"
            descriptor["descriptor_type"] = descriptor_type
            mapping_size = regime["granule"] if is_page else regime["level_sizes"][level]
            low_reserved = raw & ((mapping_size - 1) & ~0xFFF)
            if low_reserved:
                return {
                    "ok": False,
                    "mapped": False,
                    "status": "INVALID_DESCRIPTOR",
                    "error": "leaf descriptor has non-zero output-address reserved bits",
                    "reserved": low_reserved,
                    "input_va": va,
                    "selected_ttbr": selected,
                    "translation_path": path,
                }
            if pa_bits < 55:
                high_reserved = raw & (((1 << 52) - 1) & ~((1 << pa_bits) - 1))
                if high_reserved:
                    return {
                        "ok": False,
                        "mapped": False,
                        "status": "PHYSICAL_ADDRESS_WIDTH",
                        "error": "leaf descriptor contains address bits above IPS",
                        "input_va": va,
                        "selected_ttbr": selected,
                        "translation_path": path,
                    }
            pa_mask = (1 << pa_bits) - 1
            output_base = raw & pa_mask & ~(mapping_size - 1)
            if output_base + mapping_size > (1 << pa_bits):
                return {
                    "ok": False,
                    "mapped": False,
                    "status": "PHYSICAL_ADDRESS_WIDTH",
                    "error": "leaf mapping exceeds configured physical address width",
                    "input_va": va,
                    "selected_ttbr": selected,
                    "translation_path": path,
                }
            offset_in_mapping = va & (mapping_size - 1)
            output_pa = output_base + offset_in_mapping
            attributes = _leaf_attributes(snapshot, raw, table_restrictions)
            return {
                "ok": True,
                "mapped": True,
                "status": "MAPPED",
                "evidence_status": snapshot.evidence_status,
                "evidence_class": "SYNTHETIC" if snapshot.source.get("kind") == "synthetic" else "CAPTURED_OR_UNKNOWN",
                "input_va": va,
                "selected_ttbr": selected,
                "translation_level": level,
                "descriptor_physical_address": descriptor_pa,
                "descriptor_raw": raw,
                "descriptor_raw_hex": f"0x{raw:016x}",
                "descriptor_type": descriptor_type,
                "output_pa": output_pa,
                "output_pa_hex": f"0x{output_pa:016x}",
                "mapping_va_base": va - offset_in_mapping,
                "mapping_pa_base": output_base,
                "page_or_block_size": mapping_size,
                "page_or_block_size_hex": f"0x{mapping_size:x}",
                "physical_dump_complete": dump_complete,
                "attributes": attributes,
                "translation_path": path,
            }
        return _error_result("INVALID_DESCRIPTOR", "walk ended without a leaf")
    except SnapshotError as exc:
        return exc.as_dict()
    except (ArithmeticError, ValueError, TypeError) as exc:
        return _error_result("ANALYZER_ERROR", str(exc))


def _property_all(segments: Sequence[Dict[str, Any]], key: str) -> Optional[bool]:
    values = [segment["attributes"].get(key) for segment in segments]
    if not values:
        return None
    if any(value is None for value in values):
        return None
    return all(bool(value) for value in values)


def _permission_signature(segment: Dict[str, Any]) -> Tuple[Any, ...]:
    attrs = segment["attributes"]
    mair = attrs.get("mair", {})
    return (
        attrs.get("readable"),
        attrs.get("writable"),
        attrs.get("executable"),
        attrs.get("ap"),
        attrs.get("pxn"),
        attrs.get("uxn"),
        attrs.get("attr_index"),
        mair.get("raw"),
        attrs.get("shareability_raw"),
    )


def analyze_range(
    snapshot: Snapshot,
    virtual_base: int,
    length: int,
    ttbr: str = "auto",
) -> Dict[str, Any]:
    """Walk every mapping boundary in a VA interval."""
    try:
        base = parse_uint(virtual_base, "virtual base")
        length_value = parse_uint(length, "range length")
        if length_value == 0:
            return _error_result("INVALID_RANGE", "range length must be non-zero")
        end = checked_add(base, length_value, "virtual range")
        cursor = base
        raw_segments: List[Dict[str, Any]] = []
        first_failure: Optional[Dict[str, Any]] = None
        max_steps = 1_000_000
        while cursor < end:
            if len(raw_segments) >= max_steps:
                return _error_result(
                    "RANGE_TOO_LARGE",
                    "range would require more than one million mapping walks",
                )
            result = walk_va(snapshot, cursor, ttbr)
            if not result.get("ok"):
                first_failure = {
                    "virtual_address": cursor,
                    "status": result.get("status"),
                    "error": result.get("error"),
                    "detail": result,
                }
                break
            mapping_end = checked_add(
                int(result["mapping_va_base"]),
                int(result["page_or_block_size"]),
                "mapping boundary",
            )
            chunk_end = min(end, mapping_end)
            if chunk_end <= cursor:
                return _error_result(
                    "ANALYZER_ERROR", "walker returned a non-advancing mapping"
                )
            chunk_length = chunk_end - cursor
            pa = int(result["output_pa"])
            segment = {
                "virtual_base": cursor,
                "length": chunk_length,
                "physical_base": pa,
                "descriptor_type": result["descriptor_type"],
                "translation_level": result["translation_level"],
                "mapping_size": result["page_or_block_size"],
                "attributes": result["attributes"],
                "physical_dump_complete": result["physical_dump_complete"],
            }
            raw_segments.append(segment)
            cursor = chunk_end

        if first_failure is None:
            coverage = "fully_mapped"
        elif raw_segments:
            coverage = "partially_mapped"
        elif first_failure["status"] == "UNMAPPED":
            coverage = "unmapped"
        else:
            coverage = "error"
        result: Dict[str, Any] = {
            "ok": first_failure is None,
            "status": coverage,
            "virtual_base": base,
            "length": length_value,
            "virtual_end": end,
            "segments": raw_segments,
            "mapped_physical_intervals": [
                {
                    "physical_base": segment["physical_base"],
                    "virtual_base": segment["virtual_base"],
                    "length": segment["length"],
                }
                for segment in raw_segments
            ],
            "first_failure": first_failure,
            "fully_mapped": coverage == "fully_mapped",
            "partially_mapped": coverage == "partially_mapped",
            "unmapped": coverage == "unmapped",
            "readable": _property_all(raw_segments, "readable")
            if first_failure is None
            else None,
            "writable": _property_all(raw_segments, "writable")
            if first_failure is None
            else None,
            "executable": _property_all(raw_segments, "executable")
            if first_failure is None
            else None,
            "physical_contiguous": None,
            "permission_changes": [],
            "attribute_changes": [],
            "page_block_transitions": [],
            "evidence_status": snapshot.evidence_status,
            "loader_authority": "NOT_PROVEN",
        }
        if raw_segments:
            contiguous = True
            for previous, current in zip(raw_segments, raw_segments[1:]):
                expected_pa = checked_add(previous["physical_base"], previous["length"], "mapped physical interval")
                if expected_pa != current["physical_base"]:
                    contiguous = False
                if _permission_signature(previous) != _permission_signature(current):
                    result["permission_changes"].append(
                        {
                            "at_virtual_address": current["virtual_base"],
                            "from": _permission_signature(previous),
                            "to": _permission_signature(current),
                        }
                    )
                prev_attr = previous["attributes"]
                curr_attr = current["attributes"]
                if (
                    prev_attr.get("attr_index") != curr_attr.get("attr_index")
                    or prev_attr.get("mair", {}).get("raw")
                    != curr_attr.get("mair", {}).get("raw")
                    or prev_attr.get("shareability_raw")
                    != curr_attr.get("shareability_raw")
                ):
                    result["attribute_changes"].append(
                        {"at_virtual_address": current["virtual_base"]}
                    )
                if (
                    previous["descriptor_type"] != current["descriptor_type"]
                    or previous["mapping_size"] != current["mapping_size"]
                ):
                    result["page_block_transitions"].append(
                        {
                            "at_virtual_address": current["virtual_base"],
                            "from": {
                                "type": previous["descriptor_type"],
                                "size": previous["mapping_size"],
                            },
                            "to": {
                                "type": current["descriptor_type"],
                                "size": current["mapping_size"],
                            },
                        }
                    )
            result["physical_contiguous"] = contiguous
        return result
    except SnapshotError as exc:
        return exc.as_dict()


def _read_c_string(blob: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(blob):
        return ""
    end = blob.find(b"\0", offset)
    if end < 0:
        end = len(blob)
    return blob[offset:end].decode("utf-8", errors="replace")


class ElfImage:
    """Small dependency-free ELF64/AArch64 reader for analysis reports."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        try:
            self.data = self.path.read_bytes()
        except OSError as exc:
            raise SnapshotError("ELF_READ_ERROR", str(exc)) from exc
        self.sections: List[Dict[str, Any]] = []
        self.symbols: Dict[str, Dict[str, Any]] = {}
        self.program_headers: List[Dict[str, Any]] = []
        self._parse()

    def _parse(self) -> None:
        if len(self.data) < 64:
            raise SnapshotError("ELF_INVALID", "ELF header is truncated")
        ident = self.data[:16]
        if ident[:4] != b"\x7fELF" or ident[4] != 2 or ident[5] != 1:
            raise SnapshotError("ELF_INVALID", "expected little-endian ELF64")
        (
            _ident,
            e_type,
            e_machine,
            _version,
            e_entry,
            e_phoff,
            e_shoff,
            _flags,
            e_ehsize,
            e_phentsize,
            e_phnum,
            e_shentsize,
            e_shnum,
            e_shstrndx,
        ) = struct.unpack_from("<16sHHIQQQIHHHHHH", self.data, 0)
        if e_machine != 183:
            raise SnapshotError("ELF_INVALID", "ELF is not AArch64")
        if e_ehsize < 64 or e_phentsize < 56 or e_shentsize < 64:
            raise SnapshotError("ELF_INVALID", "unsupported ELF header sizes")
        ph_end = e_phoff + e_phentsize * e_phnum
        sh_end = e_shoff + e_shentsize * e_shnum
        if ph_end > len(self.data) or sh_end > len(self.data):
            raise SnapshotError("ELF_INVALID", "ELF tables are truncated")
        for index in range(e_phnum):
            offset = e_phoff + index * e_phentsize
            p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = (
                struct.unpack_from("<IIQQQQQQ", self.data, offset)
            )
            self.program_headers.append(
                {
                    "index": index,
                    "type": p_type,
                    "flags": p_flags,
                    "offset": p_offset,
                    "vaddr": p_vaddr,
                    "paddr": p_paddr,
                    "filesz": p_filesz,
                    "memsz": p_memsz,
                    "align": p_align,
                }
            )
        raw_sections: List[Dict[str, Any]] = []
        for index in range(e_shnum):
            offset = e_shoff + index * e_shentsize
            (
                sh_name,
                sh_type,
                sh_flags,
                sh_addr,
                sh_offset,
                sh_size,
                sh_link,
                sh_info,
                sh_addralign,
                sh_entsize,
            ) = struct.unpack_from("<IIQQQQIIQQ", self.data, offset)
            raw_sections.append(
                {
                    "index": index,
                    "name_offset": sh_name,
                    "type": sh_type,
                    "flags": sh_flags,
                    "address": sh_addr,
                    "offset": sh_offset,
                    "size": sh_size,
                    "link": sh_link,
                    "info": sh_info,
                    "align": sh_addralign,
                    "entsize": sh_entsize,
                }
            )
        if e_shstrndx >= len(raw_sections):
            raise SnapshotError("ELF_INVALID", "section string table index is invalid")
        shstr = raw_sections[e_shstrndx]
        shstr_end = shstr["offset"] + shstr["size"]
        if shstr_end > len(self.data):
            raise SnapshotError("ELF_INVALID", "section string table is truncated")
        shstr_blob = self.data[shstr["offset"] : shstr_end]
        for section in raw_sections:
            item = dict(section)
            item["name"] = _read_c_string(shstr_blob, section["name_offset"])
            self.sections.append(item)
        for section in self.sections:
            if section["type"] != 2:
                continue
            link = section["link"]
            if link >= len(self.sections):
                continue
            strtab = self.sections[link]
            str_end = strtab["offset"] + strtab["size"]
            if str_end > len(self.data):
                raise SnapshotError("ELF_INVALID", "symbol string table is truncated")
            strings = self.data[strtab["offset"] : str_end]
            entsize = section["entsize"] or 24
            if entsize < 24:
                raise SnapshotError("ELF_INVALID", "symbol entry size is too small")
            table_end = section["offset"] + section["size"]
            if table_end > len(self.data):
                raise SnapshotError("ELF_INVALID", "symbol table is truncated")
            for offset in range(section["offset"], table_end, entsize):
                if offset + 24 > table_end:
                    break
                st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from(
                    "<IBBHQQ", self.data, offset
                )
                name = _read_c_string(strings, st_name)
                if name and name not in self.symbols:
                    self.symbols[name] = {
                        "name": name,
                        "value": st_value,
                        "size": st_size,
                        "info": st_info,
                        "section_index": st_shndx,
                    }
        self.header = {
            "type": e_type,
            "machine": e_machine,
            "entry": e_entry,
            "entry_hex": f"0x{e_entry:x}",
            "program_headers": e_phnum,
            "sections": e_shnum,
        }

    def symbol_report(self, names: Iterable[str]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for name in names:
            item = self.symbols.get(name)
            result[name] = None if item is None else {
                "value": item["value"],
                "value_hex": f"0x{item['value']:x}",
                "size": item["size"],
                "section_index": item["section_index"],
            }
        return result


REQUIRED_SYMBOLS = (
    "_start",
    "__kernel_start",
    "__kernel_end",
    "__bss_start",
    "__bss_end",
    "__stack_bottom",
    "__stack_top",
    "_exception_vectors_base",
)


def _intended_section_permissions(section: Dict[str, Any]) -> Dict[str, Any]:
    flags = section["flags"]
    executable = bool(flags & 0x4)
    writable = bool(flags & 0x1)
    return {
        "readable": True,
        "writable": writable,
        "executable": executable,
        "basis": f"ELF section flags 0x{flags:x}; hardware mapping remains separate evidence",
    }


def _compare_permissions(
    intended: Dict[str, Any], actual: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    if actual is None:
        return {"status": "BLOCKED", "reason": "no snapshot supplied"}
    if actual.get("status") != "fully_mapped":
        return {
            "status": "UNKNOWN",
            "reason": "snapshot does not fully map the requested interval",
            "mapping_status": actual.get("status"),
        }
    observed = {
        key: actual.get(key) for key in ("readable", "writable", "executable")
    }
    if any(value is None for value in observed.values()):
        return {
            "status": "UNKNOWN",
            "reason": "permission evidence is incomplete",
            "observed": observed,
        }
    mismatches = [
        key for key in ("readable", "writable", "executable")
        if observed[key] != intended[key]
    ]
    source_status = actual.get("evidence_status")
    fact_status = (
        source_status if source_status in {"CONFIRMED", "LIKELY", "DESIGN"} else "UNKNOWN"
    )
    return {
        "status": fact_status if not mismatches else "UNKNOWN",
        "match": not mismatches,
        "mismatches": mismatches,
        "observed": observed,
    }


def _audit_interval(
    snapshot: Optional[Snapshot],
    name: str,
    base: int,
    length: int,
    intended: Dict[str, Any],
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "name": name,
        "virtual_base": base,
        "length": length,
        "virtual_end": checked_add(base, length, f"{name} ELF interval"),
        "intended_permissions": intended,
        "mapping_fact": None,
        "permission_comparison": _compare_permissions(intended, None),
    }
    if snapshot is not None:
        mapping = analyze_range(snapshot, base, length)
        item["mapping_fact"] = mapping
        item["permission_comparison"] = _compare_permissions(intended, mapping)
    return item


def loader_contract_bridge(checks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Separate snapshot mapping facts from Loader Entry Contract authority."""
    facts: List[Dict[str, Any]] = []
    for check in checks:
        mapping = check.get("mapping_fact")
        if mapping and mapping.get("status") == "fully_mapped":
            source_status = mapping.get("evidence_status")
            if source_status in {"CONFIRMED", "LIKELY", "DESIGN"}:
                fact_status = source_status
            else:
                fact_status = "UNKNOWN"
            reason = (
                "whole interval mapped by supplied snapshot bytes; "
                "synthetic bytes remain DESIGN evidence"
            )
        elif mapping:
            fact_status = "UNKNOWN"
            reason = "supplied snapshot did not prove a complete interval"
        else:
            fact_status = "BLOCKED"
            reason = "no snapshot mapping evidence was supplied"
        facts.append(
            {
                "name": check["name"],
                "status": fact_status,
                "reason": reason,
                "mapping_fact": mapping,
            }
        )
    return {
        "mapping_facts": facts,
        "loader_authority": {
            "descriptor_trusted": False,
            "ownership_proven": False,
            "payload_deposit_proven": False,
            "collision_audit_complete": False,
            "control_transfer_proven": False,
            "reason": "mapping proof is not ownership, trust, collision, or control-transfer proof",
        },
        "loader_entry_contract_fields": {
            "kernel_executable_mapping_proven": False,
            "kernel_readable_mapping_proven": False,
            "kernel_writable_mapping_proven": False,
            "entry_pc_proven": False,
            "initial_sp_proven": False,
        },
    }


def analyze_elf(
    elf_path: str | Path, snapshot: Optional[Snapshot] = None
) -> Dict[str, Any]:
    elf = ElfImage(elf_path)
    checks: List[Dict[str, Any]] = []
    for section in elf.sections:
        if not (section["flags"] & 0x2) or section["size"] == 0:
            continue
        checks.append(
            _audit_interval(
                snapshot,
                f"section:{section['name']}",
                section["address"],
                section["size"],
                _intended_section_permissions(section),
            )
        )
    symbols = elf.symbol_report(REQUIRED_SYMBOLS)
    bottom = elf.symbols.get("__stack_bottom")
    top = elf.symbols.get("__stack_top")
    if bottom and top and top["value"] > bottom["value"]:
        checks.append(
            _audit_interval(
                snapshot,
                "symbol:stack",
                bottom["value"],
                top["value"] - bottom["value"],
                {
                    "readable": True,
                    "writable": True,
                    "executable": False,
                    "basis": "DreyzeOS linker stack contract; hardware mapping remains separate evidence",
                },
            )
        )
    vectors = elf.symbols.get("_exception_vectors_base")
    if vectors:
        checks.append(
            _audit_interval(
                snapshot,
                "symbol:exception_vectors",
                vectors["value"],
                0x800,
                {
                    "readable": True,
                    "writable": False,
                    "executable": True,
                    "basis": "AArch64 vector span is 2048 bytes; hardware mapping remains separate evidence",
                },
            )
        )
    return {
        "status": "DESIGN",
        "evidence_status": (
            snapshot.evidence_status if snapshot else "UNKNOWN"
        ),
        "evidence_class": "SYNTHETIC" if snapshot and snapshot.source.get("kind") == "synthetic" else "CAPTURED_OR_UNKNOWN",
        "elf": elf.header,
        "path": str(Path(elf_path)),
        "required_symbols": symbols,
        "checks": checks,
        "program_headers": elf.program_headers,
        "loader_contract_bridge": loader_contract_bridge(checks),
        "limitations": [
            "ELF section/program-header permissions are intended image metadata, not hardware page-table proof",
            "a complete mapping does not prove ownership, descriptor trust, or control transfer",
        ],
    }


def _search_ranges(
    snapshot: Snapshot, explicit: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    ranges = list(snapshot.virtual_search_ranges)
    if explicit is not None:
        ranges.append(explicit)
    return ranges


def find_pa_mappings(
    snapshot: Snapshot,
    physical_base: int,
    length: int,
    search_ranges: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    target_base = parse_uint(physical_base, "physical base")
    target_length = parse_uint(length, "physical length")
    if target_length == 0:
        raise SnapshotError("INVALID_RANGE", "physical length must be non-zero")
    target_end = checked_add(target_base, target_length, "physical query")
    ranges = list(snapshot.virtual_search_ranges if search_ranges is None else search_ranges)
    matches: List[Dict[str, Any]] = []
    for query in ranges:
        report = analyze_range(
            snapshot,
            query["base"],
            query["length"],
            query.get("ttbr", "auto"),
        )
        for segment in report.get("segments", []):
            segment_end = checked_add(segment["physical_base"], segment["length"], "mapped physical interval")
            overlap_base = max(target_base, segment["physical_base"])
            overlap_end = min(target_end, segment_end)
            if overlap_base < overlap_end:
                va = segment["virtual_base"] + (
                    overlap_base - segment["physical_base"]
                )
                matches.append(
                    {
                        "virtual_base": va,
                        "physical_base": overlap_base,
                        "length": overlap_end - overlap_base,
                        "attributes": segment["attributes"],
                        "translation_level": segment["translation_level"],
                        "descriptor_type": segment["descriptor_type"],
                        "source_search_range": query,
                    }
                )
    return matches


def analyze_mmio_query(
    snapshot: Optional[Snapshot],
    name: str,
    search_range: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    target = MMIO_TARGETS.get(name)
    if target is None:
        raise SnapshotError("INVALID_VALUE", f"unknown MMIO target {name}")
    result: Dict[str, Any] = {
        "target": name,
        "physical_device_address": {
            "status": "CONFIRMED",
            "base": target["physical_base"],
            "size": target["size"],
            "source": target["source"],
            "basis": "static Watch4,2 DeviceTree evidence; physical only",
        },
        "translation": {
            "status": "UNKNOWN",
            "matches": [],
            "reason": "no translation snapshot/search range supplied",
        },
        "access_authority": {
            "status": "UNKNOWN",
            "value": "NOT_PROVEN",
            "reason": "a VA-to-PA mapping is not a DreyzeOS MMIO authorization",
        },
    }
    if snapshot is None:
        return result
    ranges = _search_ranges(snapshot, search_range)
    if not ranges:
        result["translation"]["reason"] = (
            "snapshot has no supplied virtual search range; absence of a match is not proof of unmapped"
        )
        return result
    matches = find_pa_mappings(
        snapshot, target["physical_base"], target["size"], ranges
    )
    translation_status = (
        snapshot.evidence_status
        if matches and snapshot.evidence_status in {"CONFIRMED", "LIKELY", "DESIGN"}
        else "UNKNOWN"
    )
    result["translation"] = {
        "status": translation_status,
        "evidence_class": "SYNTHETIC" if snapshot.source.get("kind") == "synthetic" else "CAPTURED_OR_UNKNOWN",
        "matches": matches,
        "reason": (
            "physical range matched supplied snapshot translations"
            if matches
            else "no match in the supplied VA search ranges; search is not exhaustive"
        ),
    }
    return result


def analyze_framebuffer(snapshot: Optional[Snapshot]) -> Dict[str, Any]:
    if snapshot is None or snapshot.framebuffer is None:
        return {
            "status": "BLOCKED",
            "mapping": "UNKNOWN",
            "reason": "static /vram is zero-filled and no runtime framebuffer range was supplied",
            "access_authority": "NOT_PROVEN",
        }
    fb = snapshot.framebuffer
    ranges = _search_ranges(snapshot)
    matches = (
        find_pa_mappings(snapshot, fb["physical_base"], fb["size"], ranges)
        if ranges
        else []
    )
    mapping_status = (
        snapshot.evidence_status
        if matches and snapshot.evidence_status in {"CONFIRMED", "LIKELY", "DESIGN"}
        else "UNKNOWN"
    )
    return {
        "status": "DESIGN",
        "physical_range": fb,
        "mapping": {
            "status": mapping_status,
            "evidence_class": "SYNTHETIC" if snapshot.source.get("kind") == "synthetic" else "CAPTURED_OR_UNKNOWN",
            "matches": matches,
            "reason": (
                "mapping matched supplied snapshot search ranges"
                if matches
                else "no exhaustive VA search range was supplied"
            ),
        },
        "collision_audit": {
            "status": "UNKNOWN",
            "reason": "an optional mapping query does not prove collision audit completeness",
        },
        "access_authority": "NOT_PROVEN",
    }


def snapshot_summary(snapshot: Snapshot) -> Dict[str, Any]:
    return {
        "status": "DESIGN",
        "evidence_status": snapshot.evidence_status,
        "source": snapshot.source,
        "registers": snapshot.registers,
        "physical_memory_regions": [
            {
                "physical_base": region.physical_base,
                "declared_length": region.declared_length,
                "bytes_supplied": len(region.data),
                "memory_bytes_present": region.memory_bytes_present,
                "memory_range_complete": region.memory_range_complete,
                "label": region.label,
            }
            for region in snapshot.regions
        ],
        "protected_regions": snapshot.protected_regions,
        "virtual_search_ranges": snapshot.virtual_search_ranges,
        "framebuffer": snapshot.framebuffer,
        "safety": {
            "hardware_access": False,
            "loader_authority": "NOT_PROVEN",
            "partial_dump_is_complete_ram": False,
        },
    }


def _json_dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Offline AArch64 translation-table evidence analyzer. "
            "Reads only local JSON manifests and memory blobs."
        )
    )
    parser.add_argument("--snapshot", help="JSON snapshot manifest")
    parser.add_argument("--image", help="DreyzeOS ELF to audit against the snapshot")
    parser.add_argument("--va", type=lambda value: parse_uint(value, "virtual address"))
    parser.add_argument("--length", type=lambda value: parse_uint(value, "length"))
    parser.add_argument(
        "--ttbr", choices=("auto", "ttbr0", "ttbr1"), default="auto"
    )
    parser.add_argument(
        "--walk",
        action="store_true",
        help="return one translation result instead of range analysis",
    )
    parser.add_argument("--decode-tcr", help="decode a numeric TCR_EL1 value")
    parser.add_argument("--decode-mair", help="decode MAIR_EL1 (use with --attr-index)")
    parser.add_argument("--attr-index", type=int, default=0)
    parser.add_argument(
        "--query-mmio",
        choices=tuple(MMIO_TARGETS.keys()),
        help="query a static physical MMIO target against supplied translations",
    )
    parser.add_argument(
        "--query-framebuffer",
        action="store_true",
        help="query the optional manifest framebuffer range",
    )
    parser.add_argument(
        "--search-base",
        type=lambda value: parse_uint(value, "search base"),
        help="one additional VA search range base for MMIO queries",
    )
    parser.add_argument(
        "--search-length",
        type=lambda value: parse_uint(value, "search length"),
        help="one additional VA search range length for MMIO queries",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="retained for explicit machine-readable invocation; output is always JSON",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        if args.decode_tcr is not None:
            output = decode_tcr(parse_uint(args.decode_tcr, "TCR_EL1"))
        elif args.decode_mair is not None:
            output = decode_mair(
                parse_uint(args.decode_mair, "MAIR_EL1"), args.attr_index
            )
        else:
            snapshot = Snapshot.load(args.snapshot) if args.snapshot else None
            if args.image:
                output = analyze_elf(args.image, snapshot)
            elif args.query_framebuffer:
                output = analyze_framebuffer(snapshot)
            elif args.query_mmio:
                explicit_range = None
                if (args.search_base is None) != (args.search_length is None):
                    parser.error("--search-base and --search-length must be paired")
                if args.search_base is not None:
                    explicit_range = {
                        "base": args.search_base,
                        "length": args.search_length,
                        "address_space": "virtual",
                        "ttbr": args.ttbr,
                        "name": "command-line search range",
                    }
                output = analyze_mmio_query(snapshot, args.query_mmio, explicit_range)
            elif args.va is not None:
                if snapshot is None:
                    parser.error("--va requires --snapshot")
                if args.length is None:
                    parser.error("--va requires --length")
                output = (
                    walk_va(snapshot, args.va, args.ttbr)
                    if args.walk
                    else analyze_range(snapshot, args.va, args.length, args.ttbr)
                )
            elif snapshot is not None:
                output = snapshot_summary(snapshot)
            else:
                parser.print_help()
                return 0
        print(_json_dump(output))
        return 0
    except SnapshotError as exc:
        print(_json_dump(exc.as_dict()), file=sys.stderr)
        return 2
    except OSError as exc:
        print(_json_dump(_error_result("IO_ERROR", str(exc))), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

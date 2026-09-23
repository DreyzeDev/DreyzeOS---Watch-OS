#!/usr/bin/env python3
"""Reproducibility and non-operational checks for the host-only reference."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_stage0_reference.py"
SOURCE_DIR = ROOT / "research" / "t8006_evidence" / "stage0_reference"


def run(command: list[str], *, cwd: Path = ROOT) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return completed.stdout


class Stage0ReferenceTests(unittest.TestCase):
    def test_reproducible_build_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stage0-reference-a-") as first:
            with tempfile.TemporaryDirectory(prefix="stage0-reference-b-") as second:
                run([sys.executable, str(BUILDER), "--output-dir", first])
                run([sys.executable, str(BUILDER), "--output-dir", second])
                first_dir = Path(first)
                second_dir = Path(second)
                first_manifest = json.loads(
                    (first_dir / "stage0_reference_manifest.json").read_text()
                )
                second_manifest = json.loads(
                    (second_dir / "stage0_reference_manifest.json").read_text()
                )
                first_elf = first_dir / "stage0_reference.elf"
                second_elf = second_dir / "stage0_reference.elf"

                self.assertEqual(first_elf.read_bytes(), second_elf.read_bytes())
                self.assertEqual(
                    hashlib.sha256(first_elf.read_bytes()).hexdigest(),
                    first_manifest["artifact_sha256"],
                )
                self.assertEqual(
                    first_manifest["artifact_sha256"],
                    second_manifest["artifact_sha256"],
                )
                self.assertEqual(first_manifest["artifact_size"], first_elf.stat().st_size)
                self.assertRegex(first_manifest["source_commit"], r"^[0-9a-f]{40}$")
                self.assertEqual(first_manifest["source_inputs"], second_manifest["source_inputs"])
                self.assertEqual(
                    first_manifest["reproducible_build_commands"],
                    second_manifest["reproducible_build_commands"],
                )
                self.assertEqual(
                    first_manifest["sidecar_sha256"],
                    second_manifest["sidecar_sha256"],
                )
                for image_name, image_path in (
                    ("elf", ROOT / "build" / "DreyzeOS.elf"),
                    ("flat_binary", ROOT / "build" / "DreyzeOS.bin"),
                ):
                    image_record = first_manifest["dreyzeos_image_reference"][image_name]
                    image_bytes = image_path.read_bytes()
                    self.assertEqual(
                        image_record["sha256"],
                        hashlib.sha256(image_bytes).hexdigest(),
                    )
                    self.assertEqual(image_record["size"], len(image_bytes))
                self.assertIn(
                    "local byte identity only",
                    first_manifest["dreyzeos_image_reference"]["sha256_semantics"],
                )
                self.assertEqual(first_manifest["handoff_abi_version"], 1)
                self.assertFalse(first_manifest["target_addresses_assigned"])
                self.assertFalse(first_manifest["target_executable"])
                self.assertFalse(first_manifest["transfer_implementation_present"])
                self.assertIsNone(first_manifest["target_entry_symbol"])
                self.assertIsNone(first_manifest["required_alignment"])
                self.assertIn("X86-64", first_manifest["host_machine"].upper())
                self.assertTrue(
                    all(
                        "C:\\" not in flag and "/home/" not in flag
                        for flag in first_manifest["reproducible_build_flags"]
                    )
                )
                self.assertTrue((first_dir / "stage0_reference.map").is_file())
                self.assertTrue((first_dir / "stage0_reference.readelf.txt").is_file())
                self.assertTrue((first_dir / "stage0_reference.nm.txt").is_file())
                self.assertTrue((first_dir / "stage0_reference.objdump.txt").is_file())

                # It is a host fixture that rejects absent facts without I/O.
                result = subprocess.run(
                    [str(first_elf)],
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, b"")

    def test_c_gate_statuses_and_v1_layout(self) -> None:
        compiler = shlex.split(os.environ.get("HOST_CC", "cc"))
        self.assertTrue(compiler)
        with tempfile.TemporaryDirectory(prefix="stage0-reference-contract-") as temp:
            executable = Path(temp) / "stage0_reference_contract_test"
            run(
                [
                    *compiler,
                    "-std=c11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-DSTAGE0_HOST_REFERENCE=1",
                    "-I",
                    str(ROOT / "include"),
                    "-I",
                    str(SOURCE_DIR),
                    str(SOURCE_DIR / "stage0_reference.c"),
                    str(SOURCE_DIR / "stage0_reference_contract_test.c"),
                    "-o",
                    str(executable),
                ]
            )
            subprocess.run([str(executable)], cwd=ROOT, check=True)

    def test_static_review_no_target_or_forbidden_symbols(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stage0-reference-audit-") as temp:
            output = Path(temp)
            run([sys.executable, str(BUILDER), "--output-dir", temp])
            elf = output / "stage0_reference.elf"
            nm = shutil.which("nm") or "nm"
            readelf = shutil.which("readelf") or "readelf"
            objdump = shutil.which("objdump") or "objdump"
            symbols = run([nm, "-a", str(elf)])
            undefined = run([nm, "-u", str(elf)])
            header = run([readelf, "-h", str(elf)])
            evaluator = run(
                [objdump, "-d", "--disassemble=stage0_reference_evaluate", str(elf)]
            )
            self.assertIn("X86-64", header.upper())
            self.assertNotIn("AArch64", header)

            forbidden_symbols = re.compile(
                r"(?:^|[^A-Za-z0-9_])(?:open|open64|fopen|fwrite|pwrite|pwrite64|"
                r"write|writev|ftruncate|unlink|rename|fsync|sync|ioctl)(?:$|[^A-Za-z0-9_])",
                re.IGNORECASE,
            )
            self.assertIsNone(forbidden_symbols.search(undefined))
            forbidden_device_symbols = re.compile(
                r"mmio|uart|aic|framebuffer|writel|writeq|write32|write64|"
                r"transfer_to|branch_to_payload",
                re.IGNORECASE,
            )
            self.assertIsNone(forbidden_device_symbols.search(symbols))
            self.assertIsNone(re.search(r"\b(?:call|jmp)\w*\s+\*", evaluator))

            source = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (
                    SOURCE_DIR / "stage0_reference.h",
                    SOURCE_DIR / "stage0_reference.c",
                    SOURCE_DIR / "main.c",
                )
            )
            forbidden_addresses = (
                "0x100000000",
                "0x800000000",
                "0x2e500000",
                "0x2d180000",
                "0x2d188000",
                "0x18000000",
                "0x18400000",
                "0x18490000",
            )
            for address in forbidden_addresses:
                self.assertNotIn(address.lower(), source.lower())

            objcopy = shutil.which("objcopy") or "objcopy"
            text_path = output / "text.bin"
            run(
                [
                    objcopy,
                    "--dump-section",
                    f".text={text_path}",
                    str(elf),
                ]
            )
            text_section = text_path.read_bytes()
            for address in (
                0x100000000,
                0x800000000,
                0x2E500000,
                0x2D180000,
                0x2D188000,
                0x18000000,
                0x18400000,
                0x18490000,
            ):
                self.assertFalse(
                    address.to_bytes(8, "little") in text_section,
                    f"target address literal found in executable/read-only section: {address:#x}",
                )

            self.assertIn("stage0_reference_evaluate", symbols)
            self.assertNotIn("stage0_transfer", symbols)

            production_elf = ROOT / "build" / "DreyzeOS.elf"
            self.assertTrue(production_elf.is_file())
            cross_nm = shutil.which("aarch64-linux-gnu-nm")
            self.assertIsNotNone(cross_nm)
            production_symbols = run([cross_nm, "-a", str(production_elf)])
            self.assertNotRegex(
                production_symbols,
                r"stage0_reference|STAGE0_HOST_REFERENCE|stage0_transfer",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

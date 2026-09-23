#!/usr/bin/env python3
"""Build a deterministic host-only Stage-0 contract reference artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "research" / "t8006_evidence" / "stage0_reference"
TEMPLATE = ROOT / "research" / "t8006_evidence" / "stage0_reference_manifest.template.json"
SOURCE_INPUTS = (
    "research/t8006_evidence/stage0_reference/stage0_reference.h",
    "research/t8006_evidence/stage0_reference/stage0_reference.c",
    "research/t8006_evidence/stage0_reference/main.c",
    "research/t8006_evidence/stage0_reference/stage0_reference_contract_test.c",
    "research/t8006_evidence/stage0_reference_manifest.template.json",
    "Makefile",
    "tools/build_stage0_reference.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_output(command: list[str], *, cwd: Path = ROOT) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return completed.stdout


def source_clean_at_head(paths: tuple[str, ...]) -> bool:
    try:
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", *paths],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", *paths],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            ["git", "diff", "--cached", "--quiet", "HEAD", "--", *paths],
            cwd=ROOT,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def build(
    output_dir: Path,
    cc_text: str,
    dreyzeos_elf: Path,
    dreyzeos_bin: Path,
) -> dict[str, Any]:
    compiler = shlex.split(cc_text)
    if not compiler or shutil.which(compiler[0]) is None:
        raise RuntimeError(f"host C compiler not found: {cc_text}")
    if not dreyzeos_elf.is_file() or not dreyzeos_bin.is_file():
        raise RuntimeError(
            "build DreyzeOS.elf and DreyzeOS.bin before the Stage-0 reference"
        )

    target_triple = command_output([*compiler, "-dumpmachine"]).strip()
    if re.search(r"(^|[-_])(aarch64|arm64|armv[0-9]*|arm)([-_]|$)", target_triple.lower()):
        raise RuntimeError("refusing to build the host reference with an ARM compiler")

    output_dir.mkdir(parents=True, exist_ok=True)
    elf_path = output_dir / "stage0_reference.elf"
    map_path = output_dir / "stage0_reference.map"
    report_path = output_dir / "stage0_reference.readelf.txt"
    symbols_path = output_dir / "stage0_reference.nm.txt"
    disassembly_path = output_dir / "stage0_reference.objdump.txt"
    source_paths = (
        SOURCE_DIR / "stage0_reference.c",
        SOURCE_DIR / "main.c",
    )
    object_paths = (
        output_dir / "stage0_reference.o",
        output_dir / "main.o",
    )

    deterministic_flags = [
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fno-ident",
        "-fno-pie",
        "-fno-asynchronous-unwind-tables",
        "-fno-unwind-tables",
        f"-ffile-prefix-map={ROOT}=.",
        "-DSTAGE0_HOST_REFERENCE=1",
        "-I",
        str(ROOT / "include"),
        "-I",
        str(SOURCE_DIR),
    ]
    compile_commands = []
    for source_path, object_path in zip(source_paths, object_paths):
        command = [
            *compiler,
            *deterministic_flags,
            "-c",
            str(source_path),
            "-o",
            str(object_path),
        ]
        subprocess.run(command, cwd=ROOT, check=True)
        compile_commands.append(command)

    link_flags = [
        "-no-pie",
        "-Wl,--build-id=none",
        "-Wl,--no-undefined",
        "-Wl,-z,noexecstack",
        f"-Wl,-Map,{map_path}",
        *(str(object_path) for object_path in object_paths),
        "-o", str(elf_path),
    ]
    link_command = [*compiler, *link_flags]
    subprocess.run(link_command, cwd=ROOT, check=True)

    def normalize_output(text: str) -> str:
        return text.replace(str(output_dir), "<output>").replace(
            str(ROOT), "<repo>"
        )

    map_path.write_text(
        normalize_output(map_path.read_text(encoding="utf-8")), encoding="utf-8"
    )

    readelf = shutil.which("readelf")
    nm = shutil.which("nm")
    objdump = shutil.which("objdump")
    if not readelf or not nm or not objdump:
        raise RuntimeError("host readelf, nm, and objdump are required")
    elf_report = "\n".join(
        (
            command_output([readelf, "-h", str(elf_path)]),
            command_output([readelf, "-l", str(elf_path)]),
            command_output([readelf, "-S", str(elf_path)]),
        )
    )
    report_path.write_text(normalize_output(elf_report), encoding="utf-8")
    symbols_path.write_text(
        normalize_output(command_output([nm, "-a", str(elf_path)])),
        encoding="utf-8",
    )
    disassembly_path.write_text(
        normalize_output(command_output([objdump, "-d", str(elf_path)])),
        encoding="utf-8",
    )

    machine_match = re.search(r"^\s*Machine:\s*(.+)$", elf_report, re.MULTILINE)
    entry_match = re.search(
        r"^\s*Entry point address:\s*(\S+)$", elf_report, re.MULTILINE
    )
    if not machine_match or not entry_match:
        raise RuntimeError("could not parse host ELF machine/entry metadata")

    manifest = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    commit = command_output(["git", "rev-parse", "HEAD"]).strip()
    manifest.update(
        {
            "artifact_path": elf_path.name,
            "artifact_sha256": sha256(elf_path),
            "artifact_size": elf_path.stat().st_size,
            "source_commit": commit,
            "source_inputs": {name: sha256(ROOT / name) for name in SOURCE_INPUTS},
            "source_inputs_clean_at_build": source_clean_at_head(SOURCE_INPUTS),
            "host_machine": machine_match.group(1).strip(),
            "host_elf_entry_address": entry_match.group(1),
            "host_compiler": target_triple,
            "host_compiler_version": command_output([*compiler, "--version"]).splitlines()[0],
            "reproducible_build_flags": [
                argument.replace(str(ROOT), "<repo>")
                for argument in deterministic_flags
            ],
            "reproducible_build_commands": [
                [
                    argument.replace(str(output_dir), "<output>").replace(
                        str(ROOT), "<repo>"
                    )
                    for argument in command
                ]
                for command in (*compile_commands, link_command)
            ],
            "dreyzeos_image_reference": {
                "elf": {
                    "path": str(dreyzeos_elf.relative_to(ROOT)),
                    "sha256": sha256(dreyzeos_elf),
                    "size": dreyzeos_elf.stat().st_size,
                },
                "flat_binary": {
                    "path": str(dreyzeos_bin.relative_to(ROOT)),
                    "sha256": sha256(dreyzeos_bin),
                    "size": dreyzeos_bin.stat().st_size,
                },
                "sha256_semantics": "local byte identity only; not target residency or authenticity",
            },
            "sidecar_sha256": {
                "linker_map": sha256(map_path),
                "readelf_report": sha256(report_path),
                "symbol_report": sha256(symbols_path),
                "disassembly_report": sha256(disassembly_path),
            },
            "target_addresses_assigned": False,
            "target_executable": False,
            "transfer_implementation_present": False,
        }
    )
    manifest_path = output_dir / "stage0_reference_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "build" / "stage0_reference",
    )
    parser.add_argument("--cc", default=os.environ.get("HOST_CC", "cc"))
    parser.add_argument(
        "--dreyzeos-elf", type=Path, default=ROOT / "build" / "DreyzeOS.elf"
    )
    parser.add_argument(
        "--dreyzeos-bin", type=Path, default=ROOT / "build" / "DreyzeOS.bin"
    )
    args = parser.parse_args()

    try:
        manifest = build(
            args.output_dir.resolve(),
            args.cc,
            args.dreyzeos_elf.resolve(),
            args.dreyzeos_bin.resolve(),
        )
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"stage0 reference build failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

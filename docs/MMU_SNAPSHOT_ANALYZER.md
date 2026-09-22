# Offline AArch64 MMU / Translation Evidence Analyzer — Phase 4 Step 2.10

**Target context**: Watch4,2 / N131bAP / Apple S4 T8006 / watchOS 10.6.1
(21U580)

**Implementation**: `tools/mmu_snapshot_analyzer.py`

**Evidence status**: DESIGN / HOST ONLY

## Purpose and safety boundary

This tool answers translation-table research questions against a future local
snapshot. It accepts a JSON manifest and local physical-memory blobs, then
performs bounded arithmetic and pure offline descriptor decoding.

It does not:

- access a real Watch, `/dev/mem`, `ptrace`, USB, DFU, Peepo, or usbliter8;
- execute exploit code, inject a payload, write RAM/flash/NAND/NOR, or jump to
  a target address;
- read a raw pointer merely because it is non-zero;
- open DreyzeOS MMIO or framebuffer gates;
- convert a static physical DeviceTree address into a virtual pointer.

The repository's current hardware state remains:

- static `/memory` = `base=0`, `size=0` (**CONFIRMED** artifact fact);
- runtime DRAM base/size = **UNKNOWN / BLOCKED**;
- static `/vram` is zero-filled; runtime framebuffer = **UNKNOWN / BLOCKED**;
- DreyzeOS fixed VMA `0x100000000` = **DESIGN placeholder**, not a load proof;
- `LOADER CONTRACT = BLOCKED`;
- `FIRST HARDWARE EXECUTION = NOT READY`.

## Invocation

```sh
python3 tools/mmu_snapshot_analyzer.py --help
python3 tools/mmu_snapshot_analyzer.py \
  --snapshot tests/fixtures/mmu/valid_4k_ttbr0.json \
  --va 0x40123456 --length 1 --walk
python3 tools/mmu_snapshot_analyzer.py --image build/DreyzeOS.elf
python3 tools/mmu_snapshot_analyzer.py \
  --snapshot tests/fixtures/mmu/valid_4k_ttbr0.json \
  --query-mmio uart0 --search-base 0x40123000 --search-length 0x2000
```

Output is JSON and includes explicit status/error fields. Supplying `--image`
without `--snapshot` is useful for inspecting symbols and intended ELF
intervals, but the mapping comparison is **BLOCKED**.

## TCR_EL1 decoding

The decoder reports raw `TCR_EL1` and:

- `T0SZ` / `T1SZ` and resulting VA widths;
- `TG0` / `TG1` and 4 KiB, 16 KiB, or 64 KiB granules;
- `SH0` / `SH1`;
- `ORGN0` / `ORGN1`;
- `IRGN0` / `IRGN1`;
- `EPD0` / `EPD1`;
- `IPS` and the resulting physical-address width;
- derived level count, first-level index width, and block/page sizes.

Reserved granule encodings, unsupported VA widths, invalid IPS values, and
inconsistent geometry return explicit `UNSUPPORTED_*` statuses. No granule is
hardcoded.

## MAIR_EL1 decoding

For each leaf descriptor the report retains:

- `AttrIndx`;
- the raw selected MAIR byte;
- a conservative category: `Device`, `Normal`, or
  `Unknown/implementation-specific`;
- the raw MAIR value and shareability.

The category is not a cache-coherency or access-authority grant. Raw encoding
remains the strongest reportable fact.

## Page-table walk

`walk_va()` selects TTBR0 or TTBR1 from the decoded canonical VA regions and
uses the selected TCR regime. It supports:

- table descriptors;
- block descriptors at non-final levels;
- page descriptors at the final level;
- the three supported granules;
- 32/36/40/42/44/48/52-bit IPS encodings where geometry is supported.

Each result reports input VA, selected TTBR, level/path, descriptor physical
address, raw descriptor, descriptor type, output PA, mapping size, AP, PXN,
UXN, AF, contiguous hint, shareability, AttrIndx, MAIR interpretation, and
whether the bytes came from a complete or partial supplied range.

The walker rejects or reports:

- non-canonical VA;
- UINT64 interval wrap;
- PA-width violations;
- unsupported TCR geometry;
- missing/truncated table bytes;
- invalid/reserved descriptor types;
- table pages outside the supplied dump;
- translation disabled by EPD;
- explicit TTBR selection mismatch.

A `MAPPED` result is a mapping fact from the supplied bytes. It is never
permission to perform hardware access.

## Range analysis

`analyze_range()` walks every mapping boundary, not just the first page. It
returns:

- `fully_mapped`, `partially_mapped`, `unmapped`, or `error`;
- every mapped VA/PA interval;
- whole-range readable/writable/executable values;
- permission and MAIR/attribute changes;
- page/block transitions;
- physical contiguity;
- the first failure location.

Adjacent intervals are not overlaps; a one-byte intersection is an overlap.
Zero-length intervals, wrapping ranges, and non-advancing mappings fail closed.

## DreyzeOS ELF audit

`analyze_elf()` parses the current ELF64/AArch64 image without pyelftools and
reports:

`_start`, `__kernel_start`, `__kernel_end`, `__bss_start`, `__bss_end`,
`__stack_bottom`, `__stack_top`, `_exception_vectors_base`.

It compares ELF intended section permissions with actual snapshot mappings for
allocated sections, the linker stack interval, and the 2048-byte exception
vector span. ELF program/section flags are image intent only; they do not
prove page-table permissions.

The current fixed non-PIC image remains linked at `0x100000000`. Without a
target snapshot, complete executable/readable/writable coverage at that VMA
is **UNKNOWN / BLOCKED**. A synthetic PASS is explicitly synthetic and does
not change hardware readiness.

## Loader Entry Contract bridge

The analyzer exposes mapping facts for a future bridge, but keeps authority
separate:

| Report item | Analyzer may report | Analyzer never auto-promotes |
|---|---|---|
| kernel text/entry mapping | mapping fact from snapshot | `entry_pc_proven` |
| writable BSS/stack mapping | mapping fact from snapshot | ownership or safe stack handoff |
| descriptor VA mapping | readable mapping fact | descriptor trust |
| PA/VA translation | translation fact | payload deposit/ownership |
| framebuffer/MMIO translation | physical match | DreyzeOS gate authorization |
| collision inputs | supplied ranges | collision audit complete |
| any mapping | evidence from supplied bytes | control-flow transfer |

The bridge intentionally leaves `descriptor_trusted`,
`ownership_proven`, `payload_deposit_proven`, `collision_audit_complete`,
`entry_pc_proven`, and `control_transfer_proven` false. This mirrors
`tests/loader_entry_contract.[ch]`; Loader Handoff ABI V1 remains exactly 128
bytes and unchanged.

## MMIO and framebuffer modes

The optional MMIO query knows only static physical target facts:

- UART0 `0x2E500000 / 0x4000`;
- AIC `0x2D180000 / 0x8000`;
- AIC timebase `0x2D188000 / 0x1000`;
- display `0x18000000 / 0x2F0000`;
- MIPI `0x18400000 / 0x90000` and `0x18490000 / 0x10000`.

Those physical ranges are **CONFIRMED** from the static Watch4,2 DeviceTree.
A reverse query is only against explicitly supplied VA search ranges. A match
inherits the manifest evidence status: **DESIGN** for synthetic fixtures and
**CONFIRMED** only when the supplied capture itself warrants that status;
access authority remains **NOT_PROVEN**.

Framebuffer analysis requires a future manifest framebuffer range and
provenance. With the current static `/vram` artifact, the result is
**UNKNOWN / BLOCKED**.

## Synthetic evidence and tests

The test suite contains repository-owned no-Apple-byte fixtures for 4 KiB
TTBR0 and 16 KiB TTBR1. Host-generated tests cover:

- 4 KiB, 16 KiB, and 64 KiB pages;
- TTBR0/TTBR1 selection, blocks, page descriptors, AP/PXN/UXN/AF;
- Device/Normal/unknown MAIR categories;
- missing/truncated tables, invalid descriptors, PA width, canonicality,
  overflow, unsupported geometry;
- range permission/attribute changes, partial mappings, physical continuity;
- ELF symbol/permission reporting;
- MMIO/framebuffer query boundaries and loader-authority separation.

Run:

```sh
make clean
make
make check
make tests
python3 tests/test_mmu_snapshot_analyzer.py
```

## Known limitations and next evidence

The analyzer cannot reconstruct bytes that were not captured, prove a live
device state from static firmware, infer ownership, or choose a safe DreyzeOS
load address. It also does not implement a loader, a stage-0, a hardware MMU
transition, or an exploit path.

The next evidence required is still a target-specific, reproducible loader/shim
snapshot that proves the complete normalized entry environment: payload
placement and ownership, entry VA/PC, EL1, SP/DAIF, translation and cache
policy, executable/readable/writable mappings, descriptor readability, bounded
boot_args/DeviceTree, collision exclusion, and control transfer.

Until that evidence exists:

`LOADER CONTRACT = BLOCKED`

`FIRST HARDWARE EXECUTION = NOT READY`

## Step 2.11 verifier integration

The unified host verifier imports this analyzer rather than maintaining a
second page-table walker. It preserves snapshot provenance, compares proven
TCR/TTBR/MAIR facts with the bundle CPU state, audits the fixed DreyzeOS ELF,
and leaves ownership and access authority separate from translation facts.
See [HANDOFF_EVIDENCE_VERIFIER.md](HANDOFF_EVIDENCE_VERIFIER.md).

No current Watch4,2 artifact contains a live translation-table snapshot. The
static `/memory` result remains `base=0,size=0`; analyzer or synthetic results
do not change hardware readiness.

## Step 2.12 evidence-gap integration

Step 2.12 does not add another page-table walker. The unified gap tool
[`tools/t8006_evidence_gap.py`](../tools/t8006_evidence_gap.py) consumes the
Step 2.11 verifier graph and the target requirement inventory. It distinguishes
`DESIGN` offline fixtures from target-proven `CONFIRMED` evidence and reports
the exact next evidence group for each unresolved requirement.

The required data-only capture schema is
[T8006_EVIDENCE_CAPTURE_SPEC.md](T8006_EVIDENCE_CAPTURE_SPEC.md). A complete
synthetic graph may demonstrate that the pipeline is ready to consume data,
but it cannot prove a live Watch state, ownership, access authority, or a safe
handoff.

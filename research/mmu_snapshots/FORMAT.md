# Offline MMU Snapshot Format — v1

## Scope

`dreyzeos.mmu_snapshot.v1` is a host-only research format for an
AArch64 translation-table snapshot. It is not a loader ABI, not a hardware
authorization token, and not a promise that a physical address is readable.

A snapshot consists of one JSON manifest and zero or more local binary memory
blobs. The analyzer never opens `/dev/mem`, uses `ptrace`, talks to USB, or
accesses a Watch. A capture may contain copyrighted firmware or RAM bytes;
those bytes must remain outside the repository unless redistribution is
explicitly authorized.

The status vocabulary is:

- **CONFIRMED** — the supplied artifact directly supports the statement;
- **LIKELY** — strong but indirect evidence;
- **DESIGN** — a project or synthetic model;
- **UNKNOWN** — evidence is insufficient;
- **BLOCKED** — the next safe step cannot proceed without the missing evidence.

“Synthetic” is an evidence class, not a hardware status. Synthetic fixtures
remain **DESIGN**.

## Manifest shape

The root object has these fields:

| Field | Required | Meaning |
|---|:---:|---|
| `schema` | yes | Must be `dreyzeos.mmu_snapshot.v1` |
| `architecture` | yes | Must be `aarch64` |
| `target` | yes | Descriptive target metadata; it does not prove target identity |
| `source` | yes | Capture/synthetic origin and description |
| `evidence_status` | yes | One of the five statuses above |
| `registers` | no | Register wrappers described below |
| `physical_memory_regions` | no | Supplied physical bytes, described below |
| `protected_regions` | no | Optional named collision inputs |
| `virtual_search_ranges` | no | Optional, explicitly bounded VA ranges for PA/MMIO searches |
| `framebuffer` | no | Optional future framebuffer range with provenance |

A target name, a register value, a non-zero address, or a descriptor bit never
grants access authority.

## Register provenance

Registers use an explicit wrapper:

```json
"tcr_el1": {
  "value": "0x0000000000000000",
  "value_present": true,
  "value_proven": false
}
```

`value_present` means that bytes for the value exist in the manifest.
`value_proven` means that the capture process has a separate evidence claim for
the register value. The analyzer can decode a present value for research, but
it does not silently upgrade `value_proven`.

Supported register names include:

- `current_el`, `sctlr_el1`, `tcr_el1`, `ttbr0_el1`, `ttbr1_el1`,
  `mair_el1`;
- optional `vbar_el1`, `daif`, `sp`, and `pc`.

Numeric values may be JSON integers or strings accepted by Python `int(value, 0)`.
All values are bounded to unsigned 64-bit.

## Physical memory regions

A real capture should reference local binary data:

```json
{
  "physical_base": "0x0000000000100000",
  "file": "capture-physical.bin",
  "file_offset": 0,
  "length": "0x4000",
  "memory_bytes_present": true,
  "memory_range_complete": false,
  "label": "captured table pages"
}
```

`file` is relative to the manifest directory and path traversal is rejected.
The analyzer reads exactly the declared length. `file_offset` and all interval
arithmetic are checked for overflow.

The two completeness flags have different meanings:

| Flag | Meaning |
|---|---|
| `memory_bytes_present` | Bytes for the declared region are supplied locally |
| `memory_range_complete` | The supplied bytes describe the complete declared physical range |

A partial dump can therefore decode a descriptor whose bytes are present while
still reporting `physical_dump_complete=false`. Missing table bytes return an
explicit `TABLE_BYTES_MISSING` or `PHYSICAL_DUMP_INCOMPLETE` result. A partial
dump is never treated as complete RAM.

For compact repository-owned synthetic fixtures only, the manifest may use
`data_words` instead of a blob:

```json
{
  "physical_base": "0x1000",
  "length": "0x4000",
  "memory_bytes_present": true,
  "memory_range_complete": true,
  "data_words": [
    {"offset": "0x0", "value": "0x2003"}
  ]
}
```

`data_words` is rejected for non-synthetic sources. It expands to zero-filled
local test bytes and contains no Apple firmware data.

## Optional ranges

`protected_regions` use `[base, base + length)` semantics and an explicit
`address_space` of `physical` or `virtual`. They are inputs to research
reports only. `virtual_search_ranges` are not an assertion that the entire VA
space was searched; they bound optional reverse PA-to-VA queries.

A framebuffer object requires `physical_base`, `size`, and `provenance`.
Omitting it is meaningful: for the current Watch4,2 static artifact the
`/vram` range is zero-filled, so runtime framebuffer mapping remains
UNKNOWN/BLOCKED.

## Interpretation rules

- `TCR_EL1` determines the granule and geometry; the analyzer does not assume
  4 KiB, 16 KiB, 64 KiB, TTBR0, TTBR1, 48-bit VA, or 48-bit PA.
- `MAIR_EL1` is decoded by `AttrIndx`; raw bytes are retained and ambiguous
  encodings stay unknown.
- A descriptor proves only a translation-table fact in the supplied bytes.
  It does not prove that the real device still has that state or that DreyzeOS
  may access the result.
- `SCTLR_EL1.M=1` and a TTBR value do not by themselves prove a usable mapping.
- Mapping proof is never ownership proof, descriptor trust, collision proof,
  payload-deposit proof, or control-transfer proof.

## Repository fixtures

`tests/fixtures/mmu/valid_4k_ttbr0.json` and
`tests/fixtures/mmu/valid_16k_ttbr1.json` are synthetic, compact manifests.
The host test suite also constructs 4 KiB, 16 KiB, and 64 KiB tables, blocks,
permission transitions, incomplete dumps, and malformed configurations in
memory. No captured Apple firmware or RAM is committed.

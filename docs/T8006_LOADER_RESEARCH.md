# T8006 Loader Evidence Audit — Phase 4 Step 2.9

**Target**: Apple Watch Series 4, 44mm GPS, `Watch4,2`, `N131bAP` / `n131bAP`
**SoC**: Apple S4 / `T8006`, AArch64
**Firmware artifact**: watchOS 10.6.1, `21U580`
**Scope**: static source, firmware, DeviceTree, kernelcache and host-side contract review only
**Safety boundary**: no Apple Watch, DFU, USB exploit, shellcode, payload delivery, hardware jump, MMIO access, flash write or recovery claim was attempted.

## Executive result

The Step 2.7 baseline is structurally sound, but it still does not contain a
T8006 loader contract. The exact static Watch4,2 ADT says:

```text
NODE: /memory
  reg: base=0x0000000000000000 size=0x0
```

The exact static `/chosen/memory-map` contains empty
`MemoryMapReserved-*` properties. Therefore `0x800000000` and
`0x40000000`/1 GiB remain historical research fallbacks or host fixtures;
they are **not** a confirmed runtime DRAM base or runtime DRAM size.

Public usbliter8 and Peepo artifacts provide useful, target-adjacent research
evidence, but neither is a DreyzeOS loader. The correct result of this audit is
to narrow the blockers, not to declare readiness:

* `LOADER CONTRACT = BLOCKED`
* `FIRST HARDWARE EXECUTION = NOT READY`

The public snapshots reviewed here are usbliter8
`479dbbf4ad80e4a454e0779d1b4d1ec5eb0d7bd5` and Peepo
`6d20d676f7c2d1620ba4764f7500baa906d67b64`.

## Evidence status vocabulary

* **CONFIRMED** — directly present in a reviewed source, binary, DeviceTree,
  specification or reproducible host result.
* **LIKELY** — strong related evidence, but not direct Watch4,2 target proof.
* **DESIGN** — DreyzeOS host-side contract or architecture proposal.
* **UNKNOWN** — the reviewed evidence does not determine the fact.
* **BLOCKED** — the missing fact prevents the next safe hardware step.

Related-device behavior, PongoOS, m1n1 and generic ARM64 conventions are not
promoted to T8006 **CONFIRMED** evidence.

## 1. Static Watch4,2 memory evidence

| Artifact | Exact static result | Status | What it does not prove |
|---|---|:---:|---|
| `research/ipsw/21U580/nodes_dump.txt`, `/memory` | `reg: base=0x0000000000000000 size=0x0` | **CONFIRMED** | No live DRAM base, size or usable range |
| Same file, `/chosen/memory-map` | `MemoryMapReserved-0` through `-15` are empty strings; no populated 16-byte ranges | **CONFIRMED** | No runtime reservation map or framebuffer collision map |
| `research/ipsw/21U580/DEVTREE_DUMP.md`, `/memory` | `reg = [0x0+0x0]` | **CONFIRMED** | Same static placeholder; not a runtime map |
| `DEVTREE_DUMP.md`, `/chosen/memory-map` | Each reserved property is a 16-byte all-zero value | **CONFIRMED** | A producer may replace it at boot, but this artifact does not show the live result |
| Static `/arm-io/uart0` | Physical `reg` base `0x2e500000`, size `0x4000`, IRQ `262` | **CONFIRMED** | Virtual mapping, clock state, baud divisor or safe handoff |
| Static `/arm-io/aic` | Physical `reg` base `0x2d180000`, size `0x8000`, AIC version `2` | **CONFIRMED** | Virtual mapping, live mask state or permission to touch MMIO |
| Static `/vram` | `reg = [0x0+0x0]` | **CONFIRMED** | Runtime framebuffer address, size, mapping or scanout state |

The artifact contains a static `/chosen/iBoot` node, but its timestamps and
`load-kernel-start` values do not provide a live memory-population record. The
reviewed kernelcache/XNU evidence confirms how a consumer reads
`boot_args.phys_base`, `boot_args.mem_size`, `boot_args.virt_base`, `video`,
and `devicetree_p`; it does not provide target-specific runtime values or a
producer trace for this static snapshot. Runtime population mechanism and
runtime values are separate questions and remain **UNKNOWN**.

Production boot-info fallback now leaves `dram_phys_base`, `dram_size`, and `dram_virt_base` at zero, with `virt_base_valid = false`. The historical
`0x800000000` / 1 GiB values remain only as explicitly labelled research or
host-test fixtures; they are not runtime DRAM evidence, do not open a mapping
gate, and never authorize a physical dereference.

## 2. T8006 loader evidence gap matrix

| PROPERTY | CURRENT VALUE | STATUS | EXACT EVIDENCE | SOURCE | WHAT IS STILL MISSING |
|---|---|:---:|---|---|---|
| Payload physical destination | No DreyzeOS destination found | **BLOCKED** | No reviewed loader/shim artifact names one | usbliter8/Peepo audit; `DreyzeOS.ld` | Target-specific transfer destination and ownership interval |
| Payload execution VA | Linker VMA `0x100000000` | **BLOCKED** | Linker symbol/entry are fixed at that placeholder | `DreyzeOS.ld`, ELF audit | Exact VA or a genuinely PIC initial stage |
| Payload maximum size | No DreyzeOS bound | **UNKNOWN** | usbliter8 transfer sizes are exploit layout sizes | usbliter8 `exploit.c` | Loader limit plus collision-free usable interval |
| Payload alignment | No DreyzeOS rule | **UNKNOWN** | No handoff source states alignment | reviewed artifacts | Transfer alignment and instruction/data alignment requirement |
| Entry PC | `_start` is image offset 0 at link VMA | **BLOCKED** | Static ELF only proves link-time entry | `boot/entry.S`, ELF | Actual target entry PC and mapping |
| Entry EL | DreyzeOS requires EL1 | **BLOCKED** | `entry.S` rejects privileged ELs other than EL1; public loader artifacts do not state DreyzeOS EL | `boot/entry.S`, usbliter8 | Evidence or normalization to EL1 before transfer |
| Initial SP | No V1 field; entry installs its own linked stack after entry | **BLOCKED** | No target handoff state proves the first safe stack | `boot/entry.S`, V1 ABI | Known/normalized stack and writable range |
| DAIF | Entry masks DAIF only after EL1 precondition | **BLOCKED** | No incoming DAIF evidence in public T8006 loader code | `boot/entry.S` | Safe initial DAIF and transition policy |
| SCTLR_EL1 | Not handed over by V1 | **UNKNOWN** | usbliter8 changes SCTLR for its own trampoline, not DreyzeOS | V1 ABI; usbliter8 `start.S` | Exact incoming value or loader normalization |
| TCR_EL1 | Not handed over by V1 | **BLOCKED** | No target-specific TCR handoff evidence | V1 ABI; static audits | Translation granule, address size and control policy |
| TTBR0_EL1 | Not handed over by V1 | **BLOCKED** | No DreyzeOS page-table root is identified | V1 ABI; usbliter8/Peepo audit | Root, ownership and readable/executable coverage |
| TTBR1_EL1 | Not handed over by V1 | **BLOCKED** | No DreyzeOS high-half mapping is identified | V1 ABI; static audits | Root and coverage, or explicit normalization |
| MAIR_EL1 | Not handed over by V1 | **UNKNOWN** | No DreyzeOS memory-attribute contract | V1 ABI | Attribute values for RAM/MMIO/code |
| I-cache state | Not represented | **UNKNOWN** | usbliter8 invalidates its own trampoline cache, not DreyzeOS state | usbliter8 `start.S` | Entry cache contract and required maintenance |
| D-cache state | Not represented | **UNKNOWN** | No DreyzeOS cache-coherency proof | V1 ABI | Entry state and clean/invalidate policy |
| Executable mapping | No target mapping proof | **BLOCKED** | Host PIC model accepts this only as an explicit input | `tests/pic_stage0_host.c` | Executable bytes for stage-0 and target entry |
| Readable mapping | Descriptor prefix is a design precondition | **BLOCKED** | No real descriptor address is known | V1 trust design | Loader proof for the complete 128-byte prefix |
| Writable RAM mapping | No safe destination interval | **BLOCKED** | Static `/memory` is zero; no runtime map | `nodes_dump.txt` | Writable RAM interval excluding all reservations |
| DeviceTree pointer | XNU `boot_args.devicetree_p` offset `0x60` is known | **UNKNOWN** | Consumer layout is confirmed; delivered pointer is not | XNU/kernelcache notes; V1 | Independently verified pointer and target address |
| DeviceTree size/bounds | XNU `devicetree_length` offset `0x68` is known | **UNKNOWN** | Static ADT has no live pointer/length pair | `boot_info.h`, static ADT | Complete bounded object and collision interval |
| `boot_args` pointer | XNU consumer uses x0 in its own ABI | **UNKNOWN** | This does not define DreyzeOS x0 | kernelcache notes; `entry.S` | Loader-owned x0 semantics and readable range |
| `boot_args` bounds | V1 design has a separate readable range | **DESIGN** | Range conversion/containment is host-tested | `loader_handoff.h`, `handoff_gate.c` | Real range supplied by a loader |
| Descriptor readable address | No real address | **BLOCKED** | `VERIFIED` is not a pointer proof | V1 trust design | Pre-existing readable mapping and address convention |
| Descriptor copy location | Host model copies to its own output object | **DESIGN** | Exactly 128 bytes are copied after caller proof | `pic_stage0_host.c` | Real stage-0 storage that is writable and safe |
| UART mapping | Static PA `0x2e500000`; VA unknown | **UNKNOWN** | Static DT `reg` only | `nodes_dump.txt`, `memory_map.h` | Verified VA mapping, clock/divisor and pin route |
| AIC mapping | Static PA `0x2d180000`; VA unknown | **UNKNOWN** | Static DT `reg` only | `nodes_dump.txt`, `aic.c` | Verified VA mapping and live interrupt policy |
| Framebuffer mapping | Static `/vram` is zero; `base_vaddr=0` in production | **BLOCKED** | No runtime FB range or VA map | `nodes_dump.txt`, `framebuffer.c` | Runtime range, mapping attributes and collision proof |
| Collision with reserved RAM | No populated reservation ranges | **BLOCKED** | `/chosen/memory-map` is empty/zero | static ADT | Runtime reservation list and interval calculation |
| Collision with loader | Loader region unknown | **BLOCKED** | No delivery layout | usbliter8/Peepo audit | Loader code/heap/stack ownership bounds |
| Collision with DeviceTree | Runtime DT location unknown | **BLOCKED** | Static DT file is not its live RAM copy | static ADT; V1 design | Live DT interval and payload overlap check |
| Collision with framebuffer | Runtime FB location unknown | **BLOCKED** | Static `/vram` is zero | static ADT; FB code | Live FB interval and payload overlap check |
| Transfer protocol | usbliter8 sends exploit-specific USB words/raw iBoot | **BLOCKED** | Public source has no DreyzeOS transfer protocol | usbliter8 `exploit.c`, `usbliter8ctl` | Target-specific bounded deposit protocol |
| Control-flow transfer primitive | usbliter8 returns to a fixed ROM task path | **BLOCKED** | No arbitrary DreyzeOS entry handoff | usbliter8 `start.S`, `handler.c` | Controlled branch/return to the verified DreyzeOS entry |

Every row marked **UNKNOWN** or **BLOCKED** has a concrete closure condition in
the last column. No row is closed by analogy to another Apple SoC.

## 3. Static usbliter8 audit — evidence, not exploit instructions

Repository: `https://github.com/JoshAtticus/usbliter8`
Revision: `479dbbf4ad80e4a454e0779d1b4d1ec5eb0d7bd5`
Target tree: `t8020_t8006_shellcode/`, `usb_req_handler/`, generated
`resources/`, `exploit.c`, and `usbliter8ctl`.

The T8006 shellcode build uses `clang -arch arm64` and Mach-O `-preload`; no
T8006 ELF linker script is present. `vmacho` extracts a binary which is then
stored in `resources/shellcode_t8006.h`. The generated lengths in this snapshot
are `shellcode_t8006_len = 816` and `handler_t8006_len = 116` bytes.

### Exact source findings

| Repository file / symbol | Target and hardcoded facts | What it really proves | What it does **not** prove |
|---|---|---|---|
| `t8020_t8006_shellcode/start.S:start` | T8006 offsets include `NEW_SP=0x1801D8BC0`, `TRAMP_BASE=0x1801C8000`, `ROM_TRAMP=0x100007A00`, handler offset `0x3C00`, return offset `0x3F00` | Exploit trampoline code changes SCTLR, switches to an exploit stack, copies code, writes a PTE, invalidates translation/instruction cache, and restores an iBoot/ROM task path | A DreyzeOS stack, PA, VA, descriptor, or entry EL |
| `start.S`, return trampoline | `ELR_EL1=0x10000C370` (`RETURN_TO_EL0_ADDR`), `SPSR_EL1=0x100`, then `eret`; local `br x22` enters the copied return trampoline | A fixed return/control path for the exploit's original task environment | A controllable branch to arbitrary DreyzeOS code; this return is EL0/ROM-task context, not the DreyzeOS EL1 contract |
| `targets/t8006/offsets.h` | `BOOT_TRAMP_PTEP=0x1801B4390`, `BOOT_TRAMP_PTE=0x1801C86E3`, `DMA_BUF_LO=0x801D9600`, `USB_DMA_DEST=0x230100B14`, `JUMP_STATE=0x1801C4030`, USB callback `0x1801C03F8` | Exact constants used by this exploit snapshot for a particular ROM/heap/USB state | Any constant is a safe DreyzeOS memory map or runtime DRAM fact |
| `exploit.c:SET32/SET64/SETMANY` | Encodes 32-bit words/64-bit values into an exploit-specific overwrite buffer; `SETMANY` copies source bytes in 4-byte steps | Source-side construction of the exploit data layout | A generic arbitrary-address writer; no independent destination/permission proof |
| `exploit.c:pb_data` | `PB_MAX_PAYLOAD=256`; builds USB packet data and CRC | The packet builder has a 256-byte local payload limit | A maximum DreyzeOS payload or RAM transfer bound |
| `exploit.c:crazy_transfer` | Sends one 32-bit pattern per acknowledged USB transfer; caller supplies a count | A bounded exploit transfer loop with 4-byte source granularity | A caller-controlled physical destination or a DreyzeOS loader protocol |
| `exploit.c:t8006_create_overwrite` | `ov_start=0x1801D960C`, `ov_size=0xB04`; writes fixed T8006 heap/task gadget addresses and values | A T8006-specific overwrite/ROP layout exists in source | Arbitrary RAM write coverage, safe payload placement, or DreyzeOS branch target |
| `exploit.c:t8006_create_shellcode` | `shc_base=0x1801C8000`, `shc_start=0x1801C83EC`, `shc_size=0x400`; copies generated shellcode/handler into exploit buffer | Where this exploit expects its own shellcode bytes | A maximum safe DreyzeOS image or an executable mapping for DreyzeOS |
| `exploit.c:t8020_t8006_exploit_run` | Transfers the `0xB04/4` overwrite words, then the `0x400/4` shellcode buffer words | The public source has two exploit-specific transfer phases | No DreyzeOS payload transfer, descriptor handoff, or hardware success for Watch4,2 |
| `usb_req_handler/handler.c:custom_handle_usb_req` | Function pointers target fixed iBoot symbols; custom boot writes `JUMP_AWAY` to `MAIN_TASK_STACK_LR`, using `PACIB` when enabled | A custom USB request can alter a fixed iBoot task return path in the exploit environment | An arbitrary caller-controlled DreyzeOS PC or an EL1 state contract |
| `usb_req_handler/targets/t8006/offsets.h` | `HANDLE_USB_REQ=0x10000E388`, `PLATFORM_DEMOTE=0x100007ED4`, `PLATFORM_SET_REMOTE_BOOT=0x100006B54`, `MAIN_TASK_STACK_LR=0x1801CDF58`, `JUMP_AWAY=0x100001B98` | Fixed target symbols used by the handler | Stable offsets for another build, a DreyzeOS entry, or a general branch primitive |
| `usbliter8ctl` | `TRANSFER_SIZE=0x800`; source reads raw iBoot and issues custom control requests | Public raw-iBoot control tooling exists | A DreyzeOS RAM destination or a safe payload execution sequence |

### Arbitrary RAM-write primitive status

**DreyzeOS payload RAM-write primitive: BLOCKED.** The public source confirms
that exploit-specific USB words are constructed and transferred, and that the
T8006 layout contains fixed heap/DMA destinations. It does not expose a
generic API with an arbitrary caller-selected address, a target-independent
range, a verified maximum length, or a DreyzeOS destination. The known facts
are:

* source granularity: 32-bit words in `crazy_transfer`;
* packet-builder payload cap: 256 bytes in `pb_data`;
* exploit phase sizes: `0xB04` bytes and `0x400` bytes;
* source buffers: aligned local `uint32_t` arrays;
* destination: exploit-specific ROM/heap/USB state derived from fixed layout
  constants, not a generic DreyzeOS PA;
* alignment, permissions and maximum safe DreyzeOS range: **UNKNOWN**.

### Control-flow primitive status

**DreyzeOS control-flow transfer primitive: BLOCKED.** The source has `br x22`
to a locally copied exploit trampoline and `eret` to the fixed
`RETURN_TO_EL0_ADDR`; the request handler writes a fixed `JUMP_AWAY` value into
a fixed iBoot task stack slot. Those facts confirm exploit control-flow
operations, but they do not prove a controllable branch to a DreyzeOS entry PC,
nor do they establish entry EL, SP, DAIF, translation or cache state.

No exploit runner or delivery sequence was executed or produced by this audit.

## 4. Static Peepo audit — kernel R/W is not a loader

Repository: `https://github.com/datalocaltmp/Peepo`
Revision: `6d20d676f7c2d1620ba4764f7500baa906d67b64`

The public README states the following compatibility claims:

| Public claim | Status as an artifact claim | DreyzeOS interpretation |
|---|:---:|---|
| Series 4 `Watch4,1`, T8006, watchOS 10.6.1 and 10.6.2, `xnu-10063.144.1` | **CONFIRMED** | Public on-device claim for `Watch4,1`, not this project's `Watch4,2` |
| Series 5 `Watch5,1`–`Watch5,4`, same builds | **LIKELY** / public untested claim | Related-device expectation, not target proof |
| SE 1st gen `Watch5,9`–`Watch5,12`, same builds | **LIKELY** / public untested claim | Related-device expectation, not target proof |
| `Watch4,2` | No compatibility claim in the reviewed matrix | **UNKNOWN/BLOCKED** for this project |

In `Peepo Watch App/darksword.m` the kernel primitive and static capabilities
are concrete:

* `physical_oob_read_mo`, `physical_oob_write_mo`, `early_kread` and
  `early_kwrite64` provide kernel-memory read/write operations in the exploit
  environment (**CONFIRMED capability of the source**);
* `OFF_PMAP_TTE=0x0`, `OFF_PMAP_TTEP=0x8`, and `ds_va_to_phys` read L1/L2/L3
  translation-table entries with 16 KiB pages (**CONFIRMED static page-table
  walking capability**);
* `gPhysmapOff = tte - ttep` is derived from live pmap objects
  (**CONFIRMED algorithm; unavailable here without the forbidden device run**);
* `DS_DRAM_LO=0x807000000` and `DS_DRAM_HI=0x840000000` are source
  constants/comments for a readable physmap window in that research path,
  not a DreyzeOS load map or `Watch4,2` proof;
* the kernelcache dump fallback `0x2800000` is a dump bound, not a payload
  bound.

The reviewed Peepo source has no DreyzeOS loader handoff, no boot_args parser,
no DeviceTree handoff contract, no payload entry routine, and no proof of
initial EL/SP/DAIF/SCTLR/TCR/TTBR/MAIR/cache state. Peepo could potentially
provide live memory-map or page-table evidence after a separately authorized
research run, but **Peepo != loader** and no such run was performed.

## 5. DreyzeOS ELF/linker audit

The current image remains deliberately fixed-address and non-PIC:

| Property | Result | Status |
|---|---|:---:|
| Link/load VMA | `_start = 0x100000000` | **CONFIRMED** link-time fact; **BLOCKED** as a hardware placement |
| Relocations | `readelf -r` reports none | **CONFIRMED** static-link fact |
| Position independence | C and assembly contain link-time page-relative/direct in-image references | **CONFIRMED** non-PIC audit |
| Meaning of zero relocations | Linker resolved references; it does not make the image movable | **CONFIRMED** interpretation |
| Arbitrary load | Not safe without matching VMA/mapping or a future PIC stage | **BLOCKED** |
| ELF permissions | R-E, R, RW program segments; no RWX segment | **CONFIRMED** build property |

The flat binary therefore cannot be treated as a freely movable payload. The
host-only PIC model is a design boundary, not an implementation claim.

## 6. PIC stage-0 host-only audit

`tests/pic_stage0_host.c` and `.h` remain **DESIGN / HOST ONLY**. Static review
and host tests confirm:

* no MMIO, device I/O, inline assembly, exploit logic, or hardware write;
* no function-pointer invocation, branch/return to a target address, payload
  execution, or assumption that runtime PC equals physical address;
* exactly the pre-proven 128-byte descriptor prefix is copied before validation;
* wire `payload_va` is converted through `loader_handoff_u64_to_uintptr()` before native arithmetic; nonrepresentable addresses are rejected;
* runtime PC/link-base signed delta checks reject zero values and `INT64` overflow;
* negative deltas are accepted only when representable;
* executable mapping overflow, payload size zero, offset-at-size,
  malformed descriptors, truncated prefixes, and each missing CPU-contract bit
  are rejected;
* target-entry overflow is defense-in-depth: a structurally valid V1 payload
  range already cannot wrap, and malformed max-address cases are rejected.

The model still does not relocate or jump. It only returns a host decision and
computed address.

## 7. ABI V1 structural audit

V1 is exactly 128 bytes, packed, and fixed-width:

| Offset | Field | Width |
|---:|---|---:|
| `0x00` | `magic` | `u64` |
| `0x08` | `version` | `u32` |
| `0x0C` | `size` | `u32` |
| `0x10` | `flags` | `u64` |
| `0x18` | `entry_el` | `u32` |
| `0x1C` | `reserved0` | `u32` |
| `0x20` | `payload_pa` | `u64` |
| `0x28` | `payload_va` | `u64` |
| `0x30` | `payload_size` | `u64` |
| `0x38` | `mmu_enabled` | `u32` |
| `0x3C` | `reserved1` | `u32` |
| `0x40` | `raw_x0` | `u64` |
| `0x48` | `raw_x1` | `u64` |
| `0x50` | `boot_args_range` | `24` |
| `0x68` | `device_tree_range` | `24` |

The structural validator rejects:

* bad magic/version, `size < 128`, unknown flags, non-zero reserved fields;
* `mmu_enabled > 1`;
* known entry EL other than EL1;
* known payload location with zero size/addresses or PA/VA overflow;
* UART/AIC validity without `MAPPING_STATE_KNOWN` and general MMIO validity;
* any mapping-valid bit without `MAPPING_STATE_KNOWN`.

These rules describe format consistency. They do not prove that a claimed
address is mapped, executable, writable, collision-free or physically safe.

## 8. Descriptor root of trust — DESIGN only

`DREYZE_HANDOFF_FLAG_VERIFIED` is an assertion, not a signature or pointer
proof. The safe design sequence is:

1. the loader already knows the descriptor address is readable;
2. the loader passes that pointer through a separately agreed ABI;
3. minimal stage-0 uses only the pre-proven readable mapping;
4. it copies exactly the fixed 128-byte prefix into its own memory;
5. structural V1 validation runs on the copy;
6. only then are the additional boot_args/DeviceTree ranges considered;
7. no nested pointer is trusted automatically; each complete object must fit
   inside an independently verified readable range.

This is a **DESIGN** sequence until a T8006 loader/shim implements and proves
the first step. V1 cannot bootstrap its own pointer trust.

## 9. ABI V2 decision

V1 deliberately does not carry initial SP, DAIF, `TTBR0_EL1`, `TTBR1_EL1`,
`TCR_EL1`, `MAIR_EL1`, cache state, executable ranges or writable-kernel-RAM
ranges.

| Approach | Benefit | Cost/risk | Decision |
|---|---|---|---|
| ABI V2 carries raw CPU registers and mapping ranges | More observable state in one object | Larger ABI, raw values still are not proof, and stale/invalid ranges can create false authority | **DESIGN**, not selected |
| Loader normalizes CPU state to a DreyzeOS contract | Minimal descriptor; stage-0 receives a known EL1/SP/DAIF/MMU/cache/mapping policy | Requires a real loader/shim that proves and performs normalization | **DESIGN**, preferred |

**ABI V2 NEEDED NOW: NO.** Keep V1 stable. If future evidence shows that the
loader cannot normalize the state, append a versioned V2 proposal rather than
silently changing V1; candidate fields would still need independent validity
and mapping proofs.

## 9A. Step 2.9 internal Loader Entry Contract

The host-only implementation in
[LOADER_ENTRY_CONTRACT.md](LOADER_ENTRY_CONTRACT.md) is the machine-checkable
DESIGN model for the missing loader preconditions. It does not modify V1 or
enter the production image.

The model separates facts from authority: a non-zero PA/VA, a V1 VERIFIED bit,
or an MMU-enabled bit does not authorize access. The validator requires a
trusted copied descriptor, normalized EL1/SP/DAIF/translation/cache policy,
explicit executable/readable/writable mapping ranges, RUNTIME_VERIFIED DRAM
provenance, independently bounded nested objects, and a complete collision
audit. It returns explicit rejection statuses and never dereferences a raw
pointer or performs a transfer.

The preferred architecture remains a tiny PIC stage-0 DESIGN followed by the
current fixed non-PIC kernel, but the PIC model is HOST ONLY. It cannot prove
target PA/VA equivalence, live mappings, CPU register state, loader ownership,
or a control-flow primitive. V1 therefore remains stable and the hardware
readiness state remains BLOCKED.

## 10. Production MMIO and framebuffer safety

* `mmio_mapping_set_verified_for_test`,
  `loader_handoff_set_verified_for_test`, and
  `framebuffer_set_mapping_verified_for_test` are under `HOST_TEST` only.
* The production ELF must not contain those setters or
  `framebuffer_set_virtual_base_for_test`; the production-ELF test checks symbols.
* In the production framebuffer path, `base_vaddr == 0`,
  `mapping_verified == false`, and `is_write_allowed == false` after init.
* `framebuffer_enable_writes(true)` remains rejected until a future trusted
  verifier supplies a concrete virtual mapping and deliberately opens a gate.
* Current `platform_init` leaves UART and AIC untouched while the MMIO gate is
  false. The AIC “all masked” operation exists only behind a future verified
  MMIO path; it is not a claim about the current hardware state.
* No IRQ enable, UART access, AIC access or framebuffer write was performed by
  this audit.

## 11. Entry machine-code contract audit

The required static order remains:

1. preserve x0/x1;
2. read `CurrentEL`, compare against EL1, and branch-loop on unsupported
   privileged EL;
3. mask DAIF;
4. set the linked stack pointer;
5. clear BSS without touching the later `.stack` section;
6. install `VBAR_EL1` and execute `ISB`;
7. set CPACR for FP/SIMD, with barriers;
8. call `kernel_main`.

`CurrentEL` is not a safe EL0 detector: the source documents its EL0
restriction, and the EL1 contract must be supplied by the loader. The
unsupported path is a branch loop and does not use WFI.

## 12. Exact next evidence required

The next useful artifact is a static, reproducible target-specific loader/shim
contract (source, disassembly, or equivalent binary analysis) that closes all
of the following in one consistent environment:

1. controlled payload deposit PA, alignment, transfer bound and ownership;
2. target execution VA/entry PC or a genuinely PIC initial stage;
3. entry EL1 and known/normalized SP and DAIF;
4. SCTLR/TCR/TTBR0/TTBR1/MAIR and I/D-cache transition policy;
5. executable/readable/writable mappings for stage-0, descriptor and payload;
6. descriptor prefix address, readability proof and copy location;
7. runtime boot_args/DeviceTree bounds;
8. complete collision intervals for loader, payload, DT, framebuffer and
   `/chosen/memory-map` reservations;
9. a control-flow transfer primitive that reaches the agreed DreyzeOS entry;
10. no persistent-write requirement.

Peepo could potentially help with live page-table/memory evidence in a future,
separately authorized research context. usbliter8 could be a candidate source
for target-specific delivery research. Neither closes these requirements now.

**LOADER CONTRACT = BLOCKED**
**FIRST HARDWARE EXECUTION = NOT READY**

## 13. Step 2.10 offline translation analyzer

Step 2.10 adds `tools/mmu_snapshot_analyzer.py`, a pure host/offline decoder
for a future captured AArch64 translation-table snapshot. Its JSON manifest
explicitly separates register `value_present` from `value_proven` and
physical `memory_bytes_present` from `memory_range_complete`. It supports
architectural 4 KiB, 16 KiB, and 64 KiB geometry when the decoded TCR is
supported; it never assumes identity mapping, a fixed TTBR, 48-bit VA, or a
48-bit PA.

The analyzer reports translation facts only:

| Query | Analyzer result | What it still does not prove |
|---|---|---|
| VA walk | selected TTBR, level, descriptor, PA, AP/PXN/UXN/AF, MAIR | live state or access authority |
| VA range | complete/partial mapping, permissions, attributes, PA continuity | ownership or collision completion |
| DreyzeOS ELF | intended-vs-snapshot mapping comparison | ELF flags as hardware permissions |
| MMIO reverse query | match in explicitly searched VA ranges | safe MMIO access or gate opening |
| framebuffer query | optional manifest range mapping | runtime /vram fact or write permission |
| loader bridge | mapping evidence candidates | descriptor trust, payload deposit, control transfer |

Repository fixtures are synthetic and contain no Apple firmware bytes. The
static Watch4,2 /memory artifact remains `base=0,size=0`; no runtime table
snapshot was added. Therefore this tool changes no readiness conclusion.

**LOADER CONTRACT = BLOCKED**

**FIRST HARDWARE EXECUTION = NOT READY**

## Step 2.11 — unified offline handoff evidence

The new evidence bundle and verifier are a deterministic HOST/OFFLINE bridge
between the V1 descriptor, normalized CPU contract, MMU snapshot, ELF, and
bounded object/range evidence. SHA-256 checks only local declaration equality;
target strings do not prove capture identity; a `VERIFIED` descriptor bit is
not a root of trust; and a VA-to-PA mapping is not ownership or access
authority. Conflicting proven values are BLOCKED rather than resolved by
preference.

No target-specific captured bundle has been added. Runtime DRAM, payload
placement/ownership, execution mapping, entry state, object bounds, complete
reservations, and control transfer remain UNKNOWN/BLOCKED.

## Step 2.12 — target-specific evidence requirements

The public/static review for this step found **no new target-specific runtime
artifact**. The next gap is therefore evidence collection, not another claim
about a loader path. The required facts and exact closure conditions are in
[research/t8006_evidence/REQUIRED_RUNTIME_EVIDENCE.md](../research/t8006_evidence/REQUIRED_RUNTIME_EVIDENCE.md)
and [requirements.json](../research/t8006_evidence/requirements.json). The
data-only bundle contract is in
[docs/T8006_EVIDENCE_CAPTURE_SPEC.md](T8006_EVIDENCE_CAPTURE_SPEC.md).

`tools/t8006_evidence_gap.py` is an offline checklist over the Step 2.11
evidence graph. It never promotes a synthetic mapping to target truth, and it
keeps target identity, ownership, descriptor trust, collision completeness,
and control transfer separate from page-table translation facts.

The static `/memory = base=0,size=0` artifact remains **CONFIRMED** as a static
file fact. Runtime DRAM, payload placement, live TTBR/TCR/MAIR state, and a
future control-transfer protocol remain **UNKNOWN/BLOCKED**.

# DreyzeOS

**Experimental Research Operating System for Apple Watch Series 4 (Apple S4 / T8006)**

> ⚠️ **RESEARCH PROJECT ONLY** — This is an exploratory OS development project.
> The goal is to understand Apple Watch hardware at the bare-metal level.
> No permanent modifications to device firmware are made.
> All execution is RAM-resident and reversible via reboot.

---

## Project Status

| Phase | Name | Status |
|-------|------|--------|
| PHASE 1 | Research + Toolchain + Repository | 🔄 IN PROGRESS |
| PHASE 2 | Minimal freestanding kernel | 🔄 IN PROGRESS |
| PHASE 3 | T8006 hardware research | 🔄 IN PROGRESS |
| PHASE 4 | Safe execution path | ⏳ PENDING |
| PHASE 5 | First controlled execution | ⏳ PENDING |
| PHASE 6 | Timer / logging / hw discovery | ⏳ PENDING |
| PHASE 7 | Display output | ⏳ PENDING |
| PHASE 8 | Digital Crown + Button | ⏳ PENDING |
| PHASE 9 | Touch | ⏳ PENDING |
| PHASE 10 | GUI | ⏳ PENDING |

---

## Target Hardware

- **Device**: Apple Watch Series 4 (44mm / 40mm, GPS / GPS+Cellular)
- **SoC**: Apple S4 (chip identifier: T8006)
- **Architecture**: ARM64_32 (ILP32 userspace, 64-bit kernel) — CONFIRMED
- **OS replaced**: None (watchOS remains intact; experiments run from RAM)

## Repository Structure

```
DreyzeOS/
├── README.md
├── LICENSE
├── Makefile               # Main build system
├── CMakeLists.txt         # CMake alternative
├── docs/
│   ├── ROADMAP.md         # Development phases
│   ├── HARDWARE.md        # T8006 hardware documentation
│   ├── BOOT.md            # Boot chain analysis
│   ├── RESEARCH.md        # Research notes and findings
│   └── SAFETY.md          # Safety analysis for device experiments
├── boot/
│   ├── entry.S            # AArch64 entry point, stack init, BSS clear
│   └── startup.c          # Early startup C code
├── kernel/
│   ├── kernel.c           # kernel_main()
│   ├── panic.c            # panic() handler
│   └── log.c              # Early logging subsystem
├── arch/
│   └── arm64/
│       ├── cpu.c          # CPU initialization
│       ├── cpu.h
│       ├── exceptions.S   # Exception vectors (AArch64)
│       ├── exceptions.c
│       ├── mmu.c          # MMU setup (minimal)
│       └── mmu.h
├── hal/
│   └── t8006/
│       ├── platform.c     # T8006 platform initialization
│       ├── platform.h
│       ├── memory_map.h   # T8006 memory map (UNKNOWN values marked)
│       └── device_tree.c  # Apple DeviceTree parser
├── drivers/
│   ├── uart/              # UART driver (stub)
│   ├── display/           # Display driver (stub)
│   ├── touch/             # Touch controller driver (stub)
│   ├── crown/             # Digital Crown driver (stub)
│   ├── button/            # Side button driver (stub)
│   └── timer/             # Timer driver (stub)
├── lib/
│   ├── string.c           # memcpy, memset, strlen, etc.
│   └── memory.c           # Memory allocator (minimal)
├── include/               # Global headers
├── tools/
│   ├── image_builder.py   # Build DreyzeOS IMG4/raw image
│   ├── inspect_binary.py  # Analyze built binary
│   └── device_tree_dump.py # Apple DeviceTree parser/dumper
└── tests/                 # Host-side unit tests
```

## Building

### Prerequisites
- WSL2 with Ubuntu
- `aarch64-linux-gnu-gcc` cross-compiler
- `llvm` / `clang` (for AArch64)
- `python3`

### Build
```bash
# In WSL2 / Ubuntu:
cd /mnt/c/Users/pc/Desktop/DreyzeOS
make

# Output: build/DreyzeOS.bin
```

## Safety

Read [docs/SAFETY.md](docs/SAFETY.md) before attempting any hardware experiment.

**Rule**: Any unknown operation is considered UNSAFE until proven otherwise.

## Research Sources

- [Peepo — Apple Watch kernel research](https://github.com/datalocaltmp/Peepo)
- [PongoOS — pongoOS environment](https://github.com/checkra1n/PongoOS)
- [XNU Source — Apple open source](https://github.com/apple-oss-distributions/xnu)
- [checkra1n](https://checkra.in/) — checkm8 bootrom exploit research
- [theapplewiki.com](https://www.theapplewiki.com/) — Apple hardware documentation

# DreyzeOS Makefile
# Target: Apple Watch Series 4 / Apple S4 (T8006) — AArch64
# Build environment: WSL2 Ubuntu / Linux

# ============================================================
# Toolchain — AArch64 cross-compiler
# ============================================================
CROSS   ?= aarch64-linux-gnu-
CC      := $(CROSS)gcc
AS      := $(CROSS)gcc
LD      := $(CROSS)ld
OBJCOPY := $(CROSS)objcopy
OBJDUMP := $(CROSS)objdump
READELF := $(CROSS)readelf
NM      := $(CROSS)nm
SIZE    := $(CROSS)size

# ============================================================
# Directories
# ============================================================
BUILDDIR := build

# ============================================================
# Framebuffer test pattern compile-time switch (default 0: disabled)
DREYZE_FB_TEST_PATTERN ?= 0

# Build Provenance (Git Commit SHA and canonical branch)
GIT_COMMIT ?= $(shell git rev-parse --short=8 HEAD 2>/dev/null || echo "UNKNOWN")
CANONICAL_BRANCH ?= master

# Compiler flags — freestanding AArch64 bare-metal (GCC)
CFLAGS := \
	-march=armv8-a \
	-ffreestanding \
	-fno-builtin \
	-fno-stack-protector \
	-fno-pie \
	-fno-pic \
	-nostdlib \
	-nostdinc \
	-Wall \
	-Wextra \
	-Wno-unused-parameter \
	-O2 \
	-g \
	-DDREYZE_FB_TEST_PATTERN=$(DREYZE_FB_TEST_PATTERN) \
	-DGIT_COMMIT_SHA=\"$(GIT_COMMIT)\" \
	-DDREYZEOS_CANONICAL_BRANCH=\"$(CANONICAL_BRANCH)\" \
	-I. \
	-Iinclude \
	-Ilib

# Assembler flags
ASFLAGS := \
	-march=armv8-a \
	-ffreestanding \
	-nostdlib \
	-g

# Linker flags
LDFLAGS := \
	-T DreyzeOS.ld \
	--no-undefined \
	-Map $(BUILDDIR)/DreyzeOS.map

# ============================================================
# Source files
# ============================================================
BOOT_SRCS := \
	boot/entry.S

KERNEL_SRCS := \
	kernel/kernel.c \
	kernel/panic.c \
	kernel/log.c \
	kernel/boot_stage.c \
	kernel/cpu_state.c

HAL_SRCS := \
	hal/t8006/platform.c \
	hal/t8006/device_tree.c \
	hal/t8006/uart.c \
	hal/t8006/aic.c \
	hal/t8006/framebuffer.c

LIB_SRCS := \
	lib/string.c \
	lib/memory.c

# All sources
C_SRCS := $(KERNEL_SRCS) $(HAL_SRCS) $(LIB_SRCS)
S_SRCS := $(BOOT_SRCS)

# Object files in build directory
C_OBJS := $(patsubst %.c, $(BUILDDIR)/%.o, $(C_SRCS))
S_OBJS := $(patsubst %.S, $(BUILDDIR)/%.o, $(S_SRCS))
ALL_OBJS := $(S_OBJS) $(C_OBJS)

# ============================================================
# Output targets
# ============================================================
ELF     := $(BUILDDIR)/DreyzeOS.elf
BIN     := $(BUILDDIR)/DreyzeOS.bin
DUMP    := $(BUILDDIR)/DreyzeOS.dump

# ============================================================
# Default target
# ============================================================
.PHONY: all clean info check tests help dump toolchain-check

all: toolchain-check $(BIN)
	@$(MAKE) --no-print-directory info

# ============================================================
# Check toolchain
# ============================================================
toolchain-check:
	@echo "[TOOLCHAIN] Checking AArch64 cross-compiler..."
	@which $(CC) > /dev/null 2>&1 || \
		(echo "ERROR: $(CC) not found. Install with:" && \
		 echo "  sudo apt-get install gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu" && \
		 exit 1)
	@echo "[TOOLCHAIN] $(CC) found: $$($(CC) --version | head -1)"

# ============================================================
# Link ELF
# ============================================================
$(ELF): $(ALL_OBJS) DreyzeOS.ld | $(BUILDDIR)
	@echo "[LD] $@"
	$(LD) $(LDFLAGS) -o $@ $(ALL_OBJS)

# ============================================================
# Extract raw binary
# ============================================================
$(BIN): $(ELF)
	@echo "[BIN] $@"
	$(OBJCOPY) -O binary $< $@
	@echo "[SIZE] Binary:"
	@ls -lh $@

# ============================================================
# Compile C files
# ============================================================
$(BUILDDIR)/%.o: %.c | $(BUILDDIR)
	@mkdir -p $(dir $@)
	@echo "[CC] $<"
	$(CC) $(CFLAGS) -c $< -o $@

# ============================================================
# Assemble .S files
# ============================================================
$(BUILDDIR)/%.o: %.S | $(BUILDDIR)
	@mkdir -p $(dir $@)
	@echo "[AS] $<"
	$(CC) $(ASFLAGS) -c $< -o $@

# ============================================================
# Create build directory
# ============================================================
$(BUILDDIR):
	mkdir -p $(BUILDDIR)

# ============================================================
# Post-build info
# ============================================================
info: $(ELF) $(BIN)
	@echo ""
	@echo "=========================================="
	@echo " DreyzeOS Build Info"
	@echo "=========================================="
	@echo ""
	@echo "--- Section sizes ---"
	@$(SIZE) $(ELF) 2>/dev/null || true
	@echo ""
	@echo "--- ELF sections ---"
	@$(READELF) -S $(ELF) 2>/dev/null | grep -E '^\s+\[' | head -30 || true
	@echo ""
	@echo "--- Entry point ---"
	@$(READELF) -h $(ELF) 2>/dev/null | grep "Entry point" || true
	@echo ""
	@echo "--- Key symbols ---"
	@$(NM) -n $(ELF) 2>/dev/null | grep -E '_start|kernel_main|panic|__kernel|__bss|__stack' || true
	@echo ""
	@echo "--- Binary ---"
	@ls -lh $(BIN) 2>/dev/null || true
	@echo "=========================================="

# ============================================================
# Disassembly
# ============================================================
dump: $(ELF)
	@echo "[DUMP] $(DUMP)"
	$(OBJDUMP) -d -S $(ELF) > $(DUMP)
	@echo "Written: $(DUMP)"
	@head -50 $(DUMP)

# ============================================================
# Binary validation
# ============================================================
check: $(ELF) $(BIN)
	@echo "[CHECK] Validating binary..."
	python3 tools/inspect_binary.py $(ELF) $(BIN)

# ============================================================
# Tests
# ============================================================
tests:
	@echo "[TEST] Host-side tests..."
	python3 tests/test_runner.py

# ============================================================
# Clean
# ============================================================
clean:
	@echo "[CLEAN] Removing $(BUILDDIR)/"
	rm -rf $(BUILDDIR)

# ============================================================
# Help
# ============================================================
help:
	@echo ""
	@echo "DreyzeOS Build System"
	@echo "Target: Apple Watch Series 4 / T8006 (AArch64)"
	@echo ""
	@echo "Targets:"
	@echo "  all      Build DreyzeOS.elf + DreyzeOS.bin (default)"
	@echo "  info     Print sections, entry point, symbols"
	@echo "  dump     Disassemble to $(DUMP)"
	@echo "  check    Validate binary with inspect_binary.py"
	@echo "  tests    Run host-side Python tests"
	@echo "  clean    Remove build/"
	@echo ""
	@echo "Toolchain: CROSS=$(CROSS)"
	@echo "  Compiler: $(CC)"
	@echo "  Linker:   $(LD)"
	@echo ""
	@echo "Install toolchain in WSL2 Ubuntu:"
	@echo "  sudo apt-get install gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu"
	@echo ""

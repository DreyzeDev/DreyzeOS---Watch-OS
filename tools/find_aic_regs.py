#!/usr/bin/env python3
"""
Search for AIC register access patterns in the kernelcache.
Focus: find loads/stores relative to the AIC base address register.
Strategy: 
  1. Find all AIC-related functions using string cross-refs
  2. Look for patterns where the AIC base (0x2d180000) appears in constants
  3. Find MOV/MOVK sequences that produce MMIO addresses
  4. Cross-reference Asahi Linux register layout
"""
import struct
import capstone
import re

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
md.detail = True

TEXT_EXEC_FILE = 0xb18000
TEXT_EXEC_VA = 0xfffffff007b1c000
TEXT_EXEC_END_FILE = 0x2948000

def foff_to_va(foff):
    return TEXT_EXEC_VA + (foff - TEXT_EXEC_FILE)

def va_to_foff(va):
    return TEXT_EXEC_FILE + (va - TEXT_EXEC_VA)

# AIC functions we know about:
# handleInterrupt: VA 0xfffffff0088cbb00 - but that is a subroutine range issue
# Let's find the actual start of handleInterrupt by searching backward from 0xfffffff0088cbb00
# for a function prologue

# Strategy: search for patterns of the form:
#   ldr w_reg, [x_aicbase, #offset]  or  str w_reg, [x_aicbase, #offset]
# where x_aicbase was loaded from the object's _aicBaseAddress field (ivar offset ~0x90-0xb8)

# More specifically, in AIC code we expect patterns like:
#   ldr x8, [x19, #0x??]   ; load _aicBaseAddress from ivar
#   ldr w9, [x8, #0x????]   ; read from AIC_EVENT or similar
# OR:
#   ldr x8, [x19, #0x??]
#   mov w9, #0
#   str w9, [x8, #0x????]   ; write to AIC register

# But since _aicBaseAddress ivar offset is unknown, let's take a different approach:
# Find ADRP+ADD that resolve to addresses in range 0x2d180000..0x2d200000

# Also look for patterns with AIC_EVENT = 0x2004 as an immediate in ARM64 instructions
# ARM64 LDR with immediate 0x2004 encodes as unsigned offset: 0x2004/4 = 0x801
# In ARM64 encoding: ldr w, [xN, #0x2004] → unsigned scaled offset

# Search for LDR with offset 0x2000, 0x2004, 0x202c in __TEXT_EXEC
print("Searching for AIC MMIO read patterns in __TEXT_EXEC...")
print("Looking for instructions with offsets: 0x2000, 0x2004, 0x202c, 0x4100, 0x4200")
print("="*70)

TARGET_OFFSETS = {
    0x2000: "AIC_WHOAMI?",
    0x2004: "AIC_EVENT?",
    0x2008: "AIC_TYPE?",
    0x202c: "AIC_IPI_ACK?",
    0x2024: "AIC_IPI_SEND?",
    0x4100: "AIC_SW_GEN_SET?",
    0x4180: "AIC_SW_GEN_CLR?",
    0x4200: "AIC_MASK_SET?",  
    0x4280: "AIC_MASK_CLR?",
    0x4300: "AIC_HW_STATE?",
    0x4400: "AIC_IRQ_CFG?",
    0x0000: "AIC_REV?",
    0x0004: "AIC_INFO?",
    0x0008: "AIC_WHOAMI2?",
}

# Build a lookup set of target offsets
target_set = set(TARGET_OFFSETS.keys())

# Read __TEXT_EXEC in chunks and find matching patterns
# AIC functions are around 0x18c5000..0x18cd000
start_foff = 0x18c4000
end_foff   = 0x18d0000
code = data[start_foff:end_foff]
base_va = foff_to_va(start_foff)

matches = []
for insn in md.disasm(code, base_va):
    op_str = insn.op_str
    mnem = insn.mnemonic
    
    # Look for loads/stores with interesting offsets
    # Pattern: ldr/str with [xN, #OFFSET]
    m = re.search(r'\[x\d+,\s*#(0x[0-9a-fA-F]+)\]', op_str)
    if m:
        offset = int(m.group(1), 16)
        if offset in target_set:
            matches.append((insn.address, mnem, op_str, offset))

print(f"\nMatches in 0x{start_foff:x}..0x{end_foff:x}:")
for va, mnem, op, offset in matches:
    name = TARGET_OFFSETS.get(offset, "???")
    print(f"  0x{va:x}: {mnem:8} {op}  ; {name}")

print(f"\nTotal matches: {len(matches)}")

# Also search broader range for AIC_EVENT 0x2004
print("\n\nBroader search for 0x2004 in __TEXT_EXEC...")
start2 = 0xb18000
end2   = 0x2948000
code2 = data[start2:end2]
base_va2 = foff_to_va(start2)
matches2 = []
for insn in md.disasm(code2, base_va2):
    m = re.search(r'\[x\d+,\s*#0x2004\]', insn.op_str)
    if m:
        matches2.append((insn.address, insn.mnemonic, insn.op_str))

print(f"Found {len(matches2)} instructions with offset 0x2004:")
for va, mnem, op in matches2[:30]:
    foff = va_to_foff(va)
    print(f"  0x{va:x} (file:0x{foff:x}): {mnem} {op}")

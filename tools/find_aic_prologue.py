#!/usr/bin/env python3
"""
Search kernelcache for AIC register access patterns.
Strategy: Search for MMIO register value constants that appear in the code
as immediate values after ADRP instructions or in MOV instructions.

Key insight: AIC MMIO reads use ldr w0, [x8, #offset] patterns.
Since the MMIO base is loaded from an ivar (not hardcoded in instructions),
we should look at what values are compared after reading AIC_EVENT.

XNU AIC v1 (A12/T8006 AIC2 hardware, but using "v1" software interface):
- AIC_EVENT = 0x2004: bits[23:16] = type, bits[15:0] = irq number
  - type 0 = FIQ (timer handled via ARM timer)
  - type 1 = external IRQ
  - type 4 = IPI
  
Confirm by finding the comparison values 0x10000 (type=1 shifted) or
#1 in ubfx / lsr sequences after what looks like reading AIC_EVENT.

Let's disassemble a bigger window of the handleInterrupt function.
"""
import struct
import capstone

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

TEXT_EXEC_FILE = 0xb18000
TEXT_EXEC_VA   = 0xfffffff007b1c000

def foff_to_va(foff):
    return TEXT_EXEC_VA + (foff - TEXT_EXEC_FILE)

def va_to_foff(va):
    return TEXT_EXEC_FILE + (va - TEXT_EXEC_VA)

# The handleInterrupt function
# From previous disasm, we see the tail at 0xfffffff0088cbb00
# Prologue must be further back.
# Let's look for a "sub sp, sp, #N" before 0xfffffff0088cb800

# From prior analysis, the handleInterrupt function is called by the vectorType-related code.
# Let's find it by looking for the string "unexpected vectorType" cross-ref
# and going to its enclosing function.

IACK_STR = b"unexpected vectorType: 0x%08x, IACK=0x%08x"
iack_foff = data.find(IACK_STR)
PRELINK_TEXT_FILE = 0x4000
PRELINK_TEXT_VA   = 0xfffffff007008000
iack_str_va = PRELINK_TEXT_VA + (iack_foff - PRELINK_TEXT_FILE)
iack_str_page = iack_str_va & ~0xfff
iack_str_off = iack_str_va & 0xfff

print(f"'unexpected vectorType' string: file=0x{iack_foff:x} VA=0x{iack_str_va:x}")
print(f"Page=0x{iack_str_page:x} offset=0x{iack_str_off:x}")

# Find ADRP to this page in AIC function region (broader search)
# Search from 0x18c0000 to 0x18e0000
search_start = 0x18c0000
search_end   = 0x18e0000
code = data[search_start:search_end]
base_va = foff_to_va(search_start)

print(f"\nSearching for ADRP to 0x{iack_str_page:x} in 0x{search_start:x}..0x{search_end:x}...")

refs = []
insns_list = list(md.disasm(code, base_va))
for idx, insn in enumerate(insns_list):
    if insn.mnemonic == 'adrp':
        import re
        m = re.search(r'#(0x[0-9a-fA-F]+)', insn.op_str)
        if m:
            page = int(m.group(1), 16)
            if page == iack_str_page:
                refs.append((idx, insn))

print(f"Found {len(refs)} ADRP refs to IACK string page")

for ref_idx, ref_insn in refs:
    print(f"\n--- ADRP at 0x{ref_insn.address:x} (file:0x{va_to_foff(ref_insn.address):x}) ---")
    # Print context around this ADRP
    start = max(0, ref_idx - 5)
    end   = min(len(insns_list), ref_idx + 5)
    for insn in insns_list[start:end]:
        marker = ">>>" if insn.address == ref_insn.address else "   "
        print(f"  {marker} 0x{insn.address:x}: {insn.mnemonic:10} {insn.op_str}")

# Now find the function that contains 0xfffffff0088cbbec (the BRK after the timer check)
# Disassemble from 0x18c8000 backwards to find SUB SP/STP prologue
print("\n\nSearching for handleInterrupt function prologue...")
# From the handleInterrupt disasm, the tail epilogue ends at 0xfffffff0088cbbe0 (retab)
# So function starts somewhere before that.
# Search backward in 3KB chunks
epilogue_foff = va_to_foff(0xfffffff0088cbbe0)

# Scan backward for prologue pattern: stp x29, x30, [sp, #-N]! 
# ARM64 prologue encoding
for offset in range(0, 3000, 4):
    foff = epilogue_foff - offset
    if foff < TEXT_EXEC_FILE:
        break
    # Read 4 bytes
    word = struct.unpack('<I', data[foff:foff+4])[0]
    # Pattern for: sub sp, sp, #imm  → 0xD10XXXXX (sub sp, sp, #N)
    # Pattern for: stp x29, x30, [sp, #-N]! → 0xA9BXXXX
    if (word & 0xFFC003FF) == 0xA9800000:  # stp (pre-indexed) with xN registers
        reg1 = (word >> 0) & 0x1F
        reg2 = (word >> 10) & 0x1F
        rn   = (word >> 5) & 0x1F
        if reg1 == 29 and reg2 == 30 and rn == 31:  # stp x29, x30, [sp, ...]
            va = foff_to_va(foff)
            print(f"  Possible prologue STP x29,x30 at file=0x{foff:x} VA=0x{va:x} (offset -{offset} from epilogue)")

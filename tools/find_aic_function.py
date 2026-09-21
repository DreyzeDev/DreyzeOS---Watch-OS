#!/usr/bin/env python3
"""
Find the actual start of AppleInterruptController::handleInterrupt() by looking
for function prologue before the known string reference.

The string "vectorType == kAICIackVecTypeTimer" is somewhere near 0x18c7b00.
Let's find the actual function entry.
"""
import struct
import capstone
import re

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

TEXT_EXEC_FILE = 0xb18000
TEXT_EXEC_VA   = 0xfffffff007b1c000

def foff_to_va(foff):
    return TEXT_EXEC_VA + (foff - TEXT_EXEC_FILE)

def va_to_foff(va):
    return TEXT_EXEC_FILE + (va - TEXT_EXEC_VA)

# Find all cross-references to AIC strings via ADRP + ADD patterns
# First find the string "vectorType == kAICIackVecTypeTimer" in __PRELINK_TEXT
# __PRELINK_TEXT: file 0x4000..0x6fc000, va 0xfffffff007008000
PRELINK_TEXT_FILE = 0x4000
PRELINK_TEXT_VA   = 0xfffffff007008000

# Search for the string
TIMER_STR = b"vectorType == kAICIackVecTypeTimer"
IACK_STR  = b"unexpected vectorType: 0x%08x, IACK=0x%08x"
START_STR = b"_aicVersion = %d _aicBaseAddress ="

timer_foff = data.find(TIMER_STR)
iack_foff  = data.find(IACK_STR)
start_foff = data.find(START_STR)

if timer_foff >= 0:
    timer_va = PRELINK_TEXT_VA + (timer_foff - PRELINK_TEXT_FILE)
    print(f"'vectorType==Timer' string: file=0x{timer_foff:x} VA=0x{timer_va:x}")

if iack_foff >= 0:
    iack_va = PRELINK_TEXT_VA + (iack_foff - PRELINK_TEXT_FILE)
    print(f"'unexpected vectorType/IACK' string: file=0x{iack_foff:x} VA=0x{iack_va:x}")

if start_foff >= 0:
    start_va_str = PRELINK_TEXT_VA + (start_foff - PRELINK_TEXT_FILE)
    print(f"'_aicVersion = %d' string: file=0x{start_foff:x} VA=0x{start_va_str:x}")

print()

# Now search __TEXT_EXEC for ADRP instructions that reference these string VAs
# ADRP loads the page: target_page = (pc & ~0xfff) + (imm21 << 12)
# For a string at VA 0xXXXX, the ADRP target is (VA & ~0xfff)

def find_adrp_to_va(code_start_foff, code_end_foff, target_va_page, hint=""):
    """Find ADRP instructions in code region that target the given page."""
    code = data[code_start_foff:code_end_foff]
    base_va = foff_to_va(code_start_foff)
    results = []
    for i, insn in enumerate(md.disasm(code, base_va)):
        if insn.mnemonic == 'adrp':
            # op_str like "x0, #0xfffffff0072b4000"
            m = re.search(r'#(0x[0-9a-fA-F]+)', insn.op_str)
            if m:
                page = int(m.group(1), 16)
                if page == target_va_page:
                    results.append(insn)
    return results

# target pages
timer_page = (PRELINK_TEXT_VA + (timer_foff - PRELINK_TEXT_FILE)) & ~0xfff
iack_page  = (PRELINK_TEXT_VA + (iack_foff - PRELINK_TEXT_FILE)) & ~0xfff

print(f"Timer string page: 0x{timer_page:x}")
print(f"IACK string page:  0x{iack_page:x}")
print()

# Search in AIC function region
AIC_REGION_START = 0x18c0000
AIC_REGION_END   = 0x18d8000

print(f"Searching ADRP to timer page in 0x{AIC_REGION_START:x}..0x{AIC_REGION_END:x}...")
timer_refs = find_adrp_to_va(AIC_REGION_START, AIC_REGION_END, timer_page)
for insn in timer_refs:
    print(f"  ADRP timer ref at VA=0x{insn.address:x} file=0x{va_to_foff(insn.address):x}")

print(f"Searching ADRP to IACK page in 0x{AIC_REGION_START:x}..0x{AIC_REGION_END:x}...")
iack_refs = find_adrp_to_va(AIC_REGION_START, AIC_REGION_END, iack_page)
for insn in iack_refs:
    print(f"  ADRP IACK ref at VA=0x{insn.address:x} file=0x{va_to_foff(insn.address):x}")

# Now disassemble the region around each reference to find function boundary
print()
print("Detailed disasm around timer string reference:")
if timer_refs:
    ref_va = timer_refs[0].address
    ref_foff = va_to_foff(ref_va)
    # Search backward for the prologue (STP x29, x30 or sub sp, sp, #N)
    # Look 800 bytes back
    window_start = ref_foff - 800
    window_code = data[window_start:ref_foff + 400]
    window_base_va = foff_to_va(window_start)
    
    insns = list(md.disasm(window_code, window_base_va))
    
    # Find prologue: look for "sub sp, sp, #N" near start
    prologue_idx = None
    for idx, insn in enumerate(insns):
        if insn.mnemonic == 'sub' and 'sp, sp,' in insn.op_str:
            # Check if near start
            prologue_idx = idx
    
    if prologue_idx is not None:
        start_print = max(0, prologue_idx - 2)
    else:
        start_print = 0
    
    print(f"\n  Function likely starts around idx {prologue_idx}")
    for insn in insns[start_print:]:
        marker = ">>>" if abs(insn.address - ref_va) < 8 else "   "
        print(f"  {marker} 0x{insn.address:x}: {insn.mnemonic:10} {insn.op_str}")

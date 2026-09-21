#!/usr/bin/env python3
"""
Find the ::start() method of AppleInterruptController that reads _aicVersion / _aicBaseAddress.
This contains references to register offsets we care about.
File 0x18c5f68 has the ADRP for the _aicVersion string.
Disassemble a range around it.
"""
import struct
import capstone

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

# VA of start() method reference to _aicVersion = %d _aicBaseAddress
# 0x18c5f68
start_file = 0x18c5f68 - 600
start_va = 0xfffffff007b1c000 + (0x18c5f68 - 0x18c5f68) + (0x18c5f68 - 0xb18000) - 600

# Recalculate: file off -> VA
# __TEXT_EXEC: vm=0xfffffff007b1c000, file=0xb18000
# VA = 0xfffffff007b1c000 + (fileoff - 0xb18000)
def foff_to_va(foff):
    return 0xfffffff007b1c000 + (foff - 0xb18000)

focus_foff = 0x18c5f68
focus_va = foff_to_va(focus_foff)
print(f"Focus VA: 0x{focus_va:x}")

# Disassemble 250 instructions before and after
off_start = focus_foff - 700
off_end = focus_foff + 1200
code = data[off_start:off_end]
start_va_calc = foff_to_va(off_start)

print(f"\nDisassembly of start() method (file: 0x{off_start:x}..0x{off_end:x}):")
print("="*70)
for i in md.disasm(code, start_va_calc):
    prefix = ">>> " if abs(i.address - focus_va) < 16 else "    "
    print(f"{prefix}0x{i.address:x}: {i.mnemonic:10} {i.op_str}")

#!/usr/bin/env python3
import capstone

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

TEXT_EXEC_FILE = 0xb18000
TEXT_EXEC_VA   = 0xfffffff007b1c000

def va_to_foff(va):
    return TEXT_EXEC_FILE + (va - TEXT_EXEC_VA)

# Look at 0xfffffff0088cb5e0 to 0xfffffff0088cb700 (around 0x4154 and 0x4200)
foff_start = va_to_foff(0xfffffff0088cb5c0)
foff_end = va_to_foff(0xfffffff0088cb700)
code = data[foff_start:foff_end]

print("=== Disassembly around 0x4154 and 0x4200 ===")
for insn in md.disasm(code, 0xfffffff0088cb5c0):
    print(f"0x{insn.address:x}: {insn.mnemonic:10} {insn.op_str}")

# Look at 0xfffffff0088caee0 to 0xfffffff0088caf50 (around 0x4000)
foff_start2 = va_to_foff(0xfffffff0088caee0)
foff_end2 = va_to_foff(0xfffffff0088caf50)
code2 = data[foff_start2:foff_end2]

print("\n=== Disassembly around 0x4000 ===")
for insn in md.disasm(code2, 0xfffffff0088caee0):
    print(f"0x{insn.address:x}: {insn.mnemonic:10} {insn.op_str}")

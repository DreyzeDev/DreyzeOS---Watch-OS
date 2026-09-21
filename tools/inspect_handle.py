#!/usr/bin/env python3
import capstone

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

TEXT_EXEC_FILE = 0xb18000
TEXT_EXEC_VA   = 0xfffffff007b1c000

def va_to_foff(va):
    return TEXT_EXEC_FILE + (va - TEXT_EXEC_VA)

# Let's inspect code from 0xfffffff0088cb800 to 0xfffffff0088cbb00
foff_start = va_to_foff(0xfffffff0088cb800)
foff_end = va_to_foff(0xfffffff0088cbbb0)
code = data[foff_start:foff_end]

for insn in md.disasm(code, 0xfffffff0088cb800):
    print(f"0x{insn.address:x}: {insn.mnemonic:10} {insn.op_str}")

#!/usr/bin/env python3
import capstone

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

TEXT_EXEC_FILE = 0xb18000
TEXT_EXEC_VA   = 0xfffffff007b1c000

def va_to_foff(va):
    return TEXT_EXEC_FILE + (va - TEXT_EXEC_VA)

pc = 0xfffffff007b28538
foff = va_to_foff(pc)
code = data[foff:foff+200]

print(f"Disassembly at entry point pc=0x{pc:x} (file off 0x{foff:x}):")
for insn in md.disasm(code, pc):
    print(f"  0x{insn.address:x}: {insn.mnemonic:10} {insn.op_str}")

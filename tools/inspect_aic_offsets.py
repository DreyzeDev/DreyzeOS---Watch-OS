#!/usr/bin/env python3
import capstone

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

TEXT_EXEC_FILE = 0xb18000
TEXT_EXEC_VA   = 0xfffffff007b1c000

def va_to_foff(va):
    return TEXT_EXEC_FILE + (va - TEXT_EXEC_VA)

# Let's search for references to offset 0x5c8 or vtable setup
# Or let's inspect all places where w1 is loaded with 0x2000, 0x2004, 0x4080, 0x4100, etc. in 0x18c4000..0x18d0000
foff_start = 0x18c4000
foff_end = 0x18d0000
code = data[foff_start:foff_end]
base_va = TEXT_EXEC_VA + (foff_start - TEXT_EXEC_FILE)

print("Register accesses in AIC driver:")
for insn in md.disasm(code, base_va):
    if insn.mnemonic == 'mov' and 'w1, #' in insn.op_str:
        print(f"0x{insn.address:x}: {insn.mnemonic:10} {insn.op_str}")
    elif insn.mnemonic == 'mov' and 'w8, #' in insn.op_str and ('0x4' in insn.op_str or '0x2' in insn.op_str or '0x8' in insn.op_str or '0x1' in insn.op_str):
        print(f"0x{insn.address:x}: {insn.mnemonic:10} {insn.op_str}")

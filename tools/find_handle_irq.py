#!/usr/bin/env python3
import struct
import capstone
import re

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

# File offset 0x2b043a is in __DATA_CONST segment:
# __DATA_CONST vm: 0xfffffff007700000..0xfffffff007b1c000, file: 0x6fc000..0xb18000
# Wait, offset 0x2b043a is in __PRELINK_TEXT (vm: 0xfffffff007008000..0xfffffff007700000, file: 0x4000..0x6fc000)
# VM address of 0x2b043a = 0xfffffff007008000 + (0x2b043a - 0x4000) = 0xfffffff0072b443a!

target_str_va = 0xfffffff007008000 + (0x2b043a - 0x4000)
print(f"String VA: 0x{target_str_va:x}")

# Now search __TEXT_EXEC (file: 0xb18000..0x2948000, vm: 0xfffffff007b1c000..0xfffffff00994c000)
# for ADRP x*, target_str_va page (page = target_str_va & ~0xfff)
target_page = target_str_va & ~0xfff
target_lo = target_str_va & 0xfff

print(f"Searching for references to page 0x{target_page:x} (lo: 0x{target_lo:x})...")

# In __TEXT_EXEC:
text_exec = data[0xb18000:0x2948000]
exec_va = 0xfffffff007b1c000

for off in range(0, len(text_exec) - 8, 4):
    instr = struct.unpack_from('<I', text_exec, off)[0]
    # Check if ADRP
    if (instr & 0x9f000000) == 0x90000000:
        # Decode ADRP
        rd = instr & 0x1f
        immlo = (instr >> 29) & 0x3
        immhi = (instr >> 5) & 0x7ffff
        imm = (immhi << 2) | immlo
        if imm & (1 << 20):
            imm -= (1 << 21)
        pc_page = (exec_va + off) & ~0xfff
        dest_page = pc_page + (imm << 12)
        if dest_page == target_page:
            # Check next instruction for add or ldr
            next_instr = struct.unpack_from('<I', text_exec, off + 4)[0]
            # add rd, rd, #target_lo?
            print(f"\nMatch at VA: 0x{exec_va + off:x} (file off: 0x{0xb18000 + off:x})")
            # Disassemble 50 instructions around this
            code_start = max(0, off - 60)
            code_end = min(len(text_exec), off + 140)
            for i in md.disasm(text_exec[code_start:code_end], exec_va + code_start):
                prefix = "==>" if i.address == (exec_va + off) else "   "
                print(f"{prefix} 0x{i.address:x}: {i.mnemonic:8} {i.op_str}")
            break

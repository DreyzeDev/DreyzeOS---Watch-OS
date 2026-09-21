#!/usr/bin/env python3
import struct
import capstone

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

# Strings at 0x2b043a and 0x2b0480
# 0xfffffff007008000 + (0x2b043a - 0x4000) = 0xfffffff0072b443a
# 0xfffffff007008000 + (0x2b0480 - 0x4000) = 0xfffffff0072b4480

text_exec = data[0xb18000:0x2948000]
exec_va = 0xfffffff007b1c000

print("Scanning for exact references to 0xfffffff0072b443a or 0xfffffff0072b4480...")

for off in range(0, len(text_exec) - 16, 4):
    instr = struct.unpack_from('<I', text_exec, off)[0]
    if (instr & 0x9f000000) == 0x90000000: # ADRP
        immlo = (instr >> 29) & 0x3
        immhi = (instr >> 5) & 0x7ffff
        imm = (immhi << 2) | immlo
        if imm & (1 << 20): imm -= (1 << 21)
        dest_page = ((exec_va + off) & ~0xfff) + (imm << 12)
        if dest_page == 0xfffffff0072b4000:
            next_instr = struct.unpack_from('<I', text_exec, off + 4)[0]
            # ADD X*, X*, #imm
            if (next_instr & 0xff800000) == 0x91000000:
                add_imm = (next_instr >> 10) & 0xfff
                if add_imm in [0x43a, 0x480, 0x481, 0x43b]:
                    va = exec_va + off
                    print(f"\nFOUND REFERENCE at VA: 0x{va:x} (offset: 0x{0xb18000+off:x}), add_imm=0x{add_imm:x}")
                    # Disassemble function starting 150 instructions before and 100 after
                    f_start = max(0, off - 400)
                    f_end = min(len(text_exec), off + 200)
                    dis = list(md.disasm(text_exec[f_start:f_end], exec_va + f_start))
                    for i in dis:
                        p = "==>" if i.address == va else "   "
                        print(f"{p} 0x{i.address:x}: {i.mnemonic:8} {i.op_str}")

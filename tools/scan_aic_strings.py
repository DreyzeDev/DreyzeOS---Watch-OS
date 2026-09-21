#!/usr/bin/env python3
import struct

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

text_exec = data[0xb18000:0x2948000]
exec_va = 0xfffffff007b1c000

print("Scanning for references to AIC strings in 0xfffffff0072b4000...")
for off in range(0, len(text_exec) - 8, 4):
    instr = struct.unpack_from('<I', text_exec, off)[0]
    if (instr & 0x9f000000) == 0x90000000:
        immlo = (instr >> 29) & 0x3
        immhi = (instr >> 5) & 0x7ffff
        imm = (immhi << 2) | immlo
        if imm & (1 << 20): imm -= (1 << 21)
        dest_page = ((exec_va + off) & ~0xfff) + (imm << 12)
        if dest_page == 0xfffffff0072b4000:
            next_instr = struct.unpack_from('<I', text_exec, off + 4)[0]
            if (next_instr & 0xff800000) == 0x91000000:
                add_imm = (next_instr >> 10) & 0xfff
                target = dest_page + add_imm
                f_off = (target - 0xfffffff007008000) + 0x4000
                if 0 <= f_off < len(data):
                    s = data[f_off:f_off+60].split(b'\x00')[0]
                    if any(k in s for k in [b'AppleInterrupt', b'kAIC', b'aic', b'Interrupt']):
                        print(f"VA 0x{exec_va+off:x} (file 0x{0xb18000+off:x}) -> 0x{target:x}: {s.decode('ascii', errors='replace')}")

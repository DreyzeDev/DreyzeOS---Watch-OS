#!/usr/bin/env python3
import struct
import capstone

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

# VA 0xfffffff0088cbb00 corresponds to:
# file off = 0xb18000 + (0xfffffff0088cbb00 - 0xfffffff007b1c000)
# 0xfffffff0088cbb00 - 0xfffffff007b1c000 = 0xdafb00
# file off = 0xb18000 + 0xdafb00 = 0x18c7b00

target_va = 0xfffffff0088cbb00
file_off = 0x18c7b00

print(f"Disassembling handleInterrupt around 0x{target_va:x} (file offset 0x{file_off:x})...")

code = data[file_off - 128 : file_off + 384]
start_va = target_va - 128

for i in md.disasm(code, start_va):
    print(f"  0x{i.address:x}: {i.mnemonic:10} {i.op_str}")

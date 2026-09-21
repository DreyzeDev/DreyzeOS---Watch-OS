#!/usr/bin/env python3
import capstone
import struct

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

TEXT_EXEC_FILE = 0xb18000
TEXT_EXEC_VA   = 0xfffffff007b1c000
PRELINK_TEXT_FILE = 0x4000
PRELINK_TEXT_VA   = 0xfffffff007008000

# String at file offset 0x94839
str_va = PRELINK_TEXT_VA + (0x94839 - PRELINK_TEXT_FILE)
str_page = str_va & ~0xfff
str_off = str_va & 0xfff

print(f"String /chosen/memory-map VA: 0x{str_va:x}, page: 0x{str_page:x}, off: 0x{str_off:x}")

# Search __TEXT_EXEC for ADRP to this page
code = data[TEXT_EXEC_FILE:TEXT_EXEC_FILE+0x100000] # first 1MB of code
for insn in md.disasm(code, TEXT_EXEC_VA):
    if insn.mnemonic == 'adrp' and f"#{hex(str_page)}" in insn.op_str:
        print(f"Found ADRP at 0x{insn.address:x}: {insn.mnemonic} {insn.op_str}")

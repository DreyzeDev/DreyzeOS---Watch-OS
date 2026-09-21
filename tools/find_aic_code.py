#!/usr/bin/env python3
"""
Find and disassemble AppleInterruptController methods in kernelcache.macho.
"""
import struct
import capstone
import re

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

# Find string "AppleInterruptController"
needle = b"_aicVersion = %d _aicBaseAddress"
pos = data.find(needle)
print(f"String '{needle.decode()}' at file offset 0x{pos:x}")

# Find references to this string in __TEXT_EXEC or __DATA
# The string address in VM can be calculated:
# String is in __DATA_CONST or __TEXT. Let's find its VM address.
# Let's search for ADRP/ADD or LDR pointing to this offset.

# Alternatively, search for the method names in Mach-O
needle_handle = b"handleInterrupt"
pos_handle = [m.start() for m in re.finditer(re.escape(needle_handle), data)]
print(f"Found {len(pos_handle)} occurrences of 'handleInterrupt'")

# Let's search for "kAICIackVecTypeTimer"
pos_timer = data.find(b"kAICIackVecTypeTimer")
print(f"'kAICIackVecTypeTimer' at file offset 0x{pos_timer:x}")

# Context around kAICIackVecTypeTimer:
print("Context:")
start = max(0, pos_timer - 64)
end = min(len(data), pos_timer + 128)
print(data[start:end])

#!/usr/bin/env python3
import struct
import capstone

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

# Search for the string "_serial_putc"
pos = data.find(b'_serial_putc\x00')
print(f"String '_serial_putc' at offset 0x{pos:x}")

# Find references to this string or xrefs
# In Mach-O, symbol table might have it
# Let's search for the byte sequence or pattern of a serial_putc function
# In Samsung/Apple UART:
# putc waits for TX empty bit in UTRSTAT (offset 0x10), then writes char to UTXH (offset 0x20)
# Let's search for ldr wX, [xY, #0x10] and strb/str wZ, [xY, #0x20]

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

# Search in __TEXT_EXEC segment (file offset 0xb18000..0x2948000)
# Let's scan for candidate functions
text_exec = data[0xb18000:0x2948000]

print(f"Scanning __TEXT_EXEC ({len(text_exec)} bytes) for UART putc pattern...")
found = 0
for off in range(0, len(text_exec) - 64, 4):
    # Check if instruction is ldr w*, [x*, #16] (0x10) or similar
    instr_bytes = text_exec[off:off+16]
    # In ARM64:
    # ldr w1, [x0, #16] is 0xb9401001
    # ldr w2, [x0, #16] is 0xb9401002
    # tbz / tbnz / and / tst
    # strb w1, [x0, #32] is 0x39008001
    # str w1, [x0, #32] is 0xb9002001
    if (text_exec[off+3] & 0xff) == 0xb9 and (text_exec[off+1] & 0xff) == 0x10: # ldr w*, [x*, #16]
        # Disassemble 10 instructions
        code = text_exec[off:off+40]
        dis = list(md.disasm(code, 0xfffffff007b1c000 + off))
        dis_text = " ".join([f"{i.mnemonic} {i.op_str}" for i in dis])
        if ("#0x10" in dis_text or "#16" in dis_text) and ("#0x20" in dis_text or "#32" in dis_text):
            print(f"\nCandidate putc function at file offset 0x{0xb18000+off:x} (VA: 0x{0xfffffff007b1c000+off:x}):")
            for i in dis[:8]:
                print(f"  0x{i.address:x}: {i.mnemonic:8} {i.op_str}")
            found += 1
            if found >= 5:
                break

#!/usr/bin/env python3
"""
Inspect the Mach-O header and entry point of kernelcache.macho.
Find LC_UNIXTHREAD or entry point command, and disassemble early start code.
"""
import struct
import capstone

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

# Parse 64-bit Mach-O header
magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack_from('<IiiIIIII', data, 0)
print(f"Mach-O Magic: 0x{magic:x}")
print(f"cputype: 0x{cputype:x}, cpusubtype: 0x{cpusubtype:x}")
print(f"filetype: 0x{filetype:x}, ncmds: {ncmds}, sizeofcmds: {sizeofcmds}")

offset = 32
entry_point = None

for i in range(ncmds):
    cmd, cmdsize = struct.unpack_from('<II', data, offset)
    if cmd == 0x5: # LC_UNIXTHREAD
        print(f"Found LC_UNIXTHREAD at offset 0x{offset:x}")
        # ARM64 thread state: flavor 6 (ARM_THREAD_STATE64), count
        flavor, count = struct.unpack_from('<II', data, offset + 8)
        # Entry pc is at offset 16 + 32*8 = 16 + 256 = 272?
        # struct arm_thread_state64: uint64_t x[29], fp, lr, sp, pc, cpsr
        # x[0..28] = 29*8 = 232, fp=8, lr=8, sp=8, pc=8 -> pc is at index 32 (offset + 16 + 32*8 = offset + 272)
        pc = struct.unpack_from('<Q', data, offset + 16 + 32*8)[0]
        print(f"LC_UNIXTHREAD pc = 0x{pc:x}")
        entry_point = pc
    elif cmd == 0x80000028: # LC_MAIN
        entryoff, stacksize = struct.unpack_from('<QQ', data, offset + 8)
        print(f"Found LC_MAIN: entryoff=0x{entryoff:x}")
    elif cmd == 0x19: # LC_SEGMENT_64
        segname = data[offset+8:offset+24].rstrip(b'\x00').decode('ascii', errors='ignore')
        vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', data, offset + 24)
        if segname in ['__TEXT', '__TEXT_EXEC']:
            print(f"Segment {segname}: vm=0x{vmaddr:x}..0x{vmaddr+vmsize:x}, file=0x{fileoff:x}..0x{fileoff+filesize:x}")
    offset += cmdsize

if entry_point:
    print(f"\nEntry point VA: 0x{entry_point:x}")

#!/usr/bin/env python3
"""
Deep inspection of watchOS 10.6.1 (21U580) kernelcache.macho.
"""
import os
import sys
import struct
import re

KC_PATH = "research/ipsw/21U580/kernelcache.macho"

def main():
    if not os.path.exists(KC_PATH):
        print("Error: kernelcache.macho not found")
        return

    with open(KC_PATH, "rb") as f:
        data = f.read(4096)

    # Mach-O 64-bit header
    magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack("<IIIIIIII", data[:32])

    print("=== MACH-O HEADER ===")
    print(f"  Magic:        0x{magic:08x} ({'MH_MAGIC_64' if magic == 0xfeedfacf else 'UNKNOWN'})")
    print(f"  CPU Type:     0x{cputype:08x} ({'ARM64' if cputype == 0x0100000c else 'OTHER'})")
    
    # Subtype: arm64e has high bits or specific mask
    subtype_mask = cpusubtype & 0xff
    arm64e_flag = (cpusubtype & 0x80000000) != 0
    print(f"  CPU Subtype:  0x{cpusubtype:08x} (subtype={subtype_mask}, PAC={arm64e_flag})")
    print(f"  File Type:    0x{filetype:08x} ({'MH_FILESET' if filetype == 12 else 'OTHER'})")
    print(f"  Commands:     {ncmds}")
    print(f"  Size of Cmds: {sizeofcmds} bytes")
    print(f"  Flags:        0x{flags:08x}")

    # Read all load commands
    with open(KC_PATH, "rb") as f:
        cmd_data = f.read(32 + sizeofcmds)[32:]

    offset = 0
    fileset_entries = []
    has_symtab = False
    symtab_info = None

    LC_FILESET_ENTRY = 0x80000035
    LC_SYMTAB = 0x2
    LC_SEGMENT_64 = 0x19

    segments = []

    for i in range(ncmds):
        if offset + 8 > len(cmd_data):
            break
        cmd, cmdsize = struct.unpack_from("<II", cmd_data, offset)
        if cmd == LC_FILESET_ENTRY:
            # Fileset entry
            vmaddr, fileoff, id_offset = struct.unpack_from("<QQI", cmd_data, offset + 8)
            # id_offset is relative to start of load command
            entry_id = cmd_data[offset + id_offset : offset + cmdsize].split(b"\x00")[0].decode("ascii", errors="replace")
            fileset_entries.append((entry_id, vmaddr, fileoff))
        elif cmd == LC_SYMTAB:
            has_symtab = True
            symoff, nsyms, stroff, strsize = struct.unpack_from("<IIII", cmd_data, offset + 8)
            symtab_info = (symoff, nsyms, stroff, strsize)
        elif cmd == LC_SEGMENT_64:
            segname = cmd_data[offset + 8 : offset + 24].split(b"\x00")[0].decode("ascii", errors="replace")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", cmd_data, offset + 24)
            segments.append((segname, vmaddr, vmsize, fileoff, filesize))
        offset += cmdsize

    print(f"\n=== SEGMENTS ({len(segments)}) ===")
    for s in segments:
        print(f"  {s[0]:16} vm: 0x{s[1]:016x}..0x{s[1]+s[2]:016x} (size: 0x{s[2]:x}) file: 0x{s[3]:x}..0x{s[3]+s[4]:x}")

    print(f"\n=== SYMBOL TABLE ===")
    if has_symtab:
        print(f"  Present! nsyms={symtab_info[1]}, symoff=0x{symtab_info[0]:x}, stroff=0x{symtab_info[2]:x} (strsize={symtab_info[3]} bytes)")
    else:
        print("  LC_SYMTAB not in top-level header (may be stripped or in fileset entries)")

    print(f"\n=== FILESET ENTRIES ({len(fileset_entries)}) ===")
    # Print kernel first, then interesting kexts
    for entry_id, vmaddr, fileoff in sorted(fileset_entries, key=lambda x: x[1]):
        entry_lower = entry_id.lower()
        if any(k in entry_lower for k in ["mach", "kernel", "t8006", "applearm", "iokit", "disp", "touch", "gpio", "uart", "crown", "aic", "mipi", "rtp", "aop", "wdt", "spmi", "pmu"]):
            print(f"  0x{vmaddr:016x} (fileoff: 0x{fileoff:08x}) {entry_id}")

    # Search for XNU version string
    print("\n=== SEARCHING FOR XNU VERSION STRING ===")
    with open(KC_PATH, "rb") as f:
        full_data = f.read()

    match = re.search(rb"Darwin Kernel Version [^\n\x00]+", full_data)
    if match:
        print(f"  XNU Version: {match.group(0).decode('ascii', errors='replace')}")
    else:
        match2 = re.search(rb"xnu-[0-9\.]+", full_data)
        if match2:
            print(f"  XNU tag: {match2.group(0).decode('ascii', errors='replace')}")

    # Also search for T8006 references in kernelcache strings
    t8006_matches = set(re.findall(rb"[A-Za-z0-9_,-]*t8006[A-Za-z0-9_,-]*", full_data, re.IGNORECASE))
    print(f"\n=== T8006 SPECIFIC DRIVER STRINGS IN KERNELCACHE ({len(t8006_matches)}) ===")
    for m in sorted(t8006_matches)[:30]:
        print(f"  {m.decode('ascii', errors='replace')}")

if __name__ == "__main__":
    main()

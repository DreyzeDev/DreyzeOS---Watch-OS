#!/usr/bin/env python3
"""
DreyzeOS Binary Inspector
Validates and reports on built DreyzeOS ELF + raw binary.

Usage: python3 tools/inspect_binary.py build/DreyzeOS.elf build/DreyzeOS.bin
"""

import sys
import os
import struct

# ============================================================
# ELF parsing (no external libs — pure Python)
# ============================================================

ELF_MAGIC = b'\x7fELF'

EM_AARCH64 = 183  # AArch64 architecture

def read_elf(path):
    """Read and parse ELF header + sections."""
    with open(path, 'rb') as f:
        data = f.read()

    if data[:4] != ELF_MAGIC:
        print(f"ERROR: {path} is not an ELF file")
        return None

    # ELF64 header
    (ei_class, ei_data, ei_version, ei_osabi,
     ei_abiversion) = struct.unpack_from('5B', data, 4)

    if ei_class != 2:
        print(f"ERROR: Not ELF64 (class={ei_class}, expected 2)")
        return None

    if ei_data != 1:
        print(f"ERROR: Not little-endian (data={ei_data}, expected 1)")
        return None

    (e_type, e_machine, e_version, e_entry,
     e_phoff, e_shoff, e_flags,
     e_ehsize, e_phentsize, e_phnum,
     e_shentsize, e_shnum, e_shstrndx) = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)

    result = {
        'raw': data,
        'ei_class': ei_class,
        'ei_data': ei_data,
        'e_type': e_type,
        'e_machine': e_machine,
        'e_entry': e_entry,
        'e_shoff': e_shoff,
        'e_shnum': e_shnum,
        'e_shentsize': e_shentsize,
        'e_shstrndx': e_shstrndx,
        'sections': [],
    }

    # Parse section headers
    if e_shoff > 0 and e_shnum > 0:
        # Get section name string table
        shstrtab_offset = e_shoff + e_shstrndx * e_shentsize
        (_, _, _, _, shstr_off, shstr_size, _, _, _, _) = struct.unpack_from(
            '<IIQQQQIIQQ', data, shstrtab_offset)

        for i in range(e_shnum):
            sh_off = e_shoff + i * e_shentsize
            (sh_name, sh_type, sh_flags, sh_addr,
             sh_offset, sh_size, sh_link, sh_info,
             sh_addralign, sh_entsize) = struct.unpack_from('<IIQQQQIIQQ', data, sh_off)

            # Get section name
            name_off = shstr_off + sh_name
            name_end = data.index(b'\x00', name_off)
            name = data[name_off:name_end].decode('ascii', errors='replace')

            result['sections'].append({
                'name': name,
                'type': sh_type,
                'flags': sh_flags,
                'addr': sh_addr,
                'offset': sh_offset,
                'size': sh_size,
            })

    return result

def check_elf(elf_path):
    """Validate ELF and print report."""
    print(f"\n{'='*50}")
    print(f"ELF Analysis: {elf_path}")
    print(f"{'='*50}")

    elf = read_elf(elf_path)
    if not elf:
        return False

    ok = True

    # Check machine type
    arch_ok = (elf['e_machine'] == EM_AARCH64)
    arch_str = "AArch64 ✓" if arch_ok else f"WRONG ({elf['e_machine']}) ✗"
    if not arch_ok:
        ok = False
    print(f"Architecture:  {arch_str}")

    # Entry point
    entry = elf['e_entry']
    print(f"Entry point:   0x{entry:016x}")

    # Check entry is at expected load base (placeholder)
    EXPECTED_BASE = 0x0000000100000000
    if entry == EXPECTED_BASE:
        print(f"               = DREYZEOS_LOAD_BASE ✓ (placeholder load address)")
    else:
        print(f"               ≠ DREYZEOS_LOAD_BASE (0x{EXPECTED_BASE:016x})")
        print(f"               NOTE: Entry offset from base = 0x{entry - EXPECTED_BASE:x}")

    # Sections
    print(f"\nSections ({len(elf['sections'])}):")
    print(f"  {'Name':<20} {'Addr':<20} {'Size':<12} {'Offset'}")
    print(f"  {'-'*20} {'-'*20} {'-'*12} {'-'*12}")

    required_sections = {'.text.boot', '.text', '.bss', '.rodata'}
    found_sections = set()

    total_load_size = 0
    for sec in elf['sections']:
        if sec['name'] == '':
            continue
        flag_str = ''
        if sec['flags'] & 0x2:  flag_str += 'A'  # ALLOC
        if sec['flags'] & 0x4:  flag_str += 'X'  # EXEC
        if sec['flags'] & 0x1:  flag_str += 'W'  # WRITE

        print(f"  {sec['name']:<20} 0x{sec['addr']:<18x} {sec['size']:<12} [{'0x'+hex(sec['offset'])[2:]}] {flag_str}")

        if sec['name'] in required_sections:
            found_sections.add(sec['name'])

        if sec['flags'] & 0x2:  # ALLOC
            total_load_size += sec['size']

    print(f"\n  Total allocated size: {total_load_size} bytes ({total_load_size/1024:.1f} KB)")

    # Check required sections
    missing = required_sections - found_sections
    if missing:
        print(f"\nWARNING: Missing sections: {missing}")
        ok = False
    else:
        print(f"\nRequired sections: all present ✓")

    # Check .text.boot is first (critical for bare-metal)
    text_boot = next((s for s in elf['sections'] if s['name'] == '.text.boot'), None)
    text = next((s for s in elf['sections'] if s['name'] == '.text'), None)
    if text_boot and text:
        if text_boot['addr'] <= text['addr']:
            print(f".text.boot before .text: ✓")
        else:
            print(f".text.boot NOT before .text: ✗ — BOOT CODE MUST BE FIRST")
            ok = False

    return ok

def check_bin(bin_path):
    """Validate raw binary."""
    print(f"\n{'='*50}")
    print(f"Binary Analysis: {bin_path}")
    print(f"{'='*50}")

    if not os.path.exists(bin_path):
        print("ERROR: Binary not found")
        return False

    with open(bin_path, 'rb') as f:
        data = f.read()

    size = len(data)
    print(f"Size: {size} bytes ({size/1024:.1f} KB)")

    if size == 0:
        print("ERROR: Binary is empty!")
        return False

    # Check first instruction — should be a branch or ADRP (AArch64 instruction)
    if size >= 4:
        first_instr = struct.unpack_from('<I', data, 0)[0]
        print(f"First instruction: 0x{first_instr:08x}")

        # AArch64 branch (B): bits [31:26] = 0b000101
        is_branch = (first_instr >> 26) == 0b000101
        # AArch64 MOV immediate (MOVZ): various
        is_nop = (first_instr == 0xd503201f)

        if is_branch:
            # Decode branch target (26-bit signed offset × 4)
            offset = (first_instr & 0x3FFFFFF) << 2
            if offset & (1 << 27):  # sign extend
                offset -= (1 << 28)
            print(f"  → B instruction (branch to offset +0x{offset:x})")
        elif is_nop:
            print(f"  → NOP instruction")
        else:
            print(f"  → Other instruction (check disassembly)")

    # Check for KLOG_MAGIC in binary (indicates log buffer)
    KLOG_MAGIC = 0x4C474F44  # "DLOG"
    magic_bytes = struct.pack('<I', KLOG_MAGIC)
    pos = data.find(magic_bytes)
    if pos != -1:
        print(f"\nKLOG buffer magic found at offset 0x{pos:x} ✓")
    else:
        print(f"\nKLOG buffer magic not found (may be in BSS — initialized at runtime)")

    # Size sanity
    if size > 64 * 1024 * 1024:
        print(f"\nERROR: Binary too large (> 64MB)")
        return False

    print(f"\nBinary: OK ✓")
    return True

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <elf> <bin>")
        sys.exit(1)

    elf_path = sys.argv[1]
    bin_path = sys.argv[2]

    elf_ok = False
    bin_ok = False

    if os.path.exists(elf_path):
        elf_ok = check_elf(elf_path)
    else:
        print(f"ELF not found: {elf_path}")

    if os.path.exists(bin_path):
        bin_ok = check_bin(bin_path)
    else:
        print(f"Binary not found: {bin_path}")

    print(f"\n{'='*50}")
    print(f"RESULT: ELF={'PASS' if elf_ok else 'FAIL'}  BIN={'PASS' if bin_ok else 'FAIL'}")
    print(f"{'='*50}\n")

    sys.exit(0 if (elf_ok and bin_ok) else 1)

if __name__ == '__main__':
    main()

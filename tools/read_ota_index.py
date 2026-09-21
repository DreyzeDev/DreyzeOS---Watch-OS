#!/usr/bin/env python3
"""
Read ZIP Central Directory from a remote URL without downloading the full file.
Uses HTTP Range requests to fetch only the end of the ZIP.
"""
import struct
import sys
import subprocess
import os

OTA_URL = "https://updates.cdn-apple.com/2024SummerFCS/patches/062-51967/6C714E97-CD8D-42CF-B586-9015643A14CF/com_apple_MobileAsset_SoftwareUpdate/ea0b1ffe1a386549747807fb13cd889d91c36591.zip"
FILE_SIZE = 2780878873
TAIL_SIZE = 131072  # 128KB tail to find EOCD

OUTDIR = "/mnt/c/Users/pc/Desktop/DreyzeOS/research/ipsw/21U580"
os.makedirs(OUTDIR, exist_ok=True)

def curl_range(url, start, end, outfile):
    """Download a byte range via curl."""
    result = subprocess.run([
        "curl", "-s", "-L", "--range", f"{start}-{end}",
        "-o", outfile, url,
        "--max-time", "60"
    ], capture_output=True)
    return result.returncode == 0

def read_eocd(data):
    """Find and parse EOCD (End of Central Directory)."""
    sig = b'PK\x05\x06'
    pos = data.rfind(sig)
    if pos < 0:
        return None
    eocd = data[pos:]
    try:
        disk_num, disk_start, num_here, num_total, cd_size, cd_offset, comment_len = \
            struct.unpack_from('<HHHHIIH', eocd, 4)
        return {
            'pos': pos, 'num_total': num_total,
            'cd_size': cd_size, 'cd_offset': cd_offset
        }
    except struct.error:
        return None

def parse_central_directory(data, num_entries):
    """Parse ZIP Central Directory entries."""
    entries = []
    offset = 0
    CD_SIG = b'PK\x01\x02'
    
    for _ in range(num_entries):
        if offset + 46 > len(data):
            break
        if data[offset:offset+4] != CD_SIG:
            # Try to find next signature
            next_pos = data.find(CD_SIG, offset)
            if next_pos < 0:
                break
            offset = next_pos
        
        try:
            (sig, ver_made, ver_needed, flags, compression,
             mod_time, mod_date, crc32, compressed_size,
             uncomp_size, name_len, extra_len, comment_len,
             disk_start, int_attr, ext_attr, local_offset) = \
                struct.unpack_from('<4sHHHHHHIIIHHHHHII', data, offset)
            
            name_offset = offset + 46
            name = data[name_offset:name_offset + name_len].decode('utf-8', errors='replace')
            
            entries.append({
                'name': name,
                'compressed_size': compressed_size,
                'uncomp_size': uncomp_size,
                'local_offset': local_offset,
                'compression': compression,
            })
            
            offset += 46 + name_len + extra_len + comment_len
        except struct.error:
            break
    
    return entries

def main():
    print(f"[*] Watch4,2 watchOS 10.6.1 (21U580) OTA Analysis")
    print(f"[*] File size: {FILE_SIZE:,} bytes ({FILE_SIZE/1024/1024/1024:.2f} GB)")
    print(f"[*] SHA2-256: f331199e8415ecbc75df0c8a6e1974c4f54acfc5c2ea1555f6daefff92ddcc78")
    print()
    
    # Step 1: Fetch tail to find EOCD
    print(f"[*] Step 1: Fetching last {TAIL_SIZE//1024}KB to find EOCD...")
    range_start = FILE_SIZE - TAIL_SIZE
    tail_file = "/tmp/ota_tail.bin"
    
    if not curl_range(OTA_URL, range_start, FILE_SIZE, tail_file):
        print("ERROR: curl failed")
        sys.exit(1)
    
    with open(tail_file, 'rb') as f:
        tail_data = f.read()
    
    print(f"    Downloaded: {len(tail_data):,} bytes")
    
    eocd = read_eocd(tail_data)
    if not eocd:
        print("ERROR: EOCD not found. ZIP may use ZIP64 or different format.")
        # Try ZIP64 EOCD locator
        sig64 = b'PK\x06\x07'
        pos64 = tail_data.rfind(sig64)
        if pos64 >= 0:
            print(f"  Found ZIP64 EOCD locator at tail+{pos64}")
            (_, disk_cd, offset64, num_disks) = struct.unpack_from('<4sIQI', tail_data, pos64)
            print(f"  ZIP64 CD offset: {offset64}")
        sys.exit(1)
    
    print(f"    EOCD found: {eocd['num_total']} entries")
    print(f"    Central Directory: offset={eocd['cd_offset']:,} size={eocd['cd_size']:,} bytes ({eocd['cd_size']/1024:.1f} KB)")
    
    # Step 2: Fetch Central Directory
    print(f"\n[*] Step 2: Fetching Central Directory...")
    cd_file = "/tmp/ota_cd.bin"
    
    if not curl_range(OTA_URL, eocd['cd_offset'], eocd['cd_offset'] + eocd['cd_size'], cd_file):
        print("ERROR: Failed to fetch Central Directory")
        sys.exit(1)
    
    with open(cd_file, 'rb') as f:
        cd_data = f.read()
    
    print(f"    Downloaded: {len(cd_data):,} bytes")
    
    # Step 3: Parse entries
    print(f"\n[*] Step 3: Parsing {eocd['num_total']} entries...")
    entries = parse_central_directory(cd_data, eocd['num_total'])
    print(f"    Parsed: {len(entries)} entries")
    
    # Step 4: Display and categorize
    print(f"\n{'='*60}")
    print("ALL FILES IN OTA:")
    print(f"{'='*60}")
    
    interesting = []
    
    for e in sorted(entries, key=lambda x: x['name']):
        size_str = f"{e['uncomp_size']:>12,}"
        comp_str = f"{e['compressed_size']:>12,}"
        print(f"  {size_str}  {comp_str}  offset=0x{e['local_offset']:08x}  {e['name']}")
        
        # Flag interesting files
        name_lower = e['name'].lower()
        if any(kw in name_lower for kw in [
            'devicetree', 'kernelcache', 'buildmanifest', 'restore.plist',
            'iboot', 'llb', 'dt', 'manifest', 'plist', 'info'
        ]):
            interesting.append(e)
    
    # Save file list
    list_path = f"{OUTDIR}/ota_file_list.txt"
    with open(list_path, 'w') as f:
        f.write(f"Watch4,2 watchOS 10.6.1 (21U580) OTA File List\n")
        f.write(f"URL: {OTA_URL}\n")
        f.write(f"File size: {FILE_SIZE:,} bytes\n")
        f.write(f"SHA2-256: f331199e8415ecbc75df0c8a6e1974c4f54acfc5c2ea1555f6daefff92ddcc78\n")
        f.write(f"Total entries: {len(entries)}\n\n")
        for e in sorted(entries, key=lambda x: x['name']):
            f.write(f"{e['uncomp_size']:12,}  {e['compressed_size']:12,}  0x{e['local_offset']:08x}  {e['name']}\n")
    
    print(f"\n[*] File list saved: {list_path}")
    
    print(f"\n{'='*60}")
    print("INTERESTING FILES (DeviceTree, kernelcache, etc.):")
    print(f"{'='*60}")
    for e in interesting:
        print(f"  {e['name']}")
        print(f"    size={e['uncomp_size']:,}  compressed={e['compressed_size']:,}  offset=0x{e['local_offset']:08x}")
    
    # Save interesting file offsets for targeted extraction
    offsets_path = f"{OUTDIR}/interesting_files.txt"
    with open(offsets_path, 'w') as f:
        for e in interesting:
            f.write(f"{e['name']}\t{e['local_offset']}\t{e['compressed_size']}\t{e['uncomp_size']}\t{e['compression']}\n")
    print(f"\n[*] Interesting file offsets: {offsets_path}")

if __name__ == '__main__':
    main()

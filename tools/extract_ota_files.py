#!/usr/bin/env python3
"""
Extract specific files from a remote ZIP via HTTP Range requests.
No need to download the full archive.
"""
import struct
import sys
import subprocess
import os
import zlib

OTA_URL = "https://updates.cdn-apple.com/2024SummerFCS/patches/062-51967/6C714E97-CD8D-42CF-B586-9015643A14CF/com_apple_MobileAsset_SoftwareUpdate/ea0b1ffe1a386549747807fb13cd889d91c36591.zip"
OUTDIR = "/mnt/c/Users/pc/Desktop/DreyzeOS/research/ipsw/21U580"

# Files to extract: (zip_path, output_filename, cd_local_offset, compressed_size, uncomp_size, compression)
# Values from read_ota_index.py output
FILES_TO_EXTRACT = [
    # (zip_name, out_name, local_offset, comp_size, uncomp_size, comp_method)
    ("AssetData/boot/Firmware/all_flash/DeviceTree.n131bap.im4p",
     "DeviceTree.n131bap.im4p", 0x00830d12, 33193, 33193, 0),

    ("AssetData/boot/BuildManifest.plist",
     "BuildManifest.plist", 0x03cadea2, 5616, 86955, 8),

    ("AssetData/boot/Restore.plist",
     "Restore.plist", 0x00003e2d, 429, 1030, 8),

    ("Info.plist",
     "Info.plist", 0x00000116, 859, 2239, 8),

    ("META-INF/com.apple.ZipMetadata.plist",
     "ZipMetadata.plist", 0x00000037, 141, 173, 8),

    ("AssetData/boot/Firmware/all_flash/LLB.n131b.RELEASE.im4p.plist",
     "LLB.n131b.RELEASE.im4p.plist", 0x00839088, 248, 331, 8),

    ("AssetData/boot/Firmware/all_flash/iBoot.n131b.RELEASE.im4p.plist",
     "iBoot.n131b.RELEASE.im4p.plist", 0x00838f22, 248, 331, 8),

    ("AssetData/Info.plist",
     "AssetData_Info.plist", 0x097cdc81, 789, 2131, 8),

    # kernelcache is large but critical - extract it
    ("AssetData/boot/kernelcache.release.watch4",
     "kernelcache.release.watch4", 0x02e2bdf2, 15212633, 15221732, 8),
]

def read_local_file_header(data):
    """Parse ZIP local file header, return (header_size, compression, compressed_size)."""
    if data[:4] != b'PK\x03\x04':
        raise ValueError(f"Not a local file header: {data[:4].hex()}")
    (sig, ver, flags, comp, mod_time, mod_date, crc32,
     comp_size, uncomp_size, name_len, extra_len) = struct.unpack_from('<4sHHHHHIIIHH', data, 0)
    header_size = 30 + name_len + extra_len
    return header_size, comp, comp_size, uncomp_size

def curl_range(url, start, size, outfile):
    """Download a byte range via curl."""
    end = start + size - 1
    result = subprocess.run([
        "curl", "-s", "-L", "--range", f"{start}-{end}",
        "-o", outfile, url,
        "--max-time", "120",
        "--retry", "3",
    ], capture_output=True)
    if result.returncode != 0:
        print(f"  curl stderr: {result.stderr.decode()[:200]}")
    return result.returncode == 0

def extract_file(zip_name, out_name, local_offset, comp_size, uncomp_size, comp_method):
    """Download and extract a single file from the remote ZIP."""
    out_path = os.path.join(OUTDIR, out_name)
    
    if os.path.exists(out_path) and os.path.getsize(out_path) == uncomp_size:
        print(f"  SKIP (already exists): {out_name} ({uncomp_size:,} bytes)")
        return True
    
    print(f"  Extracting: {zip_name}")
    print(f"    Output: {out_name}")
    print(f"    Compressed: {comp_size:,} bytes, Uncompressed: {uncomp_size:,} bytes")
    
    # Download local file header (up to 1KB) to find actual data offset
    hdr_file = f"/tmp/lhdr_{out_name.replace('/', '_')}.bin"
    if not curl_range(OTA_URL, local_offset, min(1024, comp_size + 30 + 512), hdr_file):
        print(f"    ERROR: Failed to download header")
        return False
    
    with open(hdr_file, 'rb') as f:
        hdr_data = f.read()
    
    try:
        header_size, actual_comp, actual_comp_size, actual_uncomp_size = read_local_file_header(hdr_data)
    except ValueError as e:
        print(f"    ERROR: {e}")
        return False
    
    data_offset = local_offset + header_size
    print(f"    Local header size: {header_size}, data at offset: 0x{data_offset:08x}")
    
    # Download compressed data
    raw_file = f"/tmp/raw_{out_name.replace('/', '_')}.bin"
    if not curl_range(OTA_URL, data_offset, comp_size, raw_file):
        print(f"    ERROR: Failed to download data")
        return False
    
    with open(raw_file, 'rb') as f:
        raw_data = f.read()
    
    print(f"    Downloaded: {len(raw_data):,} bytes")
    
    # Decompress if needed
    if comp_method == 0 or actual_comp == 0:
        # Stored (no compression)
        final_data = raw_data[:uncomp_size]
    elif comp_method == 8 or actual_comp == 8:
        # Deflate
        try:
            final_data = zlib.decompress(raw_data, -15)  # raw deflate
        except zlib.error as e:
            print(f"    ERROR: Decompression failed: {e}")
            # Try with different wbits
            try:
                final_data = zlib.decompress(raw_data)
            except:
                print(f"    ERROR: All decompression attempts failed")
                return False
    else:
        print(f"    ERROR: Unknown compression method: {comp_method}")
        return False
    
    print(f"    Decompressed: {len(final_data):,} bytes (expected: {uncomp_size:,})")
    
    with open(out_path, 'wb') as f:
        f.write(final_data)
    
    print(f"    Saved: {out_path}")
    return True

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    
    print("Watch4,2 watchOS 10.6.1 (21U580) — Targeted File Extraction")
    print("=" * 60)
    print(f"Output: {OUTDIR}")
    print()
    
    success = 0
    fail = 0
    
    for item in FILES_TO_EXTRACT:
        print(f"[{'='*50}]")
        ok = extract_file(*item)
        if ok:
            success += 1
        else:
            fail += 1
        print()
    
    print(f"{'='*60}")
    print(f"Extracted: {success}/{success+fail} files")
    print(f"Output directory: {OUTDIR}")
    
    # List what we got
    print("\nFiles in output directory:")
    for f in sorted(os.listdir(OUTDIR)):
        path = os.path.join(OUTDIR, f)
        if os.path.isfile(path):
            print(f"  {os.path.getsize(path):>12,}  {f}")

if __name__ == '__main__':
    main()

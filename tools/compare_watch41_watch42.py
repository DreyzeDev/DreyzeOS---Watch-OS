#!/usr/bin/env python3
"""
Inspect Watch4,1 (40mm GPS) OTA BuildManifest to compare with Watch4,2 (44mm GPS).
"""
import os
import sys
import struct
import subprocess
import zlib
import plistlib

WATCH4_1_URL = "https://updates.cdn-apple.com/2024SummerFCS/patches/062-51376/0F788546-2BDF-4ECD-8ADB-6A69965D41EA/com_apple_MobileAsset_SoftwareUpdate/4d0c56ea1af5ae6bdde4d6d58d46563918507eec.zip"
WATCH4_1_SIZE = 2782771140

def curl_range(url, start, size, outfile):
    end = start + size - 1
    res = subprocess.run(["curl", "-s", "-L", "--range", f"{start}-{end}", "-o", outfile, url, "--max-time", "60"], capture_output=True)
    return res.returncode == 0

def get_watch4_1_manifest():
    outdir = "research/ipsw/21U580/watch4_1"
    os.makedirs(outdir, exist_ok=True)
    
    tail_file = "/tmp/w41_tail.bin"
    range_start = WATCH4_1_SIZE - 65536
    if not curl_range(WATCH4_1_URL, range_start, 65536, tail_file):
        print("Failed to curl tail")
        return
    with open(tail_file, "rb") as f:
        tdata = f.read()
    pos = tdata.rfind(b'PK\x05\x06')
    if pos < 0:
        print("No EOCD in tail")
        return
    _, _, _, num_total, cd_size, cd_offset, _ = struct.unpack_from('<HHHHIIH', tdata[pos:], 4)
    print(f"Watch4,1: {num_total} entries, CD offset=0x{cd_offset:x}, size={cd_size}")

    cd_file = "/tmp/w41_cd.bin"
    if not curl_range(WATCH4_1_URL, cd_offset, cd_size, cd_file):
        print("Failed to curl CD")
        return
    with open(cd_file, "rb") as f:
        cdata = f.read()

    # Find BuildManifest and kernelcache entries
    offset = 0
    bm_entry = None
    kc_entry = None
    dt_entry = None

    CD_SIG = b'PK\x01\x02'
    for _ in range(num_total):
        if offset + 46 > len(cdata) or cdata[offset:offset+4] != CD_SIG:
            next_pos = cdata.find(CD_SIG, offset + 1)
            if next_pos < 0: break
            offset = next_pos
        (sig, ver, vneed, flags, comp, mtime, mdate, crc32,
         comp_size, uncomp_size, name_len, extra_len, comm_len,
         dstart, iattr, eattr, local_off) = struct.unpack_from('<4sHHHHHHIIIHHHHHII', cdata, offset)
        name = cdata[offset+46 : offset+46+name_len].decode('utf-8', errors='replace')
        if name.endswith("BuildManifest.plist"):
            bm_entry = (name, local_off, comp_size, uncomp_size, comp)
        elif "kernelcache" in name:
            kc_entry = (name, local_off, comp_size, uncomp_size, comp, crc32)
        elif "DeviceTree" in name:
            dt_entry = (name, local_off, comp_size, uncomp_size, comp, crc32)
        offset += 46 + name_len + extra_len + comm_len

    print(f"Watch4,1 BuildManifest: {bm_entry}")
    print(f"Watch4,1 KernelCache:   {kc_entry}")
    print(f"Watch4,1 DeviceTree:    {dt_entry}")

    # Extract BuildManifest
    if bm_entry:
        hdr_file = "/tmp/w41_bm_hdr.bin"
        curl_range(WATCH4_1_URL, bm_entry[1], 1024, hdr_file)
        with open(hdr_file, "rb") as f:
            hdata = f.read()
        nlen, xlen = struct.unpack_from('<HH', hdata, 26)
        data_off = bm_entry[1] + 30 + nlen + xlen
        raw_file = "/tmp/w41_bm_raw.bin"
        curl_range(WATCH4_1_URL, data_off, bm_entry[2], raw_file)
        with open(raw_file, "rb") as f:
            rdata = f.read()
        decomp = zlib.decompress(rdata, -15)
        bm_out = os.path.join(outdir, "BuildManifest.plist")
        with open(bm_out, "wb") as f:
            f.write(decomp)
        print(f"Saved Watch4,1 BuildManifest to {bm_out}")
        
        pl = plistlib.loads(decomp)
        for idx, bi in enumerate(pl.get("BuildIdentities", [])):
            manifest = bi.get("Manifest", {})
            dt_dig = manifest.get("DeviceTree", {}).get("Digest", b"").hex()
            kc_dig = manifest.get("KernelCache", {}).get("Digest", b"").hex()
            dev_cls = bi.get("Info", {}).get("DeviceClass", "N/A")
            print(f"  Watch4,1 Identity {idx}: DeviceClass={dev_cls}")
            print(f"    DT Digest: {dt_dig}")
            print(f"    KC Digest: {kc_dig}")

if __name__ == '__main__':
    get_watch4_1_manifest()

#!/usr/bin/env python3
import plistlib
import os

bm_path = "research/ipsw/21U580/BuildManifest.plist"
if not os.path.exists(bm_path):
    print("Error: BuildManifest.plist not found")
    exit(1)

with open(bm_path, "rb") as f:
    pl = plistlib.load(f)

print(f"BuildIdentities count: {len(pl.get('BuildIdentities', []))}")

for idx, bi in enumerate(pl.get("BuildIdentities", [])):
    info = bi.get("Info", {})
    device_class = info.get("DeviceClass", "N/A")
    board_id = bi.get("BoardConfig", "N/A")
    manifest = bi.get("Manifest", {})
    
    dt_info = manifest.get("DeviceTree", {}).get("Info", {})
    dt_path = dt_info.get("Path", "N/A")
    
    kc_info = manifest.get("KernelCache", {}).get("Info", {})
    kc_path = kc_info.get("Path", "N/A")

    dt_digest = manifest.get("DeviceTree", {}).get("Digest", b"").hex()
    kc_digest = manifest.get("KernelCache", {}).get("Digest", b"").hex()

    print(f"\n--- Identity {idx} ---")
    print(f"  DeviceClass:  {device_class}")
    print(f"  BoardConfig:  {board_id}")
    print(f"  DeviceTree:   {dt_path}")
    print(f"  DT Digest:    {dt_digest}")
    print(f"  KernelCache:  {kc_path}")
    print(f"  KC Digest:    {kc_digest}")

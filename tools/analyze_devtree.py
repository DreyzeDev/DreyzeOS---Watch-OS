#!/usr/bin/env python3
"""
Deep analysis of Apple Watch Series 4 (Watch4,2 / N131bAP / T8006) DeviceTree.
"""
import os
import sys
import struct

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.device_tree_dump import parse_adt, walk_nodes, find_mmio_regions

ADT_PATH = "research/ipsw/21U580/DeviceTree.n131bap.adt"

def main():
    if not os.path.exists(ADT_PATH):
        print(f"Error: {ADT_PATH} not found")
        sys.exit(1)

    with open(ADT_PATH, "rb") as f:
        data = f.read()

    root, _ = parse_adt(data)

    print("=== DEVICE TREE ROOT PROPERTIES ===")
    for p in root.props:
        print(f"  {p.name}: {p.as_str() if p.size < 64 else f'<{p.size} bytes>'}")

    print("\n=== TOP LEVEL NODES ===")
    for c in root.children:
        print(f"  /{c.name} (props: {len(c.props)}, children: {len(c.children)})")

    print("\n=== TARGETED HARDWARE SEARCH ===")
    keywords = [
        "disp", "dfr", "framebuffer", "lcd", "oled", "mipi", "backlight",
        "touch", "multitouch", "z2", "bcm",
        "crown", "encoder", "rotary", "dial",
        "button", "gpio", "pin", "key",
        "spi", "i2c", "i2s", "uart", "serial",
        "timer", "aic", "interrupt", "wdt",
        "dart", "iommu", "sart", "dapf",
        "pmgr", "power", "pmu", "spmi",
        "memory", "dram", "carveout", "reserved",
        "usb", "otg", "dock"
    ]

    nodes_by_kw = {kw: [] for kw in keywords}

    for path, node in walk_nodes(root):
        path_lower = path.lower()
        compat = node.get_prop("compatible")
        compat_str = compat.as_str().lower() if compat else ""
        
        for kw in keywords:
            if kw in path_lower or kw in compat_str:
                reg_prop = node.get_prop("reg")
                regs = reg_prop.as_reg() if reg_prop else []
                reg_str = " ".join([f"[0x{b:x}+0x{s:x}]" for b, s in regs]) if regs else "no reg"
                nodes_by_kw[kw].append((path, compat.as_str() if compat else "N/A", reg_str, node))

    for kw in keywords:
        matches = nodes_by_kw[kw]
        if matches:
            print(f"\n--- Matches for '{kw}' ({len(matches)}) ---")
            # Deduplicate by path
            seen = set()
            for path, compat, reg_str, node in matches:
                if path in seen:
                    continue
                seen.add(path)
                print(f"  {path}")
                print(f"    compatible: {compat}")
                print(f"    reg: {reg_str}")
                # Print other interesting props
                for p in node.props:
                    if p.name in ["interrupts", "clock-gates", "function", "pin-count", "status", "AAPL,phandle"]:
                        print(f"    {p.name}: {p.as_hex()}")

if __name__ == "__main__":
    main()

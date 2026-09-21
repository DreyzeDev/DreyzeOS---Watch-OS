#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.device_tree_dump import parse_adt, walk_nodes

ADT_PATH = "research/ipsw/21U580/DeviceTree.n131bap.adt"

def dump_node(node, path):
    print(f"\n==========================================")
    print(f"NODE: {path}")
    print(f"==========================================")
    for p in node.props:
        # Determine format
        if p.name == "reg":
            regs = p.as_reg()
            reg_strs = [f"base=0x{b:016x} size=0x{s:x}" for b, s in regs]
            print(f"  reg: {', '.join(reg_strs)}")
        elif p.size == 4:
            v = p.as_u32()
            print(f"  {p.name}: 0x{v:08x} ({v})")
        elif p.size == 8:
            v = p.as_u64()
            print(f"  {p.name}: 0x{v:016x}")
        elif p.size < 128 and all(32 <= b < 127 or b == 0 for b in p.value):
            print(f"  {p.name}: {p.as_str()!r}")
        else:
            print(f"  {p.name}: <{p.size} bytes: {p.as_hex()[:48]}...>")
    for c in node.children:
        print(f"  CHILD -> {c.name}")

def main():
    with open(ADT_PATH, "rb") as f:
        data = f.read()
    root, _ = parse_adt(data)

    target_paths = [
        "/buttons",
        "/backlight",
        "/memory",
        "/pram",
        "/vram",
        "/chosen/memory-map",
        "/chosen/carveout-memory-map",
        "/arm-io/disp0",
        "/arm-io/mipi-dsim",
        "/arm-io/mipi-dsim/lcd",
        "/arm-io/gpio",
        "/arm-io/aop-gpio",
        "/arm-io/spi0",
        "/arm-io/spi1",
        "/arm-io/spi2",
        "/arm-io/spi3",
        "/arm-io/dockchannel-rtp/rtp-transport/multi-touch",
        "/arm-io/dockchannel-rtp/rtp-transport/optical",
        "/arm-io/dockchannel-rtp",
        "/arm-io/rtp",
        "/arm-io/aop",
        "/arm-io/aic",
        "/arm-io/aic-timebase",
        "/arm-io/uart0",
        "/arm-io/dockchannel-uart",
        "/arm-io/usb-complex/usb-device",
        "/cpus",
        "/cpus/cpu0",
        "/cpus/cpu1"
    ]

    for path, node in walk_nodes(root):
        if path in target_paths or any(path.startswith(tp + "/") for tp in ["/chosen/memory-map"]):
            dump_node(node, path)

if __name__ == "__main__":
    main()

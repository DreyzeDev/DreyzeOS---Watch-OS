#!/usr/bin/env python3
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.device_tree_dump import parse_adt, walk_nodes

root, _ = parse_adt(open('research/ipsw/21U580/DeviceTree.n131bap.adt','rb').read())

for path, node in walk_nodes(root):
    if path == '/chosen/memory-map':
        print(f"NODE: {path}")
        for p in node.props:
            if len(p.value) == 16:
                base, size = struct.unpack('<QQ', p.value)
                print(f"  {p.name:25}: base=0x{base:016x} size=0x{size:08x} ({size/(1024*1024):.2f} MB)")
            else:
                print(f"  {p.name:25}: len={len(p.value)} {p.as_hex()}")

    if path == '/buttons':
        print(f"\nNODE: {path}")
        for p in node.props:
            print(f"  {p.name:25}: {p.as_hex()} | {p.as_str()[:30] if p.size < 64 else ''}")

    if 'disp0' in path:
        print(f"\nNODE: {path}")
        for p in node.props:
            if p.name in ['reg', 'display-timing-info', 'dot-pitch']:
                print(f"  {p.name:25}: {p.as_hex()}")

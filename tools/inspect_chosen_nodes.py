#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from tools.device_tree_dump import parse_adt, walk_nodes

with open('research/ipsw/21U580/DeviceTree.n131bap.adt', 'rb') as f:
    data = f.read()

root, _ = parse_adt(data)

print(f"Total ADT size: {len(data)} bytes\n")

for path, node in walk_nodes(root):
    if any(k in path.lower() for k in ['chosen', 'memory', 'disp', 'video', 'framebuffer', 'lcd', 'backlight', 'vram']):
        print(f"=== Node: {path} ===")
        for p in node.props:
            val_repr = p.as_str()
            # print up to 50 bytes hex or str
            if len(p.value) <= 16:
                val_hex = ' '.join(f'{b:02x}' for b in p.value)
            else:
                val_hex = ' '.join(f'{b:02x}' for b in p.value[:16]) + '...'
            print(f"  prop: {p.name:24} (size {len(p.value):4d}): hex=[{val_hex}] str={val_repr!r}")
        print()

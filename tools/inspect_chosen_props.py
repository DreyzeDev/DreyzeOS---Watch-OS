#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from tools.device_tree_dump import parse_adt, walk_nodes

with open('research/ipsw/21U580/DeviceTree.n131bap.adt', 'rb') as f:
    data = f.read()

root, _ = parse_adt(data)

for path, node in walk_nodes(root):
    if path == '/chosen':
        print(f"=== Node: {path} ===")
        for p in node.props:
            val_hex = ' '.join(f'{b:02x}' for b in p.value[:32])
            print(f"  prop: {p.name:24} (size {len(p.value):4d}): hex=[{val_hex}] str={p.as_str()!r}")

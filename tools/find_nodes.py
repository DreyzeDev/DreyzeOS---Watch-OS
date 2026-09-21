#!/usr/bin/env python3
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.device_tree_dump import parse_adt, walk_nodes

root, _ = parse_adt(open('research/ipsw/21U580/DeviceTree.n131bap.adt','rb').read())

print("=== ALL SPI NODES ===")
for path, node in walk_nodes(root):
    if 'spi' in path.lower() and 'spmi' not in path.lower() and 'dsim' not in path.lower():
        regs = node.get_prop('reg').as_reg() if node.get_prop('reg') else []
        compat = node.get_prop('compatible').as_str() if node.get_prop('compatible') else 'N/A'
        print(f"  {path} : compat={compat} reg={regs}")

print("\n=== ALL I2C NODES ===")
for path, node in walk_nodes(root):
    if 'i2c' in path.lower():
        regs = node.get_prop('reg').as_reg() if node.get_prop('reg') else []
        compat = node.get_prop('compatible').as_str() if node.get_prop('compatible') else 'N/A'
        print(f"  {path} : compat={compat} reg={regs}")

print("\n=== ALL SIO / SERIAL / UART NODES ===")
for path, node in walk_nodes(root):
    if any(k in path.lower() for k in ['sio', 'uart', 'serial']):
        regs = node.get_prop('reg').as_reg() if node.get_prop('reg') else []
        compat = node.get_prop('compatible').as_str() if node.get_prop('compatible') else 'N/A'
        print(f"  {path} : compat={compat} reg={regs}")

print("\n=== ALL CHOSEN NODES & MEMORY MAP ===")
for path, node in walk_nodes(root):
    if path.startswith('/chosen'):
        print(f"  {path}")
        for p in node.props:
            if p.size == 4:
                v = p.as_u32()
                print(f"    {p.name}: 0x{v:x} ({v})")
            elif p.size == 8:
                v = p.as_u64()
                print(f"    {p.name}: 0x{v:x}")
            elif p.size < 64:
                print(f"    {p.name}: {p.as_str()!r}")

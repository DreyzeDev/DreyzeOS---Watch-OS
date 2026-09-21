#!/usr/bin/env python3
"""
DreyzeOS Apple DeviceTree Dumper / Parser
Parses Apple's proprietary binary DeviceTree format (ADT).

Usage:
    python3 tools/device_tree_dump.py <devtree.bin> [--output report.md]
    python3 tools/device_tree_dump.py <devtree.bin> --find-mmio

ADT Format (confirmed from multiple open-source parsers):
    struct dt_node_header {
        uint32_t prop_count;
        uint32_t child_count;
    };
    // followed by prop_count properties:
    struct dt_prop {
        char name[32];     // null-terminated, 32 bytes
        uint32_t size;     // size of value in bytes (high bit: type hint)
        uint8_t  value[]; // value bytes (padded to 4-byte boundary)
    };
    // followed by child_count child nodes (recursive)
"""

import sys
import os
import struct
import json
import argparse
from typing import Optional

# ============================================================
# Apple DeviceTree (ADT) Parser
# ============================================================

DT_PROP_NAME_LEN = 32  # Fixed 32-byte name field

class DTProperty:
    """A single DeviceTree property."""
    def __init__(self, name: str, size: int, value: bytes):
        self.name = name
        self.size = size
        self.value = value

    def as_u32(self) -> Optional[int]:
        if len(self.value) >= 4:
            return struct.unpack_from('<I', self.value)[0]
        return None

    def as_u64(self) -> Optional[int]:
        if len(self.value) >= 8:
            return struct.unpack_from('<Q', self.value)[0]
        return None

    def as_str(self) -> str:
        try:
            null_pos = self.value.index(b'\x00')
            return self.value[:null_pos].decode('ascii', errors='replace')
        except (ValueError, UnicodeDecodeError):
            return self.value.decode('ascii', errors='replace').rstrip('\x00')

    def as_hex(self) -> str:
        return self.value[:min(64, len(self.value))].hex()

    def as_reg(self):
        """Parse 'reg' property as list of (base, size) tuples."""
        regs = []
        data = self.value
        # Try 8-byte pairs (base_u64, size_u64)
        if len(data) >= 16 and len(data) % 16 == 0:
            for i in range(0, len(data), 16):
                base, sz = struct.unpack_from('<QQ', data, i)
                regs.append((base, sz))
        # Try 4-byte pairs (base_u32, size_u32)
        elif len(data) >= 8 and len(data) % 8 == 0:
            for i in range(0, len(data), 8):
                base, sz = struct.unpack_from('<II', data, i)
                regs.append((base, sz))
        return regs

    def __repr__(self):
        return f"DTProperty(name={self.name!r}, size={self.size}, value={self.as_hex()[:32]})"


class DTNode:
    """A DeviceTree node with properties and children."""
    def __init__(self, name: str = ""):
        self.name = name
        self.props: list[DTProperty] = []
        self.children: list['DTNode'] = []

    def get_prop(self, name: str) -> Optional[DTProperty]:
        for p in self.props:
            if p.name == name:
                return p
        return None

    def __repr__(self):
        return f"DTNode(name={self.name!r}, props={len(self.props)}, children={len(self.children)})"


def parse_adt(data: bytes, offset: int = 0) -> tuple[DTNode, int]:
    """
    Recursively parse Apple DeviceTree from binary data.
    Returns (node, new_offset).
    """
    node = DTNode()

    if offset + 8 > len(data):
        raise ValueError(f"Unexpected end of data at offset 0x{offset:x}")

    prop_count, child_count = struct.unpack_from('<II', data, offset)
    offset += 8

    # Parse properties
    for _ in range(prop_count):
        if offset + DT_PROP_NAME_LEN + 4 > len(data):
            raise ValueError(f"Truncated property at offset 0x{offset:x}")

        # Name: 32 bytes, null-terminated
        name_bytes = data[offset:offset + DT_PROP_NAME_LEN]
        try:
            null_pos = name_bytes.index(b'\x00')
            name = name_bytes[:null_pos].decode('ascii', errors='replace')
        except ValueError:
            name = name_bytes.decode('ascii', errors='replace')
        offset += DT_PROP_NAME_LEN

        # Size: 4 bytes (high bit may be type flag)
        raw_size = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        prop_size = raw_size & 0x7FFFFFFF  # mask type bit

        # Value: prop_size bytes, padded to 4-byte boundary
        value = data[offset:offset + prop_size]
        padded = (prop_size + 3) & ~3
        offset += padded

        prop = DTProperty(name, prop_size, value)
        node.props.append(prop)

        # Get node name from 'name' property
        if name == 'name':
            node.name = prop.as_str()

    # Parse children
    for _ in range(child_count):
        child, offset = parse_adt(data, offset)
        node.children.append(child)

    return node, offset


# ============================================================
# Report generation
# ============================================================

def walk_nodes(node: DTNode, path: str = "/"):
    """Generator: yield (path, node) for all nodes in tree."""
    yield path, node
    for child in node.children:
        child_path = path.rstrip('/') + '/' + child.name
        yield from walk_nodes(child, child_path)


def find_mmio_regions(root: DTNode) -> list[dict]:
    """Extract all MMIO regions from 'reg' properties."""
    regions = []
    for path, node in walk_nodes(root):
        reg_prop = node.get_prop('reg')
        if reg_prop:
            compatible_prop = node.get_prop('compatible')
            compatible = compatible_prop.as_str() if compatible_prop else "N/A"
            regs = reg_prop.as_reg()
            for base, size in regs:
                if base != 0 and size != 0:
                    regions.append({
                        'path': path,
                        'compatible': compatible,
                        'base': base,
                        'size': size,
                    })
    return regions


def generate_report(root: DTNode, output_path: Optional[str] = None) -> str:
    """Generate a human-readable report from parsed DeviceTree."""
    lines = []
    lines.append("# Apple DeviceTree Dump")
    lines.append("# Generated by DreyzeOS device_tree_dump.py")
    lines.append("")

    # MMIO regions
    regions = find_mmio_regions(root)
    lines.append("## MMIO Regions (from 'reg' properties)")
    lines.append("")
    if regions:
        lines.append("| Node Path | Compatible | Base Address | Size |")
        lines.append("|-----------|-----------|--------------|------|")
        for r in sorted(regions, key=lambda x: x['base']):
            lines.append(
                f"| `{r['path']}` | `{r['compatible']}` "
                f"| `0x{r['base']:016x}` | `0x{r['size']:x}` |"
            )
    else:
        lines.append("No 'reg' properties found.")
    lines.append("")

    # Full tree
    lines.append("## Full DeviceTree")
    lines.append("")
    lines.append("```")
    _dump_tree(root, lines, indent=0)
    lines.append("```")

    report = '\n'.join(lines)

    if output_path:
        with open(output_path, 'w') as f:
            f.write(report)
        print(f"Report written to {output_path}")

    return report


def _dump_tree(node: DTNode, lines: list, indent: int):
    """Recursively dump tree as text."""
    prefix = "  " * indent
    lines.append(f"{prefix}[{node.name or '(unnamed)'}]")
    for prop in node.props:
        value_str = _format_prop_value(prop)
        lines.append(f"{prefix}  {prop.name} = {value_str}")
    for child in node.children:
        _dump_tree(child, lines, indent + 1)


def _format_prop_value(prop: DTProperty) -> str:
    """Format a property value for display."""
    if prop.name in ('name', 'compatible', 'device_type', 'status'):
        return repr(prop.as_str())
    if prop.name == 'reg':
        regs = prop.as_reg()
        if regs:
            return ' '.join(f"[0x{b:x}+0x{s:x}]" for b, s in regs)
    if prop.size == 4:
        v = prop.as_u32()
        if v is not None:
            return f"0x{v:08x}"
    if prop.size == 8:
        v = prop.as_u64()
        if v is not None:
            return f"0x{v:016x}"
    if prop.size == 0:
        return "(empty)"
    # Raw hex
    hex_str = prop.value[:32].hex()
    suffix = "..." if len(prop.value) > 32 else ""
    return f"<{prop.size} bytes: {hex_str}{suffix}>"


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="DreyzeOS Apple DeviceTree Dumper"
    )
    parser.add_argument('input', help='DeviceTree binary file (raw ADT, not IMG4)')
    parser.add_argument('--output', '-o', help='Output report file (markdown)')
    parser.add_argument('--mmio', action='store_true', help='Print MMIO regions only')
    parser.add_argument('--json', help='Export full tree as JSON to file')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}")
        sys.exit(1)

    with open(args.input, 'rb') as f:
        data = f.read()

    print(f"Parsing DeviceTree: {args.input} ({len(data)} bytes)")

    try:
        root, consumed = parse_adt(data, 0)
    except Exception as e:
        print(f"ERROR: Failed to parse DeviceTree: {e}")
        print("NOTE: This parser expects raw ADT binary, NOT IMG4 wrapped.")
        print("      Use img4tool to extract: img4tool -e -p DeviceTree.raw DeviceTree.img4")
        sys.exit(1)

    print(f"Parsed {consumed}/{len(data)} bytes")
    print(f"Root children: {len(root.children)}")

    if args.mmio or not args.output:
        regions = find_mmio_regions(root)
        print(f"\n=== MMIO Regions ({len(regions)} found) ===")
        for r in sorted(regions, key=lambda x: x['base']):
            print(f"  0x{r['base']:016x} +0x{r['size']:08x}  {r['path']}")
            if r['compatible'] != 'N/A':
                print(f"    compatible: {r['compatible']}")

    if args.output:
        generate_report(root, args.output)

    if args.json:
        def node_to_dict(n: DTNode) -> dict:
            return {
                'name': n.name,
                'props': {p.name: p.as_hex() for p in n.props},
                'children': [node_to_dict(c) for c in n.children],
            }
        with open(args.json, 'w') as f:
            json.dump(node_to_dict(root), f, indent=2)
        print(f"JSON tree written to {args.json}")


if __name__ == '__main__':
    main()

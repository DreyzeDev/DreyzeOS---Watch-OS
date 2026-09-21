#!/usr/bin/env python3
"""
DreyzeOS IM4P/IMG4 Parser
Parses Apple IMG4 container format (ASN.1/DER) to extract raw payload.

IMG4 format:
  SEQUENCE {
    IA5String "IMG4"
    [0] EXPLICIT {
      SEQUENCE {
        IA5String "IM4P"     <- IM4P type tag
        IA5String <fourcc>   <- e.g. "dtre" for DeviceTree
        UTF8String <description>
        OCTET STRING <payload>  <- actual data (may be encrypted)
        [1] SEQUENCE { ... }  <- keybag (if encrypted)
      }
    }
    ...
  }

For DeviceTree (dtre), the payload is NOT encrypted in OTA packages
for research purposes. The raw ADT binary follows directly.

Reference:
  https://www.theiphonewiki.com/wiki/IMG4_File_Format
  https://github.com/libimobiledevice/libimobiledevice (img4tool)
"""

import sys
import os
import struct

# ============================================================
# Minimal ASN.1/DER parser
# ============================================================

# ASN.1 universal tags
TAG_SEQUENCE    = 0x30
TAG_IA5STRING   = 0x16
TAG_UTF8STRING  = 0x0C
TAG_OCTETSTRING = 0x04
TAG_BOOLEAN     = 0x01
TAG_INTEGER     = 0x02
TAG_SET         = 0x31
# Context-specific
TAG_CTX_0       = 0xA0
TAG_CTX_1       = 0xA1
TAG_CTX_2       = 0xA2
TAG_CTX_3       = 0xA3

def parse_length(data, offset):
    """Parse DER length encoding. Returns (length, new_offset)."""
    b = data[offset]
    offset += 1
    if b < 0x80:
        return b, offset
    num_bytes = b & 0x7F
    length = 0
    for _ in range(num_bytes):
        length = (length << 8) | data[offset]
        offset += 1
    return length, offset

def parse_tlv(data, offset):
    """Parse a single TLV. Returns (tag, value_bytes, new_offset)."""
    if offset >= len(data):
        return None, None, offset
    
    tag = data[offset]
    offset += 1
    
    # Handle multi-byte tags
    if (tag & 0x1F) == 0x1F:
        while data[offset] & 0x80:
            tag = (tag << 8) | data[offset]
            offset += 1
        tag = (tag << 8) | data[offset]
        offset += 1
    
    length, offset = parse_length(data, offset)
    value = data[offset:offset + length]
    return tag, value, offset + length

def parse_sequence(data):
    """Parse all TLVs in a sequence. Returns list of (tag, value)."""
    items = []
    offset = 0
    while offset < len(data):
        tag, value, offset = parse_tlv(data, offset)
        if tag is None:
            break
        items.append((tag, value))
    return items

# ============================================================
# IM4P Parser
# ============================================================

def parse_im4p(data):
    """
    Parse an IM4P file (unwrapped IMG4 component).
    Returns dict with: fourcc, description, payload, has_keybag
    """
    # IM4P is a raw SEQUENCE (no outer IMG4 wrapper)
    # Check if this is IMG4 (has outer wrapper) or IM4P (raw)
    
    if data[:4] == b'\x30':
        # Might be SEQUENCE directly
        pass
    
    # Try to parse as SEQUENCE
    tag, seq_data, _ = parse_tlv(data, 0)
    
    if tag != TAG_SEQUENCE:
        raise ValueError(f"Expected SEQUENCE tag 0x30, got 0x{tag:02x}")
    
    items = parse_sequence(seq_data)
    
    if not items:
        raise ValueError("Empty SEQUENCE")
    
    result = {
        'type': None,
        'fourcc': None,
        'description': None,
        'payload': None,
        'has_keybag': False,
        'keybag_size': 0,
    }
    
    item_idx = 0
    
    # First item should be type string "IM4P"
    if items[item_idx][0] == TAG_IA5STRING:
        result['type'] = items[item_idx][1].decode('ascii', errors='replace')
        item_idx += 1
    
    # Second item: fourcc
    if item_idx < len(items) and items[item_idx][0] == TAG_IA5STRING:
        result['fourcc'] = items[item_idx][1].decode('ascii', errors='replace')
        item_idx += 1
    
    # Third item: description
    if item_idx < len(items) and items[item_idx][0] in (TAG_UTF8STRING, TAG_IA5STRING):
        result['description'] = items[item_idx][1].decode('utf-8', errors='replace')
        item_idx += 1
    
    # Fourth item: payload (OCTET STRING)
    if item_idx < len(items) and items[item_idx][0] == TAG_OCTETSTRING:
        result['payload'] = items[item_idx][1]
        item_idx += 1
    
    # Optional: keybag [1] SEQUENCE
    if item_idx < len(items):
        tag = items[item_idx][0]
        if tag == TAG_CTX_1:
            result['has_keybag'] = True
            result['keybag_size'] = len(items[item_idx][1])
    
    return result

def extract_im4p_payload(im4p_path, output_path):
    """Extract raw payload from IM4P file."""
    print(f"\n[IM4P] Parsing: {im4p_path}")
    
    with open(im4p_path, 'rb') as f:
        data = f.read()
    
    print(f"  File size: {len(data):,} bytes")
    print(f"  Magic bytes: {data[:4].hex()}")
    
    # Check for IMG4 wrapper (IM4P inside IMG4)
    # IMG4 outer: SEQUENCE { IA5String "IMG4" [0] { ... } }
    # Try direct parse first
    
    try:
        result = parse_im4p(data)
    except Exception as e:
        print(f"  Direct IM4P parse failed: {e}")
        # Try to find IM4P inside IMG4 wrapper
        im4p_marker = b'IM4P'
        pos = data.find(im4p_marker)
        if pos > 0:
            # Backtrack to find the SEQUENCE start
            # The SEQUENCE containing IM4P string starts a few bytes before
            for start in range(max(0, pos-6), pos):
                if data[start] == 0x30:
                    try:
                        result = parse_im4p(data[start:])
                        print(f"  Found IM4P at offset {start}")
                        break
                    except:
                        continue
            else:
                raise ValueError("Could not parse IM4P")
        else:
            raise ValueError("IM4P marker not found")
    
    print(f"  Type:        {result['type']!r}")
    print(f"  FourCC:      {result['fourcc']!r}")
    print(f"  Description: {result['description']!r}")
    
    if result['payload'] is None:
        print("  ERROR: No payload found")
        return False
    
    payload = result['payload']
    print(f"  Payload:     {len(payload):,} bytes")
    
    if result['has_keybag']:
        print(f"  KEYBAG:      PRESENT ({result['keybag_size']} bytes) — PAYLOAD IS ENCRYPTED")
        print(f"  NOTE: DeviceTree is typically encrypted in IMG4.")
        print(f"        Without firmware keys, we cannot decrypt it.")
        print(f"        Keys are Apple-internal for T8006/watchOS 10.x.")
        return False
    else:
        print(f"  Encryption:  NONE — raw payload")
    
    # For DeviceTree (fourcc='dtre'), payload is raw ADT binary
    if result['fourcc'] == 'dtre':
        # Validate: first 8 bytes should be ADT root header (prop_count, child_count)
        if len(payload) >= 8:
            prop_count, child_count = struct.unpack_from('<II', payload, 0)
            print(f"  ADT root: prop_count={prop_count}, child_count={child_count}")
            if prop_count > 0 and prop_count < 256:
                print(f"  ADT validation: OK ✓")
            else:
                print(f"  ADT validation: suspicious prop_count={prop_count}")
    
    with open(output_path, 'wb') as f:
        f.write(payload)
    
    print(f"  Payload saved: {output_path}")
    return True

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file.im4p> [output]")
        sys.exit(1)
    
    im4p_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else im4p_path.replace('.im4p', '.raw')
    
    success = extract_im4p_payload(im4p_path, output_path)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import re

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

print("=== SERIAL CONSOLE STRINGS ===")
matches = re.findall(rb'[^\x00\r\n]{0,30}serial_putc[^\x00\r\n]{0,30}', data)
for m in sorted(set(matches)):
    print(" ", m.decode('ascii', errors='replace'))

matches2 = re.findall(rb'[^\x00\r\n]{0,30}uart[0-9]?[^\x00\r\n]{0,30}', data, re.IGNORECASE)
found = set()
for m in matches2:
    s = m.decode('ascii', errors='replace').strip()
    if any(k in s.lower() for k in ['samsung', 'console', 'baud', 'putc', 'getc', 'init', 's3c', 'fifo']):
        found.add(s)
for s in sorted(found)[:30]:
    print(" ", s)

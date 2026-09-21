#!/usr/bin/env python3
"""
Research AIC2 in kernelcache.macho.
Find functions referencing 0x2d180000 or AIC strings.
"""
import re
import struct

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

print("=== SEARCHING FOR AIC STRINGS ===")
matches = re.findall(rb'[^\x00\r\n]{0,30}aic[^\x00\r\n]{0,30}', data, re.IGNORECASE)
found = set()
for m in matches:
    s = m.decode('ascii', errors='replace').strip()
    if any(k in s.lower() for k in ['apple', 'controller', 'interrupt', 'dispatch', 'mask', 'ack', 'eoi']):
        found.add(s)
for s in sorted(found)[:30]:
    print(" ", s)

print("\n=== SEARCHING FOR AIC KEXTS ===")
matches2 = re.findall(rb'com\.apple\.[A-Za-z0-9_\.]*aic[A-Za-z0-9_\.]*', data, re.IGNORECASE)
for m in sorted(set(matches2)):
    print(" ", m.decode('ascii', errors='replace'))

print("\n=== SEARCHING FOR AppleInterruptController / AppleARMInterruptController ===")
matches3 = re.findall(rb'Apple[A-Za-z0-9_]*Interrupt[A-Za-z0-9_]*', data)
for m in sorted(set(matches3)):
    print(" ", m.decode('ascii', errors='replace'))

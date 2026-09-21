#!/usr/bin/env python3
"""
Inspect kernelcache for UART driver and register accesses.
"""
import re

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

print("=== UART MATCHES IN KERNELCACHE ===")
matches = re.findall(rb'Apple[A-Za-z0-9_]*UART[A-Za-z0-9_]*', data)
for m in sorted(set(matches)):
    print(" ", m.decode('ascii', errors='replace'))

print("\n=== uart-1 MATCHES ===")
matches2 = re.findall(rb'[^\x00\r\n]{0,30}uart-1[^\x00\r\n]{0,30}', data)
for m in sorted(set(matches2)):
    print(" ", m.decode('ascii', errors='replace'))

print("\n=== S3C / SAMSUNG MATCHES ===")
matches3 = re.findall(rb'[^\x00\r\n]{0,20}s3c[^\x00\r\n]{0,20}', data, re.IGNORECASE)
for m in sorted(set(matches3))[:20]:
    print(" ", m.decode('ascii', errors='replace'))

#!/usr/bin/env python3
"""
Find PE_init_platform and related functions in kernelcache.
Search for how XNU accesses /chosen/memory-map and boot_args->Video.
"""
import re

with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

terms = [b'PE_init_platform', b'memory-map', b'/chosen', b'Boot_Video', b'v_baseAddr', b'v_rowBytes', b'video_console']
for t in terms:
    pos = 0
    matches = []
    while True:
        idx = data.find(t, pos)
        if idx == -1 or len(matches) > 5:
            break
        matches.append(idx)
        pos = idx + len(t)
    print(f"Term '{t.decode()}': found {len(matches)} matches")
    for m in matches[:3]:
        print(f"  at 0x{m:x}: {data[m-10:m+40]!r}")

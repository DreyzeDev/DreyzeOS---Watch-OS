#!/usr/bin/env python3
"""
Inspect boot_args structure in XNU on ARM64.
In XNU arm64 (osfmk/arm64/boot.h):
typedef struct boot_args {
    uint16_t    Revision;       /* 0x00 */
    uint16_t    Version;        /* 0x02 */
    uint32_t    virtBase;       /* 0x04 or 64-bit depending on version */
    uint64_t    physBase;       /* 0x08 */
    uint64_t    memSize;        /* 0x10 */
    uint64_t    topOfKernelData;/* 0x18 */
    boot_video  Video;          /* Video console parameters */
    uint32_t    machineType;    /* Machine Type */
    void        *deviceTreeP;   /* Virtual/Physical address of DeviceTree */
    uint32_t    deviceTreeLength;/* Length of DeviceTree */
    char        CommandLine[BOOT_LINE_LENGTH]; /* 0xsomething */
} boot_args;

Let's check the offsets in XNU kernelcache!
"""
import struct

# Let's search strings in kernelcache for "deviceTreeP" or "boot_args" or "Video"
with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    data = f.read()

import re
matches = [m.start() for m in re.finditer(b'deviceTreeP|deviceTreeLength|boot_args', data)]
print(f"Found {len(matches)} string matches:")
for m in matches[:10]:
    s = data[m:m+60].split(b'\x00')[0]
    print(f"  0x{m:x}: {s}")

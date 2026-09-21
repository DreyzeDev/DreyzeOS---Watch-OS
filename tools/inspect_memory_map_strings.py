with open('research/ipsw/21U580/kernelcache.macho', 'rb') as f:
    f.seek(0x94700)
    chunk = f.read(600)
print(chunk.split(b'\x00'))

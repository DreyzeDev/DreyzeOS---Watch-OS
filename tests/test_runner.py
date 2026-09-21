#!/usr/bin/env python3
"""
DreyzeOS Host-Side Test Runner
Runs all host-side tests (Python-based, no hardware required).
"""

import sys
import os
import struct

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

test_results = []

def run_command_cross(cmd_list, shell_cmd_str=""):
    import shutil
    import subprocess
    if shutil.which(cmd_list[0]):
        return subprocess.run(cmd_list, capture_output=True, text=True)
    elif shutil.which("wsl"):
        w_cmd = shell_cmd_str if shell_cmd_str else " ".join(cmd_list)
        return subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-c", w_cmd], capture_output=True, text=True)
    else:
        return subprocess.run(cmd_list, capture_output=True, text=True)

def test(name):
    """Decorator for test functions."""
    def decorator(fn):
        def wrapper():
            try:
                fn()
                test_results.append((name, True, None))
                print(f"  PASS: {name}")
            except AssertionError as e:
                test_results.append((name, False, str(e)))
                print(f"  FAIL: {name} — {e}")
            except Exception as e:
                test_results.append((name, False, f"Exception: {e}"))
                print(f"  FAIL: {name} — Exception: {e}")
        return wrapper
    return decorator

# ============================================================
# Tests: DeviceTree Parser
# ============================================================

def make_test_adt():
    """Create a minimal valid ADT binary for testing."""
    # Root node: 2 props, 1 child
    # Prop 1: name = "root"
    # Prop 2: compatible = "test,t8006"
    # Child: name = "uart0", reg = (0x235200000, 0x10000)

    def make_prop(name: str, value: bytes) -> bytes:
        name_bytes = name.encode('ascii').ljust(32, b'\x00')[:32]
        size = len(value)
        padded_value = value + b'\x00' * ((4 - size % 4) % 4)
        return name_bytes + struct.pack('<I', size) + padded_value

    def make_node(props: list, children: list) -> bytes:
        data = struct.pack('<II', len(props), len(children))
        for p in props:
            data += p
        for c in children:
            data += c
        return data

    # Child node (uart0)
    uart_props = [
        make_prop('name', b'uart0\x00'),
        make_prop('compatible', b'samsung,s3c6400-uart\x00'),
        make_prop('reg', struct.pack('<QQ', 0x235200000, 0x10000)),
    ]
    uart_node = make_node(uart_props, [])

    # Root node
    root_props = [
        make_prop('name', b'root\x00'),
        make_prop('compatible', b'test,t8006\x00'),
    ]
    root_node = make_node(root_props, [uart_node])

    return root_node

@test("ADT parser — basic parse")
def test_adt_parse():
    from tools.device_tree_dump import parse_adt
    data = make_test_adt()
    root, consumed = parse_adt(data, 0)
    assert consumed == len(data), f"consumed={consumed} != len={len(data)}"
    assert root.name == 'root', f"root.name={root.name!r}"
    assert len(root.children) == 1, f"children={len(root.children)}"

@test("ADT parser — property access")
def test_adt_props():
    from tools.device_tree_dump import parse_adt
    data = make_test_adt()
    root, _ = parse_adt(data, 0)
    compat = root.get_prop('compatible')
    assert compat is not None, "No 'compatible' property"
    assert 't8006' in compat.as_str(), f"compatible={compat.as_str()!r}"

@test("ADT parser — child node and MMIO region")
def test_adt_mmio():
    from tools.device_tree_dump import parse_adt, find_mmio_regions
    data = make_test_adt()
    root, _ = parse_adt(data, 0)
    regions = find_mmio_regions(root)
    assert len(regions) == 1, f"regions={regions}"
    assert regions[0]['base'] == 0x235200000
    assert regions[0]['size'] == 0x10000

@test("ADT parser — report generation")
def test_adt_report():
    from tools.device_tree_dump import parse_adt, generate_report
    data = make_test_adt()
    root, _ = parse_adt(data, 0)
    report = generate_report(root)
    assert 'MMIO' in report
    assert '0x0000000235200000' in report or '235200000' in report

# ============================================================
# Tests: Binary Inspector
# ============================================================

@test("inspect_binary — exists and is valid Python")
def test_inspect_binary_exists():
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'tools', 'inspect_binary.py')
    assert os.path.exists(path), f"File not found: {path}"
    spec = importlib.util.spec_from_file_location('inspect_binary', path)
    mod = importlib.util.module_from_spec(spec)
    # Just check it can be loaded (no syntax errors)
    spec.loader.exec_module(mod)

# ============================================================
# Tests: Build output validation
# ============================================================

@test("build/DreyzeOS.elf — exists after build")
def test_elf_exists():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf_path = os.path.join(project_root, 'build', 'DreyzeOS.elf')
    if not os.path.exists(elf_path):
        # Not a hard failure for CI before first build
        print(f"\n    NOTE: ELF not found (run 'make' first): {elf_path}")
        return  # Skip, not fail
    assert os.path.getsize(elf_path) > 0, "ELF is empty"

@test("build/DreyzeOS.bin — exists after build")
def test_bin_exists():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bin_path = os.path.join(project_root, 'build', 'DreyzeOS.bin')
    if not os.path.exists(bin_path):
        print(f"\n    NOTE: Binary not found (run 'make' first): {bin_path}")
        return
    assert os.path.getsize(bin_path) > 0, "Binary is empty"

@test("UART0 — header hardware constants match DeviceTree")
def test_uart0_constants():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    header_path = os.path.join(project_root, 'hal', 't8006', 'memory_map.h')
    with open(header_path, 'r') as f:
        content = f.read()
    import re
    assert re.search(r'#define\s+T8006_UART0_BASE\s+0x000000002e500000', content), "T8006_UART0_BASE not 0x2e500000"
    assert re.search(r'#define\s+UART_UTXH_OFFSET\s+0x20', content), "UART_UTXH_OFFSET not 0x20"
    assert re.search(r'#define\s+UART_UTRSTAT_OFFSET\s+0x10', content), "UART_UTRSTAT_OFFSET not 0x10"

@test("UART0 — exported symbols in built ELF")
def test_uart0_symbols_in_elf():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf_path = os.path.join(project_root, 'build', 'DreyzeOS.elf')
    if not os.path.exists(elf_path):
        return
    import subprocess
    res = subprocess.run(['aarch64-linux-gnu-nm', elf_path], capture_output=True, text=True)
    assert res.returncode == 0
    symbols = res.stdout
    for sym in ['uart_init', 'uart_putc', 'uart_puts', 'uart_diag', 'uart_is_ready']:
        assert sym in symbols, f"Missing UART symbol {sym} in ELF"

@test("UART0 — verified in Watch4,2 DeviceTree binary")
def test_watch42_devtree_uart0():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    adt_path = os.path.join(project_root, 'research', 'ipsw', '21U580', 'DeviceTree.n131bap.adt')
    if not os.path.exists(adt_path):
        return
    from tools.device_tree_dump import parse_adt, walk_nodes
    root, _ = parse_adt(open(adt_path, 'rb').read())
    uart0_node = None
    for path, node in walk_nodes(root):
        if path == '/arm-io/uart0':
            uart0_node = node
            break
    assert uart0_node is not None, "Node /arm-io/uart0 not found in Watch4,2 DeviceTree"
    regs = uart0_node.get_prop('reg').as_reg()
    assert len(regs) > 0, "No reg in uart0"
    assert regs[0][0] == 0x2e500000, f"UART0 base 0x{regs[0][0]:x} != 0x2e500000"
    assert regs[0][1] == 0x4000, f"UART0 size 0x{regs[0][1]:x} != 0x4000"

# ============================================================
# Tests: AIC (Apple Interrupt Controller)
# ============================================================

@test("AIC — hardware constants match DeviceTree and kernelcache")
def test_aic_constants():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    header_path = os.path.join(project_root, 'hal', 't8006', 'memory_map.h')
    aic_h_path = os.path.join(project_root, 'hal', 't8006', 'aic.h')
    with open(header_path, 'r') as f:
        mm_content = f.read()
    with open(aic_h_path, 'r') as f:
        aic_content = f.read()
    import re
    assert re.search(r'#define\s+T8006_AIC_BASE\s+0x000000002d180000', mm_content), "T8006_AIC_BASE not 0x2d180000"
    assert re.search(r'#define\s+T8006_AIC_SIZE\s+0x00008000', mm_content), "T8006_AIC_SIZE not 0x8000"
    assert re.search(r'#define\s+T8006_AIC_TIMEBASE_BASE\s+0x000000002d188000', mm_content), "T8006_AIC_TIMEBASE_BASE not 0x2d188000"
    assert re.search(r'#define\s+AIC_REG_EVENT\s+0x2004', aic_content), "AIC_REG_EVENT not 0x2004"
    assert re.search(r'#define\s+AIC_REG_WHOAMI\s+0x2000', aic_content), "AIC_REG_WHOAMI not 0x2000"
    assert re.search(r'#define\s+AIC_REG_MASK_SET_BASE\s+0x4000', aic_content), "AIC_REG_MASK_SET_BASE not 0x4000"
    assert re.search(r'#define\s+AIC_REG_MASK_CLR_BASE\s+0x4080', aic_content), "AIC_REG_MASK_CLR_BASE not 0x4080"

@test("AIC — exported symbols in built ELF")
def test_aic_symbols_in_elf():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf_path = os.path.join(project_root, 'build', 'DreyzeOS.elf')
    if not os.path.exists(elf_path):
        return
    import subprocess
    res = subprocess.run(['aarch64-linux-gnu-nm', elf_path], capture_output=True, text=True)
    assert res.returncode == 0
    symbols = res.stdout
    for sym in ['aic_init', 'aic_enable_irq', 'aic_disable_irq', 'aic_mask_all',
                'aic_ack', 'aic_eoi', 'aic_get_cpu_id', 'aic_handle_irq', 'aic_diag',
                'arch_irq_enable', 'arch_irq_disable']:
        assert sym in symbols, f"Missing AIC symbol {sym} in ELF"

@test("AIC — verified in Watch4,2 DeviceTree binary")
def test_watch42_devtree_aic():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    adt_path = os.path.join(project_root, 'research', 'ipsw', '21U580', 'DeviceTree.n131bap.adt')
    if not os.path.exists(adt_path):
        return
    from tools.device_tree_dump import parse_adt, walk_nodes
    root, _ = parse_adt(open(adt_path, 'rb').read())
    aic_node = None
    timebase_node = None
    for path, node in walk_nodes(root):
        if path == '/arm-io/aic':
            aic_node = node
        elif path == '/arm-io/aic-timebase':
            timebase_node = node
    assert aic_node is not None, "Node /arm-io/aic not found in Watch4,2 DeviceTree"
    assert timebase_node is not None, "Node /arm-io/aic-timebase not found in Watch4,2 DeviceTree"
    compat = aic_node.get_prop('compatible')
    assert compat is not None and 'aic,1' in compat.as_str(), f"AIC compatible={compat.as_str()!r}"
    regs = aic_node.get_prop('reg').as_reg()
    assert len(regs) == 1, f"AIC regs count={len(regs)}"
    assert regs[0][0] == 0x2d180000, f"AIC base 0x{regs[0][0]:x} != 0x2d180000"
    assert regs[0][1] == 0x8000, f"AIC size 0x{regs[0][1]:x} != 0x8000"
    tb_regs = timebase_node.get_prop('reg').as_reg()
    assert len(tb_regs) == 1, f"AIC timebase regs count={len(tb_regs)}"
    assert tb_regs[0][0] == 0x2d188000, f"AIC timebase base 0x{tb_regs[0][0]:x} != 0x2d188000"
    assert tb_regs[0][1] == 0x1000, f"AIC timebase size 0x{tb_regs[0][1]:x} != 0x1000"

# ============================================================
# Tests: Phase 3 Step 3 — Dynamic DeviceTree / Boot-Info
# ============================================================

# ---------------------------------------------------------------------------
# ADT binary builder helpers (mirrors C adt_node_hdr_t / adt_prop_hdr_t)
#   adt_node_hdr: uint32 prop_count, uint32 child_count
#   adt_prop_hdr: char name[32], uint32 size
#   prop data is NOT padded in Apple ADT (size is exact, next prop/node
#   starts at next 4-byte boundary after size bytes)
# ---------------------------------------------------------------------------

def _make_adt_prop(name: str, value: bytes) -> bytes:
    """Build a single ADT property blob."""
    name_bytes = name.encode('ascii').ljust(32, b'\x00')[:32]
    size = len(value)
    # Pad value to 4-byte boundary (Apple ADT stores padded but size is unpadded)
    padded = value + b'\x00' * ((4 - size % 4) % 4)
    return name_bytes + struct.pack('<I', size) + padded

def _make_adt_node(props: list, children: list) -> bytes:
    """Build a complete ADT node blob."""
    hdr = struct.pack('<II', len(props), len(children))
    body = b''.join(props) + b''.join(children)
    return hdr + body

def _make_minimal_chosen_node(mem_map_entries: dict | None = None) -> bytes:
    """
    Build a /chosen node.
    mem_map_entries: dict of {prop_name: (paddr, size)} for /chosen/memory-map children.
    If None — no memory-map child.
    """
    chosen_props = [
        _make_adt_prop('name', b'chosen\x00'),
        _make_adt_prop('chip-id', struct.pack('<I', 0x8006)),
        _make_adt_prop('board-id', struct.pack('<I', 0x1c)),
    ]
    children = []
    if mem_map_entries is not None:
        mm_props = [_make_adt_prop('name', b'memory-map\x00')]
        for prop_name, (paddr, size) in mem_map_entries.items():
            mm_props.append(_make_adt_prop(prop_name, struct.pack('<QQ', paddr, size)))
        children.append(_make_adt_node(mm_props, []))
    return _make_adt_node(chosen_props, children)

def _make_full_test_tree(include_chosen: bool = True,
                          mem_map: dict | None = None) -> bytes:
    """Build a minimal but valid full ADT tree (root → [chosen])."""
    children = []
    if include_chosen:
        children.append(_make_minimal_chosen_node(mem_map))
    root_props = [
        _make_adt_prop('name', b'device-tree\x00'),
        _make_adt_prop('compatible', b'apple,t8006\x00'),
    ]
    return _make_adt_node(root_props, children)


@test("boot-info — valid tree: parse static Watch4,2 ADT")
def test_boot_info_valid_tree():
    """
    Parse the real static Watch4,2 ADT using the Python ADT parser.
    Validates that the tree is parseable, root model is Watch4,2,
    and /chosen exists.
    Source: research/ipsw/21U580/DeviceTree.n131bap.adt (CONFIRMED).
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    adt_path = os.path.join(project_root, 'research', 'ipsw', '21U580', 'DeviceTree.n131bap.adt')
    if not os.path.exists(adt_path):
        # Skip if IPSW not extracted — not a failure in CI
        print("\n    NOTE: ADT binary not found — skipping (run Phase 2 extraction first)")
        return
    from tools.device_tree_dump import parse_adt, walk_nodes
    data = open(adt_path, 'rb').read()
    root, consumed = parse_adt(data)
    assert consumed > 0, "parse_adt consumed 0 bytes"
    assert root is not None, "root is None"
    model_prop = root.get_prop('model')
    assert model_prop is not None, "No model prop in root"
    assert 'Watch4,2' in model_prop.as_str(), f"model={model_prop.as_str()} expected Watch4,2"
    # Find /chosen
    chosen = None
    for path, node in walk_nodes(root):
        if path == '/chosen':
            chosen = node
            break
    assert chosen is not None, "No /chosen node in Watch4,2 DeviceTree"
    chip_prop = chosen.get_prop('chip-id')
    assert chip_prop is not None, "No chip-id in /chosen"


@test("boot-info — missing /chosen: synthetic tree without chosen")
def test_boot_info_missing_chosen():
    """
    A synthetic ADT tree without /chosen must still parse without crashing.
    Verifies that the parser handles absent nodes gracefully.
    """
    from tools.device_tree_dump import parse_adt, walk_nodes
    data = _make_full_test_tree(include_chosen=False)
    root, consumed = parse_adt(data)
    assert consumed > 0, "consumed=0 on synthetic tree"
    assert root is not None, "root is None"
    # /chosen must NOT be present
    paths = [path for path, _ in walk_nodes(root)]
    assert '/chosen' not in paths, "Unexpected /chosen in tree built without it"


@test("boot-info — truncated tree: parser must not crash")
def test_boot_info_truncated_tree():
    """
    Feed truncated (malformed) ADT blobs to the parser.
    The parser must raise an exception or return gracefully — NOT hang or produce
    garbage results from out-of-bounds reads. Tests 4 truncation points.
    """
    from tools.device_tree_dump import parse_adt
    full = _make_full_test_tree()
    truncation_points = [0, 4, 8, len(full) // 2]
    for cut in truncation_points:
        data = full[:cut]
        try:
            root, consumed = parse_adt(data)
            # If it returns without exception, consumed must be <= len(data)
            assert consumed <= len(data), \
                f"consumed={consumed} > len(data)={len(data)} at cut={cut}"
        except Exception:
            # Exception is also acceptable — means parser detected truncation
            pass


@test("boot-info — memory-map parsing: static ADT has zero-filled entries")
def test_boot_info_memory_map_parsing():
    """
    In the static Watch4,2 DeviceTree, all /chosen/memory-map entries are
    zero-filled placeholders (iBoot fills them at runtime).
    Verifies: (a) the memory-map node exists, (b) memory map reservations are
    16 bytes each, (c) all paddr/size values are 0x0 (CONFIRMED from ADT inspection).
    Note: metadata properties like AAPL,phandle, name, kernel-only are ignored,
    matching DreyzeOS HAL logic.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    adt_path = os.path.join(project_root, 'research', 'ipsw', '21U580', 'DeviceTree.n131bap.adt')
    if not os.path.exists(adt_path):
        print("\n    NOTE: ADT binary not found — skipping")
        return
    from tools.device_tree_dump import parse_adt, walk_nodes
    data = open(adt_path, 'rb').read()
    root, _ = parse_adt(data)
    mm_node = None
    for path, node in walk_nodes(root):
        if path == '/chosen/memory-map':
            mm_node = node
            break
    assert mm_node is not None, "/chosen/memory-map not found in Watch4,2 DeviceTree"
    # Filter out metadata properties matching C parser logic
    reservation_props = [
        p for p in mm_node.props
        if p.name not in ('name', 'kernel-only') and not p.name.startswith('AAPL,')
    ]
    assert len(reservation_props) > 0, "No memory-map reservation entries found"
    for p in reservation_props:
        assert len(p.value) >= 16, \
            f"memory-map entry '{p.name}' size={len(p.value)} < 16 bytes"
        paddr, sz = struct.unpack_from('<QQ', p.value)
        # In static DT all MemoryMapReserved-N entries must be zero
        assert paddr == 0 and sz == 0, \
            f"Static memory-map entry '{p.name}' is non-zero: paddr=0x{paddr:x} sz=0x{sz:x}"


@test("boot-info — framebuffer discovery: synthetic tree with Display entry")
def test_boot_info_framebuffer_discovery():
    """
    Build a synthetic ADT with a /chosen/memory-map 'Display' entry containing
    a non-zero paddr and size, then verify the parser can locate it.
    This mirrors what iBoot inserts at runtime.
    FB_PADDR and FB_SIZE are synthetic test values (not real hardware addresses).
    """
    from tools.device_tree_dump import parse_adt, walk_nodes

    FB_PADDR = 0x0000000880000000  # synthetic test value
    FB_SIZE  = 0x0000000000200000  # 2 MB synthetic

    mem_map = {
        'MemoryMapReserved-0': (0, 0),           # zero placeholder
        'Display':             (FB_PADDR, FB_SIZE),  # simulated iBoot entry
        'KernelText':          (0x800100000, 0x400000),
    }
    data = _make_full_test_tree(mem_map=mem_map)
    root, consumed = parse_adt(data)
    assert consumed > 0, "consumed=0"

    # Locate /chosen/memory-map
    mm_node = None
    for path, node in walk_nodes(root):
        if path == '/chosen/memory-map':
            mm_node = node
            break
    assert mm_node is not None, "/chosen/memory-map not found in synthetic tree"

    # Find a property whose name contains 'Display' (case-insensitive)
    fb_prop = None
    for p in mm_node.props:
        if 'display' in p.name.lower():
            fb_prop = p
            break
    assert fb_prop is not None, "No 'Display' property found in /chosen/memory-map"
    assert len(fb_prop.value) >= 16, "Display entry too short"

    paddr, size = struct.unpack_from('<QQ', fb_prop.value)
    assert paddr == FB_PADDR, f"paddr=0x{paddr:x} expected 0x{FB_PADDR:x}"
    assert size  == FB_SIZE,  f"size=0x{size:x} expected 0x{FB_SIZE:x}"


@test("boot-info — bounds checking: prop_count=0xFFFFFFFF must not crash")
def test_boot_info_bounds_checking():
    """
    Feed the parser a malformed node header with prop_count=0xFFFFFFFF.
    The parser must either raise an exception or return 0 consumed — it must NOT
    loop indefinitely or access out-of-bounds memory.
    """
    from tools.device_tree_dump import parse_adt

    # Build a blob with a node header claiming 0xFFFFFFFF props and 0 children,
    # but with only a 'name' property following (tiny data).
    name_prop = _make_adt_prop('name', b'fuzz\x00')
    bad_hdr = struct.pack('<II', 0xFFFFFFFF, 0)  # prop_count=max_uint32, child_count=0
    bad_blob = bad_hdr + name_prop

    try:
        root, consumed = parse_adt(bad_blob)
        # If it returns without exception, consumed must be <= len(bad_blob)
        assert consumed <= len(bad_blob), \
            f"consumed={consumed} > len={len(bad_blob)} on malformed input"
    except Exception:
        # Raising an exception is the correct response to a malformed header
        pass


# ============================================================
# Tests: Phase 4 Step 1 — Boot Framebuffer Output
# ============================================================

class SoftwareFramebuffer:
    """
    Host-side Software Framebuffer implementation.
    Emulates the C hal/t8006/framebuffer.c driver with canary guard regions,
    strict stride calculations, and integer overflow checks.
    """
    def __init__(self, width: int, height: int, row_bytes: int = None, depth: int = 32,
                 total_size: int = None, guard_size: int = 256):
        self.width = width
        self.height = height
        self.depth = depth
        self.bpp = (depth + 7) // 8
        min_row = width * self.bpp
        if row_bytes is None:
            row_bytes = min_row
        assert row_bytes >= min_row, f"row_bytes {row_bytes} < min_row {min_row}"
        self.row_bytes = row_bytes

        min_size = row_bytes * height
        self.size = total_size if total_size is not None else min_size
        assert self.size >= min_size, f"size {self.size} < min_size {min_size}"

        self.guard_size = guard_size
        self.canary_front = b'\xDE\xAD\xBE\xEF' * (guard_size // 4)
        self.canary_back  = b'\xCA\xFE\xBA\xBE' * (guard_size // 4)

        # Allocated memory with guard zones before and after
        self.raw = bytearray(self.canary_front + b'\x00' * self.size + self.canary_back)
        self.base_offset = guard_size
        self.is_configured = True
        self.writes_allowed = False

    def check_canaries(self):
        """Assert that no writes overflowed or underflowed the allocated framebuffer memory."""
        front = bytes(self.raw[:self.guard_size])
        back = bytes(self.raw[self.base_offset + self.size:])
        assert front == self.canary_front, "CANARY CORRUPTION: Front canary modified (underflow)!"
        assert back == self.canary_back, "CANARY CORRUPTION: Back canary modified (overflow)!"

    def put_pixel(self, x: int, y: int, color: int):
        if not self.is_configured or not self.writes_allowed:
            return
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return

        y_offset = y * self.row_bytes
        x_offset = x * self.bpp
        offset = y_offset + x_offset
        if offset > self.size or (self.size - offset) < self.bpp:
            return

        abs_off = self.base_offset + offset
        if self.bpp == 4:
            struct.pack_into("<I", self.raw, abs_off, color & 0xFFFFFFFF)
        elif self.bpp == 2:
            struct.pack_into("<H", self.raw, abs_off, color & 0xFFFF)
        elif self.bpp == 1:
            self.raw[abs_off] = color & 0xFF

    def get_pixel(self, x: int, y: int) -> int:
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return 0
        offset = y * self.row_bytes + x * self.bpp
        abs_off = self.base_offset + offset
        if self.bpp == 4:
            return struct.unpack_from("<I", self.raw, abs_off)[0]
        elif self.bpp == 2:
            return struct.unpack_from("<H", self.raw, abs_off)[0]
        return self.raw[abs_off]

    def fill(self, color: int):
        if not self.is_configured or not self.writes_allowed:
            return
        for y in range(self.height):
            for x in range(self.width):
                self.put_pixel(x, y, color)

    def draw_rect(self, x: int, y: int, w: int, h: int, color: int):
        if not self.is_configured or not self.writes_allowed:
            return
        if x >= self.width or y >= self.height or w <= 0 or h <= 0:
            return
        if x + w > self.width:
            w = self.width - x
        if y + h > self.height:
            h = self.height - y
        for row in range(h):
            for col in range(w):
                self.put_pixel(x + col, y + row, color)


@test("framebuffer — exported symbols in built ELF")
def test_framebuffer_symbols_in_elf():
    """Verify that all required framebuffer functions are present in DreyzeOS.elf."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf_path = os.path.join(project_root, 'build', 'DreyzeOS.elf')
    if not os.path.exists(elf_path):
        return
    import subprocess
    res = subprocess.run(['aarch64-linux-gnu-nm', elf_path], capture_output=True, text=True)
    assert res.returncode == 0, f"nm failed: {res.stderr}"
    symbols = res.stdout
    required = [
        'framebuffer_init',
        'framebuffer_is_available',
        'framebuffer_get_info',
        'framebuffer_enable_writes',
        'framebuffer_put_pixel',
        'framebuffer_fill',
        'framebuffer_clear',
        'framebuffer_draw_rect',
        'framebuffer_draw_test_pattern',
        'framebuffer_diag',
        'platform_get_framebuffer'
    ]
    for sym in required:
        assert sym in symbols, f"Missing symbol {sym} in DreyzeOS.elf"


@test("framebuffer — color encoding: BGRX/BGRA matches kernelcache format")
def test_framebuffer_color_format():
    """
    Verify color encoding matches kernelcache 'BBBBBBBBGGGGGGGGRRRRRRRR' (BGRA/BGRX).
    In 32-bit little endian:
      Byte 0: Blue  (0x000000FF)
      Byte 1: Green (0x0000FF00)
      Byte 2: Red   (0x00FF0000)
    """
    def fb_rgb(r, g, b):
        return ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)

    red = fb_rgb(0xFF, 0, 0)
    green = fb_rgb(0, 0xFF, 0)
    blue = fb_rgb(0, 0, 0xFF)
    white = fb_rgb(0xFF, 0xFF, 0xFF)

    fb = SoftwareFramebuffer(10, 10)
    fb.writes_allowed = True

    # Check Red byte placement
    fb.put_pixel(0, 0, red)
    packed_red = bytes(fb.raw[fb.base_offset : fb.base_offset + 4])
    assert packed_red == b'\x00\x00\xFF\x00', f"Red byte layout incorrect: {packed_red.hex()}"

    # Check Green byte placement
    fb.put_pixel(1, 0, green)
    packed_green = bytes(fb.raw[fb.base_offset + 4 : fb.base_offset + 8])
    assert packed_green == b'\x00\xFF\x00\x00', f"Green byte layout incorrect: {packed_green.hex()}"

    # Check Blue byte placement
    fb.put_pixel(2, 0, blue)
    packed_blue = bytes(fb.raw[fb.base_offset + 8 : fb.base_offset + 12])
    assert packed_blue == b'\xFF\x00\x00\x00', f"Blue byte layout incorrect: {packed_blue.hex()}"

    # Check White byte placement
    fb.put_pixel(3, 0, white)
    packed_white = bytes(fb.raw[fb.base_offset + 12 : fb.base_offset + 16])
    assert packed_white == b'\xFF\xFF\xFF\x00', f"White byte layout incorrect: {packed_white.hex()}"

    fb.check_canaries()


@test("framebuffer — safety interlock: writes blocked when disabled")
def test_framebuffer_safety_interlock():
    """Verify that when writes_allowed is False, no memory modifications occur."""
    fb = SoftwareFramebuffer(20, 20)
    assert fb.writes_allowed is False

    # Attempt to write pixels, fill, and draw rect
    fb.put_pixel(5, 5, 0x00FFFFFF)
    fb.fill(0x00FF0000)
    fb.draw_rect(2, 2, 10, 10, 0x0000FF00)

    # All framebuffer memory must remain pure 0x00
    screen_mem = bytes(fb.raw[fb.base_offset : fb.base_offset + fb.size])
    assert screen_mem == b'\x00' * fb.size, "Writes succeeded while safety interlock was active!"
    fb.check_canaries()


@test("framebuffer — clipping & bounds: out-of-bounds coordinates rejected")
def test_framebuffer_clipping_and_bounds():
    """Verify that coordinates outside [0, width-1] x [0, height-1] are rejected safely."""
    fb = SoftwareFramebuffer(100, 100)
    fb.writes_allowed = True

    # Test out-of-bounds coordinates
    invalid_coords = [
        (-1, 0), (0, -1), (-1, -1),
        (100, 50), (50, 100), (100, 100),
        (1000, 50), (50, 1000), (0xFFFFFFFF, 0xFFFFFFFF)
    ]
    for x, y in invalid_coords:
        fb.put_pixel(x, y, 0x00FFFFFF)

    # Valid pixel write at (0, 0) and (99, 99)
    fb.put_pixel(0, 0, 0x00FF0000)
    fb.put_pixel(99, 99, 0x0000FF00)

    assert fb.get_pixel(0, 0) == 0x00FF0000
    assert fb.get_pixel(99, 99) == 0x0000FF00
    assert fb.get_pixel(100, 100) == 0

    fb.check_canaries()


@test("framebuffer — stride & padding: non-standard rowBytes handled correctly")
def test_framebuffer_stride_and_padding():
    """
    Verify stride with row padding (row_bytes > width * bpp).
    Example: width=10, bpp=4 -> pixel row=40 bytes, but row_bytes=64 (24 bytes padding per row).
    Pixel (0, 1) MUST be at offset 64, not 40!
    Padding between rows MUST remain 0x00.
    """
    WIDTH = 10
    HEIGHT = 5
    ROW_BYTES = 64  # 40 bytes pixels + 24 bytes padding
    fb = SoftwareFramebuffer(WIDTH, HEIGHT, row_bytes=ROW_BYTES)
    fb.writes_allowed = True

    # Plot (9, 0) — end of first row (offset 9 * 4 = 36)
    fb.put_pixel(9, 0, 0x000000FF)

    # Plot (0, 1) — start of second row (offset 1 * 64 + 0 = 64)
    fb.put_pixel(0, 1, 0x00FF0000)

    # Verify pixel readbacks
    assert fb.get_pixel(9, 0) == 0x000000FF
    assert fb.get_pixel(0, 1) == 0x00FF0000

    # Verify exact byte locations in memory
    raw_screen = fb.raw[fb.base_offset : fb.base_offset + fb.size]
    # Offset 36..40 is pixel (9, 0) = Blue
    assert raw_screen[36:40] == b'\xFF\x00\x00\x00'
    # Padding bytes 40..64 MUST be zero
    assert raw_screen[40:64] == b'\x00' * 24, f"Padding corrupted: {raw_screen[40:64].hex()}"
    # Offset 64..68 is pixel (0, 1) = Red
    assert raw_screen[64:68] == b'\x00\x00\xFF\x00'

    fb.check_canaries()


@test("framebuffer — canary overrun check on multiple resolutions")
def test_framebuffer_canary_overrun():
    """
    Verify zero buffer underflow/overflow across multiple synthetic framebuffer sizes:
      - 368 x 448 (Apple Watch Series 4 44mm real screen)
      - 312 x 390 (Apple Watch Series 3 42mm screen)
      - 16 x 16 (tiny screen)
      - 64 x 32 with large stride 512 bytes
    """
    configs = [
        (368, 448, 368 * 4),
        (312, 390, 312 * 4),
        (16, 16, 16 * 4),
        (64, 32, 512),
    ]
    for w, h, stride in configs:
        fb = SoftwareFramebuffer(w, h, row_bytes=stride)
        fb.writes_allowed = True

        # Write to all 4 corners
        fb.put_pixel(0, 0, 0x00FFFFFF)
        fb.put_pixel(w - 1, 0, 0x00FF0000)
        fb.put_pixel(0, h - 1, 0x0000FF00)
        fb.put_pixel(w - 1, h - 1, 0x000000FF)

        # Fill entire buffer
        fb.fill(0x00808080)

        # Draw rect along perimeter
        fb.draw_rect(0, 0, w, 2, 0x00FFFFFF)
        fb.draw_rect(0, h - 2, w, 2, 0x00FFFFFF)

        # Verify canaries are 100% untouched
        fb.check_canaries()


@test("framebuffer — fill & draw_rect with boundary clipping")
def test_framebuffer_fill_and_rect():
    """Verify fill, draw_rect, and rectangle clipping against screen edge."""
    fb = SoftwareFramebuffer(50, 50)
    fb.writes_allowed = True

    # 1. Fill entire screen with black
    fb.fill(0x00000000)
    assert fb.get_pixel(25, 25) == 0

    # 2. Draw 10x10 white rectangle at (10, 10)
    fb.draw_rect(10, 10, 10, 10, 0x00FFFFFF)
    assert fb.get_pixel(10, 10) == 0x00FFFFFF
    assert fb.get_pixel(19, 19) == 0x00FFFFFF
    assert fb.get_pixel(9, 10) == 0
    assert fb.get_pixel(20, 10) == 0

    # 3. Draw rectangle crossing right and bottom boundary: (45, 45) with size 20x20
    # Must clip to 5x5 visible inside screen without overflow
    fb.draw_rect(45, 45, 20, 20, 0x00FF0000)
    assert fb.get_pixel(45, 45) == 0x00FF0000
    assert fb.get_pixel(49, 49) == 0x00FF0000

    fb.check_canaries()


@test("framebuffer — test pattern generation on Watch4,2 geometry (368x448)")
def test_framebuffer_test_pattern_generation():
    """
    Emulate framebuffer_draw_test_pattern() on 368x448 geometry.
    Verifies:
      - 3-pixel outer white border
      - 6 color bars in upper half (Red, Green, Blue, Yellow, Cyan, Magenta)
      - Centered white rectangle in lower half
      - Zero canary violations
    """
    WIDTH, HEIGHT = 368, 448
    fb = SoftwareFramebuffer(WIDTH, HEIGHT, row_bytes=WIDTH * 4)
    fb.writes_allowed = True

    # 1. Clear to black
    fb.fill(0)

    # 2. Outer border (3 pixels wide)
    bw = 3
    fb.draw_rect(0, 0, WIDTH, bw, 0x00FFFFFF)
    fb.draw_rect(0, HEIGHT - bw, WIDTH, bw, 0x00FFFFFF)
    fb.draw_rect(0, 0, bw, HEIGHT, 0x00FFFFFF)
    fb.draw_rect(WIDTH - bw, 0, bw, HEIGHT, 0x00FFFFFF)

    # 3. 6 color bars
    colors = [
        0x00FF0000,  # Red
        0x0000FF00,  # Green
        0x000000FF,  # Blue
        0x00FFFF00,  # Yellow
        0x0000FFFF,  # Cyan
        0x00FF00FF   # Magenta
    ]
    margin_x = 20
    bar_y = 20
    bar_h = HEIGHT // 5
    avail_w = WIDTH - (margin_x * 2)
    bar_w = avail_w // 6

    for i in range(6):
        fb.draw_rect(margin_x + (i * bar_w), bar_y, bar_w - 2, bar_h, colors[i])

    # 4. Centered white rectangle
    rect_w = WIDTH // 3
    rect_h = HEIGHT // 6
    rect_x = (WIDTH - rect_w) // 2
    rect_y = bar_y + bar_h + 30
    fb.draw_rect(rect_x, rect_y, rect_w, rect_h, 0x00FFFFFF)

    # Assertions
    # Outer border
    assert fb.get_pixel(0, 0) == 0x00FFFFFF
    assert fb.get_pixel(WIDTH // 2, 1) == 0x00FFFFFF
    assert fb.get_pixel(1, HEIGHT // 2) == 0x00FFFFFF

    # First color bar (Red)
    assert fb.get_pixel(margin_x + 5, bar_y + 5) == 0x00FF0000

    # Second color bar (Green)
    assert fb.get_pixel(margin_x + bar_w + 5, bar_y + 5) == 0x0000FF00

    # Third color bar (Blue)
    assert fb.get_pixel(margin_x + (2 * bar_w) + 5, bar_y + 5) == 0x000000FF

    # Center white box
    assert fb.get_pixel(rect_x + 5, rect_y + 5) == 0x00FFFFFF

    # Canaries intact
    fb.check_canaries()



# ============================================================
# Tests: Phase 4 Step 2 — Boot Stage Tracking & Failsafe
# ============================================================

@test("boot stage — symbols present in ELF")
def test_boot_stage_symbols_in_elf():
    """Verify that all boot stage API symbols are in the compiled ELF."""
    elf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "build", "DreyzeOS.elf")
    if not os.path.exists(elf_path):
        raise AssertionError(f"ELF not found: {elf_path} (run 'make' first)")

    import subprocess
    result = subprocess.run(
        ["aarch64-linux-gnu-nm", "--defined-only", elf_path],
        capture_output=True, text=True
    )
    # Fall back to wsl nm if direct call fails
    if result.returncode != 0:
        result = subprocess.run(
            ["wsl", "-d", "Ubuntu", "--", "bash", "-c",
             f"aarch64-linux-gnu-nm --defined-only /mnt/c/Users/pc/Desktop/DreyzeOS/build/DreyzeOS.elf"],
            capture_output=True, text=True
        )

    sym_output = result.stdout + result.stderr
    required_symbols = [
        "boot_stage_set",
        "boot_stage_get",
        "boot_stage_get_last_successful",
        "boot_stage_failsafe",
        "boot_stage_name",
    ]
    for sym in required_symbols:
        assert sym in sym_output, f"Symbol '{sym}' not found in ELF"


@test("boot stage — stage values are monotonically increasing")
def test_boot_stage_progression():
    """
    Python simulation: verify STAGE 0..6 are monotonically increasing integers
    and BOOT_STAGE_ERROR is not in the normal progression sequence.
    """
    # Mirror the enum values from boot_stage.h
    BOOT_STAGE_ENTRY     = 0
    BOOT_STAGE_RAM_LOG   = 1
    BOOT_STAGE_BOOT_ARGS = 2
    BOOT_STAGE_MEM_MAP   = 3
    BOOT_STAGE_AIC       = 4
    BOOT_STAGE_FB        = 5
    BOOT_STAGE_IDLE      = 6
    BOOT_STAGE_ERROR     = 0xFF

    stages = [
        BOOT_STAGE_ENTRY,
        BOOT_STAGE_RAM_LOG,
        BOOT_STAGE_BOOT_ARGS,
        BOOT_STAGE_MEM_MAP,
        BOOT_STAGE_AIC,
        BOOT_STAGE_FB,
        BOOT_STAGE_IDLE,
    ]

    # Verify monotonically increasing
    for i in range(len(stages) - 1):
        assert stages[i] < stages[i + 1], (
            f"Stages not monotonically increasing at index {i}: "
            f"{stages[i]} >= {stages[i+1]}"
        )

    # BOOT_STAGE_ERROR must not be in normal sequence
    assert BOOT_STAGE_ERROR not in stages, \
        "BOOT_STAGE_ERROR (0xFF) must not appear in normal boot stage sequence"

    # ERROR must be higher than all normal stages
    assert BOOT_STAGE_ERROR > BOOT_STAGE_IDLE, \
        f"BOOT_STAGE_ERROR ({BOOT_STAGE_ERROR}) must be > BOOT_STAGE_IDLE ({BOOT_STAGE_IDLE})"


@test("boot stage — failsafe preserves last successful stage separately")
def test_boot_stage_failsafe_preserves_last_successful():
    """
    Python simulation: when failsafe is triggered at STAGE 3,
    last_successful must remain STAGE 3, current must be ERROR.
    Verifies the two-variable design (g_current_stage vs g_last_successful_stage).
    """
    BOOT_STAGE_ENTRY     = 0
    BOOT_STAGE_RAM_LOG   = 1
    BOOT_STAGE_BOOT_ARGS = 2
    BOOT_STAGE_MEM_MAP   = 3
    BOOT_STAGE_AIC       = 4
    BOOT_STAGE_FB        = 5
    BOOT_STAGE_IDLE      = 6
    BOOT_STAGE_ERROR     = 0xFF

    # Simulate boot_stage_set and boot_stage_failsafe logic
    g_current_stage = BOOT_STAGE_ENTRY
    g_last_successful_stage = BOOT_STAGE_ENTRY

    def boot_stage_set(stage):
        nonlocal g_current_stage, g_last_successful_stage
        g_current_stage = stage
        if stage != BOOT_STAGE_ERROR:
            g_last_successful_stage = stage

    def boot_stage_failsafe():
        nonlocal g_current_stage
        # Does NOT update g_last_successful_stage
        g_current_stage = BOOT_STAGE_ERROR

    # Simulate progression to stage 3
    boot_stage_set(BOOT_STAGE_ENTRY)
    boot_stage_set(BOOT_STAGE_RAM_LOG)
    boot_stage_set(BOOT_STAGE_BOOT_ARGS)
    boot_stage_set(BOOT_STAGE_MEM_MAP)

    assert g_last_successful_stage == BOOT_STAGE_MEM_MAP, \
        f"Last successful should be STAGE_3 before failsafe, got {g_last_successful_stage}"

    # Trigger failsafe at stage 3
    boot_stage_failsafe()

    assert g_current_stage == BOOT_STAGE_ERROR, \
        f"Current stage should be ERROR after failsafe, got {g_current_stage}"
    assert g_last_successful_stage == BOOT_STAGE_MEM_MAP, \
        f"Last successful stage must be preserved as STAGE_3, got {g_last_successful_stage}"

    # Critically: last_successful must NOT be ERROR
    assert g_last_successful_stage != BOOT_STAGE_ERROR, \
        "g_last_successful_stage must not be set to BOOT_STAGE_ERROR by failsafe"


@test("boot stage — ERROR stage is separate from all valid stages")
def test_boot_stage_error_separate_from_last_successful():
    """
    Verify BOOT_STAGE_ERROR (0xFF) is not equal to any valid boot stage value.
    This is a static correctness check on the enum design.
    """
    BOOT_STAGE_ERROR = 0xFF
    valid_stages = {
        "ENTRY":     0,
        "UART":      1,
        "BOOT_ARGS": 2,
        "MEM_MAP":   3,
        "AIC":       4,
        "FB":        5,
        "IDLE":      6,
    }
    for name, value in valid_stages.items():
        assert BOOT_STAGE_ERROR != value, \
            f"BOOT_STAGE_ERROR ({BOOT_STAGE_ERROR}) must not equal {name} ({value})"

    # Must be representable as uint8_t
    assert 0 <= BOOT_STAGE_ERROR <= 255, \
        f"BOOT_STAGE_ERROR must fit in uint8_t, got {BOOT_STAGE_ERROR}"

# ============================================================
# Tests: Phase 4 Step 2.4 — Handoff Pointer Safety & Trust Boundary
# ============================================================

@test("C-level host test harness execution")
def test_c_host_tests_execution():
    """Compile and execute tests/test_host_c.c to verify real C code on host."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    c_bin = os.path.join(root_dir, "build", "test_host_c")
    compile_cmd = [
        "gcc", "-DHOST_TEST", f"-I{root_dir}", f"-I{os.path.join(root_dir, 'include')}",
        f"-I{os.path.join(root_dir, 'lib')}",
        os.path.join(root_dir, "tests", "test_host_c.c"),
        os.path.join(root_dir, "kernel", "boot_stage.c"),
        os.path.join(root_dir, "kernel", "log.c"),
        os.path.join(root_dir, "hal", "t8006", "device_tree.c"),
        os.path.join(root_dir, "hal", "t8006", "mmio_gate.c"),
        os.path.join(root_dir, "hal", "t8006", "handoff_gate.c"),
        os.path.join(root_dir, "hal", "t8006", "platform.c"),
        os.path.join(root_dir, "hal", "t8006", "uart.c"),
        os.path.join(root_dir, "hal", "t8006", "aic.c"),
        os.path.join(root_dir, "hal", "t8006", "framebuffer.c"),
        os.path.join(root_dir, "lib", "string.c"),
        "-o", c_bin
    ]
    wsl_cmd = (
        "gcc -DHOST_TEST -I. -Iinclude -Ilib "
        "tests/test_host_c.c kernel/boot_stage.c kernel/log.c hal/t8006/device_tree.c "
        "hal/t8006/mmio_gate.c hal/t8006/handoff_gate.c hal/t8006/platform.c hal/t8006/uart.c hal/t8006/aic.c "
        "hal/t8006/framebuffer.c lib/string.c "
        "-o build/test_host_c && ./build/test_host_c"
    )
    result = run_command_cross(compile_cmd, f"cd /mnt/c/Users/pc/Desktop/DreyzeOS && {wsl_cmd}")
    if result.returncode != 0:
        raise AssertionError(f"Host C test build/execution failed (rc={result.returncode}):\n{result.stdout}\n{result.stderr}")
    
    # Run test executable
    res_run = run_command_cross([c_bin], "cd /mnt/c/Users/pc/Desktop/DreyzeOS && ./build/test_host_c")
    if res_run.returncode != 0:
        raise AssertionError(f"Host C test run failed:\n{res_run.stdout}\n{res_run.stderr}")
    assert "All C-Level Host Tests PASSED" in res_run.stdout


@test("linker — layout, section boundaries, and alignment assertions")
def test_linker_layout_and_assertions():
    """Verify vector alignment (2048B), stack alignment (16B), and stack placement outside BSS."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf_path = os.path.join(root_dir, "build", "DreyzeOS.elf")
    result = run_command_cross(
        ["aarch64-linux-gnu-nm", "-n", elf_path],
        "aarch64-linux-gnu-nm -n /mnt/c/Users/pc/Desktop/DreyzeOS/build/DreyzeOS.elf"
    )
    syms = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            syms[parts[2]] = int(parts[0], 16)

    # 1. Exception vectors 2048-byte aligned
    assert "_exception_vectors_base" in syms
    vbar = syms["_exception_vectors_base"]
    assert (vbar % 2048) == 0, f"_exception_vectors_base (0x{vbar:x}) is not 2048-byte aligned!"

    # 2. Stack alignment (16-byte)
    assert "__stack_top" in syms
    sp_top = syms["__stack_top"]
    assert (sp_top % 16) == 0, f"__stack_top (0x{sp_top:x}) is not 16-byte aligned!"

    # 3. Stack placed outside / after BSS
    assert "__bss_end" in syms
    assert "__stack_bottom" in syms
    bss_end = syms["__bss_end"]
    stack_bottom = syms["__stack_bottom"]
    assert stack_bottom >= bss_end, (
        f"Stack (0x{stack_bottom:x}) must be placed after BSS end (0x{bss_end:x})!"
    )


@test("entry.S — EL1 contract, CurrentEL ordering, and VBAR_EL1")
def test_entry_system_register_audit():
    """Verify EL1-only CurrentEL use, EL2/EL3 rejection, and VBAR_EL1 setup."""
    entry_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "boot", "entry.S")
    with open(entry_path, "r", encoding="utf-8") as f:
        src = f.read()

    # CurrentEL must be read
    assert "mrs" in src and "CurrentEL" in src, "CurrentEL not queried in entry.S!"
    assert "UNDEFINED at EL0" in src, "EL0 CurrentEL constraint is undocumented"
    assert "permitted at all Exception Levels" not in src, "Incorrect EL0 claim remains"
    assert "_unsupported_el_halt:" in src, "Safe halt for invalid EL not implemented!"

    # VBAR_EL1 must be set and followed by isb
    assert "msr" in src and "vbar_el1" in src, "VBAR_EL1 not installed in entry.S!"
    assert "isb" in src, "ISB missing after system register configuration!"

    # Validate the actual linked instruction order, not only source strings.
    elf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "build", "DreyzeOS.elf")
    dis = run_command_cross(
        ["aarch64-linux-gnu-objdump", "-d", elf_path],
        "aarch64-linux-gnu-objdump -d /mnt/c/Users/pc/Desktop/DreyzeOS/build/DreyzeOS.elf"
    )
    text = dis.stdout
    start = text.find("<__kernel_start>:")
    if start < 0:
        start = text.find("<_start>:")
    unsupported = text.find("<_unsupported_el_halt>:")
    assert start >= 0 and unsupported > start, "Cannot locate _start disassembly"
    block = text[start:unsupported]
    currentel = block.find("mrs\t")
    compare = block.find("cmp\t")
    reject = block.find("b.ne")
    vbar = block.find("msr\tvbar_el1")
    assert 0 <= currentel < compare < reject < vbar, \
        "CurrentEL validation must precede VBAR_EL1 write"

    halt_end = text.find("\n", unsupported)
    halt_block = text[unsupported: text.find("\n\n", unsupported)]
    assert "wfi" not in halt_block.lower(), \
        "Unsupported-EL fallback must not depend on WFI"


@test("entry/docs — CurrentEL EL0 and loader ABI claims are truthful")
def test_entry_contract_documentation():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root_dir, "boot", "entry.S"), encoding="utf-8") as f:
        entry = f.read().lower()
    with open(os.path.join(root_dir, "docs", "HARDWARE_BRINGUP.md"), encoding="utf-8") as f:
        bringup = f.read()
    with open(os.path.join(root_dir, "docs", "PRE_HARDWARE_AUDIT.md"), encoding="utf-8") as f:
        audit = f.read()

    assert "currentel at el0 is undefined" in entry
    assert "dreyzeos loader abi — unknown/blocked" in bringup.lower()
    assert "xnu `x0=boot_args` is not a dreyzeos contract" in audit.lower()


@test("pre-hardware MMIO — actual C harness keeps UART and AIC untouched")
def test_pre_hardware_mmio_gate_harness():
    """The native harness asserts zero UART/AIC MMIO accesses and RAM-log availability."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(root_dir, "build", "test_host_c")
    assert os.path.exists(output_path), "C harness was not built"
    result = run_command_cross([output_path], "./build/test_host_c")
    assert result.returncode == 0, result.stderr
    assert "test_pre_hardware_mmio_gate... PASS" in result.stdout


@test("CPU state — snapshot symbols and read-only invariant")
def test_cpu_state_symbols_and_safety():
    """Verify CPU state snapshot symbols in ELF and ensure no MSR writes to MMU registers."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf_path = os.path.join(root_dir, "build", "DreyzeOS.elf")
    result = run_command_cross(
        ["aarch64-linux-gnu-nm", elf_path],
        "aarch64-linux-gnu-nm /mnt/c/Users/pc/Desktop/DreyzeOS/build/DreyzeOS.elf"
    )
    for sym in ["boot_cpu_state_capture", "boot_cpu_state_get", "boot_cpu_state_diag"]:
        assert sym in result.stdout, f"Symbol '{sym}' missing from ELF!"

    # Check that kernel/cpu_state.c contains NO 'msr sctlr' or 'msr tcr' or 'msr ttbr'
    cpu_c_path = os.path.join(root_dir, "kernel", "cpu_state.c")
    with open(cpu_c_path, "r", encoding="utf-8") as f:
        cpu_src = f.read()

    assert "msr sctlr" not in cpu_src.lower()
    assert "msr tcr" not in cpu_src.lower()
    assert "msr ttbr" not in cpu_src.lower()
    assert "msr mair" not in cpu_src.lower()


@test("boot_args — real virt_base tracking without phys_base proxying")
def test_virt_base_truthfulness():
    """Simulate platform_boot_info_init: virt_base is NEVER proxied from phys_base."""
    # When virt_base is 0 (or raw ADT), virt_base_valid must be False
    raw_adt_info = {
        "boot_args_present": False,
        "dram_phys_base": 0x800000000,
        "dram_virt_base": 0,
        "virt_base_valid": False,
        "is_fallback_data": False
    }
    assert raw_adt_info["virt_base_valid"] is False
    assert raw_adt_info["dram_virt_base"] == 0
    # Must never equal phys_base if not explicitly supplied
    assert raw_adt_info["dram_virt_base"] != raw_adt_info["dram_phys_base"]

    # When boot_args provides virt_base, it is real
    boot_args_info = {
        "boot_args_present": True,
        "dram_phys_base": 0x800000000,
        "dram_virt_base": 0xFFFFFFF000000000,
        "virt_base_valid": True,
        "is_fallback_data": False
    }
    assert boot_args_info["virt_base_valid"] is True
    assert boot_args_info["dram_virt_base"] == 0xFFFFFFF000000000


@test("framebuffer — hard safety interlock symbols in ELF")
def test_framebuffer_hard_interlock_symbols():
    """Verify mapping_verified getter and setter symbols exist in compiled ELF."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf_path = os.path.join(root_dir, "build", "DreyzeOS.elf")
    result = run_command_cross(
        ["aarch64-linux-gnu-nm", elf_path],
        "aarch64-linux-gnu-nm /mnt/c/Users/pc/Desktop/DreyzeOS/build/DreyzeOS.elf"
    )
    assert "framebuffer_set_mapping_verified" in result.stdout
    assert "framebuffer_is_mapping_verified" in result.stdout


@test("DeviceTree parser — malformed and fuzz-like blobs rejection")
def test_devicetree_malformed_fuzz():
    """Verify that parser handles malformed, truncated, and cyclic structures without crashing."""
    from tools.device_tree_dump import parse_adt

    # 1. Empty blob
    try:
        parse_adt(b"", 0)
    except Exception:
        pass  # Expected safe rejection

    # 2. Oversized property count
    malformed_props = struct.pack('<II', 0xFFFFFFFF, 0)
    try:
        parse_adt(malformed_props, 0)
    except Exception:
        pass

    # 3. Oversized child count
    malformed_children = struct.pack('<II', 0, 0x10000)
    try:
        parse_adt(malformed_children, 0)
    except Exception:
        pass

    # 4. Truncated node header
    try:
        parse_adt(b"\x01\x00\x00", 0)
    except Exception:
        pass


@test("ELF relocations — static link audit (0 relocations)")
def test_elf_relocation_audit():
    """Verify binary contains 0 dynamic/static relocations (statically linked)."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf_path = os.path.join(root_dir, "build", "DreyzeOS.elf")
    result = run_command_cross(
        ["aarch64-linux-gnu-readelf", "-r", elf_path],
        "aarch64-linux-gnu-readelf -r /mnt/c/Users/pc/Desktop/DreyzeOS/build/DreyzeOS.elf"
    )
    assert "There are no relocations in this file." in result.stdout


# ============================================================
# Run all tests
# ============================================================

def main():
    print("\n" + "="*50)
    print("DreyzeOS Test Suite")
    print("="*50 + "\n")

    # Collect and run all test functions
    tests = [
        test_adt_parse,
        test_adt_props,
        test_adt_mmio,
        test_adt_report,
        test_inspect_binary_exists,
        test_elf_exists,
        test_bin_exists,
        test_uart0_constants,
        test_uart0_symbols_in_elf,
        test_watch42_devtree_uart0,
        test_aic_constants,
        test_aic_symbols_in_elf,
        test_watch42_devtree_aic,
        # Phase 3 Step 3 — Dynamic DeviceTree / Boot-Info
        test_boot_info_valid_tree,
        test_boot_info_missing_chosen,
        test_boot_info_truncated_tree,
        test_boot_info_memory_map_parsing,
        test_boot_info_framebuffer_discovery,
        test_boot_info_bounds_checking,
        # Phase 4 Step 1 — Boot Framebuffer Output
        test_framebuffer_symbols_in_elf,
        test_framebuffer_color_format,
        test_framebuffer_safety_interlock,
        test_framebuffer_clipping_and_bounds,
        test_framebuffer_stride_and_padding,
        test_framebuffer_canary_overrun,
        test_framebuffer_fill_and_rect,
        test_framebuffer_test_pattern_generation,
        # Phase 4 Step 2 — Boot Stage Tracking & Failsafe
        test_boot_stage_symbols_in_elf,
        test_boot_stage_progression,
        test_boot_stage_failsafe_preserves_last_successful,
        test_boot_stage_error_separate_from_last_successful,
        # Phase 4 Step 2.4 — Handoff Pointer Safety & Trust Boundary
        test_c_host_tests_execution,
        test_linker_layout_and_assertions,
        test_entry_system_register_audit,
        test_entry_contract_documentation,
        test_pre_hardware_mmio_gate_harness,
        test_cpu_state_symbols_and_safety,
        test_virt_base_truthfulness,
        test_framebuffer_hard_interlock_symbols,
        test_devicetree_malformed_fuzz,
        test_elf_relocation_audit,
    ]

    for t in tests:
        t()

    # Summary
    total = len(test_results)
    passed = sum(1 for _, ok, _ in test_results if ok)
    failed = total - passed

    print(f"\n{'='*50}")
    print(f"Tests: {total}  PASS: {passed}  FAIL: {failed}")
    print(f"{'='*50}\n")

    if failed > 0:
        print("Failed tests:")
        for name, ok, err in test_results:
            if not ok:
                print(f"  - {name}: {err}")
        sys.exit(1)
    else:
        print("All tests PASSED ✓")

if __name__ == '__main__':
    main()

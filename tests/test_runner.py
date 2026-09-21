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

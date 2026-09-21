import sys
sys.path.insert(0, '.')
from tools.device_tree_dump import parse_adt, walk_nodes

root, _ = parse_adt(open('research/ipsw/21U580/DeviceTree.n131bap.adt', 'rb').read())
for path, node in walk_nodes(root):
    if 'aic' in path:
        print('Node:', path)
        for p in node.props:
            print(f'  prop: {p.name}, size: {len(p.value)}, as_str: {p.as_str()!r}')
            if p.name == 'reg':
                print(f'    reg: {p.as_reg()}')

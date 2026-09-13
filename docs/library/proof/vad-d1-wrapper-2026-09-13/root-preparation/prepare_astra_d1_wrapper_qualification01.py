"""Prepare an independent copy of reviewed inert wrapper inputs; no execution."""
import hashlib
import json
from pathlib import Path

root = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
source = root / '_scratch/vad-d1-dormant-invocation-repair01'
dest = root / '_scratch/astra-d1-wrapper-qualification01'
assert not dest.exists()
pins = {
    'before/run-root.ps1': '75b8058874a0389ccdd02f63815b1430b543967e5ad232904bbb86b7a0073a23',
    'run-root.repaired.ps1': '11b56a5686d972c4ed212de21f2f2a23b0062da616a762701bda3434831cdb63',
    'inert_child.py': '9ef273a19f466e07d73c1cb7e2d895256045813ed49e2dd2315176e3dbc7f07f',
    'call_wrapper.ps1': '3165e20b0b8f836f37fac7175a3433adfbf0e740952e091dd389f02e32d5c1df',
    'qualify_wrapper.ps1': '4aa3bc369618da8b668e68a13122673ff2fb70c32ecd183d3e2aa32ecf80e104',
    'run_preflight01.ps1': 'd2aa72b5f661b3102c77284e3e69034e28e69e8eb48cb2dc832b43ecfbb81afe',
    'QUALIFICATION01-PROTOCOL.md': 'af5457794acfe5e4b04f1ea9a355877d88857e59285f9aae276c2c5a3fbca99c',
}
names = tuple(pins) + ('REPAIR-BRIEF-2026-09-13.md', 'SOURCE-REVIEW-VERDICT.md',
    'PREQUALIFICATION-OUTCOME-REFINEMENT.md', 'ORIGINAL-BINDINGS.json', 'wrapper-repair.patch.txt')
raws = {name: (source / name).read_bytes() for name in names}
for name, pin in pins.items():
    assert hashlib.sha256(raws[name]).hexdigest() == pin, name
dest.mkdir()
copies = []
for name, original in raws.items():
    raw = original
    if name == 'run_preflight01.ps1':
        before = str(source).encode()
        after = str(dest).encode()
        assert raw.count(before) == 1
        raw = raw.replace(before, after)
    target = dest / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as output:
        output.write(raw)
    assert target.read_bytes() == raw and (source / name).read_bytes() == original
    copies.append({'name': name, 'source_sha256': hashlib.sha256(original).hexdigest(),
                   'copy_sha256': hashlib.sha256(raw).hexdigest(),
                   'only_change': 'fixed root proposal path' if name == 'run_preflight01.ps1' else None})
(dest / 'COPY-BINDINGS.json').write_text(json.dumps(copies, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'prepared_files': len(copies), 'dest': str(dest),
                  'root_launcher_sha256': hashlib.sha256((dest / 'run_preflight01.ps1').read_bytes()).hexdigest(),
                  'execution_performed': False}))

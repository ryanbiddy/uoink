"""Prepare new B3 launch source from successful B2 text; no runtime/wheel access."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path

out = Path(__file__).absolute().parent
scratch = out.parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
bindings = []
def write(name, raw):
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
def copy(source, name, expected):
    raw = source.read_bytes()
    assert len(raw) < 1024 * 1024 and sha(raw) == expected
    write(name, raw)
    bindings.append({'source': str(source), 'target': name, 'bytes': len(raw), 'sha256': sha(raw)})
    return raw
b3 = scratch / 'companion-b3-builder01'
b3seal = copy(b3 / 'SHA256.json', 'prior-seals/B3-56-SHA256.json', '07e4ac3373142058da95b97568b9a8542b8c42942f8e8f877f00fabc7f97c142')
rows = {row['file']: row for row in json.loads(b3seal)['payloads']}
for name in ['build_faster_whisper_localassets_wheel.py', 'recipe/B2.py.txt', 'recipe/NOTICE.txt', 'recipe/patch.txt', 'recipe/member-manifest.json', 'recipe/utils.py.txt']:
    copy(b3 / name, 'inputs/' + name, rows[name]['sha256'])
size = rows['build_faster_whisper_localassets_wheel.py']['bytes']
assert size == 16660

old314 = scratch / 'b2-real-wheel-preparation01'
old313 = scratch / 'b2-python313-reproduction-preparation01'
base314 = copy(old314 / 'build-guarded.py', 'prior-protocols/build-guarded314.py.txt', '3becaed597aa15f3b2fc5d5cc816aaf172d89cfa4165aed92d18e47fb56ccc73').decode()
base313 = copy(old313 / 'build-guarded313.py', 'prior-protocols/build-guarded313.py.txt', '616295bae49ab05844a57e88ad1b47cc5b612cb9094e275c1aabcedd991a788a').decode()
baseouter = copy(old313 / 'copy-and-launch.py', 'prior-protocols/copy-and-launch.py.txt', '6fcf3a4476b3b4517b227bf213a875c88831aa5a03e7435704362b8bca36ed26').decode()
copy(old313 / 'runtime-copy-plan.json', 'runtime-copy-plan.json', '8b676299c1e60414231ffefcf62bd00705c6f24d633a9aa23e91a1829b618b0b')
copy(old314 / 'SHA256.json', 'prior-seals/B2-first-preparation21-SHA256.json', 'ebab6c9180c7c8f230e55b619d1cc469d7043f1a43e197a3a8abd126f7eb7484')
copy(old313 / 'SHA256.json', 'prior-seals/B2-private313-preparation28-SHA256.json', '0b1cb98b296f34965d8bcebe8a67755bb5315df1a3663b479e282da630346f4c')
changes = []
for label, before in [('314', base314), ('313', base313)]:
    after = before
    def replace(left, right, reason):
        global after
        assert after.count(left) == 1, (label, reason, after.count(left))
        after = after.replace(left, right)
        changes.append({'child': label, 'reason': reason, 'before': left, 'after': right})
    replace('("b2-real-wheel-" + args.label)', '("b3-real-wheel-" + args.label)', 'Use fresh B3 run directories.')
    replace('bounded(source, 16354, 16354)', 'bounded(source, 16660, 16660)', 'Bind exact B3 utility size.')
    replace('ef7189180bc443f7b0b68386b8452d0b57b2be4beca3eee9d81409a7658b4c3f', 'f25530a3ee58169c049e63c2e6bfff444061f2c04c9a87ec2af43c8850b81892', 'Bind exact independently qualified B3 utility.')
    if label == '314':
        replace('reproducibility_python313="PENDING_PRIVATE_RUNTIME_REVIEW"', 'reproducibility_python313="PENDING_B3_REPRODUCTION"', 'Private runtime is already verified; B3 reproduction remains pending.')
    else:
        replace('parser.add_argument("--execute-reviewed-build", action="store_true", required=True)', '''parser.add_argument("--execute-reviewed-build", action="store_true", required=True)
parser.add_argument("--comparison-sha256", required=True)
parser.add_argument("--comparison-size", required=True, type=int)''', 'Require root-observed first B3 output identity.')
        replace('args = parser.parse_args()', '''args = parser.parse_args()
if len(args.comparison_sha256) != 64 or set(args.comparison_sha256) - set("0123456789abcdef") or not 1 <= args.comparison_size <= 5 * 1024 * 1024:
    raise ValueError("Exact bounded root-observed first output identity required")''', 'Validate comparison input before wheel access.')
        replace('b2-real-wheel-py314-01/artifact/faster_whisper-1.2.1+uoink.localassets1-py3-none-any.whl', 'b3-real-wheel-py314-01/artifact/faster_whisper-1.2.1+uoink.localassets2-py3-none-any.whl', 'Read only the new first B3 output for comparison.')
        replace('builder.read_regular_file(comparison, 1387859, 1387859)', 'builder.read_regular_file(comparison, args.comparison_size, args.comparison_size)', 'Use root-observed first output size without inventing it.')
        replace('builder.digest(reference) != "d64027be41a352117199ecedfa1e9eed48d323140aa4e2c77065111f288b7883"', 'builder.digest(reference) != args.comparison_sha256', 'Pin the first B3 identity after root measures it.')
    ast.parse(after)
    write('build-guarded' + label + '.py', after.encode())
    write('child' + label + '-B2-to-B3.patch.txt', ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='successful-B2/child' + label + '.py', tofile='proposed-B3/child' + label + '.py')).encode())

# Keep the exact reviewed path/hash/runtime validation helpers. Omit copy_runtime
# entirely; this new launcher has no runtime-copy action or source read loop.
parsed = ast.parse(baseouter)
selected = ['no_links', 'bounded', 'write_json', 'verify_preparation', 'plan', 'verify_runtime', 'fresh']
helpers = '\n\n'.join(ast.get_source_segment(baseouter, next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == name)) for name in selected)
header = '''"""Prepared B3 builds; reuse verified private runtime, never copy it."""
import sys
if tuple(sys.version_info[:3]) != (3, 14, 6) or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode) or "site" in sys.modules:
    raise RuntimeError("Requires reviewed Python 3.14.6 -I -S -B")
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import traceback
OUT = Path(__file__).absolute().parent
SCRATCH = OUT.parent
RUNTIME = SCRATCH / "b2-stdlib313-runtime01"
PLAN_HASH = "8b676299c1e60414231ffefcf62bd00705c6f24d633a9aa23e91a1829b618b0b"
PTH = b"python313.zip\\n.\\n"
CAP = 8 * 1024 * 1024
digest = lambda raw: hashlib.sha256(raw).hexdigest()

'''
launcher = header + helpers + '\n\n' + (out / 'launch-tail.py.txt').read_text(encoding='utf-8')
ast.parse(launcher)
write('launch.py', launcher.encode())
write('launcher-B2-to-B3.patch.txt', ''.join(difflib.unified_diff(baseouter.splitlines(True), launcher.splitlines(True), fromfile='successful-B2/copy-and-launch.py', tofile='proposed-B3/launch.py')).encode())
write('child-adaptation-reasons.json', (json.dumps(changes, indent=2)+'\n').encode())
for relative in ['b2-real-wheel-py313-01/build-result.json', 'b2-real-wheel-py313-01/launch-result.json', 'b2-stdlib313-copy01/copy-result.json']:
    source = scratch / relative
    raw = source.read_bytes()
    assert len(raw) < 256 * 1024
    copy(source, 'runtime-history/' + relative.replace('/', '--'), sha(raw))
write('INPUT-BINDINGS.json', (json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(), 'bindings': bindings,
    'private_runtime_reused_plan_only': True, 'actual_runtime_or_wheel_accessed': False,
    'B3_first_output_sha256': None, 'B3_first_output_built': False}, indent=2)+'\n').encode())
print(json.dumps({'builder': rows['build_faster_whisper_localassets_wheel.py']['sha256'], 'launcher_sha256': sha(launcher.encode()),
    'child314_sha256': sha((out / 'build-guarded314.py').read_bytes()), 'child313_sha256': sha((out / 'build-guarded313.py').read_bytes()),
    'actual_runtime_or_wheel_accessed': False}))

"""Build inert B3 text recipes and source proposals without any wheel access."""
import ast
import base64
import csv
from datetime import datetime, timezone
import difflib
import hashlib
import io
import json
from pathlib import Path

out = Path(__file__).absolute().parent
old = out.parent / 'companion-b2-builder01'
hub = out.parent / 'companion-hub-keyword-review01'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
bindings = []
def write(name, raw):
    target = out / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(raw)
def original(name, target=None):
    source = old / name
    raw = source.read_bytes()
    row = oldrows[name]
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    if target is not None:
        write(target, raw)
    bindings.append({'source': str(source), 'target': target, 'bytes': len(raw), 'sha256': sha(raw)})
    return raw
seal = (old / 'SHA256.json').read_bytes()
assert sha(seal) == 'ac31912d51a4a6b38c8e028e65bd005e9fedcd7125d51f219ca51973b834fc8f'
oldrows = {row['file']: row for row in json.loads(seal)['payloads']}
write('prior-seals/builder63-SHA256.json', seal)
hubseal = (hub / 'SHA256.json').read_bytes()
assert sha(hubseal) == 'b08fb56fe9d76ca3d289105c206cfbfd584b12f87608ddf285172b58b8c2fc33'
write('prior-seals/hub97-SHA256.json', hubseal)
for name in oldrows:
    if name.startswith('fixtures/upstream-text/'):
        original(name, name)
b2 = original('recipe/B2.py.txt', 'recipe/B2.py.txt')
assert sha(b2) == 'bf452635becacf6bba46825be6d6eea533da472ce966ee47f5ce7bccfc3bf06d'
utils = (hub / 'qualification/utils-after.py.txt').read_bytes()
assert len(utils) == 4897 and sha(utils) == 'ecec29ad34688e2d559218685672c3c2f1086f524d78bcfd53e633a5739d5b19'
write('recipe/utils.py.txt', utils)
bindings.append({'source': str(hub / 'qualification/utils-after.py.txt'), 'target': 'recipe/utils.py.txt', 'bytes': len(utils), 'sha256': sha(utils)})
patch = original('recipe/patch.txt') + (hub / 'qualification/patch.txt').read_bytes()
write('recipe/patch.txt', patch)
notice = f'''Uoink local derivative: faster-whisper 1.2.1+uoink.localassets2
Based on faster-whisper 1.2.1 by SYSTRAN; original MIT license retained.

Local changes:
1. Route supplied tokenizer buffers, including empty buffers, to the parser
   before considering ambient files. Prepare available tokenizer input before
   CTranslate2 construction and refuse missing local-only input. The explicit
   non-local fallback for absent tokenizer input is retained.
2. Remove the obsolete local_dir_use_symlinks keyword from download_model's
   optional output-directory call. Preserve its other forwarded arguments.
The local version identifies these modifications separately from upstream.

Patch SHA-256: {sha(patch)}
Source-level synthetic checks do not establish actual Hub I/O, native/model
compatibility, advisory clearance, speaker attribution, or release acceptance.
No upstream endorsement is claimed.
'''.encode()
write('recipe/NOTICE.txt', notice)

# Compute all proposed text members and RECORD from text/identity receipts only.
old_manifest = json.loads(original('recipe/member-manifest.json', 'prior-inputs/B2-member-manifest.json'))
old_dist = 'faster_whisper-1.2.1.dist-info'
new_dist = 'faster_whisper-1.2.1+uoink.localassets2.dist-info'
texts = {}
for path in (out / 'fixtures/upstream-text').rglob('*.txt'):
    name = path.relative_to(out / 'fixtures/upstream-text').as_posix()[:-4]
    if not name.endswith('/RECORD'):
        texts[name.replace(old_dist + '/', new_dist + '/', 1)] = path.read_bytes()
texts['faster_whisper/transcribe.py'] = b2
texts['faster_whisper/utils.py'] = utils
texts['faster_whisper/version.py'] = texts['faster_whisper/version.py'].replace(b'__version__ = "1.2.1"', b'__version__ = "1.2.1+uoink.localassets2"')
texts[new_dist + '/METADATA'] = texts[new_dist + '/METADATA'].replace(b'Version: 1.2.1\n', b'Version: 1.2.1+uoink.localassets2\n')
texts[new_dist + '/WHEEL'] = texts[new_dist + '/WHEEL'].replace(b'Generator: bdist_wheel (0.45.1)\n', b'Generator: uoink-localassets-wheel (1)\n')
texts[new_dist + '/UOINK-LOCALASSETS-NOTICE.txt'] = notice
asset = next(row for row in old_manifest['members'] if row['member'].endswith('.onnx'))
rows = []
for name, raw in sorted(texts.items()):
    rows.append({'member': name, 'bytes': len(raw), 'sha256': sha(raw), 'basis': 'Proposed B3 text; not packaged'})
rows.append({'member': asset['member'], 'bytes': asset['bytes'], 'sha256': asset['sha256'],
             'basis': 'Inherited recorded asset identity; no B3 asset read or build'})
record = io.StringIO(newline='')
writer = csv.writer(record, lineterminator='\n')
for row in sorted(rows, key=lambda row: row['member']):
    row['record_hash'] = 'sha256=' + base64.urlsafe_b64encode(bytes.fromhex(row['sha256'])).decode().rstrip('=')
    writer.writerow([row['member'], row['record_hash'], row['bytes']])
writer.writerow([new_dist + '/RECORD', '', ''])
record_bytes = record.getvalue().encode()
rows.sort(key=lambda row: row['member'])
rows.append({'member': new_dist + '/RECORD', 'bytes': len(record_bytes), 'sha256': sha(record_bytes),
             'record_hash': '', 'basis': 'Proposed B3 RECORD derived from member identities; not packaged'})
assert len(rows) == 16
write('proposed-text/RECORD.txt', record_bytes)
for name in ('version.py',):
    write('proposed-text/' + name + '.txt', texts['faster_whisper/' + name])
for name in ('METADATA', 'WHEEL', 'LICENSE'):
    write('proposed-text/' + name + '.txt', texts[new_dist + '/' + name])
manifest = {'status': 'PROPOSED_ONLY', 'distribution': 'faster-whisper', 'version': '1.2.1+uoink.localassets2',
    'filename': 'faster_whisper-1.2.1+uoink.localassets2-py3-none-any.whl', 'output_wheel_sha256': None,
    'output_wheel_built': False, 'member_count': 16, 'members': rows, 'zip': old_manifest['zip'],
    'proposal_revision': 'B3-tokenizer-and-Hub-keyword', 'source_sha256': sha(b2), 'utils_sha256': sha(utils),
    'aggregate_normalized_patch_sha256': sha(patch), 'original_B2_unchanged': True}
write('recipe/member-manifest.json', (json.dumps(manifest, indent=2)+'\n').encode())

before_builder = original('build_faster_whisper_localassets_wheel.py', 'prior-inputs/B2-builder.py.txt').decode()
builder = before_builder.replace('1.2.1+uoink.localassets1', '1.2.1+uoink.localassets2')
marker = 'INPUT_VERSION_SHA256 = "70ee45276562706d9787f105fb3010417fa9621fe6a9e2fad01a209f3044d9c5"\n'
assert builder.count(marker) == 1
builder = builder.replace(marker, marker + 'INPUT_UTILS_SHA256 = "5b36ceb9d0fd3961de8cfb144bd82f9a4ef3151b2e5958405a11efb4f3ac4f82"\n')
tree = ast.parse(builder)
changes = []
for name in ('RECIPE_HASHES', 'RECIPE_SIZES'):
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    old_text = ast.get_source_segment(builder, node)
    values = {path.name: sha(path.read_bytes()) if name == 'RECIPE_HASHES' else len(path.read_bytes()) for path in sorted((out / 'recipe').iterdir())}
    replacement = name + ' = ' + repr(values)
    changes.append((old_text, replacement))
for before, after in changes:
    assert builder.count(before) == 1
    builder = builder.replace(before, after)
old_check = 'if digest(members["faster_whisper/transcribe.py"]) != INPUT_SOURCE_SHA256 or digest(members["faster_whisper/version.py"]) != INPUT_VERSION_SHA256:'
assert builder.count(old_check) == 1
builder = builder.replace(old_check, old_check[:-1] + ' or digest(members["faster_whisper/utils.py"]) != INPUT_UTILS_SHA256:')
assignment = '    result["faster_whisper/transcribe.py"] = recipe["B2.py.txt"]\n'
assert builder.count(assignment) == 1
builder = builder.replace(assignment, assignment + '    result["faster_whisper/utils.py"] = recipe["utils.py.txt"]\n')
ast.parse(builder)
write('build_faster_whisper_localassets_wheel.py', builder.encode())
write('builder-B2-to-B3.patch.txt', ''.join(difflib.unified_diff(before_builder.splitlines(True), builder.splitlines(True), fromfile='B2/builder.py', tofile='B3/builder.py')).encode())

tests_before = original('tests-synthetic.py', 'prior-inputs/B2-tests.py.txt').decode()
tests = tests_before.replace('changed = {"faster_whisper/transcribe.py",', 'changed = {"faster_whisper/utils.py", "faster_whisper/transcribe.py",')
tests = tests.replace('1.2.1+uoink.localassets1', '1.2.1+uoink.localassets2')
write('tests-retained62.py.txt', tests.encode())
write('retained62-expectation.patch.txt', ''.join(difflib.unified_diff(tests_before.splitlines(True), tests.splitlines(True), fromfile='B2/tests.py', tofile='B3/retained62.py')).encode())
write('tests-synthetic.py', (tests + '\n' + (out / 'new-contracts.py.txt').read_text(encoding='utf-8')).encode())

runner_before = original('run-synthetic.py', 'prior-inputs/B2-run-synthetic.py.txt').decode()
runner = runner_before.replace('{"bw01", "bw02", "bw03"}', '{"b3w01"}')
runner = runner.replace('or "/_scratch/python313-graph-01/" in path or path.endswith(".onnx")):',
    'or "/_scratch/python313-graph-01/" in path or "/_scratch/b2-real-wheel-" in path\n                or "/_scratch/b2-stdlib313-" in path or path.endswith(".onnx")):')
write('run-synthetic.py', runner.encode())
write('guard-adaptation.patch.txt', ''.join(difflib.unified_diff(runner_before.splitlines(True), runner.splitlines(True), fromfile='B2/run-synthetic.py', tofile='B3/run-synthetic.py')).encode())
write('input-bindings.json', (json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(), 'bindings': bindings,
    'upstream_wheel_or_asset_accessed': False, 'builder_executed_during_preparation': False,
    'recipe_hashes': {p.name: sha(p.read_bytes()) for p in sorted((out / 'recipe').iterdir())}}, indent=2)+'\n').encode())
print(json.dumps({'builder_sha256': sha(builder.encode()), 'tests_sha256': sha((out / 'tests-synthetic.py').read_bytes()),
    'manifest_sha256': sha((out / 'recipe/member-manifest.json').read_bytes()), 'actual_wheel_or_model_accessed': False}))

import ast
import difflib
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
root = out.parents[1]
inputs = [
    ('utils-before.py.txt', '_scratch/runtime-candidate03-source/local-current/faster_whisper/utils.py', 4946, '5b36ceb9d0fd3961de8cfb144bd82f9a4ef3151b2e5958405a11efb4f3ac4f82'),
    ('hub-signature-source.py.txt', '_scratch/runtime-candidate03-source/upstream/huggingface--huggingface_hub/src/huggingface_hub/_snapshot_download.py', 31197, '29c2316ec5d0862d0311b0a2cfd97cd39be636042073cef427279b4261893a93'),
]
for name, rel, size, sha in inputs:
    path = root / rel
    assert path.stat().st_size == size
    with path.open('rb') as stream:
        raw = stream.read(size + 1)
    assert len(raw) == size and hashlib.sha256(raw).hexdigest() == sha
    with (out / name).open('xb') as stream:
        stream.write(raw)
before = (out / 'utils-before.py.txt').read_bytes()
line = b'        kwargs["local_dir_use_symlinks"] = False\n'
assert before.count(line) == 1
after = before.replace(line, b'')
ast.parse(after)
with (out / 'utils-after.py.txt').open('xb') as stream:
    stream.write(after)
patch = ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True), 'a/faster_whisper/utils.py', 'b/faster_whisper/utils.py'))
(out / 'patch.txt').write_text(patch, encoding='utf-8', newline='\n')
rows = []
for path in sorted(p for p in out.iterdir() if p.is_file()):
    raw = path.read_bytes()
    rows.append({'file': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
manifest = json.dumps({'payloads': rows}, indent=2) + '\n'
(out / 'INPUT-SHA256.json').write_text(manifest, encoding='utf-8', newline='\n')
print(json.dumps({'patched_sha256': hashlib.sha256(after).hexdigest(), 'input_manifest_sha256': hashlib.sha256(manifest.encode()).hexdigest()}))

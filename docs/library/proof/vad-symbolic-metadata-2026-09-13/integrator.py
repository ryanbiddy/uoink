"""Preserve reviewed instruments and the actual static refusal, without artifact access."""
import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / '_scratch/vad-symbolic-adapter-proposal-final-proof01'
expected = '09f3affc4738efe4ae6e3b825cd616ac85c0c4adc3569ef008aa59ad832cc499'
assert hashlib.sha256((source / 'SHA256.json').read_bytes()).hexdigest() == expected
doc = json.loads((source / 'SHA256.json').read_bytes())
rows = doc.get('files', doc.get('payloads'))
if isinstance(rows, list):
    converted = {}
    for row in rows:
        name = row.get('path', row.get('file'))
        assert name and name not in converted
        converted[name] = row
    rows = converted
assert len(rows) == 108
assert {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} == set(rows) | {'SHA256.json'}
for name, facts in rows.items():
    path = (source / name).resolve(strict=True)
    assert path.is_relative_to(source)
    assert path.stat().st_size == facts['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest() == facts['sha256']
receipt_path = root / '_scratch/vad-symbolic-adapter-proposal01/results/symbolic-run01.json'
receipt = json.loads(receipt_path.read_bytes())
assert (receipt['status'], receipt['reason'], receipt['reader_exit']) == ('refused', 'Reference cycle refused', 2)
launch = root / '_scratch/vad-symbolic-run01-launch'
assert json.loads((launch / 'exit.json').read_bytes())['actual_process_exit'] == 2
out = root / 'docs/library/proof/vad-symbolic-metadata-2026-09-13'
out.mkdir(exist_ok=False)
(out / '.gitattributes').write_bytes(b'* -text\n')
shutil.copytree(source, out / 'reviewed-proposal108')
shutil.copytree(launch, out / 'actual-static-run01/launch')
shutil.copyfile(receipt_path, out / 'actual-static-run01/receipt.json')
shutil.copyfile(root / '_scratch/launch_vad_symbolic_run01.py', out / 'actual-static-run01/launcher.py')
shutil.copyfile(Path(__file__), out / 'integrator.py')
verdict = '''# Static symbolic VAD inspection: refusal retained

The first actual symbolic inspection refused a reference cycle. Reader and
outer process both exited 2 in 0.035824 seconds, using unchanged reviewed
adapter SHA-256 `0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc`.
This is a static refusal, not a model test or an accepted metadata result.

The reader recorded the same 17,719,103-byte artifact digest as the previous
inventory and a 131-member ZIP64 directory before reaching the symbolic
graph. The cycle prevents a complete metadata association result. The current
receipt does not identify the cycle's nodes or establish whether it belongs
to selected model metadata or omitted training state. Do not infer either.
The refusal also occurs before the reader's normal final artifact-identity
checks; its recorded digest is the pre-parse observation, not an atomic
snapshot or a completed post-inspection stability claim.

The exact adapter passed all 24 synthetic cases in author and independent
root runs. The earlier 23-pass/one-failure audit attempt is preserved. The
pure tracer's original 56/1, 57/0 with missing startup binding, and final
57/0 with explicit binding remain in the nested proof. Synthetic success
did not guarantee that this legacy checkpoint fits the restricted grammar.

Root and the independent reviewer read the exact source before this one
static invocation. Only validated in-memory data.pkl bytes reached the inert
tracer. Opaque whole-file hashing and ZIP tail scans can overlap storage
bytes; no storage member was selected or decompressed, and no GLOBAL,
reducer, object, tensor, converter or model was executed.

The 108-payload reviewed proposal is preserved unchanged inside this archive,
with the root brief, launcher, exact reader copy, raw output, actual exit and
refusal receipt. No acceptance test, production source or package changed.

The next proposal is reporting-only: add a bounded cycle witness while keeping
the same refusal and every grammar/hash/ZIP/CRC/resource rule. It needs its
own brief, source review and synthetic qualification before any new static
read. No cycle bypass, partial acceptance or model-load approval follows.
Release, website work and marketing remain held.
'''
(out / 'astra-verdict.md').write_text(verdict, encoding='utf8', newline='\n')
target = root / 'docs/library/ASTRA-VAD-SYMBOLIC-RUN01-VERDICT-2026-09-13.md'
assert not target.exists()
target.write_text(verdict, encoding='utf8', newline='\n')
files = {p.relative_to(out).as_posix(): {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in out.rglob('*') if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps({'files': files}, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'payloads': len(files), 'manifest_sha256': hashlib.sha256((out / 'SHA256.json').read_bytes()).hexdigest()}))

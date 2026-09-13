"""Preserve independently reviewed inert B/B2 evidence and distribution plan."""
import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def validate(directory, expected):
    assert digest(directory / 'SHA256.json') == expected
    data = json.loads((directory / 'SHA256.json').read_bytes())
    entries = data.get('files', data.get('payloads'))
    if isinstance(entries, list):
        rows = {}
        for row in entries:
            name = row.get('path', row.get('file'))
            assert isinstance(name, str) and name not in rows
            rows[name] = row
        entries = rows
    assert isinstance(entries, dict)
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    assert actual == set(entries) | {'SHA256.json'}
    for name, row in entries.items():
        path = (directory / name).resolve(strict=True)
        assert path.is_relative_to(directory) and path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
    return len(entries)

inputs = [
    ('companion-b-combined-review01', 'original-b1-review', 67, '05620906f1d09b8afce3f7065798495c3e7f35666a17aa2948a992500d9530e9'),
    ('companion-b-distribution-plan01', 'original-distribution-plan', 52, '765f515351a3a3e9f180adf63476137c90c8220acc2a6bf7f290dcce9be60011'),
    ('companion-b2-combined-review01', 'b2-reviewed-repair', 70, '28a7d1d8601ffb26b65cba2d4a9cb05774aa465ba5b312b1c36a8ec40256f955'),
]
for name, _, count, expected in inputs:
    assert validate(root / '_scratch' / name, expected) == count
out = root / 'docs/library/proof/companion-tokenizer-preparation-2026-09-13'
out.mkdir(exist_ok=False)
(out / '.gitattributes').write_bytes(b'* -text\n')
for name, destination, count, expected in inputs:
    shutil.copytree(root / '_scratch' / name, out / destination)
    assert validate(out / destination, expected) == count
shutil.copyfile(Path(__file__), out / 'integrator.py')
verdict = '''# Tokenizer companion preparation: B2 review

B2 qualifies the selected constructor behavior in ten synthetic contracts.
It remains an unapplied source derivative. No complete dependency module,
tokenizer parser, CTranslate2 model or wheel ran in this qualification.

B1 moves local-file and supplied-buffer tokenizer parsing ahead of native model
allocation, and refuses missing local-only tokenizer files before allocation.
The explicit nonlocal fallback remains. Its first protocol had one baseline
pass and five failures; the derivative passed six cases in author and Astra
runs. Those results and exact inputs are preserved.

Gemini's later empty-buffer finding exposed a B1 boundary: `b''` was treated as
absent. B2 changes that condition to `is not None`. The four new cases cross
local-only true/false with ambient tokenizer-file presence. B1 now records six
passes and four failures on the expanded protocol. Both B2 runs pass all ten
with zero failures, errors or skips and actual exit 0. Their case IDs, source
and protocol hashes match. These are two runs of ten distinct contracts.
Original six assertions and all accepted product tests are unchanged.

The exact B2 source SHA-256 is
`bf452635becacf6bba46825be6d6eea533da472ce966ee47f5ce7bccfc3bf06d`.
The aggregate raw patch retains its line-ending difference; a separately
labeled normalized patch shows the logical changes. Neither was applied to
the checkout, staging or an installed runtime.

The distribution plan binds the locally captured upstream faster-whisper 1.2.1
wheel and MIT license, proposes version `1.2.1+uoink.localassets1`, and specifies
exact changed members, notice, metadata and RECORD. Its original plan and B2
addendum remain separate and immutable. The bundled ONNX member's declaration
comes from captured RECORD metadata; this preparation does not establish its
decoded payload or model behavior.

The archive includes the 67-payload original review, 52-payload distribution
plan and 70-payload B2 review with their original seals. The next task is a
reviewed deterministic builder with synthetic ZIP tests, then the exact
runtime and compatibility proposal. This verdict approves no wheel build,
installation, model execution, dependency-test change or market release.
'''
(out / 'astra-verdict.md').write_text(verdict, encoding='utf8', newline='\n')
target = root / 'docs/library/ASTRA-COMPANION-B2-PREPARATION-VERDICT-2026-09-13.md'
assert not target.exists()
target.write_text(verdict, encoding='utf8', newline='\n')
files = {p.relative_to(out).as_posix(): {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in out.rglob('*') if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps({'files': files}, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'payloads': len(files), 'manifest_sha256': digest(out / 'SHA256.json')}))

"""Archive existing metadata receipts and proposals; never open a checkpoint."""
import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def validate(directory, expected):
    manifest = directory / 'SHA256.json'
    assert digest(manifest) == expected
    data = json.loads(manifest.read_bytes())
    entries = data.get('files', data.get('payloads'))
    if isinstance(entries, list):
        entries = {row['path']: row for row in entries}
    assert isinstance(entries, dict)
    names = {path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file()}
    assert names == set(entries) | {'SHA256.json'}, (directory, names ^ (set(entries) | {'SHA256.json'}))
    for name, facts in entries.items():
        path = (directory / name).resolve(strict=True)
        assert path.is_relative_to(directory)
        assert path.stat().st_size == facts['bytes'] and digest(path) == facts['sha256'], name
    return len(entries)

bindings = [
    ('vad-static-inventory-final-proof01', 'vad-static-inventory-2026-09-13', '60e3f77ba1244e2044b29f1c67facb917b24cc769f6fb4cb08c18c2f4415ee46'),
    ('vad-static-metadata-tail-final-proof01', 'vad-static-metadata-tail-2026-09-13', 'f1a9c61f617fd700019c8c1567453d770614df88415c818000ac969f55bc53aa'),
]
results = []
for source_name, target_name, expected in bindings:
    source = root / '_scratch' / source_name
    target = root / 'docs/library/proof' / target_name
    count = validate(source, expected)
    assert not target.exists()
    assert (source / '.gitattributes').read_bytes() == b'* -text\n'
    shutil.copytree(source, target)
    assert validate(target, expected) == count
    results.append({'proof': target_name, 'payloads': count, 'manifest_sha256': expected})

source = root / '_scratch/vad-fixed-loader-proposal01'
expected = '129773fb33e4ec94a4e217373064d6d55de68d1db71f299a2372a91be1a76403'
assert validate(source, expected) == 38
out = root / 'docs/library/proof/vad-fixed-loader-proposal-2026-09-13'
out.mkdir(exist_ok=False)
(out / '.gitattributes').write_bytes(b'* -text\n')
shutil.copytree(source, out / 'original-proposal')
assert validate(out / 'original-proposal', expected) == 38
addendum = root / '_scratch/vad-fixed-loader-run04-addendum01.md'
assert digest(addendum) == '7fb48cbd57d479d24e127374edc834baf4a91b149a0889110adeb12b3b6e18b8'
shutil.copyfile(addendum, out / 'run04-addendum.md')
shutil.copyfile(Path(__file__), out / 'integrator.py')
files = {p.relative_to(out).as_posix(): {'bytes': p.stat().st_size, 'sha256': digest(p)}
         for p in out.rglob('*') if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps({'files': files}, indent=2) + '\n', encoding='utf8', newline='\n')
assert validate(out, digest(out / 'SHA256.json')) == len(files)
results.append({'proof': out.name, 'payloads': len(files), 'manifest_sha256': digest(out / 'SHA256.json')})
verdict = '''# Static VAD evidence and fixed-loader preparation

The bounded static inventory is complete. It identifies the legacy checkpoint's
archive structure and instruction literals without constructing objects or
tensors. The default VAD security defect remains open; no replacement loader,
converted model or runtime has qualified.

All four inspections concern the same 17,719,103-byte staged artifact, SHA-256
`0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`.
Runs 01 and 02 refused before inventory with reader exit 2; the outer process
reported 1. The reviewed narrow ZIP-version compatibility change allowed run03
to finish with reader and outer exit 0. Run04 added a bounded tail sample and
also finished with both exits 0. Those earlier refusals stay recorded.

The archive has 131 members. Only the 21,882-byte `archive/data.pkl` payload
received separate CRC validation and opcode parsing. Other member bytes were
included in the whole-file hash but were not extracted into tensors. Protocol 2
contains 17 GLOBAL literals, 160 BINPERSID, 327 REDUCE and nine each of NEWOBJ
and BUILD. Those names were recorded as data; no referenced callable ran.

Run04's literal tail names PyanNet and its configuration fields. This supports
a factory hypothesis, not verified metadata associations, tensor shapes or
trusted provenance. The fixed-loader proposal therefore leaves unknown
configuration and schema fields unset and refuses its draft manifest. Its
source-bound route avoids checkpoint-selected classes and unrestricted-load
fallbacks. It is preparation, not an implemented security repair.

The inventory archive retains the original failed 31/2 synthetic run, repaired
36/0, reporting 45/0 and compatibility 89/0 results. Tail qualification records
17 passing checks. Raw readers, briefs, repairs, measured exits and all nested
seals are preserved. No accepted product tests were edited. This documentary
integration copies existing evidence only; it performs no checkpoint read.

Proof directories are `proof/vad-static-inventory-2026-09-13` (80 payloads),
`proof/vad-static-metadata-tail-2026-09-13` (29 payloads) and
`proof/vad-fixed-loader-proposal-2026-09-13` (the original 38-payload proposal
and its immutable seal, run04 addendum and transport wrapper).

The next bounded task is a reviewed symbolic metadata adapter to recover
declared associations and tensor descriptors as inert records. Provenance,
conversion and isolated runtime qualification remain separate decisions.
Nothing here approves model loading, release, website work or marketing.
'''
target = root / 'docs/library/ASTRA-VAD-STATIC-PREPARATION-VERDICT-2026-09-13.md'
assert not target.exists()
target.write_text(verdict, encoding='utf8', newline='\n')
print(json.dumps(results, indent=2))

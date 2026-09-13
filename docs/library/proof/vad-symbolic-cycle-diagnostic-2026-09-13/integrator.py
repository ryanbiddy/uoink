"""Preserve reviewed instruments and the actual static refusal, without artifact access."""
import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / '_scratch/vad-symbolic-cycle-diagnostic-final-proof01'
expected = '94f3bddc87892b013f67eb989be4d060791e91bea1f8106c029d6a135c5f56f5'
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
assert len(rows) == 158
assert {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} == set(rows) | {'SHA256.json'}
for name, facts in rows.items():
    path = (source / name).resolve(strict=True)
    assert path.is_relative_to(source)
    assert path.stat().st_size == facts['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest() == facts['sha256']
receipt_path = root / '_scratch/vad-symbolic-adapter-proposal01/results/symbolic-cycle01.json'
receipt = json.loads(receipt_path.read_bytes())
assert (receipt['status'], receipt['reason'], receipt['reader_exit']) == ('refused', 'Reference cycle refused', 2)
launch = root / '_scratch/vad-symbolic-cycle01-launch'
assert json.loads((launch / 'exit.json').read_bytes())['actual_process_exit'] == 2
out = root / 'docs/library/proof/vad-symbolic-cycle-diagnostic-2026-09-13'
out.mkdir(exist_ok=False)
(out / '.gitattributes').write_bytes(b'* -text\n')
shutil.copytree(source, out / 'reviewed-proposal158')
shutil.copytree(launch, out / 'actual-static-run01/launch')
shutil.copyfile(receipt_path, out / 'actual-static-run01/receipt.json')
shutil.copyfile(root / '_scratch/launch_vad_cycle01.py', out / 'actual-static-run01/launcher.py')
shutil.copyfile(Path(__file__), out / 'integrator.py')
verdict = '''# Static cycle diagnostic: training entry path observed

The diagnostic retains Reference cycle refused, reader and outer exit 2,
in 0.029370 seconds. It reports a five-node cycle reached along a known
training root. This identifies one observed path; shared references prevent
any claim that the cycle belongs exclusively to training metadata.

The witness is complete within its 12-node cap. Its path is newobj 2867,
dict 2868, list 2898, newobj 2901 and dict 2902. Recorded-operation edges
connect each symbolic object to its dictionary. A literal content-field
value leads into the list, and a literal parent-field value closes the cycle
to node 2867. No arbitrary field values or GLOBAL names were emitted.
These structural roles do not establish an OmegaConf class or semantics.

The unchanged reviewed reader is SHA-256
`15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd`.
It recorded the same 17,719,103-byte artifact digest and 131-member archive
before refusing. Normal final file-identity checks are not reached after
this refusal; no atomic or completed post-inspection stability is claimed.

Author and root synthetic runs each pass 36 cases with actual exit 0. The
23 inherited behavior checks stay unchanged, one composition predicate is
replaced by a scope-specific reporting-delta check, and 12 witness cases are
added. The original 24-case adapter qualification and its failed first attempt
remain historical evidence. This diagnostic did not relax cycle acceptance,
grammar, hash/ZIP/CRC checks or the 256-KiB final receipt cap.

Root read the full diff, all synthetic assertions and independent review
before this single new static run. The original 158-payload proposal seal
is preserved, with the exact reader, root brief/launcher, raw output and
actual refusal receipt. No model, object, tensor or converter ran; storage
members were not selected or decompressed. Opaque hash and ZIP-tail reads
retain their previously documented overlap with storage bytes.

The next design may inspect the existing selected metadata roots separately
while retaining the overall strict refusal and exit 2. It must independently
validate the selected reachable closure, refuse any selected cycle alias,
omit training values and label any returned static data partial and untrusted.
Source review and synthetic qualification are required before another static
invocation. No metadata, model, runtime or release approval follows here.
'''
(out / 'astra-verdict.md').write_text(verdict, encoding='utf8', newline='\n')
target = root / 'docs/library/ASTRA-VAD-CYCLE-DIAGNOSTIC-VERDICT-2026-09-13.md'
assert not target.exists()
target.write_text(verdict, encoding='utf8', newline='\n')
files = {p.relative_to(out).as_posix(): {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in out.rglob('*') if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps({'files': files}, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'payloads': len(files), 'manifest_sha256': hashlib.sha256((out / 'SHA256.json').read_bytes()).hexdigest()}))

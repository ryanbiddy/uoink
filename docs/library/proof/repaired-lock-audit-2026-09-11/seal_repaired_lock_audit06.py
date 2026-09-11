"""Bind retained exact-version advisory results to the actual package inventory."""
import hashlib
import json
import shutil
from pathlib import Path

r = Path(__file__).resolve().parents[1]
raw = r / '_scratch/repaired-lock-osv-2026-09-11'
graph = r / '_scratch/package06-runtime-graph-01'
package = r / 'docs/library/proof/candidate-package-06-2026-09-11'
out = r / 'docs/library/proof/repaired-lock-audit-2026-09-11'
out.mkdir(exist_ok=False)
(out / '.gitattributes').write_text('* -text\n', encoding='utf8', newline='\n')
vendor = r / '_scratch/setuptools-vendored-osv-2026-09-11'
for folder, label in ((raw, 'osv'), (graph, 'runtime-graph'), (vendor, 'setuptools-vendored-osv')):
    for source in folder.rglob('*'):
        if source.is_file():
            target = out / label / source.relative_to(folder)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
for name in ('audit_repaired_lock.py', 'verify_package06_graph.py', 'seal_repaired_lock_audit06.py', 'audit_setuptools_vendor06.py'):
    shutil.copyfile(r / '_scratch' / name, out / name)
lock = r / 'requirements-installer-lock.txt'
shutil.copyfile(lock, out / lock.name)
audit = json.loads((raw / 'summary.json').read_text())
edges = json.loads((graph / 'summary.json').read_text())
pins = json.loads((graph / 'inventory.json').read_text())
metadata = json.loads((package / 'runtime-distributions.json').read_text())
normalize = lambda name: name.lower().replace('_', '-').replace('.', '-')
assert {normalize(name): row['version'] for name, row in metadata.items()} == pins
assert not edges['failed_edges'] and len(pins) == 140
digest = hashlib.sha256(lock.read_bytes()).hexdigest()
assert audit['lock_sha256'] == edges['lock_sha256'] == digest
binding = {'package': json.loads((package / 'package-manifest.json').read_text()),
           'lock_sha256': digest, 'actual_runtime_pins': len(pins),
           'dependency_edges': edges['dependency_edges'], 'failed_edges': [],
           'raw_advisory_summary': audit,
           'setuptools_vendored_advisory_summary': json.loads((vendor / 'summary.json').read_text()),
           'interpretation': 'Raw OSV findings retained. Lightning 2.6.6 code repair has separate wheel/source/runtime evidence; the inconsistent advisory fixed event is not silently filtered. No whole-graph security clearance or model inference claim.'}
(out / 'binding.json').write_text(json.dumps(binding, indent=2) + '\n', encoding='utf8')
files = {p.relative_to(out).as_posix(): {'bytes': p.stat().st_size,
         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(out.rglob('*')) if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps({'algorithm': 'sha256', 'files': files}, indent=2) + '\n', encoding='utf8')
print(json.dumps({'payloads': len(files), 'pins': len(pins), 'dependency_edges': edges['dependency_edges']}))

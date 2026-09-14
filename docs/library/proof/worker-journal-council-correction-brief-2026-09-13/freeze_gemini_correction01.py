"""Freeze reviewed text only; never execute or follow candidate payloads."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '_scratch/gemini-worker-journal-accuracy-review01'
DEST = ROOT / 'docs/library/proof/worker-journal-council-correction-brief-2026-09-13'
PINS = {
    'DISCREPANCIES.md': '39858dfd24e72a81220c28e88fd0e0766361c50ef6326e125e765fe4aa8c118f',
    'CORRECTIVE-BRIEF.md': '9db8a4bb59fc9a6ef3201929d56b4f5c6f597bd83e61b35f2c8e03415b7dd076',
    'CORRECTION-INPUTS.json': 'f095e168acba3e4c28fb9678a326730de0eaac37cc2d7b9dc6f4666d98b9e36e',
}
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def checked(path):
    assert path.resolve().is_relative_to(ROOT)
    for part in (path, *path.parents):
        assert not part.is_symlink() and not part.is_junction(), str(part)
        if part == ROOT:
            break
    return path.read_bytes()
def gitraw(path):
    return subprocess.check_output(['git', 'show', 'HEAD:' + path.relative_to(ROOT).as_posix()], cwd=ROOT)

assert not DEST.exists()
payloads = {}
for name, expected in PINS.items():
    raw = checked(SOURCE / name)
    assert sha(raw) == expected, name
    payloads[name] = raw
mapping = json.loads(payloads['CORRECTION-INPUTS.json'])
catalog_path = ROOT / mapping['catalog_path']
catalog_raw = checked(catalog_path)
assert sha(catalog_raw) == mapping['catalog_sha256'] and catalog_raw == gitraw(catalog_path)
catalog = {row['id']: row for row in json.loads(catalog_raw)['inputs']}
rows = []
for row in mapping['inputs']:
    relative = row['path']
    assert relative.startswith('docs/library/proof/') and '..' not in Path(relative).parts
    path = ROOT / relative
    raw = checked(path)
    assert raw == gitraw(path), row['id']
    for key in ('path', 'bytes', 'sha256', 'lines'):
        assert row[key] == catalog[row['id']][key], (row['id'], key)
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    line_count = len(raw.decode('utf-8-sig').splitlines())
    assert line_count == row['lines']
    ranges = row['required_ranges_inclusive']
    assert all(type(first) is int and type(last) is int and 1 <= first <= last <= line_count for first, last in ranges)
    assert sum(last-first+1 for first, last in ranges) == row['required_line_count']
    rows.append({key: row[key] for key in ('id', 'path', 'bytes', 'sha256', 'lines', 'required_line_count')})
assert len(rows) == mapping['selected_count'] == 33
assert sum(row['bytes'] for row in rows) == mapping['selected_bytes'] == 440045
assert sum(row['required_line_count'] for row in rows) == mapping['required_lines'] == 6422
original_path = ROOT / 'docs/library/proof/worker-journal-council-failed-2026-09-13/ORIGINAL-GEMINI-REPORT.md'
original = checked(original_path)
assert original == gitraw(original_path)
assert sha(original) == mapping['original_report']['sha256'] and len(original) == 36931
for name in ('ACTUAL-INPUT-MAP-TOOL.json', 'prepare_input_map.py'):
    payloads[name] = checked(SOURCE / name)
DEST.mkdir()
for name, raw in payloads.items():
    (DEST / name).write_bytes(raw)
    assert checked(SOURCE / name) == raw == checked(DEST / name)
root_check = {
    'schema': 'uoink.council-correction-root-input-check.v1',
    'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'status': 'FIXED_TEXT_INPUTS_MATCH_GIT_AND_DISK',
    'selected_count': 33, 'selected_bytes': 440045, 'minimum_required_lines': 6422,
    'displayed_coverage': 'Not inferred from hashes; correction worker must report its actual displayed ranges.',
    'original_report': {'path': original_path.relative_to(ROOT).as_posix(), 'bytes': len(original), 'sha256': sha(original)},
    'rows': rows,
}
(DEST / 'ROOT-INPUT-CHECK.json').write_text(json.dumps(root_check, indent=2) + '\n', encoding='utf-8')
(DEST / '.gitattributes').write_bytes(b'* -text\n')
print(json.dumps({'status': root_check['status'], 'selected_count': 33, 'selected_bytes': 440045, 'minimum_required_lines': 6422, 'destination': DEST.relative_to(ROOT).as_posix()}))

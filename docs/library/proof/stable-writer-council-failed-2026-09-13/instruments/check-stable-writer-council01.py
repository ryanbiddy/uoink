"""Inspect frozen text bindings and review accuracy; execute no candidate code."""
import hashlib
import json
import os
from pathlib import Path
import sys

assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db'
root = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
worker = Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2b39a17c-941\gemini')
map_path = 'docs/library/proof/stable-writer-council-brief-2026-09-13/INPUT-SELECTION.json'
raw_map = (root / map_path).read_bytes()
assert hashlib.sha256(raw_map).hexdigest() == '3053c328e65636d895f8caa1545425638492f9cb816fc0ac8bdff4fe19baa51d'
catalog = json.loads(raw_map)
selections = [value for value in catalog.values() if isinstance(value, list) and len(value) == 48 and all(isinstance(row, dict) and 'id' in row for row in value)]
assert len(selections) == 1
rows = selections[0]
coverage_rel = 'docs/library/GEMINI-STABLE-DIRECTORY-WRITER-COUNCIL-2026-09-13-COVERAGE.json'
report_rel = 'docs/library/GEMINI-STABLE-DIRECTORY-WRITER-COUNCIL-2026-09-13.md'
for name in (coverage_rel, report_rel):
    assert (root / name).read_bytes() == (worker / name).read_bytes()
coverage = json.loads((root / coverage_rel).read_bytes())
reported = {row['id']: row for row in coverage['files']}
assert len(reported) == len(coverage['files']) == 48 and set(reported) == {row['id'] for row in rows}
comparisons = []
for row in rows:
    path = row['path']
    assert path.startswith('docs/library/proof/') and '..' not in Path(path).parts
    raw = (root / path).read_bytes()
    assert raw == (worker / path).read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    claim = reported[row['id']]
    mismatches = {key: {'expected': row[key], 'reported': claim.get(key)} for key in ('path', 'bytes', 'lines', 'sha256') if claim.get(key) != row[key]}
    comparisons.append({'id': row['id'], 'mismatches': mismatches})
report_text = (root / report_rel).read_text(encoding='utf-8-sig')
source = (root / 'docs/library/proof/windows-stable-directory-qualification-2026-09-13/proposal01/test_stable_directory.py').read_text(encoding='utf-8-sig')
import re
claimed_tests = re.findall(r'^\d+\. `(test_[a-z0-9_]+)`', report_text, flags=re.M)
actual_tests = re.findall(r'^    def (test_[a-z0-9_]+)\(', source, flags=re.M)
assert len(claimed_tests) == len(actual_tests) == 11
summary = {
    'review_run': '2b39a17c-9418-4cfe-85d8-ecc07d7cdde2',
    'actual_selected_inputs_match_both_roots': 48,
    'exact_worker_output_copies': 2,
    'coverage_rows_with_mismatch': sum(bool(row['mismatches']) for row in comparisons),
    'coverage_mismatch_counts': {key: sum(key in row['mismatches'] for row in comparisons) for key in ('path', 'bytes', 'lines', 'sha256')},
    'claimed_test_names': claimed_tests,
    'actual_test_names': actual_tests,
    'claimed_test_names_absent_from_source': [name for name in claimed_tests if name not in actual_tests],
    'review_accuracy': 'FAILED',
    'component_measurements_changed': False,
    'candidate_or_native_execution': False,
    'comparisons': comparisons,
}
out = root / '_scratch/STABLE-WRITER-COUNCIL01-ROOT-CHECK.json'
with out.open('xb') as stream:
    stream.write((json.dumps(summary, indent=2) + '\n').encode())
print(json.dumps({key: value for key, value in summary.items() if key not in ('comparisons', 'claimed_test_names', 'actual_test_names')}))

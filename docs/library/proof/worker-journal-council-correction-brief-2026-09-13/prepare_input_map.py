"""Data-only fixed catalog subset; never import a candidate or follow embedded paths."""
import hashlib
import json
from pathlib import Path

ROOT = Path('E:/AI/projects/uoink/checkouts/Yoink-library')
HERE = ROOT / '_scratch/gemini-worker-journal-accuracy-review01'
CATALOG = ROOT / 'docs/library/proof/worker-journal-adapter-council-brief-2026-09-13/SELECTED-INPUTS.json'
REPORT = Path('C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/cede76cb-7ca/gemini/docs/library/GEMINI-WORKER-JOURNAL-ADAPTER-COUNCIL-2026-09-13.md')
REPORT_SHA = '50a65888706d2a329318c73702b6f468c713d07f7e2bd4c48e423228f6fdda58'

# None means complete text. Ranges are inclusive displayed source lines.
RANGES = {
    'S07': None, 'S09': None, 'S11': None, 'S12': None,
    'S13': None, 'S14': None, 'S15': [[94, 98], [116, 236]],
    'S17': None, 'S20': None, 'S24': None,
    'S31': None, 'S32': None, 'S33': None,
    'S35': [[337, 351], [650, 670]],
    'S36': None, 'S37': [[1, 91], [133, 248]],
    'S38': [[45, 55], [177, 214]], 'S39': None, 'S40': None,
    'S42': [[1, 33], [255, 344], [410, 422]],
    'S45': [[149, 200]], 'S46': None, 'S47': None,
    'S48': [[410, 477], [628, 643], [738, 743]], 'S49': None,
    'S51': None, 'S54': [[196, 506]],
    'S60': None, 'S61': None, 'S64': None, 'S65': None,
    'S68': None, 'S69': None,
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


catalog_bytes = CATALOG.read_bytes()
catalog = json.loads(catalog_bytes)
rows = {row['id']: row for row in catalog['inputs']}
report_bytes = REPORT.read_bytes()
assert len(report_bytes) == 36931 and sha(report_bytes) == REPORT_SHA
selected = []
for source_id, ranges in RANGES.items():
    original = rows[source_id]
    relative = original['path']
    assert relative.startswith('docs/library/') and '..' not in Path(relative).parts
    raw = (ROOT / relative).read_bytes()  # Fixed selected text only.
    assert len(raw) == original['bytes'] and sha(raw) == original['sha256'], source_id
    actual_lines = len(raw.decode('utf-8-sig').splitlines())
    assert actual_lines == original['lines'], source_id
    ranges = ranges or [[1, actual_lines]]
    assert all(1 <= first <= last <= actual_lines for first, last in ranges)
    selected.append({
        'id': source_id, 'path': relative, 'groups': original['groups'],
        'bytes': len(raw), 'lines': actual_lines, 'sha256': sha(raw),
        'required_ranges_inclusive': ranges,
        'required_line_count': sum(last - first + 1 for first, last in ranges),
        'read_status': 'Pending actual corrective-worker displayed coverage',
    })
assert len(selected) == 33
document = {
    'schema': 'uoink.gemini-source-accuracy-correction-inputs.v1',
    'status': 'PREPARED_FOR_ROOT_REVIEW_NOT_DISPATCHED',
    'catalog_path': CATALOG.relative_to(ROOT).as_posix(),
    'catalog_sha256': sha(catalog_bytes),
    'catalog_count': catalog['selected_text_count'],
    'original_report': {'path': str(REPORT), 'bytes': len(report_bytes),
                        'sha256': sha(report_bytes), 'lines': 308},
    'selected_count': len(selected),
    'selected_bytes': sum(row['bytes'] for row in selected),
    'required_lines': sum(row['required_line_count'] for row in selected),
    'verification': 'Data-only exact bytes/SHA/line counts; no candidate execution or rendered-line coverage claim',
    'purpose': 'Repair original source account only; preserve all 17/65 qualification outcomes',
    'inputs': selected,
}
output = HERE / 'CORRECTION-INPUTS.json'
assert not output.exists()
output.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'selected_count': len(selected), 'selected_bytes': document['selected_bytes'],
                  'required_lines': document['required_lines'], 'map_sha256': sha(output.read_bytes()),
                  'original_report_unchanged': sha(REPORT.read_bytes()) == REPORT_SHA}))

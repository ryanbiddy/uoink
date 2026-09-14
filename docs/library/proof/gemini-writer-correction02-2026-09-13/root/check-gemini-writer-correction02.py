"""Compare only selected source and review texts; do not execute candidate code."""
import hashlib
import json
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
worker=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\5444c59a-8ae\gemini')
map_rel='docs/library/proof/writer-exclusion-correction02-brief-2026-09-13/INPUT-SELECTION.json'
raw=(repo/map_rel).read_bytes()
assert raw==(worker/map_rel).read_bytes()
assert hashlib.sha256(raw).hexdigest()=='173324c8aa8b66ce55c35ba151bb34b89eb5351f7bb80fa332c87340b77b62ed'
mapping=json.loads(raw)
for row in mapping['files']:
    data=(repo/row['path']).read_bytes()
    assert data==(worker/row['path']).read_bytes()
    assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
base='docs/library/GEMINI-WRITER-EXCLUSION-CORRECTION02-2026-09-13'
report=(worker/(base+'.md')).read_bytes()
coverage_raw=(worker/(base+'.coverage.json')).read_bytes()
coverage=json.loads(coverage_raw)
assert len(report.decode().split())<=600
assert [r['id'] for r in coverage]==[r['id'] for r in mapping['files']]
for row,binding in zip(coverage,mapping['files']):
    assert set(row)=={'id','viewed_ranges'}
    for start,end in row['viewed_ranges']:
        assert type(start) is int and type(end) is int and 1<=start<=end<=binding['lines']
print(json.dumps({'input_pairs':5,'selected_bytes':sum(r['bytes'] for r in mapping['files']),
                  'report_words_whitespace':len(report.decode().split()),'report_bytes':len(report),
                  'report_sha256':hashlib.sha256(report).hexdigest(),'coverage_bytes':len(coverage_raw),
                  'coverage_sha256':hashlib.sha256(coverage_raw).hexdigest(),'coverage_schema_and_bounds_valid':True,
                  'worker_view_trace_independently_verified':False,'source_verdict':'separate root review required'}))

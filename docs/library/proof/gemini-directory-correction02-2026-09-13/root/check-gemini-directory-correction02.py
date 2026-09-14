"""Read exact review inputs and outputs; execute no candidate code."""
import hashlib
import json
import re
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
worker=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\a28eb713-c06\gemini')
map_rel='docs/library/proof/stable-directory-correction02-brief-2026-09-13/INPUT-SELECTION.json'
raw_map=(repo/map_rel).read_bytes()
assert raw_map==(worker/map_rel).read_bytes()
assert hashlib.sha256(raw_map).hexdigest()=='874b686d4a078d37385cac6b5a860a21aebeec08781d2ec150cd3f2e0491b277'
mapping=json.loads(raw_map)
texts={}
for row in mapping['files']:
    data=(repo/row['path']).read_bytes()
    assert data==(worker/row['path']).read_bytes()
    assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
    texts[row['id']]=data.decode('utf-8')
base='docs/library/GEMINI-STABLE-DIRECTORY-CORRECTION02-2026-09-13'
report=(worker/(base+'.md')).read_bytes()
coverage_raw=(worker/(base+'.coverage.json')).read_bytes()
text=report.decode('utf-8')
coverage=json.loads(coverage_raw)
assert len(text.split())<=600
assert [row['id'] for row in coverage]==[row['id'] for row in mapping['files']]
for row,binding in zip(coverage,mapping['files']):
    assert set(row)=={'id','viewed_ranges'}
    for start,end in row['viewed_ranges']:
        assert type(start) is int and type(end) is int and 1<=start<=end<=binding['lines']
names=re.findall(r'\btest_[a-z0-9_]+\b',text)
actual=set(re.findall(r'^    def (test_[a-z0-9_]+)\(',texts['A-05'],re.M))
assert actual<=set(names) and set(names)-actual=={'test_windows_reservations'}
print(json.dumps({'input_pairs':5,'input_bytes':65576,'map_sha256':hashlib.sha256(raw_map).hexdigest(),
                  'report_bytes':len(report),'report_words_whitespace':len(text.split()),'report_sha256':hashlib.sha256(report).hexdigest(),
                  'coverage_bytes':len(coverage_raw),'coverage_sha256':hashlib.sha256(coverage_raw).hexdigest(),
                  'actual_test_names':len(actual),'coverage_schema_and_bounds_valid':True,
                  'worker_reading_trace_independently_verified':False,'source_claim_acceptance':'separate root verdict required'}))

"""Retain exact OSV batch output and each referenced advisory, without filtering."""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import urllib.request

r = Path(__file__).resolve().parents[1]
out = r / '_scratch/repaired-lock-osv-2026-09-11'
out.mkdir(exist_ok=False)
lock = r / 'requirements-installer-lock.txt'
pins = [line.split('==') for line in lock.read_text().splitlines()
        if line and not line.startswith('#')]
assert len(pins) == 140
queries = [{'package': {'name': name, 'ecosystem': 'PyPI'}, 'version': version}
           for name, version in pins]
request = {'queries': queries}
(out / 'request.json').write_text(json.dumps(request, indent=2) + '\n', encoding='utf8')
started = dt.datetime.now(dt.timezone.utc).isoformat()
req = urllib.request.Request('https://api.osv.dev/v1/querybatch', data=json.dumps(request).encode(),
                             headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=60) as response:
    raw = response.read()
(out / 'response.json').write_bytes(raw)
result = json.loads(raw)['results']
assert len(result) == len(pins)
ids = sorted({v['id'] for row in result for v in row.get('vulns', [])})
advisories = out / 'advisories'
advisories.mkdir()
def fetch(identifier):
    assert re.fullmatch(r'[A-Za-z0-9_-]+', identifier)
    url = 'https://api.osv.dev/v1/vulns/' + identifier
    with urllib.request.urlopen(url, timeout=40) as response:
        raw = response.read()
    (advisories / (identifier + '.json')).write_bytes(raw)
    return json.loads(raw)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    records = list(pool.map(fetch, ids))
parent = {}
def find(value):
    parent.setdefault(value, value)
    if parent[value] != value:
        parent[value] = find(parent[value])
    return parent[value]
for advisory in records:
    aliases = [advisory['id'], *advisory.get('aliases', [])]
    for alias in aliases:
        parent[find(alias)] = find(aliases[0])
groups = {}
for identifier in parent:
    groups.setdefault(find(identifier), []).append(identifier)
rows = [{'name': pin[0], 'version': pin[1], 'entries': row.get('vulns', [])}
        for pin, row in zip(pins, result) if row.get('vulns')]
summary = {'started_utc': started, 'finished_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
           'lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest(), 'queried_packages': len(pins),
           'matched_packages': len(rows), 'package_advisory_entries': sum(len(row['entries']) for row in rows),
           'unique_advisory_records': len(ids), 'distinct_alias_groups': len(groups),
           'scope': 'Unfiltered OSV exact-version queries for the source lock; built inventory still needs parity proof',
           'packages': rows, 'alias_groups': list(groups.values()), 'clean': not ids}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf8')
print(json.dumps({k:v for k,v in summary.items() if k not in ('packages', 'alias_groups')}, indent=2))

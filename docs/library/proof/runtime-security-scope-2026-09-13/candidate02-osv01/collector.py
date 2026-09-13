"""Public OSV metadata only, with exact HTTP bytes and conservative accounting."""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import http.client
import json
from pathlib import Path
import re
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '_scratch/runtime-candidate02-osv01'
SELECTION = ROOT / '_scratch/runtime-candidate02-metadata/selection.json'
BRIEF = ROOT / '_scratch/RUNTIME-CANDIDATE02-OSV-BRIEF-2026-09-13.md'
HOST = 'api.osv.dev'
STARTED = dt.datetime.now(dt.timezone.utc).isoformat()
FAILURES = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(path, value):
    with path.open('x', encoding='utf8') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=True) + '\n')


class RecordedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, wire_path):
        super().__init__(HOST, timeout=45)
        self.wire_path = wire_path

    def send(self, data):
        assert isinstance(data, (bytes, bytearray)), 'Unexpected HTTP stream input'
        with self.wire_path.open('ab') as stream:
            stream.write(data)
        super().send(data)


def request(relative_dir, method, path, body=None):
    assert path == '/v1/querybatch' or re.fullmatch(r'/v1/vulns/[A-Za-z0-9_-]+', path)
    directory = OUT / relative_dir
    directory.mkdir(parents=True, exist_ok=False)
    payload = b'' if body is None else json.dumps(body, separators=(',', ':'), ensure_ascii=True).encode('utf8')
    (directory / 'request-body.json').write_bytes(payload)
    headers = {'User-Agent': 'uoink-uninstalled-candidate-metadata-review/2026-09-13',
               'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Connection': 'close'}
    if method == 'POST':
        headers['Content-Type'] = 'application/json'
    metadata = {'method': method, 'url': 'https://' + HOST + path, 'headers': headers,
                'request_body_bytes': len(payload), 'request_body_sha256': sha(payload),
                'started_utc': utc(), 'status': None, 'error': None,
                'redirects_followed': False, 'automatic_retries': 0}
    save(directory / 'request.json', metadata)
    connection = RecordedHTTPSConnection(directory / 'request-wire.bin')
    response = None
    chunks = []
    started = time.monotonic()
    parsed = None
    try:
        connection.request(method, path, body=payload if method == 'POST' else None, headers=headers)
        response = connection.getresponse()
        metadata.update(status=response.status, reason=response.reason,
                        response_headers=list(response.headers.raw_items()),
                        response_http_version=response.version)
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b''.join(chunks)
        expected_length = response.getheader('Content-Length')
        if expected_length is not None:
            assert len(raw) == int(expected_length), 'Truncated Content-Length response'
        assert response.status == 200, 'HTTP status ' + str(response.status)
        assert response.getheader('Content-Encoding', 'identity') == 'identity', 'Unexpected content encoding'
        parsed = json.loads(raw.decode('utf8'))
        assert isinstance(parsed, dict), 'OSV response is not an object'
    except Exception as error:
        partial = getattr(error, 'partial', None)
        if isinstance(partial, bytes):
            chunks.append(partial)
        metadata['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        connection.close()
        raw = b''.join(chunks)
        (directory / 'response-body.json').write_bytes(raw)
        metadata.update(finished_utc=utc(), seconds=time.monotonic() - started,
                        response_bytes=len(raw), response_sha256=sha(raw))
        wire = directory / 'request-wire.bin'
        metadata['request_wire_sha256'] = sha(wire.read_bytes()) if wire.exists() else None
        metadata['request_wire_scope'] = 'HTTP bytes handed to the TLS connection; not a packet capture or delivery acknowledgement'
        save(directory / 'exchange.json', metadata)
    return parsed if metadata['error'] is None else None, metadata


def query_scope(name, pins):
    states = [{'name': package, 'version': version, 'scope': name,
               'complete': False, 'pages': [], 'entries': [], 'errors': []} for package, version in pins]
    pending = [(index, None) for index in range(len(pins))]
    used_tokens = {index: set() for index in range(len(pins))}
    page = 0
    while pending:
        page += 1
        if page > 50:
            error = {'scope': name, 'type': 'PaginationLimit', 'message': 'Exceeded 50 pages; remaining queries incomplete'}
            FAILURES.append(error)
            for index, _ in pending:
                states[index]['errors'].append(error)
            break
        queries = []
        for index, token in pending:
            package, version = pins[index]
            query = {'package': {'ecosystem': 'PyPI', 'name': package}, 'version': version}
            if token:
                query['page_token'] = token
            queries.append(query)
        relative = 'batches/' + name + '/page-%03d' % page
        result, exchange = request(relative, 'POST', '/v1/querybatch', {'queries': queries})
        save(OUT / relative / 'query-map.json', [{'original_index': index, 'name': pins[index][0],
                                                'version': pins[index][1], 'page_token': token} for index, token in pending])
        print('BATCH', name, page, 'queries', len(pending), 'HTTP', exchange['status'], flush=True)
        try:
            assert result is not None, 'Request failed; see exchange.json'
            rows = result['results']
            assert isinstance(rows, list) and len(rows) == len(pending), 'Batch response cardinality mismatch'
        except Exception as error:
            failure = {'scope': name, 'page': page, 'type': type(error).__name__, 'message': str(error)}
            FAILURES.append(failure)
            for index, _ in pending:
                states[index]['errors'].append(failure)
            break
        follow = []
        for (index, token), row in zip(pending, rows):
            state = states[index]
            state['pages'].append(relative)
            try:
                assert isinstance(row, dict) and 'error' not in row, 'Invalid per-query response'
                entries = row.get('vulns', [])
                assert isinstance(entries, list), 'Invalid vulnerability list'
                for entry in entries:
                    assert isinstance(entry, dict) and re.fullmatch(r'[A-Za-z0-9_-]+', entry['id']), 'Invalid advisory id'
                    state['entries'].append({'page': page, 'entry': entry})
                next_token = row.get('next_page_token')
                if next_token:
                    assert isinstance(next_token, str), 'Invalid next-page token'
                    assert next_token not in used_tokens[index], 'Repeated pagination token'
                    used_tokens[index].add(next_token)
                    follow.append((index, next_token))
                else:
                    state['complete'] = True
            except Exception as error:
                failure = {'scope': name, 'name': state['name'], 'page': page,
                           'type': type(error).__name__, 'message': str(error)}
                state['errors'].append(failure)
                FAILURES.append(failure)
        pending = follow
    save(OUT / (name + '-query-results.json'), states)
    return states


def alias_groups(identifiers, records):
    parent = {}
    def find(value):
        parent.setdefault(value, value)
        while parent[value] != value:
            value = parent[value]
        return value
    for identifier in identifiers:
        record = records.get(identifier)
        connected = [identifier] if record is None else [identifier, record['id'], *record.get('aliases', [])]
        for alias in connected:
            parent[find(alias)] = find(connected[0])
    groups = {}
    for identifier in parent:
        groups.setdefault(find(identifier), []).append(identifier)
    return sorted([sorted(group) for group in groups.values()])


def summarize(states, records):
    identifiers = sorted({row['entry']['id'] for state in states for row in state['entries']})
    missing = sorted(set(identifiers) - set(records))
    groups = alias_groups(identifiers, records)
    packages = []
    for state in states:
        entries = [row['entry']['id'] for row in state['entries']]
        packages.append({'name': state['name'], 'version': state['version'], 'query_complete': state['complete'],
                         'raw_entries': len(entries), 'ids': entries, 'duplicate_ids': sorted({item for item in entries if entries.count(item) > 1})})
    return {'queried_pins': len(states), 'completed_pin_queries': sum(state['complete'] for state in states),
            'query_complete': all(state['complete'] for state in states),
            'raw_entries': sum(len(state['entries']) for state in states), 'unique_returned_ids': len(identifiers),
            'alias_groups': groups, 'alias_group_count': len(groups) if not missing else None,
            'provisional_alias_group_count': len(groups), 'alias_grouping_complete': not missing,
            'missing_full_records': missing, 'matched_packages': [row for row in packages if row['ids']],
            'all_queries': packages}


assert not OUT.exists(), 'Fresh output directory required'
selection_bytes = SELECTION.read_bytes()
selected = json.loads(selection_bytes.decode('utf-8-sig'))['selected']
assert len(selected) == 144 and all(isinstance(key, str) and isinstance(value, str) for key, value in selected.items())
assert selected['nltk'] == '3.10.3+uoink.pathsec1'
OUT.mkdir()
(OUT / '.gitattributes').write_bytes(b'* -text\n')
(OUT / 'selection.json').write_bytes(selection_bytes)
(OUT / 'collector.py').write_bytes(Path(__file__).read_bytes())
(OUT / 'brief.md').write_bytes(BRIEF.read_bytes())
save(OUT / 'plan.json', {'started_utc': STARTED, 'selection_sha256': sha(selection_bytes),
                        'candidate_pins': 144, 'separate_comparison': {'nltk': '3.10.3'},
                        'scope': 'Public OSV metadata for an uninstalled candidate; no release/security-clearance claim',
                        'endpoints': ['https://api.osv.dev/v1/querybatch', 'https://api.osv.dev/v1/vulns/{id}'],
                        'api_docs': ['https://google.github.io/osv.dev/post-v1-querybatch/', 'https://google.github.io/osv.dev/get-v1-vulns/'],
                        'original_audit_unchanged': {'raw_entries': 19, 'alias_groups': 15}})
candidate = query_scope('candidate', sorted(selected.items()))
comparison = query_scope('upstream-nltk-comparison', [('nltk', '3.10.3')])
ids = sorted({row['entry']['id'] for state in candidate + comparison for row in state['entries']})


def advisory(identifier):
    result, exchange = request('advisories/' + identifier, 'GET', '/v1/vulns/' + identifier)
    error = exchange['error']
    if result is not None:
        try:
            assert result['id'] == identifier, 'Advisory identity mismatch'
            assert isinstance(result.get('aliases', []), list) and all(isinstance(alias, str) for alias in result.get('aliases', [])), 'Invalid advisory aliases'
            assert isinstance(result.get('affected', []), list), 'Invalid affected records'
        except Exception as problem:
            error = {'type': type(problem).__name__, 'message': str(problem)}
            result = None
    return identifier, result, error


records = {}
with ThreadPoolExecutor(max_workers=4) as pool:
    for identifier, record, error in pool.map(advisory, ids):
        if error:
            FAILURES.append({'advisory': identifier, **error})
        else:
            records[identifier] = record
        print('ADVISORY', identifier, 'complete', record is not None, flush=True)
candidate_summary = summarize(candidate, records)
comparison_summary = summarize(comparison, records)
local = next(row for row in candidate_summary['all_queries'] if row['name'] == 'nltk')
summary = {'started_utc': STARTED, 'finished_utc': utc(), 'selection_sha256': sha(selection_bytes),
           'candidate': candidate_summary, 'upstream_nltk_comparison': comparison_summary,
           'full_advisory_records': len(records), 'requested_advisory_records': len(ids),
           'failures': FAILURES, 'metadata_collection_complete': not FAILURES and candidate_summary['query_complete'] and comparison_summary['query_complete'],
           'local_nltk': {**local, 'package_index_identity': 'No PyPI release record for this local version',
                          'interpretation': 'OSV response does not establish security of the local patch; upstream comparison stays separate'},
           'withdrawn_returned_ids': sorted(identifier for identifier, record in records.items() if record.get('withdrawn')),
           'original_audit_unchanged': {'raw_entries': 19, 'alias_groups': 15},
           'security_cleared': False, 'compatibility_tested': False, 'model_loader_safety_established': False,
           'installed_or_executed_candidate': False, 'release_ready': False}
save(OUT / 'summary.json', summary)
save(OUT / 'advisory-index.json', {identifier: {'id': record['id'], 'aliases': record.get('aliases', []),
     'summary': record.get('summary'), 'published': record.get('published'), 'modified': record.get('modified'),
     'withdrawn': record.get('withdrawn'), 'affected': record.get('affected', []), 'severity': record.get('severity', []),
     'database_specific': record.get('database_specific', {})} for identifier, record in records.items()})
assert SELECTION.read_bytes() == selection_bytes, 'Candidate selection changed during metadata collection'
files = {path.relative_to(OUT).as_posix(): {'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
         for path in sorted(OUT.rglob('*')) if path.is_file()}
save(OUT / 'SHA256.json', {'algorithm': 'sha256', 'files': files})
assert all((OUT / name).stat().st_size == row['bytes'] and sha((OUT / name).read_bytes()) == row['sha256'] for name, row in files.items())
print(json.dumps({'candidate_raw_entries': candidate_summary['raw_entries'], 'candidate_alias_groups': candidate_summary['alias_group_count'],
                  'candidate_matches': candidate_summary['matched_packages'], 'upstream_nltk_raw_entries': comparison_summary['raw_entries'],
                  'upstream_nltk_alias_groups': comparison_summary['alias_group_count'], 'complete': summary['metadata_collection_complete'],
                  'failures': FAILURES, 'payloads': len(files), 'manifest_sha256': sha((OUT / 'SHA256.json').read_bytes())}, indent=2), flush=True)
raise SystemExit(int(not summary['metadata_collection_complete']))

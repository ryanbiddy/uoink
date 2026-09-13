"""Bounded metadata text capture; never downloads distributions or loads models."""
from __future__ import annotations

import datetime as dt
import email
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
SOURCE = ROOT / 'docs/library/proof/runtime-graph-01-2026-09-12'
OUT = ROOT / '_scratch/runtime-candidate02-metadata'
MAX_NEW_PACKAGES = 10
MAX_BODY = 16 * 1024 * 1024
FORBIDDEN = r'C:\Users\hello\AppData\Local\Uoink\index.db'.casefold()


def guard(event, args):
    if event == 'subprocess.Popen':
        raise PermissionError('Metadata collection cannot launch subprocesses')
    if event == 'open' and args:
        name = str(args[0]).replace('/', '\\').casefold()
        if name == FORBIDDEN:
            raise PermissionError('Forbidden live index')


sys.addaudithook(guard)
sys.path.append(r'C:\Users\hello\AppData\Roaming\Python\Python314\site-packages')
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

spec = importlib.util.spec_from_file_location('captured_graph', ROOT / 'scripts/check_runtime_graph.py')
graph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(graph)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf8')


def allowed_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.port not in (443, None) or p.username or p.password or p.query or p.fragment:
        return False
    if p.hostname == 'pypi.org':
        return bool(re.fullmatch(r'/(?:pypi/[a-z0-9-]+/json|simple/[a-z0-9-]+/)', p.path))
    if p.hostname == 'files.pythonhosted.org':
        return bool(re.fullmatch(r'/packages/[a-zA-Z0-9_./+-]+\.whl\.metadata', p.path))
    return False


class BoundRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise PermissionError('Metadata redirect outside allowed endpoint')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


records = []
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), BoundRedirect())


def request(url, kind):
    if not allowed_url(url):
        raise ValueError('Unapproved metadata endpoint: ' + url)
    index = len(records) + 1
    rec = {'request': index, 'url': url, 'kind': kind, 'started_utc': now(), 'status': None}
    records.append(rec)
    write_json(OUT / 'retrievals.json', records)
    headers = {'User-Agent': 'uoink-runtime-metadata-review/2026-09-13', 'Accept-Encoding': 'identity'}
    if kind == 'simple':
        headers['Accept'] = 'application/vnd.pypi.simple.v1+json'
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=30) as response:
            rec['status'] = response.status
            rec['final_url'] = response.url
            rec['content_type'] = response.headers.get('Content-Type')
            if not allowed_url(response.url):
                raise ValueError('Final URL outside allowed metadata endpoints')
            length = response.headers.get('Content-Length')
            if length and int(length) > MAX_BODY:
                raise ValueError('Metadata response exceeds byte limit')
            body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise ValueError('Metadata response exceeds byte limit')
            text = body.decode('utf8')
            if body.startswith((b'PK\x03\x04', b'\x1f\x8b')):
                raise ValueError('Archive response refused')
            suffix = '.metadata' if kind == 'metadata' else '.json'
            rel = f'responses/{index:03d}-{kind}{suffix}'
            (OUT / rel).write_bytes(body)
            rec.update(bytes=len(body), sha256=digest(body), saved_file=rel)
            if kind in ('pypi', 'simple'):
                graph._unique_json(text)
            elif not email.message_from_string(text).get('Metadata-Version'):
                raise ValueError('Response lacks METADATA header')
            rec['finished_utc'] = now()
            write_json(OUT / 'retrievals.json', records)
            return body
    except urllib.error.HTTPError as exc:
        rec['status'] = exc.code
        rec['error'] = str(exc)
        body = exc.read(min(MAX_BODY, 1024 * 1024))
        try:
            body.decode('utf8')
            rel = f'responses/{index:03d}-http-error.txt'
            (OUT / rel).write_bytes(body)
            rec.update(bytes=len(body), sha256=digest(body), saved_file=rel)
        except UnicodeError:
            rec['error_body'] = 'Non-UTF8 response not retained as metadata'
    except Exception as exc:
        rec['error'] = f'{type(exc).__name__}: {exc}'
    rec['finished_utc'] = now()
    write_json(OUT / 'retrievals.json', records)
    return None


def main():
    graph._no_links(OUT)
    if OUT.exists():
        raise FileExistsError('Fresh output root required')
    OUT.mkdir()
    for rel in ('responses', 'evidence/pypi', 'evidence/metadata'):
        (OUT / rel).mkdir(parents=True, exist_ok=True)
    evidence = OUT / 'evidence'
    before = graph._unique_json((SOURCE / 'SHA256.json').read_text(encoding='utf8'))
    copied = []
    for rel, expected in before.items():
        source_path = graph._bounded_path(SOURCE, rel)
        body = source_path.read_bytes()
        if digest(body) != expected:
            raise ValueError('Original capture changed: ' + rel)
        target = graph._bounded_path(evidence, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        if target.read_bytes() != body:
            raise ValueError('Capture copy mismatch: ' + rel)
        copied.append({'path': rel, 'sha256': expected, 'bytes': len(body)})
    write_json(OUT / 'original-copy-bindings.json', copied)
    lock_bytes = (ROOT / 'requirements-installer-lock.txt').read_bytes()
    (OUT / 'input-production-lock.txt').write_bytes(lock_bytes)
    initial = graph.parse_lock(OUT / 'input-production-lock.txt')
    selected = dict(initial)
    selected.update({'torch': '2.13.0', 'torchaudio': '2.11.0', 'torchvision': '0.28.0',
                     'torchcodec': '0.16.0', 'transformers': '5.17.0',
                     'huggingface-hub': '1.31.0', 'tokenizers': '0.23.2'})
    tags = graph.get_supported_wheel_tags()
    env = dict(graph.TARGET_ENV)
    pypi = {}
    simple = {}
    meta = {}
    failures = []
    metadata_bindings = []
    new_names = set()
    new_selections = []
    attempted = set()
    packages = {key.split('[')[0]: value for key, value in selected.items()}
    extras = {name: set() for name in packages}
    for key in selected:
        if '[' in key:
            extras[key.split('[')[0]].update(x.strip() for x in key.split('[', 1)[1][:-1].split(','))

    def package_record(name):
        if name in pypi:
            return pypi[name]
        path = evidence / 'pypi' / (name + '.json')
        if path.exists():
            body = path.read_bytes()
        else:
            if len(new_names) >= MAX_NEW_PACKAGES:
                failures.append({'package': name, 'error': 'New-package metadata bound reached'})
                pypi[name] = None
                return None
            new_names.add(name)
            body = request(f'https://pypi.org/pypi/{name}/json', 'pypi')
            if body is not None:
                path.write_bytes(body)
        pypi[name] = graph._unique_json(body.decode('utf8')) if body is not None else None
        return pypi[name]

    def choose(name, version):
        data = package_record(name)
        if data is None:
            return None
        files = data.get('releases', {}).get(version)
        if files is None:
            failures.append({'package': name, 'version': version, 'error': 'Selected version not in retained PyPI record; no implicit refetch or local-artifact substitution'})
            return None
        result = graph.check_wheel_for_release(name, version, files, tags, env)
        if result['status'] != 'OK':
            failures.append({'package': name, 'version': version, 'error': result['error'], 'status': result['status']})
            return None
        return result['wheel']

    def load_metadata(name, version):
        key = (name, version)
        if key in attempted:
            return meta.get(name)
        attempted.add(key)
        wheel = choose(name, version)
        if wheel is None:
            return None
        path = evidence / 'metadata' / (wheel['filename'] + '.metadata')
        if path.exists():
            body = path.read_bytes()
            origin = 'retained'
        else:
            expected = wheel.get('core_metadata')
            if not isinstance(expected, dict) or not expected.get('sha256'):
                if name not in simple:
                    raw = request(f'https://pypi.org/simple/{name}/', 'simple')
                    simple[name] = graph._unique_json(raw.decode('utf8')) if raw is not None else None
                entry = next((item for item in (simple[name] or {}).get('files', []) if item.get('filename') == wheel['filename']), None)
                if entry is None or entry.get('hashes', {}).get('sha256') != wheel['sha256']:
                    failures.append({'package': name, 'version': version, 'error': 'Missing or mismatched PEP 691 artifact entry'})
                    return None
                expected = entry.get('core-metadata') or entry.get('dist-info-metadata')
            if not isinstance(expected, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(expected.get('sha256', ''))):
                failures.append({'package': name, 'version': version, 'error': 'No published SHA256 for exact METADATA'})
                return None
            body = request(wheel['url'] + '.metadata', 'metadata')
            if body is None:
                return None
            if digest(body) != expected['sha256']:
                failures.append({'package': name, 'version': version, 'error': 'METADATA hash differs from published record', 'actual': digest(body), 'expected': expected['sha256']})
                return None
            path.write_bytes(body)
            origin = 'new_text_capture'
        parsed = graph.parse_metadata_text(body.decode('utf8'))
        if graph.canonical_name(parsed.get('name') or '') != name or Version(parsed.get('version') or '0') != Version(version):
            failures.append({'package': name, 'version': version, 'error': 'Exact METADATA Name/Version mismatch'})
            return None
        meta[name] = parsed
        metadata_bindings.append({'package': name, 'version': version, 'wheel': wheel,
                                  'metadata_path': path.relative_to(evidence).as_posix(),
                                  'metadata_sha256': digest(body), 'origin': origin})
        return parsed

    for round_no in range(20):
        for name, version in list(packages.items()):
            load_metadata(name, version)
        requirements = {}
        changed = False
        for name, data in list(meta.items()):
            for raw in data['requires_dist']:
                req = Requirement(raw)
                active = req.marker is None or any(req.marker.evaluate(dict(env, extra=extra)) for extra in {''} | extras.get(name, set()))
                if not active:
                    continue
                if req.url:
                    failures.append({'package': name, 'error': 'Direct dependency URL not collected', 'requirement': raw})
                    continue
                target = graph.canonical_name(req.name)
                requirements.setdefault(target, []).append({'source': name, 'requirement': raw, 'specifier': str(req.specifier)})
                extra_set = extras.setdefault(target, set())
                before_extras = len(extra_set)
                extra_set.update(req.extras)
                changed |= len(extra_set) != before_extras
        pending = sorted(set(requirements) - set(packages))
        for name in pending:
            data = package_record(name)
            if data is None:
                continue
            constraints = [SpecifierSet(row['specifier']) for row in requirements[name]]
            possibilities = []
            for version in data.get('releases', {}):
                try:
                    parsed_version = Version(version)
                except Exception:
                    continue
                if parsed_version.is_prerelease or parsed_version.is_devrelease or not all(c.contains(parsed_version) for c in constraints):
                    continue
                result = graph.check_wheel_for_release(name, version, data['releases'][version], tags, env)
                if result['status'] == 'OK':
                    possibilities.append((parsed_version, version))
            if not possibilities:
                failures.append({'package': name, 'error': 'No non-yanked compatible wheel satisfies incoming requirements', 'requirements': requirements[name]})
                continue
            version = max(possibilities)[1]
            packages[name] = version
            selected[name] = version
            new_selections.append({'package': name, 'version': version, 'requirements': requirements[name], 'rule': 'Highest stable non-yanked compatible wheel satisfying incoming requirements; review proposal only'})
            changed = True
        if not changed:
            break
    else:
        failures.append({'error': 'Metadata closure did not stabilize within 20 rounds'})
    write_json(OUT / 'selection.json', {'selected': selected})
    write_json(OUT / 'new-selections.json', new_selections)
    write_json(OUT / 'metadata-bindings.json', metadata_bindings)
    write_json(OUT / 'collection-limits.json', failures)
    write_json(OUT / 'selection-diff.json', {'changed': {k: {'before': initial.get(k), 'after': v} for k, v in selected.items() if initial.get(k) != v}, 'removed': sorted(set(initial) - set(selected)), 'extras': {k: sorted(v) for k, v in extras.items() if v}})
    original_after = []
    for rel, expected in before.items():
        actual = digest(graph._bounded_path(SOURCE, rel).read_bytes())
        if actual != expected:
            raise ValueError('Original capture changed during collection: ' + rel)
        original_after.append({'path': rel, 'sha256': actual})
    write_json(OUT / 'original-after-bindings.json', original_after)
    manifest = {p.relative_to(evidence).as_posix(): digest(p.read_bytes()) for p in sorted(evidence.rglob('*')) if p.is_file()}
    write_json(evidence / 'SHA256.json', manifest)
    summary = {'finished_utc': now(), 'reference_only': True, 'new_packages_queried': sorted(new_names),
               'requests': len(records), 'retrieval_failures': [r for r in records if r.get('error')],
               'original_files_unchanged': len(original_after), 'selection_count': len(selected),
               'metadata_records_available': len(meta), 'limits': failures,
               'collector_sha256': digest(Path(__file__).read_bytes()),
               'validator_sha256': digest((ROOT / 'scripts/check_runtime_graph.py').read_bytes()),
               'input_lock_sha256': digest(lock_bytes), 'product_tests_run': False}
    write_json(OUT / 'collection-summary.json', summary)
    print(json.dumps(summary, indent=2))
    return 1 if summary['retrieval_failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())

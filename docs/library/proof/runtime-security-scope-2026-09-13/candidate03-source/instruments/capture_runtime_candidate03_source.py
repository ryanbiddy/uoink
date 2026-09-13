"""Capture bounded version-bound public source as text, never execute it."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
OUT = ROOT / '_scratch/runtime-candidate03-source'
OLD = ROOT / 'docs/library/proof/security-backport12-astra-review-2026-09-12/review'
STAGE = ROOT / 'installer/staging/python/Lib/site-packages'
PLAN = {
    ('huggingface/transformers', 'v5.17.0'): [
        'src/transformers/pipelines/base.py',
        'src/transformers/pipelines/pt_utils.py',
        'src/transformers/processing_utils.py',
        'src/transformers/models/wav2vec2/processing_wav2vec2.py',
    ],
    ('huggingface/huggingface_hub', 'v1.31.0'): [
        'src/huggingface_hub/_snapshot_download.py',
        'src/huggingface_hub/file_download.py',
        'src/huggingface_hub/utils/__init__.py',
    ],
    ('pytorch/audio', 'v2.11.0'): [
        'src/torchaudio/__init__.py',
        'src/torchaudio/_torchcodec.py',
        'src/torchaudio/pipelines/__init__.py',
    ],
    ('meta-pytorch/torchcodec', 'v0.16.0'): [
        'src/torchcodec/decoders/_audio_decoder.py',
        'src/torchcodec/_core/_metadata.py',
        'src/torchcodec/decoders/__init__.py',
    ],
    ('m-bain/whisperX', 'v3.8.6'): ['pyproject.toml'],
}
LOCAL = [
    'whisperx/__init__.py', 'whisperx/vads/__init__.py', 'whisperx/diarize.py',
    'pyannote/audio/__init__.py', 'pyannote/audio/core/io.py',
    'pyannote/audio/core/task.py', 'pyannote/audio/utils/hf_hub.py',
    'torch_audiomentations/__init__.py',
    'torch_audiomentations/core/transforms_interface.py',
    'torch_audiomentations/utils/io.py',
    'torch_audiomentations/augmentations/background_noise.py',
    'faster_whisper/utils.py',
]


def sha(body):
    return hashlib.sha256(body).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + '\n', encoding='utf8')


def check_path(path):
    for p in [*reversed(path.absolute().parents), path.absolute()]:
        try:
            info = p.lstat()
        except FileNotFoundError:
            continue
        if p.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked source/output path refused')


def allowed(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.port not in (443, None) or p.username or p.password or p.query or p.fragment:
        return False
    if p.hostname == 'api.github.com':
        return any(p.path == '/repos/' + repo + '/commits/' + ref for repo, ref in PLAN)
    if p.hostname == 'raw.githubusercontent.com':
        for (repo, _), paths in PLAN.items():
            prefix = '/' + repo + '/'
            if p.path.startswith(prefix):
                commit, _, rel = p.path[len(prefix):].partition('/')
                return bool(re.fullmatch('[0-9a-f]{40}', commit)) and rel in paths
    return False


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            raise PermissionError('Source redirect outside explicit plan')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


records = []
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirect())


def fetch(url, kind):
    if not allowed(url):
        raise ValueError('Unapproved source URL')
    record = {'id': len(records) + 1, 'url': url, 'kind': kind, 'started_utc': now()}
    records.append(record)
    write('retrievals.json', records)
    req = urllib.request.Request(url, headers={'User-Agent': 'uoink-source-review/2026-09-13', 'Accept-Encoding': 'identity'})
    body = None
    try:
        with opener.open(req, timeout=30) as response:
            record.update(status=response.status, final_url=response.url, content_type=response.headers.get('Content-Type'))
            if not allowed(response.url):
                raise ValueError('Final source URL outside explicit plan')
            size = response.headers.get('Content-Length')
            if size and int(size) > 2 * 1024 * 1024:
                raise ValueError('Source response exceeds 2 MiB')
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise ValueError('Source response exceeds 2 MiB')
            body.decode('utf8')
            if body.startswith((b'PK\x03\x04', b'\x1f\x8b')):
                raise ValueError('Archive body refused')
            name = f'responses/{record["id"]:03d}-{kind}.txt'
            (OUT / name).write_bytes(body)
            record.update(saved_file=name, bytes=len(body), sha256=sha(body))
    except urllib.error.HTTPError as exc:
        record.update(status=exc.code, error=str(exc))
        error_body = exc.read(65536)
        try:
            error_body.decode('utf8')
            name = f'responses/{record["id"]:03d}-http-error.txt'
            (OUT / name).write_bytes(error_body)
            record.update(saved_file=name, bytes=len(error_body), sha256=sha(error_body))
        except UnicodeError:
            record['error_body'] = 'Non-text response refused'
        body = None
    except Exception as exc:
        record['error'] = f'{type(exc).__name__}: {exc}'
        body = None
    record['finished_utc'] = now()
    write('retrievals.json', records)
    return body


def main():
    check_path(OUT)
    if OUT.exists():
        raise FileExistsError('Fresh output root required')
    if sum(map(len, PLAN.values())) > 15:
        raise ValueError('Source-file limit exceeded')
    OUT.mkdir()
    (OUT / 'responses').mkdir()
    bindings = []
    existing = json.loads((OLD / 'source-bindings.json').read_text(encoding='utf8'))
    for row in existing:
        source = OLD / 'inspected-source' / row['path']
        check_path(source)
        body = source.read_bytes()
        if sha(body) != row['sha256']:
            raise ValueError('Retained source changed: ' + row['path'])
        target = OUT / 'retained' / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        bindings.append({'origin': 'retained13', 'source': str(source), 'saved_file': target.relative_to(OUT).as_posix(), 'sha256': sha(body), 'bytes': len(body)})
    for rel in LOCAL:
        source = STAGE / rel
        check_path(source)
        body = source.read_bytes()
        body.decode('utf8')
        target = OUT / 'local-current' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        bindings.append({'origin': 'installed-staging-source-only', 'source': str(source), 'saved_file': target.relative_to(OUT).as_posix(), 'sha256': sha(body), 'bytes': len(body)})
    commits = []
    for (repo, ref), paths in PLAN.items():
        raw = fetch(f'https://api.github.com/repos/{repo}/commits/{ref}', 'commit')
        if raw is None:
            commits.append({'repository': repo, 'ref': ref, 'error': 'Commit resolution failed; no branch fallback'})
            continue
        parsed = json.loads(raw.decode('utf8'))
        commit = parsed.get('sha', '')
        if not re.fullmatch('[0-9a-f]{40}', commit):
            raise ValueError('Invalid resolved commit')
        commits.append({'repository': repo, 'ref': ref, 'commit': commit, 'response_sha256': sha(raw), 'html_url': parsed.get('html_url')})
        for rel in paths:
            url = f'https://raw.githubusercontent.com/{repo}/{commit}/{rel}'
            body = fetch(url, 'source')
            if body is None:
                continue
            target = OUT / 'upstream' / repo.replace('/', '--') / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            bindings.append({'origin': 'upstream-source-text', 'repository': repo, 'ref': ref,
                             'commit': commit, 'url': url, 'source_path': rel,
                             'saved_file': target.relative_to(OUT).as_posix(), 'sha256': sha(body), 'bytes': len(body)})
    write('commit-bindings.json', commits)
    write('source-bindings.json', bindings)
    summary = {'completed_utc': now(), 'requests': len(records),
               'successful_upstream_source_files': sum(row['origin'] == 'upstream-source-text' for row in bindings),
               'retained_source_files': len(existing), 'additional_local_source_files': len(LOCAL),
               'failures': [row for row in records if row.get('error')],
               'executed_captured_source': False, 'collector_sha256': sha(Path(__file__).read_bytes())}
    write('capture-summary.json', summary)
    print(json.dumps(summary, indent=2))
    return 1 if summary['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Independent fixtures for phase3-v1-2026-09-07 (run AM, Astra).

Run only these files, from the project root, in PowerShell:
  $tests = (Get-ChildItem tests/library_work_astra/test_phase3_*.py).FullName
  python -m pytest -q -rs -p no:cacheprovider $tests
Integration MUST also run with $env:PHASE3_REQUIRE_IMPLEMENTATION='1'. Missing
0028/source_subscriptions then fails instead of skipping. An existing module with
missing methods or broken imports ALWAYS fails. No contract DDL is substituted
for a missing implementation. The harness checks are not acceptance evidence.

The contract freezes registry payloads and SQL, but does NOT name the Python
scheduler, backend, publication, or fault-injection seams. ASSUMPTIONS for Fable:
* source_subscriptions.SourceSubscriptionService(index, clock=callable UTC ms,
  adapters={adapter_name: fake}, capture_backend=fake, publication=fake,
  instance_id=str, crash_hook=callable(boundary)). Construction does local repair
  only; reconcile() is explicitly callable and never fetches/starts capture.
* The four named tools are methods(context, args), using library_work.RequestContext.
  mint_user_intent(context, {operation: args_without_token}) is a trusted LOCAL
  seam, NOT a fifth registry tool. archive_source(context, {source_id}) archives.
* poll_source(source_id, manual=False) claims/fetches/commits synchronously;
  detection_tick() visits due sources. Adapter.fetch(source, cursor) receives SQL
  row dictionaries and returns snapshot() below. No HTTP parser is mocked here.
* reserve_capture(source_id, item_id) and dispatch_capture(start_id, owner_token)
  are separate public scheduler seams. Operational denial can be any result;
  assertions inspect the frozen ledger, not invented operational result schemas.
* complete_capture(start_id, owner_token), fail_capture(start_id, owner_token,
  code='download_failed'), corpus_deleted(video_id), dispatch_classification()
  perform the named local transitions; fail_capture consults backend.inspect.
* Backend.preflight(start), enqueue(conn, start), dispatch(backend_id, owner_token),
  inspect(backend_id), acquire_capture_key(key, owner_token), and
  release_capture_key(key, owner_token) are injected. enqueue MUST use the caller's
  transaction. inspect returns {state: unknown|alive|stopped}. Dispatch is a fake
  side-effect spy and never completes automatically. Manual lock ownership is a
  fake common-dispatcher input, not proof of a production interprocess lock.
* Publication.inspect(start) / reconcile(start) return {complete, video_id};
  files, provenance, citations and clips must all exist for complete=True. Tests
  stage durable artifact prefixes; they do not execute production extraction.
* crash_hook names used: before_started_commit, after_started_commit,
  after_backend_insert_before_binding, after_outbox_commit,
  after_prepare_run_before_outbox_ack. Hooks bracket the actual transaction named;
  before_started_commit is inside it. BaseException simulates abrupt unwinding.
  Reopening ALL connections models service restart, not OS kill or power loss.

Align ONLY these plumbing assumptions to the implemented public interface. Keep
the behavioral assertions and contract payloads. No private service fields are
read/patched. Fixture SQL seeds legacy/pre-existing/corrupt-boundary states and
reads the normative ledger; tested transitions always call the service. Real
Index migrations and real Phase 2 prepare_run remain in use, with no model client.
Fable's detector ruling wins: YouTube channel/playlist fakes describe Atom windows;
the normative adapter label youtube_playlist_flat_v1 is retained in the schema.
Packaging deferred to AN: source_subscriptions.py, 0028, updated registry/adapters
and dashboard assets need inclusion. These files do not edit packaging.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / 'docs/library/PHASE3-CONTRACT-2026-09-07.md'
MIGRATION = ROOT / 'migrations/0028_source_subscriptions.sql'
VERSION = 'phase3-v1-2026-09-07'
MINUTE = 60_000
DAY = 24 * 60 * MINUTE
TABLES = (
    'source_subscriptions', 'source_consent_receipts', 'source_user_intents',
    'source_detection_cursors', 'source_items', 'source_capture_starts',
    'source_classification_policy', 'source_classification_outbox',
)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def at(value):
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000)


def utc_day(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%d')


class Clock:
    def __init__(self, now=None):
        self.now = at('2026-09-07T00:00:00Z') if now is None else now

    def __call__(self):
        return self.now

    def advance(self, ms):
        self.now += ms


def unavailable(what):
    message = f'AM integration pending: {what}; see test_phase3_support.py assumptions'
    if os.environ.get('PHASE3_REQUIRE_IMPLEMENTATION') == '1':
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture
def phase3_isolation(monkeypatch):
    """Apply guards BEFORE importing runtime modules; all DBs stay in this worktree."""
    scratch = ROOT / '_scratch'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='astra-phase3-', dir=scratch) as temporary:
        root = Path(temporary).resolve()
        for key in ('LOCALAPPDATA', 'APPDATA', 'XDG_DATA_HOME', 'TEMP', 'TMP',
                    'UOINK_DATA_ROOT', 'UOINK_OUTPUT_ROOT'):
            monkeypatch.setenv(key, str(root))

        def forbidden(*args, **kwargs):
            raise AssertionError('Phase 3 fixtures forbid real network/process activity')

        for name in ('create_connection', 'getaddrinfo'):
            monkeypatch.setattr(socket, name, forbidden)
        for name in ('connect', 'connect_ex', 'bind', 'sendto'):
            monkeypatch.setattr(socket.socket, name, forbidden)
        monkeypatch.setattr(subprocess, 'Popen', forbidden)
        monkeypatch.setattr(os, 'system', forbidden)
        for name in ('startfile', 'posix_spawn', 'posix_spawnp'):
            if hasattr(os, name):
                monkeypatch.setattr(os, name, forbidden)
        connect = sqlite3.connect
        opened = []

        def isolated_connect(database, *args, **kwargs):
            name = os.fsdecode(database)
            if name != ':memory:':
                assert not name.startswith('file:'), 'Use explicit fixture DB paths, not URIs'
                assert Path(name).resolve().is_relative_to(root), 'Non-fixture DB access blocked'
            conn = connect(database, *args, **kwargs)
            opened.append(conn)
            return conn

        monkeypatch.setattr(sqlite3, 'connect', isolated_connect)
        monkeypatch.setattr(sqlite3.dbapi2, 'connect', isolated_connect)
        try:
            yield root
        finally:
            # Also clean up connections retained by assertion/exception tracebacks.
            for conn in opened:
                conn.close()


@pytest.fixture
def migration_dir(phase3_isolation, monkeypatch):
    if not MIGRATION.is_file():
        unavailable('migrations/0028_source_subscriptions.sql is absent')
    import index
    target = phase3_isolation / 'migrations'
    target.mkdir()
    for path in (ROOT / 'migrations').glob('*.sql'):
        if int(path.name.split('_', 1)[0]) <= 28:
            shutil.copy2(path, target / path.name)
    monkeypatch.setattr(index, '_MIGRATIONS_DIR', target)
    return target


@pytest.fixture
def phase3_db(phase3_isolation, migration_dir):
    from index import Index
    with Index.open(phase3_isolation / 'fixture.db') as idx:
        assert idx.schema_version() == 28
        assert idx._conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        yield idx
        assert idx._conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert idx._conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


@pytest.fixture
def phase3_module(phase3_isolation):
    path = ROOT / 'source_subscriptions.py'
    if not path.is_file():
        unavailable('source_subscriptions.py is absent')
    module = importlib.import_module('source_subscriptions')
    assert Path(module.__file__).resolve() == path.resolve(), 'Wrong checkout imported'
    assert hasattr(module, 'SourceSubscriptionService'), __doc__
    return module


def rows(idx, table, where='', params=()):
    assert table in TABLES or table in {
        'library_runs', 'library_manifest', 'library_work', 'library_attempts',
        'library_proposals', 'item_shelves', 'yoinks', 'citations', 'clips',
        'astra_fake_jobs', 'podcast_feeds', 'monitored_playlists',
    }
    query = f'SELECT * FROM {table}' + (f' WHERE {where}' if where else '')
    return [dict(row) for row in idx._conn.execute(query, params)]


def source_row(idx, sid):
    return rows(idx, 'source_subscriptions', 'source_id=?', (sid,))[0]


def cursor_row(idx, sid):
    return rows(idx, 'source_detection_cursors', 'source_id=?', (sid,))[0]


def item_rows(idx, sid):
    return rows(idx, 'source_items', 'source_id=?', (sid,))


def ledger(idx, sid=None):
    return rows(idx, 'source_capture_starts', 'source_id=?' if sid else '', (sid,) if sid else ())


def ok(result):
    assert result['ok'] is True, result
    assert result['schema_version'] == 1, result
    assert result['contract_version'] == VERSION, result
    return result


def video(number):
    return f'v{number:010d}'


def observation(number, *, entry_id=None):
    entry = entry_id or video(number)
    return dict(entry_id=entry, canonical_url=f'https://www.youtube.com/watch?v={entry}',
                title=f'Fixture video {number}', published_at_ms=at('2026-09-06T00:00:00Z') + number,
                metadata={'identity_method': 'yt:videoId'})


def snapshot(entries=(), *, coverage='window', truncated=False, etag='fixture-v1'):
    return dict(observations=copy.deepcopy(list(entries)), coverage=coverage,
                observed_count=len(entries), truncated=truncated, etag=etag,
                last_modified=None, not_modified=False, error=None)


class Feed:
    def __init__(self):
        self.responses = {}
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.lock = threading.Lock()

    def fetch(self, source, cursor):
        with self.lock:
            result = copy.deepcopy(self.responses[source['source_id']])
            self.calls.append((copy.deepcopy(source), copy.deepcopy(cursor)))
            blocked = self.block
        self.entered.set()
        if blocked:
            assert self.release.wait(5), 'Adapter was not released by test'
        return result


class Crash(BaseException):
    pass


class Faults:
    def __init__(self):
        self.crash_at = None
        self.pause_at = None
        self.seen = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, boundary):
        self.seen.append(boundary)
        if boundary == self.pause_at:
            self.entered.set()
            assert self.release.wait(5), f'Unreleased fault barrier: {boundary}'
        if boundary == self.crash_at:
            self.crash_at = None
            raise Crash(boundary)


class Backend:
    """Fake durable queue; verifies authorization BEFORE recording side effects."""
    def __init__(self, db_path):
        self.db_path = db_path
        self.launches = []
        self.preflight_ok = True
        self.workers = {}
        self.keys = {}
        self.lock = threading.Lock()

    def preflight(self, start):
        return {'ok': self.preflight_ok, 'code': None if self.preflight_ok else 'fixture_preflight'}

    def acquire_capture_key(self, key, owner_token):
        with self.lock:
            if key in self.keys and self.keys[key] != owner_token:
                return False
            self.keys[key] = owner_token
            return True

    def release_capture_key(self, key, owner_token):
        with self.lock:
            if self.keys.get(key) == owner_token:
                del self.keys[key]

    def enqueue(self, conn, start):
        assert conn.in_transaction, 'Backend insertion escaped reservation transaction'
        conn.execute('INSERT OR IGNORE INTO astra_fake_jobs VALUES(?,?,?)',
                     (start['start_id'], start['start_id'], start['owner_token']))
        saved = conn.execute('SELECT * FROM astra_fake_jobs WHERE job_id=?',
                             (start['start_id'],)).fetchone()
        assert saved['owner_token'] == start['owner_token'], 'Replay changed queue ownership'
        return {'backend_kind': 'astra_fake', 'backend_id': start['start_id']}

    def dispatch(self, backend_id, owner_token):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            start = conn.execute('SELECT * FROM source_capture_starts WHERE backend_id=?',
                                 (backend_id,)).fetchone()
            assert start is not None, 'Orphan backend launch'
            assert start['owner_token'] == owner_token, 'Obsolete owner dispatched'
            assert start['state'] == 'started' and start['started_at_ms'] is not None
            job = conn.execute('SELECT * FROM astra_fake_jobs WHERE job_id=?', (backend_id,)).fetchone()
            assert job is not None and job['start_id'] == start['start_id']
            # A second connection must see both commits before a capture side effect.
            with self.lock:
                assert backend_id not in [entry[0] for entry in self.launches], 'Duplicate dispatch'
                self.launches.append((backend_id, owner_token))
                self.workers[backend_id] = 'alive'
        return {'ok': True}

    def inspect(self, backend_id):
        return {'state': self.workers.get(backend_id, 'unknown')}


class Publication:
    """Durable prefixes of synthetic, timed output; no production capture code."""
    stages = ('corpus_file', 'sidecar', 'item_upsert', 'citations', 'clips', 'complete_publication')

    def __init__(self, root, db_path):
        self.root, self.db_path = root, db_path

    def paths(self, vid):
        return self.root / f'{vid}.md', self.root / f'{vid}.json', self.root / f'{vid}.complete'

    def stage(self, idx, start, through='complete_publication'):
        vid = start['capture_key'].split(':', 1)[1]
        corpus, sidecar, marker = self.paths(vid)
        url = f'https://www.youtube.com/watch?v={vid}'
        completed = self.stages[:self.stages.index(through) + 1]
        corpus.write_text('Fixture source evidence with actual timing.\n', encoding='utf-8')
        if 'sidecar' in completed:
            sidecar.write_text(json.dumps({'video_id': vid, 'url': url, 'platform': 'youtube',
                                          'source_type': 'video'}), encoding='utf-8')
        if 'item_upsert' in completed:
            idx.upsert_yoink(dict(video_id=vid, slug=vid, title='Fixture capture', topic='Unfiled',
                                 yoinked_at='2026-09-07', corpus_path=str(corpus), sidecar_path=str(sidecar),
                                 platform='youtube', source_type='video',
                                 metadata_json=json.dumps({'url': url})))
        with idx.write_transaction() as conn:
            if 'citations' in completed:
                conn.execute('''INSERT OR REPLACE INTO citations
                    (video_id,kind,seq,timestamp_start,timestamp_end,text,source_url,source_deep_link)
                    VALUES(?,'transcript_chunk',0,12.5,21.75,?,?,?)''',
                             (vid, 'Fixture source evidence.', url, url + '&t=12s'))
            if 'clips' in completed:
                conn.execute('''INSERT OR REPLACE INTO clips(video_id,seq,start,end,text,source_deep_link)
                                VALUES(?,0,12.5,21.75,?,?)''',
                             (vid, 'Fixture source evidence.', url + '&t=12s'))
        if 'complete_publication' in completed:
            marker.write_text(vid, encoding='utf-8')
        return vid

    def inspect(self, start):
        vid = start['capture_key'].split(':', 1)[1]
        corpus, sidecar, marker = self.paths(vid)
        with closing(sqlite3.connect(self.db_path)) as conn:
            complete = all(path.is_file() for path in (corpus, sidecar, marker)) and all(
                conn.execute(f'SELECT 1 FROM {table} WHERE video_id=?', (vid,)).fetchone()
                for table in ('yoinks', 'citations', 'clips'))
        return {'complete': bool(complete), 'video_id': vid}

    def reconcile(self, start):
        return self.inspect(start)


def race(*calls):
    barrier = threading.Barrier(len(calls))

    def run(call):
        barrier.wait(timeout=5)
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(run, call) for call in calls]
        return [future.result(timeout=10) for future in futures]


class Rig:
    def __init__(self, root, module):
        self.root, self.module = root, module
        self.path = root / 'service.db'
        self.clock, self.feed, self.faults = Clock(), Feed(), Faults()
        self.backend = Backend(self.path)
        self.publication = Publication(root, self.path)
        self.connections = []
        self.sequence = 0
        from library_work import RequestContext
        self.context = RequestContext(authenticated=True, operator=True,
                                      local_user_confirmed=True, session_id='astra-local', client_id='fixture')
        self.idx, self.svc = self.open()

    def open(self):
        from index import Index
        idx = Index.open(self.path)
        self.connections.append(idx)
        idx._conn.execute('PRAGMA busy_timeout=250')
        with idx.write_transaction() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS astra_fake_jobs(
                job_id TEXT PRIMARY KEY, start_id TEXT UNIQUE NOT NULL, owner_token TEXT NOT NULL)''')
        self.sequence += 1
        service = self.module.SourceSubscriptionService(
            idx, clock=self.clock, adapters={name: self.feed for name in (
                'podcast_rss_v1', 'youtube_channel_rss_v1', 'youtube_playlist_flat_v1')},
            capture_backend=self.backend, publication=self.publication,
            instance_id=f'astra-instance-{self.sequence}', crash_hook=self.faults)
        return idx, service

    def close(self):
        for idx in self.connections:
            idx.close()
        self.connections.clear()

    def restart(self):
        self.close()
        self.idx, self.svc = self.open()
        self.svc.reconcile()

    def register(self, number=1, kind='youtube_playlist'):
        key = ('UC' + f'{number:022d}') if kind == 'youtube_channel' else f'PL{number:010d}'
        url = f'https://www.youtube.com/channel/{key}' if kind == 'youtube_channel' else f'https://www.youtube.com/playlist?list={key}'
        args = dict(kind=kind, url=url, poll_interval_min=15)
        result = ok(self.svc.register_source(self.context, args))
        sid = result['source']['source_id']
        assert sid == 'src_' + digest(kind + '\n' + key)
        self.feed.responses[sid] = snapshot()
        return sid

    def operation(self, sid, state, key=None):
        row, cur = source_row(self.idx, sid), cursor_row(self.idx, sid)
        self.sequence += 1
        args = dict(source_id=sid, consent_state=state, expected_revision=row['revision'],
                    operation_key=key or f'consent-{self.sequence}')
        if state == 'on':
            args['expected_cursor_revision'] = cur['revision']
        token = ok(self.svc.mint_user_intent(self.context, {'operation': args}))['user_intent_token']
        return dict(args, user_intent_token=token)

    def consent(self, sid, state, key=None):
        args = self.operation(sid, state, key)
        return ok(self.svc.set_source_consent(self.context, args)), args

    def enrolled(self, count=2, number=1, kind='youtube_playlist', entries=None):
        sid = self.register(number, kind)
        self.consent(sid, 'on')
        self.feed.responses[sid] = snapshot(entries if entries is not None else [observation(n) for n in range(count)])
        self.svc.poll_source(sid)
        assert source_row(self.idx, sid)['initial_enrollment_completed_ms'] is not None
        return sid

    def reserve(self, sid, item=None, svc=None):
        item = item or next(row for row in item_rows(self.idx, sid) if row['state'] == 'eligible')
        before = {row['start_id'] for row in ledger(self.idx)}
        (svc or self.svc).reserve_capture(sid, item['item_id'])
        added = [row for row in ledger(self.idx) if row['start_id'] not in before]
        assert len(added) == 1 and added[0]['state'] == 'reserved', added
        assert added[0]['reservation_expires_ms'] - added[0]['reserved_at_ms'] == 120_000
        return added[0]

    def start(self, sid, item=None):
        reservation = self.reserve(sid, item)
        self.svc.dispatch_capture(reservation['start_id'], reservation['owner_token'])
        saved = next(row for row in ledger(self.idx) if row['start_id'] == reservation['start_id'])
        assert saved['state'] == 'started' and saved['started_at_ms'] == self.clock()
        return saved

    def failed(self, start):
        self.backend.workers[start['backend_id']] = 'stopped'
        self.svc.fail_capture(start['start_id'], start['owner_token'], code='download_failed')
        assert rows(self.idx, 'source_capture_starts', 'start_id=?', (start['start_id'],))[0]['state'] == 'failed'

    def complete(self, start):
        vid = self.publication.stage(self.idx, start)
        self.backend.workers[start['backend_id']] = 'stopped'
        self.svc.complete_capture(start['start_id'], start['owner_token'])
        assert rows(self.idx, 'source_capture_starts', 'start_id=?', (start['start_id'],))[0]['state'] == 'succeeded'
        return vid

    def allowance(self, sid):
        summary = ok(self.svc.source_status(self.context, {'source_id': sid}))['source']
        allowance = summary['allowance']
        today = [row for row in ledger(self.idx, sid) if row['utc_day'] == utc_day(self.clock())]
        charged = sum(row['started_at_ms'] is not None for row in today)
        reserved = sum(row['started_at_ms'] is None and row['state'] != 'released' for row in today)
        assert allowance['cap'] == 10
        assert allowance['charged'] == charged and allowance['reserved'] == reserved
        assert allowance['remaining'] == max(0, 10 - charged - reserved)
        assert allowance['utc_day'] == utc_day(self.clock())
        assert charged + reserved <= 10
        return allowance


@pytest.fixture
def rig(phase3_isolation, migration_dir, phase3_module):
    fixture = Rig(phase3_isolation, phase3_module)
    try:
        yield fixture
        assert fixture.idx._conn.execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        fixture.close()

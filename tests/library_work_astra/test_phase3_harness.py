"""Fixture self-checks, NOT S01-S17 implementation acceptance.

These run before implementation exists. The reference database uses the contract
DDL only to check fixture SQL, fake queue behavior and timed evidence. Acceptance
fixtures in support.py always require the actual shipped 0028; there is no fallback.
"""

import json
import os
import shutil
import socket
import sqlite3
import subprocess
from contextlib import closing

import pytest

from test_phase3_migration import seed_item, seed_source, seed_start
from test_phase3_support import (
    Backend, CONTRACT, Clock, Feed, Publication, ROOT, at,
    digest, phase3_isolation, race, snapshot, unavailable, utc_day,
)


@pytest.fixture
def reference_db(phase3_isolation, monkeypatch):
    import index
    target = phase3_isolation / 'reference-migrations'
    target.mkdir()
    for path in (ROOT / 'migrations').glob('*.sql'):
        if int(path.name.split('_', 1)[0]) <= 27:
            shutil.copy2(path, target / path.name)
    monkeypatch.setattr(index, '_MIGRATIONS_DIR', target)
    with index.Index.open(phase3_isolation / 'reference.db') as idx:
        assert idx.schema_version() == 27
        document = CONTRACT.read_text(encoding='utf-8')
        fence = chr(96) * 3
        ddl = document.split(fence + 'sql\n', 1)[1].split('\n' + fence, 1)[0]
        idx._conn.executescript(ddl)
        with idx.write_transaction() as conn:
            conn.execute('CREATE TABLE astra_fake_jobs(job_id TEXT PRIMARY KEY, start_id TEXT UNIQUE, owner_token TEXT)')
        yield idx
        assert idx._conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert idx._conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


@pytest.mark.parametrize('operation', ['dns', 'connect', 'bind', 'subprocess', 'shell', 'outside-db'])
def test_fixture_blocks_real_io(phase3_isolation, operation):
    with pytest.raises(AssertionError):
        if operation == 'dns':
            socket.getaddrinfo('example.org', 443)
        elif operation in ('connect', 'bind'):
            with socket.socket() as sock:
                getattr(sock, operation)(('127.0.0.1', 1))
        elif operation == 'subprocess':
            subprocess.Popen(['this-must-never-launch'])
        elif operation == 'shell':
            os.system('this-must-never-launch')
        else:
            sqlite3.connect(ROOT / 'must-never-open.db')


def test_fixture_strict_integration_mode_does_not_skip(monkeypatch):
    monkeypatch.setenv('PHASE3_REQUIRE_IMPLEMENTATION', '1')
    with pytest.raises(pytest.fail.Exception, match='AM integration pending'):
        unavailable('synthetic missing component')
    monkeypatch.delenv('PHASE3_REQUIRE_IMPLEMENTATION')
    with pytest.raises(pytest.skip.Exception, match='AM integration pending'):
        unavailable('synthetic missing component')


def test_fixture_clock_is_explicit_utc_even_on_dst_boundary():
    clock = Clock(at('2026-11-01T23:59:59Z'))
    assert utc_day(clock()) == '2026-11-01'
    clock.advance(2_000)
    assert utc_day(clock()) == '2026-11-02'
    assert clock() == at('2026-11-01T16:00:01-08:00')


def test_fixture_adapter_copies_observations_and_never_dispatches():
    feed = Feed()
    source, cursor = {'source_id': 'fixture'}, {'revision': 1}
    response = snapshot([{'entry_id': 'v0000000001', 'title': 'Original'}])
    feed.responses['fixture'] = response
    result = feed.fetch(source, cursor)
    result['observations'][0]['title'] = 'Mutated by caller'
    assert response['observations'][0]['title'] == 'Original'
    source['source_id'] = 'mutated'
    assert feed.calls[0][0]['source_id'] == 'fixture'


def test_fixture_two_connections_share_db_but_not_python_locks(reference_db):
    with closing(sqlite3.connect(reference_db._path, check_same_thread=False)) as other:
        assert other is not reference_db._conn
        other.execute('PRAGMA busy_timeout=100')
        with reference_db.write_transaction() as conn:
            seed_source(conn)
            assert other.execute('SELECT COUNT(*) FROM source_subscriptions').fetchone()[0] == 0
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                other.execute('BEGIN IMMEDIATE')
        assert other.execute('SELECT COUNT(*) FROM source_subscriptions').fetchone()[0] == 1
    assert sorted(race(lambda: 1, lambda: 2)) == [1, 2]


@pytest.mark.parametrize('state', ['reserved', 'released', 'started', 'uncertain', 'failed', 'succeeded'])
def test_fixture_ledger_seed_matches_normative_ddl(reference_db, state):
    with reference_db.write_transaction() as conn:
        sid = seed_source(conn)
        iid = seed_item(conn, sid, 'v0000000001')
        seed_start(conn, sid, iid, 'v0000000001', state=state)
    row = dict(reference_db._conn.execute('SELECT * FROM source_capture_starts').fetchone())
    assert row['state'] == state
    assert (row['started_at_ms'] is None) == (state in ('reserved', 'released'))


def test_fixture_queue_requires_transaction_and_visible_started_binding(reference_db):
    backend = Backend(reference_db._path)
    with reference_db.write_transaction() as conn:
        sid = seed_source(conn)
        iid = seed_item(conn, sid, 'v0000000001')
        seed_start(conn, sid, iid, 'v0000000001')
    start = dict(reference_db._conn.execute('SELECT * FROM source_capture_starts').fetchone())
    with pytest.raises(AssertionError, match='transaction'):
        backend.enqueue(reference_db._conn, start)
    with pytest.raises(RuntimeError, match='rollback'), reference_db.write_transaction() as conn:
        backend.enqueue(conn, start)
        raise RuntimeError('rollback')
    assert reference_db._conn.execute('SELECT COUNT(*) FROM astra_fake_jobs').fetchone()[0] == 0
    with reference_db.write_transaction() as conn:
        binding = backend.enqueue(conn, start)
        conn.execute('UPDATE source_capture_starts SET backend_kind=?,backend_id=?',
                     (binding['backend_kind'], binding['backend_id']))
    with pytest.raises(AssertionError):
        backend.dispatch(start['start_id'], start['owner_token'])
    with reference_db.write_transaction() as conn:
        conn.execute("UPDATE source_capture_starts SET state='started',started_at_ms=reserved_at_ms")
    backend.dispatch(start['start_id'], start['owner_token'])
    with pytest.raises(AssertionError, match='Duplicate dispatch'):
        backend.dispatch(start['start_id'], start['owner_token'])
    assert len(backend.launches) == 1


def test_fixture_publication_prefixes_and_real_phase2_prepare(reference_db, phase3_isolation):
    from library_work import LibraryWorkService, RequestContext
    publication = Publication(phase3_isolation, reference_db._path)
    start = {'capture_key': 'youtube:v0000000001'}
    for stage in Publication.stages:
        publication.stage(reference_db, start, stage)
        assert publication.inspect(start)['complete'] == (stage == 'complete_publication')
    service = LibraryWorkService(reference_db, phase3_isolation / 'library', clock=Clock())
    context = RequestContext(authenticated=True, operator=True, local_user_confirmed=True,
                             session_id='fixture', client_id='fixture')
    result = service.approve_taxonomy(context, dict(version_id='fixture-v1', nodes=[dict(
        shelf_id='testing', path=['Testing'], definition='Fixture evidence',
        include=['tests'], exclude=['unrelated'])]))
    assert result['ok'], result
    args = dict(run_id='fixture-run', version_id='fixture-v1',
                video_ids=['v0000000001'], prompt_hash=digest('fixture prompt'))
    result = service.prepare_run(context, args)
    assert result['ok'], result
    before = [tuple(row) for row in reference_db._conn.execute('SELECT * FROM library_work')]
    assert len(before) == 1
    assert service.prepare_run(context, args)['error']['code'] == 'idempotency_conflict'
    assert [tuple(row) for row in reference_db._conn.execute('SELECT * FROM library_work')] == before
    work = dict(reference_db._conn.execute('SELECT * FROM library_work').fetchone())
    assert work['state'] == 'ready'
    packet = json.loads(work['packet_json'])
    assert packet['card']['excerpts'][0]['start'] == 12.5
    assert packet['card']['excerpts'][0]['end'] == 21.75
    assert reference_db._conn.execute('SELECT COUNT(*) FROM library_attempts').fetchone()[0] == 0

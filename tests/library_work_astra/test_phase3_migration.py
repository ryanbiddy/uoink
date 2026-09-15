"""S01 and SQL backstops for S10/S12/S14/S15, against shipped 0028 only.

Replaying a no-op Index.open is insufficient: S01 removes ONLY the fixture's
version-28 checkpoint and observes the real runner executing 0028 a second time.
No production database, migration, or legacy flag is modified by these tests.
"""

import json
import re
import sqlite3
from contextlib import closing

import pytest

from test_phase3_support import (
    CONTRACT, TABLES, at, digest, ledger, migration_dir, phase3_db,
    phase3_isolation, phase3_module, rig, rows, source_row, utc_day,
)


def seed_source(conn, number=1):
    key = f'PL{number:010d}'
    sid = 'src_' + digest('youtube_playlist\n' + key)
    conn.execute('''INSERT INTO source_subscriptions
        (source_id,kind,source_key,canonical_url,adapter,created_at_ms,updated_at_ms)
        VALUES(?,'youtube_playlist',?,?,'youtube_playlist_flat_v1',?,?)''',
                 (sid, key, f'https://www.youtube.com/playlist?list={key}', 0, 0))
    return sid


def seed_item(conn, sid, entry):
    iid = 'si_' + digest(sid + '\n' + entry)
    conn.execute('''INSERT INTO source_items
        (item_id,source_id,entry_id,capture_key,first_seen_ms,last_seen_ms,first_scan_revision,metadata_json)
        VALUES(?,?,?,?,0,0,1,'{}')''', (iid, sid, entry, 'youtube:' + entry))
    return iid


def seed_start(conn, sid, iid, entry, *, name='start', slot=1, state='reserved', now=None,
               backend_kind=None, backend_id=None):
    now = at('2026-09-07T12:00:00Z') if now is None else now
    started = None if state in ('reserved', 'released') else now
    conn.execute('''INSERT INTO source_capture_starts
        (start_id,source_id,item_id,capture_key,consent_epoch,utc_day,slot,state,
         reserved_at_ms,reservation_expires_ms,started_at_ms,owner_token,owner_instance,backend_kind,backend_id)
        VALUES(?,?,?,?,1,?,?,?,?,?,?,?,?,?,?)''',
                 (name, sid, iid, 'youtube:' + entry, utc_day(now), slot, state,
                  now, now + 120_000, started, 'x' * 43, 'fixture', backend_kind, backend_id))


def snapshot_tables(idx):
    return {table: rows(idx, table) for table in TABLES}


@pytest.mark.parametrize('populated', [False, True], ids=['empty-27', 'legacy-27'])
def test_s01_migration_executes_twice_through_real_runner(phase3_isolation, migration_dir, populated):
    from index import Index, _run_migrations
    migration = migration_dir / '0028_source_subscriptions.sql'
    ddl = migration.read_text(encoding='utf-8')
    migration.unlink()  # The disposable migration copy only.
    path = phase3_isolation / 'migration.db'
    with Index.open(path) as idx:
        assert idx.schema_version() == 27
        if populated:
            with idx.write_transaction() as conn:
                conn.execute('''INSERT INTO podcast_feeds(id,feed_url,title,added_at,auto_ingest)
                                VALUES(71,'https://example.org/feed.xml','Fixture','2026-09-06',1)''')
                conn.execute('''INSERT INTO monitored_playlists(id,playlist_url,name,added_at)
                                VALUES(91,'https://www.youtube.com/playlist?list=PL0000000001','Fixture','2026-09-06')''')
                conn.execute('''INSERT INTO podcast_episodes(feed_id,guid,title,discovered_at,auto_ingest_requested)
                                VALUES(71,'legacy-guid','Fixture episode','2026-09-06',1)''')
        migration.write_text(ddl, encoding='utf-8')
        trace = []
        idx._conn.set_trace_callback(trace.append)
        assert _run_migrations(idx._conn) == 28
        assert all(not values for values in snapshot_tables(idx).values()), 'DDL itself imported/authorized work'
        assert rows(idx, 'library_runs') == rows(idx, 'library_work') == []
        with idx.write_transaction() as conn:
            sid = seed_source(conn)
            iid = seed_item(conn, sid, 'v0000000001')
            seed_start(conn, sid, iid, 'v0000000001', state='failed')
        before = snapshot_tables(idx)
        objects = [tuple(row) for row in idx._conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name LIKE 'source_%' ORDER BY name")]
        with idx.write_transaction() as conn:
            conn.execute('DELETE FROM schema_version WHERE version=28')
        assert _run_migrations(idx._conn) == 28
        assert snapshot_tables(idx) == before
        assert objects == [tuple(row) for row in idx._conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name LIKE 'source_%' ORDER BY name")]
        executions = [sql for sql in trace if re.search(
            r'\bCREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+source_subscriptions\b', sql, re.I)]
        assert len(executions) == 2, '0028 was not actually replayed'
        assert idx._conn.execute('SELECT COUNT(*) FROM schema_version WHERE version=28').fetchone()[0] == 1
        assert idx._conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert idx._conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert len(rows(idx, 'podcast_feeds')) == int(populated)
        assert len(rows(idx, 'monitored_playlists')) == int(populated)
    with Index.open(path) as idx:
        assert idx.schema_version() == 28
        assert snapshot_tables(idx) == before


def test_s01_failed_migration_rolls_back_and_can_retry(phase3_isolation, migration_dir):
    from index import Index
    migration = migration_dir / '0028_source_subscriptions.sql'
    ddl = migration.read_text(encoding='utf-8')
    migration.unlink()
    path = phase3_isolation / 'rollback.db'
    with Index.open(path) as idx:
        assert idx.schema_version() == 27
    migration.write_text(ddl + '\nTHIS IS NOT SQL;\n', encoding='utf-8')
    with pytest.raises(sqlite3.Error):
        Index.open(path)
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute('SELECT MAX(version) FROM schema_version').fetchone()[0] == 27
        assert conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'source_%'").fetchall() == []
    migration.write_text(ddl, encoding='utf-8')
    with Index.open(path) as idx:
        assert idx.schema_version() == 28
        assert all(not values for values in snapshot_tables(idx).values())


def test_s01_startup_legacy_import_preserves_first_receipt_and_cutover_hold(rig):
    with rig.idx.write_transaction() as conn:
        conn.execute('''INSERT INTO podcast_feeds(id,feed_url,title,added_at,auto_ingest,enabled)
                        VALUES(71,'https://example.org/feed.xml','Fixture','2026-09-06',1,0)''')
        conn.execute('''INSERT INTO monitored_playlists(id,playlist_url,name,added_at,poll_interval_min)
                        VALUES(91,'https://www.youtube.com/playlist?list=PL0000000001','Fixture','2026-09-06',5)''')
    rig.restart()
    feeds = rows(rig.idx, 'source_subscriptions', 'legacy_feed_id=71')
    playlists = rows(rig.idx, 'source_subscriptions', 'legacy_playlist_id=91')
    assert len(feeds) == len(playlists) == 1
    feed, playlist = feeds[0], playlists[0]
    assert (feed['consent_state'], feed['boundary'], feed['detection_enabled']) == ('on', 'initial', 0)
    assert playlist['consent_state'] == 'off' and playlist['poll_interval_min'] == 15
    expected_hold = at('2026-09-08T00:00:00Z')
    assert feed['accounting_hold_until_ms'] == playlist['accounting_hold_until_ms'] == expected_hold
    receipt = rows(rig.idx, 'source_consent_receipts', "authority='legacy_explicit_opt_in'")
    assert len(receipt) == 1
    rig.clock.advance(2 * 24 * 60 * 60_000)
    rig.restart()
    assert rows(rig.idx, 'source_consent_receipts', "authority='legacy_explicit_opt_in'") == receipt
    for before in (feed, playlist):
        after = source_row(rig.idx, before['source_id'])
        for key in ('source_id', 'accounting_hold_until_ms', 'back_catalog_enrolled', 'consent_epoch', 'boundary'):
            assert after[key] == before[key]
    assert ledger(rig.idx) == rows(rig.idx, 'library_work') == []
    assert rig.feed.calls == rig.backend.launches == []


@pytest.mark.parametrize('slot', [0, 11, -1])
def test_s10_sql_rejects_slot_outside_ten(phase3_db, slot):
    with phase3_db.write_transaction() as conn:
        sid = seed_source(conn)
        iid = seed_item(conn, sid, 'v0000000001')
    with pytest.raises(sqlite3.IntegrityError), phase3_db.write_transaction() as conn:
        seed_start(conn, sid, iid, 'v0000000001', slot=slot)


@pytest.mark.parametrize('first_state', ['reserved', 'started', 'uncertain', 'succeeded', 'failed'])
def test_s10_sql_occupied_slot_cannot_be_reused(phase3_db, first_state):
    with phase3_db.write_transaction() as conn:
        sid = seed_source(conn)
        first = seed_item(conn, sid, 'v0000000001')
        second = seed_item(conn, sid, 'v0000000002')
        seed_start(conn, sid, first, 'v0000000001', state=first_state)
    with pytest.raises(sqlite3.IntegrityError), phase3_db.write_transaction() as conn:
        seed_start(conn, sid, second, 'v0000000002', name='duplicate-slot', state='failed')


def test_s10_sql_released_slot_reusable_and_second_source_independent(phase3_db):
    with phase3_db.write_transaction() as conn:
        sid = seed_source(conn)
        other = seed_source(conn, 2)
        first = seed_item(conn, sid, 'v0000000001')
        second = seed_item(conn, sid, 'v0000000002')
        third = seed_item(conn, other, 'v0000000003')
        seed_start(conn, sid, first, 'v0000000001', state='released')
        seed_start(conn, sid, second, 'v0000000002', name='reuse', state='failed')
        seed_start(conn, other, third, 'v0000000003', name='independent', state='failed')
    assert len(ledger(phase3_db)) == 3


@pytest.mark.parametrize('state', ['reserved', 'started', 'uncertain'])
def test_s10_sql_one_active_pipeline_per_source(phase3_db, state):
    with phase3_db.write_transaction() as conn:
        sid = seed_source(conn)
        first = seed_item(conn, sid, 'v0000000001')
        second = seed_item(conn, sid, 'v0000000002')
        seed_start(conn, sid, first, 'v0000000001', state=state)
    with pytest.raises(sqlite3.IntegrityError), phase3_db.write_transaction() as conn:
        seed_start(conn, sid, second, 'v0000000002', name='second', slot=2)


@pytest.mark.parametrize('state', ['reserved', 'started', 'uncertain', 'succeeded'])
def test_s15_sql_global_key_owned_including_success(phase3_db, state):
    with phase3_db.write_transaction() as conn:
        sid, other = seed_source(conn), seed_source(conn, 2)
        first = seed_item(conn, sid, 'v0000000001')
        second = seed_item(conn, other, 'v0000000001')
        seed_start(conn, sid, first, 'v0000000001', state=state)
    with pytest.raises(sqlite3.IntegrityError), phase3_db.write_transaction() as conn:
        seed_start(conn, other, second, 'v0000000001', name='duplicate-key')


@pytest.mark.parametrize('change', [
    {'utc_day': '2026-09-06'}, {'slot': 11}, {'owner_token': 'short'},
    {'state': 'released', 'started_at_ms': at('2026-09-07T23:59:59Z')},
    {'state': 'started', 'started_at_ms': None},
    {'state': 'started', 'started_at_ms': at('2026-09-08T00:00:01Z')},
    {'state': 'started', 'started_at_ms': at('2026-09-07T23:59:58Z')},
    {'backend_kind': 'queue', 'backend_id': None},
])
def test_s12_sql_rejects_invalid_dispatch_and_binding(phase3_db, change):
    with phase3_db.write_transaction() as conn:
        sid = seed_source(conn)
        iid = seed_item(conn, sid, 'v0000000001')
        seed_start(conn, sid, iid, 'v0000000001', now=at('2026-09-07T23:59:59Z'))
    assignments = ','.join(f'{key}=?' for key in change)
    with pytest.raises(sqlite3.IntegrityError), phase3_db.write_transaction() as conn:
        conn.execute(f'UPDATE source_capture_starts SET {assignments}', tuple(change.values()))


def test_s14_sql_backend_binding_and_source_item_fk(phase3_db):
    with phase3_db.write_transaction() as conn:
        sid, other = seed_source(conn), seed_source(conn, 2)
        first = seed_item(conn, sid, 'v0000000001')
        second = seed_item(conn, other, 'v0000000002')
        seed_start(conn, sid, first, 'v0000000001', state='failed', backend_kind='queue', backend_id='one')
    with pytest.raises(sqlite3.IntegrityError), phase3_db.write_transaction() as conn:
        seed_start(conn, other, second, 'v0000000002', name='bad-backend', backend_kind='queue', backend_id='one')
    with pytest.raises(sqlite3.IntegrityError), phase3_db.write_transaction() as conn:
        seed_start(conn, other, first, 'v0000000001', name='foreign-item')


def test_registry_tool_schemas_match_frozen_contract(phase3_module):
    import uoink_mcp_tools
    document = CONTRACT.read_text(encoding='utf-8')
    frozen = json.loads(document.split('```json\n', 1)[1].split('\n```', 1)[0])
    actual = {tool['name']: tool['inputSchema'] for tool in uoink_mcp_tools.list_tools()}
    for tool in frozen['tools']:
        assert actual.get(tool['name']) == tool['inputSchema'], tool['name']
    assert 'source_consent_intent' not in actual
    assert 'mint_source_user_intent' not in actual

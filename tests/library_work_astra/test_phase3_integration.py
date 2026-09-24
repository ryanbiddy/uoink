"""Execute selected production definitions without importing/starting the helper.

AST selection preserves the function/class bodies from this checkout. Explicit
globals replace I/O and scheduling only. These tests are not installed-tree or
interprocess evidence; S21/S22 still require Fable's disposable helper.
"""

import ast
import copy
import json
import logging
import threading
from types import SimpleNamespace

import pytest

from test_phase3_support import (
    ROOT, cursor_row, item_rows, ledger, migration_dir, observation, ok,
    phase3_isolation, phase3_module, rig, snapshot,
)


def server_parts(rig):
    names = {
        '_ServerCaptureBackend', '_find_job_for_start', '_source_instance_id',
        '_standing_due_polls', '_poll_source_for_watch', '_standing_capture_pass',
        '_podcast_feed_scheduler_tick',
    }
    path = ROOT / 'server.py'
    parsed = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    nodes = [node for node in parsed.body if getattr(node, 'name', None) in names]
    assert {node.name for node in nodes} == names
    launches = []

    class DormantThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            launches.append(self.kwargs)

        def is_alive(self):
            return True

    namespace = dict(
        source_subscriptions=rig.module, json=json, log=logging.getLogger('astra'),
        threading=SimpleNamespace(Thread=DormantThread),
        socket=SimpleNamespace(gethostname=lambda: 'fixture-host'), DATA_ROOT=rig.root,
        _source_capture_threads={}, _source_capture_threads_lock=threading.RLock(),
        _jobs={}, _jobs_lock=threading.RLock(),
        _JOB_TERMINAL_STATES={'completed', 'failed', 'cancelled'},
        _extract_lock=threading.Lock(), _source_service=lambda: rig.svc.service,
        _get_index=lambda: rig.idx, maybe_toast=lambda *a, **k: None,
        _heartbeat_note_poll=lambda *a, **k: None,
        _heartbeat_note_ingest=lambda: None, _heartbeat_note_tick=lambda **k: None,
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    namespace['launches'] = launches
    return namespace


@pytest.mark.parametrize('job_state', [None, 'queued', 'running'])
def test_s13_server_probe_does_not_infer_death_from_install_identity(rig, job_state):
    sid = rig.enrolled(1)
    start = rig.start(sid)
    ns = server_parts(rig)
    start['owner_instance'] = ns['_source_instance_id']()
    if job_state:
        ns['_jobs']['job-fixture'] = dict(source_start_id=start['start_id'], state=job_state)
    # No thread in this process is not proof about another process, its child,
    # or the separate podcast worker. No stopped-process evidence is supplied.
    assert ns['_ServerCaptureBackend']().probe(start) in ('unknown', 'running')


def test_s09_server_tick_recovers_expired_poll_ownership(rig):
    sid = rig.register()
    claim = rig.svc.claim_poll(sid)
    assert claim
    rig.clock.advance(120_001)
    ns = server_parts(rig)
    ns['_podcast_feed_scheduler_tick']()
    cursor = cursor_row(rig.idx, sid)
    assert cursor['poll_owner_token'] is None, 'Expired poll is stranded until helper restart'
    assert cursor['last_error_code'] == 'poll_timeout'
    assert cursor['next_poll_at_ms'] > rig.clock()
    assert rig.feed.calls == []


def test_s09_server_tick_does_not_expire_queued_polls_before_fetch(rig):
    sources = [rig.register(number=n) for n in range(16)]
    for sid in sources:
        rig.feed.responses[sid] = snapshot([observation(1)])

    class BoundedSlowFeed:
        def poll(self, source, cursor, *, conditional):
            # Each individual fake invocation fits the eight-second HTTP budget.
            rig.clock.advance(8_000)
            return rig.feed.poll(source, cursor, conditional=conditional)

    service = rig.module.SourceSubscriptionService(
        rig.idx, clock=rig.clock, adapters={name: BoundedSlowFeed() for name in rig.module.ADAPTERS.values()},
        backend=rig.backend)
    ns = server_parts(rig)
    ns['_source_service'] = lambda: service
    results = ns['_podcast_feed_scheduler_tick']()
    assert len(results) == 16
    assert all(result['ok'] for result in results), results
    assert all(cursor_row(rig.idx, sid)['revision'] == 1 for sid in sources)


def test_s15_podcast_short_id_collision_is_visible_and_never_links(rig):
    feed_url, guid = 'https://show.example/feed.xml', 'incoming-guid'
    vid = rig.module.podcast_corpus_id(feed_url, guid)
    # Seed a conflicting full identity at the deterministic shortened key.
    # This models a collision/import corruption without a hash brute force.
    rig.idx.upsert_yoink(dict(
        video_id=vid, slug=vid, title='Unrelated episode', topic='Unfiled',
        yoinked_at='2026-09-07', source_type='episode', platform='podcast',
        corpus_path=str(rig.root / 'unrelated.md'),
        sidecar_path=str(rig.root / 'unrelated.json'),
        metadata_json=json.dumps(dict(feed_url='https://other.example/feed.xml', guid='other-guid'))))
    before = copy.deepcopy(rig.idx.get_yoink(vid))
    sid = ok(rig.svc.register_source(rig.context, dict(kind='podcast_rss', url=feed_url)))['source']['source_id']
    rig.consent(sid, 'on')
    rig.feed.responses[sid] = snapshot([dict(entry_id=guid, title='Incoming episode')])
    rig.svc.poll_source(sid)
    item = item_rows(rig.idx, sid)[0]
    rig.svc.claim_start(sid, item_id=item['item_id'])
    item = item_rows(rig.idx, sid)[0]
    assert item['state'] != 'committed' and item['video_id'] is None, item
    assert item['blocked_reason'], 'Full-identity mismatch needs a visible conflict'
    assert ledger(rig.idx) == [] and rig.backend.launches == []
    assert rig.idx.get_yoink(vid) == before

"""Automatic podcast metadata watch and standing capture contracts.

Phase 3 alignment (run AP, 2026-09-07). These tests encode contract
``phase3-v1-2026-09-07`` (docs/library/PHASE3-CONTRACT-2026-09-07.md) in place
of the pre-contract watch semantics they replaced:

* ``add_feed`` projects an off standing source. The old boolean can neither
  opt a feed in nor authorize anything; consent needs the confirmed operation
  and its receipt (contract, "Consent and enrollment").
* Detection never captures. The scheduler tick claims due polls and records
  observations; a separate capture pass advances work only through the atomic
  ledger reservation (contract, "Scheduler and adapter boundaries").
* Standing capture never implies model consent: the server backend queues the
  transcription with ``consent_given=False`` and refuses at preflight while
  transcription setup or the model download is missing.

Run: python -m pytest -q tests/test_podcast_watch.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_subscriptions_fixtures import (  # noqa: E402
    Clock, FakeAdapter, FakeBackend, MINUTE_MS, make_service, rows, snapshot, starts, status,
    turn_on,
)

import index as index_mod  # noqa: E402
import podcasts  # noqa: E402
import server  # noqa: E402
import source_subscriptions as ss  # noqa: E402


def _episode(guid: str, title: str) -> dict:
    return {
        "guid": guid,
        "title": title,
        "audio_url": f"https://cdn.example/{guid}.mp3",
        "episode_page_url": f"https://show.example/{guid}",
        "published_at": "2026-08-01T12:00:00Z",
    }


def _wall_clock() -> Clock:
    """The old add routes stamp their source rows with the real clock, so a
    service driving those rows must start at or after that instant (a fixed
    T0 would look like a clock regression)."""
    return Clock(int(time.time() * 1000))


def _raise(message: str):
    raise AssertionError(message)


def test_add_feed_projects_an_off_source_and_the_old_boolean_cannot_opt_in(tmp_path):
    db_path = tmp_path / "index.db"
    idx = index_mod.Index.open(db_path)
    feed = podcasts.add_feed(idx, "https://show.example/feed.xml", poll_interval_min=60)
    assert feed["auto_ingest"] == 0
    source_id = feed["source_id"]
    assert ss.legacy_source_id(idx._conn, feed_id=feed["id"]) == source_id

    # The old boolean route can no longer grant consent (contract, "Consent
    # and enrollment": a user-confirmed operation and a receipt are required).
    with pytest.raises(podcasts.ManagedBySubscription) as refused:
        podcasts.set_feed_auto_ingest(idx, feed["id"], True)
    assert refused.value.source_id == source_id
    assert podcasts.get_feed(idx, feed["id"])["auto_ingest"] == 0
    # Re-adding with the old opt-in flag returns the same off source and says
    # that consent is a separate step.
    again = podcasts.add_feed(idx, "https://show.example/feed.xml", auto_ingest=True)
    assert again["id"] == feed["id"] and again["auto_ingest"] == 0
    assert again["source_id"] == source_id and again["consent_required"] is True

    # Episodes written through the old path carry no marker; nothing is a candidate.
    assert podcasts.upsert_episodes(
        idx, feed["id"], [_episode("before", "Before opt-in")]) == (1, 0)
    assert podcasts.list_episodes(idx, feed_id=feed["id"])[0]["auto_ingest_requested"] == 0
    assert podcasts.list_auto_ingest_candidates(idx, feed_id=feed["id"], limit=10) == []

    clock = _wall_clock()
    service = make_service(idx, clock=clock)
    summary = status(service, source_id)["source"]
    assert summary["consent_state"] == "off" and summary["revision"] == 0
    assert summary["consent_epoch"] == 0 and summary["boundary"] == "none"
    assert summary["detection_enabled"] is True and summary["archived"] is False
    assert summary["legacy"]["feed_id"] == feed["id"]
    assert summary["enrollment"]["initial_completed"] is False
    assert summary["enrollment"]["remaining_initial_slots"] == 25
    # A projection is not a cutover import: no hold, no receipt.
    assert summary["allowance"]["hold_reason"] is None
    assert rows(service, "SELECT COUNT(*) AS n FROM source_consent_receipts")[0]["n"] == 0

    # Only the confirmed consent operation turns capture on, and it is receipted.
    receipt = turn_on(service, source_id)
    assert receipt["changed"] is True and receipt["consent_state"] == "on"
    assert receipt["before_revision"] == 0 and receipt["after_revision"] == 1
    assert receipt["boundary"] == "initial", "no new start before the initial snapshot"
    idx.close()

    # Durable across a helper restart: consent, its receipt and the schema
    # version survive; the old flag stays a projection that authorizes nothing.
    idx = index_mod.Index.open(db_path)
    assert podcasts.get_feed(idx, feed["id"])["auto_ingest"] == 0
    service = make_service(idx, clock=clock)
    summary = status(service, source_id)["source"]
    assert summary["consent_state"] == "on" and summary["revision"] == 1
    assert summary["boundary"] == "initial" and summary["enrollment"]["pending"] is True
    assert [r["authority"] for r in rows(
        service, "SELECT authority FROM source_consent_receipts")] == ["local_user"]
    assert podcasts.list_auto_ingest_candidates(idx, feed_id=feed["id"], limit=10) == [], \
        "consent without a started ledger row authorizes nothing"
    assert idx._conn.execute(
        "SELECT MAX(version) FROM schema_version").fetchone()[0] == index_mod.latest_schema_version()
    idx.close()


def test_scheduler_tick_polls_only_due_sources_and_never_captures_from_detection(
        tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    due = podcasts.add_feed(idx, "https://due.example/feed.xml")
    future = podcasts.add_feed(idx, "https://future.example/feed.xml")
    clock = _wall_clock()
    adapter = FakeAdapter([snapshot(["new"], titles={"new": "Fresh episode"})])
    backend = FakeBackend()
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    with idx.write_transaction() as conn:
        # The subscription cursor is the only scheduling authority: the future
        # source is not due for half an hour, while the due feed's legacy
        # last_polled_at column says "never poll again" and is ignored.
        conn.execute(
            "UPDATE source_detection_cursors SET next_poll_at_ms=? WHERE source_id=?",
            (clock.now + 30 * MINUTE_MS, future["source_id"]))
        conn.execute(
            "UPDATE podcast_feeds SET last_polled_at=? WHERE id=?",
            ("2999-01-01T00:00:00Z", due["id"]))
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_source_service", lambda: service)
    toasts = []
    monkeypatch.setattr(server, "maybe_toast",
                        lambda title, body, **_kw: toasts.append((title, body)))
    monkeypatch.setattr(
        server, "_auto_ingest_podcast_feed",
        lambda _feed_id: _raise("the tick must not route capture through the legacy feed helper"))

    results = server._podcast_feed_scheduler_tick()

    assert [c["source_id"] for c in adapter.calls] == [due["source_id"]]
    assert len(results) == 1 and results[0]["ok"] is True
    assert results[0]["source_id"] == due["source_id"] and results[0]["outcome"] == "snapshot"
    assert results[0]["inserted"] == 1 and results[0]["enrollment"] is None
    # Detection persisted the observation as metadata only: the source is off.
    item = rows(service, "SELECT * FROM source_items WHERE source_id=?", (due["source_id"],))[0]
    assert item["entry_id"] == "new" and item["state"] == "observed"
    assert item["eligibility"] == "none" and item["first_seen_consent_epoch"] is None
    # The old episode row exists for the legacy pipeline but carries no marker.
    episode = podcasts.list_episodes(idx, feed_id=due["id"])[0]
    assert episode["guid"] == "new" and episode["auto_ingest_requested"] == 0
    assert item["legacy_episode_id"] == episode["id"]
    # No capture from detection: no reservation, no backend run, no candidate.
    assert starts(service) == [] and backend.runs == []
    assert podcasts.list_auto_ingest_candidates(idx, feed_id=due["id"], limit=10) == []
    # Run AM raises no discovery notification for a metadata-only source; only
    # enrollment of a consented source does (see the consented-source test).
    assert toasts == []

    # The future source is polled once its own cursor says so.
    clock.advance(30 * MINUTE_MS)
    results = server._podcast_feed_scheduler_tick()
    assert [c["source_id"] for c in adapter.calls] == [due["source_id"], future["source_id"]]
    assert len(results) == 1 and results[0]["source_id"] == future["source_id"]
    assert backend.runs == []
    idx.close()


def test_standing_podcast_capture_queues_publish_without_model_consent(
        tmp_path, monkeypatch):
    """Phase 0 protection kept: the automatic path downloads and queues the
    transcription for corpus publication without ever implying model consent,
    and standing capture never authorizes a first model download."""
    idx = index_mod.Index.open(tmp_path / "index.db")
    feed = podcasts.add_feed(idx, "https://auto.example/feed.xml")
    podcasts.upsert_episodes(idx, feed["id"], [_episode("auto", "Auto")])
    episode_id = podcasts.list_episodes(idx, feed_id=feed["id"])[0]["id"]
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_read_settings", lambda: {
        "whisper_model": "base", "diarization_default": False})
    audio = tmp_path / "auto.mp3"
    audio.write_bytes(b"audio")
    source = {"source_id": feed["source_id"], "kind": "podcast_rss",
              "source_key": feed["feed_url"], "legacy_feed_id": feed["id"]}
    item = {"item_id": "si_auto", "entry_id": "auto", "legacy_episode_id": episode_id,
            "metadata_json": json.dumps({"audio_url": "https://cdn.example/auto.mp3"})}
    start = {"start_id": "st_watch", "owner_token": "o" * 43}
    backend = server._ServerCaptureBackend()

    # Preflight refuses (non-terminally) while the model is not downloaded.
    monkeypatch.setattr(server.whisper_runner, "is_whisperx_available", lambda: True)
    monkeypatch.setattr(server.whisper_runner, "is_model_downloaded", lambda _root, _model: False)
    refused = backend.preflight(item, source)
    assert refused.status == "preflight_failed"
    assert refused.code == "missing_transcription_setup" and refused.terminal is False
    monkeypatch.setattr(server.whisper_runner, "is_model_downloaded", lambda _root, _model: True)
    assert backend.preflight(item, source) is None
    assert backend.preflight({**item, "legacy_episode_id": None}, source).code == "missing_episode_row"
    no_audio = backend.preflight({**item, "metadata_json": "{}"}, source)
    assert no_audio.code == "no_audio_url" and no_audio.terminal is True

    downloads = []
    monkeypatch.setattr(
        podcasts, "download_episode_audio",
        lambda _idx, requested_id, **_kwargs: (
            downloads.append(requested_id) or
            {"ok": True, "episode_id": requested_id, "local_path": str(audio)}))
    queued = []
    monkeypatch.setattr(
        server, "_queue_podcast_transcription",
        lambda requested_id, **kwargs: (
            queued.append((requested_id, kwargs)) or
            ({"ok": True, "job_id": "watch-job"}, 202)))

    # AS-02 (run AT-4): a backend executes only a start whose persisted execution
    # claim this incarnation holds; an unclaimed start is left to its executor
    # (``uncertain``) rather than run twice. The dispatcher claims before run().
    unclaimed = backend.run(start, item, source)
    assert unclaimed.status == "uncertain" and downloads == [] and queued == []
    assert backend.claim_execution(start, "watch-instance")["outcome"] == "claimed"
    outcome = backend.run(start, item, source)
    assert outcome.status == "in_flight", "the transcription worker completes the ledger row"
    assert downloads == [episode_id]
    assert queued == [(episode_id, {
        "model": "base", "diarize": False, "consent_given": False,
        "publish_to_corpus": True,
        "source_start_id": "st_watch", "source_owner_token": "o" * 43,
    })]
    idx.close()


def test_scheduler_advances_capture_only_through_the_ledger_for_a_consented_source(
        tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    on_feed = podcasts.add_feed(idx, "https://auto-tick.example/feed.xml")
    off_feed = podcasts.add_feed(idx, "https://metadata.example/feed.xml")
    clock = _wall_clock()
    adapter = FakeAdapter([snapshot(["ep-1", "ep-2"],
                                    titles={"ep-1": "Episode 1", "ep-2": "Episode 2"})])
    backend = FakeBackend()
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend)
    turn_on(service, on_feed["source_id"])
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_source_service", lambda: service)
    toasts = []
    monkeypatch.setattr(server, "maybe_toast",
                        lambda title, body, **_kw: toasts.append((title, body)))
    ingests_before = server._heartbeat_payload()["counts"]["ingests"]

    results = server._podcast_feed_scheduler_tick()

    # Detection ran for both due sources; only the consented one enrolled.
    by_source = {r["source_id"]: r for r in results}
    assert set(by_source) == {on_feed["source_id"], off_feed["source_id"]}
    assert all(r["ok"] is True and r["inserted"] == 2 for r in results)
    enrollment = by_source[on_feed["source_id"]]["enrollment"]
    assert enrollment["boundary"] == "initial" and enrollment["enrolled"] == 2
    assert by_source[off_feed["source_id"]]["enrollment"] is None
    assert toasts == [("New source items", "2 new item(s) discovered from a watched source.")]
    # The capture pass started exactly one item, for the consented source only,
    # through a charged ledger row (never from the poll itself).
    assert len(backend.runs) == 1 and backend.runs[0]["source_id"] == on_feed["source_id"]
    ledger = starts(service)
    assert len(ledger) == 1 and ledger[0]["source_id"] == on_feed["source_id"]
    assert ledger[0]["state"] == "succeeded" and ledger[0]["started_at_ms"] is not None
    assert ledger[0]["slot"] == 1 and ledger[0]["utc_day"] == ss.utc_day(clock.now)
    assert server._heartbeat_payload()["counts"]["ingests"] == ingests_before + 1
    off_items = rows(service, "SELECT state, eligibility FROM source_items WHERE source_id=?",
                     (off_feed["source_id"],))
    assert len(off_items) == 2
    assert all(r["state"] == "observed" and r["eligibility"] == "none" for r in off_items)

    # Within the interval nothing is due and the start clock holds: at most
    # one new start per source per configured interval.
    assert server._podcast_feed_scheduler_tick() == []
    assert len(backend.runs) == 1
    assert status(service, on_feed["source_id"])["source"]["capture_status"] == "not_due"
    # The compatibility helper advances only through the same reservation.
    legacy = server._auto_ingest_podcast_feed(on_feed["id"])
    assert legacy[0]["ok"] is False and legacy[0]["outcome"] == "not_due"
    assert legacy[0]["source_id"] == on_feed["source_id"]
    assert len(backend.runs) == 1 and len(starts(service)) == 1
    unknown = server._auto_ingest_podcast_feed(999_999)
    assert unknown[0]["ok"] is False and unknown[0]["error"] == "managed_by_subscription"
    idx.close()

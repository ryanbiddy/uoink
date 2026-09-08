"""V-3 taste scan under the Phase 3 standing capture contract.

Run: python tests/test_auto_uoink_poll.py  (or python -m pytest -q tests/test_auto_uoink_poll.py)

Contract phase3-v1-2026-09-07, "Scheduler and adapter boundaries": existing
playlist manual/taste scans must delegate source-owned capture eligibility to
the subscription service, and neither a global auto-uoink flag nor
``monitored_playlists.enabled`` can override per-source consent. Under run AM
a playlist added through the old registry route is projected as an off
standing source; ``poll_playlist`` (with or without a taste filter) runs only
the service's gated refresh through the injected ``refresh`` seam, records the
discoveries as durable observations, and never enqueues capture. The taste
filter is never consulted for a linked playlist. Capture happens solely through
the ledger after the confirmed consent operation.

The pre-contract expectations these tests replaced (taste-gated enqueue stamped
``capture_reason='auto_uoink:taste'``, the shared ``last_seen_video_ids``
cursor, re-scoring declined videos into capture) all describe capture from
detection, which the contract forbids. What survives of M-1 is the guarantee
behind it: no observation is ever lost, and a video observed while off is not
suppressed forever; it becomes part of the bounded cohort once consent is on.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_subscriptions_fixtures import (  # noqa: E402
    Clock, FakeAdapter, FakeBackend, MINUTE_MS, OPERATOR, items, make_service, snapshot, starts,
    status, turn_on,
)

import index as index_mod  # noqa: E402
import memory_layer  # noqa: E402
import mobile_playlists  # noqa: E402
import source_subscriptions as ss  # noqa: E402
import taste_scoring  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _seed(idx, root, video_id, title, channel):
    folder = Path(root) / video_id
    folder.mkdir(parents=True, exist_ok=True)
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": channel,
        "title": title, "topic": "AI and ML", "hook_type": "curiosity_gap",
        "yoinked_at": "2026-01-05T09:00:00",
        "corpus_path": str(folder / "corpus.md"),
        "sidecar_path": "", "source_type": "youtube",
    }, content=f"{title} transcript body")


def _watch_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def _pending_count(idx) -> int:
    return int(idx._conn.execute("SELECT COUNT(*) FROM pending_yoinks").fetchone()[0])


def _watched_playlist(idx, url, name, *, adapter, backend=None):
    """The old registry route projects the playlist as an off standing source
    (detection on, consent never inferred from ``enabled``). The service clock
    starts at the real instant the route stamped, so its cursor is due now."""
    pl = mobile_playlists.add_playlist(idx, url, name=name, normalize_playlist_url=lambda u: u)
    source_id = ss.legacy_source_id(idx._conn, playlist_id=int(pl["id"]))
    _assert(source_id is not None, "the old registry route projects a standing source")
    clock = Clock(int(time.time() * 1000))
    service = make_service(idx, clock=clock, adapter=adapter, backend=backend or FakeBackend())

    def refresh(sid):
        return service.refresh_source(OPERATOR, {"source_id": sid})

    return pl, source_id, service, clock, refresh


def test_auto_uoink_poll():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    try:
        # Taste: admire 'Fireship' (the signal that used to drive capture).
        _seed(idx, tmp.name, "seedaaaaaaa", "AI agents 101", "Fireship")
        anchors = memory_layer.get_taste_anchors(idx)
        anchors["admired_channels"] = ["Fireship"]
        memory_layer._write_taste_anchors(idx, anchors)

        candidates = ["newgoodvid1", "newmehvid22"]
        adapter = FakeAdapter([snapshot(candidates, titles={
            "newgoodvid1": "New AI agents deep dive",
            "newmehvid22": "Unrelated gardening tips"})])
        backend = FakeBackend()
        pl, source_id, service, clock, refresh = _watched_playlist(
            idx, "https://youtube.com/playlist?list=PLtest", "My watch later",
            adapter=adapter, backend=backend)
        pid = pl["id"]
        _assert(pl["enabled"] is True, "detection stays enabled on the old row")
        summary = status(service, source_id)["source"]
        _assert(summary["consent_state"] == "off" and summary["detection_enabled"] is True,
                f"projected source is off with detection on: {summary}")

        profile = taste_scoring.build_taste_profile(idx)
        real_filter = taste_scoring.make_filter(profile)
        consulted = []

        def tf(candidate):
            consulted.append(candidate)
            return real_filter(candidate)

        # Without the gate the old path refuses rather than listing or enqueuing.
        refused = mobile_playlists.poll_playlist(
            idx, pid, normalize_video_to_canonical_url=_watch_url, taste_filter=tf)
        _assert(refused["ok"] is False and refused["error"] == "managed_by_subscription",
                f"ungated poll is refused: {refused}")
        _assert(adapter.calls == [] and consulted == [],
                "refusal performs no network I/O and no scoring")

        captured_urls = []
        result = mobile_playlists.poll_playlist(
            idx, pid,
            normalize_video_to_canonical_url=lambda vid: (
                captured_urls.append(vid) or _watch_url(vid)),
            taste_filter=tf,
            fetch_entries=lambda _url: (_ for _ in ()).throw(
                AssertionError("the yt-dlp listing must not run for a linked playlist")),
            refresh=refresh)
        _assert(result["ok"] is True, f"poll ok: {result}")
        _assert(result["managed_by_subscription"] is True and result["source_id"] == source_id,
                f"delegated to the subscription service: {result}")
        _assert(result["outcome"] == "snapshot" and result["total_in_playlist"] == 2,
                f"one gated refresh ran: {result}")
        _assert(result["new"] == [] and result["skipped"] == [],
                f"detection makes no capture decision: {result}")
        _assert(captured_urls == [] and _pending_count(idx) == 0,
                "nothing is enqueued from detection")
        _assert(consulted == [], "the taste filter is never consulted for a linked playlist")
        _assert([c["source_id"] for c in adapter.calls] == [source_id], "exactly one adapter poll")
        print("ok  taste scan delegates to the gated refresh and enqueues nothing")

        # The discoveries are durable observations with no eligibility: the
        # source is off, so nothing is a candidate for capture.
        observed = items(service, source_id)
        _assert(sorted(i["entry_id"] for i in observed) == sorted(candidates),
                f"both candidates observed: {observed}")
        _assert(all(i["state"] == "observed" and i["eligibility"] == "none"
                    and i["first_seen_consent_epoch"] is None for i in observed),
                f"metadata only: {observed}")
        _assert(mobile_playlists.list_events(idx, playlist_id=pid) == [],
                "no queue event is written from detection")
        _assert(mobile_playlists.list_taste_captures(idx) == [],
                "no taste capture provenance exists")
        _assert(backend.runs == [] and starts(service) == [], "no reservation, no capture")
        print("ok  discoveries persisted as observations, no capture provenance")

        # Re-poll inside the interval: the due-time gate answers; no second
        # fetch, no duplicate observation.
        result2 = mobile_playlists.poll_playlist(
            idx, pid, normalize_video_to_canonical_url=_watch_url, taste_filter=tf,
            refresh=refresh)
        _assert(result2["ok"] is True and result2["outcome"] == "not_due", f"not due: {result2}")
        _assert(result2["new"] == [] and len(adapter.calls) == 1,
                f"no duplicate fetch or capture: {result2}")
        _assert(len(items(service, source_id)) == 2, "observations are not duplicated")
        print("ok  re-poll: gated by due time, no duplicate observation")

        print("\nall green")
    finally:
        idx.close()
        tmp.cleanup()


def test_auto_uoink_does_not_burn_backlog_or_starve_plain_poll():
    """M-1 restated under Phase 3: the durable observation set is the cursor.

    A scan with no taste signal loses nothing, a later shorter listing prunes
    nothing, and the plain "capture everything" poll shares the same gated
    refresh and enqueues nothing either. What used to be "still capturable
    later" is now: the backlog observed while off becomes the bounded initial
    cohort once the user confirms consent.
    """
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    try:
        candidates = ["backlogvid1", "backlogvid2"]
        adapter = FakeAdapter([snapshot(candidates, titles={
            "backlogvid1": "AI agents deep dive", "backlogvid2": "Gardening tips"})])
        pl, source_id, service, clock, refresh = _watched_playlist(
            idx, "https://youtube.com/playlist?list=PLm1", "Backlog", adapter=adapter)
        pid = pl["id"]

        # Scan with NO taste signal: nothing is captured, nothing is lost.
        empty_filter = taste_scoring.make_filter(taste_scoring.build_taste_profile(idx))
        scan1 = mobile_playlists.poll_playlist(
            idx, pid, normalize_video_to_canonical_url=_watch_url,
            taste_filter=empty_filter, refresh=refresh)
        _assert(scan1["ok"] is True and scan1["new"] == [] and scan1["skipped"] == [],
                f"no signal -> no capture decision either way: {scan1}")
        _assert(sorted(i["entry_id"] for i in items(service, source_id)) == candidates,
                "both observations retained")

        # A PLAIN poll (no taste_filter) after the scan: same gate, no enqueue.
        clock.advance(60 * MINUTE_MS)
        plain_urls = []
        plain = mobile_playlists.poll_playlist(
            idx, pid,
            normalize_video_to_canonical_url=lambda vid: (
                plain_urls.append(vid) or _watch_url(vid)),
            refresh=refresh)
        _assert(plain["ok"] is True and plain["outcome"] == "snapshot" and plain["new"] == [],
                f"plain poll enqueues nothing: {plain}")
        _assert(plain_urls == [] and _pending_count(idx) == 0, "no pending_yoinks row")
        _assert([c["source_id"] for c in adapter.calls] == [source_id, source_id],
                "each due poll fetches exactly once")

        # A later listing that omits a video prunes nothing (contract: keep the
        # full durable identity set; never prune seen ids to the latest response).
        adapter.results = [snapshot(["backlogvid1"])]
        clock.advance(60 * MINUTE_MS)
        third = mobile_playlists.poll_playlist(idx, pid, refresh=refresh)
        _assert(third["ok"] is True and third["total_in_playlist"] == 1,
                f"third poll saw one entry: {third}")
        _assert(sorted(i["entry_id"] for i in items(service, source_id)) == candidates,
                "no observation is lost")
        print("ok  observations survive empty-signal scans, plain polls and shorter listings")

        # Consent confirmed later: the observed backlog is the bounded initial cohort.
        turn_on(service, source_id)
        _assert(status(service, source_id)["source"]["enrollment"]["pending"] is True,
                "enrollment is pending until the next valid snapshot")
        adapter.results = [snapshot(candidates)]
        clock.advance(60 * MINUTE_MS)
        enrolling = mobile_playlists.poll_playlist(idx, pid, refresh=refresh)
        _assert(enrolling["ok"] is True and enrolling["outcome"] == "snapshot",
                f"boundary snapshot: {enrolling}")
        cohort = [i for i in items(service, source_id) if i["eligibility"] == "back_catalog"]
        _assert(sorted(i["entry_id"] for i in cohort) == candidates,
                f"videos observed while off form the initial cohort: {cohort}")
        _assert(all(i["state"] == "eligible" for i in cohort),
                "eligible, not started: capture still needs the ledger")
        _assert(_pending_count(idx) == 0 and starts(service) == [],
                "consent alone enqueues and reserves nothing")
        print("ok  backlog observed while off becomes the bounded cohort after consent")

        print("\nall green")
    finally:
        idx.close()
        tmp.cleanup()


def test_taste_signal_cannot_override_consent_only_the_ledger_captures():
    """The old backlog-burn half of M-1 ("a declined video is captured by a
    later scan once taste exists") no longer describes any path: taste never
    captures, and a global taste signal cannot override per-source consent.
    Its surviving purpose: a video observed while off is not suppressed
    forever; it starts through the ledger once consent is on, with no taste
    provenance and no queue row."""
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    try:
        adapter = FakeAdapter([snapshot(["laterhit001"],
                                        titles={"laterhit001": "AI agents deep dive"})])
        backend = FakeBackend()
        pl, source_id, service, clock, refresh = _watched_playlist(
            idx, "https://youtube.com/playlist?list=PLm2", "Backlog2",
            adapter=adapter, backend=backend)
        pid = pl["id"]

        # Scan #1 with no signal: observed, not captured.
        f0 = taste_scoring.make_filter(taste_scoring.build_taste_profile(idx))
        scan1 = mobile_playlists.poll_playlist(
            idx, pid, normalize_video_to_canonical_url=_watch_url, taste_filter=f0,
            refresh=refresh)
        _assert(scan1["ok"] is True and scan1["new"] == [], f"observed only: {scan1}")

        # The user now builds taste signal: admire 'Fireship'. The model itself
        # would accept the candidate, but consent for this source is still off.
        _seed(idx, tmp.name, "seedbbbbbbb", "AI agents 101", "Fireship")
        anchors = memory_layer.get_taste_anchors(idx)
        anchors["admired_channels"] = ["Fireship"]
        memory_layer._write_taste_anchors(idx, anchors)
        f1 = taste_scoring.make_filter(taste_scoring.build_taste_profile(idx))
        verdict = f1({"video_id": "laterhit001", "title": "AI agents deep dive",
                      "channel": "Fireship"}) or {}
        _assert(verdict.get("capture") is True,
                f"the taste model alone would accept this candidate: {verdict}")
        clock.advance(60 * MINUTE_MS)
        scan2 = mobile_playlists.poll_playlist(
            idx, pid, normalize_video_to_canonical_url=_watch_url, taste_filter=f1,
            refresh=refresh)
        _assert(scan2["ok"] is True and scan2["new"] == [] and scan2["skipped"] == [],
                f"taste signal cannot capture: {scan2}")
        _assert(_pending_count(idx) == 0 and backend.runs == [], "no enqueue, no capture")
        item = items(service, source_id)[0]
        _assert(item["state"] == "observed" and item["eligibility"] == "none",
                f"still metadata only while off: {item}")
        _assert(service.capture_pass() == [], "the capture pass ignores an off source")
        print("ok  taste signal cannot override per-source consent")

        # Consent on, one boundary snapshot, then the ledger starts the capture.
        turn_on(service, source_id)
        clock.advance(60 * MINUTE_MS)
        boundary = mobile_playlists.poll_playlist(idx, pid, refresh=refresh)
        _assert(boundary["ok"] is True and boundary["outcome"] == "snapshot",
                f"boundary snapshot: {boundary}")
        _assert(items(service, source_id)[0]["state"] == "eligible", "enrolled, not started")
        outcomes = service.capture_pass()
        _assert([o["outcome"] for o in outcomes] == ["succeeded"], f"one ledger capture: {outcomes}")
        ledger = starts(service, source_id)
        _assert(len(ledger) == 1 and ledger[0]["state"] == "succeeded"
                and ledger[0]["video_id"] == "laterhit001", f"ledger: {ledger}")
        _assert(backend.runs[0]["source_id"] == source_id, "charged to this source")
        item = items(service, source_id)[0]
        _assert(item["state"] == "committed" and item["video_id"] == "laterhit001",
                f"committed: {item}")
        _assert(mobile_playlists.list_taste_captures(idx) == [] and _pending_count(idx) == 0,
                "no taste provenance and no queue row: the ledger is the only capture record")
        print("ok  observed-while-off video captured through the ledger after consent")
        print("\nall green")
    finally:
        idx.close()
        tmp.cleanup()


if __name__ == "__main__":
    test_auto_uoink_poll()
    test_auto_uoink_does_not_burn_backlog_or_starve_plain_poll()
    test_taste_signal_cannot_override_consent_only_the_ledger_captures()

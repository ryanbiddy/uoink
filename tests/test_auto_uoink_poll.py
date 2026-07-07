"""V-3 -- taste-gated poll: mobile_playlists.poll_playlist(taste_filter=...).

Run: python tests/test_auto_uoink_poll.py  (or via pytest tests/)

Red on unpatched main: poll_playlist has no `taste_filter` / `fetch_entries`
params (TypeError), and mobile_queue_events has no capture_reason column, so
the capture-provenance assertions fail.

Green with the fix: a taste filter makes the poll selective -- only
candidates that clear the taste bar are enqueued + logged (stamped
capture_reason='auto_uoink:taste' + taste_score); declined ones land in
skipped[] with no queue row and no event. list_taste_captures() surfaces
exactly the captured rows for the digest.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import memory_layer  # noqa: E402
import mobile_playlists  # noqa: E402
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


def test_auto_uoink_poll():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    try:
        # Taste: admire 'Fireship'.
        _seed(idx, tmp.name, "seedaaaaaaa", "AI agents 101", "Fireship")
        anchors = memory_layer.get_taste_anchors(idx)
        anchors["admired_channels"] = ["Fireship"]
        memory_layer._write_taste_anchors(idx, anchors)

        # A monitored playlist the user already tracks.
        pl = mobile_playlists.add_playlist(
            idx, "https://youtube.com/playlist?list=PLtest",
            name="My watch later",
            normalize_playlist_url=lambda u: u)
        pid = pl["id"]

        # Injected candidates: one from the admired channel, one not.
        candidates = [
            {"video_id": "newgoodvid1", "title": "New AI agents deep dive",
             "channel": "Fireship"},
            {"video_id": "newmehvid22", "title": "Unrelated gardening tips",
             "channel": "GardenWorld"},
        ]

        profile = taste_scoring.build_taste_profile(idx)
        tf = taste_scoring.make_filter(profile)

        captured_urls = []
        result = mobile_playlists.poll_playlist(
            idx, pid,
            normalize_video_to_canonical_url=lambda vid: (
                captured_urls.append(vid)
                or f"https://www.youtube.com/watch?v={vid}"),
            taste_filter=tf,
            fetch_entries=lambda _url: candidates)

        _assert(result["ok"] is True, f"poll ok: {result}")
        new_ids = [n["video_id"] for n in result["new"]]
        skipped_ids = [s["video_id"] for s in result["skipped"]]
        _assert(new_ids == ["newgoodvid1"],
                f"only the admired-channel candidate captures: {new_ids}")
        _assert(skipped_ids == ["newmehvid22"],
                f"the off-taste candidate is skipped: {skipped_ids}")
        _assert(captured_urls == ["newgoodvid1"],
                f"only captured candidate is enqueued: {captured_urls}")
        cap = result["new"][0]
        _assert(cap["capture_reason"] == "auto_uoink:taste",
                f"captured row is labelled: {cap}")
        _assert((cap["taste_score"] or 0) >= taste_scoring.DEFAULT_THRESHOLD,
                f"captured row carries its score: {cap}")
        print("ok  taste-gated poll captures on-taste, skips off-taste")

        # The event row persists the provenance.
        events = mobile_playlists.list_events(idx, playlist_id=pid)
        _assert(len(events) == 1, f"only the captured row logs an event: {events}")
        _assert(events[0]["capture_reason"] == "auto_uoink:taste",
                f"event provenance persisted: {events[0]}")

        # list_taste_captures surfaces exactly the captured row.
        caps = mobile_playlists.list_taste_captures(idx)
        _assert([c["video_id"] for c in caps] == ["newgoodvid1"],
                f"taste captures list is correct: {caps}")
        print("ok  provenance persisted + list_taste_captures works")

        # Re-poll with the same candidates. M-1: the taste scan advances the
        # shared cursor ONLY past the video it captured, so the *captured* one
        # is not re-captured (no duplicate), but the *declined* one stays
        # eligible and is re-evaluated (still skipped, taste unchanged). This
        # is what keeps a later scan able to catch the backlog once taste
        # improves, and keeps the plain poll able to grab it.
        result2 = mobile_playlists.poll_playlist(
            idx, pid,
            normalize_video_to_canonical_url=lambda vid:
                f"https://www.youtube.com/watch?v={vid}",
            taste_filter=tf,
            fetch_entries=lambda _url: candidates)
        _assert(result2["new"] == [],
                f"re-poll makes no duplicate capture: {result2}")
        _assert([s["video_id"] for s in result2["skipped"]] == ["newmehvid22"],
                f"declined video stays eligible and is re-evaluated: {result2}")
        print("ok  re-poll: no duplicate capture, declined stays eligible")

        print("\nall green")
    finally:
        idx.close()
        tmp.cleanup()


def test_auto_uoink_does_not_burn_backlog_or_starve_plain_poll():
    """M-1 regression: the taste scan must NOT advance the shared poll cursor
    past videos it declined.

    Proves two properties the review demanded:
      1. A video the taste scan declined is still capturable later -- both by
         a plain 'capture everything' poll (cross-feature) AND by a later
         taste scan once taste signal exists (backlog burn).
      2. A plain poll running after a taste scan still grabs the non-matching
         videos the scan skipped.
    """
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    try:
        pl = mobile_playlists.add_playlist(
            idx, "https://youtube.com/playlist?list=PLm1",
            name="Backlog", normalize_playlist_url=lambda u: u)
        pid = pl["id"]

        candidates = [
            {"video_id": "backlogvid1", "title": "AI agents deep dive",
             "channel": "Fireship"},
            {"video_id": "backlogvid2", "title": "Gardening tips",
             "channel": "GardenWorld"},
        ]

        # --- Scan with NO taste signal: an empty corpus/anchors means the
        # filter declines everything (scores ~0). Pre-fix, this burned the
        # whole backlog by advancing last_seen past both.
        empty_profile = taste_scoring.build_taste_profile(idx)
        empty_filter = taste_scoring.make_filter(empty_profile)
        scan1 = mobile_playlists.poll_playlist(
            idx, pid,
            normalize_video_to_canonical_url=lambda vid:
                f"https://www.youtube.com/watch?v={vid}",
            taste_filter=empty_filter,
            fetch_entries=lambda _url: candidates)
        _assert(scan1["new"] == [],
                f"no signal -> nothing auto-captured: {scan1}")
        _assert(sorted(s["video_id"] for s in scan1["skipped"])
                == ["backlogvid1", "backlogvid2"],
                f"both declined for lack of signal: {scan1}")
        # The declined videos must NOT be marked seen.
        row = mobile_playlists.get_playlist(idx, pid)
        _assert(row["last_seen_video_ids"] == [],
                f"declined videos must stay unseen in the cursor: {row}")

        # --- Property 2: a PLAIN poll (no taste_filter, capture-everything)
        # after the scan still grabs both non-matching videos.
        plain_urls = []
        plain = mobile_playlists.poll_playlist(
            idx, pid,
            normalize_video_to_canonical_url=lambda vid: (
                plain_urls.append(vid)
                or f"https://www.youtube.com/watch?v={vid}"),
            fetch_entries=lambda _url: candidates)
        _assert(sorted(n["video_id"] for n in plain["new"])
                == ["backlogvid1", "backlogvid2"],
                f"plain poll grabs the scan-declined videos: {plain}")
        _assert(sorted(plain_urls) == ["backlogvid1", "backlogvid2"],
                f"plain poll enqueues both: {plain_urls}")
        print("ok  plain poll after a scan still captures scan-declined videos")

        print("\nall green")
    finally:
        idx.close()
        tmp.cleanup()


def test_declined_video_captured_after_taste_improves():
    """M-1 regression, backlog-burn half: a video declined by a weak-signal
    scan is re-scored and captured by a later scan once taste signal exists --
    it is not permanently suppressed."""
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    try:
        pl = mobile_playlists.add_playlist(
            idx, "https://youtube.com/playlist?list=PLm2",
            name="Backlog2", normalize_playlist_url=lambda u: u)
        pid = pl["id"]
        candidates = [
            {"video_id": "laterhit001", "title": "AI agents deep dive",
             "channel": "Fireship"},
        ]

        # Scan #1 with no signal -> declined, and (post-fix) left unseen.
        f0 = taste_scoring.make_filter(taste_scoring.build_taste_profile(idx))
        scan1 = mobile_playlists.poll_playlist(
            idx, pid,
            normalize_video_to_canonical_url=lambda vid:
                f"https://www.youtube.com/watch?v={vid}",
            taste_filter=f0, fetch_entries=lambda _url: candidates)
        _assert(scan1["new"] == [], f"declined with no signal: {scan1}")

        # User now builds taste signal: admire 'Fireship'.
        _seed(idx, tmp.name, "seedbbbbbbb", "AI agents 101", "Fireship")
        anchors = memory_layer.get_taste_anchors(idx)
        anchors["admired_channels"] = ["Fireship"]
        memory_layer._write_taste_anchors(idx, anchors)

        # Scan #2 with signal -> the previously declined video is re-evaluated
        # and now captured. Pre-fix it would have been 'seen' and skipped
        # forever.
        f1 = taste_scoring.make_filter(taste_scoring.build_taste_profile(idx))
        scan2 = mobile_playlists.poll_playlist(
            idx, pid,
            normalize_video_to_canonical_url=lambda vid:
                f"https://www.youtube.com/watch?v={vid}",
            taste_filter=f1, fetch_entries=lambda _url: candidates)
        _assert([n["video_id"] for n in scan2["new"]] == ["laterhit001"],
                f"declined video is captured once taste improves: {scan2}")
        print("ok  declined video is captured by a later scan once taste exists")
        print("\nall green")
    finally:
        idx.close()
        tmp.cleanup()


if __name__ == "__main__":
    test_auto_uoink_poll()
    test_auto_uoink_does_not_burn_backlog_or_starve_plain_poll()
    test_declined_video_captured_after_taste_improves()

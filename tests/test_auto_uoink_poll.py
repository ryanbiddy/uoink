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

        # Re-poll with the same candidates: both now 'seen', nothing new.
        result2 = mobile_playlists.poll_playlist(
            idx, pid,
            normalize_video_to_canonical_url=lambda vid:
                f"https://www.youtube.com/watch?v={vid}",
            taste_filter=tf,
            fetch_entries=lambda _url: candidates)
        _assert(result2["new"] == [] and result2["skipped"] == [],
                f"re-poll sees nothing new: {result2}")
        print("ok  re-poll is idempotent (no duplicate captures)")

        print("\nall green")
    finally:
        idx.close()
        tmp.cleanup()


if __name__ == "__main__":
    test_auto_uoink_poll()

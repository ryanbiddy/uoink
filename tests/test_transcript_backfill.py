"""3.18 transcript backfill: every saved video ends up with its words.

An isolated library holds one save in each state: words already saved, no
captions with the video on disk, no captions and no media (fetch again), a
source that is gone, a capture that stopped midway, a text post, and a
YouTube save whose captions exist now. ASR, yt-dlp, ffprobe and ffmpeg are
mocked; nothing touches the network or a real model.

Run: bash rel-run/safe.sh q-backfill 18111 python -m pytest tests/test_transcript_backfill.py -q
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import types
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest
import urllib.request

REAL_URLOPEN = urllib.request.urlopen
REAL_CREATE_CONNECTION = __import__("socket").create_connection

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import server  # noqa: E402
import transcript_backfill as tb  # noqa: E402
import uoink_reliability as reliability  # noqa: E402

TEXT_FOR = {
    "has-words": [(0.0, 2.0, "words that were already saved")],
}


def _x(n: int) -> str:
    return f"https://x.com/examplemaker/status/180000000000000{n:04d}"


def _wait(predicate, timeout=10.0, message="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {message}")


class Library:
    """A throwaway Uoink library plus the fakes every test shares."""

    def __init__(self, tmp_path: Path, monkeypatch):
        self.mp = monkeypatch
        self.root = tmp_path / "corpus"
        self.root.mkdir()
        self.data = tmp_path / "data"
        self.data.mkdir()
        self.idx = index_mod.Index.open(self.data / "index.db")
        self.asr_calls: list[str] = []
        self.downloads: list[str] = []
        self.caption_fetches: list[str] = []
        self.ffmpeg_calls: list[list] = []
        self.segments: dict[str, list] = {}
        self.segment_hook = None
        self.gone_urls: set[str] = set()
        self.rate_limited_urls: set[str] = set()
        self.caption_urls: set[str] = set()
        self.refused_caption_urls: set[str] = set()
        self.notified: list[str] = []
        self.model_cached = True
        unexpected = Mock(side_effect=AssertionError("unmocked network I/O"))
        mp = monkeypatch
        mp.setattr(server.urllib.request, "urlopen", unexpected)
        mp.setattr(server.socket, "create_connection", unexpected)
        mp.setattr(server, "DESKTOP_ROOT", self.root)
        mp.setattr(server, "DATA_ROOT", self.data)
        mp.setattr(server, "_get_index", lambda: self.idx)
        mp.setattr(server, "_transcript_backfill_instance", None)
        self.settings = {"asr_fallback_enabled": True, "whisper_model": "base",
                         "transcript_reliability_auto_check": False, "keep_media": False}
        self.silent: set[str] = set()  # slugs whose media has no audio track
        mp.setattr(server, "_read_settings", lambda: self.settings)
        mp.setattr(server, "_write_settings", Mock(side_effect=AssertionError("settings written")))
        mp.setattr(server, "_reliability_model_status",
                   lambda _m=None: {"model": "base", "cached": self.model_cached})
        mp.setattr(server, "_fetch_channel_context", lambda *a, **k: {})
        mp.setattr(server, "_start_comments_thread", lambda *a, **k: None)
        mp.setattr(server, "_start_entity_extraction_thread", lambda *a, **k: None)
        mp.setattr(server, "_download_thumbnail", lambda *a, **k: None)
        mp.setattr(server, "_incremental_index_update", lambda *a, **k: None)
        mp.setattr(server, "_get_saved_anthropic_key", lambda: None)
        mp.setattr(server, "_anthropic_key_for_feature", lambda *a: None)
        mp.setattr(server, "_run_subprocess", self.fake_run)
        mp.setattr(reliability, "transcribe_media", self.fake_asr)
        original_notify = self.idx._notify_source_changed

        def notify(video_id):
            self.notified.append(video_id)
            return original_notify(video_id)
        mp.setattr(self.idx, "_notify_source_changed", notify)

    # ---- fakes -----------------------------------------------------------
    @staticmethod
    def slug_for(media: Path) -> str:
        return media.parent.parent.name if media.parent.name.startswith(".asr-") else media.parent.name

    def fake_asr(self, media_path, **kwargs):
        media = Path(media_path)
        assert media.is_file(), f"ASR got a missing file: {media}"
        slug = self.slug_for(media)
        self.asr_calls.append(slug)
        segments = self.segments.get(slug, [
            (0.0, 2.0, f"{slug} opening line"),
            (2.0, 4.0, "the middle part"),
            (4.0, 6.0, f"{slug} closing words"),
        ])
        checkpoint = kwargs.get("checkpoint")
        out = []
        for number, (start, end, text) in enumerate(segments):
            if self.segment_hook is not None:
                self.segment_hook(slug, number)
            if checkpoint is not None:
                checkpoint(types.SimpleNamespace(start=start, end=end, text=text))
            out.append((start, end, text))
        return out

    def fake_run(self, cmd, **kwargs):
        name = Path(str(cmd[0])).stem.lower()
        if name == "ffprobe":
            streams = [] if self.slug_for(Path(cmd[-1])) in self.silent else [{"index": 1}]
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"streams": streams}), b"")
        if name == "ffmpeg":
            self.ffmpeg_calls.append(list(cmd))
            out = Path(cmd[-1])
            if "%" in out.name:
                out = out.with_name(out.name.replace("%04d", "0001"))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"jpg")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        assert list(cmd[:len(server.YTDLP_CMD)]) == list(server.YTDLP_CMD), f"unexpected command: {cmd}"
        url = cmd[-1]
        target = Path(cmd[cmd.index("-o") + 1])
        if "--skip-download" in cmd:
            self.caption_fetches.append(url)
            if url in self.refused_caption_urls:
                raise subprocess.CalledProcessError(
                    1, cmd, stderr=b"ERROR: Unable to download video subtitles: HTTP Error 429: Too Many Requests")
            if url in self.caption_urls:
                (target.parent / "video.en.srt").write_text(
                    "1\n00:00:00,000 --> 00:00:03,000\ncaption words from the source\n\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        if "bestaudio/best" in cmd:
            self.downloads.append(url)
            if url in self.gone_urls:
                raise subprocess.CalledProcessError(
                    1, cmd, stderr=b"ERROR: [twitter] 1: HTTP Error 404: Not Found")
            if url in self.rate_limited_urls:
                raise subprocess.CalledProcessError(
                    1, cmd, stderr=b"ERROR: HTTP Error 429: Too Many Requests")
            Path(str(target).replace("%(ext)s", "m4a")).write_bytes(b"audio")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        # A capture's video download.
        self.downloads.append(url)
        Path(str(target).replace("%(ext)s", "mp4")).write_bytes(b"\x00\x00\x00\x18ftypmp4")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    # ---- fixture saves ---------------------------------------------------
    def add_video(self, slug, *, url, video_id, title, duration, saved_at,
                  words=None, media=False, topic="AI", base=None):
        folder = (base or self.root) / topic / slug
        (folder / "screenshots").mkdir(parents=True)
        (folder / "screenshots" / "shot_0001.jpg").write_bytes(b"jpg")
        entries = list(words or [])
        # The shape 3.x captures wrote before local ASR existed.
        sidecar = {
            "schema_version": 2, "url": url,
            "platform": server._detect_platform_from_url(url), "source_type": None,
            "title": title, "topic": topic, "yoinked_at": saved_at, "interval_seconds": 30,
            "duration_seconds": duration, "channel": "examplemaker", "video_id": video_id,
            "transcript": [{"start": s, "end": e, "text": t} for s, e, t in entries],
            "screenshots": [{"timestamp": "00:00:00", "path": "screenshots/shot_0001.jpg",
                             "filename": "shot_0001.jpg"}],
            "comments": [], "comments_status": "disabled", "hook_type_status": "skipped",
            "comment_intelligence_status": "not_run",
        }
        sidecar["health"] = server.compute_health(sidecar)
        md = server._build_yoink_md(
            metadata={"title": title, "channel": "examplemaker", "duration": duration,
                      "description": "A saved clip about making things."},
            url=url, entries=entries, shots=[folder / "screenshots" / "shot_0001.jpg"],
            interval=30, channel_ctx={}, yoinked_at=saved_at, topic=topic)
        corpus = folder / f"{slug}.md"
        corpus.write_text(md, encoding="utf-8")
        sidecar_path = folder / f"{slug}.json"
        sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
        (folder / "metadata.json").write_text(json.dumps(
            {"id": video_id, "title": title, "duration": duration, "webpage_url": url}), encoding="utf-8")
        if media:
            (folder / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp4" + b"0" * 64)
        assert server._index_yoink(folder, sidecar, corpus, sidecar_path, root=base or self.root)
        return folder

    def add_text_post(self, slug, *, url, video_id):
        folder = self.root / "X" / slug
        folder.mkdir(parents=True)
        sidecar = {"url": url, "source_type": "x_thread", "platform": "twitter", "title": "A text post",
                   "video_id": video_id, "yoinked_at": "2026-08-01T10:00:00", "text": "just words"}
        sidecar["health"] = server.compute_health(sidecar)
        corpus = folder / f"{slug}.md"
        corpus.write_text("# A text post\n\njust words\n", encoding="utf-8")
        sidecar_path = folder / f"{slug}.json"
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
        assert server._index_yoink(folder, sidecar, corpus, sidecar_path)
        return folder

    def add_half_capture(self, slug, *, url, video_id, title, duration, marker=True,
                         topic="AI", media_name="video.mp4", media_bytes=None):
        """What a capture killed during transcription leaves behind."""
        folder = self.root / topic / slug
        (folder / "screenshots").mkdir(parents=True)
        (folder / ".capture-source.json").write_text(
            json.dumps({"url": server._video_capture_source(url), "video_id": video_id}), encoding="utf-8")
        (folder / "metadata.json").write_text(json.dumps({
            "id": video_id, "title": title, "duration": duration, "webpage_url": url,
            "uploader": "examplemaker", "channel": "examplemaker"}), encoding="utf-8")
        (folder / "thumbnail.jpg").write_bytes(b"jpg")
        for n in (1, 2):
            (folder / "screenshots" / f"shot_{n:04d}.jpg").write_bytes(b"jpg")
        (folder / media_name).write_bytes(
            b"\x00\x00\x00\x18ftypmp4" + b"1" * 256 if media_bytes is None else media_bytes)
        if marker:
            # The note _run_extraction leaves until the sidecar is written.
            (folder / server.CAPTURE_INCOMPLETE_NAME).write_text(
                f"Uoink has not finished saving this capture yet.\n\nurl: {url}\n"
                "started: 2026-11-01T09:00:00\n", encoding="utf-8")
        return folder

    def snapshot(self, folder: Path) -> dict:
        return {p.relative_to(folder).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in folder.rglob("*") if p.is_file()}

    def backfill(self):
        return server._transcript_backfill()

    def finished(self):
        job = self.backfill()
        return job._state["status"] != "running" and not job._alive()


@pytest.fixture
def lib(tmp_path, monkeypatch):
    library = Library(tmp_path, monkeypatch)
    yield library
    job = server._transcript_backfill_instance
    if job is not None:
        job.pause()
        job.wait(5)


def _seed(lib: Library) -> dict:
    """One save in every state the brief lists."""
    f = {}
    f["has_words"] = lib.add_video(
        "has-words", url=_x(1), video_id="1800000000000000001", title="Already has words",
        duration=900, saved_at="2026-07-02T09:00:00", words=TEXT_FOR["has-words"], media=True)
    f["on_disk"] = lib.add_video(
        "on-disk", url=_x(2), video_id="1800000000000000002", title="Video kept on disk",
        duration=600, saved_at="2026-08-03T09:00:00", media=True)
    f["download"] = lib.add_video(
        "fetch-again", url=_x(3), video_id="1800000000000000003", title="Needs a fresh fetch",
        duration=300, saved_at="2026-09-04T09:00:00")
    f["gone"] = lib.add_video(
        "gone-source", url=_x(4), video_id="1800000000000000004", title="Deleted at the source",
        duration=1200, saved_at="2026-10-05T09:00:00")
    lib.idx.record_availability("1800000000000000004", status="deleted",
                                gone_since="2026-11-01T00:00:00Z")
    f["text"] = lib.add_text_post("text-post", url=_x(5), video_id="1800000000000000005")
    f["half"] = lib.add_half_capture(
        "two-hour-talk_0123456789abcdef", url="https://www.youtube.com/watch?v=AbCdEfGhIj1",
        video_id="AbCdEfGhIj1", title="A two hour talk", duration=7200)
    return f


def test_scan_tells_every_state_apart(lib):
    f = _seed(lib)
    status = server._transcript_backfill_status()
    by_key = {i["key"]: i for i in server._transcript_backfill_scan()["items"]}
    assert "1800000000000000001" not in by_key, "a save with words is never listed"
    assert "1800000000000000005" not in by_key, "a text post has no media to transcribe"
    assert by_key["1800000000000000002"]["media"] == "on_disk"
    assert by_key["1800000000000000003"]["media"] == "download"
    assert by_key["1800000000000000004"]["media"] == "gone"
    half_key = "folder:AI/" + f["half"].name
    assert by_key[half_key]["half"] is True and by_key[half_key]["media"] == "on_disk"
    assert status["count"] == 3 and status["on_disk"] == 2 and status["download"] == 1
    assert status["gone"] == 1 and status["half_capture_count"] == 1
    assert status["state"] == "idle" and status["model_ready"] is True
    # Looking never starts anything.
    assert lib.asr_calls == [] and lib.downloads == [] and server._transcript_backfill_instance._thread is None


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_run_kill_restart_resume_finish_and_search(lib):
    """Kill the helper mid-item, start a new one, and the run carries on."""
    f = _seed(lib)
    untouched = {name: lib.snapshot(f[name]) for name in ("has_words", "text")}
    gate, blocked = threading.Event(), threading.Event()
    killed = {"done": False}

    def hook(slug, number):
        if slug == "on-disk" and number == 1 and not killed["done"]:
            killed["done"] = True
            blocked.set()
            gate.wait(30)
            raise SystemExit  # the old process is gone; it saves nothing more
    lib.segment_hook = hook

    first = lib.backfill()
    assert first.start()["ok"] is True
    blocked.wait(10)
    assert blocked.is_set(), "the run should reach the second save"
    on_disk = json.loads((server.DATA_ROOT / tb.STATE_FILE).read_text(encoding="utf-8"))
    assert on_disk["status"] == "running"
    half_key = "folder:AI/" + f["half"].name
    assert on_disk["results"][half_key]["outcome"] == "transcribed", "longest first: the 2 h talk"

    # Restart: a fresh helper reads the progress file and resumes by itself.
    server._transcript_backfill_instance = None
    server._resume_transcript_backfill_at_boot()
    second = server._transcript_backfill_instance
    assert second is not first
    _wait(lambda: second._state["status"] == "done" and not second._alive(), message="the resumed run")
    gate.set()
    first.wait(5)

    assert lib.asr_calls.count(f["half"].name) == 1, "finished work is not redone"
    assert lib.asr_calls.count("on-disk") == 2, "the interrupted save starts over"
    assert lib.asr_calls.count("fetch-again") == 1
    assert "has-words" not in lib.asr_calls and "gone-source" not in lib.asr_calls
    assert _x(4) not in lib.downloads, "a gone source is never fetched"
    assert lib.downloads == [_x(3)], "only the save without media is fetched again"
    for name, before in untouched.items():
        assert lib.snapshot(f[name]) == before, f"{name} must not be touched"

    status = server._transcript_backfill_status()
    assert status["state"] == "done" and status["count"] == 0
    assert status["progress"]["transcribed"] == 3, "the run's totals carry over the restart"
    assert status["progress"]["done"] == 3 and status["progress"]["left"] == 0
    assert status["gone"] == 1 and status["half_capture_count"] == 0

    for video_id, slug, folder in (("1800000000000000002", "on-disk", f["on_disk"]),
                                   ("1800000000000000003", "fetch-again", f["download"])):
        sidecar = json.loads((folder / f"{slug}.json").read_text(encoding="utf-8"))
        assert sidecar["transcript_source"] == "asr"
        assert sidecar["transcript_backfill"]["status"] == "done"
        assert sidecar["health"]["transcript"] == "ok"
        assert sidecar["transcript_note"] == "Local Whisper transcript: captions unavailable"
        md = (folder / f"{slug}.md").read_text(encoding="utf-8")
        assert f"{slug} closing words" in md
        assert "No captions available for this video." not in md
        assert "**Transcript:** Local Whisper transcript: captions unavailable" in md
        assert md.count("## Screenshots") == 1 and "## Description" in md
        assert (folder / "transcript.txt").read_text(encoding="utf-8").startswith(f"{slug} opening line")
        hits = lib.idx.search(f"{slug} closing words", limit=5, match="strict")
        assert video_id in [h["video_id"] for h in hits], "keyword search finds the new words"
        transcript = server._library_transcript(video_id)
        assert transcript and transcript["transcribed_by"] == "whisper"
        assert video_id in lib.notified, "the semantic index hears about the change"
        assert not list(folder.glob(".asr-*")), "no temporary audio is left behind"
    assert (f["on_disk"] / "video.mp4").exists(), "media on disk is kept"

    # The capture that stopped midway is now a complete library entry.
    half = f["half"]
    assert not (half / server.CAPTURE_INCOMPLETE_NAME).exists()
    assert (half / "video.mp4").exists(), "finishing never deletes the video it reused"
    assert sorted(p.name for p in (half / "screenshots").glob("*.jpg")) == ["shot_0001.jpg", "shot_0002.jpg"]
    assert lib.ffmpeg_calls == [], "screenshots on disk are reused, nothing is rendered"
    row = lib.idx.get_yoink("AbCdEfGhIj1")
    assert row and row["deleted_at"] is None
    assert "two-hour-talk_0123456789abcdef closing words" in Path(row["corpus_path"]).read_text(encoding="utf-8")
    assert server._library_transcript("AbCdEfGhIj1") is not None
    assert [h["video_id"] for h in lib.idx.search("closing words two hour", match="strict")] == ["AbCdEfGhIj1"]


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_restart_between_sidecar_and_index_finishes_the_save(lib):
    """A stop after the sidecar write but before indexing is found and finished."""
    folder = lib.add_video("cut-short", url=_x(7), video_id="1800000000000000007",
                           title="Stopped while saving", duration=120,
                           saved_at="2026-08-01T00:00:00", media=True)
    real_index = server._index_yoink
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SystemExit  # killed right here
        return real_index(*args, **kwargs)
    lib.mp.setattr(server, "_index_yoink", flaky)
    first = lib.backfill()
    first.start()
    first.wait(10)
    sidecar = json.loads((folder / "cut-short.json").read_text(encoding="utf-8"))
    assert sidecar["transcript_backfill"]["status"] == "saving"
    assert lib.idx.search("closing words", match="strict") == [], "not searchable yet"

    server._transcript_backfill_instance = None
    server._resume_transcript_backfill_at_boot()
    second = server._transcript_backfill_instance
    _wait(lambda: second._state["status"] == "done" and not second._alive(), message="repair")
    assert lib.asr_calls == ["cut-short"], "the saved words are reused, not transcribed again"
    sidecar = json.loads((folder / "cut-short.json").read_text(encoding="utf-8"))
    assert sidecar["transcript_backfill"]["status"] == "done"
    assert [h["video_id"] for h in lib.idx.search("closing words", match="strict")] == ["1800000000000000007"]


def test_new_capture_during_backfill_completes_promptly(lib):
    """The backfill waits at its next segment while the user captures."""
    lib.add_video("long-one", url=_x(8), video_id="1800000000000000008", title="A long save",
                  duration=3600, saved_at="2026-08-01T00:00:00", media=True)
    lib.segments["long-one"] = [(i * 10.0, i * 10.0 + 9, f"segment {i}") for i in range(60)]
    progress = []

    def hook(slug, number):
        if slug == "long-one":
            progress.append(time.monotonic())
            time.sleep(0.03)
        elif slug.startswith("fresh-capture"):
            time.sleep(0.6)  # the capture's own transcription takes a moment
    lib.segment_hook = hook
    job = lib.backfill()
    job.start()
    _wait(lambda: len(progress) >= 3, message="backfill progress")

    url = _x(9)
    metadata = {"id": "1800000000000000009", "title": "Fresh capture", "duration": 30,
                "uploader": "samplebuilder", "webpage_url": url, "thumbnails": []}
    folder = server.DESKTOP_ROOT / "AI" / "fresh-capture"
    started = time.monotonic()
    server._live_extract_begin(url)
    try:
        with server._manual_extraction_ownership(url) as ownership:
            assert ownership.ok
            before = len(progress)
            result = server._run_extraction(url, 30, folder, notify=False, metadata=metadata,
                                            generate_paste=False)
            during = len(progress) - before
            waiting = job.status()["current"]["waiting_for_capture"]
    finally:
        server._live_extract_end()
    elapsed = time.monotonic() - started
    assert result["ok"] is True and result["transcript_source"] == "asr"
    assert during <= 1, f"the backfill kept transcribing during the capture ({during} segments)"
    assert waiting is True, "the dashboard can say the backfill is waiting for the capture"
    assert elapsed < 5, f"the capture took {elapsed:.1f}s with a backfill running"
    assert not (folder / server.CAPTURE_INCOMPLETE_NAME).exists()
    _wait(lambda: lib.finished(), timeout=20, message="backfill to finish after the capture")
    sidecar = json.loads((server.DESKTOP_ROOT / "AI" / "long-one" / "long-one.json").read_text(encoding="utf-8"))
    assert len(sidecar["transcript"]) == 60


def test_pause_stops_at_a_segment_and_resume_carries_on(lib):
    lib.add_video("pausable", url=_x(10), video_id="1800000000000000010", title="Pause me",
                  duration=600, saved_at="2026-08-01T00:00:00", media=True)
    lib.add_video("next-up", url=_x(11), video_id="1800000000000000011", title="Next one",
                  duration=60, saved_at="2026-08-02T00:00:00", media=True)
    lib.segments["pausable"] = [(i, i + 1, f"line {i}") for i in range(40)]
    reached = threading.Event()

    def hook(slug, number):
        if slug == "pausable" and number == 5:
            reached.set()
        time.sleep(0.01)
    lib.segment_hook = hook
    job = lib.backfill()
    job.start()
    reached.wait(10)
    paused = job.pause()
    assert paused["state"] == "paused"
    assert job.wait(5), "pause stops at the next segment"
    assert json.loads((server.DATA_ROOT / tb.STATE_FILE).read_text(encoding="utf-8"))["status"] == "paused"
    assert lib.asr_calls == ["pausable"]
    sidecar = json.loads((server.DESKTOP_ROOT / "AI" / "pausable" / "pausable.json").read_text(encoding="utf-8"))
    assert sidecar["transcript"] == [], "a paused save keeps no half transcript"
    lib.segment_hook = None
    assert job.resume()["state"] == "running"
    _wait(lambda: lib.finished(), message="resumed run")
    assert job._state["status"] == "done"
    assert lib.asr_calls == ["pausable", "pausable", "next-up"]


def test_words_in_the_sidecar_are_never_listed_or_overwritten(lib):
    """Each guard holds on its own: stale index health, no corpus lines, a late apply."""
    folder = lib.add_video("stale-health", url=_x(24), video_id="1800000000000000024",
                           title="Words only in the sidecar", duration=300,
                           saved_at="2026-07-01T00:00:00", words=[(0.0, 2.0, "kept words")], media=True)
    with lib.idx.write_transaction() as conn:
        conn.execute("UPDATE yoinks SET health_score_json=NULL WHERE video_id=?", ("1800000000000000024",))
    corpus = folder / "stale-health.md"
    corpus.write_text("# Words only in the sidecar\n\n---\n\n## Transcript\n\n*older note*\n", encoding="utf-8")
    assert server._transcript_backfill_scan()["items"] == [], "sidecar words keep it off the list"
    before = lib.snapshot(folder)
    item = {"key": "1800000000000000024", "folder": str(folder), "url": _x(24),
            "sidecar_path": str(folder / "stale-health.json"), "corpus_path": str(corpus)}
    assert server._transcript_backfill_apply(item, [(0.0, 1.0, "new words")], "asr",
                                             {"status": "completed"}) == "skipped"
    assert lib.snapshot(folder) == before, "a save that has words is never touched"


def test_transcribe_media_checkpoint_runs_between_lazy_segments(tmp_path):
    """The real ASR wrapper calls the checkpoint before decoding the next segment."""
    media = tmp_path / "video.mp4"
    media.write_bytes(b"\x00")
    decoded, seen = [], []

    def lazy(_path):
        for n in range(4):
            decoded.append(n)
            yield types.SimpleNamespace(start=float(n), end=n + 1.0, text=f"line {n}")

    def checkpoint(segment):
        seen.append(segment.end)
        if segment.end == 2.0:
            raise tb.Paused()
    with pytest.raises(tb.Paused):
        reliability.transcribe_media(media, _transcribe=lazy, checkpoint=checkpoint)
    assert seen == [1.0, 2.0] and decoded == [0, 1], "nothing past the pause point is decoded"
    rows = reliability.transcribe_media(media, _transcribe=lazy)
    assert [r[2] for r in rows] == ["line 0", "line 1", "line 2", "line 3"]


def test_order_longest_or_newest():
    items = [
        {"key": "a", "duration": 60, "saved_at": "2026-11-01"},
        {"key": "b", "duration": 7200, "saved_at": "2026-07-01"},
        {"key": "c", "duration": None, "saved_at": "2026-10-01"},
        {"key": "d", "duration": 600, "saved_at": "2026-09-01"},
    ]
    assert [i["key"] for i in tb.order_items(items, "longest")] == ["b", "d", "a", "c"]
    assert [i["key"] for i in tb.order_items(items, "newest")] == ["a", "c", "d", "b"]


def _job(tmp_path, items, work, **kwargs):
    return tb.TranscriptBackfill(tmp_path, scan=lambda: {"items": [dict(i) for i in items]},
                                 work=work, capture_busy=lambda: False, **kwargs)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_file_that_stops_uoink_is_tried_twice_then_skipped(tmp_path):
    """P1: a media file that kills the helper must not kill it on every boot."""
    items = [{"key": "crasher", "title": "Crashes the transcriber", "duration": 900, "media": "on_disk"},
             {"key": "fine", "title": "Fine", "duration": 60, "media": "on_disk"}]
    calls = []

    def work(item, checkpoint, stop, network_ok):
        calls.append(item["key"])
        if item["key"] == "crasher":
            raise SystemExit  # the helper process dies here (segfault, out of memory)
        return {"outcome": "transcribed"}
    job = _job(tmp_path, items, work)
    job.start()
    job.wait(5)
    for _boot in range(3):
        job = _job(tmp_path, items, work)
        job.resume_after_restart()
        assert job.wait(5)
    assert calls == ["crasher", "crasher", "fine"], calls
    result = job._state["results"]["crasher"]
    assert result["outcome"] == "failed" and "stopped while transcribing" in result["reason"]
    assert job._state["status"] == "done" and job._state["attempts"] == {}
    assert job.status()["failed_items"][0]["key"] == "crasher"


def test_a_save_that_stays_busy_waits_longer_then_is_set_aside(tmp_path):
    """P1: busy is retried with growing waits, other saves go first, and it ends."""
    items = [{"key": "held", "duration": 900, "media": "on_disk"},
             {"key": "free", "duration": 60, "media": "on_disk"}]
    calls, times = [], []

    def work(item, checkpoint, stop, network_ok):
        calls.append(item["key"])
        times.append(time.monotonic())
        return {"outcome": "busy"} if item["key"] == "held" else {"outcome": "transcribed"}
    job = _job(tmp_path, items, work, busy_retry=0.002)
    job.start()
    assert job.wait(10), "a save that is always busy must not keep the run going forever"
    assert calls[:2] == ["held", "free"], "the run moves on to the next save"
    assert calls.count("held") == tb.MAX_BUSY_TRIES
    held = [t for k, t in zip(calls, times) if k == "held"]
    gaps = [b - a for a, b in zip(held, held[1:])]
    assert gaps[-1] > gaps[0], "each busy try waits longer"
    assert job._state["results"]["held"]["outcome"] == "failed"
    assert job._state["results"]["free"]["outcome"] == "transcribed"


def test_a_refusal_on_a_save_with_media_on_disk_waits_out_the_back_off(tmp_path):
    """P1: no 1 s retry loop against a site that just said slow down."""
    items = [{"key": "local", "duration": 60, "media": "on_disk", "host": "x"}]
    calls = []

    def work(item, checkpoint, stop, network_ok):
        calls.append(network_ok("x"))
        return {"outcome": "backoff", "host": "x", "kind": "rate_limited"}
    job = _job(tmp_path, items, work, busy_retry=0.01)
    job.start()
    time.sleep(1.5)
    status = job.status()
    assert calls == [True], f"asked the site again during its back-off: {calls}"
    assert status["state"] == "running" and status["backoff"]["x"]["seconds_left"] > 200
    job.pause()
    job.wait(5)


def test_a_finish_request_that_lands_as_the_worker_exits_is_not_stranded(tmp_path):
    """P2: finish(key) between "nothing left" and the worker's exit still runs."""
    items = [{"key": "folder:AI/late", "duration": 60, "media": "on_disk", "half": True}]
    done = []

    def work(item, checkpoint, stop, network_ok):
        done.append(item["key"])
        return {"outcome": "transcribed"}
    job = _job(tmp_path, items, work)
    real_next = job._next
    raced = {"n": 0}

    def racing_next():
        item, wait = real_next()
        if item is None and not raced["n"]:
            raced["n"] = 1
            assert job.finish("folder:AI/late")["ok"]  # arrives right here
        return item, wait
    job._next = racing_next
    with job._lock:
        job._launch()  # a worker with nothing queued yet (state idle)
    assert job.wait(5)
    assert done == ["folder:AI/late"], "the request was left in Queued"
    assert job._state["requested"] == []

    # Pause, resume while the old worker winds down, pause again: no stray worker.
    inside, release = threading.Event(), threading.Event()

    def slow(item, checkpoint, stop, network_ok):
        inside.set()
        release.wait(5)
        return {"outcome": "transcribed"}
    job2 = _job(tmp_path / "second", [{"key": "slow", "duration": 60, "media": "on_disk"}], slow)
    job2.start()
    assert inside.wait(5)
    job2.pause()
    job2.resume()
    assert job2._relaunch is True, "resume asks for a new worker after the old one exits"
    job2.pause()
    assert job2._relaunch is False, "a pause cancels the relaunch the resume asked for"
    release.set()
    assert job2.wait(5) and job2._thread is None


def test_strikes_reset_when_the_site_answers_and_fade_with_time(tmp_path):
    """P2: strikes do not pile up for good after one bad day."""
    clock = {"now": 1_000_000.0}
    items = [{"key": "a", "duration": 60, "media": "on_disk", "host": "youtube"}]
    job = _job(tmp_path, items, lambda *a: {"outcome": "transcribed"}, clock=lambda: clock["now"])
    with job._lock:
        job._strike("youtube", "rate_limited")
        job._strike("youtube", "rate_limited")
        assert job._state["backoff"]["youtube"]["strikes"] == 2
        clock["now"] += 3 * 3600
        job._settle(items[0], "a", {"outcome": "transcribed", "network_ok": ["youtube"]}, 1.0)
        assert "youtube" not in job._state["backoff"], "a normal answer clears the strikes"
        job._strike("youtube", "rate_limited")
        clock["now"] += tb.RATE_LIMIT_BACKOFF_SEC[0] + tb.STRIKE_MEMORY_SEC + 1
        job._strike("youtube", "rate_limited")
        entry = job._state["backoff"]["youtube"]
    assert entry["strikes"] == 1, "a strike long after the last wait starts over"
    assert entry["until"] - clock["now"] == tb.RATE_LIMIT_BACKOFF_SEC[0]
    with job._lock:
        job._strike("x", "rate_limited")
    clock["now"] += tb.RATE_LIMIT_BACKOFF_SEC[0] + 1
    job.start()
    assert "x" not in job._state["backoff"], "a new run forgets waits that already ended"
    job.wait(5)


def test_newest_first_run_order(lib):
    lib.add_video("older", url=_x(12), video_id="1800000000000000012", title="Older", duration=900,
                  saved_at="2026-07-01T00:00:00", media=True)
    lib.add_video("newer", url=_x(13), video_id="1800000000000000013", title="Newer", duration=30,
                  saved_at="2026-10-01T00:00:00", media=True)
    job = lib.backfill()
    job.start("newest")
    _wait(lambda: lib.finished(), message="newest-first run")
    assert lib.asr_calls == ["newer", "older"]
    assert job._state["order"] == "newest"


def test_rate_limit_backs_off_and_offline_work_continues(lib):
    lib.add_video("limited", url=_x(14), video_id="1800000000000000014", title="Limited",
                  duration=900, saved_at="2026-07-01T00:00:00")
    lib.add_video("local", url=_x(15), video_id="1800000000000000015", title="Local copy",
                  duration=60, saved_at="2026-07-02T00:00:00", media=True)
    lib.rate_limited_urls.add(_x(14))
    job = lib.backfill()
    job.start()
    _wait(lambda: "1800000000000000015" in job._state["results"] and job.status()["backoff"], message="back-off")
    status = job.status()
    assert status["backoff"]["x"]["seconds_left"] > 200
    assert status["state"] == "running", "the run waits instead of failing"
    assert lib.downloads == [_x(14)], "no second request during the back-off"
    assert status["count"] == 1 and "1800000000000000014" not in job._state["settled"]


def test_gone_at_fetch_is_recorded_and_not_retried(lib):
    lib.add_video("vanished", url=_x(16), video_id="1800000000000000016", title="Vanished",
                  duration=120, saved_at="2026-07-01T00:00:00")
    lib.gone_urls.add(_x(16))
    job = lib.backfill()
    job.start()
    _wait(lambda: lib.finished(), message="gone run")
    status = job.status()
    assert status["gone"] == 1 and status["count"] == 0
    assert job._state["settled"]["1800000000000000016"]["outcome"] == "gone"
    job.start()
    _wait(lambda: lib.finished(), message="second run")
    assert lib.downloads == [_x(16)], "a gone source is asked for once"
    sidecar = json.loads((server.DESKTOP_ROOT / "AI" / "vanished" / "vanished.json").read_text(encoding="utf-8"))
    assert sidecar["transcript"] == [] and "transcript_backfill" not in sidecar


def test_no_speech_is_saved_honestly_and_not_counted_again(lib):
    folder = lib.add_video("music-only", url=_x(17), video_id="1800000000000000017", title="Music",
                           duration=200, saved_at="2026-07-01T00:00:00", media=True)
    lib.segments["music-only"] = []
    job = lib.backfill()
    job.start()
    _wait(lambda: lib.finished(), message="no speech run")
    sidecar = json.loads((folder / "music-only.json").read_text(encoding="utf-8"))
    assert sidecar["asr_fallback"]["status"] == "no_speech"
    assert sidecar["health"]["transcript"] == "no speech"
    md = (folder / "music-only.md").read_text(encoding="utf-8")
    assert "No transcript: captions unavailable, and Whisper found no speech" in md
    assert "No captions available for this video." not in md
    status = job.status()
    assert status["count"] == 0 and status["no_words"] == 1


def test_youtube_save_gets_captions_before_any_asr(lib):
    url = "https://www.youtube.com/watch?v=CcDdEeFfGg2"
    folder = lib.add_video("yt-refused", url=url, video_id="CcDdEeFfGg2", title="Captions now",
                           duration=500, saved_at="2026-07-01T00:00:00", media=True)
    lib.caption_urls.add(url)
    job = lib.backfill()
    job.start()
    _wait(lambda: lib.finished(), message="captions run")
    assert lib.asr_calls == [], "captions came back, so no CPU was spent"
    sidecar = json.loads((folder / "yt-refused.json").read_text(encoding="utf-8"))
    assert sidecar["transcript_source"] == "captions"
    assert sidecar["transcript"][0]["text"] == "caption words from the source"
    assert "caption words from the source" in (folder / "yt-refused.md").read_text(encoding="utf-8")


def test_refused_captions_use_the_copy_on_disk_and_rest_youtube(lib):
    """YouTube says 429: the save still gets words, and the next one skips captions."""
    first, second = "https://www.youtube.com/watch?v=RrSsTtUuVv3", "https://youtu.be/WwXxYyZz004"
    lib.add_video("yt-limited", url=first, video_id="RrSsTtUuVv3", title="Refused captions",
                  duration=800, saved_at="2026-07-01T00:00:00", media=True)
    lib.add_video("yt-next", url=second, video_id="WwXxYyZz004", title="Next YouTube save",
                  duration=100, saved_at="2026-07-02T00:00:00", media=True)
    lib.refused_caption_urls.update({first, second})
    job = lib.backfill()
    job.start()
    _wait(lambda: lib.finished(), message="refused captions run")
    assert lib.caption_fetches == [first], "no caption request while YouTube rests"
    assert lib.asr_calls == ["yt-limited", "yt-next"]
    status = job.status()
    assert status["backoff"]["youtube"]["reason"] == "rate_limited"
    assert status["count"] == 0 and status["progress"]["transcribed"] == 2
    sidecar = json.loads((server.DESKTOP_ROOT / "AI" / "yt-limited" / "yt-limited.json").read_text(encoding="utf-8"))
    assert sidecar["transcript_note"] == "Local Whisper transcript: YouTube refused captions"
    assert sidecar["captions_skipped_reason"] == server.CAPTIONS_RATE_LIMITED


def test_missing_model_refuses_to_start(lib):
    lib.add_video("waits", url=_x(18), video_id="1800000000000000018", title="Waits", duration=60,
                  saved_at="2026-07-01T00:00:00", media=True)
    lib.model_cached = False
    result = lib.backfill().start()
    assert result["ok"] is False and "transcription model" in result["error"]
    assert result["state"] == "idle" and lib.asr_calls == []


def test_killed_capture_leaves_a_folder_that_says_so_and_finish_completes_it(lib):
    """A capture killed during transcription is marked, listed and finishable."""
    url = _x(19)
    metadata = {"id": "1800000000000000019", "title": "Killed midway", "duration": 90,
                "uploader": "samplebuilder", "webpage_url": url, "thumbnails": []}
    folder = server.DESKTOP_ROOT / "AI" / "killed-midway"

    def die(slug, number):
        if slug == "killed-midway":
            raise SystemExit
    lib.segment_hook = die
    with pytest.raises(SystemExit):
        server._run_extraction(url, 30, folder, notify=False, metadata=metadata, generate_paste=False)
    lib.segment_hook = None
    note = (folder / server.CAPTURE_INCOMPLETE_NAME).read_text(encoding="utf-8")
    assert "has not finished saving" in note and "press Finish" in note
    assert (folder / "video.mp4").exists() and not (folder / "killed-midway.json").exists()
    status = server._transcript_backfill_status()
    half = status["half_captures"]
    assert [h["title"] for h in half] == ["Killed midway"] and half[0]["media"] == "on_disk"
    downloads_before = list(lib.downloads)

    result = lib.backfill().finish(half[0]["key"])
    assert result["ok"] is True
    _wait(lambda: lib.finished() and not lib.backfill()._state["requested"], timeout=20, message="finish")
    assert lib.downloads == downloads_before, "Finish reuses the video on disk"
    sidecar = json.loads((folder / "killed-midway.json").read_text(encoding="utf-8"))
    assert sidecar["transcript_source"] == "asr"
    assert not (folder / server.CAPTURE_INCOMPLETE_NAME).exists()
    assert (folder / "video.mp4").exists()
    assert lib.idx.get_yoink("1800000000000000019") is not None
    assert lib.backfill()._state["status"] == "idle", "Finish never starts the whole run"


def test_successful_capture_leaves_no_note(lib):
    url = _x(20)
    metadata = {"id": "1800000000000000020", "title": "Clean capture", "duration": 30,
                "uploader": "samplebuilder", "webpage_url": url, "thumbnails": []}
    folder = server.DESKTOP_ROOT / "AI" / "clean-capture"
    result = server._run_extraction(url, 30, folder, notify=False, metadata=metadata, generate_paste=False)
    assert result["ok"] is True
    assert not (folder / server.CAPTURE_INCOMPLETE_NAME).exists()
    assert not (folder / "video.mp4").exists(), "normal captures still clean up their video"


def test_capture_in_progress_is_not_listed_as_half(lib):
    folder = lib.add_half_capture("in-flight", url=_x(21), video_id="1800000000000000021",
                                  title="Still capturing", duration=60)
    key = server._manual_capture_key(_x(21))
    lock = server._ServerCaptureBackend.acquire_identity(key)  # what a running capture holds
    try:
        assert lock, "test holds the identity like a running capture"
        assert server._transcript_backfill_scan()["items"] == []
    finally:
        server._ServerCaptureBackend.release_identity(key, lock)
    assert [i["title"] for i in server._transcript_backfill_scan()["items"]] == ["Still capturing"]
    assert folder.exists()


def test_scanning_a_half_capture_does_not_claim_it(lib):
    url = _x(34)
    lib.add_half_capture("asr-off-half", url=url, video_id="1800000000000000034",
                         title="Finish with ASR off", duration=60)
    locks = server.source_subscriptions.CaptureLock
    key = server._manual_capture_key(url)
    path = Path(locks.path_for(lib.data, key))
    assert [item["key"] for item in server._transcript_backfill_scan()["items"]] == ["folder:AI/asr-off-half"]
    assert not path.exists(), "a status scan must not take the worker's capture lock"
    # A CLI capture holds the OS lock without registering a helper-local identity.
    with locks.try_acquire(lib.data, key):
        assert server._transcript_backfill_scan()["items"] == []
    assert len(server._transcript_backfill_scan()["items"]) == 1


def _meta(n: int, title: str, duration: int = 60) -> dict:
    return {"id": f"18000000000000000{n:02d}", "title": title, "duration": duration,
            "uploader": "samplebuilder", "webpage_url": _x(n), "thumbnails": []}


@pytest.mark.parametrize("other", ["capture", "playlist"])
def test_finish_and_a_capture_of_the_same_save_never_deadlock(lib, other):
    """P1: one lock order. Finish holds the save's lock, so it never waits for a capture."""
    url = _x(30)
    folder = lib.add_half_capture("same-save", url=url, video_id="1800000000000000030",
                                  title="Wanted twice", duration=600)
    slug, key = folder.name, "folder:AI/" + folder.name
    lib.segments[slug] = [(i, i + 1.0, f"line {i}") for i in range(400)]
    asr_started = threading.Event()

    def hook(name, number):
        if name == slug:
            asr_started.set()
            time.sleep(0.01)
    lib.segment_hook = hook
    job = lib.backfill()
    assert job.finish(key)["ok"]
    assert asr_started.wait(10)
    assert key in [i["key"] for i in server._transcript_backfill_scan()["items"]], \
        "the save being finished stays listed (the row says Finishing)"

    other_started, other_done, got_lock = threading.Event(), threading.Event(), threading.Event()

    def another_capture():  # W: a different capture that runs for a while
        server._live_extract_begin(_x(31))
        other_started.set()
        other_done.wait(15)
        server._live_extract_end()
    if other == "capture":
        threading.Thread(target=another_capture, daemon=True).start()
        assert other_started.wait(5)
    else:
        lib.mp.setitem(server._jobs, "fixture-playlist", {"state": "running", "kind": "playlist"})
    time.sleep(0.3)  # the backfill reaches its next segment while W runs

    def same_save():  # U: a capture of the very save Finish is working on
        if other == "capture":
            server._live_extract_begin(url)
        try:
            with server._manual_extraction_ownership(url) as ownership:
                if ownership.ok:
                    got_lock.set()
        finally:
            if other == "capture":
                server._live_extract_end()
    threading.Thread(target=same_save, daemon=True).start()
    time.sleep(0.2)
    other_done.set()  # W ends while U still waits for the save's lock
    acquired = got_lock.wait(5)
    server._jobs.pop("fixture-playlist", None)
    assert acquired, "deadlock: the capture never got the save while Finish held it"
    _wait(lambda: lib.finished() and not job._state["requested"], timeout=30, message="Finish after the capture")
    assert job._state["results"][key]["outcome"] == "transcribed"
    assert (folder / f"{slug}.json").exists() and not (folder / server.CAPTURE_INCOMPLETE_NAME).exists()


def test_capture_note_lives_until_the_sidecar_and_the_index_are_written(lib):
    """P1: a good re-capture clears an old note, and a failed index write keeps it."""
    folder = lib.add_half_capture("recaptured", url=_x(32), video_id="1800000000000000032",
                                  title="Captured again", duration=60)
    result = server._run_extraction(_x(32), 30, folder, notify=False,
                                    metadata=_meta(32, "Captured again"), generate_paste=False)
    assert result["ok"] is True and Path(result["folder"]) == folder
    assert lib.idx.get_yoink("1800000000000000032") is not None
    assert not (folder / server.CAPTURE_INCOMPLETE_NAME).exists(), "a good re-capture leaves no stale note"

    def index_down(*args, **kwargs):
        raise RuntimeError("the index is not answering")
    lib.mp.setattr(server, "_index_yoink", index_down)
    second = server.DESKTOP_ROOT / "AI" / "index-fails"
    with pytest.raises(Exception):
        server._run_extraction(_x(33), 30, second, notify=False,
                               metadata=_meta(33, "Index fails"), generate_paste=False)
    assert (second / server.CAPTURE_INCOMPLETE_NAME).exists(), "not finished until the index has it"


def test_finish_and_the_backfill_work_with_local_asr_turned_off(lib):
    """P2: the user's own Start or Finish runs ASR without changing the setting."""
    lib.settings["asr_fallback_enabled"] = False
    before = dict(lib.settings)
    lib.add_half_capture("asr-off-half", url=_x(34), video_id="1800000000000000034",
                         title="Finish with ASR off", duration=60)
    lib.add_video("asr-off-save", url=_x(35), video_id="1800000000000000035", title="ASR off",
                  duration=30, saved_at="2026-07-01T00:00:00", media=True)
    job = lib.backfill()
    job.start()
    _wait(lambda: lib.finished(), timeout=20, message="run with ASR off")
    results = job._state["results"]
    assert results["folder:AI/asr-off-half"]["outcome"] == "transcribed", results
    assert results["1800000000000000035"]["outcome"] == "transcribed", results
    assert lib.settings == before, "the user's settings are never changed"
    server._write_settings.assert_not_called()


def test_saves_outside_the_library_and_unreadable_corpus_files_are_left_alone(lib, tmp_path):
    """P2: only files inside the library are written, and unreadable means do not touch."""
    far = lib.add_video("moved-away", url=_x(36), video_id="1800000000000000036",
                        title="Row points outside", duration=60, saved_at="2026-07-01T00:00:00",
                        media=True, base=tmp_path / "old-library")
    (far / "moved-away.md").unlink()  # only the sidecar path is left to judge by
    garbled = lib.add_video("garbled", url=_x(37), video_id="1800000000000000037",
                            title="Unreadable corpus", duration=60, saved_at="2026-07-01T00:00:00", media=True)
    (garbled / "garbled.md").write_bytes(b"# \xff\xfe not text\n")
    md_only = lib.add_video("md-only", url=_x(38), video_id="1800000000000000038",
                            title="Words only in the Markdown", duration=60,
                            saved_at="2026-07-01T00:00:00", media=True)
    (md_only / "md-only.md").write_text(
        "# Words only in the Markdown\n\n---\n\n## Transcript\n\n[0:01] words from an older save\n",
        encoding="utf-8")
    keys = {i["key"] for i in server._transcript_backfill_scan()["items"]}
    assert "1800000000000000036" not in keys, "a row pointing outside the library is never listed"
    assert "1800000000000000037" not in keys, "an unreadable corpus is not 'no words'"
    for folder, slug, n in ((far, "moved-away", 36), (md_only, "md-only", 38), (garbled, "garbled", 37)):
        before = lib.snapshot(folder)
        item = {"key": f"18000000000000000{n}", "folder": str(folder), "url": _x(n),
                "sidecar_path": str(folder / f"{slug}.json"), "corpus_path": str(folder / f"{slug}.md")}
        assert server._transcript_backfill_apply(item, [(0.0, 1.0, "new words")], "asr",
                                                 {"status": "completed"}) == "skipped", slug
        assert lib.snapshot(folder) == before, f"{slug} must not be touched"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_reindex_during_an_interrupted_save_does_not_strand_it(lib):
    """P2: stopped after the sidecar, reindexed by a tag edit, still finished later."""
    folder = lib.add_video("reindexed", url=_x(39), video_id="1800000000000000039",
                           title="Tagged mid-save", duration=120, saved_at="2026-07-01T00:00:00", media=True)
    real = server._transcript_text_from_sidecar
    calls = {"n": 0}

    def die_once(sidecar):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SystemExit  # killed after the sidecar write, before the Markdown
        return real(sidecar)
    lib.mp.setattr(server, "_transcript_text_from_sidecar", die_once)
    first = lib.backfill()
    first.start()
    first.wait(10)
    sidecar_path = folder / "reindexed.json"
    on_disk = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert on_disk["transcript_backfill"]["status"] == "saving"
    # Something else reindexes the save from the file meanwhile (a tag edit does).
    assert server._index_yoink(folder, on_disk, folder / "reindexed.md", sidecar_path)
    server._transcript_backfill_instance = None
    server._resume_transcript_backfill_at_boot()
    second = server._transcript_backfill_instance
    _wait(lambda: second._state["status"] == "done" and not second._alive(), message="repair after a reindex")
    assert "reindexed closing words" in (folder / "reindexed.md").read_text(encoding="utf-8")
    saved = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert saved["transcript_backfill"]["status"] == "done" and saved["health"]["transcript"] == "ok"
    assert lib.asr_calls == ["reindexed"], "the saved words are reused"


def test_finish_reuses_only_a_real_video_and_keeps_the_topic_folder(lib):
    """P2/P3: a 0-byte or audio-only leftover is fetched again; the topic folder stays."""
    empty = lib.add_half_capture("empty-video", url=_x(40), video_id="1800000000000000040",
                                 title="Download stopped at zero bytes", duration=60,
                                 topic="Cooking", media_bytes=b"")
    lib.add_half_capture("audio-only", url=_x(41), video_id="1800000000000000041",
                         title="Only audio left", duration=60, media_name="audio.m4a")
    items = {i["key"]: i for i in server._transcript_backfill_scan()["items"]}
    assert items["folder:Cooking/empty-video"]["media"] == "download"
    assert items["folder:AI/audio-only"]["media"] == "download", "Finish needs a video, so it fetches one"
    job = lib.backfill()
    assert job.finish("folder:Cooking/empty-video")["ok"]
    _wait(lambda: lib.finished() and not job._state["requested"], timeout=20, message="finish")
    assert job._state["results"]["folder:Cooking/empty-video"]["outcome"] == "transcribed"
    assert _x(40) in lib.downloads, "a 0-byte video is fetched again, not reused"
    assert json.loads((empty / "empty-video.json").read_text(encoding="utf-8"))["topic"] == "Cooking"
    assert lib.idx.get_yoink("1800000000000000040")["topic"] == "Cooking"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_repaired_no_speech_save_counts_as_no_speech(lib):
    """P3: finishing an interrupted save keeps what it found (no speech is not words)."""
    lib.add_video("quiet-cut", url=_x(43), video_id="1800000000000000043", title="Only music",
                  duration=120, saved_at="2026-07-01T00:00:00", media=True)
    lib.segments["quiet-cut"] = []
    real_index = server._index_yoink
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SystemExit
        return real_index(*args, **kwargs)
    lib.mp.setattr(server, "_index_yoink", flaky)
    first = lib.backfill()
    first.start()
    first.wait(10)
    server._transcript_backfill_instance = None
    server._resume_transcript_backfill_at_boot()
    second = server._transcript_backfill_instance
    _wait(lambda: second._state["status"] == "done" and not second._alive(), message="repair")
    progress = second.status()["progress"]
    assert progress["no_words"] == 1 and progress["transcribed"] == 0, progress


def test_media_without_audio_waits_for_a_resting_site_instead_of_asking_it(lib):
    """P1: ASR's source-audio fetch gets no link while that site is backed off."""
    lib.add_video("silent-clip", url=_x(42), video_id="1800000000000000042", title="No audio track",
                  duration=60, saved_at="2026-07-01T00:00:00", media=True)
    lib.silent.add("silent-clip")
    job = lib.backfill()
    with job._lock:
        job._strike("x", "rate_limited")
    item = next(i for i in server._transcript_backfill_scan()["items"] if i["key"] == "1800000000000000042")
    result = server._transcript_backfill_work(item, job._checkpoint, job._stop, job.network_ok)
    assert result == {"outcome": "wait_network", "host": "x"}
    assert lib.downloads == [], "no request to a site that is resting"
    # Finishing a stopped capture also asks the site for things: it waits too.
    lib.add_half_capture("resting-half", url=_x(44), video_id="1800000000000000044",
                         title="Waits for X", duration=60)
    half = next(i for i in server._transcript_backfill_scan()["items"] if i.get("half"))
    assert half["media"] == "on_disk"
    result = server._transcript_backfill_work(half, job._checkpoint, job._stop, job.network_ok)
    assert result == {"outcome": "wait_network", "host": "x"}
    assert lib.asr_calls == [] and lib.downloads == []


def test_http_routes_and_token_gate(lib):
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    # Loopback only: the test talks to its own in-process helper.
    lib.mp.setattr(server.urllib.request, "urlopen", REAL_URLOPEN)
    lib.mp.setattr(server.socket, "create_connection", REAL_CREATE_CONNECTION)
    lib.add_video("via-http", url=_x(22), video_id="1800000000000000022", title="Over HTTP",
                  duration=60, saved_at="2026-07-01T00:00:00", media=True)
    # Port 0: never the resident helper port, whatever the environment says.
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    lib.mp.setattr(server, "PORT", httpd.server_address[1])
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def call(method, path, body=None, token=True):
        headers = {"X-Uoink-Token": server.TOKEN} if token else {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"http://127.0.0.1:{server.PORT}{path}",
                                         data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")
    try:
        status, _ = call("GET", "/library/transcript-backfill", token=False)
        assert status in (401, 403)
        status, body = call("GET", "/library/transcript-backfill")
        assert status == 200 and body["count"] == 1 and body["state"] == "idle"
        status, body = call("POST", "/library/transcript-backfill/start", {"order": "sideways"})
        assert status == 400
        status, body = call("POST", "/library/transcript-backfill/start", {"order": "newest"})
        assert status == 200 and body["state"] in ("running", "done")
        _wait(lambda: lib.finished(), message="http run")
        status, body = call("GET", "/library/transcript-backfill")
        assert body["state"] == "done" and body["count"] == 0 and body["progress"]["transcribed"] == 1
        status, body = call("POST", "/library/transcript-backfill/pause", {})
        assert status == 200
        status, body = call("POST", "/library/transcript-backfill/finish", {"key": "folder:nope"})
        assert status == 409 and body["ok"] is False
        for action in ("start", "pause", "resume", "finish"):
            status, _ = call("POST", f"/library/transcript-backfill/{action}", {"key": "k"}, token=False)
            assert status in (401, 403), f"POST {action} without the token"
        status, body = call("POST", "/library/transcript-backfill/finish", {})
        assert status == 400 and body["ok"] is False
        status, body = call("POST", "/library/transcript-backfill/sideways", {})
        assert status == 404
        status, body = call("POST", "/library/transcript-backfill/extra/start", {})
        assert status == 404, "only one action segment is accepted"
        assert lib.backfill()._state["status"] == "done", "nothing above started a run"
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---- CLI: uoink backfill status|start|pause|resume --------------------------
def test_cli_backfill_talks_to_the_running_helper(lib, capsys):
    import argparse
    from http.server import ThreadingHTTPServer
    import uoink_cli as cli
    lib.mp.setattr(server.urllib.request, "urlopen", REAL_URLOPEN)
    lib.mp.setattr(server.socket, "create_connection", REAL_CREATE_CONNECTION)
    lib.add_video("via-cli", url=_x(23), video_id="1800000000000000023", title="From the terminal",
                  duration=90, saved_at="2026-07-01T00:00:00", media=True)
    # Port 0: never the resident helper port, whatever the environment says.
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    lib.mp.setattr(server, "PORT", httpd.server_address[1])
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def run(action, order=None):
        ns = argparse.Namespace(action=action, order=order)
        return cli.backfill_command(ns, server, running=True)
    try:
        status = run("status")
        assert status["ok"] is True and status["count"] == 1 and status["state"] == "idle"
        text = cli.human(status)
        assert text.startswith("1 save has video but no transcript (1 on this computer, 0 to fetch again).")
        assert "uoink backfill start" in text and "CPU" in text
        started = run("start", "newest")
        assert started["ok"] is True and started["order"] == "newest"
        _wait(lambda: lib.finished(), message="cli run")
        done = run("status")
        assert done["count"] == 0 and done["state"] == "done"
        assert cli.human(done).startswith("Every save with video has its words.\nLast run: 1 transcribed")
        assert run("pause")["ok"] is True
        resumed = run("resume")
        assert resumed["ok"] is True and resumed["state"] == "done", "resume after a finished run is a no-op"
        assert lib.asr_calls == ["via-cli"]
        # The real entry point: exit 0 on success, 1 when the helper refuses.
        import uoink_agent_runtime as runtime
        lib.mp.setattr(runtime, "helper_running", lambda backend: True)
        capsys.readouterr()
        assert cli.main(["backfill", "status"]) == 0
        assert json.loads(capsys.readouterr().out)["state"] == "done"
        lib.model_cached = False
        assert cli.main(["backfill", "start"]) == 1
        refused = json.loads(capsys.readouterr().out)
        assert refused["ok"] is False and "transcription model" in refused["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_cli_backfill_without_the_helper_says_what_to_do(monkeypatch, capsys):
    import uoink_agent_runtime as runtime
    import uoink_cli as cli
    monkeypatch.setattr(runtime, "helper_running", lambda backend: False)
    monkeypatch.setattr(server.urllib.request, "urlopen",
                        Mock(side_effect=AssertionError("no HTTP when the helper is off")))
    assert cli.main(["backfill", "status"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out == {"ok": False, "error": "The Uoink helper is not running. Open Uoink, then try again."}
    assert cli.main(["backfill", "pause", "--order", "newest"]) == 2
    assert "--order goes with start" in capsys.readouterr().err
    assert cli.main(["backfill", "sideways"]) == 2
    assert "backfill" in cli.parser().format_help()


def test_cli_backfill_text_for_a_big_running_library():
    import uoink_cli as cli
    text = cli.human({
        "ok": True, "state": "running", "count": 512, "on_disk": 140, "download": 372, "gone": 19,
        "no_words": 4, "half_capture_count": 2, "pausing": False, "order": "longest", "message": None,
        "progress": {"done": 12, "left": 500, "total": 512, "eta_seconds": 11400, "transcribed": 10,
                     "no_words": 1, "gone": 1, "failed": 0},
        "current": {"key": "a", "title": "A very long talk about making things", "fraction": 0.4,
                    "waiting_for_capture": True},
        "backoff": {"x": {"seconds_left": 1080, "reason": "rate_limited"}}, "model_ready": True,
    })
    assert text.splitlines() == [
        "512 saves have video but no transcript (140 on this computer, 372 to fetch again).",
        "Running: 12 done, 500 left, about 3 h 10 min to go.",
        "Now: A very long talk about making things (40%)",
        "Waiting while your capture finishes.",
        "X asked Uoink to slow down. Trying again in 18 min.",
        "19 saves can't be transcribed because the video is gone and no copy is on this computer.",
        "2 captures did not finish. Finish them in Uoink under Settings, Library health.",
    ]
    pausing = cli.backfill_text({"state": "paused", "pausing": True, "count": 3, "on_disk": 3,
                                 "download": 0, "progress": {"done": 1, "left": 2}})
    assert "Pausing at the next safe point. The save in hand starts over on resume." in pausing


def test_repo_launchers_route_backfill_to_the_cli():
    root = Path(__file__).resolve().parent.parent
    assert "|status|backfill|" in (root / "uoink").read_text(encoding="utf-8")
    assert " status backfill " in (root / "uoink.cmd").read_text(encoding="utf-8")

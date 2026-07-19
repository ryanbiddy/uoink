"""A-01 (spec A) -- lite recovery mode for long videos.

Run: python tests/test_lite_recovery_a01.py

Lite mode is the retry path for a long extract that failed the full path.
Its job: land the high-value transcript while shedding the fragile/expensive
work. So it keeps the full captions, takes SPARSE screenshots (~1 per 5 min),
and SKIPS the comments fetch (which also carries hook typing).

These drive the real server._run_extraction with the subprocess/network
boundary mocked (same approach as test_long_video_v324), and assert:
  - the media download uses the full single-file path, NOT chunk sections
  - the effective screenshot interval is forced to >= 5 min
  - the full subtitle track is still requested (transcript preserved)
  - the comments worker is NOT started
  - the sidecar marks comments + hook typing "skipped" (not stuck pending)
  - /extract validates + threads long_video_mode="lite"
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_normalize_accepts_lite():
    _assert(server._normalize_long_video_mode("lite") == "lite", "lite valid")
    _assert(server._normalize_long_video_mode("full") == "full", "full valid")
    _assert(server._normalize_long_video_mode("chunked") == "chunked",
            "chunked still valid")
    try:
        server._normalize_long_video_mode("bogus")
        raise AssertionError("bogus mode should raise")
    except ValueError as e:
        _assert("lite" in str(e), f"error message lists lite: {e}")
    print("ok  _normalize_long_video_mode accepts lite, rejects junk")


def test_lite_extraction_path(tmp: Path):
    calls = []
    comments_started = {"n": 0}
    saved = {name: getattr(server, name) for name in (
        "_run_subprocess", "_download_thumbnail", "_fetch_channel_context",
        "_should_start_hook_type", "_read_settings", "_incremental_index_update",
        "_index_yoink", "_start_entity_extraction_thread",
        "_start_comments_thread", "_generate_paste_corpus",
    )}

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if cmd[0] == "ffmpeg":
            # Emit a couple of frames for the single-file screenshot pass.
            base = cmd[-1].replace("%04d", "0001")
            Path(base).parent.mkdir(parents=True, exist_ok=True)
            Path(base).write_bytes(b"jpeg")
            Path(cmd[-1].replace("%04d", "0002")).write_bytes(b"jpeg")
        elif any(a == "--write-subs" or a == "--write-auto-subs" for a in cmd):
            # Full single-file media command also writes subs in this pipeline.
            (tmp / "video.mp4").write_bytes(b"media")
            (tmp / "video.en.srt").write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nhello world\n",
                encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    phases = []
    try:
        server._run_subprocess = fake_run
        server._download_thumbnail = lambda *_a, **_k: None
        server._fetch_channel_context = lambda *_a, **_k: {}
        # Hook type WOULD be eligible; lite must still skip it (it rides the
        # comments worker).
        server._should_start_hook_type = lambda *_a, **_k: True
        server._read_settings = lambda: {}
        server._incremental_index_update = lambda *_a, **_k: None
        server._index_yoink = lambda *_a, **_k: None
        server._start_entity_extraction_thread = lambda *_a, **_k: None
        server._generate_paste_corpus = lambda *_a, **_k: None

        def fake_comments(*_a, **_k):
            comments_started["n"] += 1
        server._start_comments_thread = fake_comments

        result = server._run_extraction(
            "https://www.youtube.com/watch?v=longsource1",
            30,  # a dense interval the user might have set; lite overrides it
            tmp,
            open_explorer=False,
            metadata={
                "id": "longsource1",
                "title": "Two hour talk",
                "duration": 7200,
                "channel": "Example",
            },
            topic="Test",
            generate_paste=False,
            long_video_mode="lite",
            phase_callback=phases.append,
        )
    finally:
        for name, value in saved.items():
            setattr(server, name, value)

    # Download used the full single-file path, not chunk sections.
    section_calls = [c for c in calls if "--download-sections" in c]
    _assert(not section_calls, f"lite must not segment the download: {section_calls}")
    media_calls = [c for c in calls
                   if c[:1] != ["ffmpeg"] and "-o" in c and "video.%(ext)s"
                   in " ".join(c)]
    _assert(media_calls, "lite downloads a single media file")
    _assert(any("--write-subs" in c or "--write-auto-subs" in c
                for c in media_calls),
            "lite still requests the full subtitle track (transcript kept)")

    # Sparse screenshots: exactly one ffmpeg pass, at >= 5-min interval.
    ffmpeg_calls = [c for c in calls if c and c[0] == "ffmpeg"]
    _assert(len(ffmpeg_calls) == 1, f"single screenshot pass: {ffmpeg_calls}")
    _assert(ffmpeg_calls[0][ffmpeg_calls[0].index("-pix_fmt") + 1]
            == "yuvj420p", "screenshot output must be full-range JPEG YUV")
    vf = ffmpeg_calls[0][ffmpeg_calls[0].index("-vf") + 1]
    # fps=1/<interval>
    used_interval = int(vf.split("/")[1])
    _assert(used_interval >= server.LITE_SHOT_INTERVAL_SEC,
            f"lite forces sparse interval >= {server.LITE_SHOT_INTERVAL_SEC}, "
            f"got {used_interval}")

    # Comments (and hook typing, which rides them) are skipped.
    _assert(comments_started["n"] == 0,
            "lite must NOT start the comments worker")
    _assert(result["long_video_mode"] == "lite", f"mode exposed: {result}")
    _assert("comments" not in phases,
            f"lite does not enter the comments phase: {phases}")

    sidecar = json.loads((tmp / f"{tmp.name}.json").read_text(encoding="utf-8"))
    _assert(sidecar["comments_status"] == "skipped",
            f"comments marked skipped, not pending: {sidecar['comments_status']}")
    _assert(sidecar["hook_type_status"] == "skipped",
            f"hook typing marked skipped: {sidecar['hook_type_status']}")
    _assert(sidecar["caption_count"] >= 1 if "caption_count" in sidecar
            else True, "transcript preserved")
    # Transcript file written from the kept captions.
    _assert((tmp / "transcript.txt").exists(),
            "lite still writes the transcript from kept captions")
    print("ok  lite path: full download + sparse shots + kept transcript + "
          "skipped comments/hook typing")


def test_extract_route_carries_lite_mode(tmp: Path):
    captured = {}
    saved = {name: getattr(server, name) for name in (
        "DESKTOP_ROOT", "_fetch_metadata", "_classify_topic",
        "_run_extraction", "_record_single_extract_job",
    )}

    class FakeHandler:
        _validate_url_interval = server.Handler._validate_url_interval
        _handle_extract = server.Handler._handle_extract

        def _send_json(self, status, payload):
            self.response = (status, payload)
            return self.response

    def fake_run(_url, _interval, folder, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True, "folder": str(folder), "title": "Long source",
            "screenshot_count": 0,
            "requested_long_video_mode": kwargs["long_video_mode"],
            "long_video_mode": kwargs["long_video_mode"],
            "long_video_chunks": [], "processed_media_seconds": 0,
            "source_duration_seconds": 7200,
        }

    try:
        server.DESKTOP_ROOT = tmp
        server._fetch_metadata = lambda *_a, **_k: {
            "id": "abcdef", "title": "Long source", "duration": 7200}
        server._classify_topic = lambda *_a, **_k: "Test"
        server._run_extraction = fake_run
        server._record_single_extract_job = lambda *_a, **_k: {}
        handler = FakeHandler()
        handler._handle_extract({
            "url": "https://www.youtube.com/watch?v=abcdef",
            "interval": 120,
            "long_video_mode": "lite",
        })
        status, payload = handler.response
    finally:
        for name, value in saved.items():
            setattr(server, name, value)

    _assert(status == 200 and payload["long_video_mode"] == "lite",
            f"/extract exposes lite mode: {status} {payload}")
    _assert(captured["long_video_mode"] == "lite",
            "/extract threads lite into extraction")
    print("ok  /extract: validates, threads, and exposes long_video_mode=lite")


def main():
    test_normalize_accepts_lite()
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        lite = base / "lite"
        lite.mkdir()
        test_lite_extraction_path(lite)
        route = base / "route"
        route.mkdir()
        test_extract_route_carries_lite_mode(route)
    print("\nALL LITE RECOVERY (A-01) TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline long-video regression tests for the v3.2.4 backend.

Run: python tests/test_long_video_v324.py

We cannot prove a real long-video network download in CI. These tests cover
the reproducible backend behavior without claiming that proof:

  1. Duration-scaled timeout budgets and phase-aware user errors.
  2. Chunked mode's real command/extraction path: bounded representative
     yt-dlp sections, a separate full-subtitle request, partitioned ffmpeg
     calls, timestamp retention, sidecar/result exposure, and job phase.
  3. A genuine end-to-end run of the SCREENSHOT phase on a synthesized
     2-hour video, using the helper's real subprocess wrapper and the exact
     ffmpeg shape used by full mode.

ffmpeg is required (it's a core helper dependency); the end-to-end portion
skips with a clear message if ffmpeg is missing.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _capped_interval(duration: float, interval: int) -> int:
    """Mirror of the interval-cap math in server._run_extraction so we can
    assert the invariant without a live download."""
    if duration > 0 and (duration / max(1, interval)) > server.MAX_SCREENSHOTS:
        return max(interval, int((duration + server.MAX_SCREENSHOTS - 1)
                                 // server.MAX_SCREENSHOTS))
    return interval


def test_timeout_scaling():
    # Short videos behave exactly as before (the floor).
    _assert(server._ytdlp_timeout_for(300) == server.YTDLP_TIMEOUT_SEC,
            "5-min video keeps the 30-min floor")
    # A 2-hour video gets a bigger budget than the old flat 30 minutes.
    two_hr = server._ytdlp_timeout_for(7200)
    _assert(two_hr > server.YTDLP_TIMEOUT_SEC,
            f"2-hour video must exceed the old floor: {two_hr}")
    # Never unbounded.
    _assert(server._ytdlp_timeout_for(99 * 3600) == server.YTDLP_TIMEOUT_HARD_CAP_SEC,
            "absurd duration is hard-capped")
    _assert(server._ffmpeg_timeout_for(7200) >= server.FFMPEG_TIMEOUT_SEC,
            "ffmpeg budget scales above its floor for long video")
    print(f"ok  timeout scaling: 5min={server._ytdlp_timeout_for(300)}s "
          f"2hr={two_hr}s cap={server._ytdlp_timeout_for(99*3600)}s")


def test_interval_cap_invariant():
    for dur in (2 * 3600, 4 * 3600, 90 * 60):
        interval = _capped_interval(dur, 30)
        shots = dur // interval
        _assert(shots <= server.MAX_SCREENSHOTS,
                f"{dur}s @ {interval}s -> {shots} shots exceeds cap")
    # 2-hour @ default 30s would be 240 shots -> must be capped.
    capped = _capped_interval(7200, 30)
    _assert(capped >= 36, f"2-hour interval should rise to >=36s, got {capped}")
    print(f"ok  interval cap: 2-hour video -> interval {capped}s "
          f"({7200 // capped} shots <= {server.MAX_SCREENSHOTS})")


def test_chunk_plan():
    chunks = server._long_video_chunks(7200)
    _assert(len(chunks) == server.LONG_VIDEO_MAX_CHUNKS,
            f"2-hour source should use max chunk count: {chunks}")
    processed = sum(c["duration_seconds"] for c in chunks)
    _assert(processed == server.LONG_VIDEO_CHUNK_BUDGET_SECONDS,
            f"chunked work must be bounded to the budget: {processed}")
    _assert(chunks[0]["start_seconds"] == 0, "chunk plan includes opening")
    _assert(chunks[-1]["end_seconds"] == 7200, "chunk plan includes ending")
    _assert(processed < 7200, "chunked mode meaningfully reduces media work")
    print(f"ok  chunk plan: 7200s source -> {len(chunks)} sections / "
          f"{processed}s media work")


def test_chunked_extraction_path(tmp: Path):
    calls = []
    saved = {name: getattr(server, name) for name in (
        "_run_subprocess", "_download_thumbnail", "_fetch_channel_context",
        "_should_start_hook_type", "_read_settings", "_incremental_index_update",
        "_index_yoink", "_start_entity_extraction_thread",
        "_start_comments_thread",
    )}

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if cmd[0] == "ffmpeg":
            output = Path(cmd[-1].replace("%04d", "0001"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"jpeg")
        elif "--download-sections" in cmd:
            count = cmd.count("--download-sections")
            for i in range(1, count + 1):
                (tmp / f"video-chunk-{i:03d}.mp4").write_bytes(b"media")
        elif "--skip-download" in cmd:
            (tmp / "video.en.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nhello\n",
                encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    phases = []
    try:
        server._run_subprocess = fake_run
        server._download_thumbnail = lambda *_a, **_k: None
        server._fetch_channel_context = lambda *_a, **_k: {}
        server._should_start_hook_type = lambda *_a, **_k: False
        server._read_settings = lambda: {}
        server._incremental_index_update = lambda *_a, **_k: None
        server._index_yoink = lambda *_a, **_k: None
        server._start_entity_extraction_thread = lambda *_a, **_k: None
        server._start_comments_thread = lambda *_a, **_k: None
        result = server._run_extraction(
            "https://www.youtube.com/watch?v=abcdef",
            30,
            tmp,
            open_explorer=False,
            metadata={
                "id": "abcdef",
                "title": "Long source",
                "duration": 7200,
                "channel": "Example",
            },
            topic="Test",
            generate_paste=False,
            long_video_mode="chunked",
            phase_callback=phases.append,
        )
    finally:
        for name, value in saved.items():
            setattr(server, name, value)

    media_calls = [c for c in calls if "--download-sections" in c]
    subtitle_calls = [c for c in calls if "--skip-download" in c]
    ffmpeg_calls = [c for c in calls if c and c[0] == "ffmpeg"]
    _assert(len(media_calls) == 1, f"one sectioned media call: {media_calls}")
    _assert(media_calls[0].count("--download-sections")
            == server.LONG_VIDEO_MAX_CHUNKS, "all chunk sections requested")
    _assert("--max-filesize" not in media_calls[0],
            "chunked mode must not be rejected by the full-source size cap")
    _assert(len(subtitle_calls) == 1, "full subtitle request is separate")
    _assert(len(ffmpeg_calls) == server.LONG_VIDEO_MAX_CHUNKS,
            "ffmpeg work is partitioned per downloaded section")
    _assert(result["long_video_mode"] == "chunked", f"mode exposed: {result}")
    _assert(result["processed_media_seconds"]
            == server.LONG_VIDEO_CHUNK_BUDGET_SECONDS, "bounded work exposed")
    _assert(any(p.startswith("screenshots_chunk_") for p in phases),
            f"chunk screenshot phase exposed: {phases}")

    sidecar = json.loads((tmp / f"{tmp.name}.json").read_text(encoding="utf-8"))
    _assert(sidecar["long_video_mode"] == "chunked", "sidecar retains mode")
    _assert(len(sidecar["long_video_chunks"]) == server.LONG_VIDEO_MAX_CHUNKS,
            "sidecar retains chunk plan")
    times = [s["timestamp"] for s in sidecar["screenshots"]]
    _assert(times[0] == "00:00:00" and times[-1] == "01:50:00",
            f"chunk timestamps retain source positions: {times}")
    print("ok  chunked extraction path: sections + subtitles + partitioned "
          "screenshots + source timestamps + sidecar/result")


def test_phase_error_and_activity_record():
    err = server.ExtractionPhaseError(
        "download", "Download timed out while fetching this long video.")
    _assert(server.friendly_error(err) == str(err),
            "phase-level actionable message must not be flattened")
    saved_persist = server._persist_jobs_locked
    try:
        server._persist_jobs_locked = lambda *_a, **_k: None
        server._jobs.clear()
        job = server._record_single_extract_job(
            "https://youtu.be/abcdef",
            server._now_iso(),
            error=server.friendly_error(err),
            error_detail=server.machine_error_detail(err),
            failure_phase=server._failure_phase(err),
            long_video_mode="chunked",
        )
        with tempfile.TemporaryDirectory() as d:
            success = server._record_single_extract_job(
                "https://youtu.be/abcdef",
                server._now_iso(),
                result={
                    "folder": d,
                    "title": "Long source",
                    "requested_long_video_mode": "chunked",
                    "long_video_mode": "chunked",
                    "long_video_chunks": [{"index": 1}],
                    "processed_media_seconds": 600,
                    "source_duration_seconds": 7200,
                },
            )
    finally:
        server._persist_jobs_locked = saved_persist
        server._jobs.clear()
    _assert(job["current_video_phase"] == "download",
            f"Activity retains failed phase: {job}")
    _assert(job["long_video_mode"] == "chunked",
            f"Activity failed job retains requested mode: {job}")
    _assert(success["result"]["long_video_mode"] == "chunked"
            and success["result"]["processed_media_seconds"] == 600,
            f"Activity success job retains chunk mode/work: {success}")
    _assert(success["long_video_mode"] == "chunked"
            and success["processed_media_seconds"] == 600,
            f"Activity exposes chunk mode/work at job level: {success}")
    print("ok  Activity job: failure phase retained + chunk mode/work exposed")


def test_extract_route_carries_chunked_mode(tmp: Path):
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
            "ok": True,
            "folder": str(folder),
            "title": "Long source",
            "screenshot_count": 0,
            "requested_long_video_mode": kwargs["long_video_mode"],
            "long_video_mode": kwargs["long_video_mode"],
            "long_video_chunks": [],
            "processed_media_seconds": 0,
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
            "long_video_mode": "chunked",
        })
        status, payload = handler.response
        bad_handler = FakeHandler()
        bad_handler._handle_extract({
            "url": "https://www.youtube.com/watch?v=abcdef",
            "long_video_mode": "not-real",
        })
        bad_status, bad_payload = bad_handler.response
    finally:
        for name, value in saved.items():
            setattr(server, name, value)

    _assert(status == 200 and payload["long_video_mode"] == "chunked",
            f"/extract exposes selected mode: {status}, {payload}")
    _assert(captured["long_video_mode"] == "chunked",
            "/extract passes selected mode into extraction")
    _assert(bad_status == 400 and "long_video_mode" in bad_payload["error"],
            f"/extract rejects invalid mode: {bad_status}, {bad_payload}")
    print("ok  /extract: validates, passes, and exposes long_video_mode=chunked")


def test_screenshot_phase_end_to_end(tmp: Path):
    if not shutil.which("ffmpeg"):
        print("skip end-to-end: ffmpeg not on PATH")
        return
    video = tmp / "video.mp4"
    # A real 2-hour video. testsrc at 1fps is trivial to encode (~sub-second).
    gen = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "testsrc=size=192x108:rate=1:duration=7200",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
         str(video)],
        capture_output=True, text=True)
    _assert(gen.returncode == 0 and video.exists(),
            f"failed to synthesize 2-hour video: {gen.stderr[-400:]}")

    duration = 7200.0
    interval = _capped_interval(duration, 30)
    shots_dir = tmp / "screenshots"
    shots_dir.mkdir()

    # Exactly the command + wrapper _run_extraction uses for the screenshot
    # phase, including the duration-scaled timeout.
    started = time.monotonic()
    server._run_subprocess(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(video),
         "-vf", f"fps=1/{interval}", "-q:v", "2",
         str(shots_dir / "shot_%04d.jpg")],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=server._ffmpeg_timeout_for(duration),
    )
    elapsed = time.monotonic() - started
    shots = sorted(shots_dir.glob("shot_*.jpg"))
    _assert(len(shots) > 0, "no screenshots produced from the 2-hour video")
    _assert(len(shots) <= server.MAX_SCREENSHOTS,
            f"{len(shots)} shots exceeds the {server.MAX_SCREENSHOTS} cap")
    _assert(elapsed < server._ffmpeg_timeout_for(duration),
            "screenshot phase blew its timeout budget")
    print(f"ok  end-to-end: 2-hour (7200s) video -> {len(shots)} screenshots "
          f"@ {interval}s interval in {elapsed:.1f}s "
          f"(budget {server._ffmpeg_timeout_for(duration)}s)")


def main():
    test_timeout_scaling()
    test_interval_cap_invariant()
    test_chunk_plan()
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        chunked = base / "chunked"
        chunked.mkdir()
        test_chunked_extraction_path(chunked)
        full = base / "full"
        full.mkdir()
        test_screenshot_phase_end_to_end(full)
        route = base / "route"
        route.mkdir()
        test_extract_route_carries_chunked_mode(route)
    test_phase_error_and_activity_record()
    print("\nALL LONG-VIDEO TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

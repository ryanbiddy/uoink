"""Empirical long-video test for Fix 2 (2-hour video failure).

Run: python tests/test_long_video_v324.py

The shipped 2-hour failure was a DOWNLOAD-phase problem (a flat 30-minute
yt-dlp timeout + a misleading "raise the screenshot interval" error). We
can't pull a real 2-hour YouTube video in CI (no yt-dlp, no network), so this
test covers the two things that ARE reproducible offline:

  1. The new duration-scaled timeout budgets (_ytdlp_timeout_for /
     _ffmpeg_timeout_for) -- the actual root-cause fix.
  2. A genuine end-to-end run of the SCREENSHOT phase on a synthesized
     2-hour video, using the helper's real subprocess wrapper and the exact
     ffmpeg command _run_extraction builds, proving the screenshot/interval-
     cap path turns a 7200s source into <=MAX_SCREENSHOTS frames quickly.

ffmpeg is required (it's a core helper dependency); the end-to-end portion
skips with a clear message if ffmpeg is missing.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
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
    with tempfile.TemporaryDirectory() as d:
        test_screenshot_phase_end_to_end(Path(d))
    print("\nALL LONG-VIDEO TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

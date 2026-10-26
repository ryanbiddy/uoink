"""Regression tests for screenshot extraction range and short-clip handling.

Run:
    python -m pytest tests/test_screenshot_extraction_cm10.py

The real-media case uses a 15-second, limited-range YUV fixture. It skips only
when ffmpeg is unavailable; the command-shape and interval tests always run.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import server


def test_short_clip_interval_targets_about_eight_frames() -> None:
    assert server._screenshot_interval_for(15, 30) == 2
    assert server._screenshot_interval_for(22, 30) == 3
    assert server._screenshot_interval_for(15, 1) == 1
    assert server._screenshot_interval_for(0, 30) == 30
    assert server._screenshot_interval_for(7200, 30) == 30


def test_screenshot_command_forces_full_range_jpeg(tmp_path: Path) -> None:
    command = server._screenshot_ffmpeg_command(
        tmp_path / "video.mkv",
        2,
        tmp_path / "shot_%04d.jpg",
    )

    assert command[:4] == ["ffmpeg", "-loglevel", "error", "-y"]
    assert command[command.index("-vf") + 1] == "fps=1/2:round=up"
    assert command[command.index("-pix_fmt") + 1] == "yuvj420p"
    assert command[-1] == str(tmp_path / "shot_%04d.jpg")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_limited_range_15_second_fixture_produces_eight_jpegs(
        tmp_path: Path) -> None:
    video = tmp_path / "limited-range.mkv"
    generated = subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "lavfi",
            "-i", "testsrc2=size=320x180:rate=8:duration=15",
            "-vf", "scale=out_range=limited,format=yuv420p",
            "-color_range", "tv",
            "-c:v", "ffv1",
            str(video),
        ],
        capture_output=True,
        text=True,
    )
    assert generated.returncode == 0, generated.stderr[-1000:]
    assert video.exists()

    interval = server._screenshot_interval_for(15, 30)
    command = server._screenshot_ffmpeg_command(
        video,
        interval,
        tmp_path / "shot_%04d.jpg",
    )
    extracted = subprocess.run(command, capture_output=True, text=True)

    assert extracted.returncode == 0, extracted.stderr[-1000:]
    assert len(list(tmp_path.glob("shot_*.jpg"))) == 8


def _frame_md5s(command: list[str]) -> list[str]:
    """Run a screenshot command with framemd5 output instead of JPEG files."""
    framemd5 = command[:-1] + ["-f", "framemd5", "-"]
    framemd5.remove("-q:v")
    framemd5.remove("2")
    out = subprocess.run(framemd5, capture_output=True, text=True, check=True).stdout
    return [line.rsplit(",", 1)[1].strip() for line in out.splitlines()
            if line and not line.startswith("#")]


def _source_frame_md5(video: Path, frame: int) -> str:
    out = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(video),
         "-vf", f"select=eq(n\,{frame})", "-frames:v", "1",
         "-pix_fmt", "yuvj420p", "-f", "framemd5", "-"],
        capture_output=True, text=True, check=True).stdout
    return [line.rsplit(",", 1)[1].strip() for line in out.splitlines()
            if line and not line.startswith("#")][0]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_shots_are_taken_at_their_labeled_times(tmp_path: Path) -> None:
    video = tmp_path / "timed.mkv"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "testsrc2=size=160x90:rate=10:duration=65",
         "-c:v", "ffv1", str(video)],
        check=True, capture_output=True)

    shots = _frame_md5s(server._screenshot_ffmpeg_command(
        video, 30, tmp_path / "shot_%04d.jpg"))

    # Labels are 0, 30 and 60 seconds; at 10 fps those are frames 0, 300, 600.
    assert shots == [_source_frame_md5(video, n) for n in (0, 300, 600)]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_clip_shorter_than_half_the_interval_still_gets_a_shot(
        tmp_path: Path) -> None:
    # X syndication metadata can omit the duration, so the interval stays at
    # 30 s for an 8 s clip. A re-capture then failed with "Screenshot
    # generation produced no images."
    video = tmp_path / "short.mkv"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "testsrc2=size=160x90:rate=25:duration=8.6",
         "-c:v", "ffv1", str(video)],
        check=True, capture_output=True)

    command = server._screenshot_ffmpeg_command(
        video, 30, tmp_path / "shot_%04d.jpg")
    subprocess.run(command, check=True, capture_output=True)

    assert len(list(tmp_path.glob("shot_*.jpg"))) == 1

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
    assert command[command.index("-vf") + 1] == "fps=1/2"
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

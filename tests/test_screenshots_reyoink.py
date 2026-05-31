"""Empirical tests for the D-20 screenshot picker + re-yoink helpers.

Run: python tests/test_screenshots_reyoink.py
Exercises server._image_dimensions, server._screenshot_list_for_yoink, and
server._reyoink_source against real on-disk fixtures (hand-built minimal
JPEG/PNG byte streams, a sidecar.json, and a fake Index). No network, no
helper process.
"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


def _minimal_png(path: Path, width: int, height: int) -> None:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_body = struct.pack(">II", width, height) + bytes([8, 2, 0, 0, 0])
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_body + b"\x00\x00\x00\x00"
    iend = struct.pack(">I", 0) + b"IEND" + b"\xae\x42\x60\x82"
    path.write_bytes(sig + ihdr + iend)


def _minimal_jpeg(path: Path, width: int, height: int) -> None:
    soi = b"\xff\xd8"
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0_body = bytes([8]) + struct.pack(">HH", height, width) + bytes([1, 1, 0x11, 0])
    sof0 = b"\xff\xc0" + struct.pack(">H", len(sof0_body) + 2) + sof0_body
    eoi = b"\xff\xd9"
    path.write_bytes(soi + app0 + sof0 + eoi)


class FakeIndex:
    def __init__(self, rows: dict[str, dict]):
        self._rows = rows

    def get_yoink(self, video_id: str):
        return self._rows.get(video_id)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_image_dimensions(tmp: Path) -> None:
    png = tmp / "a.png"
    _minimal_png(png, 1280, 720)
    _assert(server._image_dimensions(png) == (1280, 720), "PNG dims wrong")

    jpg = tmp / "b.jpg"
    _minimal_jpeg(jpg, 1920, 1080)
    _assert(server._image_dimensions(jpg) == (1920, 1080), "JPEG dims wrong")

    junk = tmp / "c.bin"
    junk.write_bytes(b"not an image")
    _assert(server._image_dimensions(junk) == (None, None), "junk should be (None, None)")

    missing = tmp / "nope.jpg"
    _assert(server._image_dimensions(missing) == (None, None), "missing file should be (None, None)")
    print("ok  _image_dimensions: PNG, JPEG, junk, missing")


def test_screenshot_list_happy(tmp: Path) -> None:
    folder = tmp / "AI-and-ML" / "demo-video"
    shots = folder / "screenshots"
    shots.mkdir(parents=True)
    _minimal_jpeg(shots / "shot_0001.jpg", 1280, 720)
    _minimal_jpeg(shots / "shot_0002.jpg", 1280, 720)
    # A third on disk that the sidecar does NOT list (re-yoink drift backstop).
    _minimal_jpeg(shots / "shot_0003.jpg", 640, 360)

    corpus = folder / "demo-video.md"
    corpus.write_text("# demo", encoding="utf-8")
    sidecar = folder / "demo-video.sidecar.json"
    sidecar.write_text(json.dumps({
        "url": "https://www.youtube.com/watch?v=abc123",
        "interval_seconds": 30,
        "title": "Demo Video",
        "screenshots": [
            {"timestamp": "0:00", "path": "screenshots/shot_0001.jpg", "filename": "shot_0001.jpg"},
            {"timestamp": "0:30", "path": "screenshots/shot_0002.jpg", "filename": "shot_0002.jpg"},
            # references a file that no longer exists -> must be skipped
            {"timestamp": "1:00", "path": "screenshots/shot_9999.jpg", "filename": "shot_9999.jpg"},
        ],
    }), encoding="utf-8")

    idx = FakeIndex({"vid1": {
        "video_id": "vid1", "title": "Demo Video",
        "corpus_path": str(corpus), "sidecar_path": str(sidecar),
    }})

    payload = server._screenshot_list_for_yoink(idx, "vid1")
    _assert(payload is not None, "payload should not be None")
    # 2 listed-and-present + 1 disk-only backstop = 3; the missing-ref is skipped.
    _assert(payload["count"] == 3, f"expected 3 screenshots, got {payload['count']}")
    names = [s["filename"] for s in payload["screenshots"]]
    _assert(names == ["shot_0001.jpg", "shot_0002.jpg", "shot_0003.jpg"], f"order/names wrong: {names}")
    first = payload["screenshots"][0]
    _assert(first["timestamp"] == "0:00", "sidecar timestamp not passed through")
    _assert(first["timestamp_seconds"] == 0, "ts_seconds[0] should be 0")
    _assert(payload["screenshots"][1]["timestamp_seconds"] == 30, "ts_seconds[1] should be 30")
    _assert(first["width"] == 1280 and first["height"] == 720, "dims not populated")
    _assert(first["file_url"].startswith("/file?path="), "file_url shape wrong")
    _assert(first["path"].endswith("shot_0001.jpg"), "absolute path wrong")
    # disk-only backstop entry derived its timestamp from the shot number
    backstop = payload["screenshots"][2]
    _assert(backstop["timestamp_seconds"] == 60, f"backstop ts wrong: {backstop['timestamp_seconds']}")
    _assert(backstop["width"] == 640, "backstop dims wrong")
    print("ok  _screenshot_list_for_yoink: sidecar + missing-skip + disk backstop")


def test_screenshot_list_edge(tmp: Path) -> None:
    # Unknown id -> None
    idx = FakeIndex({})
    _assert(server._screenshot_list_for_yoink(idx, "missing") is None, "unknown id should be None")

    # Text-only capture (no screenshots dir) -> empty list, not None
    folder = tmp / "text" / "article"
    folder.mkdir(parents=True)
    corpus = folder / "article.md"
    corpus.write_text("# text", encoding="utf-8")
    sidecar = folder / "article.sidecar.json"
    sidecar.write_text(json.dumps({"url": "https://example.com/x", "screenshots": []}), encoding="utf-8")
    idx2 = FakeIndex({"t1": {
        "video_id": "t1", "title": "Article",
        "corpus_path": str(corpus), "sidecar_path": str(sidecar),
    }})
    payload = server._screenshot_list_for_yoink(idx2, "t1")
    _assert(payload is not None and payload["count"] == 0, "text capture should be empty list")
    print("ok  _screenshot_list_for_yoink: unknown id None, text-only empty")


def test_reyoink_source(tmp: Path) -> None:
    folder = tmp / "v" / "clip"
    (folder).mkdir(parents=True)
    corpus = folder / "clip.md"
    corpus.write_text("x", encoding="utf-8")
    sidecar = folder / "clip.sidecar.json"
    sidecar.write_text(json.dumps({"url": "https://youtu.be/zzz", "interval_seconds": 45}), encoding="utf-8")
    idx = FakeIndex({
        "v1": {"video_id": "v1", "corpus_path": str(corpus), "sidecar_path": str(sidecar)},
        # no-url case
        "v2": {"video_id": "v2", "corpus_path": str(corpus), "sidecar_path": str(tmp / "missing.json")},
    })
    _assert(server._reyoink_source(idx, "missing") is None, "unknown id should be None")
    url, interval = server._reyoink_source(idx, "v1")
    _assert(url == "https://youtu.be/zzz" and interval == 45, f"reyoink source wrong: {url}, {interval}")
    url2, interval2 = server._reyoink_source(idx, "v2")
    _assert(url2 == "" and interval2 is None, "no-sidecar should be ('', None)")
    print("ok  _reyoink_source: url+interval, unknown None, no-sidecar empty")


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        for name, fn in [
            ("dims", test_image_dimensions),
            ("happy", test_screenshot_list_happy),
            ("edge", test_screenshot_list_edge),
            ("reyoink", test_reyoink_source),
        ]:
            sub = base / name
            sub.mkdir()
            fn(sub)
    print("\nALL SCREENSHOT + RE-YOINK TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

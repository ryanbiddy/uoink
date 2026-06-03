"""Empirical tests for the v3.2.4 screenshot picker additions:
visual-diff dedup, auto-suggest (tweet/thread/blog), and even-distribution.

Run: python tests/test_screenshots_picker_v324.py
Builds real on-disk JPEGs (via Pillow when present) and exercises
server._dedupe_screenshot_entries / _suggest_screenshots / _even_indices /
_ahash_file. No server boot, no network.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _has_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


_W, _H = 64, 48


def _hgrad_jpeg(path: Path, offset: int) -> None:
    """Horizontal gradient (varies along x). `offset` nudges it a hair so
    consecutive frames are near-duplicates, not byte-identical -- like a
    near-static talking-head shot."""
    from PIL import Image
    data = bytes(((x * 4 + offset) % 256) for _y in range(_H) for x in range(_W))
    Image.frombytes("L", (_W, _H), data).save(path, "JPEG")


def _vgrad_jpeg(path: Path) -> None:
    """Vertical gradient (varies along y) -- visually/structurally distinct
    from the horizontal gradient, so its average-hash is far away."""
    from PIL import Image
    data = bytes(((y * 5) % 256) for y in range(_H) for _x in range(_W))
    Image.frombytes("L", (_W, _H), data).save(path, "JPEG")


def _entry(path: Path, index: int):
    return {"index": index, "filename": path.name, "path": str(path),
            "timestamp_seconds": index * 30}


def test_even_indices():
    _assert(server._even_indices(0, 5) == [], "empty range")
    _assert(server._even_indices(10, 1) == [5], "single -> middle")
    _assert(server._even_indices(3, 8) == [0, 1, 2], "count>=n clamps to all")
    out = server._even_indices(100, 5)
    _assert(out[0] == 0 and out[-1] == 99, f"endpoints included: {out}")
    _assert(len(out) == 5 and out == sorted(set(out)), f"unique+sorted: {out}")
    print("ok  _even_indices: empty / single / clamp / endpoints")


def test_suggest_modes():
    payload = {"screenshots": [{"index": i} for i in range(50)]}
    tweet = server._suggest_screenshots(payload, mode="tweet")
    _assert(tweet["count"] == 1, "tweet picks exactly one")
    _assert(tweet["indices"][0] >= 1, "tweet skips the cold-open frame 0")
    _assert(tweet["strategy"] == "hook_zone_heuristic", "tweet strategy label")

    thread = server._suggest_screenshots(payload, mode="thread", thread_size=6)
    _assert(thread["count"] == 6, f"thread honors size: {thread}")
    _assert(thread["indices"] == sorted(set(thread["indices"])), "thread sorted/unique")

    # thread_size clamps into 3..8
    _assert(server._suggest_screenshots(payload, mode="thread",
            thread_size=99)["count"] == 8, "thread clamps high to 8")
    _assert(server._suggest_screenshots(payload, mode="thread",
            thread_size=1)["count"] == 3, "thread clamps low to 3")

    blog = server._suggest_screenshots(payload, mode="blog")
    _assert(3 <= blog["count"] <= 5, f"blog 3-5: {blog['count']}")
    _assert(blog["indices"][0] == 0 and blog["indices"][-1] == 49,
            "blog covers start..end")
    print("ok  _suggest_screenshots: tweet/thread/blog + clamps")


def test_suggest_edges():
    # empty
    empty = server._suggest_screenshots({"screenshots": []}, mode="tweet")
    _assert(empty["count"] == 0 and empty["strategy"] == "empty", "empty handled")
    # single frame
    one = server._suggest_screenshots({"screenshots": [{"index": 0}]}, mode="tweet")
    _assert(one["indices"] == [0], "single-frame tweet picks frame 0")
    # bad mode
    try:
        server._suggest_screenshots({"screenshots": [{}]}, mode="bogus")
    except ValueError:
        print("ok  _suggest_screenshots: empty / single / bad-mode raises")
        return
    raise AssertionError("bad mode should raise ValueError")


def test_dedupe_query_contract():
    enabled, threshold = server._screenshot_dedupe_query({
        "dedupe": ["true"], "dedupe_threshold": ["99"]})
    _assert(enabled is True and threshold == 32,
            f"dedupe query enables + clamps: {enabled}, {threshold}")
    enabled, threshold = server._screenshot_dedupe_query({
        "dedupe": ["no"], "dedupe_threshold": ["bad"]})
    _assert(enabled is False and threshold == 5,
            f"dedupe query defaults invalid threshold: {enabled}, {threshold}")
    print("ok  dedupe query: shared enable/default/clamp contract")


def test_dedupe(tmp: Path):
    if not _has_pillow():
        # Documented fallback: without Pillow nothing is hashable, so dedupe
        # returns everything and flags availability=False (never silently
        # drops frames it couldn't compare).
        entries = [_entry(tmp / f"x{i}.jpg", i) for i in range(3)]
        for e in entries:
            Path(e["path"]).write_bytes(b"not-an-image")
        kept, removed, available = server._dedupe_screenshot_entries(entries)
        _assert(len(kept) == 3 and removed == 0 and available is False,
                "no-Pillow fallback keeps all, flags unavailable")
        print("ok  _dedupe (no Pillow): keeps all, dedupe_available=False")
        return

    # 4 near-identical frames (same gradient, 1-level nudges), then 1 clearly
    # different frame (gradient along the other axis).
    paths = []
    for i in range(4):
        p = tmp / f"near_{i}.jpg"
        _hgrad_jpeg(p, i)  # near-duplicate
        paths.append(_entry(p, i))
    distinct = tmp / "distinct.jpg"
    _vgrad_jpeg(distinct)
    paths.append(_entry(distinct, 4))

    kept, removed, available = server._dedupe_screenshot_entries(paths, threshold=5)
    _assert(available is True, "Pillow present -> dedupe available")
    _assert(removed >= 1, f"near-duplicate frames should be collapsed: removed={removed}")
    names = [k["filename"] for k in kept]
    _assert("distinct.jpg" in names, "the distinct frame must survive")
    _assert("near_0.jpg" in names, "first frame is always kept as the anchor")
    print(f"ok  _dedupe (Pillow): {len(paths)} -> {len(kept)} kept, {removed} removed")


def test_ahash(tmp: Path):
    if not _has_pillow():
        print("skip _ahash_file: Pillow not installed in this env")
        return
    a = tmp / "a.jpg"
    b = tmp / "b.jpg"
    _hgrad_jpeg(a, 0)
    _vgrad_jpeg(b)
    ha, hb = server._ahash_file(a), server._ahash_file(b)
    _assert(ha is not None and hb is not None, "hashes computed")
    # identical solid image hashes to itself with distance 0
    _assert(server._hamming(ha, server._ahash_file(a)) == 0, "stable hash")
    _assert(server._ahash_file(tmp / "missing.jpg") is None, "missing -> None")
    print("ok  _ahash_file: computes, stable, missing -> None")


def main():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        test_even_indices()
        test_suggest_modes()
        test_suggest_edges()
        test_dedupe_query_contract()
        sub1 = base / "dedupe"; sub1.mkdir()
        test_dedupe(sub1)
        sub2 = base / "ahash"; sub2.mkdir()
        test_ahash(sub2)
    print("\nALL SCREENSHOT PICKER v3.2.4 TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

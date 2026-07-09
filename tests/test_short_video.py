"""Short-form video capture -- TikTok, Instagram Reels, YouTube Shorts.

Context-layer build sequence item 2: a TikTok / Reel / Short becomes a
first-class uoink in the same corpus (platform / source_type / author /
topic), queryable by AI + you.

Run: python tests/test_short_video.py   (also collected by pytest)

Red before the change:
  - _classify_capture_url routes a TikTok / Reel / Short to web_page or
    youtube_video, not a first-class "short_video" source;
  - _normalize_video_url rejects TikTok / Instagram, so /extract 400s;
  - _detect_platform_from_url returns "generic" for TikTok / Instagram;
  - page_extractor.platform_for / author_for don't know the new platforms;
  - a captured short lands with no source_type='short_video' facet.

Live TikTok / Instagram rate-limit and login-wall, so extraction here is
driven with a MOCKED yt-dlp + ffmpeg (server._run_subprocess) and canned
metadata. No network. The classifier + taxonomy assertions are pure.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import types
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import page_extractor as pe  # noqa: E402
import server  # noqa: E402

PORT = 5197


def _assert(cond, msg="assertion failed"):
    if not cond:
        raise AssertionError(msg)


def _fresh_index():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    return tmp, idx


# ---- classifier + normalizers (pure) --------------------------------------
def test_classifier_routes_short_video_sources():
    cases = {
        "https://www.tiktok.com/@creator/video/7300000000000000000?is_copy_url=1":
            ("short_video", "/extract",
             "https://www.tiktok.com/@creator/video/7300000000000000000"),
        "https://vm.tiktok.com/ZMabc123/":
            ("short_video", "/extract", "https://vm.tiktok.com/ZMabc123"),
        "https://www.instagram.com/reel/CxYzAbC123/?igsh=x":
            ("short_video", "/extract",
             "https://www.instagram.com/reel/CxYzAbC123/"),
        "https://instagram.com/creator/reel/CxYzAbC123/":
            ("short_video", "/extract",
             "https://www.instagram.com/reel/CxYzAbC123/"),
        "https://www.instagram.com/p/CxYzAbC123/":
            ("short_video", "/extract",
             "https://www.instagram.com/p/CxYzAbC123/"),
        "https://www.youtube.com/shorts/dQw4w9WgXcQ":
            ("short_video", "/extract",
             "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    }
    for url, (source, endpoint, canonical) in cases.items():
        r = server._classify_capture_url(url)
        _assert(r["ok"] is True, f"{url} should be supported: {r}")
        _assert(r["source"] == source, f"{url} -> {r['source']} != {source}")
        _assert(r["endpoint"] == endpoint,
                f"{url} endpoint {r['endpoint']} != {endpoint}")
        _assert(r["canonical"] == canonical,
                f"{url} canonical {r['canonical']} != {canonical}")
    print("ok  TikTok / Reel / Short route to the short_video source (/extract)")


def test_regular_youtube_video_is_not_a_short():
    r = server._classify_capture_url(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    _assert(r["source"] == "youtube_video",
            f"a normal watch URL must stay youtube_video: {r}")
    # youtu.be carries no /shorts/ signal, so it is a regular video, not a short.
    r2 = server._classify_capture_url("https://youtu.be/dQw4w9WgXcQ")
    _assert(r2["source"] == "youtube_video",
            f"youtu.be must stay youtube_video (no short signal): {r2}")
    print("ok  regular YouTube videos are never mislabeled as shorts")


def test_normalize_video_url_accepts_short_sources():
    tt, p1 = server._normalize_video_url(
        "https://www.tiktok.com/@c/video/7300000000000000000")
    _assert(tt and p1 == server.PLATFORM_TIKTOK, f"tiktok: {tt} {p1}")
    ig, p2 = server._normalize_video_url(
        "https://www.instagram.com/reel/ABC123/")
    _assert(ig and p2 == server.PLATFORM_INSTAGRAM, f"ig: {ig} {p2}")
    yt, p3 = server._normalize_video_url(
        "https://www.youtube.com/shorts/dQw4w9WgXcQ")
    _assert(yt == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            and p3 == server.PLATFORM_YOUTUBE, f"short: {yt} {p3}")
    # _validate_url_interval must flag the short-form ones so the pipeline
    # tags source_type='short_video'.
    _assert(server._is_short_video_url(
        "https://www.tiktok.com/@c/video/7300000000000000000"))
    _assert(server._is_short_video_url("https://www.youtube.com/shorts/abcdef"))
    _assert(not server._is_short_video_url(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
    print("ok  _normalize_video_url + _is_short_video_url handle short sources")


def test_detect_platform_and_taxonomy_helpers():
    _assert(server._detect_platform_from_url(
        "https://www.tiktok.com/@c/video/7") == server.PLATFORM_TIKTOK)
    _assert(server._detect_platform_from_url(
        "https://www.instagram.com/reel/ABC/") == server.PLATFORM_INSTAGRAM)
    # page_extractor is the single taxonomy brain the index reads.
    _assert(pe.platform_for("short_video",
            "https://www.tiktok.com/@c/video/7") == "tiktok")
    _assert(pe.platform_for("short_video",
            "https://www.instagram.com/reel/ABC/") == "instagram")
    _assert(pe.platform_for("short_video",
            "https://www.youtube.com/watch?v=abc") == "youtube")
    # author for a short comes from the uploader/channel (like YouTube), NOT
    # the hostname -- author_for returns None so the caller uses sidecar.channel.
    md = {"uploader": "creatorname"}
    _assert(pe.author_for("short_video", md,
            "https://www.tiktok.com/@c/video/7") is None,
            "short author must defer to the channel, not the host")
    print("ok  platform/author taxonomy resolves TikTok + Instagram + Shorts")


# ---- mocked extraction persists the short + surfaces it --------------------
def _fake_run_subprocess(cmd, **kwargs):
    """Stand in for yt-dlp (media + subs) and ffmpeg (screenshots) so the
    extraction pipeline runs with no network + no binaries. yt-dlp writes a
    video file + an English SRT; ffmpeg writes one screenshot jpg."""
    parts = [str(c) for c in cmd]
    is_ffmpeg = parts and parts[0].endswith("ffmpeg")
    # Locate the -o output template both tools use.
    out = None
    if "-o" in parts:
        out = parts[parts.index("-o") + 1]
    elif is_ffmpeg:
        out = parts[-1]
    if is_ffmpeg and out:
        # Screenshot template: .../screenshots/shot_%04d.jpg
        shot = Path(out.replace("%04d", "0001"))
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"\xff\xd8\xff\xe0jpg")
    elif out:
        # yt-dlp media: write video.mp4 + video.en.srt next to the template.
        base_dir = Path(out).parent
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp4")
        (base_dir / "video.en.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nhello from a short\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\nabout ai agents\n",
            encoding="utf-8")
    return types.SimpleNamespace(returncode=0, stdout="", stderr=b"")


def test_mocked_extraction_persists_and_surfaces(monkeypatch):
    tmp, idx = _fresh_index()
    root = Path(tmp.name) / "corpus"
    root.mkdir(parents=True)
    try:
        monkeypatch.setattr(server, "DESKTOP_ROOT", root)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "_run_subprocess", _fake_run_subprocess)
        monkeypatch.setattr(server, "_download_thumbnail",
                            lambda *a, **k: None)
        monkeypatch.setattr(server, "_fetch_channel_context", lambda *a, **k: {})
        monkeypatch.setattr(server, "_start_comments_thread",
                            lambda *a, **k: None)
        monkeypatch.setattr(server, "_start_entity_extraction_thread",
                            lambda *a, **k: None)
        monkeypatch.setattr(server, "_read_settings", lambda: {})

        metadata = {
            "id": "tiktok_7300000000000000000",
            "title": "Building AI agents in 30 seconds",
            "description": "a quick ai agents demo #ai",
            "uploader": "creatorname",
            "creator": "Creator Name",
            "duration": 22,
            "thumbnails": [],
            "webpage_url": "https://www.tiktok.com/@creatorname/video/7300000000000000000",
        }
        url = "https://www.tiktok.com/@creatorname/video/7300000000000000000"
        folder = root / "AI" / "building-ai-agents"
        expected_topic = server._classify_topic(metadata)

        result = server._run_extraction(
            url, 30, folder, open_explorer=False, metadata=metadata,
            source_type=server.SOURCE_TYPE_SHORT_VIDEO, generate_paste=False)
        _assert(result["ok"] is True, f"extraction failed: {result}")

        # Corpus + sidecar landed on disk under the output root (not AppData).
        sidecar_path = folder / f"{folder.name}.json"
        _assert(sidecar_path.exists(), "sidecar not written under output root")
        sc = json.loads(sidecar_path.read_text(encoding="utf-8"))
        _assert(sc["platform"] == "tiktok", f"sidecar platform: {sc['platform']}")
        _assert(sc["source_type"] == "short_video",
                f"sidecar source_type: {sc.get('source_type')}")
        # Transcript captured from the SRT the mocked yt-dlp produced.
        _assert((folder / "transcript.txt").exists(), "transcript.txt missing")
        _assert(len(sc.get("transcript") or []) == 2,
                f"transcript segments: {sc.get('transcript')}")

        # Row carries the full taxonomy.
        row = idx.get_yoink("tiktok_7300000000000000000")
        _assert(row is not None, "no yoink row indexed")
        _assert(row["platform"] == "tiktok", f"row platform: {row['platform']}")
        _assert(row["source_type"] == "short_video",
                f"row source_type: {row['source_type']}")
        _assert(row["author"] == "creatorname", f"row author: {row['author']}")
        _assert(row["topic"] == expected_topic,
                f"row topic {row['topic']} != {expected_topic}")

        # Surfaces in search filters (the same query MCP + /memory/search use).
        by_platform = idx.search_yoinks_for_memory(platform="tiktok")
        _assert(by_platform["total"] == 1, f"platform=tiktok: {by_platform}")
        by_type = idx.search_yoinks_for_memory(source_type="short_video")
        _assert(by_type["total"] == 1, f"source_type=short_video: {by_type}")

        # Surfaces as a facet with a human label.
        facets = idx.corpus_facets()
        plats = {p["value"] for p in facets.get("platform", [])}
        stypes = {s["value"] for s in facets.get("source_type", [])}
        _assert("tiktok" in plats, f"platform facet missing tiktok: {plats}")
        _assert("short_video" in stypes,
                f"source_type facet missing short_video: {stypes}")
        _assert(server._humanize_facet("platform", "tiktok") == "TikTok")
        _assert(server._humanize_facet("platform", "instagram") == "Instagram")
        _assert(server._humanize_facet("source_type", "short_video")
                == "Short video")
    finally:
        idx.close()
        tmp.cleanup()
    print("ok  mocked short-video extraction persists + surfaces in "
          "search/facets with correct platform/source_type/author/topic")


# ---- honest failure over HTTP ---------------------------------------------
def _post(path, body, token=True):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def test_login_wall_fails_honestly_and_persists_nothing(monkeypatch):
    tmp, idx = _fresh_index()
    root = Path(tmp.name) / "corpus"
    root.mkdir(parents=True)
    monkeypatch.setattr(server, "DESKTOP_ROOT", root)
    monkeypatch.setattr(server, "_get_index", lambda: idx)

    def _boom(url, **kwargs):
        raise subprocess.CalledProcessError(
            1, ["yt-dlp"],
            stderr=b"ERROR: [TikTok] Unable to extract: login required")
    monkeypatch.setattr(server, "_fetch_metadata", _boom)

    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        status, res = _post(
            "/extract",
            {"url": "https://www.tiktok.com/@c/video/7300000000000000000"})
        _assert(status == 200, f"handled failure returns 200 body: {status}")
        _assert(res.get("ok") is False, f"must fail honestly: {res}")
        _assert(res.get("error"), "an actionable error message is required")
        # Nothing persisted: no row, no folder.
        _assert(idx.search_yoinks_for_memory(platform="tiktok")["total"] == 0,
                "a login-walled short must persist NO row")
        leftover = [p for p in root.rglob("*.json")]
        _assert(not leftover, f"login-walled short left files behind: {leftover}")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()
    print("ok  login-walled short fails honestly and persists nothing")


def main():
    test_classifier_routes_short_video_sources()
    test_regular_youtube_video_is_not_a_short()
    test_normalize_video_url_accepts_short_sources()
    test_detect_platform_and_taxonomy_helpers()
    # The monkeypatch-based tests are pytest-driven; run a lightweight shim
    # so `python tests/test_short_video.py` still exercises them.
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))


if __name__ == "__main__":
    main()

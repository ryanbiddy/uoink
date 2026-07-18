"""E-1 (Zing enabler): opt-in keep_media retains short-video media files.

`_run_extraction` deletes the downloaded video once screenshots + transcript
are extracted. Right for long-form sources (media can run to gigabytes), but
it starves the planned director tool (Zing), which needs the actual clip to
analyze cuts / captions / audio. The `keep_media` setting -- OPT-IN, default
OFF -- keeps the downloaded file in the uoink folder for short-video
captures ONLY and records its filename in the JSON sidecar (`media_file`)
so downstream tools can find it without globbing.

Run: python tests/test_keep_media.py   (also collected by pytest)

Red before the change:
  - `keep_media` is not a settings field (defaults / normalize / public);
  - _run_extraction deletes video.mp4 unconditionally, so keep_media ON +
    short_video leaves no media file and no sidecar `media_file` field.

Extraction is driven with a MOCKED yt-dlp + ffmpeg (server._run_subprocess),
same approach as tests/test_short_video.py. No network.
"""
from __future__ import annotations

import json
import tempfile
import types
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import server  # noqa: E402


def _assert(cond, msg="assertion failed"):
    if not cond:
        raise AssertionError(msg)


def _fake_run_subprocess(cmd, **kwargs):
    """Stand in for yt-dlp (media + subs) and ffmpeg (screenshots) so the
    extraction pipeline runs with no network + no binaries. Mirrors
    tests/test_short_video.py."""
    parts = [str(c) for c in cmd]
    is_ffmpeg = parts and parts[0].endswith("ffmpeg")
    out = None
    if "-o" in parts:
        out = parts[parts.index("-o") + 1]
    elif is_ffmpeg:
        out = parts[-1]
    if is_ffmpeg and out:
        shot = Path(out.replace("%04d", "0001"))
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"\xff\xd8\xff\xe0jpg")
    elif out:
        base_dir = Path(out).parent
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp4")
        (base_dir / "video.en.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nhello from a short\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\nabout ai agents\n",
            encoding="utf-8")
    return types.SimpleNamespace(returncode=0, stdout="", stderr=b"")


def _run_mocked_extraction(monkeypatch, *, settings: dict,
                           source_type: str | None,
                           url: str, metadata: dict):
    """Run _run_extraction with yt-dlp / ffmpeg / settings mocked.
    Returns (folder, sidecar_dict)."""
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    root = Path(tmp.name) / "corpus"
    root.mkdir(parents=True)
    try:
        monkeypatch.setattr(server, "DESKTOP_ROOT", root)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "_run_subprocess", _fake_run_subprocess)
        monkeypatch.setattr(server, "_download_thumbnail",
                            lambda *a, **k: None)
        monkeypatch.setattr(server, "_fetch_channel_context",
                            lambda *a, **k: {})
        monkeypatch.setattr(server, "_start_comments_thread",
                            lambda *a, **k: None)
        monkeypatch.setattr(server, "_start_entity_extraction_thread",
                            lambda *a, **k: None)
        monkeypatch.setattr(server, "_read_settings", lambda: dict(settings))

        folder = root / "AI" / "keep-media-case"
        result = server._run_extraction(
            url, 30, folder, open_explorer=False, metadata=metadata,
            source_type=source_type, generate_paste=False)
        _assert(result["ok"] is True, f"extraction failed: {result}")

        sidecar_path = folder / f"{folder.name}.json"
        _assert(sidecar_path.exists(), "sidecar not written")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        media_leftovers = sorted(
            p.name for p in folder.glob("video.*") if p.suffix != ".srt")
        return sidecar, media_leftovers
    finally:
        idx.close()
        tmp.cleanup()


_SHORT_URL = "https://www.tiktok.com/@creatorname/video/7300000000000000001"
_SHORT_METADATA = {
    "id": "tiktok_7300000000000000001",
    "title": "Keep media short",
    "description": "a quick ai agents demo #ai",
    "uploader": "creatorname",
    "duration": 22,
    "thumbnails": [],
    "webpage_url": _SHORT_URL,
}

_REGULAR_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
_REGULAR_METADATA = {
    "id": "dQw4w9WgXcQ",
    "title": "Keep media regular video",
    "description": "a normal long-form video",
    "channel": "somechannel",
    "duration": 212,
    "thumbnails": [],
    "webpage_url": _REGULAR_URL,
}


# ---- the settings field exists and defaults OFF ----------------------------
def test_keep_media_is_an_optin_setting():
    _assert(server._default_settings().get("keep_media") is False,
            "keep_media must exist in defaults and default OFF")
    _assert(server._normalize_settings({"keep_media": 1})["keep_media"] is True,
            "normalize must coerce keep_media to a bool")
    _assert(server._normalize_settings({})["keep_media"] is False,
            "normalize must default keep_media OFF")
    _assert(server._public_settings({}).get("keep_media") is False,
            "public settings must expose keep_media (default OFF)")
    print("ok  keep_media is a settings field, opt-in, default OFF")


# ---- (1) default OFF: byte-identical to today -------------------------------
def test_default_off_deletes_media_exactly_as_before(monkeypatch):
    sidecar, leftovers = _run_mocked_extraction(
        monkeypatch, settings={}, source_type=server.SOURCE_TYPE_SHORT_VIDEO,
        url=_SHORT_URL, metadata=_SHORT_METADATA)
    _assert(leftovers == [],
            f"default OFF must delete the downloaded media: {leftovers}")
    _assert("media_file" not in sidecar,
            "default OFF must not add media_file to the sidecar "
            "(byte-identical to before)")
    print("ok  keep_media OFF (default): media deleted, sidecar unchanged")


# ---- (2) ON + short_video: file kept + sidecar records it -------------------
def test_on_short_video_keeps_file_and_records_sidecar(monkeypatch):
    sidecar, leftovers = _run_mocked_extraction(
        monkeypatch, settings={"keep_media": True},
        source_type=server.SOURCE_TYPE_SHORT_VIDEO,
        url=_SHORT_URL, metadata=_SHORT_METADATA)
    _assert(leftovers == ["video.mp4"],
            f"keep_media ON + short_video must keep the file: {leftovers}")
    _assert(sidecar.get("media_file") == "video.mp4",
            f"sidecar must record the kept filename: "
            f"{sidecar.get('media_file')!r}")
    print("ok  keep_media ON + short_video: file kept, sidecar media_file set")


# ---- (3) ON + regular video: still deletes (scope is short_video only) ------
def test_on_regular_video_still_deletes(monkeypatch):
    sidecar, leftovers = _run_mocked_extraction(
        monkeypatch, settings={"keep_media": True}, source_type=None,
        url=_REGULAR_URL, metadata=_REGULAR_METADATA)
    _assert(leftovers == [],
            f"keep_media ON must NOT keep long-form media: {leftovers}")
    _assert("media_file" not in sidecar,
            "a regular video must not get a media_file sidecar field")
    print("ok  keep_media ON + regular video: media still deleted")


def main():
    test_keep_media_is_an_optin_setting()
    # The monkeypatch-based tests are pytest-driven; run a lightweight shim
    # so `python tests/test_keep_media.py` still exercises them.
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))


if __name__ == "__main__":
    main()

"""Import a list and mid-video card images, through the helper.

Covers the queue hand-off and library dedupe, the source tag on index, the
card-image setting, the mid-frame pick, For You's taste-ranked imports and
the import_list registry tool. A disposable Index, settings file and data
root per test; list sources come from saved fixtures, never the network.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import index as index_mod  # noqa: E402
import list_imports as li  # noqa: E402
import server  # noqa: E402
import uoink_mcp_tools  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "list_imports"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def fake_fetch(url):
    parsed = urlparse(url)
    if parsed.hostname == "hackertube.org" and parsed.path == "/api/playlist":
        return load("hackertube_playlist.json")
    if parsed.hostname == "hn.algolia.com":
        return load("hn_item_15926973.json")
    raise AssertionError(f"unexpected fetch {url}")


@pytest.fixture
def helper(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(li, "http_get_json", fake_fetch)
    (tmp_path / "data").mkdir()
    yield idx
    idx.close()


def save_video(idx, root: Path, video_id: str, *, channel="Some Channel", title="A talk",
               duration=120, shot_times=(0, 30, 60, 90), thumbnail=True):
    folder = root / "lib" / video_id
    (folder / "screenshots").mkdir(parents=True)
    shots = []
    for i, t in enumerate(shot_times, 1):
        name = f"shot_{i:04d}.jpg"
        (folder / "screenshots" / name).write_bytes(b"\xff\xd8jpg")
        shots.append({"timestamp": f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}",
                      "path": f"screenshots/{name}", "filename": name})
    if thumbnail:
        (folder / "thumbnail.jpg").write_bytes(b"\xff\xd8thumb")
    sidecar = {"video_id": video_id, "title": title, "channel": channel,
               "url": f"https://www.youtube.com/watch?v={video_id}",
               "duration_seconds": duration, "screenshots": shots}
    sidecar_path = folder / f"{video_id}.json"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    corpus = folder / f"{video_id}.md"
    corpus.write_text(f"# {title}\n", encoding="utf-8")
    idx.upsert_yoink({
        "video_id": video_id, "slug": video_id, "channel": channel, "title": title,
        "topic": "Talks", "yoinked_at": "2026-10-30T10:00:00",
        "corpus_path": str(corpus), "sidecar_path": str(sidecar_path),
        "source_type": "video", "platform": "youtube",
        "metadata_json": json.dumps({"duration_seconds": duration}),
    }, content=f"# {title}\n")
    return folder


# ---------------------------------------------------------------------------
# mid-frame card image
# ---------------------------------------------------------------------------

def test_midframe_picks_the_shot_nearest_the_middle(tmp_path, helper):
    folder = save_video(helper, tmp_path, "midframe001", duration=120, shot_times=(0, 30, 60, 90))
    sidecar = json.loads((folder / "midframe001.json").read_text(encoding="utf-8"))
    assert server._midframe_path(folder, sidecar, 120).name == "shot_0003.jpg"
    # Only an intro and an end card: nothing near the middle, keep the thumbnail.
    sparse = {"screenshots": [s for s in sidecar["screenshots"] if s["timestamp"] in ("00:00:00",)]}
    assert server._midframe_path(folder, sparse, 120) is None
    # Unknown duration: the middle of three or more shots.
    assert server._midframe_path(folder, sidecar, None).name == "shot_0003.jpg"
    # A shot the sidecar lists but the disk lost is never offered, and the
    # neighbours (30 s from the middle of 120 s) are too far to stand in.
    (folder / "screenshots" / "shot_0003.jpg").unlink()
    assert server._midframe_path(folder, sidecar, 120) is None
    assert server._midframe_path(folder, sidecar, 150).name in ("shot_0002.jpg", "shot_0004.jpg")
    assert server._midframe_path(folder, {"screenshots": []}, 120) is None
    assert server._midframe_path(folder, {}, 120) is None


def test_card_image_setting_switches_library_rows(tmp_path, helper):
    save_video(helper, tmp_path, "cardimage01")
    row = server._enrich_yoink_rows(helper, [helper.get_yoink("cardimage01")])[0]
    assert server._read_settings()["card_image"] == "middle"
    assert row["thumbnail_path"].endswith("shot_0003.jpg")
    assert row["card_image_source"] == "middle"
    assert row["original_thumbnail_path"].endswith("thumbnail.jpg")
    server._write_settings({"card_image": "thumbnail"})
    row = server._enrich_yoink_rows(helper, [helper.get_yoink("cardimage01")])[0]
    assert row["thumbnail_path"].endswith("thumbnail.jpg")
    assert row["card_image_source"] == "thumbnail"
    server._write_settings({"card_image": "sideways"})
    assert server._read_settings()["card_image"] == "middle"


def test_existing_capture_without_a_middle_shot_keeps_its_thumbnail(tmp_path, helper):
    save_video(helper, tmp_path, "oldcapture1", duration=600, shot_times=(0,))
    row = server._enrich_yoink_rows(helper, [helper.get_yoink("oldcapture1")])[0]
    assert row["thumbnail_path"].endswith("thumbnail.jpg")
    assert row["card_image_source"] == "thumbnail"


# ---------------------------------------------------------------------------
# import -> queue
# ---------------------------------------------------------------------------

def pending_urls(idx):
    with idx._lock:
        rows = idx._conn.execute(
            "SELECT url, status FROM pending_yoinks ORDER BY pending_id").fetchall()
    return [(r["url"], r["status"]) for r in rows]


def test_import_queues_new_videos_and_skips_the_library(tmp_path, helper):
    save_video(helper, tmp_path, "fNk_zzaMoSs", channel="3Blue1Brown")
    preview = server._list_import_preview("https://hackertube.org/p/hn-canon")
    assert preview["found"] == 3 and preview["already"] == 1 and preview["new"] == 2
    assert preview["message"] == "Found 3 videos, 1 already in your library."
    assert pending_urls(helper) == []  # a preview never queues

    result = server._list_import_start("https://hackertube.org/p/hn-canon")
    assert result["queued"] == 2 and result["skipped"] == 1 and result["already_queued"] == 0
    assert pending_urls(helper) == [
        ("https://www.youtube.com/watch?v=jbkSRLYSojo", "pending"),
        ("https://www.youtube.com/watch?v=D1R-jKKp3NA", "pending"),
    ]
    origin = li.lookup(server.DATA_ROOT, "jbkSRLYSojo")
    assert origin["label"] == "HackerTube" and origin["credit"] == li.HACKERTUBE_CREDIT
    assert "antidote" in origin["note"]

    again = server._list_import_start("https://hackertube.org/p/hn-canon")
    assert again["queued"] == 0 and again["already_queued"] == 2
    assert len(pending_urls(helper)) == 2  # the queue dedupes by URL


def test_indexing_an_imported_capture_adds_its_source_tag(tmp_path, helper):
    server._list_import_start("https://news.ycombinator.com/item?id=15926973", limit=1)
    folder = save_video(helper, tmp_path, "MdmQUlD7P40")
    sidecar = json.loads((folder / "MdmQUlD7P40.json").read_text(encoding="utf-8"))
    server._index_yoink(folder, sidecar, folder / "MdmQUlD7P40.md", folder / "MdmQUlD7P40.json")
    assert helper.get_tags("MdmQUlD7P40") == ["hn thread"]
    row = server._enrich_yoink_rows(helper, [helper.get_yoink("MdmQUlD7P40")])[0]
    assert row["import_origin"]["label"] == "HN thread"
    assert row["import_origin"]["note"].startswith("Shared by dpeck on Hacker News")


def test_unknown_source_is_a_clear_refusal(helper):
    with pytest.raises(li.ImportListError) as err:
        server._list_import_preview("https://example.com/videos")
    assert err.value.code == "unsupported"


# ---------------------------------------------------------------------------
# For You
# ---------------------------------------------------------------------------

def test_for_you_ranks_unopened_imports_by_taste(tmp_path, helper):
    # The user's own saves: two from 3Blue1Brown make it a taste channel.
    save_video(helper, tmp_path, "own00000001", channel="3Blue1Brown", title="Linear maps")
    save_video(helper, tmp_path, "own00000002", channel="3Blue1Brown", title="Determinants")
    for vid in ("own00000001", "own00000002"):
        helper.log_engagement(vid, helper._ENGAGEMENT_EVENT_TYPES[0], helper._ENGAGEMENT_SOURCES[0])
    server._list_import_start("https://hackertube.org/p/hn-canon")
    # Captures land: BBC (higher HackerTube quality) twice, 3Blue1Brown once.
    save_video(helper, tmp_path, "jbkSRLYSojo", channel="BBC", title="Joy of Stats")
    save_video(helper, tmp_path, "D1R-jKKp3NA", channel="BBC", title="Another BBC talk")
    save_video(helper, tmp_path, "fNk_zzaMoSs", channel="3Blue1Brown", title="Vectors")
    picks = server._imported_for_you(helper)
    ids = [p["video_id"] for p in picks]
    assert set(ids) <= {"jbkSRLYSojo", "D1R-jKKp3NA", "fNk_zzaMoSs"}
    assert ids[0] == "fNk_zzaMoSs", picks  # taste beats raw quality
    # Two BBC imports must not make BBC a "taste" channel by themselves.
    bbc = next(p for p in picks if p["video_id"] == "jbkSRLYSojo")
    assert "you've saved this channel before (bbc)" not in bbc["taste_reasons"]
    assert picks[0]["thumbnail_path"].endswith("shot_0003.jpg")
    assert picks[0]["import_origin"]["label"] == "HackerTube"
    # Opening an import takes it off the unopened list.
    helper.log_engagement("fNk_zzaMoSs", helper._ENGAGEMENT_EVENT_TYPES[0], helper._ENGAGEMENT_SOURCES[0])
    assert "fNk_zzaMoSs" not in [p["video_id"] for p in server._imported_for_you(helper)]
    payload = server._discovery_payload(helper)
    assert [r["video_id"] for r in payload["from_imports"]] == [
        p["video_id"] for p in server._imported_for_you(helper)]


# ---------------------------------------------------------------------------
# registry tool
# ---------------------------------------------------------------------------

def test_import_list_tool_preview_and_import(tmp_path, helper):
    uoink_mcp_tools.bind_backend(server)
    preview = uoink_mcp_tools.call_tool("import_list", {
        "url": "https://news.ycombinator.com/item?id=15926973", "preview_only": True})
    assert preview["ok"] is True and preview["found"] == 3 and preview["queued"] == 0
    assert pending_urls(helper) == []
    done = uoink_mcp_tools.call_tool("import_list", {
        "url": "https://news.ycombinator.com/item?id=15926973", "limit": 2})
    assert done["ok"] is True and done["queued"] == 2 and done["next_offset"] == 2
    bad = uoink_mcp_tools.call_tool("import_list", {"url": "https://example.com"})
    assert bad["ok"] is False and bad["code"] == "unsupported"
    spec = uoink_mcp_tools.TOOL_REGISTRY["import_list"]
    assert spec.input_schema["properties"]["limit"]["maximum"] == 50
    assert spec.annotations["destructiveHint"] is False

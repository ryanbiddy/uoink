"""F16: a podcast episode never reads as "Web", and its art stays local."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import index as index_mod
import server
from test_dashboard_runthrough_fixes import run_js


def _row(tmp_path, platform):
    feed = tmp_path / "feed"
    folder = feed / "ep-1"
    folder.mkdir(parents=True)
    corpus = folder / "ep-1.md"
    corpus.write_text("# Ep\n", encoding="utf-8")
    sidecar = folder / "ep-1.json"
    sidecar.write_text(json.dumps({"source_type": "episode", "platform": platform,
                                   "url": "https://pod.example/ep-1"}), encoding="utf-8")
    return {"video_id": "pod_1", "slug": "ep-1", "title": "Ep", "corpus_path": str(corpus),
            "sidecar_path": str(sidecar), "source_type": "episode", "platform": platform,
            "metadata_json": "{}", "yoinked_at": "2026-11-01T00:00:00Z"}, feed


def _enrich(tmp_path, row):
    idx = index_mod.Index.open(tmp_path / "isolated.db")
    try:
        return server._enrich_yoink_rows(idx, [row])[0]
    finally:
        idx.close()


def test_generic_tag_on_an_episode_becomes_podcast(tmp_path):
    row, _ = _row(tmp_path, "generic")
    assert _enrich(tmp_path, row)["platform"] == "podcast"


def test_cached_feed_image_is_used_and_nothing_remote(tmp_path):
    row, feed = _row(tmp_path, "podcast")
    assert _enrich(tmp_path, dict(row))["thumbnail_path"] is None
    art = feed / "artwork.jpg"
    art.write_bytes(b"jpg")
    shown = _enrich(tmp_path, dict(row))
    assert shown["thumbnail_path"] == str(art)


def test_card_labels_a_generic_episode_as_podcast_not_web():
    card = run_js("""cardHtml({video_id: "pod_1", title: "Ep", source_type: "episode", platform: "generic",
                              podcast_title: "Show", source_url: "https://pod.example/ep-1"})""")
    assert "Podcast" in card and "&middot; Web" not in card

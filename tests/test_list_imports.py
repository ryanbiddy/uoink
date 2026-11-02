"""Import a list: parsers, batching, registry, helper glue and For You.

Every test reads saved fixtures in tests/fixtures/list_imports; nothing here
touches the network. hackertube_*.json and hn_item_15926973.json are trimmed
real responses (HackerTube, ODC-By 1.0; Algolia HN API). reddit_thread.json
and ytdlp_flat_playlist.json follow those services' response shapes.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import list_imports as li  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "list_imports"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,kind,extra", [
    ("https://hackertube.org/p/hn-canon", li.SOURCE_HACKERTUBE, {"mode": "playlist", "id": "hn-canon"}),
    ("hackertube.org/c/pure-mathematics", li.SOURCE_HACKERTUBE, {"mode": "category", "id": "pure-mathematics"}),
    ("https://hackertube.org/a/math-theory", li.SOURCE_HACKERTUBE, {"mode": "area", "id": "math-theory"}),
    ("https://hackertube.org/watch/fNk_zzaMoSs", li.SOURCE_HACKERTUBE, {"mode": "video", "id": "fNk_zzaMoSs"}),
    ("https://hackertube.org/", li.SOURCE_HACKERTUBE, {"mode": "top", "params": {}}),
    ("hackertube", li.SOURCE_HACKERTUBE, {"mode": "top"}),
    ("https://hackertube.org/browse?sort=recent&evil=<x>", li.SOURCE_HACKERTUBE,
     {"mode": "top", "params": {"sort": "recent"}}),
    ("https://news.ycombinator.com/item?id=15926973", li.SOURCE_HN, {"id": 15926973}),
    ("https://old.reddit.com/r/programming/comments/1abc23/what_talks/?sort=top", li.SOURCE_REDDIT,
     {"url": "https://www.reddit.com/r/programming/comments/1abc23/what_talks/"}),
    ("https://www.youtube.com/playlist?list=PLbigpodcast0000000000000000000000", li.SOURCE_PLAYLIST,
     {"url": "https://www.youtube.com/playlist?list=PLbigpodcast0000000000000000000000"}),
    ("https://youtube.com/watch?v=abcdefghijk&list=PLbigpodcast0000000000000000000000", li.SOURCE_PLAYLIST,
     {"id": "PLbigpodcast0000000000000000000000"}),
])
def test_classify_supported_sources(text, kind, extra):
    spec = li.classify(text)
    assert spec["kind"] == kind
    for key, value in extra.items():
        assert spec[key] == value


@pytest.mark.parametrize("text,code", [
    ("", "empty"),
    ("https://www.youtube.com/watch?v=abcdefghijk", "unsupported"),
    ("https://news.ycombinator.com/news", "unsupported"),
    ("https://example.com/list", "unsupported"),
    ("https://hackertube.org/settings", "unsupported"),
    ("https://hackertube.org/p/../../etc", "unsupported"),
    ("ftp://hackertube.org/p/x", "invalid_url"),
])
def test_classify_refuses_with_a_reason(text, code):
    with pytest.raises(li.ImportListError) as err:
        li.classify(text)
    assert err.value.code == code
    assert str(err.value)


def test_extract_youtube_ids_handles_hn_escaping_and_variants():
    text = ('<a href="https:&#x2F;&#x2F;www.youtube.com&#x2F;watch?v=MdmQUlD7P40">x</a> '
            "https://youtu.be/lKXe3HUG2l4?t=42 https://m.youtube.com/watch?feature=share&amp;v=PUv66718DII "
            "https://www.youtube.com/shorts/aBcDeFgHiJk https://www.youtube-nocookie.com/embed/SxdOUGdseq4 "
            "https://youtu.be/lKXe3HUG2l4 https://www.youtube.com/watch?v=tooShort "
            "https://notyoutube.com/watch?v=MdmQUlD7P41")
    assert li.extract_youtube_ids(text) == [
        "MdmQUlD7P40", "lKXe3HUG2l4", "PUv66718DII", "aBcDeFgHiJk", "SxdOUGdseq4"]


# ---------------------------------------------------------------------------
# parsers over fixtures
# ---------------------------------------------------------------------------

def test_hackertube_playlist_keeps_why_hn_and_quality():
    title, items = li.parse_hackertube_playlist(load("hackertube_playlist.json"))
    assert title == "The HN canon"
    assert [i["video_id"] for i in items] == ["jbkSRLYSojo", "fNk_zzaMoSs", "D1R-jKKp3NA"]
    first = items[0]
    assert first["note"].startswith("HN commenters send it as a short antidote to cynicism")
    assert first["quality_score"] == 13.5 and first["channel"] == "BBC"
    assert first["url"] == "https://www.youtube.com/watch?v=jbkSRLYSojo"


def test_hackertube_list_rows_and_category_names():
    items = li.parse_hackertube_videos(load("hackertube_list.json"))
    assert [i["video_id"] for i in items] == ["fNk_zzaMoSs", "spUNpyF58BY", "ZK3O402wf1c"]
    assert all(i["note"] for i in items)
    browse = load("hackertube_browse.json")
    assert li.hackertube_name(browse, "category", "pure-mathematics") == "Pure mathematics"
    assert li.hackertube_name(browse, "area", "math-theory") == "Mathematics & Theoretical CS"
    assert li.hackertube_name(browse, "category", "nope") is None


def test_hn_thread_collects_youtube_links_with_who_shared_them():
    title, items = li.parse_hn_thread(load("hn_item_15926973.json"))
    assert title == "Ask HN: What's your favorite tech talk from 2017?"
    assert [i["video_id"] for i in items] == ["MdmQUlD7P40", "HyzD8pNlpwI", "A9U5wK_boYM"]
    assert items[0]["note"].startswith("Shared by dpeck on Hacker News:")
    assert "<" not in items[0]["note"] and "&#x2F;" not in items[0]["note"]


def test_reddit_thread_walks_replies_and_skips_removed():
    title, items = li.parse_reddit_thread(load("reddit_thread.json"))
    assert title == "What talks changed how you write code?"
    assert [i["video_id"] for i in items] == ["SxdOUGdseq4", "lKXe3HUG2l4", "PUv66718DII", "aBcDeFgHiJk"]
    assert items[0]["note"].startswith("From the r/programming post")
    assert items[2]["note"].startswith("Shared by u/bob in r/programming")


def test_ytdlp_flat_playlist_skips_private_and_reports_total():
    title, items, total = li.parse_ytdlp_flat_playlist(load("ytdlp_flat_playlist.json"))
    assert title == "Every episode of a long podcast"
    assert total == 2412
    assert [i["video_id"] for i in items] == ["ep051aaaaaa", "ep053cccccc"]
    assert items[0]["duration_seconds"] == 3725 and items[1]["channel"] == "Podcast Channel"


@pytest.mark.parametrize("bad", [None, {}, [], {"videos": "x"}])
def test_parsers_refuse_wrong_shapes(bad):
    with pytest.raises(li.ImportListError):
        li.parse_hackertube_playlist(bad)
    with pytest.raises(li.ImportListError):
        li.parse_hn_thread(bad)
    with pytest.raises(li.ImportListError):
        li.parse_reddit_thread(bad)


# ---------------------------------------------------------------------------
# fetch_source batching (fake transports)
# ---------------------------------------------------------------------------

def fake_fetch(calls):
    def fetch(url):
        calls.append(url)
        parsed = urlparse(url)
        if parsed.hostname == "hn.algolia.com":
            return load("hn_item_15926973.json")
        assert parsed.hostname == "hackertube.org", url
        if parsed.path == "/api/playlist":
            return load("hackertube_playlist.json")
        if parsed.path == "/api/browse":
            return load("hackertube_browse.json")
        if parsed.path == "/api/list":
            return load("hackertube_list.json")
        raise AssertionError(url)
    return fetch


def test_hackertube_playlist_batch_windows():
    calls = []
    spec = li.classify("https://hackertube.org/p/hn-canon")
    batch = li.fetch_source(spec, offset=1, limit=1, fetch_json=fake_fetch(calls))
    assert [i["video_id"] for i in batch["items"]] == ["fNk_zzaMoSs"]
    assert batch["total"] == 3 and batch["credit"] == li.HACKERTUBE_CREDIT
    assert calls == ["https://hackertube.org/api/playlist?slug=hn-canon"]


def test_hackertube_category_uses_list_api_with_offset():
    calls = []
    spec = li.classify("https://hackertube.org/c/pure-mathematics")
    batch = li.fetch_source(spec, offset=50, limit=50, fetch_json=fake_fetch(calls))
    assert batch["title"] == "HackerTube: Pure mathematics"
    assert "cat=pure-mathematics" in calls[-1] and "offset=50" in calls[-1] and "n=50" in calls[-1]


def test_hackertube_top_n_is_best_first_list():
    calls = []
    batch = li.fetch_source(li.classify("hackertube"), offset=0, limit=5,
                            fetch_json=fake_fetch(calls))
    assert calls == ["https://hackertube.org/api/list?offset=0&n=5"]
    assert batch["title"] == "HackerTube, best first"
    assert batch["total"] == 3  # fewer rows than asked: the end of the list


def test_youtube_playlist_requests_the_offset_window():
    asked = []

    def ytdlp(url, start, end):
        asked.append((url, start, end))
        return load("ytdlp_flat_playlist.json")

    spec = li.classify("https://www.youtube.com/playlist?list=PLbigpodcast0000000000000000000000")
    batch = li.fetch_source(spec, offset=50, limit=50, ytdlp_playlist=ytdlp)
    assert asked == [(spec["url"], 51, 100)]
    assert batch["total"] == 2412
    preview = li.build_preview(spec, batch, offset=50, limit=50, in_library=lambda vid: False)
    assert preview["next_offset"] == 52 and preview["has_more"] is True
    assert "51-52 of 2412" in preview["message"]


def test_reddit_uses_injected_fetch():
    spec = li.classify("https://www.reddit.com/r/programming/comments/1abc23/x/")
    batch = li.fetch_source(spec, offset=0, limit=2, reddit_fetch=lambda url: load("reddit_thread.json"))
    assert [i["video_id"] for i in batch["items"]] == ["SxdOUGdseq4", "lKXe3HUG2l4"]
    assert batch["total"] == 4


def test_preview_counts_library_dedupe_and_message():
    spec = li.classify("https://news.ycombinator.com/item?id=15926973")
    batch = li.fetch_source(spec, offset=0, limit=50, fetch_json=fake_fetch([]))
    preview = li.build_preview(spec, batch, offset=0, limit=50,
                               in_library=lambda vid: vid == "HyzD8pNlpwI")
    assert preview["found"] == 3 and preview["already"] == 1 and preview["new"] == 2
    assert preview["message"] == "Found 3 videos, 1 already in your library."
    assert preview["next_offset"] is None and preview["has_more"] is False
    assert preview["source"]["label"] == "HN thread"


def test_limits_are_capped_at_fifty():
    assert li.clamp_limit(500) == 50 and li.clamp_limit(0) == 1 and li.clamp_limit("x") == 50
    assert li.clamp_offset(-3) == 0 and li.clamp_offset("7") == 7


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

class FakeIndex:
    def __init__(self):
        self.tags = {}

    def add_tags(self, video_id, tags, *, source="agent"):
        self.tags.setdefault(video_id, []).extend((t, source) for t in tags)
        return len(tags)


def test_registry_records_origin_and_tags_once(tmp_path):
    spec = li.classify("https://hackertube.org/p/hn-canon")
    batch = li.fetch_source(spec, offset=0, limit=50, fetch_json=fake_fetch([]))
    preview = li.build_preview(spec, batch, offset=0, limit=50, in_library=lambda v: False)
    li.record_import(tmp_path, preview, [{**preview["videos"][0], "pending_id": 7}])
    origin = li.public_origin(li.lookup(tmp_path, "jbkSRLYSojo"))
    assert origin["label"] == "HackerTube" and origin["list_title"] == "The HN canon"
    assert origin["credit"] == li.HACKERTUBE_CREDIT and "antidote" in origin["note"]
    idx = FakeIndex()
    assert li.apply_on_index(idx, tmp_path, "jbkSRLYSojo") is True
    assert li.apply_on_index(idx, tmp_path, "jbkSRLYSojo") is False
    assert idx.tags == {"jbkSRLYSojo": [("hackertube", li.TAG_SOURCE)]}
    assert li.apply_on_index(idx, tmp_path, "notimported") is False
    assert li.imported_video_ids(tmp_path) == {"jbkSRLYSojo"}


def test_credit_line_names_the_dataset_and_license():
    assert "HackerTube" in li.HACKERTUBE_CREDIT
    assert "ODC-By 1.0" in li.HACKERTUBE_CREDIT
    assert "open-index/hacker-news" in li.HACKERTUBE_CREDIT

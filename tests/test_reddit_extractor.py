"""Tests for the Reddit thread extractor (V3.3-SOURCE-EXPANSION-SPEC.md s4).

Covers URL canonicalization, the pure parse (depth + score + deleted
filtering), markdown rendering, the extract_result shape (fetch injected, no
network), and the persist integration through page_extractor.persist_page_yoink
(fake index + temp data_root -> source_type='reddit_thread').

Run: python tests/test_reddit_extractor.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import reddit_extractor as re_x  # noqa: E402
import page_extractor  # noqa: E402

RAW = [
    {"data": {"children": [
        {"kind": "t3", "data": {
            "title": "Best local AI setup?", "author": "alice",
            "subreddit": "LocalLLaMA", "selftext": "What are you all running?",
            "score": 120, "num_comments": 4,
            "permalink": "/r/LocalLLaMA/comments/abc/best/",
            "created_utc": 1700000000}},
    ]}},
    {"data": {"children": [
        {"kind": "t1", "data": {
            "author": "bob", "body": "Ollama + a 3090.", "score": 40,
            "replies": {"data": {"children": [
                {"kind": "t1", "data": {"author": "carol",
                                        "body": "Same, great combo.",
                                        "score": 5, "replies": ""}},
                {"kind": "t1", "data": {"author": "spammer",
                                        "body": "buy followers",
                                        "score": -3, "replies": ""}},
            ]}}}},
        {"kind": "t1", "data": {"author": "dave", "body": "[deleted]",
                                "score": 10, "replies": ""}},
        {"kind": "more", "data": {}},
    ]}},
]


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_is_url_and_canonical():
    _assert(re_x.is_reddit_thread_url(
        "https://www.reddit.com/r/LocalLLaMA/comments/abc/best/"), "should match")
    _assert(not re_x.is_reddit_thread_url("https://reddit.com/r/LocalLLaMA"), "no comments path")
    _assert(not re_x.is_reddit_thread_url("https://example.com/x"), "non-reddit")
    got = re_x.canonical_json_url(
        "https://old.reddit.com/r/x/comments/abc/t/?utm_source=share#c1")
    _assert(got == "https://www.reddit.com/r/x/comments/abc/t/.json",
            f"canonical wrong: {got}")
    already = re_x.canonical_json_url("https://www.reddit.com/r/x/comments/abc/t.json")
    _assert(already.endswith("/t.json"), f"double .json: {already}")
    print("ok  url match + canonical normalization")


def test_parse_filters():
    parsed = re_x.parse_thread(RAW, depth_limit=4, score_threshold=2)
    _assert(parsed["post"]["title"] == "Best local AI setup?", "post title wrong")
    _assert(parsed["post"]["subreddit"] == "LocalLLaMA", "subreddit wrong")
    _assert(parsed["post"]["url"].endswith("/r/LocalLLaMA/comments/abc/best/"), "post url wrong")
    authors = [c["author"] for c in parsed["comments"]]
    depths = [c["depth"] for c in parsed["comments"]]
    # bob (40, d0) + carol (5, d1). spammer (-3) filtered, dave [deleted] filtered, "more" skipped.
    _assert(authors == ["bob", "carol"], f"comment filter wrong: {authors}")
    _assert(depths == [0, 1], f"depths wrong: {depths}")
    print("ok  parse: score threshold + deleted skip + 'more' skip + depth marker")


def test_parse_depth_limit():
    # depth_limit=0 -> no replies fetched, only top-level
    parsed = re_x.parse_thread(RAW, depth_limit=0, score_threshold=2)
    _assert([c["author"] for c in parsed["comments"]] == ["bob"], "depth_limit=0 should drop replies")
    print("ok  parse: depth_limit=0 drops nested replies")


def test_render():
    parsed = re_x.parse_thread(RAW, depth_limit=4, score_threshold=2)
    md = re_x.render_markdown(parsed)
    _assert(md.startswith("# Best local AI setup?"), "title heading missing")
    _assert("## Top comments" in md, "top comments header missing")
    _assert("### u/bob (score 40)" in md, "top comment heading wrong")
    _assert("#### u/carol (score 5)" in md, "nested reply heading wrong")
    _assert("**r/LocalLLaMA**" in md, "meta line missing")
    print("ok  render: post + nested comment headings")


def test_extract_result_shape():
    res = re_x.extract_reddit_thread(
        "https://www.reddit.com/r/LocalLLaMA/comments/abc/best/",
        _fetch=lambda url, timeout=20: RAW)
    _assert(res["ok"] is True, "should be ok")
    _assert(res["title"] == "Best local AI setup?", "title wrong")
    _assert(res["extraction_engine"] == "reddit-json", "engine wrong")
    _assert(res["comments_captured"] == 2, "comment count wrong")
    _assert(res["metadata"]["subreddit"] == "LocalLLaMA", "metadata subreddit wrong")
    _assert(res["markdown"].startswith("# Best"), "markdown missing")
    # error paths
    bad = re_x.extract_reddit_thread("https://example.com/x")
    _assert(bad["ok"] is False and bad["code"] == "bad_url", "bad url should fail")

    def _boom(url, timeout=20):
        raise ValueError("Reddit returned 403. This thread is private...")
    err = re_x.extract_reddit_thread(
        "https://www.reddit.com/r/x/comments/abc/t/", _fetch=_boom)
    _assert(err["ok"] is False and err["code"] == "fetch_failed", "fetch error should propagate")
    _assert("403" in err["error"], "error message lost")
    print("ok  extract_reddit_thread: happy path + bad-url + fetch-error")


class _FakeIndex:
    def __init__(self):
        self.records = []

    def upsert_yoink(self, record, *, content=""):
        self.records.append((record, content))


def test_persist_integration():
    res = re_x.extract_reddit_thread(
        "https://www.reddit.com/r/LocalLLaMA/comments/abc/best/",
        _fetch=lambda url, timeout=20: RAW)
    idx = _FakeIndex()
    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        video_id = page_extractor.persist_page_yoink(
            idx, res, data_root=data_root,
            source_type=re_x.SOURCE_TYPE, subfolder="Reddit", slug_prefix="reddit")
        _assert(video_id and video_id.startswith("reddit_"), f"video_id prefix wrong: {video_id}")
        rec, content = idx.records[0]
        _assert(rec["source_type"] == "reddit_thread", "source_type not set")
        # Phase 2: channel is the real "who" (the subreddit), not the host.
        _assert(rec["channel"] == "r/LocalLLaMA", f"channel wrong: {rec['channel']}")
        _assert(rec["platform"] == "reddit", f"platform wrong: {rec['platform']}")
        _assert(rec["author"] == "r/LocalLLaMA", f"author wrong: {rec['author']}")
        corpus = Path(rec["corpus_path"])
        sidecar = Path(rec["sidecar_path"])
        _assert(corpus.exists() and corpus.parent.parent.name == "Reddit", "corpus folder wrong")
        # Phase 2: readable slug folder (r-<sub>-<hash>), not an opaque hash.
        _assert(corpus.parent.name.startswith("r-localllama-"),
                f"reddit folder not a readable slug: {corpus.parent.name}")
        _assert(corpus.name == "reddit.md", f"corpus filename wrong: {corpus.name}")
        body = corpus.read_text(encoding="utf-8")
        _assert("Best local AI setup?" in body and "## Top comments" in body, "corpus content wrong")
        sc = json.loads(sidecar.read_text(encoding="utf-8"))
        _assert(sc["source_type"] == "reddit_thread", "sidecar source_type wrong")
        _assert(content.startswith("# Best"), "FTS content wrong")
    print("ok  persist_page_yoink: reddit_thread source_type, Reddit/ folder, corpus + sidecar + FTS")


def test_page_path_unchanged():
    # Backward-compat: default args still persist a source_type='page' yoink.
    idx = _FakeIndex()
    page_result = {"ok": True, "url": "https://example.com/post",
                   "title": "A Page", "markdown": "body", "metadata": {},
                   "extraction_engine": "stdlib", "extracted_at": "2026-05-30T00:00:00Z"}
    with tempfile.TemporaryDirectory() as d:
        vid = page_extractor.persist_page_yoink(idx, page_result, data_root=Path(d))
        _assert(vid.startswith("page_"), f"page video_id prefix changed: {vid}")
        rec, _ = idx.records[0]
        _assert(rec["source_type"] == "page", "page source_type changed")
        _assert(Path(rec["corpus_path"]).name == "page.md", "page corpus filename changed")
        _assert(Path(rec["corpus_path"]).parent.parent.name == "Pages", "page folder changed")
    print("ok  persist_page_yoink: default page path unchanged (backward-compat)")


def main():
    test_is_url_and_canonical()
    test_parse_filters()
    test_parse_depth_limit()
    test_render()
    test_extract_result_shape()
    test_persist_integration()
    test_page_path_unchanged()
    print("\nALL REDDIT EXTRACTOR TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

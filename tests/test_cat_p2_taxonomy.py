"""cat P2 -- source-agnostic taxonomy (schema + backfill + facets + filters).

Run: python tests/test_cat_p2_taxonomy.py   (or via pytest)

The data model was YouTube-shaped: `channel` was the only "who" field and
got hard-coded to the URL hostname for every non-YouTube source, so an X
Article by @boardyai showed up as "x.com". Phase 2 adds first-class
`platform` + `author` columns, populates them on write, backfills existing
rows from their sidecars, and exposes platform / source_type / author as
Library facets + search filters.

Red before the fix:
  - the yoinks table had no `platform` and no `author` column;
  - persist_page_yoink wrote channel = urlparse(url).hostname;
  - /library/facets had no platform / source_type / author facet;
  - /memory/search could not filter by platform / source_type / author.
"""
from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import page_extractor as pe  # noqa: E402
import server  # noqa: E402

PORT = 5198


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _get(path, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _fresh_index():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    return tmp, idx


# ---- schema + migration ---------------------------------------------------
def test_migration_adds_columns_and_is_idempotent():
    tmp, idx = _fresh_index()
    try:
        cols = {r[1] for r in idx._conn.execute("PRAGMA table_info(yoinks)")}
        _assert("platform" in cols, "platform column missing after migration")
        _assert("author" in cols, "author column missing after migration")
        # Re-running the migration pass is a no-op (idempotent).
        before = index_mod._current_schema_version(idx._conn)
        index_mod._run_migrations(idx._conn)
        after = index_mod._current_schema_version(idx._conn)
        _assert(before == after, f"migration not idempotent: {before} -> {after}")
    finally:
        idx.close()
        tmp.cleanup()
    print("ok  migration 0020 adds platform+author, idempotent re-run")


# ---- persist populates the taxonomy --------------------------------------
def test_persist_sets_platform_author_channel_topic_and_readable_slug():
    tmp, idx = _fresh_index()
    root = Path(tmp.name) / "corpus"
    try:
        def classify(meta):
            t = (meta.get("title", "") + " " + meta.get("description", "")).lower()
            return "AI" if "ai" in t else "Uncategorized"

        x = {"ok": True, "url": "https://x.com/boardyai/article/1",
             "title": "Boardy on AI", "markdown": "an ai article",
             "metadata": {"author_name": "Boardy", "author_handle": "boardyai"},
             "extraction_engine": "x", "extracted_at": "2026-07-01T10:00:00",
             "links": [], "images": []}
        vid = pe.persist_page_yoink(
            idx, x, data_root=root, source_type="x_article",
            subfolder="X", slug_prefix="x-article", topic_classifier=classify)
        row = idx.get_yoink(vid)
        _assert(row["platform"] == "x", f"platform: {row['platform']}")
        _assert(row["author"] == "Boardy (@boardyai)", f"author: {row['author']}")
        # channel is the real author now, not the host (Bug 3 fixed).
        _assert(row["channel"] == "Boardy (@boardyai)", f"channel: {row['channel']}")
        _assert(row["channel"] != "x.com", "channel still hostname (Bug 3)")
        _assert(row["topic"] == "AI", f"topic not classified: {row['topic']}")
        _assert(row["slug"].startswith("boardyai-"),
                f"folder slug not readable: {row['slug']}")

        r = {"ok": True, "url": "https://reddit.com/r/python/x",
             "title": "py tips", "markdown": "text",
             "metadata": {"subreddit": "python"},
             "extraction_engine": "reddit", "extracted_at": "2026-07-02T10:00:00",
             "links": [], "images": []}
        vid2 = pe.persist_page_yoink(
            idx, r, data_root=root, source_type="reddit_thread",
            subfolder="Reddit", slug_prefix="reddit")
        row2 = idx.get_yoink(vid2)
        _assert(row2["platform"] == "reddit", f"platform: {row2['platform']}")
        _assert(row2["author"] == "r/python", f"author: {row2['author']}")
    finally:
        idx.close()
        tmp.cleanup()
    print("ok  persist sets platform/author, corrects channel, classifies topic, readable slug")


# ---- backfill corrects existing rows -------------------------------------
def test_backfill_corrects_hostname_channel_and_is_idempotent():
    tmp, idx = _fresh_index()
    root = Path(tmp.name) / "corpus"
    root.mkdir(parents=True)
    try:
        # Simulate a pre-Phase-2 X row: channel = "x.com", no author, plus its
        # sidecar carrying the real author (the shape persist used to write).
        folder = root / "X" / "805baf72"
        folder.mkdir(parents=True)
        sc = folder / "x.json"
        sc.write_text(json.dumps({
            "schema_version": 2, "source_type": "x_article",
            "url": "https://x.com/boardyai/article/1", "title": "t",
            "metadata": {"author_name": "Boardy", "author_handle": "boardyai"},
        }), encoding="utf-8")
        idx.upsert_yoink({
            "video_id": "x_old1", "slug": "805baf72", "channel": "x.com",
            "title": "t", "yoinked_at": "2026-01-01T00:00:00",
            "corpus_path": str(folder / "x.md"), "sidecar_path": str(sc),
            "source_type": "x_article"})
        # Blank platform/author to mimic the pre-migration state, then apply
        # the SQL migration's platform derivation.
        idx._conn.execute(
            "UPDATE yoinks SET platform=NULL, author=NULL WHERE video_id='x_old1'")
        idx._conn.execute(
            "UPDATE yoinks SET platform='x' WHERE platform IS NULL")
        idx._conn.commit()

        before = idx.get_yoink("x_old1")
        _assert(before["channel"] == "x.com", "precondition: channel is host")
        _assert(before["author"] is None, "precondition: no author")

        stats = pe.backfill_platform_author(idx)
        after = idx.get_yoink("x_old1")
        _assert(after["author"] == "Boardy (@boardyai)", f"author: {after['author']}")
        _assert(after["channel"] == "Boardy (@boardyai)", f"channel: {after['channel']}")
        _assert(stats["channel_corrected"] == 1, f"stats: {stats}")
        _assert(stats["author_from_sidecar"] == 1, f"stats: {stats}")

        # Idempotent: a second pass changes nothing.
        stats2 = pe.backfill_platform_author(idx)
        _assert(stats2["channel_corrected"] == 0 and stats2["author_from_sidecar"] == 0,
                f"backfill not idempotent: {stats2}")
    finally:
        idx.close()
        tmp.cleanup()
    print("ok  backfill corrects hostname channel from sidecar, idempotent")


# ---- facets + filters over HTTP ------------------------------------------
def _seed_corpus(idx, root: Path):
    # Real corpus files so _enrich_yoink_rows (which drops rows with no
    # corpus_path) keeps them.
    def _cp(vid):
        p = root / vid / "corpus.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# body", encoding="utf-8")
        return str(p)
    idx.upsert_yoink({
        "video_id": "yt1", "slug": "yt1", "channel": "Karpathy",
        "platform": "youtube", "author": "Karpathy", "title": "nets",
        "topic": "AI", "yoinked_at": "2026-05-01T10:00:00",
        "corpus_path": _cp("yt1"), "sidecar_path": "", "source_type": "video"})
    idx.upsert_yoink({
        "video_id": "x1", "slug": "boardyai-1", "channel": "Boardy (@boardyai)",
        "platform": "x", "author": "Boardy (@boardyai)", "title": "x post",
        "topic": "AI", "yoinked_at": "2026-06-01T10:00:00",
        "corpus_path": _cp("x1"), "sidecar_path": "", "source_type": "x_article"})
    idx.upsert_yoink({
        "video_id": "r1", "slug": "r-python-1", "channel": "r/python",
        "platform": "reddit", "author": "r/python", "title": "reddit thread",
        "topic": "Programming", "yoinked_at": "2026-06-10T10:00:00",
        "corpus_path": _cp("r1"), "sidecar_path": "", "source_type": "reddit_thread"})


def test_http_facets_and_search_filters():
    tmp, idx = _fresh_index()
    server._get_index = lambda: idx  # type: ignore
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        _seed_corpus(idx, Path(tmp.name) / "corpus")
        status, res = _get("/library/facets")
        _assert(status == 200 and res["ok"], f"facets: {status} {res}")
        facets = res["facets"]
        _assert("platform" in facets, "no platform facet")
        _assert("source_type" in facets, "no source_type facet")
        _assert("author" in facets, "no author facet")
        plats = {p["value"]: p["label"] for p in facets["platform"]}
        _assert(plats.get("x") == "X", f"platform label: {plats}")
        _assert(plats.get("youtube") == "YouTube", f"platform label: {plats}")
        _assert(plats.get("reddit") == "Reddit", f"platform label: {plats}")
        stypes = {s["value"]: s["label"] for s in facets["source_type"]}
        _assert(stypes.get("x_article") == "X article", f"source_type label: {stypes}")
        authors = {a["value"] for a in facets["author"]}
        _assert("Boardy (@boardyai)" in authors, f"authors: {authors}")
        print("ok  /library/facets exposes platform + source_type + author with labels")

        # Filter by platform=x -> only the X row (real author, not "x.com").
        status, res = _get("/memory/search?platform=x")
        _assert(status == 200 and res["ok"], f"search platform: {res}")
        _assert(res["total"] == 1, f"platform=x count: {res['total']}")
        got = res["results"][0]
        _assert(got["platform"] == "x", f"row platform: {got['platform']}")
        _assert(got["author"] == "Boardy (@boardyai)", f"row author: {got['author']}")
        _assert(got.get("channel") != "x.com", "row still shows host")
        print("ok  /memory/search?platform=x returns the X row with the real author")

        # Filter by source_type + by author.
        status, res = _get("/memory/search?source_type=reddit_thread")
        _assert(res["total"] == 1 and res["results"][0]["platform"] == "reddit",
                f"source_type filter: {res}")
        status, res = _get("/memory/search?author=Karpathy")
        _assert(res["total"] == 1 and res["results"][0]["platform"] == "youtube",
                f"author filter: {res}")
        print("ok  /memory/search filters by source_type and author")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()


def main():
    test_migration_adds_columns_and_is_idempotent()
    test_persist_sets_platform_author_channel_topic_and_readable_slug()
    test_backfill_corrects_hostname_channel_and_is_idempotent()
    test_http_facets_and_search_filters()
    print("\nALL CAT P2 TAXONOMY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Search and list by show and original publish date (not the capture date).

Reuses the timed cues fixtures: five saves across two made-up shows with
publish dates in three shapes (ISO, yt-dlp's YYYYMMDD and an RSS pubDate)
plus one save with no known publish date.
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import index as index_mod  # noqa: E402
import server  # noqa: E402
from test_timed_cues import PODCAST_ID, SHOW, _build  # noqa: E402
from uoink_core import search_service  # noqa: E402


@pytest.mark.parametrize("value, day", [
    ("20250304", "2025-03-04"),
    ("2025-03-04", "2025-03-04"),
    ("2025-03-04T15:00:00Z", "2025-03-04"),
    ("Mon, 03 Mar 2025 23:30:00 -0800", "2025-03-04"),     # RSS, read in UTC
    (1741100400, "2025-03-04"),
    ("1741100400", None),                                 # a bare number string is not a date
    ("2025-02-30", None),
    ("soon", None),
    ("", None),
    (None, None),
    (True, None),
])
def test_published_day_shapes(value, day):
    assert index_mod.published_day(value) == day


@pytest.mark.parametrize("value, day", [
    ("2025-03-03T23:30:00-08:00", "2025-03-04"),     # the same instant as the RSS case
    ("2025-03-04T01:30:00+09:00", "2025-03-03"),
    ("2025-03-04T15:00:00.250Z", "2025-03-04"),
    ("2025-03-04 15:00:00", "2025-03-04"),           # no zone: the day as written
    ("2025-03-04T99:99:99Z", None),
    ("2025-03-04 bogus", None),
    ("2025-03-04x", None),
    ("20250304 extra", None),
])
def test_published_day_reads_iso_offsets_and_refuses_junk(value, day):
    assert index_mod.published_day(value) == day


def test_cues_never_pass_on_a_junk_date():
    import timed_cues
    assert timed_cues.published_value("2025-03-04 bogus", "20240101") == "2024-01-01"
    assert timed_cues.published_value("2025-03-03T23:30:00-08:00") == "2025-03-03T23:30:00-08:00"


_RFC_ROW = {"published_at": "Mon, 03 Mar 2025 23:30:00 -0800"}       # how podcast saves store it


def _row(video_id, meta):
    return {"video_id": video_id, "slug": video_id, "channel": SHOW, "title": video_id, "topic": "Tides",
            "yoinked_at": "2026-11-01T09:00:00", "corpus_path": "", "sidecar_path": "",
            "metadata_json": json.dumps(meta), "source_type": "episode", "platform": "podcast"}


def test_the_publish_day_is_stored_indexed_and_kept_current(tmp_path, monkeypatch):
    with index_mod.Index.open(tmp_path / "day.db") as index:
        index.upsert_yoink(_row("tppod000001", _RFC_ROW))
        index.upsert_yoink(_row("tppod000002", {"upload_date": "20240101"}))
        index.upsert_yoink(_row("tppod000003", {}))
        days = dict(index._conn.execute("SELECT video_id, published_day FROM yoinks").fetchall())
        assert days == {"tppod000001": "2025-03-04", "tppod000002": "2024-01-01", "tppod000003": None}
        index.upsert_yoink(_row("tppod000002", {"upload_date": "20230101"}))
        assert index.get_yoink("tppod000002")["published_day"] == "2023-01-01"
        plan = " ".join(str(tuple(r)) for r in index._conn.execute(
            "EXPLAIN QUERY PLAN SELECT video_id FROM yoinks y WHERE y.published_day >= ?", ("2025-01-01",)))
        assert "idx_yoinks_published_day" in plan
        # The filter reads the column: the metadata is never parsed per row.
        monkeypatch.setattr(index_mod, "published_day_from_metadata",
                            lambda _m: (_ for _ in ()).throw(AssertionError("parsed per row")))
        got = index.search_yoinks_for_memory(published_from="2025-01-01")
        assert _ids(got) == {"tppod000001"}


def _old_index(tmp_path, monkeypatch, upto=34):
    old = tmp_path / "old-migrations"
    old.mkdir()
    for path in index_mod._MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name.split("_", 1)[0]) <= upto:
            (old / path.name).write_bytes(path.read_bytes())
    real = index_mod._MIGRATIONS_DIR
    monkeypatch.setattr(index_mod, "_MIGRATIONS_DIR", old)
    db = tmp_path / "old.db"
    with index_mod.Index.open(db) as index:
        index.upsert_yoink(_row("tppod000001", _RFC_ROW))
        index.upsert_yoink(_row("tpvideo0001", {"upload_date": "20240101",
                                                "published_at": "2024-01-01T23:30:00-08:00"}))
        index.upsert_yoink(_row("tpnote00001", {"title": "no date"}))
    monkeypatch.setattr(index_mod, "_MIGRATIONS_DIR", real)
    return db


def test_migration_0038_backfills_existing_rows(tmp_path, monkeypatch):
    db = _old_index(tmp_path, monkeypatch)
    with index_mod.Index.open(db) as index:
        assert index_mod._current_schema_version(index._conn) >= index_mod.PUBLISHED_DAY_MIGRATION
        days = dict(index._conn.execute("SELECT video_id, published_day FROM yoinks").fetchall())
    assert days == {"tppod000001": "2025-03-04", "tpvideo0001": "2024-01-02", "tpnote00001": None}


def test_an_index_read_before_the_migration_still_filters(tmp_path, monkeypatch):
    db = _old_index(tmp_path, monkeypatch)
    index = index_mod.Index.open_existing(db)
    try:
        assert index.published_day_sql("y") == "uoink_published_day(y.metadata_json)"
        got = index.search_yoinks_for_memory(published_from="2025-01-01")
        assert _ids(got) == {"tppod000001"}
    finally:
        index.close()


def test_published_day_from_metadata_prefers_published_at():
    meta = {"upload_date": "20240101", "published_at": "2025-03-04T15:00:00Z"}
    assert index_mod.published_day_from_metadata(json.dumps(meta)) == "2025-03-04"
    assert index_mod.published_day_from_metadata(json.dumps({"upload_date": "20240101"})) == "2024-01-01"
    assert index_mod.published_day_from_metadata("not json") is None
    assert index_mod.published_day_from_metadata(None) is None


@pytest.fixture
def idx(tmp_path):
    index = _build(tmp_path)
    try:
        yield index
    finally:
        index.close()


def _ids(result):
    return {row["video_id"] for row in result["results"]}


def test_memory_search_filters_by_publish_date(idx):
    got = idx.search_yoinks_for_memory(published_from="2025-01-01", published_to="2025-12-31")
    assert _ids(got) == {"tpcaptions1", PODCAST_ID} and got["total"] == 2
    got = idx.search_yoinks_for_memory(channel="Other Show", published_to="2024-01-01")
    assert _ids(got) == {"tpasrvideo1"}
    got = idx.search_yoinks_for_memory(q="anemones", published_from="2025-03-04")
    assert _ids(got) == {"tpcaptions1"}
    # The capture-date bounds still mean the capture date.
    got = idx.search_yoinks_for_memory(date_from="2026-11-03", published_from="2024-01-01")
    assert _ids(got) == {"tpautocaps01", PODCAST_ID}


def test_publish_bounds_route_to_keyword_search(idx):
    assert search_service.select_mode(idx, "hybrid", filters={"published_from": "2025-01-01"}) == (
        "keyword", "Publish date filtering uses keyword search.")
    got = idx.search_mode("anemones", mode="hybrid",
                          filters={"published_from": "2025-01-01", "published_to": None})
    assert _ids(got) == {"tpcaptions1"}
    got = idx.search_mode(None, filters={"channel": SHOW, "published_to": "2024-12-31"})
    assert _ids(got) == {"tpautocaps01"}


class _QuietHandler(server.Handler):
    def log_message(self, format, *args):  # noqa: A002
        return


@pytest.fixture
def get(idx, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server, "_check_memory_search_rate_limit", lambda: True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = int(httpd.server_address[1])

    def call(**params):
        url = f"http://127.0.0.1:{port}/memory/search?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"X-Uoink-Token": server.TOKEN})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())
    try:
        yield call
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_library_route_filters_by_show_and_publish_date(get):
    status, body = get(channel=SHOW, published_from="2025-01-01")
    assert status == 200
    assert {r["video_id"] for r in body["results"]} == {"tpcaptions1", PODCAST_ID}
    by_id = {r["video_id"]: r for r in body["results"]}
    assert by_id["tpcaptions1"]["published_at"] == "2025-03-04"
    assert by_id[PODCAST_ID]["published_at"] == "2025-03-03"
    # The sorted Library path (_library_search) honours the same bounds.
    status, body = get(published_from="2024-01-01", published_to="2024-12-31", sort="oldest")
    assert status == 200 and [r["video_id"] for r in body["results"]] == ["tpautocaps01"]
    status, body = get(published_to="2000-01-01")
    assert status == 200 and body["state"] == "no_matches"


@pytest.mark.parametrize("params, error", [
    ({"published_from": "2025-13-01"}, "published_from must be YYYY-MM-DD"),
    ({"published_to": "March"}, "published_to must be YYYY-MM-DD"),
    ({"published_from": "2025-02-01", "published_to": "2025-01-01"}, "published_from is after published_to"),
])
def test_library_route_rejects_bad_publish_dates(get, params, error):
    status, body = get(**params)
    assert status == 400 and body["error"] == error

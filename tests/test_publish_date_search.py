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
from test_timed_cues import SHOW, _build  # noqa: E402
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
    assert _ids(got) == {"tpcaptions1", "tppodcast01"} and got["total"] == 2
    got = idx.search_yoinks_for_memory(channel="Other Show", published_to="2024-01-01")
    assert _ids(got) == {"tpasrvideo1"}
    got = idx.search_yoinks_for_memory(q="anemones", published_from="2025-03-04")
    assert _ids(got) == {"tpcaptions1"}
    # The capture-date bounds still mean the capture date.
    got = idx.search_yoinks_for_memory(date_from="2026-11-03", published_from="2024-01-01")
    assert _ids(got) == {"tpautocaps01", "tppodcast01"}


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
    assert {r["video_id"] for r in body["results"]} == {"tpcaptions1", "tppodcast01"}
    by_id = {r["video_id"]: r for r in body["results"]}
    assert by_id["tpcaptions1"]["published_at"] == "2025-03-04"
    assert by_id["tppodcast01"]["published_at"] == "2025-03-03"
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

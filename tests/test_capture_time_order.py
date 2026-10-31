"""Capture times sort by real time when local and UTC stamps are mixed.

Videos store yoinked_at as local time with no zone; pages, posts and notes
store UTC with a Z. Text order ranks a same-day UTC stamp above a newer
local one west of Greenwich (and below an older one east of it). Where the
platform allows it, the local zone is pinned to US Pacific so the check
bites on a UTC runner too.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

import channels
import index
import server
from uoink_core import local_search


@pytest.fixture(autouse=True)
def pacific_time():
    if not hasattr(time, "tzset"):
        yield
        return
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "PST8PDT,M3.2.0,M11.1.0"
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


BASE = datetime(2026, 10, 20, 10, 0, 0)  # local wall time, clear of DST changes


def local_stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def utc_stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed(idx, rows):
    with idx._conn:
        for video_id, stamp, source_type in rows:
            idx._conn.execute(
                "INSERT INTO yoinks(video_id, slug, title, channel, topic, source_type, yoinked_at, "
                "corpus_path, sidecar_path) VALUES (?,?,?,?,?,?,?,?,'')",
                (video_id, video_id, f"Item {video_id}", "Shared Channel", "Space", source_type,
                 stamp, f"/library/{video_id}.md"))


def mixed_rows():
    # Alternating kinds, an hour apart: newest first is page2, video2, page1, video1.
    return [
        ("video1", local_stamp(BASE), "video"),
        ("page1", utc_stamp(BASE + timedelta(hours=1)), "page"),
        ("video2", local_stamp(BASE + timedelta(hours=2)), "video"),
        ("page2", utc_stamp(BASE + timedelta(hours=3)), "page"),
    ]


@pytest.fixture
def library(tmp_path):
    with index.Index.open(tmp_path / "index.db") as idx:
        seed(idx, mixed_rows())
        yield idx


NEWEST = ["page2", "video2", "page1", "video1"]


def ids(rows):
    return [row["video_id"] for row in rows]


def test_sort_key_reads_zoned_stamps_as_local_time():
    moment = BASE + timedelta(minutes=7)
    assert index.capture_sort_key(utc_stamp(moment)) == local_stamp(moment)
    offset = moment.astimezone().utcoffset()
    assert index.capture_sort_key(moment.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00") \
        == local_stamp(moment + offset)
    assert index.capture_sort_key(local_stamp(moment)) == local_stamp(moment)
    assert index.capture_sort_key("2026-10-20") == "2026-10-20"
    assert index.capture_sort_key("not a date Z") == "not a date Z"
    assert index.capture_sort_key(None) == ""


@pytest.mark.parametrize("stamp", [
    utc_stamp(BASE), local_stamp(BASE), "2026-10-20",
    "2026-10-20T19:30:00+02:00", "2026-10-20T08:15:00.250-04:00", "garbage Z", "",
])
def test_sql_twin_agrees_with_python(tmp_path, stamp):
    with index.Index.open(tmp_path / "index.db") as idx:
        row = idx._conn.execute(
            f"WITH t(yoinked_at) AS (VALUES (?)) SELECT {index.capture_time_sql()} FROM t",
            (stamp,)).fetchone()
    assert row[0] == index.capture_sort_key(stamp)


def test_recent_list_backs_mcp_and_cli_in_real_time_order(library):
    assert ids(library.list_recent(10)) == NEWEST


def test_library_page_without_query_is_newest_first(library):
    assert ids(library.search_yoinks_for_memory(limit=10)["results"]) == NEWEST


def test_library_sort_control_orders_by_real_time(library):
    page = server._library_search(library, q=None, filters={}, kind=None, sort="newest", limit=10, offset=0)
    assert ids(page["results"]) == NEWEST
    page = server._library_search(library, q=None, filters={}, kind=None, sort="oldest", limit=10, offset=0)
    assert ids(page["results"]) == NEWEST[::-1]


@pytest.mark.parametrize("passages", [True, False])
def test_keyword_query_with_sort_orders_by_real_time(tmp_path, passages):
    # With a query the page is built by _fts_page, which re-aliases the order.
    with index.Index.open(tmp_path / "index.db") as idx:
        for video_id, stamp, source_type in mixed_rows():
            idx.upsert_yoink({"video_id": video_id, "slug": video_id, "channel": "Shared Channel",
                              "title": f"Moon {video_id}", "topic": "Space", "source_type": source_type,
                              "yoinked_at": stamp, "corpus_path": "", "sidecar_path": ""},
                             content="The moon and its phases.")
        for sort, expected in (("newest", NEWEST), ("oldest", NEWEST[::-1])):
            page = server._library_search(idx, q="moon", filters={}, kind=None, sort=sort, limit=10,
                                          offset=0, mode="keyword", passages=passages)
            assert ids(page["results"]) == expected


def test_semantic_results_resort_by_real_time(library, monkeypatch):
    import uoink_core.search_service as search_service
    rows = [{"video_id": vid, "yoinked_at": stamp} for vid, stamp in library._conn.execute(
        "SELECT video_id, yoinked_at FROM yoinks ORDER BY video_id")]
    monkeypatch.setattr(search_service, "select_mode", lambda idx, mode: ("semantic", None))
    monkeypatch.setattr(library, "search_mode",
                        lambda *args, **kwargs: {"results": list(rows), "search_mode": "semantic"})
    page = server._library_search(library, q="moon", filters={}, kind=None, sort="newest",
                                  limit=10, offset=0, mode="semantic", passages=False)
    assert ids(page["results"]) == NEWEST


def test_facet_queries_order_by_real_time(library):
    assert ids(library.query_by_facets(topic="Space")) == NEWEST
    bounds = library.corpus_facets()["date_bounds"]
    stored = dict(library._conn.execute("SELECT video_id, yoinked_at FROM yoinks").fetchall())
    assert bounds == {"min": stored["video1"], "max": stored["page2"]}
    picked = library.corpus_channels()
    assert picked[0]["corpus_path"] == "/library/page2.md"


def test_self_rows_are_newest_first(library):
    with library._conn:
        library._conn.executemany(
            "INSERT INTO yoink_tags(video_id, tag, added_at) VALUES (?, 'is_self', ?)",
            [(vid, local_stamp(BASE)) for vid in NEWEST])
    assert ids(channels.self_yoink_rows(library)) == NEWEST


def test_date_filters_use_the_local_calendar_day(tmp_path):
    # 23:30 local on the 20th is already the 21st in UTC west of Greenwich;
    # 00:30 local on the 21st is still the 20th in UTC east of it.
    late = BASE.replace(hour=23, minute=30)
    early = late + timedelta(hours=1)
    with index.Index.open(tmp_path / "index.db") as idx:
        seed(idx, [("late", utc_stamp(late), "page"), ("early", utc_stamp(early), "page")])
        day = {"date_from": "2026-10-20", "date_to": "2026-10-20"}
        assert ids(idx.search_yoinks_for_memory(**day)["results"]) == ["late"]
        page = server._library_search(idx, q=None, filters=day, kind=None, sort="newest", limit=10, offset=0)
        assert ids(page["results"]) == ["late"]
        sources = local_search.IndexSources(idx).snapshot(filters=day)
        assert [source.source_id for source in sources] == ["late"]


def test_resurface_age_reads_utc_stamps_as_utc():
    a_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    stamp = a_day_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert server._resurface_days_since(stamp) == pytest.approx(1.0, abs=0.01)
    assert server.Handler._days_since_iso(stamp) == pytest.approx(1.0, abs=0.01)
    assert server._resurface_days_since(local_stamp(datetime.now() - timedelta(days=2))) \
        == pytest.approx(2.0, abs=0.01)

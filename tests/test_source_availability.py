"""Availability checks use disposable indexes and canned HTTP responses only."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from io import BytesIO
import json
from pathlib import Path
import socket
import sqlite3
import sys
import threading
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

import index as index_mod
import source_availability as availability


T0 = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


def iso(moment=T0):
    return moment.isoformat().replace("+00:00", "Z")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Network access is forbidden in availability tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture
def idx(tmp_path):
    with index_mod.Index.open(tmp_path / "index.db") as index:
        yield index


def save(idx, video_id="item", *, platform="web", url="https://example.com/item", **metadata):
    record = {"video_id": video_id, "slug": video_id, "title": video_id, "yoinked_at": iso(),
              "corpus_path": str(idx._path.parent / f"{video_id}.md"),
              "sidecar_path": str(idx._path.parent / f"{video_id}.json"),
              "platform": platform, "metadata_json": json.dumps({"url": url, **metadata})}
    idx.upsert_yoink(record)
    return record


def response(code, body=b"", headers=None):
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
    return code, headers or {}, body


class Fetch:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, method, url, headers, timeout, max_bytes):
        self.calls.append(SimpleNamespace(method=method, url=url, headers=headers,
                                          timeout=timeout, max_bytes=max_bytes))
        if not self.answers:
            pytest.fail("Unexpected HTTP request")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def run(idx, fetch, now=T0, **kwargs):
    return availability.run_once(idx, fetch=fetch, now=now, sleep=lambda _: None, **kwargs)


def player(status, reason=""):
    return b"<script>var ytInitialPlayerResponse = " + json.dumps({
        "playabilityStatus": {"status": status, "reason": reason,
                              "errorScreen": {"playerErrorMessageRenderer": {"reason": {"simpleText": reason}}}}
    }).encode() + b";</script>"


def reddit(**fields):
    return [{"data": {"children": [{"data": {"author": "someone", "selftext": "hello", **fields}}]}}]


@pytest.mark.parametrize("platform,url,answers,expected", [
    ("youtube", "https://youtu.be/abcdefghijk", [response(200)], "available"),
    ("youtube", "https://www.youtube.com/shorts/abcdefghijk", [response(404)], "deleted"),
    ("youtube", "https://www.youtube.com/watch?v=abcdefghijk", [response(401), response(200, player("LOGIN_REQUIRED", "This video is private"))], "private"),
    ("youtube", "https://www.youtube.com/watch?v=abcdefghijk", [response(403), response(200, player("UNPLAYABLE", "Not available in your country"))], "region_blocked"),
    ("youtube", "https://www.youtube.com/watch?v=abcdefghijk", [response(401), response(200, player("UNPLAYABLE", "Blocked in this region"))], "region_blocked"),
    ("youtube", "https://www.youtube.com/watch?v=abcdefghijk", [response(401), response(200, player("OK"))], "available"),
    ("youtube", "https://www.youtube.com/watch?v=abcdefghijk", [response(403), response(200, player("ERROR", "Video unavailable"))], "deleted"),
    ("youtube", "https://www.youtube.com/watch?v=abcdefghijk", [response(401), response(200, player("LOGIN_REQUIRED", "Sign in to confirm your age"))], "unknown"),
    ("youtube", "https://www.youtube.com/watch?v=abcdefghijk", [response(403), response(200, b"consent page")], "unknown"),
    ("youtube", "https://www.youtube.com/watch?v=abcdefghijk", [response(401), response(403)], "unknown"),
    ("youtube", "https://www.youtube.com/watch?v=abcdefghijk", [response(500)], "unknown"),
    ("x", "https://x.com/user/status/123", [response(404)], "deleted"),
    ("twitter", "https://twitter.com/user/status/123", [response(403)], "private"),
    ("x", "https://x.com/user/status/123", [response(200)], "available"),
    ("x", "https://x.com/user/status/123", [response(500)], "unknown"),
    ("reddit", "https://www.reddit.com/r/test/comments/abc123/title", [response(200, reddit(removed_by_category="moderator"))], "deleted"),
    ("reddit", "https://www.reddit.com/comments/abc123", [response(200, reddit(author="[deleted]"))], "deleted"),
    ("reddit", "https://www.reddit.com/comments/abc123", [response(200, reddit(selftext="[removed]"))], "deleted"),
    ("reddit", "https://www.reddit.com/comments/abc123", [response(200, reddit(selftext="[deleted]"))], "deleted"),
    ("reddit", "https://www.reddit.com/comments/abc123", [response(200, reddit())], "available"),
    ("reddit", "https://redd.it/abc123", [response(404)], "deleted"),
    ("reddit", "https://www.reddit.com/comments/abc123", [response(403, {"reason": "private"})], "private"),
    ("reddit", "https://www.reddit.com/comments/abc123", [response(403, {"reason": "blocked"})], "unknown"),
    ("reddit", "https://www.reddit.com/comments/abc123", [response(403, b"<html>private?</html>")], "unknown"),
    ("reddit", "https://www.reddit.com/comments/abc123", [response(200, b"{")], "unknown"),
    ("web", "https://example.com/item", [response(404)], "deleted"),
    ("web", "https://example.com/item", [response(410)], "deleted"),
    ("web", "https://example.com/item", [response(451)], "region_blocked"),
    ("web", "https://example.com/item", [response(403)], "unknown"),
    ("web", "https://example.com/item", [response(401)], "unknown"),
    ("web", "https://example.com/item", [response(500)], "unknown"),
    ("web", "https://example.com/item", [response(204)], "available"),
    ("other", "https://example.com/item", [response(405), response(206)], "available"),
    ("web", "https://example.com/item", [response(501), response(410)], "deleted"),
    ("podcast", "https://show.example/episode", [response(200)], "available"),
    ("podcast", "https://show.example/episode", [response(410)], "deleted"),
    ("podcast", "https://show.example/episode", [response(405)], "unknown"),
])
def test_checker_mapping(idx, platform, url, answers, expected):
    save(idx, platform=platform, url=url)
    fetch = Fetch(*answers)
    summary = run(idx, fetch)
    row = idx.availability_record("item")
    assert summary["requests"] == len(answers)
    assert summary["checked"] == 1 and not summary["aborted"]
    assert row["http_status"] == answers[-1][0]
    assert row["status"] == ("unknown" if expected in availability.GONE else expected)
    assert row["pending_status"] == (expected if expected in availability.GONE else None)
    assert all(c.timeout == 10 and c.max_bytes <= 512 * 1024 for c in fetch.calls)
    assert all(c.headers["User-Agent"] == availability.USER_AGENT for c in fetch.calls)
    if platform in ("other", "web", "podcast"):
        assert fetch.calls[0].method == "HEAD"
        if len(answers) == 2:
            assert fetch.calls[1].method == "GET"
            assert fetch.calls[1].headers["Range"] == "bytes=0-0"
            assert fetch.calls[1].max_bytes == 1
    elif platform == "youtube":
        first = urlsplit(fetch.calls[0].url)
        assert first.netloc == "www.youtube.com" and first.path == "/oembed"
        assert parse_qs(first.query) == {"url": ["https://www.youtube.com/watch?v=abcdefghijk"], "format": ["json"]}
        if len(answers) == 2:
            assert fetch.calls[1].url == "https://www.youtube.com/watch?v=abcdefghijk"
    elif platform in ("x", "twitter"):
        assert fetch.calls[0].url.startswith("https://publish.twitter.com/oembed?")
        assert parse_qs(urlsplit(fetch.calls[0].url).query) == {"url": [url], "omit_script": ["1"]}
    else:
        assert fetch.calls[0].url == "https://www.reddit.com/comments/abc123.json?limit=1&raw_json=1"


@pytest.mark.parametrize("url,checker", [("https://youtu.be/abcdefghijk", "youtube"),
    ("https://x.com/user/status/123", "x"), ("https://www.reddit.com/comments/abc123", "reddit"),
    ("https://youtube.com.example.com/item", "web")])
def test_checker_uses_url_when_platform_is_missing(idx, url, checker):
    save(idx, platform=None, url=url)
    run(idx, Fetch(response(200, reddit())))
    assert idx.availability_record("item")["checker"] == checker


@pytest.mark.parametrize("meta,expected", [
    ({"url": "https://show.example/page", "audio_url": "https://cdn.example/audio.mp3"}, "https://cdn.example/audio.mp3"),
    ({"url": None, "audio_url": "https://cdn.example/audio.mp3"}, "https://cdn.example/audio.mp3"),
    ({"url": None, "episode_page_url": "https://show.example/page"}, "https://show.example/page"),
])
def test_podcast_prefers_audio_and_supports_legacy_metadata(idx, meta, expected):
    save(idx, platform="podcast", **meta)
    fetch = Fetch(response(200))
    assert run(idx, fetch)["checked"] == 1
    assert fetch.calls[0].method == "HEAD" and fetch.calls[0].url == expected


def test_confirmation_requires_matching_observation_at_least_twenty_hours_later(idx):
    save(idx)
    run(idx, Fetch(response(200)))
    first = T0 + timedelta(days=7)
    summary = run(idx, Fetch(response(404)), first)
    row = idx.availability_record("item")
    assert row["status"] == "available" and row["pending_status"] == "deleted"
    assert row["pending_since"] == iso(first) and row["next_check_at"] == iso(first + timedelta(days=1))
    assert row["gone_since"] is None and summary["newly_gone"] == []

    early = first + timedelta(hours=19)
    idx.record_availability("item", next_check_at=iso(early))
    run(idx, Fetch(response(404)), early)
    assert idx.availability_record("item")["status"] == "available"
    confirm = first + timedelta(hours=20)
    idx.record_availability("item", next_check_at=iso(confirm))
    summary = run(idx, Fetch(response(404)), confirm)
    row = idx.availability_record("item")
    assert row["status"] == "deleted" and row["pending_status"] is None
    assert row["gone_since"] == row["status_changed_at"] == iso(confirm)
    assert summary["confirmed_gone"] == 1 and summary["newly_gone"] == ["item"]
    assert row["next_check_at"] == iso(confirm + timedelta(days=7))


def test_different_gone_observation_restarts_confirmation_and_preserves_original_gone_since(idx):
    save(idx, platform="x", url="https://x.com/user/status/123")
    run(idx, Fetch(response(404)))
    run(idx, Fetch(response(403)), T0 + timedelta(days=1))
    row = idx.availability_record("item")
    assert row["status"] == "unknown" and row["pending_status"] == "private"
    assert row["pending_since"] == iso(T0 + timedelta(days=1))
    run(idx, Fetch(response(403)), T0 + timedelta(days=2))
    original = idx.availability_record("item")["gone_since"]
    run(idx, Fetch(response(404)), T0 + timedelta(days=9))
    summary = run(idx, Fetch(response(404)), T0 + timedelta(days=10))
    row = idx.availability_record("item")
    assert row["status"] == "deleted" and row["gone_since"] == original
    assert row["status_changed_at"] == iso(T0 + timedelta(days=10))
    assert summary["confirmed_gone"] == 1 and summary["newly_gone"] == []
    summary = run(idx, Fetch(response(404)), T0 + timedelta(days=17))
    assert summary["confirmed_gone"] == 0
    assert idx.availability_record("item")["status_changed_at"] == row["status_changed_at"]


@pytest.mark.parametrize("confirmed", [False, True])
def test_available_clears_pending_and_recovers_confirmed_gone(idx, confirmed):
    save(idx)
    run(idx, Fetch(response(404)))
    if confirmed:
        run(idx, Fetch(response(404)), T0 + timedelta(days=1))
    run(idx, Fetch(response(200)), T0 + timedelta(days=8))
    row = idx.availability_record("item")
    assert row["status"] == "available"
    assert row["pending_status"] is row["pending_since"] is row["gone_since"] is None
    assert row["consecutive_errors"] == 0
    assert row["status_changed_at"] == iso(T0 + timedelta(days=8))


def test_unknown_and_transport_errors_keep_confirmed_status_and_back_off_after_three(idx):
    save(idx)
    idx.record_availability("item", status="private", gone_since=iso(T0 - timedelta(days=2)),
                            status_changed_at=iso(T0 - timedelta(days=2)))
    for n, answer in enumerate([response(403), TimeoutError("offline"), response(500)]):
        moment = T0 + timedelta(days=n)
        run(idx, Fetch(answer), moment)
        row = idx.availability_record("item")
        assert row["status"] == "private" and row["gone_since"] == iso(T0 - timedelta(days=2))
        assert row["consecutive_errors"] == n + 1 and row["last_checked_at"] == iso(moment)
        assert row["next_check_at"] == iso(moment + timedelta(days=7 if n == 2 else 1))
        assert row["http_status"] == (None if n == 1 else answer[0])


@pytest.mark.parametrize("retry,hours", [("7200", 2), ("10", 1), ("-20", 1),
    ("9999999", 48), (format_datetime(T0 + timedelta(hours=3), usegmt=True), 3),
    (format_datetime(T0 - timedelta(days=1), usegmt=True), 1)])
def test_retry_after_and_host_skip(idx, retry, hours):
    save(idx, "a")
    save(idx, "b", url="https://example.com/second")
    save(idx, "c", url="https://other.example/third")
    fetch = Fetch(response(429, headers={"Retry-After": retry}), response(200))
    summary = run(idx, fetch)
    assert summary["requests"] == 2 and summary["checked"] == 1
    assert summary["backed_off_hosts"] == ["example.com"]
    assert idx.availability_host("example.com")["backoff_until"] == iso(T0 + timedelta(hours=hours))
    assert idx.availability_record("a") == idx.availability_record("b") == {}
    assert [row["video_id"] for row in idx.availability_due(iso(), 25)] == ["a", "b"]
    skipped = run(idx, Fetch(), T0 + timedelta(minutes=30))
    assert skipped["requests"] == 0 and skipped["backed_off_hosts"] == ["example.com"]


@pytest.mark.parametrize("code", [429, 503])
def test_exponential_backoff_persists_and_caps_at_48_hours(idx, code):
    save(idx)
    now = T0
    for strike, hours in enumerate([1, 2, 4, 8, 16, 32, 48, 48], start=1):
        run(idx, Fetch(response(code, headers={"Retry-After": "invalid"})), now)
        host = idx.availability_host("example.com")
        assert host["strikes"] == strike
        assert host["backoff_until"] == iso(now + timedelta(hours=hours))
        now += timedelta(hours=hours)
    run(idx, Fetch(response(200)), now)
    host = idx.availability_host("example.com")
    assert host["strikes"] == 0 and host["backoff_until"] is None


def test_backoff_during_fallback_keeps_item_due(idx):
    save(idx, platform="youtube", url="https://youtu.be/abcdefghijk")
    summary = run(idx, Fetch(response(401), response(503)))
    assert summary["requests"] == 2 and summary["checked"] == 0
    assert idx.availability_record("item") == {}
    later = T0 + timedelta(hours=2)
    run(idx, Fetch(response(401), response(503)), later)
    host = idx.availability_host("www.youtube.com")
    assert host["strikes"] == 2
    assert host["backoff_until"] == iso(later + timedelta(hours=2, seconds=2))


@pytest.mark.parametrize("requested,expected", [(1, 1), (25, 25), (100, 25), (0, 0)])
def test_request_cap(idx, requested, expected):
    for n in range(30):
        save(idx, f"item{n:02}")
    fetch = Fetch(*[response(200) for _ in range(expected)])
    summary = run(idx, fetch, max_requests=requested)
    assert summary["requests"] == summary["checked"] == expected
    assert len(idx.availability_due(iso(), 50)) == 30 - expected


def test_youtube_fallback_consumes_budget_and_incomplete_item_stays_due(idx):
    for n in range(13):
        save(idx, f"item{n:02}", platform="youtube", url="https://youtu.be/abcdefghijk")
    fetch = Fetch(*([response(401), response(200, player("OK"))] * 12 + [response(401)]))
    summary = run(idx, fetch)
    assert summary["requests"] == 25 and summary["checked"] == 12
    assert idx.availability_record("item12") == {}


def test_generic_fallback_also_consumes_budget(idx):
    save(idx)
    summary = run(idx, Fetch(response(405)), max_requests=1)
    assert summary["requests"] == 1 and summary["checked"] == 0
    assert idx.availability_record("item") == {}


def test_same_host_spacing_uses_fake_sleep_and_persisted_last_request(idx):
    for n in range(3):
        save(idx, str(n))
    waits = []
    idx.set_availability_host("example.com", last_request_at=iso(T0 - timedelta(seconds=1)))
    summary = availability.run_once(idx, fetch=Fetch(*[response(200)] * 3), now=T0, sleep=waits.append)
    assert summary["requests"] == 3 and waits == [1.0, 2.0, 2.0]
    assert idx.availability_host("example.com")["last_request_at"] == iso(T0 + timedelta(seconds=5))


def test_redirects_are_counted_paced_and_checked_on_destination_host(idx):
    save(idx)
    waits = []
    fetch = Fetch(response(302, headers={"Location": "/moved"}),
                  response(301, headers={"Location": "https://cdn.example/final"}), response(200))
    summary = availability.run_once(idx, fetch=fetch, now=T0, sleep=waits.append)
    assert summary["requests"] == 3 and summary["checked"] == 1
    assert waits == [2.0]
    assert [call.method for call in fetch.calls] == ["HEAD"] * 3
    assert fetch.calls[-1].url == "https://cdn.example/final"
    assert idx.availability_record("item")["status"] == "available"


def test_redirect_destination_in_backoff_and_redirect_cap_leave_items_due(idx):
    save(idx)
    idx.set_availability_host("cdn.example", backoff_until=iso(T0 + timedelta(hours=1)), strikes=1)
    redirect = response(302, headers={"Location": "https://cdn.example/final"})
    summary = run(idx, Fetch(redirect))
    assert summary["requests"] == 1 and summary["backed_off_hosts"] == ["cdn.example"]
    assert idx.availability_record("item") == {}
    summary = run(idx, Fetch(redirect), T0 + timedelta(hours=2), max_requests=1)
    assert summary["requests"] == 1 and summary["checked"] == 0


def test_skipped_hosts_do_not_starve_later_candidate_pages(idx):
    for n in range(30):
        save(idx, f"a{n:02}")
    save(idx, "z", url="https://other.example/item")
    idx.set_availability_host("example.com", backoff_until=iso(T0 + timedelta(hours=1)))
    summary = run(idx, Fetch(response(200)))
    assert summary["requests"] == summary["checked"] == 1
    assert idx.availability_record("z")["status"] == "available"


def test_offline_abort_leaves_all_statuses_untouched_including_earlier_success(idx):
    for n in range(7):
        save(idx, str(n))
        idx.record_availability(str(n), status="deleted", gone_since=iso(T0 - timedelta(days=2)),
                                status_changed_at=iso(T0 - timedelta(days=2)),
                                pending_status="private", pending_since=iso(T0 - timedelta(days=1)))
    before = idx.availability_for([str(n) for n in range(7)])
    fetch = Fetch(response(200), *[TimeoutError("offline") for _ in range(5)])
    summary = run(idx, fetch)
    assert summary["aborted"] and summary["requests"] == summary["checked"] == 6
    assert summary["confirmed_gone"] == 0 and summary["newly_gone"] == []
    for video_id, original in before.items():
        row = idx.availability_record(video_id)
        assert row["status"] == original["status"]
        assert row["gone_since"] == original["gone_since"]
        assert row["status_changed_at"] == original["status_changed_at"]
        assert row["pending_status"] == "private"
    assert idx.availability_record("6")["last_checked_at"] is None
    assert idx.availability_record("1")["consecutive_errors"] == 1
    assert json.loads(idx.availability_run_state()["last_run_json"]) == summary


def test_success_resets_consecutive_transport_errors(idx):
    for n in range(10):
        save(idx, f"item{n:02}")
    answers = [OSError("offline")] * 4 + [response(200)] + [OSError("offline")] * 4 + [response(200)]
    summary = run(idx, Fetch(*answers))
    assert not summary["aborted"] and summary["requests"] == summary["checked"] == 10


def test_due_order_filters_and_weekly_recheck(idx):
    for video_id in ("never", "unobserved", "old", "recent", "future", "trashed"):
        save(idx, video_id)
    idx.record_availability("unobserved")
    idx.record_availability("old", last_checked_at=iso(T0 - timedelta(days=8)), next_check_at=iso(T0))
    idx.record_availability("recent", last_checked_at=iso(T0 - timedelta(days=7)), next_check_at=iso(T0))
    idx.record_availability("future", next_check_at=iso(T0 + timedelta(seconds=1)))
    with idx.write_transaction() as conn:
        conn.execute("UPDATE yoinks SET deleted_at=? WHERE video_id='trashed'", (iso(),))
    save(idx, "note", platform="note")
    save(idx, "image", platform="image")
    save(idx, "local", url="file:///example/item")
    save(idx, "empty", url=None)
    save(idx, "bad_json")
    with idx.write_transaction() as conn:
        conn.execute("UPDATE yoinks SET metadata_json='{' WHERE video_id='bad_json'")
    assert [r["video_id"] for r in idx.availability_due(iso(), 20)] == ["never", "unobserved", "old", "recent"]
    assert [r["video_id"] for r in idx.availability_due(iso(), 1)] == ["never"]
    assert set(idx.availability_due(iso(), 1)[0]) == {"video_id", "platform", "source_type", "metadata_json"}
    run(idx, Fetch(*[response(200)] * 4))
    assert [r["video_id"] for r in idx.availability_due(iso(T0 + timedelta(days=7) - timedelta(seconds=1)), 20)] == ["future"]
    assert len(idx.availability_due(iso(T0 + timedelta(days=7)), 20)) == 5


def test_availability_for_is_one_query_and_upsert_preserves_state(idx):
    record = save(idx, "a")
    save(idx, "b")
    run(idx, Fetch(response(200), response(404)))
    sql = []
    idx._conn.set_trace_callback(sql.append)
    found = idx.availability_for(["a", "b", "missing", "a"])
    idx._conn.set_trace_callback(None)
    assert len(sql) == 1 and " IN (" in sql[0]
    assert set(found) == {"a", "b"}
    assert set(found["a"]) == {"status", "last_checked_at", "gone_since", "status_changed_at"}
    assert idx.availability_for([]) == {}
    idx.upsert_yoink({**record, "title": "Updated"})
    assert idx.availability_for(["a"])["a"] == found["a"]
    idx.delete_yoink("a")
    assert idx.availability_record("a") == {}
    idx.record_availability("a", status="available")  # Completed HTTP check after a hard delete.
    assert idx.availability_record("a") == {}


@pytest.mark.parametrize("now_iso", ["2026-11-03T12:00:00", "2026-11-03T12:00:00+00:00",
                                    "2026-11-03T12:00:00Z"])
def test_due_compares_utc_instants_across_iso_formats(idx, now_iso):
    save(idx)
    idx.record_availability("item", next_check_at=iso())
    assert [row["video_id"] for row in idx.availability_due(now_iso, 25)] == ["item"]


def test_summary_counts_only_live_tracked_rows_and_rolling_thirty_days(idx):
    for vid, status, age in [("a", "available", None), ("d", "deleted", 1), ("p", "private", 30),
                              ("r", "region_blocked", 31), ("f", "deleted", -1), ("u", "unknown", None),
                              ("trash", "deleted", 1)]:
        save(idx, vid)
        idx.record_availability(vid, status=status, last_checked_at=iso(),
                                gone_since=iso(T0 - timedelta(days=age)) if age is not None else None)
    save(idx, "never")
    with idx.write_transaction() as conn:
        conn.execute("UPDATE yoinks SET deleted_at=? WHERE video_id='trash'", (iso(),))
    summary = idx.availability_summary(iso())
    assert summary == {"gone_total": 4, "gone_this_month": 2, "checked_total": 6,
                       "by_status": {"available": 1, "deleted": 2, "private": 1, "region_blocked": 1, "unknown": 1}}
    assert idx.gone_video_ids() == {"d", "p", "r", "f"}


def test_migration_upgrade_rerun_constraints_and_preserved_saved_content(tmp_path, monkeypatch):
    migrations = index_mod._discover_migrations()
    assert not any(version == 29 for version, _ in migrations)
    assert any(version == 33 for version, _ in migrations)
    path = tmp_path / "upgrade.db"
    with monkeypatch.context() as patch:
        patch.setattr(index_mod, "_discover_migrations", lambda: [(v, p) for v, p in migrations if v < 33])
        with index_mod.Index.open(path) as old:
            save(old)
            old.upsert_yoink(old.get_yoink("item"), content="preserved transcript")
            before = old.get_yoink("item")
    with index_mod.Index.open(path) as upgraded:
        assert upgraded.schema_version() == index_mod.latest_schema_version()
        assert upgraded.get_yoink("item") == before
        assert upgraded._conn.execute("SELECT content FROM yoinks_fts WHERE video_id='item'").fetchone()[0] == "preserved transcript"
        upgraded.record_availability("item", status="available")
        migration = next(p for v, p in migrations if v == 33)
        # Simulate a replay after tables were created but the version stamp was lost.
        with upgraded.write_transaction() as conn:
            conn.execute("DELETE FROM schema_version WHERE version=33")
        assert index_mod._run_migrations(upgraded._conn) == index_mod.latest_schema_version()
        assert upgraded.availability_record("item")["status"] == "available"
        for fields in ({"status": "wrong"}, {"pending_status": "available"}):
            with pytest.raises(sqlite3.IntegrityError):
                upgraded.record_availability("item", **fields)
        with pytest.raises(sqlite3.IntegrityError), upgraded.write_transaction() as conn:
            conn.execute("INSERT INTO source_availability_state(singleton) VALUES(2)")
        assert "CREATE TABLE IF NOT EXISTS" in migration.read_text()
        assert upgraded._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_run_state_interval_and_utc_clock(idx):
    assert availability.is_due_to_run(idx, T0)
    save(idx)
    local = T0.astimezone(timezone(timedelta(hours=-8)))
    summary = run(idx, Fetch(response(200)), now=lambda: local)
    state = idx.availability_run_state()
    assert state["last_run_started_at"] == state["last_run_finished_at"] == iso()
    assert json.loads(state["last_run_json"]) == summary
    assert not availability.is_due_to_run(idx, T0 + timedelta(minutes=59, seconds=59))
    assert availability.is_due_to_run(idx, T0 + timedelta(minutes=60))
    idx.set_availability_run_state(last_run_started_at=iso(T0 + timedelta(hours=2)), last_run_finished_at=None)
    assert not availability.is_due_to_run(idx, T0 + timedelta(hours=2, minutes=30))


@pytest.mark.parametrize("method,code", [("GET", 200), ("GET", 404), ("HEAD", 403)])
def test_default_fetch_uses_safe_opener_and_closes_bounded_response(monkeypatch, method, code):
    import source_subscriptions
    seen = []
    stream = BytesIO(b"payload longer than budget")
    error = HTTPError("https://example.com/item", code, "test", {"Retry-After": "3600"}, stream)

    def open_safe(url, **kwargs):
        seen.append((url, kwargs))
        if code >= 400:
            raise error
        return error

    monkeypatch.setattr(source_subscriptions, "public_http_open", open_safe)
    actual = availability.default_fetch(method, "https://example.com/item", {}, 10, 7)
    assert actual == (code, {"Retry-After": "3600"}, b"payload" if method == "GET" else b"")
    assert stream.closed
    assert seen[0][1] == {"method": method, "headers": {"User-Agent": availability.USER_AGENT},
                          "timeout": 10, "follow_redirects": False}
    assert availability.USER_AGENT == f"Uoink/{Path(availability.__file__).with_name('VERSION').read_text().strip()} availability check (+https://uoink.app)"


def test_safe_opener_supports_head_without_bypassing_admission(monkeypatch):
    import source_subscriptions as ss
    admitted, opened, handlers = [], [], []
    def admit(url):
        admitted.append(url)
        return url, "example.com", ("93.184.216.34",)
    def build(*items):
        handlers.extend(items)
        return SimpleNamespace(open=lambda req, timeout: opened.append((req, timeout)) or "response")
    monkeypatch.setattr(ss, "_admit_public_http_url", admit)
    monkeypatch.setattr(ss.urllib.request, "build_opener", build)
    assert ss.public_http_open("https://example.com/item", method="HEAD", follow_redirects=False) == "response"
    assert admitted == ["https://example.com/item"] and opened[0][0].get_method() == "HEAD"
    assert next(h for h in handlers if isinstance(h, ss._BoundedRedirectHandler)).follow_redirects is False


@pytest.fixture
def helper(tmp_path, monkeypatch):
    # Import-time paths are isolated even when this file runs by itself.
    if "server" not in sys.modules:
        profile = tmp_path / "helper"
        profile.mkdir()
        monkeypatch.setenv("UOINK_ISOLATED_PROFILE", str(profile))
        monkeypatch.setenv("UOINK_ISOLATED_PORT", "18178")
        monkeypatch.delenv("UOINK_ISOLATED_APP_DIR", raising=False)
    import server
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: "")
    monkeypatch.setattr(server, "_get_saved_scrapecreators_key", lambda: "")
    monkeypatch.setattr(server, "_get_saved_relay_token", lambda: "")
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {})
    monkeypatch.setattr(server, "_reliability_model_status", lambda *args: {})
    monkeypatch.setattr(server.whisper_runner, "is_whisperx_available", lambda: False)
    monkeypatch.setattr(server, "_source_availability_lock", threading.Lock())
    return server


def test_setting_defaults_normalizes_is_public_and_saves_as_boolean(helper, monkeypatch):
    key = "source_availability_check_enabled"
    assert helper._default_settings()[key] is True
    for value, expected in [(True, True), (False, False), (0, False), (1, True), (None, False)]:
        assert helper._normalize_settings({key: value})[key] is expected
    assert helper._normalize_settings({})[key] is True
    assert helper._public_settings({"keep_media": False})[key] is True
    assert helper._public_settings({key: False})[key] is False
    written, replies = [], []
    handler = object.__new__(helper.Handler)
    handler._send_json = lambda status, body: replies.append((status, body))
    monkeypatch.setattr(helper, "_read_settings", helper._default_settings)
    monkeypatch.setattr(helper, "_write_settings", written.append)
    handler._handle_settings_post({key: False})
    assert written[-1][key] is False and replies[-1][1]["settings"][key] is False
    handler._handle_settings_post({key: "false"})
    assert replies[-1] == (400, {"ok": False, "error": f"{key} must be boolean"})


@pytest.mark.parametrize("reason", ["setting", "environment", "startup", "busy", "not_due"])
def test_tick_does_nothing_when_gated(helper, idx, monkeypatch, reason):
    monkeypatch.delenv("UOINK_DISABLE_AVAILABILITY_CHECK", raising=False)
    monkeypatch.setattr(helper, "_HELPER_STARTED_MONOTONIC", helper.time.monotonic() - (599 if reason == "startup" else 601))
    monkeypatch.setattr(helper, "_read_settings", lambda: {"source_availability_check_enabled": reason != "setting"})
    monkeypatch.setattr(helper, "_get_index", lambda: idx)
    monkeypatch.setattr(availability, "is_due_to_run", lambda *args: reason != "not_due")
    monkeypatch.setattr(availability, "run_once", lambda *args: pytest.fail("run_once must not run"))
    monkeypatch.setattr(helper.threading, "Thread", lambda **kwargs: pytest.fail("No thread should start"))
    if reason == "environment":
        monkeypatch.setenv("UOINK_DISABLE_AVAILABILITY_CHECK", "1")
    if reason == "busy":
        helper._source_availability_lock.acquire()
    try:
        helper._source_availability_tick()
    finally:
        if reason == "busy":
            helper._source_availability_lock.release()


def test_tick_starts_one_short_lived_worker_and_releases_lock_on_failure(helper, idx, monkeypatch, caplog):
    monkeypatch.delenv("UOINK_DISABLE_AVAILABILITY_CHECK", raising=False)
    monkeypatch.setattr(helper, "_HELPER_STARTED_MONOTONIC", helper.time.monotonic() - 601)
    monkeypatch.setattr(helper, "_read_settings", lambda: {})
    monkeypatch.setattr(helper, "_get_index", lambda: idx)
    threads, runs = [], []
    def thread(**kwargs):
        threads.append(kwargs)
        return SimpleNamespace(start=lambda: None)
    def check(index):
        runs.append(index)
        raise RuntimeError("test failure")
    monkeypatch.setattr(helper.threading, "Thread", thread)
    monkeypatch.setattr(availability, "run_once", check)
    helper._source_availability_tick()
    helper._source_availability_tick()
    assert len(threads) == 1 and threads[0]["name"] == "source-availability" and threads[0]["daemon"]
    threads[0]["target"]()  # Synchronous fake worker; no background work.
    assert runs == [idx] and not helper._source_availability_lock.locked()
    assert "source availability check crashed" in caplog.text


def test_tick_releases_lock_if_thread_cannot_start(helper, idx, monkeypatch, caplog):
    monkeypatch.delenv("UOINK_DISABLE_AVAILABILITY_CHECK", raising=False)
    monkeypatch.setattr(helper, "_HELPER_STARTED_MONOTONIC", helper.time.monotonic() - 601)
    monkeypatch.setattr(helper, "_read_settings", lambda: {})
    monkeypatch.setattr(helper, "_get_index", lambda: idx)
    def fail(**kwargs):
        raise RuntimeError("cannot start")
    monkeypatch.setattr(helper.threading, "Thread", fail)
    helper._source_availability_tick()
    assert not helper._source_availability_lock.locked()
    assert "source availability tick crashed" in caplog.text


def test_existing_scheduler_calls_availability_after_podcast_tick(helper, monkeypatch):
    events, threads = [], []
    class StopLoop(BaseException):
        pass
    def sleep(_):
        raise StopLoop
    def thread(**kwargs):
        threads.append(kwargs)
        return SimpleNamespace(start=lambda: None)
    monkeypatch.setattr(helper, "_podcast_feed_scheduler_tick", lambda: events.append("podcasts"))
    monkeypatch.setattr(helper, "_source_availability_tick", lambda: events.append("availability"))
    monkeypatch.setattr(helper.time, "sleep", sleep)
    monkeypatch.setattr(helper.threading, "Thread", thread)
    helper._start_podcast_feed_scheduler_thread()
    with pytest.raises(StopLoop):
        threads[0]["target"]()
    assert events == ["podcasts", "availability"] and len(threads) == 1

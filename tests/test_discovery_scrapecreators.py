"""T5: pinned OpenAPI examples, mocked transport, tmp_path storage only."""
from __future__ import annotations

import datetime as dt
import io
import json
import socket
import sqlite3
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import discovery_scrapecreators as sc
import index
import server


FIXTURES = Path(__file__).parent / "fixtures" / "scrapecreators"
KEY = "synthetic-sc-key-never-a-real-credential"
NOW = dt.datetime(2026, 10, 16, 12, tzinfo=dt.timezone.utc).timestamp()
ARGS = {"mode": "creator", "platform": "youtube", "handle": "@fixture"}


@pytest.fixture(autouse=True)
def no_network_or_real_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("discovery tests must not use network or real credentials")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(server, "_keyring", SimpleNamespace(
        get_password=forbidden, set_password=forbidden, delete_password=forbidden))
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: "")
    monkeypatch.setattr(sc, "_last_sent_at", None)


def fixture(name="youtube_channel_videos"):
    return json.loads((FIXTURES / (name + ".json")).read_text(encoding="utf-8"))["response"]


class Clock:
    def __init__(self):
        self.value = NOW
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, delay):
        self.sleeps.append(delay)
        self.value += delay


class FakeKeyring:
    def __init__(self):
        self.values, self.calls = {}, []

    def get_password(self, service, username):
        self.calls.append(("get", service, username))
        return self.values.get((service, username))

    def set_password(self, service, username, key):
        self.calls.append(("set", service, username))
        self.values[service, username] = key

    def delete_password(self, service, username):
        self.calls.append(("delete", service, username))
        del self.values[service, username]


@pytest.fixture
def rig(tmp_path, monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    index._run_migrations(conn)
    idx = index.Index(conn, tmp_path / "unused.db")
    settings = server._default_settings()
    settings.update(scrapecreators_enabled=True, scrapecreators_agent_calls_enabled=True)
    clock = Clock()
    replies = [(200, fixture())]
    calls = []

    def send(method, url, headers, timeout, max_bytes):
        calls.append((method, url, headers.copy(), timeout, max_bytes, clock()))
        status, payload = replies.pop(0)
        if isinstance(payload, Exception):
            raise payload
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return sc.TransportResponse(status, body, url)

    backend = SimpleNamespace(
        DATA_ROOT=tmp_path, VERSION="0.0.0", _normalize_video_url=server._normalize_video_url,
        _read_settings=lambda: settings.copy(), _get_saved_scrapecreators_key=lambda: KEY,
        _get_index=lambda: idx, _now_iso=lambda: server._now_iso(),
        _mark_scrapecreators_key_invalid=lambda invalid=True, expected_key=None: settings.update(scrapecreators_key_invalid=invalid))
    service = sc.DiscoveryService(backend, transport=send, clock=clock, monotonic=clock, sleep=clock.sleep)
    yield SimpleNamespace(service=service, backend=backend, idx=idx, conn=conn, settings=settings,
                          clock=clock, replies=replies, calls=calls, root=tmp_path)
    conn.close()


def run(rig, **args):
    return rig.service.discover_candidates({**ARGS, "confirm_credits": 1, **args})


def reason(result):
    assert result["ok"] is False
    return result["error"]["details"].get("reason")


def intent(rig, args=None, *, origin="http://127.0.0.1:5180", session="fixture-session", tool="discover_candidates"):
    return rig.service.mint_intent({"confirmed": True, "operation": {
        "tool": tool, "arguments": args if args is not None else ARGS}}, origin=origin, session_hash=session)


def test_default_off_settings_and_no_plaintext():
    defaults = server._default_settings()
    assert defaults["scrapecreators_enabled"] is False
    assert defaults["scrapecreators_agent_calls_enabled"] is False
    assert defaults["scrapecreators_daily_credit_cap"] == 25
    clean = server._normalize_settings({"scrapecreators_key": KEY,
                                       "scrapecreators_enabled": "true",
                                       "scrapecreators_agent_calls_enabled": 1,
                                       "scrapecreators_daily_credit_cap": True})
    assert "scrapecreators_key" not in clean
    assert clean["scrapecreators_enabled"] is False
    assert clean["scrapecreators_agent_calls_enabled"] is False
    assert clean["scrapecreators_daily_credit_cap"] == 25


@pytest.mark.parametrize("gate", ["disabled", "missing_key", "cap", "agent", "invalid_key"])
def test_gates_refuse_without_transport(rig, gate):
    expected = {"disabled": "discovery_disabled", "missing_key": "scrapecreators_key_required",
                "cap": "daily_cap_reached", "agent": "user_intent_required", "invalid_key": "scrapecreators_key_invalid"}
    if gate == "disabled":
        rig.settings["scrapecreators_enabled"] = False
    elif gate == "missing_key":
        rig.backend._get_saved_scrapecreators_key = lambda: ""
    elif gate == "agent":
        rig.settings["scrapecreators_agent_calls_enabled"] = False
    elif gate == "invalid_key":
        rig.settings["scrapecreators_key_invalid"] = True
    else:
        rig.settings["scrapecreators_daily_credit_cap"] = 1
        rig.service._record(rig.idx, sc.BALANCE_ENDPOINT, rig.service._now(), cap=1)
    assert reason(run(rig)) == expected[gate]
    assert rig.calls == []


def test_plan_is_free_and_confirmation_is_exact(rig):
    rig.settings["scrapecreators_agent_calls_enabled"] = False
    assert rig.service.discover_candidates({**ARGS, "pages": 3}) == {
        "ok": True, "needs_confirmation": True, "credits_planned": 3, "credits_today": 0, "daily_cap": 25}
    assert reason(run(rig, pages=3, confirm_credits=1)) == "confirm_credits_mismatch"
    assert rig.calls == []


@pytest.mark.parametrize("bad", [
    {"pages": True}, {"pages": 4}, {"pages": 0}, {"pages": 1.0}, {"handle": "@"},
    {"handle": "x" * 101}, {"handle": "bad\nhandle"}, {"query": "extra"},
    {"mode": "keyword", "platform": "instagram"}, {"platform": "x"},
    {"mode": []}, {"platform": {}},
    {"channel_id": "bad"}, {"confirm_credits": True}, {"url": "https://evil.example"},
])
def test_arguments_rejected_before_settings_or_data(rig, bad):
    rig.backend._read_settings = Mock(side_effect=AssertionError("must not read settings"))
    result = run(rig, **bad)
    assert result["error"]["code"] == "invalid_request"
    rig.backend._read_settings.assert_not_called()
    assert rig.calls == []


def test_intent_authorizes_one_bound_call_and_replay_refuses(rig):
    rig.settings["scrapecreators_agent_calls_enabled"] = False
    token = intent(rig)["user_intent_token"]
    args = {**ARGS, "confirm_credits": 1, "user_intent_token": token}
    assert rig.service.discover_candidates(args, origin="http://127.0.0.1:5180", session_hash="fixture-session")["ok"]
    assert reason(rig.service.discover_candidates(args, origin="http://127.0.0.1:5180", session_hash="fixture-session")) == "invalid_user_intent"
    assert len(rig.calls) == 1


@pytest.mark.parametrize("mismatch", ["origin", "session", "operation", "expired"])
def test_intent_is_five_minutes_single_origin_and_operation_bound(rig, mismatch):
    rig.settings["scrapecreators_agent_calls_enabled"] = False
    token = intent(rig)["user_intent_token"]
    args = {**ARGS, "confirm_credits": 1, "user_intent_token": token}
    origin, session = "http://127.0.0.1:5180", "fixture-session"
    if mismatch == "origin":
        origin = "http://localhost:5180"
    elif mismatch == "session":
        session = "other-session"
    elif mismatch == "operation":
        args["handle"] = "other"
    else:
        rig.clock.value += 300
    assert reason(rig.service.discover_candidates(args, origin=origin, session_hash=session)) == "invalid_user_intent"
    assert rig.calls == []


def test_intent_mint_rate_limit_and_window(rig):
    for _ in range(30):
        assert intent(rig)["ok"]
    assert intent(rig)["error"]["code"] == "rate_limited"
    rig.clock.value += 60
    assert intent(rig)["ok"]
    assert rig.calls == []


@pytest.mark.parametrize("mode,platform,name,path,cursor", [
    ("creator", "tiktok", "tiktok_profile_videos", "/v3/tiktok/profile/videos", "max_cursor"),
    ("creator", "instagram", "instagram_reels", "/v1/instagram/user/reels", "max_id"),
    ("creator", "youtube", "youtube_channel_videos", "/v1/youtube/channel-videos", "continuationToken"),
    ("creator", "youtube_shorts", "youtube_channel_shorts", "/v1/youtube/channel/shorts", "continuationToken"),
    ("keyword", "tiktok", "tiktok_keyword", "/v1/tiktok/search/keyword", "cursor"),
    ("keyword", "youtube", "youtube_search", "/v1/youtube/search", "continuationToken"),
])
def test_endpoint_table_pagination_metrics_and_headers(rig, mode, platform, name, path, cursor):
    first = fixture(name)
    next_cursor = first[cursor]
    second = fixture(name)
    second[cursor] = None
    rig.replies[:] = [(200, first), (200, second)]
    args = {"mode": mode, "platform": platform, "pages": 2, "confirm_credits": 2,
            **({"handle": "@fixture"} if mode == "creator" else {"query": "fixture topic"})}
    result = rig.service.discover_candidates(args)
    assert result["ok"] and result["endpoint"] == path
    assert len(rig.calls) == 2 and result["credits_used"] == 2
    # YouTube search supplies one video and one short; repeated rows dedupe.
    expected_items = 2 if name == "youtube_search" else 1
    assert result["coverage"] == {"pages": 2, "items": expected_items, "truncated": False, "next_cursor_present": False}
    groups = {(b["platform"], b["source_type"]): b for b in result["baselines"]}
    assert len(groups) == expected_items
    assert result["baseline"] == (None if name == "youtube_search" else result["baselines"][0])
    for candidate in result["candidates"]:
        group = ("youtube" if candidate["platform"] == "youtube_shorts" else candidate["platform"],
                 "video" if candidate["platform"] == "youtube" else "short_video")
        baseline = groups[group]
        assert baseline["metric"] == "views" and baseline["median"] == candidate["metrics"]["views"]
        assert baseline["n"] == 1 and baseline["confidence"] == "Low"
        assert candidate["lift"] == candidate["metrics"]["views"] / baseline["median"] == 1
        assert candidate["label"] == "none"
    assert rig.clock.sleeps == [1]
    for method, url, headers, timeout, max_bytes, _ in rig.calls:
        assert method == "GET" and url.startswith(sc.BASE_URL + path + "?")
        params = parse_qs(urlparse(url).query)
        assert params["trim"] == ["true"] and KEY not in url and "%40fixture" not in url
        assert params["handle" if mode == "creator" else "query"] == ["fixture" if mode == "creator" else "fixture topic"]
        assert headers == {"x-api-key": KEY, "User-Agent": "Uoink/0.0.0"}
        assert timeout == 8 and max_bytes == 8 * 1024 * 1024
    assert cursor not in parse_qs(urlparse(rig.calls[0][1]).query)
    assert parse_qs(urlparse(rig.calls[1][1]).query)[cursor] == [str(next_cursor)]
    saved = list((rig.root / "discovery" / "runs" / "2026-10").glob("*.json"))
    assert len(saved) == 1 and json.loads(saved[0].read_text(encoding="utf-8")) == result
    assert KEY not in saved[0].read_text(encoding="utf-8") and "thumbnail" not in saved[0].read_text(encoding="utf-8")
    assert result["mode"] == mode and result["platform"] == platform
    field = "handle" if mode == "creator" else "query"
    assert result[field] == args[field].removeprefix("@")
    assert sc._run_scope(result) in saved[0].name


def test_channel_id_parameter_and_three_page_limit(rig):
    payload = fixture()
    rig.replies[:] = [(200, {**payload, "continuationToken": str(i)}) for i in range(1, 4)]
    result = rig.service.discover_candidates({"mode": "creator", "platform": "youtube", "channel_id": "UC" + "a" * 22,
                                              "pages": 3, "confirm_credits": 3})
    assert result["ok"] and len(rig.calls) == 3
    assert "channelId=UC" in rig.calls[0][1]
    assert result["channel_id"] == "UC" + "a" * 22
    assert result["candidates"][0]["author_handle"] == result["channel_id"]
    assert sc._run_scope(result) in result["run_id"]
    assert result["coverage"]["truncated"] and result["coverage"]["next_cursor_present"]


@pytest.mark.parametrize("mode,platform,name,video_id,author,metrics,duration,published", [
    ("creator", "tiktok", "tiktok_profile_videos", "7517114944362499342", "stoolpresidente",
     (559925, 59605, 587, 3424), 173.675, "2025-06-18T02:45:25+00:00"),
    ("creator", "instagram", "instagram_reels", "DKKtpqaxg0C", "jane",
     (1685367, 71768, 1096, None), 91.383, "2025-05-27T18:41:50+00:00"),
    ("creator", "youtube", "youtube_channel_videos", "5EWaxmWgQMI", "fixture",
     (110447, None, None, None), 2245, "2025-01-23T22:48:53.914000+00:00"),
    ("creator", "youtube_shorts", "youtube_channel_shorts", "VREVC0wXPfs", "fixture",
     (17066, 495, 2, None), 37, "2026-04-22T17:44:35+00:00"),
    ("keyword", "tiktok", "tiktok_keyword", "7268287584244124971", "thatgreygentlemanitdxz",
     (1282645, 481608, 187, 2721), 22.874, "2023-08-17T13:48:40+00:00"),
    ("keyword", "youtube", "youtube_search", "BzSzwqb-OEE", "UCoRR6OLuIZ2-5VxtnQIaN2w",
     (14860541, None, None, None), 254, "2023-05-28T17:08:46.499000+00:00"),
])
def test_documented_examples_map_exact_candidate_fields(rig, mode, platform, name, video_id,
                                                        author, metrics, duration, published):
    args = {"mode": mode, "platform": platform,
            **({"handle": "fixture"} if mode == "creator" else {"query": "fixture topic"})}
    payload = fixture(name)
    rows, cursor, truncated = sc.parse_candidates(payload, args, rig.backend)
    assert len(rows) == (2 if name == "youtube_search" else 1)
    assert cursor is not None and not truncated
    candidate = rows[0]
    assert candidate["video_id"] == video_id and candidate["author_handle"] == author
    assert candidate["platform"] == platform
    assert candidate["metrics"] == dict(zip(("views", "likes", "comments", "shares"), metrics))
    assert candidate["duration_s"] == duration and candidate["published_at"] == published
    source_rows = {"tiktok_profile_videos": "aweme_list", "instagram_reels": "items",
                   "tiktok_keyword": "search_item_list", "youtube_channel_shorts": "shorts"}
    original = payload[source_rows.get(name, "videos")][0]
    caption = original["desc"] if platform == "tiktok" else original["caption"]["text"] if platform == "instagram" else original["title"]
    assert candidate["caption"] == "".join(c for c in caption if c >= " ")[:300]
    expected_url = (f"https://www.tiktok.com/@{author}/video/{video_id}" if platform == "tiktok"
                    else server._normalize_video_url(original["url"])[0])
    assert candidate["url"] == expected_url
    assert "thumbnail" not in candidate


def test_youtube_search_shorts_and_channel_identifiers_match_playbook_authors(rig):
    rows, _, _ = sc.parse_candidates(fixture("youtube_search"),
                                    {"mode": "keyword", "platform": "youtube", "query": "running"}, rig.backend)
    assert [(r["video_id"], r["platform"], r["author_handle"]) for r in rows] == [
        ("BzSzwqb-OEE", "youtube", "UCoRR6OLuIZ2-5VxtnQIaN2w"),
        ("uMNvF-lSCHg", "youtube_shorts", "abbyandryan")]
    short = rows[1]
    assert short["metrics"] == {"views": 462705, "likes": None, "comments": None, "shares": None}
    assert short["duration_s"] == 44
    assert short["published_at"] == "2024-07-28T17:08:46.498000+00:00"


@pytest.mark.parametrize("mode,name,rows_key", [
    ("creator", "tiktok_profile_videos", "aweme_list"),
    ("keyword", "tiktok_keyword", "search_item_list"),
])
def test_tiktok_mismatched_url_uses_aweme_identity_for_library_and_saved_pick(rig, mode, name, rows_key):
    payload = fixture(name)
    row = payload[rows_key][0]
    wrong_id = "7545933721589910798"
    row["url"] = f"https://www.tiktok.com/@branttakes/video/{wrong_id}"
    expected_id = row["aweme_id"]
    expected_url = f"https://www.tiktok.com/@{row['author']['unique_id']}/video/{expected_id}"
    assert expected_id != wrong_id
    rig.idx.upsert_yoink({"video_id": expected_id, "slug": "captured", "title": "Captured",
                          "yoinked_at": "2026-10-15T12:00:00", "corpus_path": str(rig.root / "captured.md"),
                          "sidecar_path": str(rig.root / "captured.json")})
    rig.replies[:] = [(200, payload)]
    args = {"mode": mode, "platform": "tiktok", "confirm_credits": 1,
            **({"handle": "fixture"} if mode == "creator" else {"query": "fixture topic"})}
    result = rig.service.discover_candidates(args)
    assert result["ok"] and len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["video_id"] == expected_id and candidate["url"] == expected_url
    assert candidate["author_handle"] == row["author"]["unique_id"]
    assert candidate["metrics"]["views"] == row["statistics"]["play_count"]
    assert candidate["in_library"] and candidate["state"] == "captured"
    assert list(sc.recent_runs(rig.root, now=rig.service._now())) == [result]
    # Correct and mismatched URLs for the same aweme share one selection key.
    row["url"] = expected_url
    matching, _, _ = sc.parse_candidates(payload, args, rig.backend)
    assert matching[0]["key"] == candidate["key"]
    assert matching[0]["url"] == expected_url
    assert matching[0]["video_id"] == expected_id
    assert len(rig.calls) == 1


@pytest.mark.parametrize("mode,name,rows_key", [
    ("creator", "tiktok_profile_videos", "aweme_list"),
    ("keyword", "tiktok_keyword", "search_item_list"),
])
@pytest.mark.parametrize("bad_id", [None, "", "not-an-id", "123/video/456", True, 7517114944362499342])
def test_tiktok_missing_or_invalid_aweme_id_cannot_fall_back_to_url(rig, mode, name, rows_key, bad_id):
    payload = fixture(name)
    payload[rows_key][0]["aweme_id"] = bad_id
    args = {"mode": mode, "platform": "tiktok"}
    rows, _, _ = sc.parse_candidates(payload, args, rig.backend)
    assert rows == []


@pytest.mark.parametrize("author", [None, "", "bad/name", "bad?name", "bad#name"])
def test_tiktok_mismatched_url_without_safe_author_is_dropped(rig, author):
    payload = fixture("tiktok_profile_videos")
    payload["aweme_list"][0]["author"]["unique_id"] = author
    rows, _, _ = sc.parse_candidates(payload, {"mode": "creator", "platform": "tiktok"}, rig.backend)
    assert rows == []


def test_paginated_fixture_derivatives_append_and_compute_all_lift_labels(rig):
    # Values varied in memory from the documented YouTube row to exercise math.
    template = fixture()["videos"][0]
    rows = [{**template, "url": f"https://www.youtube.com/watch?v=fixture{n:04d}", "viewCountInt": value}
            for n, value in enumerate((100, 100, 100, 100, 100, 150, 200, 500))]
    rig.replies[:] = [(200, {"videos": rows[:4], "continuationToken": "next"}),
                     (200, {"videos": rows[4:], "continuationToken": None})]
    result = run(rig, pages=2, confirm_credits=2)
    assert result["ok"] and result["coverage"] == {
        "pages": 2, "items": 8, "truncated": False, "next_cursor_present": False}
    assert result["baseline"]["median"] == 100 and result["baseline"]["n"] == 8
    assert result["baseline"]["confidence"] == "Low"
    assert [c["lift"] for c in result["candidates"]] == [1, 1, 1, 1, 1, 1.5, 2, 5]
    assert [c["label"] for c in result["candidates"]] == ["none"] * 5 + ["mild", "strong", "huge"]


def test_empty_run_has_no_baseline_groups(rig):
    payload = fixture()
    payload.update(videos=[], continuationToken=None)
    rig.replies[:] = [(200, payload)]
    result = run(rig)
    assert result["ok"] and result["coverage"]["items"] == 0
    assert result["candidates"] == [] and result["baselines"] == [] and result["baseline"] is None


def test_documented_absent_fields_stay_null_without_guessing(rig):
    payload = fixture("youtube_channel_shorts")
    row = payload["shorts"][0]
    for field in ("viewCountInt", "likeCountInt", "commentCountInt", "publishDate", "durationMs"):
        row.pop(field)
    row.update(viewCount=123, likeCount=123, commentCount=123, publishedTime="yesterday", lengthSeconds=123)
    rig.replies[:] = [(200, payload)]
    result = run(rig, platform="youtube_shorts")
    candidate = result["candidates"][0]
    assert candidate["metrics"] == {"views": None, "likes": None, "comments": None, "shares": None}
    assert candidate["duration_s"] is None and candidate["published_at"] is None


def test_repeated_cursor_stops_without_a_third_request(rig):
    rig.replies[:] = [(200, fixture()), (200, fixture())]
    result = run(rig, pages=3, confirm_credits=3)
    assert result["ok"] and result["credits_used"] == 2 and len(rig.calls) == 2
    assert result["coverage"]["truncated"] and result["coverage"]["next_cursor_present"]


@pytest.mark.parametrize("status,error", [(301, "discovery_redirect_refused"), (302, "discovery_redirect_refused"),
    (401, "scrapecreators_key_invalid"), (403, "scrapecreators_key_invalid"),
    (429, "discovery_rate_limited"), (500, "discovery_upstream_error"), (503, "discovery_upstream_error")])
def test_failed_request_counts_once_stops_and_keeps_key(rig, status, error, caplog):
    rig.replies[:] = [(status, {"error": KEY, "redirect": "https://evil.example"})]
    result = run(rig, pages=3, confirm_credits=3)
    assert reason(result) == error and result["last_error"] == result["error"]
    assert len(rig.calls) == result["credits_used"] == result["credits_today"] == 1
    assert rig.backend._get_saved_scrapecreators_key() == KEY
    assert rig.settings["scrapecreators_key_invalid"] is (status in (401, 403))
    row = rig.conn.execute("SELECT value FROM memory_layer WHERE key=?",
                           ("usage.scrapecreators.v1_youtube_channel-videos.2026-10",)).fetchone()
    assert json.loads(row[0]) == {"calls": 1, "credits": 1, "failures": 1, "last_call_at": "2026-10-16T12:00:00+00:00"}
    assert KEY not in json.dumps(result) and KEY not in caplog.text


@pytest.mark.parametrize("payload", ["oversize", b"not json", ValueError(KEY), TimeoutError(KEY)],
                         ids=["oversize", "invalid-json", "unexpected-error", "timeout"])
def test_oversize_and_unexpected_errors_use_envelope_no_leaks(rig, payload, caplog):
    oversize = payload == "oversize"
    if oversize:
        data = fixture()
        data["videos"][0]["description"] = "x" * sc.MAX_BYTES
        payload = json.dumps(data).encode("utf-8")
        assert len(payload) > sc.MAX_BYTES
        assert json.loads(payload) == data
    rig.replies[:] = [(200, payload)]
    result = run(rig, pages=3, confirm_credits=3)
    assert result["ok"] is False and "error" in result and result["credits_used"] == 1
    assert len(rig.calls) == 1 and KEY not in json.dumps(result) and KEY not in caplog.text
    if oversize:
        assert reason(result) == "discovery_response_too_large"
        assert result["candidates"] == [] and result["coverage"]["items"] == 0
        saved_path = rig.root / "discovery" / "runs" / result["fetched_at"][:7] / (result["run_id"] + ".json")
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        assert reason(saved) == "discovery_response_too_large"
        assert saved["candidates"] == [] and saved["coverage"]["items"] == 0


def test_redirected_injected_response_is_refused(rig):
    rig.service.transport = lambda *args: sc.TransportResponse(200, b"{}", "https://evil.example")
    assert reason(run(rig)) == "discovery_redirect_refused"


def test_real_transport_refuses_all_redirects_and_caps_reads(monkeypatch):
    request = urllib.request.Request(sc.BASE_URL + sc.BALANCE_ENDPOINT)
    with pytest.raises(urllib.error.HTTPError):
        sc._NoRedirect().redirect_request(request, None, 302, "found", {}, "https://evil.example")
    with pytest.raises(urllib.error.HTTPError):
        sc._NoRedirect().redirect_request(request, None, 302, "found", {}, sc.BASE_URL + sc.BALANCE_ENDPOINT)
    class Body(io.BytesIO):
        code = 200
        def geturl(self):
            return request.full_url
        def read(self, size):
            assert size == sc.MAX_BYTES + 1
            return super().read(size)
    opener = Mock()
    opener.open.return_value = Body(b"{}")
    factory = Mock(return_value=opener)
    monkeypatch.setattr(urllib.request, "build_opener", factory)
    response = sc.transport("GET", request.full_url, {"x-api-key": KEY}, 8, sc.MAX_BYTES)
    assert response.body == b"{}" and isinstance(factory.call_args.args[0], sc._NoRedirect)
    assert opener.open.call_args.kwargs == {"timeout": 8}
    for url in ("http://api.scrapecreators.com/v1/credit-balance", "https://evil.example/v1/credit-balance",
                "https://api.scrapecreators.com/v1/tiktok/user/audience"):
        with pytest.raises(sc.ResourceError):
            sc.transport("GET", url, {}, 8, sc.MAX_BYTES)
    assert opener.open.call_count == 1


def test_parser_drops_unsupported_urls_missing_metrics_are_null_and_marks_library(rig):
    data = fixture()
    first = data["videos"][0]
    first.pop("viewCountInt")
    second = {**first, "url": "https://www.youtube.com/watch?v=fixture0001"}
    data["videos"].extend([second, {**first, "url": "https://evil.example/video"}, {**first, "url": "https://x.com/u/status/123"}])
    rig.idx.upsert_yoink({"video_id": "5EWaxmWgQMI", "slug": "captured", "title": "Captured",
                          "yoinked_at": "2026-10-15T12:00:00", "corpus_path": str(rig.root / "captured.md"),
                          "sidecar_path": str(rig.root / "captured.json")})
    rig.idx.upsert_yoink({"video_id": "fixture0001", "slug": "fixture0001", "title": "Deleted",
                          "yoinked_at": "2026-10-15T12:00:00", "corpus_path": str(rig.root / "deleted.md"),
                          "sidecar_path": str(rig.root / "deleted.json")})
    rig.conn.execute("UPDATE yoinks SET deleted_at='2026-10-15' WHERE video_id='fixture0001'")
    rig.conn.commit()
    rig.replies[:] = [(200, data)]
    result = run(rig)
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["metrics"] == {"views": None, "likes": None, "comments": None, "shares": None}
    assert result["candidates"][0]["in_library"] and result["candidates"][0]["state"] == "captured"
    assert result["candidates"][1]["in_library"] is False


def test_nonfinite_metrics_become_null_and_echoed_keys_are_removed(rig):
    payload = fixture("youtube_channel_shorts")
    payload["shorts"][0].update(viewCountInt=float("inf"), likeCountInt=True, title=KEY)
    rig.replies[:] = [(200, payload)]
    result = run(rig, platform="youtube_shorts")
    assert result["ok"] and result["candidates"][0]["metrics"]["views"] is None
    assert result["candidates"][0]["metrics"]["likes"] is None
    assert KEY not in json.dumps(result)


def test_json_escaped_echoed_key_never_leaves_adapter(rig):
    text = json.dumps(fixture()).replace(fixture()["videos"][0]["title"], "".join("\\u%04x" % ord(c) for c in KEY))
    rig.replies[:] = [(200, text.encode())]
    result = run(rig)
    assert result["ok"] and result["candidates"][0]["caption"] == "[redacted]"
    assert KEY not in json.dumps(result)


@pytest.mark.parametrize("change,expected", [
    ({"scrapecreators_enabled": False}, "discovery_disabled"),
    ({"scrapecreators_agent_calls_enabled": False}, "user_intent_required"),
    ({"scrapecreators_daily_credit_cap": 1}, "daily_cap_reached")])
def test_gates_rechecked_between_pages_and_partial_run_is_saved(rig, change, expected):
    send = rig.service.transport
    rig.replies[:] = [(200, {**fixture(), "continuationToken": "next"})]
    def change_after_first(*args):
        response = send(*args)
        rig.settings.update(change)
        return response
    rig.service.transport = change_after_first
    result = run(rig, pages=2, confirm_credits=2)
    assert reason(result) == expected
    assert result["credits_used"] == result["credits_today"] == len(rig.calls) == 1
    assert len(result["candidates"]) == 1
    saved = list(sc.recent_runs(rig.root, now=rig.service._now()))
    assert saved == [result]


def test_corrupt_ledger_fails_closed_without_transport(rig):
    rig.conn.execute("INSERT INTO memory_layer(key,value,updated_at) VALUES(?,?,?)",
                     ("usage.scrapecreators.day.2026-10-16", '{"credits":-1}', "2026-10-16"))
    rig.conn.commit()
    assert reason(run(rig)) == "discovery_ledger_invalid" and rig.calls == []


def test_partial_upstream_failure_retains_candidates_and_counts_two_requests(rig):
    rig.replies[:] = [(200, {**fixture(), "continuationToken": "next"}), (429, {})]
    result = run(rig, pages=3, confirm_credits=3)
    assert reason(result) == "discovery_rate_limited"
    assert result["credits_used"] == 2 and len(rig.calls) == 2
    assert result["coverage"]["items"] == 1 and result["coverage"]["pages"] == 1
    assert list(sc.recent_runs(rig.root, now=rig.service._now())) == [result]


@pytest.mark.parametrize("failure", [OSError("private path"), sqlite3.OperationalError("private database")])
@pytest.mark.parametrize("partial", [False, True])
def test_paid_save_failure_returns_candidates_and_local_retry_never_spends(rig, monkeypatch, failure, partial):
    if partial:
        rig.replies[:] = [(200, {**fixture(), "continuationToken": "next"}), (429, {})]
    with monkeypatch.context() as patch:
        patch.setattr(sc, "_atomic_write_text", Mock(side_effect=failure))
        result = run(rig, pages=2 if partial else 1, confirm_credits=2 if partial else 1)
        assert result["save_failed"] is True and len(result["candidates"]) == 1
        assert result["ok"] is (not partial)
        assert result["credits_used"] == result["credits_today"] == (2 if partial else 1)
        assert "private" not in json.dumps(result) and KEY not in json.dumps(result)
        retry = rig.service.retry_save({"run_id": result["run_id"]})
        assert retry == result
    before = len(rig.calls)
    rig.service.transport = Mock(side_effect=AssertionError("retry must not send"))
    rig.backend._read_settings = Mock(side_effect=AssertionError("retry must not check spending"))
    rig.backend._get_saved_scrapecreators_key = Mock(side_effect=AssertionError("retry must not read credentials"))
    rig.backend._get_index = Mock(side_effect=AssertionError("retry must not touch the index"))
    # The returned object cannot mutate the retained receipt.
    expected = json.loads(json.dumps(result))
    result["candidates"].clear()
    recovered = rig.service.retry_save({"run_id": result["run_id"]})
    expected.pop("save_failed")
    assert recovered == expected
    assert json.loads(rig.service._run_path(result["run_id"]).read_text(encoding="utf-8")) == expected
    assert rig.service.retry_save({"run_id": result["run_id"]}) == expected
    assert len(rig.calls) == before
    assert result["run_id"] not in rig.service._unsaved_runs


@pytest.mark.parametrize("stage", ["library_lookup", "failure_counter", "daily_total"])
@pytest.mark.parametrize("save_fails", [False, True])
def test_local_database_failure_preserves_paid_page(rig, monkeypatch, stage, save_fails):
    payload = fixture()
    original = payload["videos"][0]
    payload["videos"] = [dict(original, id=vid, url=f"https://www.youtube.com/watch?v={vid}")
                         for vid in ("abcdefghijk", "lmnopqrstuv", "12345678901")]
    rig.replies[:] = [(200, payload), (429, {})]
    error = sqlite3.OperationalError("private database path")
    record, credits_today = rig.service._record, rig.service._credits_today

    def record_failure(*args, **kwargs):
        if kwargs.get("failure"):
            raise error
        return record(*args, **kwargs)

    def read_total(idx):
        if rig.calls:
            raise error
        return credits_today(idx)

    with monkeypatch.context() as patch:
        if stage == "library_lookup":
            patch.setattr(rig.idx, "get_yoink", Mock(side_effect=error))
        elif stage == "failure_counter":
            patch.setattr(rig.service, "_record", record_failure)
        else:
            patch.setattr(rig.service, "_credits_today", read_total)
        if save_fails:
            patch.setattr(sc, "_atomic_write_text", Mock(side_effect=OSError("disk full")))
        result = run(rig, pages=2 if stage == "failure_counter" else 1,
                     confirm_credits=2 if stage == "failure_counter" else 1)
    assert result["ok"] is False and result["last_error"] == result["error"]
    assert [c["video_id"] for c in result["candidates"]] == ["abcdefghijk", "lmnopqrstuv", "12345678901"]
    assert result["coverage"]["items"] == 3
    assert result["credits_used"] == len(rig.calls) == (2 if stage == "failure_counter" else 1)
    assert result["credits_today"] == (None if stage == "daily_total" else result["credits_used"])
    assert bool(result.get("save_failed")) is save_fails
    assert "private" not in json.dumps(result) and KEY not in json.dumps(result)
    assert rig.service._credits_today(rig.idx) == result["credits_used"]
    rig.service.transport = Mock(side_effect=AssertionError("local recovery must not send"))
    recovered = rig.service.retry_save({"run_id": result["run_id"]})
    assert recovered == {key: value for key, value in result.items() if key != "save_failed"}
    assert json.loads(rig.service._run_path(result["run_id"]).read_text(encoding="utf-8")) == recovered


def test_local_save_retry_preserves_conflicting_file(rig, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(sc, "_atomic_write_text", Mock(side_effect=OSError("disk full")))
        result = run(rig)
    path = rig.service._run_path(result["run_id"])
    original = json.dumps({**result, "candidates": []})
    path.write_text(original, encoding="utf-8")
    assert reason(rig.service.retry_save({"run_id": result["run_id"]})) == "discovery_save_conflict"
    assert path.read_text(encoding="utf-8") == original
    assert rig.service._unsaved_runs[result["run_id"]]["candidates"] == result["candidates"]
    assert len(rig.calls) == 1


def test_local_save_retry_cannot_replace_a_file_created_during_retry(rig, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(sc, "_atomic_write_text", Mock(side_effect=OSError("disk full")))
        result = run(rig)
    destination = rig.service._run_path(result["run_id"])
    original = b"a receipt from another writer"
    link = sc.os.link
    def race(source, target):
        destination.write_bytes(original)
        return link(source, target)
    monkeypatch.setattr(sc.os, "link", race)
    retry = rig.service.retry_save({"run_id": result["run_id"]})
    assert retry["save_failed"] is True and retry["candidates"] == result["candidates"]
    assert destination.read_bytes() == original
    assert len(rig.calls) == 1


def test_daily_ledger_rolls_at_utc_midnight(rig):
    rig.clock.value = dt.datetime(2026, 10, 31, 23, 59, 59, tzinfo=dt.timezone.utc).timestamp()
    rig.settings["scrapecreators_daily_credit_cap"] = 1
    assert run(rig)["credits_today"] == 1
    assert reason(run(rig)) == "daily_cap_reached"
    rig.clock.value += 1
    rig.replies[:] = [(200, fixture())]
    assert run(rig)["credits_today"] == 1
    rows = dict(rig.conn.execute("SELECT key,value FROM memory_layer WHERE key LIKE 'usage.scrapecreators.day.%'"))
    assert {key: json.loads(value)["credits"] for key, value in rows.items()} == {
        "usage.scrapecreators.day.2026-10-31": 1, "usage.scrapecreators.day.2026-11-01": 1}


def test_balance_is_gated_planned_and_metered(rig):
    plan = rig.service.test_key({})
    assert plan["needs_confirmation"] and plan["credits_planned"] == 1
    assert "may use a credit" in plan["notice"] and rig.calls == []
    rig.settings["scrapecreators_agent_calls_enabled"] = False
    assert reason(rig.service.test_key({"confirm_credits": 1})) == "user_intent_required"
    token = intent(rig, {}, tool="test_key")["user_intent_token"]
    rig.replies[:] = [(200, fixture("credit_balance"))]
    result = rig.service.test_key({"confirm_credits": 1, "user_intent_token": token},
                                 origin="http://127.0.0.1:5180", session_hash="fixture-session")
    assert result["balance"] == 333 and result["credits_today"] == 1
    assert rig.calls[0][1] == sc.BASE_URL + sc.BALANCE_ENDPOINT


def test_concurrency_is_process_wide(rig):
    entered, release = threading.Event(), threading.Event()
    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return sc.TransportResponse(200, json.dumps(fixture()).encode(), args[1])
    rig.service.transport = blocked
    results = []
    worker = threading.Thread(target=lambda: results.append(run(rig)))
    worker.start()
    try:
        assert entered.wait(5)
        other = sc.DiscoveryService(rig.backend, transport=Mock(side_effect=AssertionError("must not send")), clock=rig.clock)
        assert other.discover_candidates({**ARGS, "confirm_credits": 1})["error"]["code"] == "rate_limited"
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and results[0]["ok"]


def test_candidate_and_packet_file_bounds(rig):
    template = fixture()["videos"][0]
    rig.replies[:] = [(200, {"videos": [{**template, "url": f"https://www.youtube.com/watch?v=fixture{n:04d}"}
                                      for n in range(1000)], "continuationToken": "next"})]
    result = run(rig, pages=3, confirm_credits=3)
    assert len(result["candidates"]) == sc.MAX_CANDIDATES == 60
    assert result["coverage"]["truncated"] and len(rig.calls) == 1
    folder = rig.root / "discovery" / "runs" / "2026-10"
    for n in range(50):
        (folder / f"20261016T120000-{n:04d}.json").write_text(json.dumps(result), encoding="utf-8")
    assert len(list(sc.recent_runs(rig.root, now=rig.service._now()))) == sc.MAX_RUN_FILES_PER_PACKET == 24


def test_run_reader_caps_reads_even_for_invalid_files(rig, monkeypatch):
    folder = rig.root / "discovery" / "runs" / "2026-10"
    folder.mkdir(parents=True)
    for n in range(100):
        (folder / f"{n:04d}.json").write_text("not json", encoding="utf-8")
    opened = []
    original = Path.open
    def count(path, *args, **kwargs):
        if path.parent == folder:
            opened.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", count)
    assert list(sc.recent_runs(rig.root, now=rig.service._now())) == []
    assert len(opened) == sc.MAX_RUN_FILES_PER_PACKET


def test_scoped_reader_finds_creator_after_many_unrelated_runs(rig, monkeypatch):
    result = run(rig)
    folder = rig.root / "discovery" / "runs" / "2026-10"
    for n in range(50):
        other = {**result, "handle": f"other{n}", "fetched_at": "2026-10-16T12:00:01+00:00"}
        other["run_id"] = "20261016T120001000000Z-" + sc._run_scope(other) + "-" + f"{n:016x}"
        rig.service._save_run(other)
    # Keyword results and Shorts from the same target must not displace videos.
    for changes in ({"mode": "keyword", "query": "fixture"}, {"platform": "youtube_shorts"}):
        other = {**result, **changes, "fetched_at": "2026-10-16T12:00:02+00:00"}
        if other["mode"] == "keyword":
            other.pop("handle")
        other["run_id"] = "20261016T120002000000Z-" + sc._run_scope(other) + "-" + "b" * 16
        rig.service._save_run(other)
    opened = []
    original = Path.open
    def count(path, *args, **kwargs):
        if path.parent == folder:
            opened.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", count)
    rig.clock.value += 3
    assert list(sc.recent_runs(rig.root, now=rig.service._now(), handle="@FIXTURE", platform="youtube")) == [result]
    assert len(opened) == 1


def test_scoped_reader_caps_matching_files_and_returns_newest_first(rig, monkeypatch):
    result = run(rig)
    folder = rig.root / "discovery" / "runs" / "2026-10"
    for n in range(50):
        stamp = rig.service._now() - dt.timedelta(minutes=n + 1)
        prior = {**result, "fetched_at": stamp.isoformat()}
        prior["run_id"] = stamp.strftime("%Y%m%dT%H%M%S%fZ-") + sc._run_scope(prior) + "-" + f"{n:016x}"
        rig.service._save_run(prior)
    opened = []
    original = Path.open
    def count(path, *args, **kwargs):
        if path.parent == folder:
            opened.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", count)
    runs = list(sc.recent_runs(rig.root, now=rig.service._now(), handle="fixture", platform="youtube"))
    assert runs[0] == result
    assert len(runs) == len(opened) == sc.MAX_RUN_FILES_PER_PACKET == 24
    assert [r["fetched_at"] for r in runs] == sorted((r["fetched_at"] for r in runs), reverse=True)


def test_channel_url_identity_shares_the_packet_file_budget(rig, monkeypatch):
    result = run(rig)
    channel_id = "UC" + "a" * 22
    folder = rig.root / "discovery" / "runs" / "2026-10"
    for target in ({"handle": "fixture"}, {"channel_id": channel_id}):
        for n in range(50):
            stamp = rig.service._now() - dt.timedelta(minutes=n + 1)
            prior = {k: v for k, v in result.items() if k != "handle"}
            prior.update(target, fetched_at=stamp.isoformat())
            prior["run_id"] = stamp.strftime("%Y%m%dT%H%M%S%fZ-") + sc._run_scope(prior) + "-" + f"{n:016x}"
            rig.service._save_run(prior)
    opened = []
    original = Path.open
    def count(path, *args, **kwargs):
        if path.parent == folder:
            opened.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", count)
    runs = list(sc.recent_runs(rig.root, now=rig.service._now(), mode="creator",
                              handle="fixture", youtube_author=channel_id, include_keyword=True))
    assert len(runs) == len(opened) == sc.MAX_RUN_FILES_PER_PACKET == 24
    assert {r.get("channel_id") or r.get("handle") for r in runs} == {"fixture", channel_id}
    assert result in runs


@pytest.mark.parametrize("target", ["a/b", "a?b", "CON", "\U0001f600" * 100, "a" * 100])
def test_request_identity_is_safe_complete_and_queue_compatible(rig, target):
    result = run(rig, handle=target)
    assert result["ok"] and result["handle"] == target
    assert sc.validate_queue_arguments({"run_id": result["run_id"], "keys": [result["candidates"][0]["key"]]})[0]
    assert list(sc.recent_runs(rig.root, now=rig.service._now(), handle=target, platform="youtube")) == [result]
    assert sc._run_scope({**result, "handle": target + "z"}) != sc._run_scope(result)


def test_key_as_target_is_rejected_without_storage_or_transport(rig):
    assert reason(run(rig, handle=KEY)) == "discovery_sensitive_input"
    assert rig.calls == [] and not (rig.root / "discovery").exists()


def test_run_retention_is_ninety_days_and_keeps_unknown_files(rig):
    old = dt.datetime(2026, 7, 17, 12, tzinfo=dt.timezone.utc)
    boundary = dt.datetime(2026, 7, 18, 12, tzinfo=dt.timezone.utc)
    folder = rig.root / "discovery" / "runs" / "2026-07"
    folder.mkdir(parents=True)
    def name(stamp):
        return folder / (stamp.strftime("%Y%m%dT%H%M%S%fZ-") + "a" * 16 + ".json")
    name(old).write_text("{}")
    name(boundary).write_text("{}")
    scoped_old = folder / (old.strftime("%Y%m%dT%H%M%S%fZ-") + sc._run_scope({**ARGS, "handle": "fixture"}) + "-" + "b" * 16 + ".json")
    scoped_old.write_text("{}")
    unknown = folder / "other.json"
    unknown.write_text("{}")
    assert sc.purge_expired_runs(rig.root, now=rig.service._now()) == 2
    assert not scoped_old.exists()
    assert not name(old).exists() and name(boundary).exists() and unknown.exists()


def test_failed_receipts_are_addressable_and_purged_after_ninety_days(rig):
    rig.replies[:] = [(429, {})]
    failed = run(rig)
    path = rig.service._run_path(failed["run_id"])
    assert failed["run_id"].endswith("-failed")
    assert rig.service.read_run(failed["run_id"]) == failed
    assert sc.purge_expired_runs(rig.root, now=rig.service._now() + dt.timedelta(days=90)) == 0
    assert path.exists()
    assert sc.purge_expired_runs(rig.root, now=rig.service._now() + dt.timedelta(days=91)) == 1
    assert not path.exists()


def test_queue_intent_can_only_authorize_its_own_picks_without_paid_access(rig):
    rig.settings["scrapecreators_agent_calls_enabled"] = False
    args = {"run_id": "fixture-run", "keys": ["a", "b"]}
    token = intent(rig, args, tool="queue_discovered")["user_intent_token"]
    assert reason(rig.service.authorize_queue({**args, "keys": ["c"], "user_intent_token": token},
                  origin="http://127.0.0.1:5180", session_hash="fixture-session")) == "invalid_user_intent"
    assert rig.service.authorize_queue({**args, "user_intent_token": token},
              origin="http://127.0.0.1:5180", session_hash="fixture-session") == {"ok": True, "arguments": args}
    assert reason(rig.service.authorize_queue({"run_id": "fixture-run", "keys": [str(n) for n in range(11)]})) == "keys"
    assert rig.calls == [] and rig.service._credits_today(rig.idx) == 0


class Probe(server.Handler):
    def __init__(self, path, body=None, headers=None):
        self.command = "POST"
        self.path = path
        self.client_address = ("127.0.0.1", 1)
        raw = body if isinstance(body, bytes) else json.dumps(body or {}).encode()
        self.rfile = io.BytesIO(raw)
        self.headers = {"Host": f"127.0.0.1:{server.PORT}", "X-Uoink-Token": "fixture-helper-token",
                        "Content-Type": "application/json", "Content-Length": str(len(raw)), **(headers or {})}
        self.status = self.payload = None

    def _send_json(self, status, payload):
        self.status, self.payload = status, payload


@pytest.fixture
def routes(rig, monkeypatch):
    monkeypatch.setattr(server, "TOKEN", "fixture-helper-token")
    monkeypatch.setattr(server, "_get_discovery_service", lambda: rig.service)
    return rig


@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"}, {"Origin": "chrome-extension://extension"},
    {"Origin": "http://127.0.0.1:1"}, {"Sec-Fetch-Site": "cross-site"},
    {"Host": "evil.example"}, {"X-Uoink-Token": "wrong"}])
def test_intent_route_requires_host_auth_dashboard_origin(routes, headers):
    probe = Probe("/discovery/intent", {"confirmed": True, "operation": {"tool": "discover_candidates", "arguments": ARGS}}, headers)
    probe.do_POST()
    assert probe.status == 403 and routes.service._intents == {} and routes.calls == []


def test_intent_route_strict_json_rate_limit_and_balance_route(routes):
    for raw in (b'{"confirmed":NaN}', b'{"confirmed":true,"confirmed":false}'):
        probe = Probe("/discovery/intent", raw)
        probe.do_POST()
        assert probe.status == 400
    body = {"confirmed": True, "operation": {"tool": "test_key", "arguments": {}}}
    for _ in range(30):
        probe = Probe("/discovery/intent", body)
        probe.do_POST()
        assert probe.status == 200 and probe.payload["ok"]
    token = probe.payload["user_intent_token"]
    probe = Probe("/discovery/intent", body)
    probe.do_POST()
    assert probe.status == 429
    routes.settings["scrapecreators_agent_calls_enabled"] = False
    routes.replies[:] = [(200, fixture("credit_balance"))]
    probe = Probe("/discovery/test-key", {"confirm_credits": 1, "user_intent_token": token})
    probe.do_POST()
    assert probe.status == 200 and probe.payload["balance"] == 333


@pytest.fixture
def settings_route(tmp_path, monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(server, "_keyring", fake)
    monkeypatch.setattr(server, "_isolated_binding", lambda: SimpleNamespace(profile=tmp_path))
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {})
    monkeypatch.setattr(server, "_reliability_model_status", lambda *args: {})
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "output")
    monkeypatch.setattr(server, "TOKEN", "fixture-helper-token")
    return fake, tmp_path


def test_keyring_namespace_write_only_settings_clear_and_invalid_keep(settings_route):
    fake, folder = settings_route
    probe = Probe("/settings", {"scrapecreators_key": KEY, "scrapecreators_enabled": True,
                                "scrapecreators_agent_calls_enabled": True, "scrapecreators_daily_credit_cap": 25})
    probe.do_POST()
    assert probe.status == 200 and probe.payload["ok"]
    assert KEY not in json.dumps(probe.payload)
    assert KEY not in (folder / "settings.json").read_text()
    assert "scrapecreators_key" not in json.loads((folder / "settings.json").read_text())
    server._mark_scrapecreators_key_invalid()
    assert server._get_saved_scrapecreators_key() == KEY
    public = server._public_settings()
    assert public["scrapecreators_key_invalid"] and public["scrapecreators_key_set"]
    assert "scrapecreators_key" not in public
    probe = Probe("/settings")
    probe._handle_settings_get()
    assert KEY not in json.dumps(probe.payload)
    # Public settings also read the phone inbox's presence flag; every call
    # stays in this profile's isolated namespace.
    assert all(service == server._isolated_keyring_service(folder)
               and username in ("scrapecreators_key", "relay_pull_token")
               for _, service, username in fake.calls)
    assert not any(op != "get" for op, _, username in fake.calls if username == "relay_pull_token")
    probe = Probe("/settings", {"scrapecreators_key": None})
    probe.do_POST()
    assert probe.payload["ok"] and server._get_saved_scrapecreators_key() == ""
    assert not server._public_settings()["scrapecreators_key_invalid"]


@pytest.mark.parametrize("body", [{"scrapecreators_daily_credit_cap": cap} for cap in (0, 501, True, 2.5, "25")] +
                         [{"scrapecreators_enabled": "true"}, {"scrapecreators_agent_calls_enabled": 1},
                          {"scrapecreators_key": 42}, {"scrapecreators_key": "x" * 4097}])
def test_settings_refuse_invalid_types_without_writes(settings_route, body):
    fake, folder = settings_route
    probe = Probe("/settings", body)
    probe.do_POST()
    assert probe.status == 400 and fake.calls == [] and not (folder / "settings.json").exists()


def test_isolated_keyring_failure_has_no_fallback_or_leak(settings_route, monkeypatch, caplog):
    fake, folder = settings_route
    fake.values["Uoink", "scrapecreators_key"] = KEY
    fake.values["Yoink", "scrapecreators_key"] = KEY
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "synthetic-env-key-must-not-be-read")
    assert server._get_saved_scrapecreators_key() == ""
    assert len(fake.calls) == 1 and fake.calls[0][1] == server._isolated_keyring_service(folder)
    fake.get_password = Mock(side_effect=RuntimeError(KEY))
    fake.set_password = Mock(side_effect=RuntimeError(KEY))
    assert server._get_saved_scrapecreators_key() == ""
    probe = Probe("/settings", {"scrapecreators_key": KEY})
    probe.do_POST()
    assert not probe.payload["ok"] and KEY not in json.dumps(probe.payload) and KEY not in caplog.text
    assert not (folder / "settings.json").exists()


def test_keyring_namespaces_are_separate_and_key_length_boundary(settings_route, monkeypatch):
    fake, folder = settings_route
    key = "s" * 4096
    probe = Probe("/settings", {"scrapecreators_key": key})
    probe.do_POST()
    assert probe.payload["ok"] and server._get_saved_scrapecreators_key() == key
    monkeypatch.setattr(server, "_isolated_binding", lambda: SimpleNamespace(profile=folder / "second"))
    assert server._get_saved_scrapecreators_key() == ""
    assert all(service not in ("Uoink", "Yoink") for _, service, _ in fake.calls)


def test_http_unexpected_error_uses_standard_envelope(routes, monkeypatch):
    def broken():
        raise ValueError(KEY)
    monkeypatch.setattr(server, "_get_discovery_service", broken)
    for path in ("/discovery/intent", "/discovery/test-key"):
        probe = Probe(path, {})
        probe.do_POST()
        assert probe.payload["ok"] is False and probe.payload["error"]["code"] == "internal_error"
        assert KEY not in json.dumps(probe.payload)


def test_fixtures_are_exact_copies_of_supplied_openapi_examples():
    files = list(FIXTURES.glob("*.json"))
    assert len(files) == 7
    originals = {doc["source_url"]: doc for path in (FIXTURES / "openapi").glob("*.openapi.json")
                 for doc in [json.loads(path.read_text(encoding="utf-8"))]}
    assert len(originals) == 7
    for path in files:
        saved = json.loads(path.read_text(encoding="utf-8"))
        provenance = saved["_provenance"]
        assert provenance["source_url"].startswith("https://docs.scrapecreators.com/")
        assert provenance["source_url"].endswith("/openapi.json")
        assert provenance["kind"] == "openapi-example"
        assert provenance["fetched_at"].startswith("2026-10-16")
        original = originals[provenance["source_url"]]
        assert all(original[key] == value for key, value in provenance.items())
        assert saved["response"] == original["example_200"]
    assert {sc.BALANCE_ENDPOINT, *(spec["path"] for spec in sc.ENDPOINTS.values())} == {
        original["path"] for original in originals.values()}


@pytest.mark.parametrize("invalid", [True, False])
def test_late_key_result_cannot_change_replacement_status(settings_route, invalid):
    first = Probe("/settings", {"scrapecreators_key": KEY})
    first.do_POST()
    replacement = Probe("/settings", {"scrapecreators_key": "synthetic-replacement"})
    replacement.do_POST()
    server._mark_scrapecreators_key_invalid(not invalid, expected_key="synthetic-replacement")
    before = server._read_settings()
    server._mark_scrapecreators_key_invalid(invalid, expected_key=KEY)
    assert server._read_settings() == before
    assert server._get_saved_scrapecreators_key() == "synthetic-replacement"
    assert before["updated_at"]


@pytest.mark.parametrize("operation", ["_read_settings", "_write_settings"])
def test_invalid_key_settings_io_error_is_guarded_and_redacted(settings_route, monkeypatch, caplog, operation):
    monkeypatch.setattr(server, operation, Mock(side_effect=OSError(KEY)))
    server._mark_scrapecreators_key_invalid()
    assert KEY not in caplog.text
    assert "ScrapeCreators invalid-key settings update failed" in caplog.text

"""Offline Algolia responses through the normal capture and library readers."""
import io
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import hn_extractor as hn
import index
import list_imports
import research
import server
import shelf_router
import uoink_cli
import uoink_mcp_tools as mcp


FIXTURES = Path(__file__).parent / "fixtures" / "hn"
STORY = hn.ITEM_URL + "901"
COMMENT = hn.ITEM_URL + "903"


@pytest.fixture
def api(monkeypatch):
    requests = []
    starts = []
    monkeypatch.setattr(hn, "_last_request_at", None, raising=False)
    bodies = {key: (FIXTURES / f"{name}.json").read_bytes()
              for key, name in [("901", "story"), ("903", "comment"), ("1000", "large")]}
    config = SimpleNamespace(status=200, bodies=bodies, requests=requests, starts=starts)

    class Connection:
        def __init__(self, host, timeout):
            assert host == "hn.algolia.com" and 0 < timeout <= 10

        def request(self, method, path, headers):
            assert method == "GET" and path.startswith("/api/v1/items/")
            assert set(headers) == {"Accept", "User-Agent"}
            self.item = path.removeprefix("/api/v1/items/")
            requests.append(self.item)
            starts.append(hn.time.monotonic())

        def getresponse(self):
            resp = io.BytesIO(bodies[self.item])
            resp.status = config.status
            return resp

        def close(self):
            pass

    monkeypatch.setattr(hn.http.client, "HTTPSConnection", Connection)
    return config


def test_story_and_nested_markdown(api):
    result = hn.extract_hn_thread(STORY)
    assert result["ok"] and result["comments_captured"] == 3
    assert api.requests == ["901"]
    md = result["markdown"]
    assert md.startswith("# Show HN: A pocket tide clock")
    assert "28 points" in md and "orbit\\_plum" in md
    assert "docks & boats" in md and "https://example.test/tide-clock" in md
    assert "### mossquill · [2026-05-01T11:00:00.000Z]" in md
    assert "#### mossquill" in md and "Surviving reply." in md
    assert "[the table](https://example.test/a%28b%29?x=1&y=2)" in md
    assert "```\nif a < b:\n    tick()\n```" in md
    assert "&lt;b&gt;literal&lt;/b&gt;" in md
    assert all(s not in md for s in ("deleted body", "dead body", "[deleted]", "javascript:", "discard-code", "<script", "<b>"))


def test_comment_uses_story_identity_and_highlights_once(api):
    result = hn.extract_hn_thread(COMMENT + "&utm_source=test")
    assert result["ok"] and result["url"] == STORY
    assert api.requests == ["903", "901"]
    md = result["markdown"]
    assert md.index("## Selected comment") < md.index("tidewheel") < md.index("## Top comments")
    assert md.count("tidewheel") == 1 and COMMENT in md
    assert result["comments_captured"] == 3


def test_algolia_spaces_comment_parent_and_next_capture(api, monkeypatch):
    now = time.monotonic()

    def advance(seconds):
        nonlocal now
        now += seconds

    monkeypatch.setattr(hn, "time", SimpleNamespace(monotonic=lambda: now, sleep=advance))

    def fetch_json(url):
        assert url.startswith("https://hn.algolia.com/")
        api.starts.append(hn.time.monotonic())
        return json.loads(api.bodies["901"])

    assert hn.extract_hn_thread(COMMENT)["ok"]
    list_imports.fetch_source({"kind": list_imports.SOURCE_HN, "id": 901},
                              offset=0, limit=1, fetch_json=fetch_json)
    monkeypatch.setattr(research, "http_get_json", fetch_json)
    research.fetch_hn("clocks", 1)
    assert hn.extract_hn_thread(STORY)["ok"]
    assert api.requests == ["903", "901", "901"]
    assert len(api.starts) == 5
    assert all(b - a >= 1 for a, b in zip(api.starts, api.starts[1:]))


@pytest.mark.parametrize("kind", ["job", "poll"])
def test_non_thread_item_explains_its_type(api, kind):
    api.bodies["901"] = json.dumps({"id": 901, "type": kind}).encode()
    result = hn.extract_hn_thread(STORY)
    assert result["code"] == "unsupported_item"
    assert kind in result["error"] and "thread" in result["error"]


@pytest.mark.parametrize("score", [b'"n/a"', b"null", b"true", b"-5", b"1.5", b"9" * 200000],
                         ids=["text", "null", "boolean", "negative", "fraction", "huge-integer"])
def test_invalid_points_leave_the_thread_readable(api, score):
    api.bodies["901"] = api.bodies["901"].replace(b'"points": 28', b'"points": ' + score)
    result = hn.extract_hn_thread(STORY)
    assert result["ok"], result
    assert " points" not in result["markdown"] and "score" not in result["metadata"]
    assert "tidewheel" in result["markdown"] and len(result["markdown"].encode()) <= hn.MAX_MARKDOWN_BYTES


def test_header_respects_markdown_budget(api, monkeypatch):
    story = json.loads(api.bodies["901"])
    story["url"] = "https://example.test/" + "潮" * 3500
    story["points"] = 0
    api.bodies["901"] = json.dumps(story).encode()
    monkeypatch.setattr(hn, "MAX_MARKDOWN_BYTES", 2000)
    result = hn.extract_hn_thread(STORY)
    assert result["ok"] and result["output_truncated"]
    assert len(result["markdown"].encode()) <= 2000
    assert "0 points" in result["markdown"] and STORY in result["markdown"]
    assert "tidewheel" in result["markdown"] and result["links"]


def test_two_stories_keep_their_own_shelf_after_comment_recapture(api, tmp_path, monkeypatch):
    other = hn.ITEM_URL + "910"
    api.bodies["910"] = json.dumps({"id": 910, "type": "story", "title": "Second story"}).encode()
    third = hn.ITEM_URL + "920"
    api.bodies["920"] = json.dumps({"id": 920, "type": "story", "title": "Third story"}).encode()
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_shelf_library", lambda: None)
    with index.Index.open(tmp_path / "index.db") as db:
        monkeypatch.setattr(server, "_get_index", lambda: db)

        def capture(url, **kwargs):
            status, result = server._capture_hn_thread({"url": url, **kwargs})
            assert status == 200, result
            return result["video_id"]

        first = capture(STORY)
        assert server._reshelve([(first, "Reading")], label="Move")["moved"] == 1
        seq = db.shelf_hand_seq(first)
        second = capture(other, shelf="Workshop")
        assert capture(COMMENT) == first
        assert db.get_yoink(first)["topic"] == "Reading"
        assert db.shelf_hand_seq(first) == seq and db.get_yoink(second)["topic"] == "Workshop"
        assert shelf_router.hint_for(tmp_path, third) is None
        third_save = capture(third)
        assert db.get_yoink(third_save)["topic"] != "Workshop" and db.shelf_hand_seq(third_save) == 0
        assert capture(COMMENT, shelf="Favorites") == first
        assert db.get_yoink(first)["topic"] == "Favorites"
        assert shelf_router.hint_for(tmp_path, STORY) == "Favorites"
        assert shelf_router.hint_for(tmp_path, other) == "Workshop"
        assert shelf_router.hint_for(tmp_path, COMMENT) is None
        assert shelf_router.url_key(STORY) == "hn:901"


def test_ask_story_with_an_unavailable_selected_comment(api):
    story = json.loads(api.bodies["901"])
    story.update(title="Ask HN: How do you read tide tables?", url=None, children=[])
    api.bodies["901"] = json.dumps(story).encode()
    comment = json.loads(api.bodies["903"])
    api.bodies["903"] = json.dumps({**comment, "dead": True}).encode()
    result = hn.extract_hn_thread(COMMENT)
    assert result["ok"] and result["comments_captured"] == 0 and not result["links"]
    assert "unavailable" in result["markdown"] and "tidewheel" not in result["markdown"]
    assert "docks & boats" in result["markdown"] and "Story link" not in result["markdown"]


def test_timeout_returns_an_actionable_error(api, monkeypatch):
    def timed_out(*args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr(hn.http.client.HTTPSConnection, "getresponse", timed_out)
    result = hn.extract_hn_thread(STORY)
    assert not result["ok"] and "Algolia took too long" in result["error"]


def test_large_deep_thread_and_selected_comment_outside_limits(api):
    large = json.loads(api.bodies["1000"])
    target = large["children"][-1]
    target["story_id"] = 1000
    api.bodies[str(target["id"])] = json.dumps(target).encode()
    result = hn.extract_hn_thread(hn.ITEM_URL + str(target["id"]))
    assert result["ok"] and result["comments_captured"] == hn.MAX_COMMENTS == 500
    md = result["markdown"]
    assert md.index(target["text"]) < md.index("## Top comments")
    assert "Level 4" in md and "Level 5" not in md
    assert "shortened" in md and len(md.encode()) <= hn.MAX_MARKDOWN_BYTES


def test_markdown_byte_cap_and_single_oversized_comment(api):
    story = json.loads(api.bodies["1000"])
    for comment in story["children"]:
        comment["text"] = "海" * 1500
    story["children"][0]["text"] *= 30
    api.bodies["1000"] = json.dumps(story, ensure_ascii=False).encode()
    result = hn.extract_hn_thread(hn.ITEM_URL + "1000")
    assert result["ok"] and result["output_truncated"]
    assert 1 < result["comments_captured"] < hn.MAX_COMMENTS
    assert len(result["markdown"].encode()) <= hn.MAX_MARKDOWN_BYTES
    assert "text shortened" in result["markdown"]


@pytest.mark.parametrize("url", ["https://example.test/item?id=1", STORY + "&id=2",
                                 hn.ITEM_URL + "x", hn.ITEM_URL + "0", "https://news.ycombinator.com/jobs"])
def test_bad_item_links_do_not_fetch(api, url):
    assert hn.extract_hn_thread(url)["code"] == "bad_url"
    assert not api.requests


@pytest.mark.parametrize("status,body,error", [(302, b"", "HTTP 302"), (429, b"", "minute"),
                         (404, b"", "find"), (200, b"?", "unreadable"),
                         (200, b"[]", "unexpected"), (200, b"x" * 51, "download limit")])
def test_api_errors_and_size_cap(api, monkeypatch, status, body, error):
    monkeypatch.setattr(hn, "MAX_BYTES", 50)
    api.status, api.bodies["901"] = status, body
    result = hn.extract_hn_thread(STORY)
    assert not result["ok"] and error in result["error"]
    assert api.requests == ["901"]


def test_capture_routes_persist_one_searchable_readable_thread(api, tmp_path, monkeypatch):
    db = index.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(mcp, "_backend", server)
    monkeypatch.setattr(server, "_get_index", lambda: db)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_route_topic", lambda meta, **kw: "Tinkering")
    try:
        detect = server._classify_capture_url(COMMENT + "&utm_source=test")
        assert (detect["source"], detect["endpoint"], detect["canonical"]) == ("hn_thread", "/extract/page", COMMENT)
        handler = SimpleNamespace(_send_json=lambda status, result: result)
        saved = server.Handler._handle_extract_page(handler, {"url": STORY, "shelf": "Workshop"})
        assert saved["ok"] and db.get_yoink(saved["video_id"])["topic"] == "Workshop"
        details = server.Handler._handle_yoink_details(handler, f"/yoinks/{saved['video_id']}/details")
        assert details["details"]["story_url"] == "https://example.test/tide-clock"
        tool, args = uoink_cli.friendly_call(uoink_cli.parser().parse_args(["capture", COMMENT]), server)
        assert (tool, args) == ("uoink_page", {"url": COMMENT})
        assert server._capture_tools()[detect["source"]] == (tool, "url")
        assert mcp.uoink_page(args)["video_id"] == saved["video_id"]
        assert mcp.uoink_url(args)["video_id"] == saved["video_id"]
        assert api.requests == ["901", "903", "901", "903", "901"]
        assert db.count_corpus() == 1
        row, = db.search("tidewheel")
        assert (row["source_type"], row["platform"]) == ("hn_thread", "hn")
        corpus = mcp.get_uoink_corpus({"slug": row["slug"]})
        assert corpus["source_url"] == STORY and "## Selected comment" in corpus["corpus_md"]
        assert corpus["video_id"] == saved["video_id"]
        again = server.Handler._handle_reyoink(handler, f"/yoinks/{saved['video_id']}/reyoink")
        assert again["video_id"] == saved["video_id"] and again["metadata"]["selected_comment_id"] == "903"
    finally:
        db.close()

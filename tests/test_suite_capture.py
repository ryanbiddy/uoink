"""uoink.capture/1: token-gated suite capture route. Capture internals and
the network are mocked; nothing here fetches or runs a capture."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import index as index_mod
import page_extractor
import server
import suite_service

YOUTUBE = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
PLAYLIST = "https://www.youtube.com/playlist?list=PLabcdefghijklmnop"
REDDIT = "https://www.reddit.com/r/test/comments/abc123/a_title/"
PAGE = "https://example.org/articles/one"
FEED = "https://example.org/feed.xml"


class _QuietHandler(server.Handler):
    def log_message(self, format, *args):  # noqa: A002
        return


class _FakeTools:
    """Stands in for uoink_mcp_tools; records calls, never captures."""

    def __init__(self):
        self.calls = []
        self.result = {"ok": True, "video_id": "new-item"}
        self.gate = None

    def call_tool(self, name, arguments=None, **_kw):
        self.calls.append((name, dict(arguments or {})))
        if self.gate is not None:
            self.gate.wait(5)
        return dict(self.result)


def _request(port, method, path, *, body=None, token=True):
    headers = {}
    data = None
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    tools = _FakeTools()
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "corpus")
    monkeypatch.setattr(server, "_path_integrity_status", lambda: {"ok": True})
    monkeypatch.setattr(server, "_index_recovering", False)
    monkeypatch.setattr(server, "_mcp_tools_module", lambda: tools)
    monkeypatch.setattr(server, "_suite_capture_jobs", {})
    monkeypatch.setattr(
        server._platform, "media_capability",
        lambda: {"available": True, "code": "ok", "reason": ""})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(httpd.server_address[1]), idx, tools
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        idx.close()


def _save(idx, tmp_path, item_id, url):
    folder = tmp_path / item_id
    folder.mkdir(parents=True)
    corpus = folder / f"{item_id}.md"
    corpus.write_text("# Saved\n", encoding="utf-8")
    idx.upsert_yoink(
        {"video_id": item_id, "slug": item_id, "title": "Saved",
         "yoinked_at": "2026-07-19T12:00:00Z", "corpus_path": str(corpus),
         "sidecar_path": str(folder / f"{item_id}.json"),
         "metadata_json": json.dumps({"url": url})},
        content="Saved")


def _post(port, body, **kw):
    return _request(port, "POST", "/api/suite/v1/capture", body=body, **kw)


def test_capability_advertised_in_manifest_and_lease(env):
    port, _idx, _tools = env
    assert "uoink.capture/1" in suite_service.CAPABILITIES
    status, manifest = _request(port, "GET", suite_service.MANIFEST_PATH, token=False)
    assert status == 200
    assert "uoink.capture/1" in manifest["service"]["capabilities"]
    lease = suite_service.runtime_lease("0", pid=1, started_at="2026-01-01T00:00:00Z")
    assert "uoink.capture/1" in lease["capabilities"]


def test_bad_or_missing_token_is_403(env):
    port, _idx, tools = env
    assert _post(port, {"url": PAGE}, token=False)[0] == 403
    assert _request(port, "GET", "/api/suite/v1/capture/job_x", token=False)[0] == 403
    assert tools.calls == []


def test_inline_saved_for_reddit_thread(env):
    port, _idx, tools = env
    status, body = _post(port, {"url": REDDIT, "source_hint": "reddit_thread"})
    assert status == 200
    assert body == {
        "ok": True, "contract": "uoink.capture", "version": 1, "status": "saved",
        "source": "reddit_thread", "item_id": "new-item", "job_id": None,
        "canonical": REDDIT, "item_uri": "uoink://item/new-item"}
    assert tools.calls == [("uoink_reddit_thread", {"url": REDDIT})]


def test_inline_saved_for_allowed_web_page(env):
    port, idx, tools = env
    page_extractor.add_allowed(idx, "example.org")
    status, body = _post(port, {"url": PAGE})
    assert status == 200 and body["status"] == "saved"
    assert body["source"] == "web_page" and body["item_id"] == "new-item"
    assert tools.calls[0][0] == "uoink_page"


def test_source_hint_is_only_a_hint(env):
    port, _idx, tools = env
    status, body = _post(port, {"url": REDDIT, "source_hint": "web_page"})
    assert status == 200 and body["source"] == "reddit_thread"
    assert tools.calls[0][0] == "uoink_reddit_thread"


def test_exists_returns_item_without_recapture_for_page(env, tmp_path):
    port, idx, tools = env
    page_extractor.add_allowed(idx, "example.org")
    _save(idx, tmp_path, "page-1", PAGE)
    status, body = _post(port, {"url": PAGE + "/"})
    assert status == 200 and body["status"] == "exists"
    assert body["item_id"] == "page-1" and body["item_uri"] == "uoink://item/page-1"
    assert body["job_id"] is None
    assert tools.calls == []


def test_exists_returns_item_without_recapture_for_video(env, tmp_path):
    port, idx, tools = env
    _save(idx, tmp_path, "dQw4w9WgXcQ", YOUTUBE)
    status, body = _post(port, {"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert status == 200 and body["status"] == "exists"
    assert body["item_id"] == "dQw4w9WgXcQ" and body["source"] == "youtube_video"
    assert tools.calls == []


def test_deleted_item_is_not_exists(env, tmp_path):
    port, idx, tools = env
    page_extractor.add_allowed(idx, "example.org")
    _save(idx, tmp_path, "page-1", PAGE)
    idx._conn.execute("UPDATE yoinks SET deleted_at='2026-07-20T00:00:00Z'")
    idx._conn.commit()
    status, body = _post(port, {"url": PAGE})
    assert status == 200 and body["status"] == "saved"
    assert len(tools.calls) == 1


def test_video_is_queued_then_job_resolves_saved(env):
    port, _idx, tools = env
    tools.gate = threading.Event()
    status, body = _post(port, {"url": YOUTUBE})
    assert status == 202 and body["status"] == "queued"
    job_id = body["job_id"]
    assert job_id and body["item_id"] is None and body["item_uri"] is None
    # A second video while one is running is refused, not stacked.
    busy_status, busy = _post(port, {"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"})
    assert busy_status == 429 and busy["error"] == "busy"
    status, polled = _request(port, "GET", f"/api/suite/v1/capture/{job_id}")
    assert status == 202 and polled["status"] == "queued" and polled["job_id"] == job_id
    tools.gate.set()
    for _ in range(100):
        status, polled = _request(port, "GET", f"/api/suite/v1/capture/{job_id}")
        if polled["status"] != "queued":
            break
        time.sleep(0.05)
    assert status == 200 and polled["status"] == "saved"
    assert polled["source"] == "youtube_video" and polled["canonical"] == YOUTUBE
    assert tools.calls == [("uoink_video", {"url": YOUTUBE})]


def test_background_failure_reports_error_status(env):
    port, _idx, tools = env
    tools.result = {"ok": False, "error": "YouTube said no."}
    _status, body = _post(port, {"url": YOUTUBE})
    job_id = body["job_id"]
    for _ in range(100):
        status, polled = _request(port, "GET", f"/api/suite/v1/capture/{job_id}")
        if polled["status"] != "queued":
            break
        time.sleep(0.05)
    assert status == 200 and polled["status"] == "error"
    assert "YouTube said no" in polled["message"]


def test_playlist_is_queued_through_existing_job_code(env, monkeypatch):
    port, _idx, tools = env
    monkeypatch.setattr(server, "_fetch_playlist_preview",
                        lambda url: ({"url": url, "videos": []}, None, 200))
    monkeypatch.setattr(server, "_create_playlist_job",
                        lambda playlist, interval: ("job_20260101_000000_abcdef", {}))
    status, body = _post(port, {"url": PLAYLIST})
    assert status == 202 and body["status"] == "queued"
    assert body["source"] == "youtube_playlist"
    assert body["job_id"] == "job_20260101_000000_abcdef"
    assert tools.calls == []


@pytest.mark.parametrize("state,expected", [
    ("running", "queued"), ("completed", "saved"), ("failed", "error")])
def test_playlist_job_lookup(env, monkeypatch, state, expected):
    port, _idx, _tools = env
    monkeypatch.setattr(server, "_get_public_job", lambda job_id: {
        "state": state, "kind": "playlist", "source_url": PLAYLIST, "error": "boom"})
    status, body = _request(port, "GET", "/api/suite/v1/capture/job_20260101_000000_abcdef")
    assert body["status"] == expected and body["source"] == "youtube_playlist"
    assert status == (202 if expected == "queued" else 200)


def test_unknown_and_malformed_job_ids(env):
    port, _idx, _tools = env
    status, body = _request(port, "GET", "/api/suite/v1/capture/job_20260101_000000_abcdef")
    assert status == 404 and body["error"] == "not_found" and body["ok"] is False
    status, body = _request(port, "GET", "/api/suite/v1/capture/not-a-job")
    assert status == 400 and body["error"] == "bad_request"


def test_web_page_needs_allowlist(env):
    port, _idx, tools = env
    status, body = _post(port, {"url": PAGE})
    assert status == 409 and body["error"] == "consent_required"
    assert "example.org" in body["message"]
    assert body["contract"] == "uoink.capture" and body["version"] == 1
    assert tools.calls == []


def test_tool_side_allowlist_refusal_is_consent_required(env):
    port, idx, tools = env
    page_extractor.add_allowed(idx, "example.org")
    tools.result = {"ok": False, "code": "host_not_allowed", "error": "not allowed"}
    status, body = _post(port, {"url": PAGE})
    assert status == 409 and body["error"] == "consent_required"


def test_podcast_feed_needs_consent_and_is_never_added(env):
    port, idx, tools = env
    status, body = _post(port, {"url": FEED, "source_hint": "podcast_feed"})
    assert status == 409 and body["error"] == "consent_required"
    assert tools.calls == []
    assert idx._conn.execute("SELECT COUNT(*) FROM podcast_feeds").fetchone()[0] == 0


def test_media_unavailable_is_501(env, monkeypatch):
    port, _idx, tools = env
    monkeypatch.setattr(
        server._platform, "media_capability",
        lambda: {"available": False, "code": "media_unavailable",
                 "reason": "Video capture needs the media tools."})
    status, body = _post(port, {"url": YOUTUBE})
    assert status == 501 and body["error"] == "media_unavailable"
    assert "media tools" in body["message"]
    assert tools.calls == []


def test_unsupported_url_is_400(env):
    port, _idx, tools = env
    for url in ("ftp://example.org/file", "not a url"):
        status, body = _post(port, {"url": url})
        assert status == 400 and body["error"] == "unsupported_url", url
    assert tools.calls == []


def test_bad_requests_are_400(env):
    port, _idx, tools = env
    for payload in ({}, {"url": ""}, {"url": 5}, {"url": PAGE, "source_hint": "nope"},
                    {"url": PAGE, "source_hint": 3}):
        status, body = _post(port, payload)
        assert status == 400 and body["error"] == "bad_request", payload
        assert body["ok"] is False and body["contract"] == "uoink.capture"
    assert tools.calls == []


def test_capture_failure_is_a_plain_502(env):
    port, _idx, tools = env
    tools.result = {"ok": False, "error": "The thread could not be read."}
    status, body = _post(port, {"url": REDDIT})
    assert status == 502 and body["error"] == "capture_failed"
    assert "could not be read" in body["message"]

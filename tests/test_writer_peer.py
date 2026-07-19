from __future__ import annotations

import json
import inspect
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import server
import writer_peer


class FixtureWriter(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, format, *args):  # noqa: A002
        return

    def _send(self, payload, status=200):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        type(self).requests.append({
            "path": self.path,
            "token": self.headers.get("X-Writer-Token"),
        })
        if self.path == "/ping":
            return self._send({
                "ok": True,
                "service": "writer",
                "version": 1,
                "status": "ready",
            })
        if self.path == "/api/writer/v1/status":
            return self._send({
                "ok": True,
                "contract": "writer.api",
                "version": 1,
                "data": {
                    "service": "writer",
                    "schema_version": 1,
                    "database": "ready",
                    "uoink": "configured",
                    "counts": {
                        "drafts": 2,
                        "pieces": 3,
                        "scripts": 1,
                        "voice_samples": 1,
                    },
                },
            })
        self._send({"ok": False}, 404)


@pytest.fixture
def fixture_writer(monkeypatch):
    FixtureWriter.requests = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FixtureWriter)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = int(httpd.server_address[1])
    monkeypatch.setenv(
        "UOINK_WRITER_URL", f"http://127.0.0.1:{port}")
    try:
        yield port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_status_is_path_free_and_uses_writer_owned_credential(
        fixture_writer, monkeypatch):
    monkeypatch.setenv("UOINK_WRITER_TOKEN", "writer-fixture-token")
    status = writer_peer.status()
    assert status == {
        "ok": True,
        "peer": "writer",
        "configured": True,
        "availability": "available",
        "api_version": 1,
        "standalone": True,
        "compatibility": {
            "capture": "uoink",
            "generate": "monolith",
            "writes": "single-owner-per-mode",
        },
        "writer": {
            "database": "ready",
            "schema_version": 1,
            "counts": {
                "drafts": 2,
                "pieces": 3,
                "scripts": 1,
                "voice_samples": 1,
            },
        },
    }
    assert FixtureWriter.requests[-1] == {
        "path": "/api/writer/v1/status",
        "token": "writer-fixture-token",
    }
    serialized = json.dumps(status).casefold()
    assert "writer-fixture-token" not in serialized
    assert "127.0.0.1" not in serialized
    assert ".db" not in serialized


def test_detected_but_unconfigured_does_not_read_writer_files(
        fixture_writer, monkeypatch):
    monkeypatch.delenv("UOINK_WRITER_TOKEN", raising=False)
    status = writer_peer.status()
    assert status["configured"] is False
    assert status["availability"] == "detected_unconfigured"
    assert FixtureWriter.requests == [{
        "path": "/ping",
        "token": None,
    }]


def test_peer_url_must_be_loopback(monkeypatch):
    monkeypatch.setenv("UOINK_WRITER_URL", "https://example.com")
    monkeypatch.setenv("UOINK_WRITER_TOKEN", "secret")
    status = writer_peer.status()
    assert status["ok"] is False
    assert status["availability"] == "invalid_configuration"
    assert "loopback" in status["error"]


def test_legacy_generate_routes_remain_the_default_compatibility_path():
    source = inspect.getsource(server)
    assert source.count("writer_peer.status()") == 1
    for route, handler in (
            ('bare == "/writing/tweet"', "_handle_writing_tweet"),
            ('bare == "/writing/blog"', "_handle_writing_blog"),
            ('bare == "/writing/draft"', "_handle_writing_draft_save"),
            ('bare == "/script/generate"', "_handle_script_generate"),
            ('bare == "/script/revise"', "_handle_script_revise"),
            ('bare == "/workspace/critique"', "_handle_workspace_critique"),
    ):
        assert route in source
        assert hasattr(server.Handler, handler)


class QuietUoink(server.Handler):
    def log_message(self, format, *args):  # noqa: A002
        return


def request_uoink(port, *, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/writer-peer/v1/status",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_uoink_exposes_authenticated_read_only_peer_status(monkeypatch):
    expected = {
        "ok": True,
        "peer": "writer",
        "configured": False,
        "availability": "not_running",
    }
    monkeypatch.setattr(writer_peer, "status", lambda: expected)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuietUoink)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = int(httpd.server_address[1])
        status, payload = request_uoink(port)
        assert status == 200
        assert payload == expected
        denied, body = request_uoink(port, token=False)
        assert denied == 403
        assert body["ok"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

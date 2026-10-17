"""Offline log, HTTP rejection and Activity regressions.

Load production definitions without importing server or opening a profile.
HTTP runs through BaseHTTPRequestHandler with an in-memory socket: no binds,
connections, subprocesses, credentials or installed data are needed.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
import io
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock
from http.server import BaseHTTPRequestHandler
import urllib.request

import pytest

from test_publication_truth import publication
from test_unique_capture_folders import ROOT, URL_A, _load, capture


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    blocked = Mock(side_effect=AssertionError("unexpected external I/O"))
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "bind", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(subprocess, "run", blocked)


@pytest.fixture
def http(tmp_path):
    scope = {
        "BaseHTTPRequestHandler": BaseHTTPRequestHandler, "Path": Path,
        "json": json, "secrets": secrets, "time": time,
        "VERSION": "0.0.0", "HOST": "127.0.0.1", "PORT": 12345,
        "TOKEN": "synthetic-test-token", "ALLOWED_ORIGINS": set(),
        "log": logging.getLogger(__name__), "DATA_ROOT": tmp_path,
        "_read_settings": lambda: {}, "_active_migration_version": 1,
        "_last_successful_tick_at": None, "_index_recovering": False,
        "_OUTPUT_ROOT_FALLBACK": False, "_heartbeat_payload": lambda: {},
        "_path_integrity_status": lambda: {"ok": True},
        "_library_health_payload": lambda: {},
        "index": SimpleNamespace(latest_schema_version=lambda: 1),
        "whisper_runner": SimpleNamespace(
            normalize_model=lambda value: "test",
            is_whisperx_available=lambda: False,
            is_model_downloaded=lambda *args: False),
        "images": SimpleNamespace(MAX_IMAGE_BYTES=1024 * 1024),
    }
    _load(ROOT / "server.py", {"_strict_json_route", "_reject_json_constant",
                              "_reject_duplicate_json_keys"}, scope, constants={
        "MAX_BODY_BYTES", "ALLOWED_HOST_NAMES", "_STRICT_JSON_ROUTE_PREFIXES",
        "LIBRARY_INTENT_ROUTE", "LIBRARY_MIRROR_INTENT_ROUTE",
        "LIBRARY_MIRROR_ROUTE", "SOURCES_INTENT_ROUTE",
    })
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8-sig"))
    handler = next(n for n in tree.body
                   if isinstance(n, ast.ClassDef) and n.name == "Handler")
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, handler], type_ignores=[]))
    exec(compile(module, "server.py", "exec"), scope)
    return SimpleNamespace(scope=scope, handler=scope["Handler"])


class _Input(io.BytesIO):
    def __init__(self, data, fragment, read_error):
        super().__init__(data)
        self.fragment = fragment
        self.read_error = read_error
        self.drain_reads = []

    def read1(self, size=-1):
        self.drain_reads.append(size)
        if self.read_error:
            raise self.read_error
        return super().read1(min(size, self.fragment))

    def close(self):
        # Retain positions for assertions after the real handler finishes.
        pass


class _Socket:
    def __init__(self, request, fragment, read_error):
        self.input = _Input(request, fragment, read_error)
        self.output = bytearray()
        self.response_positions = []
        self.timeout = 30
        self.timeouts = []

    def makefile(self, *args):
        return self.input

    def sendall(self, data):
        self.response_positions.append(self.input.tell())
        self.output.extend(data)

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value
        self.timeouts.append(value)


def _request(http, body=b"{}", *, path="/extract/x", method="POST",
             headers=None, token=True, fragment=65536, read_error=None):
    fields = {"Host": "127.0.0.1:12345", "Content-Type": "application/json",
              "Content-Length": str(len(body))}
    if token:
        fields["X-Uoink-Token"] = http.scope["TOKEN"]
    fields.update(headers or {})
    head = (f"{method} {path} HTTP/1.1\r\n"
            + "".join(f"{key}: {value}\r\n" for key, value in fields.items())
            + "\r\n").encode()
    conn = _Socket(head + body, fragment, read_error)
    handler = http.handler(conn, ("127.0.0.1", 12346),
                           SimpleNamespace(server_address=("127.0.0.1", 12345)))
    response, _, payload = bytes(conn.output).partition(b"\r\n\r\n")
    status = int(response.split(b" ", 2)[1])
    return SimpleNamespace(status=status, payload=json.loads(payload), conn=conn,
                           handler=handler, head_size=len(head), body_size=len(body))


def _assert_drained_before_response(response, count=None):
    expected = response.head_size + (response.body_size if count is None else count)
    assert response.conn.response_positions
    assert response.conn.response_positions[0] == expected
    assert response.conn.input.tell() == expected
    assert response.conn.timeout == 30


def test_server_log_rotates_with_three_bounded_backups(tmp_path, monkeypatch):
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8-sig"))
    config = next(n for n in tree.body if isinstance(n, ast.Expr)
                  and isinstance(n.value, ast.Call)
                  and ast.unparse(n.value.func) == "logging.basicConfig")
    configure = Mock()
    monkeypatch.setattr(logging, "basicConfig", configure)
    log_path = tmp_path / "server.log"
    exec(compile(ast.Module(body=[config], type_ignores=[]), "server.py", "exec"), {
        "logging": logging, "RotatingFileHandler": RotatingFileHandler,
        "LOG_PATH": log_path, "sys": sys,
    })
    handlers = configure.call_args.kwargs["handlers"]
    try:
        handler, = [h for h in handlers if isinstance(h, logging.FileHandler)]
        assert isinstance(handler, RotatingFileHandler)
        assert handler.maxBytes == 5 * 1024 * 1024
        assert handler.backupCount == 3
        assert handler.encoding == "utf-8"
        assert configure.call_args.kwargs["level"] == logging.INFO
        for number in range(6):
            record = logging.LogRecord("test", logging.INFO, "", 0,
                                       f"record-{number} " + "x" * (handler.maxBytes - 128), (), None)
            handler.emit(record)
        assert {p.name for p in tmp_path.iterdir()} == {
            "server.log", "server.log.1", "server.log.2", "server.log.3"}
        for name, number in (("server.log", 5), ("server.log.1", 4),
                             ("server.log.2", 3), ("server.log.3", 2)):
            path = tmp_path / name
            assert path.stat().st_size <= handler.maxBytes
            assert path.read_text(encoding="utf-8").startswith(f"record-{number} ")
    finally:
        for handler in handlers:
            handler.close()


@pytest.mark.parametrize("path", ["/health", "/ping?probe=1"])
def test_successful_probes_log_at_debug(http, caplog, path):
    with caplog.at_level(logging.DEBUG, logger=__name__):
        response = _request(http, method="GET", path=path, token=False)
    assert response.status == 200
    assert response.payload["ok"] is True
    records = [r for r in caplog.records if r.name == __name__]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG


def test_rejected_health_probe_remains_visible(http, caplog):
    with caplog.at_level(logging.INFO, logger=__name__):
        response = _request(http, method="GET", path="/health",
                            headers={"Host": "attacker.invalid"})
    assert response.status == 403
    assert "forbidden host" in response.payload["error"]
    assert any(r.levelno >= logging.WARNING and "rejected" in r.message
               for r in caplog.records)


@pytest.mark.parametrize("headers,token,status,error", [
    ({}, False, 403, "missing or invalid token"),
    ({"X-Uoink-Token": "wrong"}, True, 403, "missing or invalid token"),
    ({"Host": "attacker.invalid"}, True, 403, "forbidden host"),
    ({"Content-Type": "text/plain"}, True, 415, "application/json"),
])
def test_early_rejections_drain_before_sending(http, headers, token, status, error):
    response = _request(http, body=b'{"url":"https://x.com/a/status/1"}',
                        headers=headers, token=token, fragment=3)
    assert response.status == status
    assert error in response.payload["error"]
    _assert_drained_before_response(response)
    assert response.handler.close_connection


@pytest.mark.parametrize("path,token", [("/extract/x", True), ("/images", True),
                                        ("/extract/x", False)])
def test_oversized_rejections_have_a_byte_bound(http, path, token):
    cap = http.scope["MAX_BODY_BYTES"]
    response = _request(http, body=b"x" * (cap + 100), path=path, token=token,
                        headers={"Content-Length": str(2 ** 40)})
    assert response.status == (413 if token else 403)
    _assert_drained_before_response(response, cap)
    assert max(response.conn.input.drain_reads) <= 16 * 1024


@pytest.mark.parametrize("length", ["invalid", "-1", "0",
                                    pytest.param("9" * 5000, id="excessive-digits")])
def test_invalid_lengths_do_not_trigger_unbounded_reads(http, length):
    response = _request(http, token=False, headers={"Content-Length": length})
    assert response.status == 403
    _assert_drained_before_response(response, 0)
    assert not response.conn.input.drain_reads


@pytest.mark.parametrize("error", [TimeoutError("stalled"), ConnectionResetError("gone")])
def test_drain_read_failure_preserves_error_and_restores_timeout(http, error):
    response = _request(http, token=False, read_error=error)
    assert response.status == 403
    _assert_drained_before_response(response, 0)
    assert 0 < response.conn.timeouts[1] <= 1.0


def test_drip_feed_has_a_total_deadline(http):
    http.scope["time"] = SimpleNamespace(monotonic=Mock(side_effect=[0, .2, .7, 1.1]))
    response = _request(http, body=b"slow body", token=False, fragment=1)
    assert response.status == 403
    _assert_drained_before_response(response, 2)
    assert response.conn.timeouts[1:3] == pytest.approx([.8, .3])


def test_short_body_eof_still_sends_original_error(http):
    response = _request(http, token=False, headers={"Content-Length": "20"})
    assert response.status == 403
    _assert_drained_before_response(response)


def test_drain_stops_at_declared_length(http):
    response = _request(http, body=b"{}following bytes", token=False,
                        headers={"Content-Length": "2"})
    assert response.status == 403
    _assert_drained_before_response(response, 2)


@pytest.mark.parametrize("body,path", [(b"{broken", "/extract/x"),
                                       (b"[]", "/extract/x"),
                                       (b'{"url":""}', "/extract/x"),
                                       (b'{"a":1,"a":2}', "/library/intent")])
def test_errors_after_json_read_never_read_body_again(http, body, path):
    http.scope["_read_settings"] = lambda: {"x_text_capture_enabled": True}
    response = _request(http, body=body, path=path)
    assert response.status == 400
    _assert_drained_before_response(response)
    assert not response.conn.input.drain_reads


def test_errors_after_image_read_never_read_body_again(http):
    http.scope["images"].build_image = Mock(return_value={"ok": True})
    http.scope["images"].persist_image = Mock(side_effect=OSError("injected"))
    http.scope.update({"_get_index": lambda: None, "DESKTOP_ROOT": Path("unused"),
                       "_classify_topic": Mock()})
    response = _request(http, body=b"image", path="/images")
    assert response.status == 500
    _assert_drained_before_response(response)
    assert not response.conn.input.drain_reads


def test_u15_token_gate_repeated_with_fragmented_bodies(http):
    # Reuse the existing regression unchanged, replacing only its socket
    # transport. Checking the first write position makes the Windows reset
    # cause deterministic rather than relying on OS packet timing.
    @contextmanager
    def serve(settings):
        http.scope["_read_settings"] = lambda: settings
        yield

    fragment = 1

    def post(path, payload, *, token=True):
        response = _request(http, body=json.dumps(payload).encode(), path=path,
                            token=token, fragment=fragment)
        _assert_drained_before_response(response)
        return response.status, response.payload

    scope = {"_server": serve, "_post": post}
    _load(ROOT / "tests/test_u15_x_capture.py", {"_assert", "test_route_token_gated"}, scope)
    for fragment in [1, 3, 7, 65536] * 10:
        scope["test_route_token_gated"]()


@pytest.mark.parametrize("error_type", [PermissionError, OSError])
@pytest.mark.parametrize("outcome", ["completed", "failed", "saved_with_errors"])
def test_corpus_lookup_failure_does_not_hide_activity(publication, caplog, error_type, outcome):
    state = publication
    state.scope["_resolve_corpus_path"] = Mock(side_effect=error_type("private-path-detail"))
    result = {"ok": True, "folder": str(state.folder), "title": "Recorded"}
    kwargs = {"result": result}
    if outcome == "failed":
        kwargs = {"error": "capture failed", "folder": state.folder, "failure_phase": "fetch"}
    elif outcome == "saved_with_errors":
        result.update(ok=False, status="saved_with_errors", failure_phase="save",
                      error="publication failed", publication_job_id="publication-job")
    with caplog.at_level(logging.WARNING):
        job = state.scope["_record_single_extract_job"](URL_A, "2026-10-15T12:00:00", **kwargs)
    expected = "completed" if outcome == "completed" else "failed"
    assert job["state"] == expected
    assert job["session_folder"] == str(state.folder)
    if expected == "completed":
        assert job["result"]["combined_md_path"] is None
    else:
        assert job["error"] == ("capture failed" if outcome == "failed" else "publication failed")
    persisted = state.idx.get_job(job["id"])
    assert persisted["status"] == expected
    assert json.loads(persisted["metadata_json"])["state"] == expected
    if outcome == "saved_with_errors":
        assert job["id"] == "publication-job"
    assert error_type.__name__ in caplog.text
    assert "private-path-detail" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)

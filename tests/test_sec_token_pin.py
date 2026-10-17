"""Offline regressions for audit findings #1 and #10.

Compile the real request handler and bootstrap helpers from their AST, without
importing server.py: importing it initializes local state and credentials.
HTTP requests use BytesIO, a synthetic token and in-memory settings; no sockets,
helper processes, browser profiles or installed app data are used.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import io
import json
import re
import secrets
import shutil
import subprocess
import threading
import time
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
PINNED_ID = "bkcapfidedhfcjpmjabeopfbcjcbmdmi"
OTHER_ID = "abcdefghijklmnopabcdefghijklmnop"
EDGE_ID = "ponmlkjihgfedcbaponmlkjihgfedcba"
MOZ_ID = "01234567-89ab-cdef-0123-456789abcdef"
PORT = 43871  # Only an HTTP Host fixture; nothing listens here.
TEST_TOKEN = "synthetic-security-test-token"
ORIGIN = f"chrome-extension://{PINNED_ID}"


@pytest.fixture(scope="module")
def handler_code():
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
    names = {
        "ALLOWED_ORIGINS", "ALLOWED_HOST_NAMES", "PINNED_EXTENSION_ID",
        "MAX_BODY_BYTES", "_TOKEN_RATE_LIMIT", "_TOKEN_RATE_WINDOW_SEC",
        "_token_request_times", "_token_rate_lock", "_UOINK_CLIENT_HEADER_VALUE",
        "_YOINK_CLIENT_HEADER_VALUE", "_allowed_extension_ids",
        "_check_token_rate_limit", "Handler",
    }
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            nodes.append(node)
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
                nodes.append(node)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id in names:
                nodes.append(node)
    future = ast.parse("from __future__ import annotations").body
    return compile(ast.Module(body=future + nodes, type_ignores=[]),
                   str(ROOT / "server.py"), "exec")


@pytest.fixture
def helper(handler_code):
    namespace = {
        "__name__": "offline_token_handler", "BaseHTTPRequestHandler": BaseHTTPRequestHandler,
        "HOST": "127.0.0.1", "PORT": PORT, "VERSION": "test", "TOKEN": TEST_TOKEN,
        "os": SimpleNamespace(environ={}), "_read_settings": Mock(return_value={}),
        "log": Mock(), "json": json, "re": re, "secrets": secrets,
        "threading": threading, "time": time, "urlparse": urlparse,
        "suite_service": SimpleNamespace(MANIFEST_PATH="/.well-known/suite-service.json",
                                         HEALTH_PATH="/api/suite/v1/health"),
    }
    exec(handler_code, namespace)
    return namespace


def request(helper, *, method="GET", path="/token", headers=None):
    headers = headers if headers is not None else token_headers()
    raw = f"{method} {path} HTTP/1.1\r\n"
    raw += "".join(f"{key}: {value}\r\n" for key, value in headers.items())
    handler = object.__new__(helper["Handler"])
    handler.server = SimpleNamespace(server_address=("127.0.0.1", PORT))
    handler.client_address = ("127.0.0.1", 12345)
    handler.connection = Mock(gettimeout=Mock(return_value=None))
    handler.rfile = io.BytesIO((raw + "\r\n").encode("ascii"))
    handler.wfile = io.BytesIO()
    handler.handle_one_request()
    head, body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)
    status_line, header_bytes = head.split(b"\r\n", 1)
    return (int(status_line.split()[1]), BytesParser().parsebytes(header_bytes),
            json.loads(body) if body else None)


def token_headers(origin=ORIGIN):
    headers = {"Host": f"127.0.0.1:{PORT}", "X-Uoink-Client": "uoink-extension"}
    if origin is not None:
        headers["Origin"] = origin
    return headers


def test_manifest_public_key_derives_pinned_id():
    manifest = json.loads((ROOT / "extension/manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(base64.b64decode(manifest["key"], validate=True)).hexdigest()[:32]
    derived_id = "".join(chr(ord("a") + int(n, 16)) for n in digest)
    assert derived_id == PINNED_ID


def test_default_allowlist_is_pinned(helper):
    assert helper["_allowed_extension_ids"]() == {PINNED_ID}


@pytest.mark.parametrize("configured", [OTHER_ID, [OTHER_ID, EDGE_ID], (OTHER_ID, EDGE_ID)])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_configured_ids_add_to_pin_and_to_each_other(helper, configured, method):
    helper["os"].environ["UOINK_EXTENSION_IDS"] = f" {MOZ_ID}, ,{OTHER_ID} "
    helper["_read_settings"].return_value = {"extension_ids": configured}
    expected = {PINNED_ID, MOZ_ID, OTHER_ID}
    if not isinstance(configured, str):
        expected.add(EDGE_ID)
    assert helper["_allowed_extension_ids"]() == expected
    for extension_id in expected:
        scheme = "moz-extension" if extension_id == MOZ_ID else "chrome-extension"
        origin = f"{scheme}://{extension_id}"
        status, headers, body = request(helper, method=method, headers=token_headers(origin))
        assert status == 200
        assert body == {"ok": True, "token": TEST_TOKEN}
        assert headers["Access-Control-Allow-Origin"] == origin


@pytest.mark.parametrize("settings", [{}, {"extension_ids": ""}, {"extension_ids": []},
                                     {"extension_ids": None}, {"extension_ids": 17}])
def test_empty_or_invalid_settings_cannot_unpin(helper, settings):
    helper["os"].environ["UOINK_EXTENSION_IDS"] = " , "
    helper["_read_settings"].return_value = settings
    assert helper["_allowed_extension_ids"]() == {PINNED_ID}


def test_unreadable_settings_cannot_unpin(helper):
    helper["_read_settings"].side_effect = OSError("synthetic settings failure")
    assert helper["_allowed_extension_ids"]() == {PINNED_ID}
    assert request(helper)[0] == 200
    assert request(helper, headers=token_headers(f"chrome-extension://{OTHER_ID}"))[0] == 403


@pytest.mark.parametrize("client", [{"X-Uoink-Client": "uoink-extension"},
                                   {"X-Yoink-Client": "yoink-extension"}])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_pinned_extension_can_mint_with_current_or_legacy_header(helper, client, method):
    headers = {"Host": f"localhost:{PORT}", "Origin": ORIGIN,
               "Sec-Fetch-Site": "none", **client}
    status, response_headers, body = request(helper, method=method, headers=headers)
    assert status == 200
    assert body == {"ok": True, "token": TEST_TOKEN}
    assert response_headers["Access-Control-Allow-Origin"] == ORIGIN


@pytest.mark.parametrize("origin", [
    f"chrome-extension://{OTHER_ID}", f"moz-extension://{MOZ_ID}",
    ORIGIN + "/", ORIGIN + "/popup.html", ORIGIN + ":80", ORIGIN + "?q=1",
    ORIGIN + "#fragment", ORIGIN + ".attacker.test", ORIGIN + "@attacker.test",
    f"chrome-extension://attacker@{PINNED_ID}", ORIGIN + " " + ORIGIN,
    "chrome-extension://", "null", "", "https://attacker.test",
    f"http://127.0.0.1:{PORT}",
])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_unlisted_or_malformed_origins_cannot_mint_or_receive_cors(helper, origin, method):
    headers = token_headers(origin)
    headers["Sec-Fetch-Site"] = "none"
    status, response_headers, body = request(helper, method=method, headers=headers)
    assert status == 403
    assert "token" not in body
    assert response_headers["Access-Control-Allow-Origin"] is None
    status, response_headers, _ = request(helper, method="OPTIONS", headers=headers)
    assert status == 200
    assert response_headers["Access-Control-Allow-Origin"] is None
    assert response_headers["Access-Control-Allow-Private-Network"] is None
    assert helper["_token_request_times"] == []


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_pinned_preflight_preserves_auth_headers_and_pna(helper, method):
    headers = token_headers()
    headers.update({"Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "X-Uoink-Client",
                    "Access-Control-Request-Private-Network": "true"})
    status, response_headers, _ = request(helper, method="OPTIONS", headers=headers)
    assert status == 200
    assert response_headers["Access-Control-Allow-Origin"] == ORIGIN
    assert response_headers["Access-Control-Allow-Private-Network"] == "true"
    assert "X-Uoink-Client" in response_headers["Access-Control-Allow-Headers"]
    assert "X-Uoink-Token" in response_headers["Access-Control-Allow-Headers"]
    assert method in response_headers["Access-Control-Allow-Methods"].split(", ")


@pytest.mark.parametrize("host", [f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}"])
def test_no_origin_dashboard_and_webview_bootstrap(helper, host):
    headers = token_headers(None)
    headers.update({"Host": host, "Sec-Fetch-Site": "same-origin"})
    status, response_headers, body = request(helper, headers=headers)
    assert status == 200
    assert body == {"ok": True, "token": TEST_TOKEN}
    assert response_headers["Access-Control-Allow-Origin"] is None


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("site", [None, "", "none", "cross-site", "same-site", "null"])
def test_no_origin_requires_explicit_trusted_fetch_metadata(helper, site, method):
    headers = token_headers(None)
    if site is not None:
        headers["Sec-Fetch-Site"] = site
    status, _, body = request(helper, method=method, headers=headers)
    assert status == 403
    assert "token" not in body


@pytest.mark.parametrize("host", [None, "", "attacker.test", f"localhost:{PORT + 1}"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_no_origin_requires_loopback_host(helper, host, method):
    headers = token_headers(None)
    headers["Sec-Fetch-Site"] = "same-origin"
    if host is None:
        headers.pop("Host")
    else:
        headers["Host"] = host
    status, _, body = request(helper, method=method, headers=headers)
    assert status == 403
    assert "token" not in body


@pytest.mark.parametrize("origin", ["https://www.youtube.com", "https://attacker.test",
                                    f"chrome-extension://{OTHER_ID}", "null", ""])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_fetch_metadata_cannot_override_a_present_untrusted_origin(helper, origin, method):
    headers = token_headers(origin)
    headers["Sec-Fetch-Site"] = "same-origin"
    assert request(helper, method=method, headers=headers)[0] == 403


@pytest.mark.parametrize("client", [None, "", "wrong-client"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_client_header_still_required(helper, client, method):
    headers = token_headers()
    if client is None:
        headers.pop("X-Uoink-Client")
    else:
        headers["X-Uoink-Client"] = client
    assert request(helper, method=method, headers=headers)[0] == 403


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE", "OPTIONS"])
def test_host_gate_still_precedes_routes_and_valid_token(helper, method):
    headers = token_headers()
    headers.update({"Host": "attacker.test", "X-Uoink-Token": TEST_TOKEN})
    status, _, body = request(helper, method=method, headers=headers)
    assert status == 403
    assert body == {"ok": False, "error": "forbidden host"}


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_pinned_origin_does_not_replace_bearer_auth(helper, method):
    status, _, body = request(helper, method=method, path="/settings", headers=token_headers())
    assert status == 403
    assert body == {"ok": False, "error": "missing or invalid token"}


@pytest.mark.parametrize("path", ["/token/", "/token/other", "/images", "/corpus/import"])
def test_token_post_exception_does_not_open_other_post_routes(helper, path):
    status, _, body = request(helper, method="POST", path=path)
    assert status == 403
    assert body == {"ok": False, "error": "missing or invalid token"}


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_token_rate_limit_still_applies(helper, method):
    for _ in range(10):
        assert request(helper, method=method)[0] == 200
    status, _, body = request(helper, method=method)
    assert status == 429
    assert "token" not in body


def test_pinned_extension_cannot_pass_dashboard_confirmation_gate(helper):
    handler = object.__new__(helper["Handler"])
    handler.headers = token_headers()
    handler.server = SimpleNamespace(server_address=("127.0.0.1", PORT))
    assert handler._is_dashboard_origin() is False


@pytest.mark.parametrize("headers,status", [
    ({"Content-Type": "text/plain", "Content-Length": "2"}, 415),
    ({"Content-Type": "application/json", "Content-Length": str(64 * 1024 + 1)}, 413),
])
def test_body_type_and_size_limits_still_apply(helper, headers, status):
    handler = object.__new__(helper["Handler"])
    handler.headers = headers
    handler.rfile = io.BytesIO(b"{}")
    with pytest.raises(helper["Handler"]._BodyError) as error:
        handler._read_json_body()
    assert error.value.status == status
    assert handler.rfile.tell() == 0


@pytest.mark.parametrize("extra,status", [
    ({}, 200),
    ({"Content-Length": "0"}, 200),
    ({"Content-Length": "2", "Content-Type": "application/json"}, 400),
    ({"Content-Length": "2", "Content-Type": "text/plain"}, 400),
    ({"Content-Length": str(64 * 1024 + 1)}, 413),
    ({"Content-Length": "-1"}, 400),
    ({"Content-Length": "invalid"}, 400),
    ({"Transfer-Encoding": "chunked"}, 400),
])
def test_token_post_is_bodyless_and_never_reads_a_body(helper, monkeypatch, extra, status):
    def no_body_read(*args, **kwargs):
        raise AssertionError("Token bootstrap must not read a request body")

    class HeadersOnly(io.BytesIO):
        read = no_body_read

    monkeypatch.setattr(io, "BytesIO", HeadersOnly)
    headers = {**token_headers(), "Sec-Fetch-Site": "none", **extra}
    actual, _, body = request(helper, method="POST", headers=headers)
    assert actual == status
    if status == 200:
        assert body == {"ok": True, "token": TEST_TOKEN}
    else:
        assert "token" not in body
        assert helper["_token_request_times"] == []


def test_untrusted_post_is_rejected_before_body_validation(helper):
    headers = {**token_headers(f"chrome-extension://{OTHER_ID}"),
               "Content-Length": str(64 * 1024 + 1)}
    status, _, body = request(helper, method="POST", headers=headers)
    assert status == 403
    assert body == {"ok": False, "error": "forbidden"}


def test_extension_token_mints_use_origin_carrying_post():
    node = shutil.which("node")
    assert node, "Node.js is required for the offline extension token harness"
    result = subprocess.run(
        [node, "--test", "--test-reporter=tap", "tests/js/sec_token_pin_test.mjs"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    passed = re.findall(r"^# pass (\d+)$", result.stdout, re.MULTILINE)
    assert len(passed) == 1 and int(passed[0]) >= 5, output
    assert re.findall(r"^# fail (\d+)$", result.stdout, re.MULTILINE) == ["0"], output

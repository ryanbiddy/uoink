"""Offline regressions for audit #2 (public diagnostics) and #8 (framing).

Compile the real handlers and payload builders without importing server.py,
which initializes app state and credentials. Requests use BytesIO; filesystem,
tool and credential probes use synthetic fixtures. No sockets or helper run.
"""
from __future__ import annotations

import ast
import io
import json
import re
import secrets
import subprocess
import threading
import time
from datetime import datetime
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

import pytest
import uoink_usage


ROOT = Path(__file__).resolve().parents[1]
PORT = 43871  # Host fixture only; nothing listens here.
PINNED_ORIGIN = "chrome-extension://bkcapfidedhfcjpmjabeopfbcjcbmdmi"
PRIVATE_ROOT = PureWindowsPath("C:/Users/synthetic-private-user/private-corpus")
PRIVATE_DETAIL = f"failure in {PRIVATE_ROOT}; /home/synthetic-private-user/tool"
HTML = b"<!doctype html><title>Synthetic local UI</title>"


@pytest.fixture(scope="module")
def surface_code():
    names = {
        "ALLOWED_ORIGINS", "ALLOWED_HOST_NAMES", "PINNED_EXTENSION_ID",
        "MAX_BODY_BYTES", "_allowed_extension_ids", "_reports_live_extract", "Handler",
        "_diagnose_payload", "_public_diagnose_payload", "_build_diagnose_payload",
        "_keyring_display_name", "_path_integrity_status",
        "_library_health_payload", "_heartbeat_payload", "_parse_utc_stamp",
        "doctor_payload",
    }
    tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
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
def helper(surface_code):
    migration = {
        "app_data": {
            "old_root": str(PRIVATE_ROOT / "old"),
            "new_root": str(PRIVATE_ROOT / "new"),
            "old_exists": True, "new_exists": True,
            "complete": False, "migrated_marker": True,
        },
        "desktop_corpus": {
            "legacy_root": str(PRIVATE_ROOT / "legacy"),
            "new_root": str(PRIVATE_ROOT / "current"),
            "legacy_present": True, "new_present": False,
        },
        "keyring_legacy_present": True,
    }
    library = {
        "status": "waiting_for_client", "waiting_for_client": True,
        "ready": 3, "leased": 0, "run_revision": 7,
        "recovery_state": None, "error_code": None,
    }
    idx = Mock()
    idx.list_content_paths.return_value = [
        {"corpus_path": str(PRIVATE_ROOT / "saved.md")},
        {"corpus_path": str(PRIVATE_ROOT / "missing.md")},
    ]
    namespace = {
        "uoink_usage": uoink_usage,
        "__name__": "offline_public_surfaces",
        "BaseHTTPRequestHandler": BaseHTTPRequestHandler,
        "HOST": "127.0.0.1", "PORT": PORT, "VERSION": "test",
        "TOKEN": "synthetic-public-surfaces-token",
        "os": SimpleNamespace(environ={}), "sys": SimpleNamespace(platform="win32"),
        "json": json, "re": re,
        "secrets": secrets, "urlparse": urlparse, "time": time,
        "datetime": datetime, "log": Mock(),
        "DESKTOP_ROOT": PRIVATE_ROOT, "INDEX_PATH": PRIVATE_ROOT / "index.db",
        "DATA_ROOT": PRIVATE_ROOT / "data", "_OUTPUT_ROOT_FALLBACK": True,
        "DASHBOARD_PATH": Mock(read_bytes=Mock(return_value=HTML)),
        "SPLASH_PATH": Mock(read_bytes=Mock(return_value=HTML)),
        "_platform": SimpleNamespace(platform_detail=lambda: "Windows AMD64",
                                     sys=SimpleNamespace(platform="win32"),
                                     media_capability=lambda: {"available": True, "code": None, "reason": None},
                                     keyring_display_name=lambda: "Windows Credential Manager"),
        "_is_writable_dir": Mock(return_value=True),
        "_read_settings": Mock(return_value={
            "anthropic_key_invalid": False, "anthropic_key_set": True,
            "output_dir": str(PRIVATE_ROOT), "librarian_apply_enabled": True,
            "whisper_model": "base",
        }),
        "_get_saved_anthropic_key": Mock(return_value="synthetic-key"),
        "_credential_store_error": Mock(return_value=None),
        "migrate_install": SimpleNamespace(migration_status=Mock(return_value=migration)),
        "YTDLP_CMD": [str(PRIVATE_ROOT / "yt-dlp.exe")],
        "_probe_command": Mock(return_value=("ok", "synthetic version")),
        "_get_index": Mock(return_value=idx), "_index_singleton": idx,
        "_PATH_INTEGRITY_TTL": 60.0,
        "_path_integrity_cache": {"checked_at": 0.0, "result": None},
        "Path": Mock(side_effect=lambda p: SimpleNamespace(
            exists=lambda: not str(p).endswith("missing.md"))),
        "_mcp_tools_module": Mock(return_value=SimpleNamespace(
            LIBRARY_CONTRACT_VERSION="test", library_status=Mock(return_value=library))),
        "_active_migration_version": 2, "_index_recovering": True,
        "index": SimpleNamespace(
            latest_schema_version=lambda: 3,
            schema_migration_status=Mock(return_value={"pending": False})),
        "_helper_health_status": Mock(return_value={"ok": True}),
        "_doctor_heartbeat": Mock(return_value={"stale": False}),
        "_mcp_stdio_selfcheck": Mock(return_value={"ok": True}),
        "_podcast_corpus_reconciliation_status": Mock(return_value={"ok": True}),
        "whisper_runner": SimpleNamespace(
            normalize_model=lambda value: "base",
            is_whisperx_available=lambda: True,
            is_model_downloaded=lambda root, model: False),
        "suite_service": SimpleNamespace(
            MANIFEST_PATH="/.well-known/suite-service.json",
            HEALTH_PATH="/api/suite/v1/health",
            utc_now=lambda: "2026-10-15T12:00:30Z"),
        "_heartbeat_lock": threading.Lock(), "_PODCAST_FEED_TICK_SEC": 30,
        "_HEARTBEAT_STALE_AFTER_SEC": 90,
        "_last_successful_tick_at": "2026-10-15T12:00:00Z",
        "_heartbeat": {
            "last_tick_completed_at": "2026-10-15T12:00:00Z",
            "last_successful_poll_at": "2026-10-15T12:00:00Z",
            "last_failed_poll_at": None, "last_poll_error": None,
            "last_ingest_completed_at": None, "last_tick_ok": True,
            "last_tick_polls": 2, "last_tick_failed_polls": 0,
            "ticks_completed": 1, "polls_ok": 2, "polls_failed": 0,
            "ingests_completed": 0,
        },
    }
    exec(surface_code, namespace)
    return namespace


def request(helper, path, *, method="GET", headers=None):
    headers = {"Host": f"127.0.0.1:{PORT}", **(headers or {})}
    raw = f"{method} {path} HTTP/1.1\r\n"
    raw += "".join(f"{key}: {value}\r\n" for key, value in headers.items() if value is not None)
    handler = object.__new__(helper["Handler"])
    handler.server = SimpleNamespace(server_address=("127.0.0.1", PORT))
    handler.client_address = ("127.0.0.1", 12345)
    handler.rfile = io.BytesIO((raw + "\r\n").encode("ascii"))
    handler.wfile = io.BytesIO()
    handler.handle_one_request()
    head, body = handler.wfile.getvalue().split(b"\r\n\r\n", 1)
    status_line, header_bytes = head.split(b"\r\n", 1)
    response_headers = BytesParser().parsebytes(header_bytes)
    if body and response_headers.get_content_type() == "application/json":
        body = json.loads(body)
    return int(status_line.split()[1]), response_headers, body


def assert_public(payload):
    """Check the entire serialized payload, including nested details/warnings."""
    text = json.dumps(payload).lower()
    for private in ("synthetic-private-user", "private-corpus", "synthetic-key",
                    "anthropic_key", "keyring_legacy_present", "saved key",
                    "no key configured", "no key entered", "key didn't carry"):
        assert private not in text
    assert not re.search(r"[a-z]:[\\/]|/home/|/users/|\\\\", text)


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_non_darwin_diagnose_keeps_bare_ffmpeg_without_new_resolver(helper, platform):
    helper["_platform"].sys.platform = platform
    assert not hasattr(helper["_platform"], "media_binary")
    payload = helper["_build_diagnose_payload"](public=True)
    helper["_probe_command"].assert_any_call(["ffmpeg", "-version"])
    assert next(row for row in payload["checks"] if row["name"] == "ffmpeg_available")["status"] == "ok"


@pytest.mark.parametrize("writable", [True, False])
@pytest.mark.parametrize("origin", [None, "https://www.youtube.com", PINNED_ORIGIN])
def test_diagnose_has_no_paths_or_key_flags(helper, writable, origin):
    helper["_is_writable_dir"].return_value = writable
    status, _, payload = request(helper, "/diagnose", headers={"Origin": origin} if origin else {})
    assert status == 200
    assert_public(payload)
    assert payload["ok"] is True
    assert payload["output_root_fallback"] is True
    checks = {check["name"]: check for check in payload["checks"]}
    for name in ("output_root_writable", "index_db_writable"):
        assert checks[name]["status"] == ("ok" if writable else "error")
    assert checks["path_integrity"]["status"] == "error"
    assert "1 of 2" in checks["path_integrity"]["detail"]
    assert payload["migration"] == {
        "app_data": {"old_exists": True, "new_exists": True,
                     "complete": False, "migrated_marker": True},
        "desktop_corpus": {"legacy_present": True, "new_present": False},
    }


@pytest.mark.parametrize("writable", [True, False])
@pytest.mark.parametrize("headers", [
    {}, {"Origin": PINNED_ORIGIN}, {"Origin": "https://www.youtube.com"},
    {"Sec-Fetch-Site": "same-origin"},
])
def test_public_index_check_has_no_install_folder_detail(helper, writable, headers):
    helper["_is_writable_dir"].return_value = writable
    status, _, payload = request(helper, "/diagnose", headers=headers)
    assert status == 200
    check = next(c for c in payload["checks"] if c["name"] == "index_db_writable")
    assert check["status"] == ("ok" if writable else "error")
    # setup.js treats any nonempty detail as the path for its Open folder
    # button. Omit the field entirely so it keeps its static installation hint.
    assert "detail" not in check
    if not writable:
        assert any(w.startswith("Index database is not writable.") for w in payload["warnings"])


@pytest.mark.parametrize("key,invalid,legacy", [
    ("", False, False), ("synthetic-key", False, True), ("", True, True),
])
def test_public_diagnosis_is_independent_of_saved_key_state(helper, key, invalid, legacy):
    baseline = request(helper, "/diagnose")[2]
    helper["_read_settings"].return_value["anthropic_key_invalid"] = invalid
    helper["_get_saved_anthropic_key"].return_value = key
    helper["migrate_install"].migration_status.return_value["keyring_legacy_present"] = legacy
    payload = request(helper, "/diagnose")[2]
    assert_public(payload)
    assert payload == baseline
    helper["_get_saved_anthropic_key"].assert_not_called()


@pytest.mark.parametrize("site", ["same-origin", "none"])
@pytest.mark.parametrize("host", [f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}"])
@pytest.mark.parametrize("client", [None, "uoink-splash"])
def test_local_splash_gets_only_key_ready_boolean(helper, site, host, client):
    public = request(helper, "/diagnose")[2]
    status, _, payload = request(helper, "/diagnose", headers={
        "Host": host, "Sec-Fetch-Site": site, "X-Uoink-Client": client,
    })
    assert status == 200
    assert payload.pop("anthropic_key_valid") is True
    assert payload == public
    assert_public(payload)
    helper["_get_saved_anthropic_key"].assert_called_once_with()


@pytest.mark.parametrize("key,invalid,expected", [
    ("synthetic-key", True, False), ("", True, False),
    ("", False, None), ("   ", False, None),
])
def test_splash_preserves_invalid_and_missing_key_states(helper, key, invalid, expected):
    helper["_get_saved_anthropic_key"].return_value = key
    helper["_read_settings"].return_value["anthropic_key_invalid"] = invalid
    status, _, payload = request(helper, "/diagnose", headers={"Sec-Fetch-Site": "same-origin"})
    assert status == 200
    if expected is None:
        # The shipped splash treats an absent value as "Add your key";
        # false means "Update your key", so a missing key must stay absent.
        assert "anthropic_key_valid" not in payload
    else:
        assert payload.pop("anthropic_key_valid") is expected
    assert_public(payload)


@pytest.mark.parametrize("origin", [
    "https://www.youtube.com", "https://m.youtube.com", "https://youtube.com",
    PINNED_ORIGIN, PINNED_ORIGIN.replace("chrome-", "moz-"),
    "https://attacker.test", f"http://127.0.0.1:{PORT}", "null", "",
])
@pytest.mark.parametrize("site", [None, "same-origin", "none", "cross-site"])
def test_present_origin_never_gets_splash_key_readiness(helper, origin, site):
    status, _, payload = request(helper, "/diagnose", headers={
        "Origin": origin, "Sec-Fetch-Site": site, "X-Uoink-Client": "uoink-splash",
    })
    assert status == 200
    assert_public(payload)
    helper["_get_saved_anthropic_key"].assert_not_called()


@pytest.mark.parametrize("site", [None, "", "cross-site", "same-site", "null"])
def test_no_origin_without_local_fetch_metadata_gets_no_key_readiness(helper, site):
    status, _, payload = request(helper, "/diagnose", headers={
        "Sec-Fetch-Site": site, "X-Uoink-Client": "uoink-splash",
    })
    assert status == 200
    assert_public(payload)
    helper["_get_saved_anthropic_key"].assert_not_called()


@pytest.mark.parametrize("host,status", [
    (None, 200), ("", 403), ("attacker.test", 403), (f"localhost:{PORT + 1}", 403),
])
def test_splash_readiness_requires_present_allowed_host(helper, host, status):
    actual, _, payload = request(helper, "/diagnose", headers={
        "Host": host, "Sec-Fetch-Site": "same-origin",
    })
    assert actual == status
    assert_public(payload)
    helper["_get_saved_anthropic_key"].assert_not_called()


@pytest.mark.parametrize("headers", [
    {}, {"Origin": PINNED_ORIGIN}, {"Origin": "https://www.youtube.com"},
    {"Sec-Fetch-Site": "same-origin"},
])
def test_http_cannot_select_console_diagnostics_even_with_token(helper, headers):
    console = helper["_diagnose_payload"] = Mock(wraps=helper["_diagnose_payload"])
    diagnose = helper["_public_diagnose_payload"] = Mock(wraps=helper["_public_diagnose_payload"])
    status, _, payload = request(helper, "/diagnose?public=false&local_ui=true", headers={
        **headers, "X-Uoink-Token": helper["TOKEN"],
    })
    assert status == 200
    local_ui = "Sec-Fetch-Site" in headers
    diagnose.assert_called_once_with(local_ui=local_ui)
    console.assert_not_called()
    if local_ui:
        assert payload.pop("anthropic_key_valid") is True
    assert_public(payload)


def test_doctor_accepts_no_argument_diagnosis(helper):
    # Existing doctor callers and tests replace this hook with a no-arg
    # function. Keep that contract independent of the HTTP builder.
    diagnosis = {"ok": True}
    helper["_diagnose_payload"] = lambda: diagnosis
    assert helper["doctor_payload"]()["diagnose"] is diagnosis


@pytest.mark.parametrize("key,invalid,expected,set_status,valid_status", [
    ("synthetic-key", False, True, "ok", "ok"),
    ("synthetic-key", True, False, "warning", "error"),
    ("", False, "skipped", "warning", "skipped"),
])
@pytest.mark.parametrize("writable", [True, False])
def test_console_doctor_keeps_paths_versions_and_key_status(
        helper, key, invalid, expected, set_status, valid_status, writable):
    helper["_get_saved_anthropic_key"].return_value = key
    helper["_read_settings"].return_value["anthropic_key_invalid"] = invalid
    helper["_is_writable_dir"].return_value = writable
    helper["_probe_command"].side_effect = [("ok", "test-yt-version"), ("ok", "test-ffmpeg-version")]
    payload = helper["doctor_payload"]()
    diag = payload["diagnose"]
    checks = {check["name"]: check for check in diag["checks"]}
    assert str(PRIVATE_ROOT) in checks["output_root_writable"]["detail"]
    assert str(PRIVATE_ROOT) in checks["index_db_writable"]["detail"]
    assert checks["yt_dlp_available"]["detail"] == "yt-dlp test-yt-version"
    assert checks["ffmpeg_available"]["detail"] == "test-ffmpeg-version"
    assert checks["anthropic_key_set"]["status"] == set_status
    assert checks["anthropic_key_valid"]["status"] == valid_status
    assert diag["anthropic_key_valid"] == expected
    assert diag["migration"] == helper["migrate_install"].migration_status.return_value
    assert str(PRIVATE_ROOT) in " ".join(diag["warnings"])
    assert "synthetic-key" not in json.dumps(payload)
    if not key:
        assert any("key didn't carry over" in warning for warning in diag["warnings"])


def test_console_doctor_keeps_probe_and_credential_store_errors(helper):
    helper["_probe_command"].return_value = ("error", PRIVATE_DETAIL)
    helper["_credential_store_error"].return_value = OSError(PRIVATE_DETAIL)
    checks = {check["name"]: check for check in helper["doctor_payload"]()["diagnose"]["checks"]}
    for name in ("yt_dlp_available", "ffmpeg_available", "keyring_available"):
        assert checks[name]["detail"] == PRIVATE_DETAIL


def test_console_diagnosis_keeps_migration_error_details(helper):
    helper["migrate_install"].migration_status.side_effect = OSError(PRIVATE_DETAIL)
    assert helper["_diagnose_payload"]()["migration"] == {"error": PRIVATE_DETAIL}


@pytest.mark.parametrize("probe_status", ["ok", "error"])
def test_diagnose_omits_tool_output_and_credential_store_exception_paths(helper, probe_status):
    helper["_probe_command"].return_value = (probe_status, PRIVATE_DETAIL)
    helper["_credential_store_error"].return_value = OSError(PRIVATE_DETAIL)
    status, _, payload = request(helper, "/diagnose")
    assert status == 200
    assert_public(payload)
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["yt_dlp_available"]["status"] == probe_status
    assert checks["ffmpeg_available"]["status"] == probe_status
    assert checks["keyring_available"]["status"] == "warning"


def _setup_diagnostic_rows(payload):
    """Run the shipped diagnostic renderer with an in-memory DOM, without boot I/O."""
    script = r"""
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { makeEnv } from './tests/js/ext_fake_env.mjs';
const source = readFileSync('extension/setup.js', 'utf8');
const start = source.indexOf('function renderDiagnose(body)');
const end = source.indexOf('async function checkConnection(', start);
assert.ok(start >= 0 && end > start, 'setup diagnostic renderer must exist');
const env = makeEnv();
for (const id of ['diagnose-list', 'diagnose']) {
  const el = env.document.createElement('div');
  el.id = id;
  env.document.body.appendChild(el);
}
env.ctx.payload = JSON.parse(readFileSync(0, 'utf8'));
env.runSource('const $ = id => document.getElementById(id);\n' +
  source.slice(start, end) + '\nrenderDiagnose(payload);');
const list = env.document.getElementById('diagnose-list');
console.log(JSON.stringify(list.children.map(row => ({
  text: row.textContent,
  detail: row.children[1]?.textContent,
  actions: row._all().filter(el => ['A', 'BUTTON'].includes(el.tagName)).length,
}))));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script], input=json.dumps(payload),
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_public_failure_details_do_not_offer_start_helper(helper):
    # A missing tool or credential store means the helper IS running; its row
    # must not get the setup page's "Start helper" button.
    helper["_probe_command"].return_value = ("error", PRIVATE_DETAIL)
    helper["_credential_store_error"].return_value = OSError(PRIVATE_DETAIL)
    helper["migrate_install"].migration_status.side_effect = OSError(PRIVATE_DETAIL)
    status, _, payload = request(helper, "/diagnose")
    assert status == 200
    rows = _setup_diagnostic_rows(payload)
    assert len(rows) == len(payload["checks"])
    for check, row in zip(payload["checks"], rows):
        assert row["actions"] == 0, f"diagnostics must not offer Start helper: {row}"
        assert "Start helper" not in row["text"]
        assert row["detail"] == str(check.get("detail") or check["status"])
    checks = {check["name"]: check for check in payload["checks"]}
    for name in ("yt_dlp_available", "ffmpeg_available", "keyring_available"):
        check = checks[name]
        assert check["status"] != "ok", check
        row = rows[payload["checks"].index(check)]
        assert "Needs attention" in row["text"], row
    assert payload["migration"]["error"] == "migration status unavailable; details are in the Uoink log"


def test_migration_failure_is_generic(helper):
    helper["migrate_install"].migration_status.side_effect = OSError(PRIVATE_DETAIL)
    status, _, payload = request(helper, "/diagnose")
    assert status == 200
    assert_public(payload)
    assert payload["migration"]["error"]


def test_migration_projection_does_not_forward_new_fields(helper):
    migration = helper["migrate_install"].migration_status.return_value
    migration["future_detail"] = PRIVATE_DETAIL
    migration["app_data"]["future_detail"] = PRIVATE_DETAIL
    migration["desktop_corpus"]["future_detail"] = PRIVATE_DETAIL
    assert_public(request(helper, "/diagnose")[2])


@pytest.mark.parametrize("path", ["/health", "/ping"])
@pytest.mark.parametrize("broken_index", [False, True])
@pytest.mark.parametrize("headers", [
    {}, {"Sec-Fetch-Site": "same-origin"}, {"Origin": PINNED_ORIGIN},
    {"Origin": "https://www.youtube.com"},
])
def test_health_preserves_counts_and_readiness_without_paths_or_key_flags(
        helper, path, broken_index, headers):
    if broken_index:
        helper["_get_index"].side_effect = OSError(PRIVATE_DETAIL)
        helper["_mcp_tools_module"].side_effect = OSError(PRIVATE_DETAIL)
    status, _, payload = request(helper, path, headers=headers)
    assert status == 200
    assert_public(payload)
    assert payload["ok"] is True
    assert payload["migration_pending"] is True
    assert payload["index_recovering"] is True
    assert payload["output_root_fallback"] is True
    assert payload["whisperx_available"] is True
    assert payload["whisperx_model_loaded"] is False
    assert payload["heartbeat"]["counts"]["polls_ok"] == 2
    assert payload["heartbeat"]["freshness"]["state"] == "fresh"
    assert payload["library"]["apply_enabled"] is True
    assert payload["path_integrity"]["ok"] is False
    if broken_index:
        assert payload["path_integrity"]["checked"] == 0
        assert payload["path_integrity"]["error"]
        assert payload["library"]["status"] == "error"
    else:
        assert payload["path_integrity"]["checked"] == 2
        assert payload["path_integrity"]["missing"] == 1
        assert payload["library"]["waiting_for_client"] is True
        assert payload["library"]["ready"] == 3


@pytest.mark.parametrize("path", ["/dashboard", "/dashboard/", "/dashboard?tab=settings",
                                  "/splash", "/splash/", "/splash?first_run=1"])
@pytest.mark.parametrize("origin", [None, "https://www.youtube.com", PINNED_ORIGIN])
def test_local_html_cannot_be_framed(helper, path, origin):
    status, headers, body = request(helper, path, headers={"Origin": origin} if origin else {})
    assert status == 200
    assert body == HTML
    assert headers.get_content_type() == "text/html"
    assert headers["Content-Security-Policy"] == "frame-ancestors 'none'"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Content-Length"] == str(len(HTML))


@pytest.mark.parametrize("path", ["/health", "/ping", "/diagnose", "/dashboard", "/splash"])
@pytest.mark.parametrize("method", ["GET", "OPTIONS"])
def test_public_surfaces_still_reject_rebinding_hosts(helper, path, method):
    status, _, payload = request(helper, path, method=method, headers={"Host": "attacker.test"})
    assert status == 403
    assert payload == {"ok": False, "error": "forbidden host"}

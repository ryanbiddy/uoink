"""Offline regressions for audit #6 (import paths) and #7 (error details).

Compile the real handlers/functions without importing server.py or initializing
app state. HTTP uses BytesIO, imports use temporary exports and a fake index,
and credentials/tool failures are synthetic. No sockets or helper processes.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import logging
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
PORT = 43871  # HTTP Host fixture only; nothing listens here.
KEY = "sk-ant-api03-synthetic-private-key"
PRIVATE = (
    'tool failed at "C:\\Users\\Synthetic Person\\private\\tool.exe" '
    'and /home/synthetic-private-user/tool '
    'https://synthetic-user:synthetic-password@example.test/private '
    f'api_key={KEY}'
)
PAYLOAD = {"format": "uoink-corpus-export", "format_version": 1, "tables": {}}


@pytest.fixture(scope="module")
def source_tree():
    return ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))


@pytest.fixture
def helper(source_tree, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network access is forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    names = {
        "Handler", "ALLOWED_ORIGINS", "ALLOWED_HOST_NAMES", "PINNED_EXTENSION_ID",
        "MAX_BODY_BYTES", "EXPORTS_DIRNAME", "_allowed_extension_ids",
        "_STRICT_JSON_ROUTE_PREFIXES",
        "_strict_json_route", "_path_has_parent_ref", "import_corpus_data",
        "run_cli", "rebuild_index_from_disk", "_sanitize_error", "_subprocess_output",
        "_youtube_rate_limit_detail",
        "machine_error_detail", "friendly_error", "_plain_error_from_text",
        "_source_name_from_error", "ExtractionPhaseError", "_public_job",
        "_index_job_row", "_record_single_extract_job", "_add_job_record",
        "_persist_jobs_locked", "_sanitize_single_job_result",
        "_update_job", "_podcast_transcription_worker", "_error_summary",
        "_redact_command_args", "_redact_error_credentials", "_redact_error_paths",
        "_ERROR_SANITIZE_INPUT_LIMIT", "_CREDENTIAL_FLAG_PATTERN",
        "_fetch_video_subtitles", "_comments_worker", "PlaylistJobCancelled",
    }
    nodes = []
    for node in source_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            nodes.append(node)
        elif isinstance(node, ast.Assign):
            assigned = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(n in names or n.endswith("_SANITIZE_RE")
                   or n == "_USERINFO_URL_RE" for n in assigned):
                nodes.append(node)
    output = tmp_path / "output"
    (output / "_exports").mkdir(parents=True)
    idx = Mock()
    idx.import_payload.return_value = {"style_anchors": {"imported": 1}}
    namespace = {
        "__name__": "offline_import_errors", "Path": Path,
        "BaseHTTPRequestHandler": BaseHTTPRequestHandler,
        "json": json, "re": re, "secrets": secrets, "subprocess": subprocess,
        "urlparse": urlparse, "os": SimpleNamespace(environ={}),
        "HOST": "127.0.0.1", "PORT": PORT, "TOKEN": "synthetic-test-token",
        "VERSION": "test", "DESKTOP_ROOT": output,
        "_read_settings": Mock(return_value={}), "_get_index": Mock(return_value=idx),
        "log": Mock(), "_error_detail_log": Mock(),
        "_now_iso": lambda: "2026-10-16T12:00:00", "_make_job_id": lambda: "job_test",
        "_jobs_lock": threading.Lock(), "_jobs": {},
        "_JOB_TERMINAL_STATES": {"completed", "failed", "cancelled"},
        "_supersede_terminal_single_jobs_locked": Mock(),
        "_resolve_corpus_path": Mock(return_value=None),
        "_normalize_long_video_mode": Mock(return_value="auto"),
        "_manual_extraction_ownership": lambda url: nullcontext(SimpleNamespace(
            ok=True, conflict=None, completed_while_waiting=False)),
        "_fetch_metadata": Mock(side_effect=RuntimeError(PRIVATE)),
        "_is_youtube_rate_limit": Mock(return_value=False),
        "_failure_phase": lambda exc, phase: phase,
        "INSTALL_HELP_URL": "https://example.test/install",
        "_run_backfill": Mock(),
        "_print_json": Mock(),
        "_install_isolation": SimpleNamespace(
            CLI_STOP="--isolated-stop", CLI_UPGRADE_CHECK="--isolated-upgrade-check",
            strip_cli=lambda argv: argv),
    }
    for name in ("LIBRARY_INTENT_ROUTE", "LIBRARY_MIRROR_INTENT_ROUTE",
                 "LIBRARY_MIRROR_ROUTE", "SOURCES_INTENT_ROUTE"):
        namespace[name] = "/unused/" + name.lower()
    exec(compile(ast.Module(body=ast.parse("from __future__ import annotations").body
                            + nodes, type_ignores=[]), str(ROOT / "server.py"), "exec"),
         namespace)
    # URL validation isn't under test; keep acquisition entirely synthetic.
    monkeypatch.setattr(namespace["Handler"], "_validate_url_interval",
                        lambda self, body: ("https://example.test/video", 30, None))
    return namespace


def request(helper, body, *, route="/corpus/import", headers=None):
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Host": f"127.0.0.1:{PORT}", "X-Uoink-Token": helper["TOKEN"],
        "Content-Type": "application/json", "Content-Length": str(len(payload)),
        **(headers or {}),
    }
    raw = f"POST {route} HTTP/1.1\r\n"
    raw += "".join(f"{k}: {v}\r\n" for k, v in headers.items() if v is not None)
    prefix = (raw + "\r\n").encode("ascii")
    handler = object.__new__(helper["Handler"])
    handler.server = SimpleNamespace(server_address=("127.0.0.1", PORT))
    handler.client_address = ("127.0.0.1", 12345)
    handler.rfile = io.BytesIO(prefix + payload)
    handler.wfile = io.BytesIO()
    handler.handle_one_request()
    head, result = handler.wfile.getvalue().split(b"\r\n\r\n", 1)
    return int(head.split()[1]), json.loads(result), handler.rfile.tell() - len(prefix)


def export_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(PAYLOAD), encoding="utf-8")
    return path


def assert_private_removed(detail):
    for secret in ("Synthetic", "Person", "private", "synthetic-private-user",
                   "synthetic-user", "synthetic-password", KEY):
        assert secret not in detail
    assert "tool failed" in detail


@pytest.mark.parametrize("relative", ["backup.json", "nested/backup.json"])
def test_import_accepts_exports_and_preserves_merge(helper, relative):
    path = export_file(helper["DESKTOP_ROOT"] / "_exports" / relative)
    status, result, _ = request(helper, {"path": str(path)})
    assert status == 200 and result["ok"] is True
    assert result["path"] == str(path.resolve())
    helper["_get_index"]().import_payload.assert_called_once_with(PAYLOAD)
    assert result["report"] == {"style_anchors": {"imported": 1}}


@pytest.mark.parametrize("location", ["outside", "root", "sibling", "parent", "relative"])
def test_import_rejects_escape_before_reading(helper, tmp_path, monkeypatch, location):
    output = helper["DESKTOP_ROOT"]
    paths = {
        "outside": tmp_path / "outside" / "backup.json",
        "root": output / "backup.json",
        "sibling": output / "_exports-other" / "backup.json",
        "parent": output / "_exports" / ".." / "backup.json",
        "relative": Path("output/_exports/backup.json"),
    }
    monkeypatch.chdir(tmp_path)
    path = export_file(paths[location])
    reads = Mock(wraps=Path.read_text)
    monkeypatch.setattr(Path, "read_text", lambda p, **kw: reads(p, **kw))
    status, result, _ = request(helper, {"path": str(path)})
    assert status == 400 and result["ok"] is False
    assert str(tmp_path) not in result["error"]
    reads.assert_not_called()
    helper["_get_index"].assert_not_called()


@pytest.mark.parametrize("link_kind", ["file", "directory", "exports"])
def test_resolved_link_targets_cannot_escape(helper, tmp_path, monkeypatch, link_kind):
    """Model resolve() results for symlinks/junctions without OS link privileges."""
    exports = helper["DESKTOP_ROOT"] / "_exports"
    alias = export_file(exports / "linked" / "backup.json")
    outside = export_file(tmp_path / "outside" / "backup.json")
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        if path == alias:
            return outside
        if link_kind == "directory" and path == alias.parent:
            return outside.parent
        if link_kind == "exports" and path == exports:
            return outside.parent
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    reads = Mock(wraps=Path.read_text)
    monkeypatch.setattr(Path, "read_text", lambda p, **kw: reads(p, **kw))
    status, result, _ = request(helper, {"path": str(alias)})
    assert status == 400 and result["ok"] is False
    reads.assert_not_called()
    helper["_get_index"].assert_not_called()


def test_import_reads_resolved_path_inside_exports(helper, monkeypatch):
    exports = helper["DESKTOP_ROOT"] / "_exports"
    target = export_file(exports / "target.json")
    alias = exports / "alias.json"
    alias.write_text("unresolved path must not be read", encoding="utf-8")
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda p, *a, **kw:
                        target if p == alias else original(p, *a, **kw))
    status, result, _ = request(helper, {"path": str(alias)})
    assert status == 200 and result["path"] == str(target)
    helper["_get_index"]().import_payload.assert_called_once_with(PAYLOAD)


def test_http_body_cannot_override_output_root(helper, tmp_path):
    path = export_file(tmp_path / "other" / "_exports" / "backup.json")
    status, result, _ = request(helper, {
        "path": str(path), "output_root": str(path.parent.parent)})
    assert status == 400 and result["ok"] is False
    helper["_get_index"].assert_not_called()


@pytest.mark.parametrize("location,allowed", [
    ("exports", True), ("nested", True), ("outside", False),
    ("root", False), ("relative", False), ("parent", False),
])
def test_cli_import_uses_the_same_exports_boundary(helper, tmp_path, monkeypatch,
                                                 location, allowed):
    output = helper["DESKTOP_ROOT"]
    paths = {
        "exports": output / "_exports" / "backup.json",
        "nested": output / "_exports" / "nested" / "backup.json",
        "outside": tmp_path / "backup.json",
        "root": output / "backup.json",
        "relative": Path("output/_exports/backup.json"),
        "parent": output / "_exports" / ".." / "backup.json",
    }
    monkeypatch.chdir(tmp_path)
    path = export_file(paths[location])
    reads = Mock(wraps=Path.read_text)
    monkeypatch.setattr(Path, "read_text", lambda p, **kw: reads(p, **kw))
    helper["run_cli"](["--import-corpus", str(path)])
    helper["_print_json"].assert_called_once()
    result = helper["_print_json"].call_args.args[0]
    assert result["ok"] is allowed
    if allowed:
        assert result["path"] == str(path.resolve())
        helper["_get_index"]().import_payload.assert_called_once_with(PAYLOAD)
    else:
        reads.assert_not_called()
        helper["_get_index"].assert_not_called()
        assert str(tmp_path) not in result["error"]


@pytest.mark.parametrize("kind", ["missing", "directory", "json", "utf8", "read", "payload"])
def test_import_failures_are_client_errors_without_private_details(helper, monkeypatch, kind):
    path = helper["DESKTOP_ROOT"] / "_exports" / "backup.json"
    if kind == "directory":
        path.mkdir()
    elif kind == "json":
        path.write_text("not json", encoding="utf-8")
    elif kind == "utf8":
        path.write_bytes(b"\xff\xfe")
    elif kind in {"read", "payload"}:
        export_file(path)
        if kind == "read":
            monkeypatch.setattr(Path, "read_text", Mock(side_effect=OSError(PRIVATE)))
        else:
            helper["_get_index"]().import_payload.side_effect = ValueError(PRIVATE)
    status, result, _ = request(helper, {"path": str(path)})
    assert status == 400 and result["ok"] is False
    assert str(path) not in result["error"]
    if kind in {"read", "payload"}:
        assert_private_removed(result["error"])
    if kind != "payload":
        helper["_get_index"].assert_not_called()


@pytest.mark.parametrize("value", [None, "", 42, ["backup.json"], {"path": "backup.json"}])
def test_bad_path_types_are_client_errors(helper, value):
    status, result, _ = request(helper, {"path": value})
    assert status == 400 and result["ok"] is False
    helper["_get_index"].assert_not_called()


@pytest.mark.parametrize("headers,expected", [
    ({"Host": "attacker.test"}, 403),
    ({"X-Uoink-Token": None}, 403),
    ({"X-Uoink-Token": "wrong"}, 403),
    ({"Content-Type": "text/plain"}, 415),
    ({"Content-Length": str(64 * 1024 + 1)}, 413),
])
def test_import_keeps_request_gates_before_body(helper, headers, expected):
    status, result, read = request(helper, {"path": "unused"}, headers=headers)
    assert status == expected and result["ok"] is False
    assert read == 0
    helper["_get_index"].assert_not_called()


@pytest.mark.parametrize("relative", [False, True])
def test_explicit_rebuild_root_still_restores_its_exports(helper, tmp_path, monkeypatch,
                                                       relative):
    root = tmp_path / "rebuild"
    path = export_file(root / "_exports" / "uoink-export-20261016.json")
    idx = helper["_get_index"]()
    idx.count_corpus.return_value = 0
    idx.rebuild_clips.return_value = 0
    monkeypatch.chdir(tmp_path)
    result = helper["rebuild_index_from_disk"](root=Path("rebuild") if relative else root)
    assert result["restored"]["ok"] is True
    assert result["restored"]["path"] == str(path.resolve())
    idx.import_payload.assert_called_once_with(PAYLOAD)


@pytest.mark.parametrize("error", [RuntimeError(PRIVATE), subprocess.CalledProcessError(
    7, [r"C:\Users\Synthetic Person\private\tool.exe", "--api-key", KEY],
    stderr=PRIVATE.encode(), output=b"stdout marker")])
def test_machine_details_are_sanitized_before_return_and_storage(helper, error):
    detail = helper["machine_error_detail"](error)
    assert_private_removed(detail)
    # The final ruling hides the whole ambiguous tail after a quoted path,
    # including any URL/credential placeholders already produced there.
    if isinstance(error, subprocess.CalledProcessError):
        assert detail == "Command: <path>\nExit code: 7\ntool failed at <path>\nstdout marker"
    else:
        assert detail == "tool failed at <path>"
    job = helper["_record_single_extract_job"](
        "https://example.test/video", "2026-10-16", error="Capture failed",
        error_detail=detail)
    assert job["error_detail"] == detail
    assert helper["_jobs"]["job_test"]["error_detail"] == detail
    row = helper["_get_index"]().upsert_job.call_args.args[0]
    assert json.loads(row["metadata_json"])["error_detail"] == detail
    raw_logs = "\n".join(str(call) for call in helper["_error_detail_log"].mock_calls)
    assert KEY in raw_logs and "synthetic-password" in raw_logs
    assert KEY not in str(helper["log"].mock_calls)


def test_extract_response_and_persisted_job_share_sanitized_detail(helper):
    status, result, _ = request(helper, {"url": "synthetic"}, route="/extract")
    assert status == 200 and result["ok"] is False
    assert_private_removed(result["error_detail"])
    assert helper["_jobs"]["job_test"]["error_detail"] == result["error_detail"]
    row = helper["_get_index"]().upsert_job.call_args.args[0]
    assert json.loads(row["metadata_json"])["error_detail"] == result["error_detail"]


@pytest.mark.parametrize("stream", ["stderr", "stdout"])
@pytest.mark.parametrize("as_bytes", [False, True], ids=["text", "bytes"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_subprocess_details_keep_headers_and_last_error_on_separate_lines(
        helper, stream, as_bytes, newline):
    output = newline.join([
        "ERROR: earlier failure",
        "ERROR: tool failed with --password synthetic-secret",
        "WARNING: trailing diagnostic",
    ])
    if as_bytes:
        output = output.encode("utf-8")
    error = subprocess.CalledProcessError(
        7, [r"C:\Users\Synthetic Person\private\yt-dlp.exe", "--token", KEY],
        **{stream if stream == "stderr" else "output": output})
    detail = helper["machine_error_detail"](error)
    assert detail.splitlines() == [
        "Command: <path>",
        "Exit code: 7",
        "ERROR: earlier failure",
        "ERROR: tool failed with --password [redacted]",
        "WARNING: trailing diagnostic",
    ]
    # The extension selects the last ERROR: line, ignoring command/exit headers.
    assert [line for line in detail.splitlines() if line.startswith("ERROR:")][-1] == (
        "ERROR: tool failed with --password [redacted]")


def test_command_string_is_sanitized_without_splitting_into_characters(helper):
    error = subprocess.CalledProcessError(
        1, 'yt-dlp --password "synthetic secret"', stderr="ERROR: tool failed")
    assert helper["machine_error_detail"](error).splitlines() == [
        "Command: yt-dlp --password [redacted]", "Exit code: 1", "ERROR: tool failed"]


@pytest.mark.parametrize("route", ["/extract", "/session/add"])
def test_extension_displays_real_sanitized_response_detail(helper, monkeypatch, route):
    expected = "This video requires a GVS PO Token which was not provided."
    helper["_fetch_metadata"].side_effect = subprocess.CalledProcessError(
        1, [r"C:\Users\Synthetic Person\private\yt-dlp.exe", "--api-key", KEY],
        stderr="ERROR: earlier refusal\nERROR: " + expected + "\nWARNING: final warning")
    if route == "/session/add":
        helper["_read_session"] = Mock(return_value={"status": "open"})
        helper["_session_folder"] = Mock(return_value=helper["DESKTOP_ROOT"] / "session")
        monkeypatch.setattr(helper["Handler"], "_validate_session_id",
                            lambda self, body: ("synthetic-session", None))
    status, response, _ = request(helper, {"url": "synthetic"}, route=route)
    assert status == 200 and response["ok"] is False
    assert KEY not in response["error_detail"]
    assert "Synthetic Person" not in response["error_detail"]
    # Feed the actual handler's response into the real extension formatter;
    # the existing browser harness supplies only fake, in-memory APIs.
    node = shutil.which("node")
    assert node, "Node.js is required for the offline extension error harness"
    script = """
import { readFileSync } from 'node:fs';
import { makeEnv } from './tests/js/ext_fake_env.mjs';
const env = makeEnv();
env.load('lib/extract.js');
const response = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(env.ctx.STC.describeFailure(response)));
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script], cwd=ROOT,
        input=json.dumps(response), capture_output=True, text=True,
        encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    visible = json.loads(result.stdout)
    assert expected in visible
    assert not any(text in visible for text in (
        "Command:", "Exit code:", "earlier refusal", "final warning", KEY))


@pytest.mark.parametrize("message", [
    "This video requires a GVS PO Token which was not provided.",
    "API key is invalid",
    "A password is required; authorization failed.",
])
def test_credential_words_in_diagnostics_are_preserved(helper, message):
    assert helper["_sanitize_error"](message) == message
    assert helper["machine_error_detail"](RuntimeError(message)) == message


@pytest.mark.parametrize("label", [
    "token", "token:", "password =", "--password", "Authorization:",
    "Authorization: Bearer", "Basic",
])
def test_credential_labels_do_not_consume_the_next_diagnostic_line(helper, label):
    detail = helper["machine_error_detail"](RuntimeError(
        label + "\r\nERROR: authentication failed\nWARNING: try again"))
    assert detail.splitlines()[1:] == [
        "ERROR: authentication failed", "WARNING: try again"]


@pytest.mark.parametrize("text,secret", [
    ('file "C:/Users/Synthetic Person/private/tool.exe" failed', "Synthetic"),
    (r'file C:\Users\Synthetic Person\private\tool.exe failed', "Person"),
    (r'file "\\server\private share\file.json" failed', "private share"),
    (r'file \\server\private share\file.json failed', "private share"),
    ('file "/home/private person/tool" failed', "private person"),
    ('file /home/private person/tool failed', "person"),
    (r"file C:\Users\O'Brien Family\AppData\secret failed", "Family"),
    (r"file C:\\Users\\Synthetic Person\\private\\tool.exe failed", "Person"),
    ("file 'C:\\Users\\O'Brien\\private folder\\x.json' failed", "Brien"),
    ("file '/home/o'brien/private folder/x.json' failed", "brien"),
    ('HTTPS://private-user:secret-pass@example.test/a', "secret-pass"),
    (f"upstream rejected {KEY}", KEY),
    ('{"anthropic_key": "synthetic-secret"}', "synthetic-secret"),
    ("ANTHROPIC_API_KEY=synthetic-secret", "synthetic-secret"),
    ("--api-key synthetic-secret", "synthetic-secret"),
    ("Authorization: Bearer synthetic-secret", "synthetic-secret"),
    ("X-Uoink-Token: synthetic-secret", "synthetic-secret"),
    ("--password synthetic-secret", "synthetic-secret"),
    ('--password "synthetic secret"', "synthetic secret"),
    ("--token synthetic-secret", "synthetic-secret"),
    ("--client-secret synthetic-secret", "synthetic-secret"),
    ("password=synthetic-secret", "synthetic-secret"),
    ("api key: synthetic-secret", "synthetic-secret"),
    ("Bearer synthetic-secret", "synthetic-secret"),
    ("Basic synthetic-secret", "synthetic-secret"),
])
def test_sanitizer_covers_paths_userinfo_and_keys(helper, text, secret):
    assert secret not in helper["_sanitize_error"](text, max_len=6000)


@pytest.mark.parametrize("path", [
    r"C:\Users\O'Brien\AppData\Local\Temp\x.mp4",
    "/home/o'brien/secret/x",
    r"C:\Users\bob\a:b\secret",
    r"C:\\Users\\bob\\x.json",
])
def test_path_redaction_preserves_existing_non_whitespace_coverage(helper, path):
    for detail in (helper["_sanitize_error"](path),
                   helper["machine_error_detail"](RuntimeError(path))):
        for fragment in ("Brien", "brien", "AppData", "secret", "x.json"):
            assert fragment not in detail
        assert detail == "<path>"


@pytest.mark.parametrize("path", [
    r"C:\Users\O'Brien Family\AppData\secret",
    r"C:\\Users\\Synthetic Person\\private\\x.json",
    "'C:\\Users\\O'Brien\\private folder\\x.json'",
    "'/home/o'brien/private folder/x.json'",
    '"/home/private/file";secret',
])
def test_paths_keep_space_support_and_trailing_diagnostics(helper, path):
    # Extensionless quoted paths with a tail now consume the entire line.
    expected = "file <path>" if path == '\"/home/private/file\";secret' else "file <path> failed"
    assert helper["_sanitize_error"](f"file {path} failed") == expected


@pytest.mark.parametrize("stream", ["stderr", "stdout"])
@pytest.mark.parametrize("as_bytes", [False, True], ids=["text", "bytes"])
def test_rate_limit_details_keep_separate_paths_and_diagnostics(helper, stream, as_bytes):
    line = (
        "ERROR: unable to download video data: HTTP Error 429 from "
        "https://fixture-user:fixture-secret@media.example/video "
        r"while saving C:\private\clip.mp4 /private/cache refusal 3"
    )
    output = "ERROR: earlier refusal\n" + line + "\nWARNING: trailing diagnostic"
    output = output.encode("utf-8") if as_bytes else output
    error = subprocess.CalledProcessError(
        1, ["yt-dlp"], **{stream if stream == "stderr" else "output": output})
    expected = (
        "ERROR: unable to download video data: HTTP Error 429 from "
        "<url> while saving <path> <path> refusal 3"
    )
    assert helper["_sanitize_error"](line) == expected
    assert helper["_youtube_rate_limit_detail"](error) == "youtube_rate_limit: " + expected


def test_rate_limit_detail_preserves_diagnostics_up_to_existing_limit(helper):
    line = r"ERROR: HTTP Error 429 saving C:\private\clip.mp4 /private/cache "
    line += "diagnostic " * 100
    expected = ("ERROR: HTTP Error 429 saving <path> <path> " + "diagnostic " * 100)[:200]
    assert helper["_sanitize_error"](line) == expected
    assert len(expected) == 200
    error = subprocess.CalledProcessError(1, ["yt-dlp"], stderr=line)
    assert helper["_youtube_rate_limit_detail"](error) == "youtube_rate_limit: " + expected


def test_redaction_happens_before_truncation(helper):
    detail = helper["machine_error_detail"](RuntimeError("x" * 2995 + " " + KEY))
    assert len(detail) <= 3000
    assert "sk-" not in detail
    assert helper["_sanitize_error"]("ordinary tool error") == "ordinary tool error"
    assert helper["_sanitize_error"]("ordinary\n\n tool\t error") == "ordinary tool error"
    assert helper["_sanitize_error"]("x" * 250) == "x" * 200
    sanitized = helper["_sanitize_error"](PRIVATE, max_len=6000)
    assert helper["_sanitize_error"](sanitized, max_len=6000) == sanitized


def test_raw_detail_logger_writes_only_server_log(source_tree, tmp_path):
    # Exercise the real file-handler/logger wiring, never the server bootstrap.
    names = {"_server_log_handler", "_error_detail_log"}
    nodes = [n for n in source_tree.body if
             (isinstance(n, ast.Assign) and any(
                 (isinstance(t, ast.Name) and t.id in names) or
                 (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                  and t.value.id == "_error_detail_log") for t in n.targets)) or
             (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
              and isinstance(n.value.func, ast.Attribute)
              and isinstance(n.value.func.value, ast.Name)
              and n.value.func.value.id == "_error_detail_log")]
    assert nodes, "Raw diagnostic details need file-only logging"
    stream = io.StringIO()
    parent = logging.Logger("offline.parent")
    parent.addHandler(logging.StreamHandler(stream))
    logger = logging.Logger("offline.detail")
    logger.parent = parent
    path = tmp_path / "server.log"
    namespace = {"LOG_PATH": path, "logging": SimpleNamespace(
        FileHandler=logging.FileHandler, getLogger=lambda _: logger)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "logging-setup", "exec"),
         namespace)
    try:
        namespace["_error_detail_log"].error("%s", PRIVATE)
        assert PRIVATE in path.read_text(encoding="utf-8")
        assert stream.getvalue() == ""
        assert logger.propagate is False
    finally:
        for handler in logger.handlers:
            handler.close()


def phase_error_messages(source_tree):
    """Every ExtractionPhaseError message in server.py, rendered with sample
    values (the timeout copy uses mins=20, as the extension E3 test does)."""
    values = {"mins": 20, "i": 0, "video_files": [None, None], "interval": 30}
    return [eval(compile(ast.Expression(node.args[1]), "server.py", "eval"), {}, dict(values))
            for node in ast.walk(source_tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "ExtractionPhaseError" and len(node.args) == 2]


def describe_failure(response):
    """The real extension formatter over the fake in-memory browser APIs."""
    node = shutil.which("node")
    assert node, "Node.js is required for the offline extension error harness"
    script = """
import { readFileSync } from 'node:fs';
import { makeEnv } from './tests/js/ext_fake_env.mjs';
const env = makeEnv();
env.load('lib/extract.js');
const response = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(env.ctx.STC.describeFailure(response)));
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script], cwd=ROOT,
        input=json.dumps(response), capture_output=True, text=True,
        encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_phase_error_detail_equals_its_friendly_error(helper, source_tree):
    messages = phase_error_messages(source_tree)
    assert len(messages) >= 5
    assert any(message.startswith(
        "Download timed out after about 20 minutes. This is a download/network issue")
        for message in messages)
    for message in messages:
        error = helper["ExtractionPhaseError"]("download", message)
        assert helper["machine_error_detail"](error) == helper["friendly_error"](error)
        assert helper["friendly_error"](error) == message


def test_extension_shows_a_download_timeout_once(helper, source_tree):
    message = next(message for message in phase_error_messages(source_tree)
                   if message.startswith("Download timed out"))
    error = helper["ExtractionPhaseError"]("download", message)
    visible = describe_failure({
        "ok": False, "error": helper["friendly_error"](error),
        "error_detail": helper["machine_error_detail"](error), "failure_phase": "download"})
    assert visible.count("Download timed out") == 1
    assert visible.endswith("Failed at the download step.")
    assert "<path>" not in visible


@pytest.mark.parametrize("text,expected", [
    ("ERROR: See https://github.com/yt-dlp/yt-dlp/wiki/FAQ for help",
     "ERROR: See <url> for help"),
    ("HTTPS://Media.Example.test/private/clip.mp4 refused",
     "<url> refused"),
    ("fetch http://example.test/a/b?token=fixture-secret failed",
     "fetch <url> failed"),
    ("open file:///C:/Users/Synthetic/private/x.json failed",
     "open <url> failed"),
    ("ERROR: [generic] 'https://example.test/x' is not a valid URL",
     "ERROR: [generic] '<url>' is not a valid URL"),
    ("See https://github.com/yt-dlp/yt-dlp/wiki/FAQ.", "See <url>."),
    ("(https://user:secret@media.example/x)", "(<url>"),
])
def test_urls_are_replaced_whole_never_as_partial_paths(helper, text, expected):
    for detail in (helper["_sanitize_error"](text, max_len=6000),
                   helper["machine_error_detail"](RuntimeError(text))):
        assert detail == expected
        for broken in ("http<path>", "htt<path>", "https:<path>", "fil<path>"):
            assert broken not in detail
        for secret in ("private", "Synthetic", "fixture-secret", "wiki/FAQ"):
            assert secret not in detail


@pytest.mark.parametrize("text", [
    "This is a download/network issue, not a screenshot setting",
    "Install yt-dlp/ffmpeg and/or check TCP/IP; yt-dlp/2024.10.07 failed",
    "drive letters inside words: fooC:\\x and 9C:\\x",
])
def test_slashes_and_drive_letters_inside_words_are_not_paths(helper, text):
    assert helper["_sanitize_error"](text, max_len=6000) == text
    assert helper["machine_error_detail"](RuntimeError(text)) == text


class _StopWorker(BaseException):
    """Ends the worker's infinite loop after one job."""


@pytest.fixture
def podcast_job(helper, tmp_path):
    """Run the real podcast transcription worker for one in-memory job."""
    job_id = "job_podcast"
    helper["_jobs"][job_id] = {
        "id": job_id, "kind": "podcast_transcribe", "state": "queued",
        "episode_id": 7, "audio_path": str(tmp_path / "episode.mp3"),
        "model": "base", "title": "Synthetic episode", "publish_to_corpus": True}
    jobs = iter([job_id])

    def get():
        try:
            return next(jobs)
        except StopIteration:
            raise _StopWorker from None

    whisper = SimpleNamespace(
        STATUS_RUNNING="running", STATUS_DONE="done", STATUS_FAILED="failed",
        set_current_thread_below_normal=lambda: True,
        normalize_model=lambda model: model or "base",
        transcribe_audio=Mock(return_value={"model": "base", "segments": []}),
        write_transcript=Mock(return_value=tmp_path / "episode.transcript.json"),
        update_episode_transcript_state=Mock())
    podcasts = SimpleNamespace(
        EPISODE_STATUS_TRANSCRIBED="transcribed",
        load_completed_episode_transcript=Mock(return_value=None),
        set_episode_status=Mock(), episode_to_corpus=Mock(return_value={"video_id": "v"}))
    helper.update(
        contextlib=contextlib, DATA_ROOT=tmp_path, whisper_runner=whisper, podcasts=podcasts,
        _podcast_transcription_queue=SimpleNamespace(get=get, task_done=Mock()),
        _podcast_capture_key=lambda episode_id: None,
        _settle_source_capture=Mock(), maybe_toast=Mock(), _heartbeat_note_ingest=Mock())

    def run():
        with pytest.raises(_StopWorker):
            helper["_podcast_transcription_worker"]()
        return helper["_jobs"][job_id]

    return SimpleNamespace(run=run, whisper=whisper, podcasts=podcasts)


def assert_no_secrets(text):
    for secret in ("Synthetic Person", "synthetic-private-user", "synthetic-user",
                   "synthetic-password", KEY):
        assert secret not in text


@pytest.mark.parametrize("error", [RuntimeError(PRIVATE), subprocess.CalledProcessError(
    1, [r"C:\Users\Synthetic Person\private\whisper.exe", "--api-key", KEY],
    stderr=PRIVATE)], ids=["runtime", "subprocess"])
def test_podcast_transcription_failure_stores_and_prints_only_sanitized_text(
        helper, podcast_job, error):
    podcast_job.whisper.transcribe_audio.side_effect = error
    job = podcast_job.run()
    public = helper["_public_job"](job)
    assert job["state"] == public["state"] == "failed"
    for text in (job["error"], job["error_detail"], public["error"], public["error_detail"]):
        assert text
        assert_no_secrets(text)
    assert public["error_detail"].startswith(type(error).__name__ + ": ")
    assert "tool failed" in public["error_detail"]
    episode = podcast_job.whisper.update_episode_transcript_state.call_args.kwargs
    assert episode["status"] == "failed" and episode["error"] == job["error"]
    row = helper["_get_index"]().upsert_job.call_args.args[0]
    assert_no_secrets(json.dumps(row))
    # Console (root logger -> stdout) lines are sanitized; tracebacks and raw
    # text go only to the file-only logger.
    helper["log"].exception.assert_not_called()
    assert_no_secrets(str(helper["log"].mock_calls))
    helper["_error_detail_log"].exception.assert_called()
    assert KEY in str(helper["_error_detail_log"].mock_calls)


def test_deferred_podcast_publish_error_is_sanitized(helper, podcast_job):
    podcast_job.podcasts.episode_to_corpus.side_effect = OSError(PRIVATE)
    job = podcast_job.run()
    public = helper["_public_job"](job)
    assert job["state"] == "completed"
    corpus_error = public["result"]["corpus_error"]
    assert corpus_error and "tool failed" in corpus_error
    assert_no_secrets(corpus_error)
    assert_no_secrets(json.dumps(helper["_get_index"]().upsert_job.call_args.args[0]))
    helper["log"].exception.assert_not_called()
    assert_no_secrets(str(helper["log"].mock_calls))
    helper["_error_detail_log"].exception.assert_called()
    helper["_settle_source_capture"].assert_called_once_with(
        "job_podcast", video_id=None, failure_code="publish_failed")


# Credential values without the sk- prefix, which the key pattern would
# otherwise catch on its own and mask a gap in the label/flag matcher.
@pytest.mark.parametrize("text,leaks", [
    ("--password fixture,SECRET", ["fixture", "SECRET"]),
    ("password=fixture;SECRET} next", ["fixture", "SECRET"]),
    (json.dumps({"password": 'hello "fixtureSECRET" world'}),
     ["hello", "fixtureSECRET", "world"]),
    (r"{'password': 'it\'s fixtureSECRET', 'ok': 1}", ["fixtureSECRET"]),
    ('token: "fixture SECRET (unterminated', ["fixture", "SECRET", "unterminated"]),
    ("['tool', '--token', 'fixturetokenVALUE', '-v']", ["fixturetokenVALUE"]),
    ('["tool", "--password", "fixture,SECRET"]', ["fixture", "SECRET"]),
    ("['yt-dlp', '--video-password', 'fixtureVIDEO']", ["fixtureVIDEO"]),
    ("--token=fixturetokenVALUE --verbose", ["fixturetokenVALUE"]),
    ("'--client-secret=fixture,SECRET'", ["fixture", "SECRET"]),
    ("Command '['tool', '--token', 'fixturetokenVALUE']' returned non-zero exit status 1.",
     ["fixturetokenVALUE"]),
    ("--video-password fixtureVIDEO --verbose", ["fixtureVIDEO"]),
    ("--ap-password=fixture,AP --verbose", ["fixture", ",AP"]),
    # A quote glued to more text is inside the value, never its end.
    ("--password 'fixture'SECRET --verbose", ["fixture", "SECRET"]),
    ("--password 'fixture',SECRET", ["fixture", "SECRET"]),
    ("--password 'it's fixtureSECRET' now", ["fixtureSECRET"]),
    ("password='fixture SECRET\\", ["fixture", "SECRET"]),
])
def test_credential_values_are_redacted_whole(helper, text, leaks):
    for detail in (helper["_sanitize_error"](text, max_len=6000),
                   helper["machine_error_detail"](RuntimeError(text))):
        assert "[redacted]" in detail
        for leak in leaks:
            assert leak not in detail


@pytest.mark.parametrize("text,expected", [
    ("['tool', '--token', 'fixturetokenVALUE', '-v']",
     "['tool', '--token', [redacted], '-v']"),
    ("Command '['tool', '--token', 'fixturetokenVALUE']' returned non-zero exit status 1.",
     "Command '['tool', '--token', [redacted]]' returned non-zero exit status 1."),
    ('["tool", "--password", "fixture,SECRET", "-v"]',
     '["tool", "--password", [redacted], "-v"]'),
    (json.dumps({"password": 'hello "fixtureSECRET" world', "ok": 1}),
     '{"password": [redacted], "ok": 1}'),
    ("--token=fixturetokenVALUE --verbose", "--token=[redacted] --verbose"),
    ("--video-password fixtureVIDEO --verbose", "--video-password [redacted] --verbose"),
    ("--password fixture,SECRET then the next words",
     "--password [redacted] then the next words"),
    ("Invalid token='fixtureVALUE'. Please retry", "Invalid token=[redacted]. Please retry"),
    ("password: 'fixtureVALUE' doesn't match", "password: [redacted] doesn't match"),
])
def test_credential_redaction_keeps_the_surrounding_diagnostic(helper, text, expected):
    # Whole-value redaction must not swallow the text or list items after it.
    assert helper["_sanitize_error"](text, max_len=6000) == expected
    assert helper["machine_error_detail"](RuntimeError(text)) == expected


@pytest.mark.parametrize("error", [
    subprocess.CalledProcessError(1, ["tool", "--password", "fixture,SECRET"]),
    subprocess.CalledProcessError(
        1, ["tool", "--token", "fixturetokenVALUE", "--password", 'say "fixtureSECRET"'],
        stderr="ERROR: tool failed"),
    subprocess.CalledProcessError(1, "tool --token fixturetokenVALUE"),
    subprocess.TimeoutExpired(["tool", "--token", "fixturetokenVALUE"], 30),
    subprocess.CalledProcessError(
        1, ["tool", "--video-password", "fixture,SECRET", "--token=fixturetokenVALUE"]),
    subprocess.CalledProcessError(1, ["tool", "--password", "'fixture'SECRET", "-v"]),
], ids=["comma-value", "list", "string-command", "timeout", "prefixed-and-equals",
        "glued-quote"])
def test_subprocess_credential_arguments_never_leak(helper, error):
    for text in (helper["machine_error_detail"](error), helper["_error_summary"](error),
                 helper["_sanitize_error"](str(error), max_len=6000)):
        for leak in ("fixturetokenVALUE", "fixtureSECRET", "SECRET"):
            assert leak not in text
    if isinstance(error, subprocess.CalledProcessError):
        assert helper["_error_summary"](error) == "CalledProcessError: exit status 1"
    else:
        assert helper["_error_summary"](error) == "TimeoutExpired: timed out after 30 seconds"


@pytest.mark.parametrize("error", [
    subprocess.CalledProcessError(
        1, [r"C:\Users\Synthetic Person\private\whisper.exe", "--token",
            "fixturetokenVALUE", "--password", "fixture,SECRET"],
        stderr="ERROR: tool failed\nAuthorization: Bearer fixtureBEARER"),
    subprocess.TimeoutExpired(
        [r"C:\Users\Synthetic Person\private\whisper.exe", "--token",
         "fixturetokenVALUE"], 30),
    subprocess.CalledProcessError(
        2, ["whisper", "--video-password", "fixture'SECRET", "--token=fixturetokenVALUE"],
        output=json.dumps({"password": 'say "fixtureSECRET"', "error": "tool failed"})),
    RuntimeError("whisper failed: ['whisper', '--token', 'fixturetokenVALUE', "
                 "'--password', 'fixture,SECRET']"),
], ids=["subprocess", "timeout", "prefixed-equals-json", "runtime-list-repr"])
def test_podcast_failure_never_exposes_non_key_credentials(helper, podcast_job, capsys,
                                                           error):
    podcast_job.whisper.transcribe_audio.side_effect = error
    job = podcast_job.run()
    public = helper["_public_job"](job)
    episode = podcast_job.whisper.update_episode_transcript_state.call_args.kwargs
    row = helper["_get_index"]().upsert_job.call_args.args[0]
    captured = capsys.readouterr()
    exposed = {
        "job.error": job["error"], "job.error_detail": job["error_detail"],
        "episode error": episode["error"], "public job": json.dumps(public),
        "persisted job": json.dumps(row), "console": str(helper["log"].mock_calls),
        "stdout": captured.out + captured.err,
    }
    for where, text in exposed.items():
        for leak in ("fixturetokenVALUE", "fixture,SECRET", "SECRET", "fixtureBEARER",
                     "Synthetic Person"):
            assert leak not in text, where
    assert job["error"] == episode["error"] == helper["_error_summary"](error)
    assert job["error_detail"].startswith(type(error).__name__ + ": ")
    if isinstance(error, subprocess.TimeoutExpired):
        assert job["error_detail"] == "TimeoutExpired: Command: <path>\nTimeout: 30 seconds"
    else:
        assert "[redacted]" in job["error_detail"]


@pytest.mark.parametrize("error,summary", [
    (subprocess.CalledProcessError(
        3, ["publisher", "--token", "fixturetokenVALUE", "--password=fixture,SECRET"],
        stderr="ERROR: tool failed"), "CalledProcessError: exit status 3"),
    (subprocess.TimeoutExpired(["publisher", "--token", "fixturetokenVALUE"], 15),
     "TimeoutExpired: timed out after 15 seconds"),
    (OSError("publish failed: ['publisher', '--token', 'fixturetokenVALUE']"), None),
], ids=["subprocess", "timeout", "os-list-repr"])
def test_deferred_podcast_publish_never_exposes_non_key_credentials(
        helper, podcast_job, capsys, error, summary):
    podcast_job.podcasts.episode_to_corpus.side_effect = error
    job = podcast_job.run()
    public = helper["_public_job"](job)
    corpus_error = public["result"]["corpus_error"]
    assert job["state"] == "completed" and corpus_error
    assert corpus_error == (summary or helper["_error_summary"](error))
    captured = capsys.readouterr()
    exposed = {
        "corpus_error": corpus_error, "job": json.dumps(job), "public job": json.dumps(public),
        "persisted job": json.dumps(helper["_get_index"]().upsert_job.call_args.args[0]),
        "console": str(helper["log"].mock_calls), "stdout": captured.out + captured.err,
    }
    for where, text in exposed.items():
        for leak in ("fixturetokenVALUE", "fixture,SECRET", "SECRET"):
            assert leak not in text, where
    helper["_settle_source_capture"].assert_called_once_with(
        "job_podcast", video_id=None, failure_code="publish_failed")


@pytest.mark.parametrize("error_type", [subprocess.CalledProcessError, subprocess.TimeoutExpired])
@pytest.mark.parametrize("flag", [
    "--password", "--video-password", "--ap-password", "--api-key", "--api_key",
    "--anthropic-api-key", "--anthropic_key", "--x-api-key", "--x-uoink-token",
    "--x-yoink-token", "--access-token", "--access_token", "--token",
    "--authorization", "--client-secret", "--client_secret", "--VIDEO-PASSWORD",
])
@pytest.mark.parametrize("equals", [False, True], ids=["next-argument", "equals"])
@pytest.mark.parametrize("secret", [
    "fixture SECRET",
    'fixture SECRET with "quotes", apostrophe\' and\tspaces\nTAIL',
], ids=["spaces", "quotes-and-line-breaks"])
def test_command_credentials_are_removed_before_formatting(helper, monkeypatch,
                                                           error_type, flag, equals, secret):
    args = ["tool", *([flag + "=" + secret] if equals else [flag, secret]), "--verbose"]
    original = list(args)
    formatter = Mock(wraps=subprocess.list2cmdline)
    monkeypatch.setattr(subprocess, "list2cmdline", formatter)
    error = (error_type(1, args) if error_type is subprocess.CalledProcessError
             else error_type(tuple(args), 30))
    detail = helper["machine_error_detail"](error)
    assert "[redacted]" in detail and "--verbose" in detail
    for leak in ("fixture", "SECRET", "quotes", "apostrophe", "TAIL"):
        assert leak not in detail
    assert args == original and list(error.cmd) == original
    assert formatter.called, "Both subprocess errors must format a redacted argument list"
    for call in formatter.call_args_list:
        assert all(secret not in str(arg) for arg in call.args[0])
    assert "SECRET" in str(helper["_error_detail_log"].mock_calls)


@pytest.mark.parametrize("path", [
    "'/home/james' smith/private/x.json'",
    "'C:\\Users\\james' smith\\private\\x.json'",
    "'/home/private/james' smith.json'",
    "'C:\\private\\james' smith.json'",
    "'/home/james' middle' smith/private/x.json'",
    '"/home/james" smith/private/x.json"',
    "'/home/james' [smith]/private/x.json'",
    "'/home/james' (smith)/private/x.json'",
    "'/home/james' smith:family/private/x.json'",
    "'C:\\Users\\james' smith, family\\private\\x.json'",
])
def test_quoted_paths_include_apostrophes_followed_by_spaces(helper, path):
    text = f"file {path} failed"
    assert helper["_sanitize_error"](text, max_len=6000) == "file <path> failed"
    assert helper["machine_error_detail"](RuntimeError(text)) == "file <path> failed"


@pytest.mark.parametrize("separator,root", [("/", "/home"), ("\\", "C:\\Users")])
@pytest.mark.parametrize("name", ["James' O'Brien", "James' o'reilly", "James' ab'c"])
def test_quoted_paths_scan_past_apostrophes_that_cannot_close(helper, separator, root, name):
    path = separator.join((root, name, "private", "x.json"))
    text = f"file '{path}' failed"
    assert helper["_sanitize_error"](text, max_len=6000) == "file <path> failed"
    assert helper["machine_error_detail"](RuntimeError(text)) == "file <path> failed"


@pytest.mark.parametrize("separator,root", [("/", "/home"), ("\\", "C:\\Users")])
@pytest.mark.parametrize("next_path", ["", " /other/file.json", " C:\\other\\file.json"])
def test_unquoted_spaced_paths_include_colons_before_later_separators(
        helper, separator, root, next_path):
    path = separator.join((root, "james' smith:family", "private", "x.json"))
    text = f"file {path}{next_path} failed"
    expected = "file <path>" + (" <path>" if next_path else "") + " failed"
    assert helper["_sanitize_error"](text, max_len=6000) == expected
    assert helper["machine_error_detail"](RuntimeError(text)) == expected


def test_quoted_paths_use_last_same_quote_across_other_quote_styles(helper):
    text = "file '/home/first/x.json' and \"C:\\second\\y.json\" and '/third/z.json' failed"
    # Ambiguous quoted paths deliberately absorb intervening words and paths.
    assert helper["_sanitize_error"](text) == "file <path> failed"


@pytest.mark.parametrize("text,expected", [
    (r"file C:\first\x.json C:\second\y.json failed", "file <path> <path> failed"),
    ("file '/home/first/x.json' wasn't found", "file <path> wasn't found"),
    ("file '/home/james' smith/private/x.json'. failed", "file <path> failed"),
    ('file "C:\\Users\\james\' smith\\x.json"! failed', "file <path> failed"),
    ('Command: tool "--video-password=fixture SECRET" --verbose',
     'Command: tool "--video-password=[redacted]" --verbose'),
    ("['tool', '--ap-password=fixture SECRET', '--verbose']",
     "['tool', '--ap-password=[redacted]', '--verbose']"),
])
def test_structural_redaction_preserves_surrounding_text(helper, text, expected):
    assert helper["_sanitize_error"](text) == expected


@pytest.mark.parametrize("root,separator", [("/home/", "/"), ("C:\\Users\\", "\\")])
@pytest.mark.parametrize("suffix", ["smith/private/x.json", "smith.json"])
def test_unterminated_quoted_path_redacts_its_relative_tail(helper, root, separator, suffix):
    text = "file '" + root + "james' " + suffix.replace("/", separator) + " failed"
    expected = "file <path>"
    assert helper["_sanitize_error"](text, max_len=6000) == expected
    assert helper["machine_error_detail"](RuntimeError(text)) == expected


@pytest.mark.parametrize("root,separator", [("/home/", "/"), ("C:\\Users\\", "\\")])
@pytest.mark.parametrize("suffix", ["smith/private/SECRET", "smith.json"])
def test_input_cap_cannot_expose_a_quoted_path_tail(helper, root, separator, suffix):
    prefix = "file '" + root + "james' " + suffix.replace("/", separator)
    # The closing quote is just outside the sanitizer's 64 KiB input window.
    text = prefix + " " * (64 * 1024 - len(prefix)) + "' failed"
    assert helper["_sanitize_error"](text, max_len=len(text)) == "file <path>"
    assert helper["machine_error_detail"](RuntimeError(text)) == "file <path>"


@pytest.mark.parametrize("text,expected", [
    ("file '/home/x.json' is 'not' available", "file <path>"),
    ("file 'C:\\Users\\x.json' is 'not' available", "file <path>"),
    ("file '/home/secret/x.json' owners' copy failed", "file <path>"),
    ("file 'C:\\Users\\secret\\x.json' owners' copy failed", "file <path>"),
    ("file '/home/james' smith '/private/x.json' failed", "file <path> failed"),
    ("file 'C:\\Users\\james' smith '\\private\\x.json' failed", "file <path> failed"),
])
def test_quoted_paths_redact_ambiguous_prose_through_last_quote(helper, text, expected):
    assert helper["_sanitize_error"](text, max_len=6000) == expected
    assert helper["machine_error_detail"](RuntimeError(text)) == expected


@pytest.mark.parametrize("root", ["/home/", "C:\\Users\\", "C:\\\\Users\\\\"])
@pytest.mark.parametrize("quote", ["'", '"'])
def test_quoted_paths_redact_extensionless_final_segments(helper, root, quote):
    text = f"No such file or directory: {quote}{root}james{quote} smith{quote}"
    expected = "No such file or directory: <path>"
    assert helper["_sanitize_error"](text) == expected
    assert helper["machine_error_detail"](RuntimeError(text)) == expected


@pytest.mark.parametrize("text,expected", [
    ("Download failed for '/tmp/a.json' because '/tmp/b.json' is locked",
     "Download failed for <path> is locked"),
    ('"/home/first/x.json" then "/home/second/y.json"', "<path>"),
    ("'C:\\first\\x.json' then 'C:\\second\\y.json'", "<path>"),
    ('"C:\\first\\x.json" then "C:\\second\\y.json"', "<path>"),
    ("'/home/first/x.json' then '/home/second/y.json'", "<path>"),
    ("Download failed for 'C:\\tmp\\a.json' because 'C:\\tmp\\b.json' is locked",
     "Download failed for <path> is locked"),
])
def test_same_quote_paths_and_intervening_words_are_redacted(helper, text, expected):
    assert helper["_sanitize_error"](text, max_len=6000) == expected
    assert helper["machine_error_detail"](RuntimeError(text)) == expected


@pytest.mark.parametrize("root", ["/home/", "C:\\Users\\"])
@pytest.mark.parametrize("quote", ["'", '"'])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_quoted_path_redaction_stays_on_its_line(helper, root, quote, newline):
    next_line = f"ERROR: it wasn't found; try {quote}again{quote}"
    for path, suffix in (
        (f"{quote}{root}james{quote} smith{quote}", " failed"),
        (f"{quote}{root}james smith failed", ""),
    ):
        text = "file " + path + suffix + newline + next_line
        expected = "file <path>"
        assert helper["_sanitize_error"](text) == expected + " " + next_line
        assert helper["machine_error_detail"](RuntimeError(text)) == expected + "\n" + next_line


@pytest.mark.parametrize("root", ["/home/", "C:\\Users\\"])
@pytest.mark.parametrize("quote", ["'", '"'])
def test_apostrophe_in_wasnt_does_not_close_a_quoted_path(helper, root, quote):
    text = f"file {quote}{root}x.json{quote} wasn't found"
    assert helper["_sanitize_error"](text) == "file <path> wasn't found"
    assert helper["machine_error_detail"](RuntimeError(text)) == "file <path> wasn't found"


def test_sanitizer_caps_input_before_redaction(helper, monkeypatch):
    limit = 64 * 1024
    text = "x" * (limit - 7) + " token=" + "fixtureSECRET" * 20000
    seen = []

    class BoundedPattern:
        def __init__(self, pattern):
            self.pattern = pattern

        def sub(self, replacement, value, *args, **kwargs):
            seen.append(len(value))
            assert len(value) <= limit, "Cap tool output before regex processing"
            return self.pattern.sub(replacement, value, *args, **kwargs)

    monkeypatch.setitem(helper, "_KEY_SANITIZE_RE", BoundedPattern(helper["_KEY_SANITIZE_RE"]))
    detail = helper["_sanitize_error"](text, max_len=len(text))
    assert seen and len(detail) <= limit
    assert "fixture" not in detail and "SECRET" not in detail
    assert helper["_sanitize_error"]("x" * 200000, max_len=300000) == "x" * limit


@pytest.mark.parametrize("unit", [
    "a", "a-a.", "/directory ", "'/directory' name/private/file.json' ",
    "'/", "password='abc'", "--" + "prefix-" * 10,
    "'/home/James' O'Brien/private/x.json' ",
    "/home/james' smith:family/private/x.json ",
    "'/home/James' " + "O'" * 100 + "Brien/private/x.json' ",
], ids=["letters", "scheme-like", "paths", "quoted-paths", "quotes",
        "quoted-credentials", "flag-prefixes", "internal-apostrophes",
        "spaced-colons", "many-nonclosing-quotes"])
def test_sanitizer_handles_large_adversarial_output_in_linear_time(helper, unit):
    text = (unit * (200000 // len(unit) + 1))[:200000]
    start = time.perf_counter()
    helper["_sanitize_error"](text, max_len=6000)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"Sanitizing 200 KB took {elapsed:.3f}s"


@pytest.mark.parametrize("root", ["/home/", "C:\\Users\\", "\\\\server\\share\\"])
@pytest.mark.parametrize("name", ["james' smith", "James' O'Brien"])
@pytest.mark.parametrize("later_path", ["", " /other/secret", " C:\\other\\secret",
                                        " \\\\other\\share\\secret"])
def test_ambiguous_quoted_path_redacts_plain_tail_and_later_absolute_paths(
        helper, root, name, later_path):
    text = f"file '{root}{name}{later_path} failed"
    assert helper["_sanitize_error"](text, max_len=6000) == "file <path>"
    assert helper["machine_error_detail"](RuntimeError(text)) == "file <path>"


@pytest.mark.parametrize("root", ["/home/", "C:\\Users\\", "\\\\server\\share\\"])
@pytest.mark.parametrize("name", ["james' smith", "James' O'Brien"])
@pytest.mark.parametrize("padding", [" ", "a"])
def test_cap_inside_plain_quoted_path_tail_redacts_to_end(helper, root, name, padding):
    prefix = f"file '{root}{name}"
    text = prefix + padding * (64 * 1024 - len(prefix)) + "' failed"
    assert helper["_sanitize_error"](text, max_len=len(text)) == "file <path>"
    assert helper["machine_error_detail"](RuntimeError(text)) == "file <path>"


@pytest.mark.parametrize("root", ["/home/", "C:\\Users\\", "\\\\server\\share\\"])
@pytest.mark.parametrize("tail", ["smith failed", "O'Brien failed", "smith /other/secret failed"])
def test_filename_extension_alone_does_not_make_a_tail_prose(helper, root, tail):
    text = f"file '{root}x.json' {tail}"
    assert helper["_sanitize_error"](text) == "file <path>"
    assert helper["machine_error_detail"](RuntimeError(text)) == "file <path>"


@pytest.mark.parametrize("root", ["/home/", "C:\\Users\\", "\\\\server\\share\\"])
def test_ambiguous_plain_path_tail_stops_at_line_break(helper, root):
    text = f"file '{root}james' smith failed\nERROR: download/network issue"
    assert helper["machine_error_detail"](RuntimeError(text)) == (
        "file <path>\nERROR: download/network issue")
    assert helper["machine_error_detail"](RuntimeError(
        f"file '{root}x.json' wasn't found")) == "file <path> wasn't found"


@pytest.mark.parametrize("worker", ["subtitles", "comments"])
@pytest.mark.parametrize("failure", ["exit-bytes", "exit-text", "timeout", "os-error"])
def test_optional_video_worker_errors_keep_raw_details_off_console(
        helper, monkeypatch, worker, failure):
    output = helper["DESKTOP_ROOT"] / "Synthetic Private Output"
    cmd = ["yt-dlp", "--video-password", "fixture SECRET", "--token=fixtureTOKEN",
           "-o", str(output / "video.%(ext)s")]
    stderr = f"ERROR: saving {output} --password fixtureSTDERR"
    if failure.startswith("exit"):
        error = subprocess.CalledProcessError(
            7, cmd, stderr=stderr.encode() if failure == "exit-bytes" else stderr)
    elif failure == "timeout":
        error = subprocess.TimeoutExpired(cmd, 30, stderr=stderr.encode())
    else:
        error = OSError(f"tool failed at {output} --password fixtureOS")
    console = io.StringIO()
    console_log = logging.Logger("offline.optional-video")
    console_log.addHandler(logging.StreamHandler(console))
    raw_stream = io.StringIO()
    detail_log = logging.Logger("offline.optional-video.detail")
    detail_log.addHandler(logging.StreamHandler(raw_stream))
    detail_log.propagate = False
    helper.update(
        log=console_log, _error_detail_log=detail_log,
        _run_subprocess=Mock(side_effect=error), YTDLP_CMD=["yt-dlp"],
        COMMENTS_TIMEOUT_SEC=30, PLATFORM_YOUTUBE="youtube",
        _detect_platform_from_url=lambda url: "youtube",
        _is_youtube_captions_refusal=Mock(return_value=True),
        _replace_comments_section=Mock(), _update_sidecar_comments=Mock())
    # Neither worker may launch a real tool, even if a regression changes its call.
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=AssertionError("real tool")))
    monkeypatch.setattr(subprocess, "Popen", Mock(side_effect=AssertionError("real tool")))
    if worker == "subtitles":
        assert helper["_fetch_video_subtitles"](
            "https://example.test/video", output, long_video_mode="full") is True
        helper["_is_youtube_captions_refusal"].assert_called_once_with(error)
    else:
        helper["_comments_worker"]("https://example.test/video", output, output / "yoink.md")
        state = "disabled" if failure.startswith("exit") else "unavailable"
        helper["_update_sidecar_comments"].assert_called_once_with(output, [], state)
        helper["_replace_comments_section"].assert_called_once()
    helper["_run_subprocess"].assert_called_once()
    visible = console.getvalue()
    assert visible and ("subtitle fetch unavailable" if worker == "subtitles" else "comments") in visible
    for secret in (str(output), "Synthetic", "Private", "Output", "fixture SECRET", "fixtureTOKEN",
                   "fixtureSTDERR", "fixtureOS", "--video-password", "--token="):
        assert secret not in visible
    raw = raw_stream.getvalue()
    assert str(error) in raw
    if failure.startswith("exit"):
        assert "fixtureSTDERR" in raw


@pytest.mark.parametrize("path", ["docs/security.md", "CHANGELOG.md"])
def test_key_validity_docs_cover_cleared_invalid_key_and_absence(path):
    text = " ".join((ROOT / path).read_text(encoding="utf-8").split())
    assert "`false` whenever `anthropic_key_invalid` is set, even if a 401 cleared the saved key" in text
    assert "absent only when no key is saved and the invalid flag is off" in text

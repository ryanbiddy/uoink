"""Usage sharing contracts. Every send is mocked; real stdio uses temp files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import uuid
from unittest.mock import Mock

import pytest

import server
import uoink_install_isolation as isolation
import uoink_mcp_tools as tools
import uoink_usage as usage

_REAL_POST = usage._post


@pytest.fixture
def store(tmp_path, monkeypatch):
    usage._queue.join()
    monkeypatch.setattr(usage, "_root", lambda: tmp_path)
    monkeypatch.setattr(usage, "_version", "3.10.0")
    monkeypatch.setattr(usage, "_kind", "source")
    monkeypatch.delenv("UOINK_USAGE_SHARING", raising=False)
    monkeypatch.delenv("UOINK_USAGE_ENDPOINT", raising=False)
    for key in list(os.environ):
        if key.startswith("UOINK_ISOLATED_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(isolation, "_CURRENT", None)
    monkeypatch.setattr(server, "_ISOLATION", None)
    monkeypatch.setattr(usage, "_post", Mock(side_effect=AssertionError("No real usage send")))
    yield tmp_path
    usage._queue.join()


def enabled():
    usage.set_enabled(True)
    return usage.disclosure()["next_payload"]


def age():
    now = time.time()
    with usage._transaction() as state:
        state["since"] = now - usage.DAY
        state["last_attempt"] = 0
    return now


def test_default_off_creates_no_file(store):
    assert server._default_settings()["usage_sharing"] is False
    usage.count("searches")
    usage._queue.join()
    assert not usage._path().exists()
    assert usage.disclosure() == {"next_payload": None, "sent": []}
    assert not usage.send_due()
    usage._post.assert_not_called()


def test_id_only_on_opt_in_and_deleted_on_opt_out(store):
    first = enabled()["install_id"]
    assert uuid.UUID(first).version == 4
    usage.count("searches")
    usage._queue.join()
    usage.set_enabled(False)
    assert usage.disclosure() == {"next_payload": None, "sent": []}
    assert first.encode() not in usage._path().read_bytes()
    assert enabled()["install_id"] != first


def test_env_zero_forces_off_even_with_saved_true(store, monkeypatch):
    identity = enabled()["install_id"]
    monkeypatch.setenv("UOINK_USAGE_SHARING", "0")
    assert server._normalize_settings({"usage_sharing": True})["usage_sharing"] is False
    usage.set_enabled(True)
    usage.count("searches")
    assert usage.disclosure()["next_payload"] is None
    assert identity.encode() not in usage._path().read_bytes()
    assert not usage.send_due()
    usage._post.assert_not_called()


def test_schema_and_fuzzed_content_never_enter_counts(store):
    enabled()
    secret = "PRIVATE_title https://secret.example/path?query=private C:/Users/alice/secret.txt"
    @usage.capture("page")
    def capture(result):
        return result
    for i in range(60):
        capture({"ok": i % 2 == 0, "url": secret, "title": secret, "path": secret,
                 "query": secret, "username": secret, "ip": "192.0.2.42", "content": secret})
        usage.count("mcp_clients", secret + str(i))
        usage.mcp_call(secret, "http")
    usage.mcp_call("search_library", "stdio")
    usage.count("mcp_clients", "Claude Code")
    usage.count("searches")
    usage._queue.join()
    p = usage.disclosure()["next_payload"]
    assert set(p) == {"schema", "install_id", "version", "os", "os_major", "arch",
                      "install_kind", "period_hours", "mcp_clients", "transports", "tools", "captures", "searches"}
    assert p["schema"] == 1 and p["os"] in ("windows", "macos", "linux")
    assert p["captures"] == {"page": {"ok": 30, "failed": 30}}
    assert p["mcp_clients"] == {"other": 60, "claude-code": 1}
    assert p["tools"] == {"search_library": 1} and p["transports"] == {"stdio": 1}
    assert p["searches"] == 1
    encoded = usage._encode(p)
    for word in ("PRIVATE", "secret", "https:", "C:/", "alice", "192.0.2.42", "query"):
        assert word.encode() not in encoded
        assert word.encode() not in usage._path().read_bytes()


def test_payload_caps_keys_counts_and_actual_wire_bytes(store):
    enabled()
    with usage._transaction() as state:
        state["counts"] = {"tools": {name: usage.MAX_COUNT * 9 for name in tools.TOOL_REGISTRY},
                           "mcp_clients": {"other": usage.MAX_COUNT},
                           "captures": {s + ":" + o: usage.MAX_COUNT for s in usage.SOURCES for o in ("ok", "failed")}}
    p = usage.disclosure()["next_payload"]
    assert len(p["tools"]) <= usage.MAX_TOOL_KEYS
    assert all(n == usage.MAX_COUNT for n in p["tools"].values())
    assert len(usage._encode(p)) < 4096


@pytest.mark.parametrize("override", [None, "", usage.USAGE_ENDPOINT, "http://example.invalid/ping"])
def test_tests_cannot_call_sender_without_explicit_safe_override(store, monkeypatch, override):
    enabled()
    now = age()
    if override is not None:
        monkeypatch.setenv("UOINK_USAGE_ENDPOINT", override)
    assert not usage.send_due(now)
    usage._post.assert_not_called()


def test_daily_gate_retry_once_reset_and_history(store, monkeypatch):
    enabled()
    usage.count("searches")
    usage._queue.join()
    now = age()
    monkeypatch.setenv("UOINK_USAGE_ENDPOINT", "https://usage-test.invalid/v1/ping")
    sender = Mock(side_effect=[False, False, True] + [True] * 11)
    monkeypatch.setattr(usage, "_post", sender)
    assert not usage.send_due(now)
    first = sender.call_args.args[1]
    usage.count("searches")
    usage._queue.join()
    assert not usage.send_due(now + usage.DAY - 1)
    assert sender.call_count == 1
    assert usage.disclosure()["next_payload"] == first
    assert not usage.send_due(now + usage.DAY)
    assert sender.call_args.args[1] == first
    assert usage.send_due(now + 2 * usage.DAY)
    assert sender.call_args.args[1]["searches"] == 2
    assert usage.disclosure()["next_payload"]["searches"] == 0
    assert usage.disclosure()["sent"][0]["payload"] == sender.call_args.args[1]
    for day in range(3, 14):
        assert usage.send_due(now + day * usage.DAY)
    history = usage.disclosure()["sent"]
    assert len(history) == 10 and all(row["date"].endswith("Z") for row in history)
    assert not usage.send_due(now + 13 * usage.DAY + 1)


def test_opt_out_and_restart_do_not_bypass_daily_gate(store, monkeypatch):
    enabled()
    now = age()
    monkeypatch.setenv("UOINK_USAGE_ENDPOINT", "https://usage-test.invalid/v1/ping")
    monkeypatch.setattr(usage, "_post", Mock(return_value=True))
    assert usage.send_due(now)
    usage.set_enabled(False)
    enabled()
    assert not usage.send_due(now + 1)
    assert usage._post.call_count == 1


def test_first_send_waits_24_hours_after_consent(store, monkeypatch):
    enabled()
    with usage._transaction() as state:
        since = state["since"]
    monkeypatch.setenv("UOINK_USAGE_ENDPOINT", "https://usage-test.invalid/v1/ping")
    monkeypatch.setattr(usage, "_post", Mock(return_value=True))
    assert not usage.send_due(since + usage.DAY - 1)
    usage._post.assert_not_called()
    assert usage.send_due(since + usage.DAY)


def test_post_has_five_second_timeout_and_no_redirects(store, monkeypatch):
    payload = enabled()
    response = Mock(status=204)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    build = Mock(return_value=opener)
    monkeypatch.setattr(usage.urllib.request, "build_opener", build)
    assert _REAL_POST("https://usage-test.invalid/v1/ping", payload)
    request = opener.open.call_args.args[0]
    assert opener.open.call_args.kwargs == {"timeout": 5}
    assert request.method == "POST" and request.data == usage._encode(payload)
    assert isinstance(build.call_args.args[0], usage._NoRedirect)
    assert build.call_args.args[0].redirect_request(None, None, 302, None, None, "https://other.invalid") is None


@pytest.mark.parametrize("mode", ["environment", "empty_environment", "binding", "server_binding"])
def test_isolation_never_sends(store, monkeypatch, mode):
    enabled()
    now = age()
    monkeypatch.setenv("UOINK_USAGE_ENDPOINT", "https://usage-test.invalid/v1/ping")
    if mode == "binding":
        monkeypatch.setattr(isolation, "_CURRENT", isolation.IsolationBinding(store, 5187))
    elif mode == "server_binding":
        monkeypatch.setattr(server, "_ISOLATION", isolation.IsolationBinding(store, 5187))
    else:
        monkeypatch.setenv("UOINK_ISOLATED_ANYTHING", "" if mode == "empty_environment" else "1")
    assert not usage.send_due(now)
    usage._post.assert_not_called()


def test_nested_capture_counts_once_and_errors_are_failed(store):
    enabled()
    @usage.capture("page")
    def inner():
        raise ValueError("private title")
    @usage.capture("x")
    def outer():
        return inner()
    with pytest.raises(ValueError):
        outer()
    usage._queue.join()
    assert usage.disclosure()["next_payload"]["captures"] == {"x": {"ok": 0, "failed": 1}}


def test_queued_live_stream_is_not_a_finished_capture(store):
    enabled()
    @usage.capture("youtube")
    def live():
        return {"ok": True, "queued": True}
    live()
    usage._queue.join()
    assert usage.disclosure()["next_payload"]["captures"] == {}


def test_http_video_metadata_failure_is_counted(store, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    enabled()
    monkeypatch.setattr(server, "DESKTOP_ROOT", store)
    monkeypatch.setattr(server, "_manual_extraction_ownership", lambda url: nullcontext(
        SimpleNamespace(ok=True, conflict=None, completed_while_waiting=False)))
    monkeypatch.setattr(server, "_fetch_metadata", Mock(side_effect=ValueError("private title")))
    monkeypatch.setattr(server, "_record_single_extract_job", lambda *a, **k: {})
    monkeypatch.setattr(server._platform, "capability_refusal", lambda *args: None)
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: payload
    handler._handle_extract({"url": "https://www.youtube.com/watch?v=abcdefghijk", "interval": 30})
    usage._queue.join()
    assert usage.disclosure()["next_payload"]["captures"] == {"youtube": {"ok": 0, "failed": 1}}


def test_slow_counter_writer_never_blocks_caller(store, monkeypatch):
    enabled()
    entered, release = threading.Event(), threading.Event()
    def blocked(*args):
        entered.set()
        release.wait(5)
        raise OSError("disk error")
    monkeypatch.setattr(usage, "_record", blocked)
    try:
        usage.count("searches")
        assert entered.wait(2)
        done = threading.Event()
        threading.Thread(target=lambda: (usage.mcp_call("search_library", "stdio"), done.set()), daemon=True).start()
        assert done.wait(1)
    finally:
        release.set()
        usage._queue.join()


def test_stale_queued_event_does_not_cross_consent_periods(store):
    enabled()
    before = time.time()
    usage.set_enabled(False)
    enabled()
    usage._record(usage._path(), "searches", "count", "ok", before)
    assert usage.disclosure()["next_payload"]["searches"] == 0


def open_failure(kind):
    if kind == "permission":
        return PermissionError("sharing violation")
    error = usage.sqlite3.OperationalError("unable to open database file")
    error.sqlite_errorcode = usage.sqlite3.SQLITE_CANTOPEN
    return error


@pytest.mark.parametrize("kind", ["permission", "sqlite"])
@pytest.mark.parametrize("operation", ["record", "disclosure"])
def test_transient_database_open_failure_preserves_counts(store, monkeypatch, kind, operation):
    enabled()
    usage.count("searches")
    usage._queue.join()
    connect = usage.sqlite3.connect
    attempts = []

    def open_once_denied(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise open_failure(kind)
        return connect(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(usage.sqlite3, "connect", open_once_denied)
        if operation == "record":
            for _ in range(20):
                usage.count("searches")
            usage._queue.join()
        else:
            assert usage.disclosure()["next_payload"]["searches"] == 1
    assert usage.disclosure()["next_payload"]["searches"] == (21 if operation == "record" else 1)
    assert len(attempts) == (21 if operation == "record" else 2)
    usage._post.assert_not_called()


@pytest.mark.parametrize("kind", ["permission", "sqlite"])
def test_persistent_open_failure_is_bounded_and_does_not_escape_count(store, monkeypatch, kind):
    enabled()
    sleep = Mock()
    connect = Mock(side_effect=open_failure(kind))
    with monkeypatch.context() as patch:
        patch.setattr(usage.sqlite3, "connect", connect)
        patch.setattr(usage, "time", SimpleNamespace(time=time.time, sleep=sleep))
        usage.count("searches")
        usage._queue.join()
    assert 1 < connect.call_count <= 4
    assert sum(call.args[0] for call in sleep.call_args_list) <= 0.35 + 1e-9
    usage.count("searches")
    usage._queue.join()
    assert usage.disclosure()["next_payload"]["searches"] == 1
    usage._post.assert_not_called()


def test_queue_join_waits_for_sqlite_lock_and_committed_count(store, monkeypatch):
    enabled()
    entered, joined = threading.Event(), threading.Event()
    connect = usage.sqlite3.connect

    def observed_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(lambda sql: entered.set() if sql == "BEGIN IMMEDIATE" else None)
        return conn

    blocker = connect(usage._path())
    blocker.execute("BEGIN IMMEDIATE")
    waiter = threading.Thread(target=lambda: (usage._queue.join(), joined.set()), daemon=True)
    try:
        monkeypatch.setattr(usage.sqlite3, "connect", observed_connect)
        usage.count("searches")
        assert entered.wait(2)
        waiter.start()
        assert not joined.wait(0.05)
    finally:
        blocker.rollback()
        blocker.close()
        if waiter.ident is not None:
            waiter.join(10)
    assert joined.is_set()
    assert usage.disclosure()["next_payload"]["searches"] == 1


def test_stdio_wire_path_records_to_shared_file(store, monkeypatch):
    from tests.test_c01_mcp_stdio import _StdioClient, _isolated_env, ROOT
    env = _isolated_env(str(store))
    profile = Path(env["UOINK_ISOLATED_PROFILE"])
    monkeypatch.setattr(usage, "_root", lambda: profile)
    enabled()
    client = _StdioClient([sys.executable, str(ROOT / "uoink_mcp.py")], ROOT, env)
    try:
        client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "private client name", "version": "private"}}})
        assert "result" in client.wait_for(1)
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "search_uoinks", "arguments": {"query": ""}}})
        assert "result" in client.wait_for(2)
        deadline = time.monotonic() + 10  # the stdio child flushes counts asynchronously; slow runners need headroom
        while time.monotonic() < deadline:
            p = usage.disclosure()["next_payload"]
            # Tool and transport counts are separate queue entries.
            if (p and p["tools"].get("search_uoinks") and p["mcp_clients"].get("other")
                    and p["transports"].get("stdio")):
                break
            time.sleep(0.02)
        assert p["tools"] == {"search_uoinks": 1}
        assert p["mcp_clients"] == {"other": 1}
        assert p["transports"] == {"stdio": 1}
    finally:
        client.close()


def test_concurrent_processes_do_not_lose_counts(store):
    enabled()
    script = ('import sys; from pathlib import Path; import uoink_usage as u; '
              'u.configure(lambda: Path(sys.argv[1]), "3.10.0"); '
              '[u.count("searches") for _ in range(100)]; u._queue.join()')
    procs = [subprocess.Popen([sys.executable, "-c", script, str(store)]) for _ in range(2)]
    for proc in procs:
        assert proc.wait(timeout=15) == 0
    disclosure = usage.disclosure()
    assert disclosure["next_payload"] is not None, disclosure
    assert disclosure["next_payload"]["searches"] == 200


def test_settings_toggle_and_one_time_card(store, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_PATH", store / "settings.json")
    monkeypatch.setattr(server, "_ISOLATION", None)
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: "")
    monkeypatch.setattr(server, "_get_saved_scrapecreators_key", lambda: "")
    monkeypatch.setattr(server, "_load_topics", lambda: {})
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_reliability_model_status", lambda *args: {})
    monkeypatch.setattr(server.whisper_runner, "is_whisperx_available", lambda: False)
    handler = object.__new__(server.Handler)
    replies = []
    handler._send_json = lambda status, body: replies.append((status, body))
    handler._handle_settings_get()
    assert replies[-1][1]["settings"]["usage_sharing"] is False
    handler._handle_usage_prompt()
    assert replies[-1][1]["show"] is True
    handler._handle_usage_prompt()
    assert replies[-1][1]["show"] is False
    handler._handle_settings_post({"usage_sharing": True})
    assert replies[-1][1]["settings"]["usage_sharing"] is True
    assert usage.disclosure()["next_payload"] is not None
    handler._handle_settings_post({"usage_sharing": False, "usage_sharing_prompt_seen": False})
    assert server._read_settings()["usage_sharing_prompt_seen"] is True
    assert usage.disclosure()["next_payload"] is None
    monkeypatch.setenv("UOINK_USAGE_SHARING", "0")
    handler._handle_settings_post({"usage_sharing": True})
    assert replies[-1][1]["settings"]["usage_sharing"] is False
    assert replies[-1][1]["settings"]["usage_sharing_forced_off"] is True


def test_dashboard_disclosure_and_default_choice():
    root = Path(__file__).resolve().parents[1]
    html = (root / "assets/dashboard/index.html").read_text(encoding="utf-8")
    assert 'usageSharing: ["usage_sharing", false]' in html
    assert 'type="submit" id="usageNoThanks">No thanks' in html
    assert 'summary>See what is sent</summary>' in html
    assert 'JSON.stringify(disclosure.next_payload ?? null, null, 2)' in html
    assert 'JSON.stringify(disclosure.sent || [], null, 2)' in html
    assert 'Sharing is forced off by UOINK_USAGE_SHARING=0.' in html
    assert 'usageOptInCard' not in (root / "assets/splash/index.html").read_text(encoding="utf-8")


def test_dashboard_usage_javascript():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["node", str(root / "tests/js/usage_sharing_test.mjs")],
                            cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_http_mcp_counts_only_registered_names(store):
    enabled()
    handler = object.__new__(server.Handler)
    handler._send_mcp_result = lambda *args: None
    handler._handle_mcp_post("/mcp/v1", {"id": 1, "method": "initialize", "params": {
        "clientInfo": {"name": "Cursor", "version": "private"}}})
    handler._handle_mcp_post("/mcp/v1", {"id": 2, "method": "tools/call", "params": {
        "name": "search_uoinks", "arguments": {"query": ""}}})
    handler._handle_mcp_post("/mcp/v1", {"id": 3, "method": "tools/call", "params": {
        "name": "private unknown name", "arguments": {}}})
    usage._queue.join()
    p = usage.disclosure()["next_payload"]
    assert p["tools"] == {"search_uoinks": 1}
    assert p["transports"] == {"http": 1}
    assert p["mcp_clients"] == {"cursor": 1}


def test_http_capture_counts_persist_failure_as_failed(store, monkeypatch):
    enabled()
    monkeypatch.setattr(server, "_get_index", lambda: None)
    monkeypatch.setattr(server.page_extractor, "extract_page", lambda *a, **k: {
        "ok": True, "title": "private title", "url": "https://private.invalid"})
    monkeypatch.setattr(server.page_extractor, "persist_page_yoink", Mock(side_effect=OSError("failed")))
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: payload
    handler._handle_extract_page({"url": "https://private.invalid"})
    usage._queue.join()
    assert usage.disclosure()["next_payload"]["captures"] == {"page": {"ok": 0, "failed": 1}}


def test_generic_mcp_capture_probe_records_the_response(store, monkeypatch):
    enabled()
    @usage.capture("page", response=True)
    def handler(self, body):
        self._send_json(200, {"ok": True, "video_id": "private-id"})
    monkeypatch.setattr(server.Handler, "_handle_extract_any", handler)
    monkeypatch.setattr(tools, "_b", lambda: server)
    assert tools.uoink_url({"url": "https://private.invalid"})["ok"]
    usage._queue.join()
    assert usage.disclosure()["next_payload"]["captures"] == {"page": {"ok": 1, "failed": 0}}


def test_generic_http_capture_counts_metadata_failure(store, monkeypatch):
    enabled()
    monkeypatch.setattr(server, "DESKTOP_ROOT", store / "output")
    monkeypatch.setattr(server, "_fetch_metadata", Mock(side_effect=OSError("offline")))
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: payload
    handler._handle_extract_any({"url": "https://example.test/private-title?query=private"})
    usage._queue.join()
    assert usage.disclosure()["next_payload"]["captures"] == {"other": {"ok": 0, "failed": 1}}


def test_memory_browsing_does_not_count_as_a_search(store):
    enabled()
    idx = server.index.Index.open(store / "library.db")
    try:
        idx.search_yoinks_for_memory()
        usage._queue.join()
        assert usage.disclosure()["next_payload"]["searches"] == 0
        idx.search_yoinks_for_memory(q="private search text")
        usage._queue.join()
        assert usage.disclosure()["next_payload"]["searches"] == 1
    finally:
        idx.close()


def test_queued_events_survive_successful_send(store, monkeypatch):
    enabled()
    occurred = time.time()
    now = age()
    monkeypatch.setenv("UOINK_USAGE_ENDPOINT", "https://usage-test.invalid/v1/ping")
    monkeypatch.setattr(usage, "_post", Mock(return_value=True))
    assert usage.send_due(now)
    usage._record(usage._path(), "searches", "count", "ok", occurred)
    assert usage.disclosure()["next_payload"]["searches"] == 1


def test_success_clears_zero_keys_for_the_next_period(store, monkeypatch):
    enabled()
    names = list(tools.TOOL_REGISTRY)
    for name in names[:usage.MAX_TOOL_KEYS]:
        usage.count("tools", name)
    usage._queue.join()
    now = age()
    monkeypatch.setenv("UOINK_USAGE_ENDPOINT", "https://usage-test.invalid/v1/ping")
    monkeypatch.setattr(usage, "_post", Mock(return_value=True))
    assert usage.send_due(now)
    with usage._transaction() as state:
        assert state["counts"] == {}
    usage.count("tools", names[-1])
    usage._queue.join()
    assert usage.disclosure()["next_payload"]["tools"] == {names[-1]: 1}


def test_unrelated_settings_save_does_not_wait_on_usage_store(store, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_PATH", store / "settings.json")
    monkeypatch.setattr(usage, "set_enabled", Mock(side_effect=AssertionError("Unrelated write touched usage DB")))
    server._write_settings({"notifications_enabled": False})
    usage.set_enabled.assert_not_called()

"""Living Library Phase 2 stage 1 (run J, 2026-09-04): adapter, transport
parity, default-off apply, /health and user-intent route tests.

Written against the frozen contract (docs/library/PHASE2-CONTRACT-2026-09-04.md,
docs/library/phase2-contract/tool-schemas.json) with the deterministic
stand-in in tests/library_service_fake.py injected through the one seam,
uoink_mcp_tools.set_library_service. No sockets, no subprocesses, no model,
no network, and the live index is never opened: server._get_index is replaced
by a sentinel in every test that reaches the request context.

The stand-in is fixture evidence for the ADAPTERS only. It certifies nothing
about library_work.py; Gemini's tests/test_library_work_*.py and the service
audit (docs/library/SERVICE-AUDIT-PLAN-2026-09-04.md) cover that.
"""
from __future__ import annotations

import asyncio
import io
import json
import math
import re
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import openapi_bridge  # noqa: E402
import server  # noqa: E402
import uoink_mcp_tools as tools  # noqa: E402
from library_service_fake import (  # noqa: E402
    FakeLibraryService,
    RaisingLibraryService,
    StringErrorLibraryService,
)

CONTRACT = json.loads(
    (ROOT / "docs" / "library" / "phase2-contract" / "tool-schemas.json").read_text(encoding="utf-8")
)
HASH = "a" * 64
TOKEN43 = "A" * 43
INDEX_SENTINEL = object()
LOOPBACK_ORIGIN = f"http://127.0.0.1:{server.PORT}"


# ---------------------------------------------------------------------------
# Fixtures and probes
# ---------------------------------------------------------------------------

@pytest.fixture
def fake(monkeypatch):
    """Inject the stand-in, isolate settings and the index, reset limiters."""
    service = FakeLibraryService()
    tools.set_library_service(service)
    monkeypatch.setattr(server, "_get_index", lambda: INDEX_SENTINEL)
    monkeypatch.setattr(server, "_read_settings", lambda: {"librarian_apply_enabled": False})
    for limiter in tools._LIBRARY_RATE_LIMITERS.values():
        limiter._calls.clear()
    tools.bind_backend(server)
    try:
        yield service
    finally:
        tools.set_library_service(None)
        for limiter in tools._LIBRARY_RATE_LIMITERS.values():
            limiter._calls.clear()


@pytest.fixture
def no_service(monkeypatch):
    """Make `import library_work` fail deterministically, even on an
    integrated tree where the module exists."""
    monkeypatch.setitem(sys.modules, "library_work", None)
    tools.set_library_service(None)
    for limiter in tools._LIBRARY_RATE_LIMITERS.values():
        limiter._calls.clear()
    monkeypatch.setattr(server, "_read_settings", lambda: {})

    def forbidden():
        raise AssertionError("the index must not be opened for an unavailable service")

    monkeypatch.setattr(server, "_get_index", forbidden)
    tools.bind_backend(server)
    try:
        yield
    finally:
        tools.set_library_service(None)


class Probe(server.Handler):
    """Drive Handler.do_GET/do_POST without a socket. Auth is real (the header
    must carry server.TOKEN); Host validation is bypassed; _send_json captures."""

    def __init__(self, method: str, path: str, body=None, headers=None):
        self.command = method
        self.path = path
        self.client_address = ("127.0.0.1", 1)
        raw = b""
        if body is not None:
            raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.rfile = io.BytesIO(raw)
        base = {"X-Uoink-Token": server.TOKEN}
        if body is not None:
            base["Content-Type"] = "application/json"
            base["Content-Length"] = str(len(raw))
        base.update(headers or {})
        self.headers = base
        self.status = None
        self.payload = None

    def _reject_bad_host(self) -> bool:
        return False

    def _send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    def _send_empty(self, status: int = 202) -> None:
        self.status = status
        self.payload = None


def post(path, body=None, headers=None) -> Probe:
    probe = Probe("POST", path, body, headers)
    server.Handler.do_POST(probe)
    return probe


def mcp_call(name: str, arguments: dict) -> Probe:
    return post("/mcp/v1", {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": name, "arguments": arguments}})


def health(monkeypatch) -> Probe:
    monkeypatch.setattr(server.whisper_runner, "is_whisperx_available", lambda: False)
    monkeypatch.setattr(server.whisper_runner, "is_model_downloaded", lambda *_a: False)
    monkeypatch.setattr(server, "_path_integrity_status",
                        lambda: {"ok": True, "checked": 0, "missing": 0})
    monkeypatch.setattr(server, "_index_recovering", False)
    monkeypatch.setattr(server, "_OUTPUT_ROOT_FALLBACK", False)
    monkeypatch.setattr(server.index, "latest_schema_version", lambda: 26)
    monkeypatch.setattr(server, "_active_migration_version", 26)
    probe = Probe("GET", "/health")
    server.Handler.do_GET(probe)
    assert probe.status == 200
    return probe


def valid_submit(**overrides) -> dict:
    body = {
        "work_id": "work-0", "client_id": "claude-code", "attempt_token": TOKEN43,
        "submission_key": "submit-1", "schema_version": 1, "video_id": "video-0",
        "source_revision": HASH, "taxonomy_revision": "b" * 64, "packet_hash": "c" * 64,
        "result": {"outcome": "assigned", "memberships": [{
            "shelf_id": "shelf-1", "shelf_path": ["AI", "Agents"], "confidence": 0.9,
            "evidence": {"basis": "packet", "kind": "timed_clip", "excerpt_id": "d" * 64,
                         "card_hash": "e" * 64, "quote": "a quoted passage"},
        }]},
        "usage": {"status": "unavailable", "reason": "client did not report usage"},
    }
    body.update(overrides)
    return body


def valid_pin_operation() -> dict:
    return {"video_id": "video-0", "shelf_id": "shelf-1", "action": "pin",
            "expected_projection_revision": 7, "operation_key": "pin-op-1"}


# ---------------------------------------------------------------------------
# Interface freeze
# ---------------------------------------------------------------------------

def test_registry_schemas_are_the_frozen_contract_file():
    assert CONTRACT["contract_version"] == tools.LIBRARY_CONTRACT_VERSION
    frozen = {entry["name"]: entry["inputSchema"] for entry in CONTRACT["tools"]}
    assert set(frozen) == set(tools.LIBRARY_TOOL_NAMES)
    listed = {entry["name"]: entry["inputSchema"] for entry in tools.list_tools()}
    spec = openapi_bridge.build_spec("http://x", tool_registry=tools.TOOL_REGISTRY, version="0")
    for name, schema in frozen.items():
        assert tools.TOOL_REGISTRY[name].input_schema == schema, name
        assert listed[name] == schema, name
        # The OpenAPI spec publishes the frozen object itself, untouched.
        published = spec["paths"][f"/tools/{name}"]["post"]["requestBody"]["content"][
            "application/json"]["schema"]
        assert published is tools.TOOL_REGISTRY[name].input_schema
    json.dumps(spec)
    assert len(tools.TOOL_REGISTRY) == 77


def test_library_tools_are_registry_only_and_stdio_is_unchanged():
    import uoink_mcp
    from test_c01_mcp_stdio import CANONICAL_STDIO_TOOLS

    stdio = {tool.name for tool in asyncio.run(uoink_mcp.mcp.list_tools())}
    assert stdio == CANONICAL_STDIO_TOOLS
    assert stdio.isdisjoint(tools.LIBRARY_TOOL_NAMES)
    for name in tools.LIBRARY_TOOL_NAMES:
        # Limits are enforced inside the adapter so the error keeps the
        # contract envelope; the ToolSpec limiter must therefore be absent.
        assert tools.TOOL_REGISTRY[name].rate_limiter is None
        assert not re.match(r"^v\d+\.\d+", tools.TOOL_REGISTRY[name].description)


# ---------------------------------------------------------------------------
# Frozen-schema validation (identical on every transport)
# ---------------------------------------------------------------------------

VALID = [
    ("list_library_work", {}),
    ("list_library_work", {"run_id": "run-1", "state": "ready", "limit": 100, "cursor": "c"}),
    ("claim_library_work", {"action": "claim", "run_id": "run-1", "client_id": "cc"}),
    ("claim_library_work", {"action": "claim", "run_id": "run-1", "client_id": "cc",
                            "max_items": 12, "lease_seconds": 60}),
    ("claim_library_work", {"action": "renew", "work_id": "w", "client_id": "cc",
                            "attempt_token": TOKEN43, "lease_seconds": 900}),
    ("claim_library_work", {"action": "release", "work_id": "w", "client_id": "cc",
                            "attempt_token": TOKEN43, "reason": "done"}),
    ("claim_library_work", {"action": "cancel", "work_id": "w", "client_id": "cc",
                            "attempt_token": TOKEN43, "reason": "shutting down"}),
    ("submit_library_result", valid_submit()),
    ("submit_library_result", valid_submit(result={"outcome": "unmapped", "reason": "no shelf fits"})),
    ("submit_library_result", valid_submit(usage={
        "status": "reported", "model": "claude-fable-5-1", "input_tokens": 1,
        "output_tokens": 2, "cache_read_tokens": 0, "cache_create_tokens": 0,
        "wall_time_ms": 5})),
    ("apply_reshelving", {"run_id": "run-1", "expected_projection_revision": 0}),
    ("apply_reshelving", {"mode": "preview", "run_id": "run-1",
                          "expected_projection_revision": 3, "activate_version": True}),
    ("apply_reshelving", {"mode": "apply", "preview_id": "p", "expected_projection_revision": 3,
                          "delta_hash": HASH, "operation_key": "k"}),
    ("pin_shelf", {**valid_pin_operation(), "user_intent_token": TOKEN43, "reason": "mine"}),
    ("undo_library_apply", {"apply_id": "apply-1", "expected_projection_revision": 8,
                            "operation_key": "undo-1", "user_intent_token": TOKEN43}),
]

INVALID = [
    # (tool, arguments, field the error must name)
    ("list_library_work", {"limit": True}, "limit"),                       # bool as integer
    ("list_library_work", {"limit": 0}, "limit"),
    ("list_library_work", {"limit": 101}, "limit"),
    ("list_library_work", {"state": "done"}, "state"),
    ("list_library_work", {"cursor": ""}, "cursor"),
    ("list_library_work", {"kind": "assign"}, "kind"),                     # unknown field
    ("claim_library_work", {"action": "steal", "run_id": "r", "client_id": "c"}, "request"),
    ("claim_library_work", {"action": "claim", "client_id": "c"}, "run_id"),
    ("claim_library_work", {"action": "claim", "run_id": "r", "client_id": "c",
                            "max_items": 13}, "max_items"),
    ("claim_library_work", {"action": "claim", "run_id": "r", "client_id": "c",
                            "lease_seconds": 59}, "lease_seconds"),
    ("claim_library_work", {"action": "renew", "work_id": "w", "client_id": "c",
                            "attempt_token": TOKEN43}, "lease_seconds"),
    ("claim_library_work", {"action": "release", "work_id": "w", "client_id": "c",
                            "attempt_token": "short", "reason": "r"}, "attempt_token"),
    ("claim_library_work", {"action": "cancel", "work_id": "w", "client_id": "c" * 65,
                            "attempt_token": TOKEN43, "reason": "r"}, "client_id"),
    ("submit_library_result", valid_submit(schema_version="1"), "schema_version"),
    ("submit_library_result", valid_submit(schema_version=True), "schema_version"),
    ("submit_library_result", valid_submit(schema_version=2), "schema_version"),
    ("submit_library_result", valid_submit(source_revision="A" * 64), "source_revision"),
    ("submit_library_result", valid_submit(packet_hash="c" * 63), "packet_hash"),
    ("submit_library_result", valid_submit(attempt_token="not a token"), "attempt_token"),
    ("submit_library_result", valid_submit(extra=1), "extra"),
    ("submit_library_result", valid_submit(result={"outcome": "assigned", "memberships": []}),
     "result.memberships"),
    ("submit_library_result", valid_submit(result={"outcome": "assigned"}), "result.memberships"),
    ("submit_library_result", valid_submit(result={"outcome": "unmapped"}), "result.reason"),
    ("submit_library_result", valid_submit(result={"outcome": "unmapped", "reason": "x",
                                                   "memberships": []}), "result.memberships"),
    ("submit_library_result", valid_submit(result={"outcome": "assigned", "memberships": [
        {"shelf_id": "s", "shelf_path": ["A", "B", "C", "D"], "confidence": 0.9,
         "evidence": valid_submit()["result"]["memberships"][0]["evidence"]}]}),
     "result.memberships[0].shelf_path"),
    ("submit_library_result", valid_submit(result={"outcome": "assigned", "memberships": [
        {"shelf_id": "s", "shelf_path": ["A", 7], "confidence": 0.9,
         "evidence": valid_submit()["result"]["memberships"][0]["evidence"]}]}),
     "result.memberships[0].shelf_path[1]"),                              # H-1: non-string segment
    ("submit_library_result", valid_submit(result={"outcome": "assigned", "memberships": [
        {"shelf_id": "s", "shelf_path": ["A"], "confidence": 1.5,
         "evidence": valid_submit()["result"]["memberships"][0]["evidence"]}]}),
     "result.memberships[0].confidence"),
    ("submit_library_result", valid_submit(result={"outcome": "assigned", "memberships": [
        {"shelf_id": "s", "shelf_path": ["A"], "confidence": math.nan,
         "evidence": valid_submit()["result"]["memberships"][0]["evidence"]}]}),
     "result.memberships[0].confidence"),                                  # NaN never validates
    ("submit_library_result", valid_submit(result={"outcome": "assigned", "memberships": [
        {"shelf_id": "s", "shelf_path": ["A"], "confidence": True,
         "evidence": valid_submit()["result"]["memberships"][0]["evidence"]}]}),
     "result.memberships[0].confidence"),
    ("submit_library_result", valid_submit(result={"outcome": "assigned", "memberships": [
        {"shelf_id": "s", "shelf_path": ["A"], "confidence": 0.7,
         "evidence": {"basis": "guess", "kind": "timed_clip", "excerpt_id": HASH,
                      "card_hash": HASH, "quote": "q"}}]}),
     "result.memberships[0].evidence.basis"),
    ("submit_library_result", valid_submit(result={"outcome": "assigned", "memberships": [
        {"shelf_id": "s", "shelf_path": ["A"], "confidence": 0.7,
         "evidence": {"basis": "packet", "kind": "timed_clip", "excerpt_id": HASH,
                      "card_hash": HASH, "quote": ""}}]}),
     "result.memberships[0].evidence.quote"),
    ("submit_library_result", valid_submit(usage={"status": "reported", "model": "m",
                                                  "input_tokens": 1, "output_tokens": 1}),
     "usage.wall_time_ms"),
    ("submit_library_result", valid_submit(usage={"status": "unavailable"}), "usage.reason"),
    ("submit_library_result", valid_submit(usage={"status": "reported", "model": "m",
                                                  "input_tokens": -1, "output_tokens": 1,
                                                  "wall_time_ms": 1}), "usage.input_tokens"),
    ("apply_reshelving", {"mode": "apply", "run_id": "r", "expected_projection_revision": 1},
     "preview_id"),
    ("apply_reshelving", {"mode": "apply", "preview_id": "p", "expected_projection_revision": 1,
                          "operation_key": "k"}, "delta_hash"),
    ("apply_reshelving", {"run_id": "r", "expected_projection_revision": -1},
     "expected_projection_revision"),
    ("apply_reshelving", {"run_id": "r", "expected_projection_revision": 1, "max_churn": 0.5},
     "max_churn"),                                                          # no client override
    ("apply_reshelving", {"run_id": "r", "expected_projection_revision": 1,
                          "activate_version": "yes"}, "activate_version"),
    ("pin_shelf", valid_pin_operation(), "user_intent_token"),              # token required
    ("pin_shelf", {**valid_pin_operation(), "user_intent_token": TOKEN43, "actor": "user"}, "actor"),
    ("pin_shelf", {**valid_pin_operation(), "action": "lock", "user_intent_token": TOKEN43}, "action"),
    ("undo_library_apply", {"apply_id": "a", "expected_projection_revision": 1,
                            "operation_key": "k"}, "user_intent_token"),
    ("undo_library_apply", {"apply_id": "", "expected_projection_revision": 1,
                            "operation_key": "k", "user_intent_token": TOKEN43}, "apply_id"),
]


@pytest.mark.parametrize("name,arguments", VALID)
def test_validator_accepts_contract_shaped_requests(name, arguments):
    assert tools.library_validate_arguments(name, arguments) is None


@pytest.mark.parametrize("name,arguments,field", INVALID)
def test_validator_rejects_malformed_requests_naming_the_field(name, arguments, field):
    error = tools.library_validate_arguments(name, arguments)
    assert error is not None, (name, arguments)
    assert error.field == field, (error.field, str(error))
    envelope = tools.library_invalid_request(error)
    assert envelope["ok"] is False
    assert envelope["schema_version"] == 1
    assert envelope["error"]["code"] == "invalid_request"
    assert envelope["error"]["retryable"] is False
    assert envelope["error"]["details"]["field"] == field


def test_malformed_request_never_reaches_the_service(fake):
    result = tools.call_tool("submit_library_result", valid_submit(schema_version=True))
    assert result["error"]["code"] == "invalid_request"
    assert fake.calls == []


# ---------------------------------------------------------------------------
# The seam
# ---------------------------------------------------------------------------

def test_unavailable_service_answers_explicitly_without_opening_the_index(no_service):
    assert tools._library_service() is None
    for name, arguments in VALID:
        result = tools.call_tool(name, arguments)
        assert result["ok"] is False, name
        assert result["schema_version"] == 1
        assert result["error"]["code"] == "service_unavailable", name
        assert result["error"]["retryable"] is False
        assert result["error"]["details"]["module"] == "library_work"
    # The same answer through the two HTTP transports.
    http = post("/tools/list_library_work", {})
    assert http.status == 200
    assert http.payload["error"]["code"] == "service_unavailable"
    rpc = mcp_call("list_library_work", {})
    assert rpc.payload["result"]["isError"] is True
    assert rpc.payload["result"]["structuredContent"]["error"]["code"] == "service_unavailable"


def test_service_method_map_covers_every_tool_and_discriminator(fake):
    calls = [
        ("list_library_work", {}, "list_work"),
        ("claim_library_work", {"action": "claim", "run_id": "r", "client_id": "c"}, "claim_work"),
        ("claim_library_work", {"action": "renew", "work_id": "w", "client_id": "c",
                                "attempt_token": TOKEN43, "lease_seconds": 60}, "renew_attempt"),
        ("claim_library_work", {"action": "release", "work_id": "w", "client_id": "c",
                                "attempt_token": TOKEN43, "reason": "r"}, "release_attempt"),
        ("claim_library_work", {"action": "cancel", "work_id": "w", "client_id": "c",
                                "attempt_token": TOKEN43, "reason": "r"}, "cancel_attempt"),
        ("submit_library_result", valid_submit(), "submit_result"),
        ("apply_reshelving", {"run_id": "r", "expected_projection_revision": 7}, "preview_apply"),
        ("pin_shelf", {**valid_pin_operation(), "user_intent_token": TOKEN43}, "pin_shelf"),
        ("undo_library_apply", {"apply_id": "a", "expected_projection_revision": 7,
                                "operation_key": "k", "user_intent_token": TOKEN43}, "undo_apply"),
    ]
    for name, arguments, method in calls:
        fake.calls.clear()
        result = tools.call_tool(name, arguments)
        assert result["schema_version"] == 1, name
        assert fake.calls[-1][0] == method, name
        assert fake.calls[-1][1] == arguments, name
    assert set(tools.LIBRARY_SERVICE_METHODS.values()) == {
        "list_work", "claim_work", "renew_attempt", "release_attempt", "cancel_attempt",
        "submit_result", "preview_apply", "apply_preview", "pin_shelf", "undo_apply"}


def test_trusted_context_carries_index_clock_flag_and_no_user_authority(fake):
    before = int(time.time() * 1000)
    tools.call_tool("claim_library_work", {"action": "claim", "run_id": "r", "client_id": "c"})
    method, arguments, context = fake.calls[-1]
    assert method == "claim_work"
    assert context["index"] is INDEX_SENTINEL
    assert context["apply_enabled"] is False
    assert context["actor"] == "registry"
    assert context["transport"] == "registry"
    assert context["contract_version"] == tools.LIBRARY_CONTRACT_VERSION
    assert context["schema_version"] == 1
    assert isinstance(context["now_ms"], int) and before <= context["now_ms"] <= before + 60_000
    # Run N acceptance N-1: tool calls carry the helper's trusted session (the
    # same one dashboard-minted capabilities bind to), derived from the
    # backend, never from tool JSON. Authority is still absent: actor stays
    # "registry", and no user_intent_token is invented.
    assert context["session_hash"] == server._library_session_hash()
    assert len(context["session_hash"]) == 64
    assert "user_intent_token" not in arguments


def test_service_exception_is_logged_not_echoed(fake, monkeypatch):
    tools.set_library_service(RaisingLibraryService())
    monkeypatch.setattr(server, "_get_index", lambda: INDEX_SENTINEL)
    result = tools.call_tool("list_library_work", {})
    assert result == {
        "ok": False, "schema_version": 1,
        "error": {"code": "internal_error", "retryable": False,
                  "message": "The Librarian service raised an unexpected error; see the helper log.",
                  "details": {"tool": "list_library_work", "method": "list_work"}},
    }
    text = json.dumps(result)
    assert "index.db" not in text and "Users" not in text and "sqlite" not in text


def test_non_conforming_service_error_is_normalised(fake):
    tools.set_library_service(StringErrorLibraryService())
    result = tools.call_tool("list_library_work", {})
    assert result["ok"] is False
    assert result["schema_version"] == 1
    assert result["error"] == {"code": "service_error", "message": "run not found",
                               "retryable": False, "details": {}}


def test_malformed_service_return_is_an_internal_error(fake, monkeypatch):
    class Broken(FakeLibraryService):
        def list_work(self, arguments, context):
            return ["not", "an", "envelope"]

    tools.set_library_service(Broken())
    result = tools.call_tool("list_library_work", {})
    assert result["error"]["code"] == "internal_error"


def test_rate_limit_uses_the_contract_envelope(fake):
    limiter = tools._LIBRARY_RATE_LIMITERS["undo_library_apply"]
    limiter._calls[:] = [time.monotonic()] * limiter.max_calls
    result = tools.call_tool("undo_library_apply", {
        "apply_id": "a", "expected_projection_revision": 7, "operation_key": "k",
        "user_intent_token": TOKEN43})
    assert result["ok"] is False and result["schema_version"] == 1
    assert result["error"]["code"] == "rate_limited"
    assert result["error"]["retryable"] is True
    assert fake.calls == []


# ---------------------------------------------------------------------------
# Default-off apply
# ---------------------------------------------------------------------------

def test_apply_is_refused_while_the_setting_is_off_and_preview_still_works(fake):
    preview = tools.call_tool("apply_reshelving", {"run_id": "r", "expected_projection_revision": 7})
    assert preview["ok"] is True and preview["preview_id"] == "preview-1"
    apply = tools.call_tool("apply_reshelving", {
        "mode": "apply", "preview_id": "preview-1", "expected_projection_revision": 7,
        "delta_hash": preview["delta_hash"], "operation_key": "apply-1"})
    assert apply == {
        "ok": False, "schema_version": 1,
        "error": {"code": "apply_disabled", "retryable": False,
                  "message": "Applying labels is disabled on this helper "
                             "(librarian_apply_enabled=false); preview remains available.",
                  "details": {"setting": "librarian_apply_enabled"}},
    }
    assert [call[0] for call in fake.calls] == ["preview_apply"]
    assert fake.projection_revision == 7


def test_apply_reaches_the_service_only_when_enabled_by_the_json_true(fake, monkeypatch):
    request = {"mode": "apply", "preview_id": "preview-1", "expected_projection_revision": 7,
               "delta_hash": HASH, "operation_key": "apply-1"}
    for truthy_but_off in ("true", 1, "yes"):
        monkeypatch.setattr(server, "_read_settings",
                            lambda v=truthy_but_off: {"librarian_apply_enabled": v})
        assert tools.call_tool("apply_reshelving", request)["error"]["code"] == "apply_disabled"
    monkeypatch.setattr(server, "_read_settings", lambda: {"librarian_apply_enabled": True})
    result = tools.call_tool("apply_reshelving", request)
    assert result["ok"] is True
    assert (result["before_revision"], result["after_revision"]) == (7, 8)
    assert fake.calls[-1][0] == "apply_preview"
    assert fake.calls[-1][2]["apply_enabled"] is True


def test_setting_defaults_off_normalises_strictly_and_is_not_dashboard_writable():
    assert server._default_settings()["librarian_apply_enabled"] is False
    assert server._normalize_settings({})["librarian_apply_enabled"] is False
    for value in ("true", 1, "yes", None, [True]):
        assert server._normalize_settings({"librarian_apply_enabled": value})[
            "librarian_apply_enabled"] is False, value
    assert server._normalize_settings({"librarian_apply_enabled": True})[
        "librarian_apply_enabled"] is True
    # The dashboard's settings route does not know the key: the gates behind
    # enabling apply are recorded evidence, not a checkbox.
    probe = post("/settings", {"librarian_apply_enabled": True})
    assert probe.status == 400
    assert probe.payload == {"ok": False, "error": "settings field required"}


# ---------------------------------------------------------------------------
# Transport parity (P2-6)
# ---------------------------------------------------------------------------

def test_registry_http_and_jsonrpc_return_identical_revisions(fake):
    direct = tools.call_tool("list_library_work", {"limit": 5})
    http = post("/tools/list_library_work", {"limit": 5})
    rpc = mcp_call("list_library_work", {"limit": 5})

    assert http.status == 200 and http.payload["ok"] is True
    assert rpc.status == 200 and rpc.payload["result"]["isError"] is False
    assert direct == http.payload["result"] == rpc.payload["result"]["structuredContent"]
    assert direct["run_revision"] == 3 and direct["projection_revision"] == 7
    assert direct["waiting_for_client"] is True
    assert json.loads(rpc.payload["result"]["content"][0]["text"]) == direct

    preview = {"run_id": "run-fixture", "expected_projection_revision": 7}
    a = tools.call_tool("apply_reshelving", preview)
    b = post("/tools/apply_reshelving", preview).payload["result"]
    c = mcp_call("apply_reshelving", preview).payload["result"]["structuredContent"]

    def timeless(payload):
        # expires_ms comes from the server clock at each call; everything
        # else, including the delta hash, must be identical.
        return {k: v for k, v in payload.items() if k != "expires_ms"}

    assert timeless(a) == timeless(b) == timeless(c)
    assert a["delta_hash"] == b["delta_hash"] == c["delta_hash"]
    assert a["expected_projection_revision"] == 7 and a["can_apply"] is False
    assert {call[2]["transport"] for call in fake.calls} == {"registry"}


def test_malformed_input_gets_the_same_envelope_on_every_transport(fake):
    bad = {"limit": 0}
    direct = tools.call_tool("list_library_work", bad)
    http = post("/tools/list_library_work", bad)
    rpc = mcp_call("list_library_work", bad)
    assert direct["error"]["code"] == "invalid_request"
    assert http.status == 400            # HTTP surfaces schema errors as 400 ...
    assert http.payload == direct        # ... with the identical contract body
    assert rpc.status == 200             # JSON-RPC carries it inside the result
    assert rpc.payload["result"]["isError"] is True
    assert rpc.payload["result"]["structuredContent"] == direct
    assert fake.calls == []


def test_idempotent_retry_and_conflict_pass_through_unaltered(fake):
    body = valid_submit()
    first = post("/tools/submit_library_result", body).payload["result"]
    again = mcp_call("submit_library_result", body).payload["result"]["structuredContent"]
    assert first == again
    assert first["outcome"] == "accepted" and first["accepted_memberships"] == ["shelf-1"]
    changed = valid_submit(result={"outcome": "unmapped", "reason": "changed my mind"})
    conflict = tools.call_tool("submit_library_result", changed)
    assert conflict["error"]["code"] == "idempotency_conflict"
    assert conflict["error"]["retryable"] is False


def test_tool_transports_decode_json_strictly(fake):
    nan = post("/tools/list_library_work", b'{"limit": NaN}')
    assert nan.status == 400 and nan.payload["error"].startswith("Bad JSON")
    infinity = post("/mcp/v1", b'{"jsonrpc":"2.0","id":1,"method":"tools/call",'
                               b'"params":{"name":"list_library_work","arguments":{"limit":Infinity}}}')
    assert infinity.status == 400 and infinity.payload["error"].startswith("Bad JSON")
    duplicate = post("/tools/list_library_work", b'{"limit": 1, "limit": 2}')
    assert duplicate.status == 400 and "duplicate" in duplicate.payload["error"]
    assert fake.calls == []
    # Other routes keep the lenient decoder they always had.
    assert server._strict_json_route("/tools/anything")
    assert server._strict_json_route("/mcp/v1") and server._strict_json_route("/mcp/v1/tools/call")
    assert server._strict_json_route("/library/intent")
    assert not server._strict_json_route("/settings")
    assert not server._strict_json_route("/extract")


# ---------------------------------------------------------------------------
# /health and the dashboard
# ---------------------------------------------------------------------------

LIBRARY_HEALTH_KEYS = {"status", "waiting_for_client", "ready", "leased", "run_revision",
                       "recovery_state", "error_code", "apply_enabled", "contract_version"}


def test_health_reports_waiting_for_client_from_the_open_index_only(fake, monkeypatch):
    monkeypatch.setattr(server, "_index_singleton", None)
    unknown = health(monkeypatch).payload["library"]
    assert unknown["status"] == "unknown" and unknown["waiting_for_client"] is False
    assert unknown["contract_version"] == tools.LIBRARY_CONTRACT_VERSION
    assert fake.calls == []                       # nothing opened, nothing asked

    monkeypatch.setattr(server, "_index_singleton", INDEX_SENTINEL)
    waiting = health(monkeypatch).payload["library"]
    assert set(waiting) == LIBRARY_HEALTH_KEYS
    assert waiting["status"] == "waiting_for_client"
    assert waiting["waiting_for_client"] is True
    assert (waiting["ready"], waiting["leased"], waiting["run_revision"]) == (2, 0, 3)
    assert waiting["recovery_state"] == "ready"
    assert waiting["apply_enabled"] is False
    assert fake.calls[-1][0] == "list_work"
    assert fake.calls[-1][2]["index"] is INDEX_SENTINEL
    assert fake.calls[-1][2]["transport"] == "health"

    fake.ready, fake.leased = 1, 1
    later = time.monotonic() + 60
    collecting = tools.library_status(INDEX_SENTINEL, apply_enabled=False, now=later)
    assert collecting["status"] == "collecting" and collecting["waiting_for_client"] is False
    fake.ready, fake.leased = 0, 0
    idle = tools.library_status(INDEX_SENTINEL, apply_enabled=True, now=later + 60)
    assert idle["status"] == "idle" and idle["apply_enabled"] is True
    fake.recovery_state = "pending"
    recovering = tools.library_status(INDEX_SENTINEL, apply_enabled=False, now=later + 120)
    assert recovering["status"] == "recovery_pending"


def test_health_without_the_service_says_unavailable_and_survives_errors(no_service, monkeypatch):
    monkeypatch.setattr(server, "_index_singleton", INDEX_SENTINEL)
    payload = health(monkeypatch).payload["library"]
    assert payload["status"] == "unavailable" and payload["waiting_for_client"] is False
    tools.set_library_service(RaisingLibraryService())
    errored = tools.library_status(INDEX_SENTINEL, apply_enabled=False, now=time.monotonic() + 999)
    assert errored["status"] == "error" and errored["waiting_for_client"] is False


def test_health_library_block_is_documented_in_both_probe_docs(fake, monkeypatch):
    monkeypatch.setattr(server, "_index_singleton", INDEX_SENTINEL)
    live = health(monkeypatch).payload["library"]
    for path, pattern in (
        (ROOT / "README_server.md", r"### `GET /ping`.*?```json\s*(\{.*?\})\s*```"),
        (ROOT / "docs" / "v2-api.md", r"### GET /health and GET /ping.*?```json\s*(\{.*?\})\s*```"),
    ):
        match = re.search(pattern, path.read_text(encoding="utf-8"), re.DOTALL)
        assert match is not None, path
        documented = json.loads(match.group(1))
        assert set(documented["library"]) == set(live) == LIBRARY_HEALTH_KEYS, path
    security = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")
    assert "`library` block" in security
    assert "`POST /library/intent`" in security


def test_dashboard_renders_the_library_status_line():
    html = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert 'id="librarianStatus"' in html
    assert "renderLibrarianStatus(data.library)" in html
    assert "waiting for a connected client" in html
    assert "renderLibrarianStatus(null)" in html   # offline path degrades honestly


# ---------------------------------------------------------------------------
# POST /library/intent
# ---------------------------------------------------------------------------

def intent_body(**overrides) -> dict:
    body = {"kind": "pin", "operation": valid_pin_operation(), "confirmed": True}
    body.update(overrides)
    return body


def test_intent_route_mints_a_token_that_pin_shelf_then_consumes(fake):
    probe = post("/library/intent", intent_body(), headers={"Origin": LOOPBACK_ORIGIN,
                                                           "Sec-Fetch-Site": "same-origin"})
    assert probe.status == 200, probe.payload
    minted = probe.payload
    assert minted["ok"] is True and minted["schema_version"] == 1
    token = minted["user_intent_token"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token)
    assert minted["kind"] == "pin" and len(minted["request_hash"]) == 64
    method, arguments, context = fake.calls[-1]
    assert method == tools.LIBRARY_INTENT_METHOD == "mint_user_intent"
    assert arguments == {"kind": "pin", "operation": valid_pin_operation()}
    assert context["actor"] == "user" and context["transport"] == "dashboard"
    assert context["intent_ttl_ms"] == 5 * 60 * 1000
    assert re.fullmatch(r"[0-9a-f]{64}", context["session_hash"])
    assert context["session_hash"] == server._library_session_hash()
    assert server.TOKEN not in json.dumps(minted)
    assert minted["expires_ms"] == context["now_ms"] + 5 * 60 * 1000

    pinned = tools.call_tool("pin_shelf", {**valid_pin_operation(), "user_intent_token": token})
    assert pinned["ok"] is True
    assert (pinned["before_revision"], pinned["after_revision"]) == (7, 8)


def test_intent_route_requires_the_helper_token_and_a_dashboard_origin(fake):
    wrong = post("/library/intent", intent_body(), headers={"X-Uoink-Token": "nope",
                                                           "Origin": LOOPBACK_ORIGIN})
    assert wrong.status == 403
    for headers in (
        {"Origin": "chrome-extension://abcdefghijklmnop"},
        {"Origin": "https://www.youtube.com"},
        {"Origin": "http://127.0.0.1:1"},                  # wrong port
        {"Origin": "https://127.0.0.1:" + str(server.PORT)},  # wrong scheme
        {"Origin": "http://evil.example"},
        {"Origin": LOOPBACK_ORIGIN, "Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ):
        probe = post("/library/intent", intent_body(), headers=headers)
        assert probe.status == 403, headers
        assert probe.payload == {"ok": False, "error": "forbidden"}
    assert fake.calls == []
    # Absent Origin (same-process WebView) and localhost forms are accepted.
    for headers in ({}, {"Origin": f"http://localhost:{server.PORT}"},
                    {"Origin": LOOPBACK_ORIGIN, "Sec-Fetch-Site": "none"}):
        assert post("/library/intent", intent_body(), headers=headers).status == 200, headers


@pytest.mark.parametrize("body,field", [
    (intent_body(confirmed=1), "confirmed"),
    ({"kind": "pin", "operation": valid_pin_operation()}, "confirmed"),
    (intent_body(kind="apply"), "kind"),
    (intent_body(operation={**valid_pin_operation(), "user_intent_token": TOKEN43}),
     "operation.user_intent_token"),
    (intent_body(operation={**valid_pin_operation(), "actor": "user"}), "operation.actor"),
    (intent_body(kind="undo"), "operation.apply_id"),
    (intent_body(operation={"video_id": "v", "shelf_id": "s", "action": "pin",
                            "operation_key": "k"}), "operation.expected_projection_revision"),
    (intent_body(extra=True), "extra"),
])
def test_intent_route_rejects_malformed_confirmations(fake, body, field):
    probe = post("/library/intent", body, headers={"Origin": LOOPBACK_ORIGIN})
    assert probe.status == 400, probe.payload
    assert probe.payload["error"]["code"] == "invalid_request"
    assert probe.payload["error"]["details"]["field"] == field
    assert fake.calls == []


def test_intent_route_decodes_strictly(fake):
    nan = post("/library/intent", b'{"kind":"pin","operation":{},"confirmed":true,"x":NaN}',
               headers={"Origin": LOOPBACK_ORIGIN})
    assert nan.status == 400 and nan.payload["error"].startswith("Bad JSON")
    duplicate = post("/library/intent", b'{"kind":"pin","kind":"undo","operation":{},"confirmed":true}',
                     headers={"Origin": LOOPBACK_ORIGIN})
    assert duplicate.status == 400 and "duplicate" in duplicate.payload["error"]
    assert fake.calls == []


def test_intent_route_without_service_is_explicit(no_service):
    probe = post("/library/intent", intent_body(), headers={"Origin": LOOPBACK_ORIGIN})
    assert probe.status == 200
    assert probe.payload["error"]["code"] == "service_unavailable"


def test_undo_intent_binds_the_undo_operation(fake):
    operation = {"apply_id": "apply-1", "expected_projection_revision": 7, "operation_key": "undo-1"}
    probe = post("/library/intent", {"kind": "undo", "operation": operation, "confirmed": True},
                 headers={"Origin": LOOPBACK_ORIGIN})
    assert probe.status == 200, probe.payload
    token = probe.payload["user_intent_token"]
    assert fake.intents[token]["kind"] == "undo"
    undone = tools.call_tool("undo_library_apply", {**operation, "user_intent_token": token})
    assert undone["ok"] is True and undone["apply_id"] == "undo-1"
    # A token the route never minted is the service's decision to refuse.
    refused = tools.call_tool("undo_library_apply", {**operation, "user_intent_token": TOKEN43})
    assert refused["error"]["code"] == "invalid_user_intent"


# ---------------------------------------------------------------------------
# Packaging (P2-0: installed imports without checkout)
# ---------------------------------------------------------------------------

def test_library_work_is_staged_installed_and_preflighted():
    from test_installer_files_complete import installed_sources, staged_sources
    assert "library_work.py" in staged_sources()
    assert "library_work.py" in installed_sources()
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*'library_work\.py',\s*$", build), "missing from the preflight list"

"""T4: socket-free HTTP probes, an in-memory library and mocked Anthropic."""
from __future__ import annotations

import io
import json
import socket
import urllib.request
from unittest.mock import Mock

import pytest

import library_resources
import research_playbooks
import server
import usage_meter
from tests.test_research_playbooks import library  # noqa: F401 -- shared fixture


@pytest.fixture(autouse=True)
def no_network_or_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("playbook route tests must not use network or credentials")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: "fixture-key")
    monkeypatch.setattr(server, "_store_saved_anthropic_key", forbidden)
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server, "_write_settings", forbidden)
    monkeypatch.setattr(server, "_mark_anthropic_key_invalid", Mock())
    monkeypatch.setattr(server, "TOKEN", "fixture-helper-token")


class Probe(server.Handler):
    """Exercise real Host, token, JSON parsing and routing without a socket."""

    def __init__(self, path, body, *, headers=None):
        self.command = "POST"
        self.path = path
        self.client_address = ("127.0.0.1", 1)
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.rfile = io.BytesIO(raw)
        self.headers = {"Host": f"127.0.0.1:{server.PORT}",
                        "X-Uoink-Token": server.TOKEN,
                        "Content-Type": "application/json", "Content-Length": str(len(raw)),
                        **(headers or {})}
        self.status = None
        self.payload = None

    def _send_json(self, status, payload):
        self.status, self.payload = status, payload


def post(body, *, path="/playbooks/run", headers=None):
    probe = Probe(path, body, headers=headers)
    probe.do_POST()
    return probe


CASES = [
    ("outlier-posts", {"author": "fixture"}),
    ("transcript-intel", {"video_ids": "a,b"}),
    ("comment-mining", {"author": "fixture", "lens": "demand"}),
    ("creator-teardown", {"author": "fixture"}),
    ("repurpose-pack", {"video_ids": "a,b"}),
]


@pytest.fixture
def route(library, monkeypatch):
    reader, seed, conn = library
    for vid in ("a", "b", "c"):
        seed(vid, clips=4, sidecar={"comments": [{"text": "I wish this had a guide"}]})
    monkeypatch.setattr(library_resources, "make_reader", lambda backend: reader)
    monkeypatch.setattr(server, "_get_index", lambda: reader.index)
    monkeypatch.setattr(server, "_get_existing_index", lambda **kwargs: reader.index)
    response = {"model": server.ANTHROPIC_MODEL,
                "content": [{"type": "text", "text": "A useful source. [cap:a]\n99 ideas\nUnknown. [cap:absent]"}],
                "usage": {"input_tokens": 321, "output_tokens": 45,
                          "cache_creation_input_tokens": 12, "cache_read_input_tokens": 34}}

    def respond(*args, **kwargs):
        assert reader.guard._active == 0  # no read lease held during inference
        return response

    model = Mock(side_effect=respond)
    monkeypatch.setattr(server, "_anthropic_messages", model)
    return reader, seed, conn, model


@pytest.fixture
def mcp_adapter(route, monkeypatch):
    import uoink_mcp
    import uoink_mcp_tools
    from mcp import types

    monkeypatch.setattr(uoink_mcp_tools, "_backend", server)
    return (*route[:3], uoink_mcp.mcp._mcp_server.request_handlers, types)


@pytest.mark.parametrize("name,arguments", CASES)
def test_run_uses_shared_packet_records_usage_and_returns_citation_warnings(route, name, arguments):
    reader, _, conn, model = route
    expected = research_playbooks.get_playbook_input(reader, name, arguments)
    probe = post({"playbook": name, "arguments": arguments})
    assert probe.status == 200 and probe.payload["ok"] is True
    model.assert_called_once_with("fixture-key", system=expected["instruction"],
                                  user=library_resources.render_document(expected["packet"]), max_tokens=4096)
    assert probe.payload["packet_hash"] == expected["packet_hash"]
    assert probe.payload["refs"] == expected["packet"]["refs"]
    assert probe.payload["citation_warnings"] == {
        "unknown_keys": ["[cap:absent]"], "cited_items": ["a"], "lines_with_numbers_but_no_key": [2]}
    assert "fixture-key" not in json.dumps(probe.payload)
    metered = usage_meter.month_summary(reader.index)["by_feature"]
    assert set(metered) == {"playbook_" + name}
    assert {k: metered["playbook_" + name][k] for k in
            ("calls", "input_tokens", "output_tokens", "cache_create", "cache_read")} == {
                "calls": 1, "input_tokens": 321, "output_tokens": 45, "cache_create": 12, "cache_read": 34}
    assert conn.execute("SELECT count(*) FROM writing_drafts").fetchone()[0] == 0


@pytest.mark.parametrize("invalid", [False, True])
def test_no_usable_key_refuses_without_model_or_library_access(route, monkeypatch, invalid):
    reader, _, _, model = route
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: "fixture-key" if invalid else "")
    monkeypatch.setattr(server, "_read_settings", lambda: {"anthropic_key_invalid": invalid})
    monkeypatch.setattr(reader, "request", Mock(side_effect=AssertionError("no library read")))
    probe = post({"playbook": "outlier-posts", "arguments": {"author": "fixture"}})
    assert probe.payload["ok"] is False
    assert probe.payload["error"]["details"]["reason"] == "anthropic_key_required"
    model.assert_not_called()
    reader.request.assert_not_called()


@pytest.mark.parametrize("headers", [
    {"X-Uoink-Token": ""}, {"X-Uoink-Token": "wrong"}, {"Host": "attacker.example"},
])
def test_gate_precedes_body_credentials_library_and_model(route, monkeypatch, headers):
    key = Mock(side_effect=AssertionError("no credential read"))
    monkeypatch.setattr(server, "_saved_anthropic_key", key)
    probe = post(b"invalid JSON", headers=headers)
    assert probe.status == 403 and probe.payload["ok"] is False
    assert probe.rfile.tell() == 0
    key.assert_not_called()
    route[3].assert_not_called()


@pytest.mark.parametrize("body", [
    {}, {"playbook": "unknown", "arguments": {}},
    {"playbook": ["outlier-posts"], "arguments": {}},
    {"playbook": "outlier-posts", "arguments": None},
    {"playbook": "outlier-posts", "arguments": {"author": ""}},
    {"playbook": "outlier-posts", "arguments": {"author": "fixture", "private-field": "secret"}},
    {"playbook": "outlier-posts", "arguments": {"author": "fixture"}, "packet": {"private-field": "secret"}},
])
def test_bad_arguments_refuse_before_credentials_and_storage(route, monkeypatch, body):
    reader = route[0]
    key = Mock(side_effect=AssertionError("no credential read"))
    monkeypatch.setattr(server, "_saved_anthropic_key", key)
    monkeypatch.setattr(reader, "request", Mock(side_effect=AssertionError("no library read")))
    probe = post(body)
    assert probe.payload["error"]["code"] == "invalid_request"
    assert "private-field" not in json.dumps(probe.payload)
    key.assert_not_called()
    reader.request.assert_not_called()
    route[3].assert_not_called()


@pytest.mark.parametrize("body", [
    b'{"playbook":"outlier-posts","arguments":{"author":NaN}}',
    b'{"playbook":"outlier-posts","arguments":{"author":Infinity}}',
    b'{"playbook":"outlier-posts","arguments":{"author":"a","author":"b"}}',
    b'[]', b'{', b'{"padding":"' + b'x' * 65536 + b'"}',
], ids=["nan", "infinity", "duplicate-key", "array", "malformed", "oversized"])
def test_strict_json_and_body_limit_refuse_without_spending(route, body):
    probe = post(body)
    assert probe.status in (400, 413) and probe.payload["ok"] is False
    route[3].assert_not_called()


@pytest.mark.parametrize("code", ["resource_not_found", "deadline_exceeded", "rate_limited"])
def test_reader_refusals_preserve_standard_envelope(route, monkeypatch, code):
    error = library_resources.ResourceError(code)
    monkeypatch.setattr(research_playbooks, "get_playbook_input", Mock(side_effect=error))
    probe = post({"playbook": "outlier-posts", "arguments": {"author": "fixture"}})
    assert probe.payload == error.envelope()
    route[3].assert_not_called()


@pytest.mark.parametrize("stage", ["packet", "model", "citations"])
def test_unexpected_errors_use_standard_envelope_without_private_text(route, monkeypatch, caplog, stage):
    failure = ValueError("private-source-text fixture-key")
    if stage == "packet":
        monkeypatch.setattr(research_playbooks, "_refresh", Mock(side_effect=failure))
    elif stage == "model":
        route[3].side_effect = failure
    else:
        monkeypatch.setattr(research_playbooks, "check_citations", Mock(side_effect=failure))
    probe = post({"playbook": "outlier-posts", "arguments": {"author": "fixture"}})
    assert probe.payload == library_resources.ResourceError("internal_error").envelope()
    assert "private-source-text" not in caplog.text and "fixture-key" not in caplog.text
    assert route[3].call_count == (0 if stage == "packet" else 1)


@pytest.mark.parametrize("status", [401, 429, 500, None])
def test_provider_failure_is_sanitized_and_never_retried(route, caplog, status):
    route[3].side_effect = server.AnthropicAPIError(status, "private-source-text fixture-key")
    probe = post({"playbook": "outlier-posts", "arguments": {"author": "fixture"}})
    assert probe.payload["ok"] is False
    assert probe.payload["error"]["code"] == "anthropic_error"
    assert probe.payload["error"]["details"] == {"status": status}
    assert probe.payload["error"]["retryable"] is (status != 401)
    assert route[3].call_count == 1
    assert server._mark_anthropic_key_invalid.call_count == (1 if status == 401 else 0)
    visible = json.dumps(probe.payload) + caplog.text
    assert "fixture-key" not in visible and "private-source-text" not in visible


def test_empty_provider_response_is_metered_but_returns_no_draft(route):
    route[3].side_effect = None
    route[3].return_value = {"content": [], "usage": {"input_tokens": 321, "output_tokens": 0}}
    probe = post({"playbook": "outlier-posts", "arguments": {"author": "fixture"}})
    assert probe.payload["ok"] is False
    assert probe.payload["error"]["code"] == "anthropic_error"
    assert "body" not in probe.payload
    route[3].assert_called_once()
    metered = usage_meter.month_summary(route[0].index)["by_feature"]["playbook_outlier-posts"]
    assert (metered["calls"], metered["input_tokens"], metered["output_tokens"]) == (1, 321, 0)
    assert route[2].execute("SELECT count(*) FROM writing_drafts").fetchone()[0] == 0


@pytest.mark.parametrize("name,arguments", CASES)
def test_serialization_failure_is_sanitized_on_all_transports(
        route, mcp_adapter, monkeypatch, caplog, name, arguments):
    import uoink_mcp_tools
    from mcp.shared.exceptions import McpError
    from tests.test_library_adapters import mcp_call, post as tool_post
    from tests.test_phase4_stdio import _playbook_prompt, _playbook_tool

    refresh = research_playbooks._refresh

    def invalid_packet(body):
        # Inject corruption after the core's numeric sanitization. This must
        # still exercise json.dumps(allow_nan=False), even with safe medians.
        body["items"][0]["unexpected_private_field"] = float("inf")
        return refresh(body)

    monkeypatch.setattr(research_playbooks, "_refresh", invalid_packet)
    payload = {"playbook": name, "arguments": arguments}
    expected = library_resources.ResourceError("internal_error").envelope()
    probe = post(payload)
    assert probe.status == 200 and probe.payload == expected
    assert uoink_mcp_tools.call_tool("get_playbook_input", payload) == expected
    direct = tool_post("/tools/get_playbook_input", payload)
    assert direct.status == 200 and direct.payload == expected
    http = mcp_call("get_playbook_input", payload)
    assert http.status == 200 and http.payload["result"]["isError"] is True
    assert http.payload["result"]["structuredContent"] == expected
    tool = _playbook_tool(mcp_adapter, payload)
    assert tool.isError is True and json.loads(tool.content[0].text) == expected
    with pytest.raises(McpError) as exc:
        _playbook_prompt(mcp_adapter, name, arguments)
    assert exc.value.error.code == -32603 and exc.value.error.data == expected
    assert "unexpected_private_field" not in caplog.text
    assert route[0].guard._active == 0
    route[3].assert_not_called()


def test_deadline_after_packet_rendering_refuses_before_spending(route, monkeypatch):
    error = library_resources.ResourceError("deadline_exceeded")
    monkeypatch.setattr(route[0], "assert_within_deadline", Mock(side_effect=error))
    probe = post({"playbook": "outlier-posts", "arguments": {"author": "fixture"}})
    assert probe.payload == error.envelope()
    route[3].assert_not_called()


@pytest.mark.parametrize("name,arguments", CASES)
def test_writing_draft_saves_playbook_kind_with_null_source_despite_warnings(route, name, arguments):
    run = post({"playbook": name, "arguments": arguments}).payload
    assert run["citation_warnings"]["unknown_keys"]
    saved = post({"kind": "playbook:" + name, "yoink_id": None, "body": run["body"]}, path="/writing/draft")
    assert saved.status == 200 and saved.payload["ok"] is True
    draft = route[0].index.get_writing_draft(saved.payload["id"])
    assert draft["kind"] == "playbook:" + name and draft["yoink_id"] is None
    assert draft["body"] == run["body"]
    assert route[3].call_count == 1


def test_large_transcript_http_run_uses_core_chapter_caps(route):
    reader, seed, _, model = route
    for n in range(8):
        seed("chapter-" + str(n), clips=8, sidecar={"chapters": [
            {"title": "<>&`" * 50, "start": k * 10} for k in range(150)]})
    args = {"video_ids": ",".join("chapter-" + str(n) for n in range(8))}
    expected = research_playbooks.get_playbook_input(reader, "transcript-intel", args)
    probe = post({"playbook": "transcript-intel", "arguments": args})
    assert probe.payload["ok"] is True
    assert model.call_args.kwargs["user"] == library_resources.render_document(expected["packet"])
    assert expected["packet"]["coverage"]["budget_drops"]["chapters"] > 0


def test_extreme_metric_baseline_still_generates(route):
    for vid in ("a", "b", "c", "d"):
        route[1](vid, views=1e308)
    probe = post({"playbook": "outlier-posts", "arguments": {"author": "fixture"}})
    assert probe.payload["ok"] is True and route[3].call_count == 1


@pytest.mark.parametrize("name", ["outlier-posts", "creator-teardown"])
def test_extreme_metric_packet_succeeds_on_all_transports(route, mcp_adapter, name):
    import uoink_mcp_tools
    from tests.test_library_adapters import mcp_call, post as tool_post
    from tests.test_phase4_stdio import _playbook_prompt, _playbook_tool, _unfence

    for vid in ("a", "b", "c", "d"):
        route[1](vid, views=1e308)
    args = {"author": "fixture"}
    payload = {"playbook": name, "arguments": args}
    result = research_playbooks.get_playbook_input(route[0], name, args)
    assert result["ok"] is True
    assert result["packet"]["baselines"][0]["median"] is None
    json.dumps(result, allow_nan=False)
    assert uoink_mcp_tools.call_tool("get_playbook_input", payload) == result
    direct = tool_post("/tools/get_playbook_input", payload)
    assert direct.status == 200 and direct.payload == {"ok": True, "result": result}
    http = mcp_call("get_playbook_input", payload)
    assert http.status == 200 and http.payload["result"]["isError"] is False
    assert http.payload["result"]["structuredContent"] == result
    tool = _playbook_tool(mcp_adapter, payload)
    assert tool.isError is False and _unfence(tool.content[0].text) == result
    prompt = _playbook_prompt(mcp_adapter, name, args)
    assert _unfence(prompt.messages[1].content.text) == result["packet"]
    route[3].assert_not_called()
    run = post(payload)
    assert run.status == 200 and run.payload["ok"] is True
    assert run.payload["packet_hash"] == result["packet_hash"]
    route[3].assert_called_once()
    assert route[0].guard._active == 0

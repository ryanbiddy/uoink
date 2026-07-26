"""The HTTP MCP transport must execute each advertised input schema."""
from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402
import uoink_mcp_tools  # noqa: E402


class _FakeHandler:
    _handle_mcp_post = server.Handler._handle_mcp_post
    _mcp_tool_call_result = server.Handler._mcp_tool_call_result
    _send_mcp_error = server.Handler._send_mcp_error
    _send_mcp_result = server.Handler._send_mcp_result

    def _send_json(self, status, payload):
        self.response = (status, payload)
        return self.response


def _fake_tools():
    calls = []

    def call_tool(name, arguments):
        calls.append((name, arguments))
        return {"ok": True, "called": name}

    module = types.SimpleNamespace(
        TOOL_REGISTRY={
            "uoink_page": uoink_mcp_tools.TOOL_REGISTRY["uoink_page"],
        },
        call_tool=call_tool,
    )
    return module, calls


def test_registry_uses_only_executable_schema_keywords():
    keywords = set()

    def collect(schema):
        if not isinstance(schema, dict):
            return
        keywords.update(schema)
        for child in (schema.get("properties") or {}).values():
            collect(child)
        collect(schema.get("items"))

    for spec in uoink_mcp_tools.TOOL_REGISTRY.values():
        collect(spec.input_schema)

    assert keywords <= {
        "additionalProperties",
        "default",
        "description",
        "enum",
        "items",
        "maxItems",
        "maxLength",
        "maximum",
        "minimum",
        "properties",
        "required",
        "type",
    }


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        (
            {
                "url": "https://example.com",
                "include_screenshot": "false",
            },
            "include_screenshot must be a boolean",
        ),
        (
            {
                "url": "https://example.com",
                "follow_links_depth": True,
            },
            "follow_links_depth must be an integer",
        ),
        (
            {"url": "https://example.com", "surprise": "field"},
            "unexpected field: surprise",
        ),
        ({}, "missing required field: url"),
    ],
)
def test_http_mcp_rejects_schema_errors_before_dispatch(
    monkeypatch, arguments, error
):
    tools, calls = _fake_tools()
    monkeypatch.setattr(server, "_mcp_tools_module", lambda: tools)
    handler = _FakeHandler()

    response = handler._handle_mcp_post(
        "/mcp/v1",
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "uoink_page",
                "arguments": arguments,
            },
        },
    )

    assert response == (
        200,
        {
            "jsonrpc": "2.0",
            "id": 7,
            "error": {"code": -32602, "message": error},
        },
    )
    assert calls == []


def test_http_mcp_dispatches_schema_valid_arguments(monkeypatch):
    tools, calls = _fake_tools()
    monkeypatch.setattr(server, "_mcp_tools_module", lambda: tools)
    handler = _FakeHandler()
    arguments = {
        "url": "https://example.com",
        "include_screenshot": False,
        "follow_links_depth": 0,
    }

    response = handler._handle_mcp_post(
        "/mcp/v1",
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "uoink_page",
                "arguments": arguments,
            },
        },
    )

    assert response[0] == 200
    assert response[1]["result"]["isError"] is False
    assert response[1]["result"]["structuredContent"] == {
        "ok": True,
        "called": "uoink_page",
    }
    assert calls == [("uoink_page", arguments)]

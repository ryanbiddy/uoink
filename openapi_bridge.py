"""OpenAPI 3.1 bridge for the Uoink helper (V3.3-SOURCE-EXPANSION-SPEC.md).

Turns the MCP TOOL_REGISTRY into an OpenAPI spec so any HTTP-capable AI that
can't speak MCP (Gemini, Grok, Perplexity, custom agents) can still call the
same tools over plain HTTP. The transport is a thin wrapper around
uoink_mcp_tools.call_tool, so MCP and HTTP share one dispatch path, one rate
limiter, and one auth gate.

Pure data assembly. server.py owns the routes (GET /openapi/v1/spec.json,
GET /.well-known/uoink-mcp.json, POST /tools/<name>).
"""
from __future__ import annotations

import re
from typing import Any

OPENAPI_VERSION = "3.1.0"

# Defensive strip for any leading internal version/sprint tag that slips into a
# tool description (e.g. "v3.1 podcast: ", "v2.5 P3 your-channel mode: ").
# Tool descriptions get cleaned at the source in uoink_mcp_tools.py, but this
# guard makes sure a stray prefix never reaches the public OpenAPI spec summary
# when a future tool is added with the old habit.
_VERSION_TAG_RE = re.compile(r"^v\d+\.\d+(?:\.\d+)?\b[^:]*:\s*")

# Tools that return a job_id and run asynchronously -- OpenAPI clients should
# poll get_job_status rather than expect a synchronous result. Surfaced in the
# operation description so a generated client knows to poll.
_ASYNC_TOOLS = {"uoink_playlist"}

_RESULT_SCHEMA = {
    "type": "object",
    "description": ("Uniform envelope. `ok` is false for tool or validation "
                    "errors (HTTP stays 200); `result` carries the tool's "
                    "payload on success."),
    "properties": {
        "ok": {"type": "boolean"},
        "result": {"description": "Tool payload on success (shape varies per tool)."},
        "error": {"type": "string", "description": "Present when ok is false."},
    },
    "required": ["ok"],
}


def _summary(description: str) -> str:
    """First sentence of the tool description, capped, for the operation
    summary. Strips any leading internal version/sprint tag defensively."""
    text = _VERSION_TAG_RE.sub("", (description or "").strip())
    if text:
        text = text[0].upper() + text[1:]
    head = text.split(". ", 1)[0].rstrip(".")
    return (head[:117] + "...") if len(head) > 120 else head


def build_spec(base_url: str, *, tool_registry: dict, version: str) -> dict:
    """Walk the registry into an OpenAPI 3.1 document. Each tool becomes a
    POST /tools/<name> operation whose requestBody schema is the tool's
    MCP input_schema (JSONSchema 3.1-compatible, so it maps 1:1)."""
    paths: dict[str, Any] = {}
    for name in sorted(tool_registry):
        spec = tool_registry[name]
        description = spec.description or ""
        if name in _ASYNC_TOOLS:
            description = (description.rstrip(".")
                           + ". Asynchronous: returns a job_id; poll "
                             "get_job_status for completion.")
        paths[f"/tools/{name}"] = {
            "post": {
                "operationId": name,
                "summary": _summary(spec.description),
                "description": description,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": spec.input_schema or {"type": "object"},
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Tool result envelope.",
                        "content": {"application/json": {"schema": _RESULT_SCHEMA}},
                    },
                    "401": {"description": "Missing or invalid X-Uoink-Token."},
                    "404": {"description": "Unknown tool name."},
                },
                "security": [{"UoinkToken": []}],
            }
        }
    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "Uoink local helper",
            "version": version,
            "description": (
                "The same tools the Uoink MCP server exposes, over plain HTTP, "
                "so any OpenAPI-capable agent can call your local corpus. "
                "Local-first: the helper runs on your machine and requests "
                "never leave it. Authenticate with the X-Uoink-Token header "
                "(the helper prints it; the dashboard copies it)."
            ),
        },
        "servers": [{"url": base_url}],
        "components": {
            "securitySchemes": {
                "UoinkToken": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Uoink-Token",
                }
            }
        },
        "security": [{"UoinkToken": []}],
        "paths": paths,
    }


def build_well_known(base_url: str, *, version: str, tool_count: int) -> dict:
    """Discovery doc at /.well-known/uoink-mcp.json so an agent that lands on
    the host can find both the MCP endpoint and the OpenAPI spec."""
    return {
        "name": "Uoink",
        "version": version,
        "description": ("Local video, podcast, and text corpus plus agent "
                        "tools. Runs on your machine, no cloud."),
        "local_first": True,
        "tool_count": tool_count,
        "mcp_endpoint": f"{base_url}/mcp/v1",
        "openapi_spec": f"{base_url}/openapi/v1/spec.json",
        "tools_endpoint_template": f"{base_url}/tools/{{tool_name}}",
        "auth": {"type": "apiKey", "header": "X-Uoink-Token"},
    }

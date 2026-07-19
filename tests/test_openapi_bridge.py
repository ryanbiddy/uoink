"""Tests for the OpenAPI bridge (V3.3-SOURCE-EXPANSION-SPEC.md).

- build_spec against the real tool registry (proves the whole registry
  maps to a valid OpenAPI 3.1 doc).
- build_well_known shape.
- Live HTTP smoke for GET /openapi/v1/spec.json, GET /.well-known/uoink-mcp.json,
  and POST /tools/<name> with server._mcp_tools_module monkeypatched to a fake
  one-tool module (deterministic dispatch, no real tool side effects).

Run: python tests/test_openapi_bridge.py
"""
from __future__ import annotations

import json
import threading
import types
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import openapi_bridge as ob  # noqa: E402

PORT = 5193
BASE = f"http://127.0.0.1:{PORT}"


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


class _FakeSpec:
    def __init__(self, name, description, input_schema):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.rate_limiter = None

        def _handler(args):
            return {"echoed": args}
        self.handler = _handler


def test_build_spec_real_registry():
    import uoink_mcp_tools as m
    spec = ob.build_spec("http://127.0.0.1:5179",
                         tool_registry=m.TOOL_REGISTRY, version="3.2.1")
    _assert(spec["openapi"] == "3.1.0", "openapi version wrong")
    _assert(len(spec["paths"]) == len(m.TOOL_REGISTRY),
            f"path count {len(spec['paths'])} != registry {len(m.TOOL_REGISTRY)}")
    # spot-check a known tool
    op = spec["paths"]["/tools/uoink_video"]["post"]
    _assert(op["operationId"] == "uoink_video", "operationId wrong")
    _assert("requestBody" in op and "application/json" in op["requestBody"]["content"],
            "requestBody missing")
    _assert(op["security"] == [{"UoinkToken": []}], "security missing")
    _assert({"200", "400", "403", "404"} <= set(op["responses"]),
            "responses missing")
    _assert("401" not in op["responses"], "spec contradicts the HTTP 403 auth gate")
    # input_schema passed through verbatim
    schema = op["requestBody"]["content"]["application/json"]["schema"]
    _assert(schema is m.TOOL_REGISTRY["uoink_video"].input_schema,
            "input_schema not passed through")
    health_schema = m.TOOL_REGISTRY["get_uoink_health"].input_schema
    _assert(ob.validate_arguments({}, health_schema)
            == "missing required field: slug",
            "real health contract accepted a request without slug")
    _assert(spec["components"]["securitySchemes"]["UoinkToken"]["name"] == "X-Uoink-Token",
            "security scheme header wrong")
    # the whole thing must be JSON-serializable
    json.dumps(spec)
    print(f"ok  build_spec: {len(spec['paths'])} tool paths, valid OpenAPI 3.1, JSON-serializable")


def test_build_well_known():
    wk = ob.build_well_known("http://127.0.0.1:5179", version="3.2.1", tool_count=63)
    _assert(wk["openapi_spec"].endswith("/openapi/v1/spec.json"), "spec url wrong")
    _assert(wk["mcp_endpoint"].endswith("/mcp/v1"), "mcp url wrong")
    _assert(wk["tool_count"] == 63 and wk["local_first"] is True, "wk fields wrong")
    _assert(wk["auth"]["header"] == "X-Uoink-Token", "wk auth header wrong")
    print("ok  build_well_known: spec/mcp/auth fields")


def test_validate_arguments():
    schema = {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "maxLength": 8},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            "tags": {"type": "array", "items": {"type": "string"},
                     "maxItems": 2},
        },
        "required": ["slug"],
        "additionalProperties": False,
    }
    _assert(ob.validate_arguments({}, schema) == "missing required field: slug",
            "required field was not enforced")
    _assert(ob.validate_arguments({"slug": "ok", "extra": 1}, schema)
            == "unexpected field: extra", "closed object was not enforced")
    _assert(ob.validate_arguments({"slug": "ok", "limit": True}, schema)
            == "limit must be an integer", "boolean passed as an integer")
    _assert(ob.validate_arguments({"slug": "ok", "limit": 11}, schema)
            == "limit must be at most 10", "numeric bound was not enforced")
    _assert(ob.validate_arguments({"slug": "ok", "tags": ["x", 2]}, schema)
            == "tags[1] must be a string", "array item type was not enforced")
    _assert(ob.validate_arguments({"slug": "ok", "limit": 7}, schema) is None,
            "valid arguments were rejected")
    print("ok  validate_arguments: required/closed/type/bounds/array contracts")


def test_http_bridge():
    import server  # noqa: E402

    fake = types.SimpleNamespace()
    fake.calls = []
    fake.TOOL_REGISTRY = {
        "echo": _FakeSpec("echo", "Echo the arguments back. Test tool.",
                          {"type": "object",
                           "properties": {"x": {"type": "integer"}},
                           "required": ["x"],
                           "additionalProperties": False}),
    }
    def _call_tool(name, args=None):
        spec = fake.TOOL_REGISTRY.get(name)
        if not spec:
            return {"ok": False, "error": "tool not found"}
        fake.calls.append((name, args))
        return spec.handler(args or {})
    fake.call_tool = _call_tool

    server._mcp_tools_module = lambda: fake  # type: ignore

    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        # spec is public
        with urllib.request.urlopen(f"{BASE}/openapi/v1/spec.json", timeout=5) as r:
            spec = json.loads(r.read().decode())
        _assert(r.status == 200 and "/tools/echo" in spec["paths"], "spec route broken")

        # well-known is public
        with urllib.request.urlopen(f"{BASE}/.well-known/uoink-mcp.json", timeout=5) as r:
            wk = json.loads(r.read().decode())
        _assert(r.status == 200 and wk["tool_count"] == 1, "well-known route broken")

        # POST /tools/echo without token -> 403
        req = urllib.request.Request(f"{BASE}/tools/echo", data=b"{}",
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("expected 403 without token")
        except urllib.error.HTTPError as e:
            _assert(e.code == 403, f"expected 403, got {e.code}")

        # Published required fields are enforced before the tool is called.
        req = urllib.request.Request(
            f"{BASE}/tools/echo", data=b"{}",
            headers={"Content-Type": "application/json",
                     "X-Uoink-Token": server.TOKEN},
            method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("expected 400 for missing required field")
        except urllib.error.HTTPError as e:
            payload = json.loads(e.read().decode())
            _assert(e.code == 400, f"expected 400, got {e.code}")
            _assert(payload == {"ok": False,
                                "error": "missing required field: x"},
                    f"validation envelope wrong: {payload}")
        _assert(fake.calls == [], "invalid request reached the tool handler")

        # POST /tools/echo with token -> 200 envelope
        req = urllib.request.Request(
            f"{BASE}/tools/echo", data=json.dumps({"x": 7}).encode(),
            headers={"Content-Type": "application/json", "X-Uoink-Token": server.TOKEN},
            method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read().decode())
        _assert(payload == {"ok": True, "result": {"echoed": {"x": 7}}},
                f"echo envelope wrong: {payload}")

        # unknown tool -> 404
        req = urllib.request.Request(
            f"{BASE}/tools/nope", data=b"{}",
            headers={"Content-Type": "application/json", "X-Uoink-Token": server.TOKEN},
            method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("expected 404 for unknown tool")
        except urllib.error.HTTPError as e:
            _assert(e.code == 404, f"expected 404, got {e.code}")

        print("ok  HTTP bridge: public spec + well-known, /tools/<name> 403/200/404")
    finally:
        httpd.shutdown()


def test_no_version_tags_in_catalog():
    """Regression guard (Stage 4 M-B): no tool description or generated spec
    summary may start with an internal version/sprint tag like 'v3.1 podcast:'."""
    import re
    import uoink_mcp_tools as m
    tag = re.compile(r"^v\d+\.\d+")
    desc_leaks = [n for n, s in m.TOOL_REGISTRY.items()
                  if tag.match((s.description or "").strip())]
    _assert(not desc_leaks, f"tool descriptions still start with a version tag: {desc_leaks}")
    spec = ob.build_spec("http://x", tool_registry=m.TOOL_REGISTRY, version="3.2.1")
    spec_leaks = [p for p, o in spec["paths"].items()
                  if tag.match(o["post"]["summary"].strip())
                  or tag.match(o["post"]["description"].strip())]
    _assert(not spec_leaks, f"spec ops still leak a version tag: {spec_leaks}")
    print("ok  no version/sprint tags in any tool description or spec op")


def main():
    test_build_spec_real_registry()
    test_build_well_known()
    test_validate_arguments()
    test_http_bridge()
    test_no_version_tags_in_catalog()
    print("\nALL OPENAPI BRIDGE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

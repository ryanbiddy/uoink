"""Guard test for Fix 5 -- assemble_workspace must stay reachable for
programmatic/agent use after the Build tab is removed from the dashboard UI.

Run: python tests/test_assemble_workspace_surface.py
Asserts the MCP tool is registered and the HTTP endpoint handler + route are
present. Pure introspection; no server boot, no network. If a future commit
removes the Build UI, this catches an accidental removal of the backend too.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402
import uoink_mcp_tools as tools  # noqa: E402
import workspaces  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_mcp_tool_registered():
    names = [t["name"] for t in tools.list_tools()]
    _assert("assemble_workspace" in names,
            "assemble_workspace MCP tool must stay registered")
    _assert(callable(getattr(workspaces, "assemble_workspace", None)),
            "workspaces.assemble_workspace must exist")
    print("ok  assemble_workspace: MCP tool registered + module fn present")


def test_http_route_present():
    _assert(hasattr(server.Handler, "_handle_workspace_assemble"),
            "POST /workspace/assemble handler must stay present")
    src = Path(server.__file__).read_text(encoding="utf-8")
    _assert('"/workspace/assemble"' in src,
            "the /workspace/assemble route must stay wired in do_POST")
    print("ok  assemble_workspace: HTTP handler + route still wired")


def main():
    test_mcp_tool_registered()
    test_http_route_present()
    print("\nASSEMBLE_WORKSPACE SURFACE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

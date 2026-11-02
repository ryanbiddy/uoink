"""Fail closed on drift between the registry and shipped stdio inventories.

Uses only the standard library and registry schemas, so both static CI jobs
can run it without installing the MCP SDK or importing the helper.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uoink_mcp_tools as tools  # noqa: E402


def literal_pin(path: str, name: str):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    assert len(nodes) == 1, f"{path}: missing or duplicate {name}"
    return ast.literal_eval(nodes[0].value)


def check() -> None:
    names = tools.stdio_tool_names()
    assert len(names) == len(set(names)) == len(tools.TOOL_REGISTRY) == 92
    assert names[:35] == tools.CORE_STDIO_TOOLS
    assert tools.stdio_tool_names("core") == tools.CORE_STDIO_TOOLS
    doc = (ROOT / "docs/v2-mcp.md").read_text(encoding="utf-8")
    headings = re.findall(r"^### ([a-z][a-z_]+)$", doc, re.M)
    assert len(headings) == len(names) and set(headings) == set(names), "tool reference drift"
    manifest = json.loads((ROOT / ".mcpb/manifest.json").read_text(encoding="utf-8"))
    assert [t["name"] for t in manifest["tools"]] == list(names), "MCPB inventory/order drift"
    assert all(t["description"] == tools.TOOL_REGISTRY[t["name"]].description
               for t in manifest["tools"]), "MCPB description drift"
    assert literal_pin("tests/test_c01_mcp_stdio.py", "CANONICAL_STDIO_TOOLS") == set(names)
    assert literal_pin("tests/test_c01_mcp_stdio.py", "CORE_STDIO_TOOLS") == names[:35]
    assert literal_pin("scripts/install_receipt/p4_common.py", "EXPECTED_STDIO_TOOLS") == names
    hints = {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
    for name, spec in tools.TOOL_REGISTRY.items():
        assert spec.name == name and spec.title and spec.title.strip(), name
        assert set(spec.annotations or {}) == hints, name
        assert all(type(v) is bool for v in spec.annotations.values()), name
    for path in ("README.md", "CHANGELOG.md"):
        text = (ROOT / path).read_text(encoding="utf-8")
        pattern = r"MCP server[^\n]*?\b(\d+)\s+tools\b"
        if path == "CHANGELOG.md":
            # History is immutable. Unreleased states the count when it
            # changes; otherwise the current release's statement must hold.
            text = text.split("## [Unreleased]", 1)[1]
            releases = list(re.finditer(r"^## \[", text, re.M))
            unreleased = text[:releases[0].start()] if releases else text
            if re.search(pattern, unreleased, re.I):
                text = unreleased
            elif len(releases) > 1:
                text = text[:releases[1].start()]
        counts = [int(n) for n in re.findall(pattern, text, re.I)]
        assert counts and all(n == len(names) for n in counts), (path, counts)
    print(f"MCP inventory OK: full={len(names)}, core=35; docs, bundle, receipt and metadata agree")


if __name__ == "__main__":
    check()

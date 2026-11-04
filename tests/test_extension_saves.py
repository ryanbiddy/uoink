"""Offline contracts for the browser saves collectors; synthetic DOM/URLs only."""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
# YouTube, X and new Reddit are single-page apps: a content script matched
# only on the saves path would not load when the user navigates there in-app.
# These origins are already in host_permissions, so no new permission prompt;
# content-saves.js stays idle unless detectPage() matches a saves page.
MATCHES = [
    "https://www.youtube.com/*",
    "https://x.com/*",
    "https://twitter.com/*",
    "https://www.reddit.com/*",
    "https://old.reddit.com/*",
]
HOST_PERMISSIONS = [
    "https://www.youtube.com/*",
    "https://m.youtube.com/*",
    "https://x.com/*",
    "https://twitter.com/*",
    "https://*.reddit.com/*",
    "http://127.0.0.1:5179/*",
]


def test_manifest_adds_only_the_saves_content_script():
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    entries = [entry for entry in manifest["content_scripts"]
               if "content-saves.js" in entry["js"]]
    assert entries == [{"matches": MATCHES, "js": ["content-saves.js"], "run_at": "document_idle"}]
    assert manifest["host_permissions"] == HOST_PERMISSIONS
    assert manifest["permissions"] == [
        "alarms", "clipboardWrite", "notifications", "storage", "contextMenus",
        "activeTab", "scripting", "offscreen",
    ]


def test_collector_uses_dom_and_worker_messages_only():
    script = (EXTENSION / "content-saves.js").read_text(encoding="utf-8")
    assert not re.search(r"\.innerHTML\s*(?:\+?=)|\[['\"]innerHTML['\"]\]\s*=", script)
    assert "document.cookie" not in script
    assert not re.search(r"\bfetch\s*\(", script)
    for marker in ("watch_later", "x_bookmarks", "reddit_saved", 'get("list") === "WL"',
                   r"\/i\/bookmarks", r"\/user\/", r"\/saved", "yt-navigate-finish"):
        assert marker in script
    assert "MutationObserver" in script
    assert "event.isTrusted" in script
    assert "globalThis.__UOINK_SAVES_TEST__ === true" in script
    assert 'attachShadow({ mode: "closed" })' in script
    assert "characterData: false" in script
    assert 'navigation.addEventListener("navigatesuccess", syncPage)' in script
    assert "document.hidden" in script
    assert "closedKey" in script
    assert "controls.close.disabled" not in script


def test_worker_routes_and_http_helpers_are_wired():
    background = (EXTENSION / "background.js").read_text(encoding="utf-8")
    extract = (EXTENSION / "lib/extract.js").read_text(encoding="utf-8")
    for message in ("stcStageSaves", "stcImportNext"):
        assert f'msg.type === "{message}"' in background
    for function in ("postStageSaves", "postImportList"):
        assert f"STC.{function}(" in background
        assert re.search(rf"^\s+{function},$", extract, re.MULTILINE)
    assert "const SAVES_STAGE_BODY_MAX = 60000;" in background
    assert "const SAVES_STAGE_CHUNK_MAX = 500;" in background
    assert "JSON.stringify(body).length" in background
    assert "append_to" in background and "append_to" in extract
    assert "msg.items.length < 1" in background
    assert "msg.offset > 100000" in background


def test_store_allowlist_includes_saves_script():
    tree = ast.parse((ROOT / "scripts/build_cws.py").read_text(encoding="utf-8"))
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "ALLOWLIST"
                              for target in node.targets))
    # Inspect the literal without importing the builder or running packaging.
    literal = assignment.value.args[0].func.value.value
    assert "content-saves.js" in literal.split()


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is unavailable")
@pytest.mark.parametrize("group", ["parsers", "collectors", "scroll", "requests", "background", "http"])
def test_saves_node_contracts(group):
    result = subprocess.run(
        [shutil.which("node"), str(ROOT / "tests/js/extension_saves_test.mjs"), group],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {group}" in result.stdout

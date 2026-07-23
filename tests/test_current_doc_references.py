from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def test_readme_local_images_resolve() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing: list[str] = []
    for target in LOCAL_IMAGE.findall(readme):
        if "://" in target or target.startswith("data:"):
            continue
        if not (ROOT / target).is_file():
            missing.append(target)

    assert missing == [], f"README references missing local images: {missing}"


def test_current_install_docs_do_not_name_retired_internal_files() -> None:
    mac = (ROOT / "docs" / "mac-install.md").read_text(encoding="utf-8")
    bundle = (ROOT / "docs" / "mcpb-bundle.md").read_text(encoding="utf-8")

    assert "RB-4-mac-plan.md" not in mac
    assert "[MAC-BUILD-PLAN.md](MAC-BUILD-PLAN.md)" in mac
    assert "handoff/DISTRIBUTION-CHECKLIST-2026-07-07.md" not in bundle
    assert "does not ship one today" in bundle


def test_mcpb_guide_uses_inbox_windows_powershell() -> None:
    bundle = (ROOT / "docs" / "mcpb-bundle.md").read_text(encoding="utf-8")
    surface_map = (
        ROOT / "docs" / "surface-maps" / "mcpb-bundle.md"
    ).read_text(encoding="utf-8")
    command = (
        "powershell -NoProfile -ExecutionPolicy Bypass "
        "-File .\\scripts\\build-mcpb.ps1"
    )

    for current_doc in (bundle, surface_map):
        assert re.search(r"\bpwsh\b", current_doc) is None
    assert bundle.count(command) == 2
    assert surface_map.count(command) == 1


def test_readme_first_run_extension_steps_match_the_splash() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    splash = (ROOT / "assets" / "splash" / "index.html").read_text(
        encoding="utf-8"
    )

    false_automatic_step = (
        "Uoink opens `chrome://extensions/` and shows the extension folder"
    )
    assert false_automatic_step not in readme
    assert "one-time setup splash" in readme
    assert "open your browser's extensions page" in readme
    assert "copy the installed extension path" in readme
    assert 'primary: { text: `Open ${browserName} extensions`' in splash
    assert 'secondary: { text: "Copy path"' in splash


def test_readme_mcp_client_claim_matches_the_compatibility_matrix() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    matrix = (ROOT / "docs" / "v2-mcp.md").read_text(encoding="utf-8")
    server = (ROOT / "server.py").read_text(encoding="utf-8")

    false_tested_claim = (
        "tested with **Claude Desktop, Cursor, Cline, and Continue**"
    )
    assert false_tested_claim not in readme
    assert "tested with **Claude Desktop and Cursor**" in readme
    assert "Cline and Continue are standard-stdio compatibility paths" in readme
    for client in ("Cline", "Continue"):
        assert (
            f"| {client} | Should work, community-reported | stdio | "
            "Standard stdio MCP; not smoke-tested by Ryan. |"
        ) in matrix
    assert "Gemini, Grok, Perplexity, and scripts can drive" not in readme
    assert "Local OpenAPI-capable agents and scripts can drive" in readme
    assert 'HOST = "127.0.0.1"' in server
    assert 'bare == "/openapi/v1/spec.json"' in server
    assert 'bare.startswith("/tools/")' in server
    assert "It works across Claude, Cursor, OpenClaw, Hermes" not in readme
    assert "Clients that support Agent Skills can load the same file" in readme
    assert (ROOT / "skills" / "uoink" / "SKILL.md").is_file()

"""Guard the live Uoink writing modules against accidental excision."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULES = ("writing_studio.py", "voice_dna.py", "scripts.py")
MCP_TOOLS = (
    "generate_script",
    "revise_script",
    "get_shot_list",
    "list_scripts",
    "get_script",
    "write_tweet",
    "write_blog",
    "list_writing_pieces",
    "get_writing_piece",
    "add_style_anchor",
    "list_style_anchors",
    "remove_style_anchor",
)


def test_live_writing_modules_carry_ownership_banner_and_callers() -> None:
    sources = {}
    for name in MODULES:
        source = (ROOT / name).read_text(encoding="utf-8")
        assert "Suite-split ownership: this is a live Uoink product surface." \
            in source
        sources[name] = source
    assert "import voice_dna" in sources["writing_studio.py"]
    assert "import writing_studio as _ws" in sources["scripts.py"]

    server = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "import scripts as p5_scripts" in server
    assert "import voice_dna" in server
    assert "import writing_studio" in server

    mcp = (ROOT / "uoink_mcp_tools.py").read_text(encoding="utf-8")
    assert "import scripts as _scripts_mod" in mcp
    assert "import voice_dna" in mcp
    assert "import writing_studio as _ws" in mcp
    for name in MCP_TOOLS:
        assert f'"{name}": ToolSpec(' in mcp

    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    for name in MODULES:
        copy_lines = [
            line for line in build.splitlines()
            if "Copy-Item" in line and f"'{name}'" in line
        ]
        assert len(copy_lines) == 1
        assert "$StagingDir -Force" in copy_lines[0]

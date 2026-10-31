"""The Claude plugin directory blocks a plugin folder without a README or license."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "agent-kit" / "plugins" / "uoink"


def test_plugin_folder_has_directory_readme():
    text = (PLUGIN / "README.md").read_text(encoding="utf-8")
    # The directory counts words outside code blocks; it requires 40.
    prose = re.sub(r"```.*?```", "", text, flags=re.S)
    assert len(prose.split()) >= 40


def test_plugin_folder_license_matches_repository():
    assert (PLUGIN / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["license"] == "MIT"

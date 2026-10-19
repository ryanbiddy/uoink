"""Build and validate a thin Darwin connector without network access."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from mcpb_manifest import validate


def manifest() -> dict:
    result = json.loads((ROOT / ".mcpb/manifest.json").read_text(encoding="utf-8"))
    result["version"] = (ROOT / "VERSION").read_text().strip()
    result["compatibility"]["platforms"] = ["darwin"]
    result["server"]["mcp_config"] = {
        "command": "/bin/bash", "args": ["${__dirname}/launch-macos.sh", "${user_config.uoink_dir}"]}
    result["user_config"]["uoink_dir"].update(
        title="Uoink app", default="/Applications/Uoink.app",
        description="Select your installed Uoink.app, including the .app name. Install the Mac DMG first. The connector reports a missing install on stderr.")
    result["long_description"] = ("Connect to the Uoink.app installed from the macOS DMG. "
        "Choose its actual location in the Uoink app setting. The connector checks the install, "
        "then runs Contents/Frameworks/Python/bin/python3 -B -s with Contents/Resources/uoink_mcp.py. "
        "Library mirroring is unavailable on macOS. This private test build is not notarized.")
    validate(result, "darwin")
    return result


def check(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        result = json.loads(archive.read("manifest.json").decode("utf-8"))
        validate(result, "darwin")
        for name in ("uoink_mcp.py", "uoink_mcp_tools.py", "uoink_agent_runtime.py", "README.md", "icon.png"):
            if not archive.read(name):
                raise ValueError(f"Empty MCPB payload: {name}")
        if archive.read("launch-macos.sh") != (ROOT / "installer/mac/mcpb-launch.sh").read_bytes():
            raise ValueError("MCPB install launcher differs from reviewed source")
    return result


def build(output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    data = manifest()
    path = output / f"uoink-{data['version']}-macos.mcpb"
    with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(data, indent=2) + "\n")
        for name in ("uoink_mcp.py", "uoink_mcp_tools.py", "uoink_agent_runtime.py"):
            archive.write(ROOT / name, name)
        archive.write(ROOT / "installer/mac/mcpb-launch.sh", "launch-macos.sh")
        archive.write(ROOT / "docs/mac/INSTALL.md", "README.md")
        archive.write(ROOT / "assets/logo-mark-256.png", "icon.png")
    check(path)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    if args.check:
        print(json.dumps({"ok": True, "version": check(args.check)["version"], "platform": "darwin"}))
    elif args.output:
        print(build(args.output))
    else:
        parser.error("choose --output or --check")

"""Offline manifest checks shared by the POSIX and Darwin MCPB builders."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def validate(manifest: dict, platform: str = "win32") -> None:
    if not manifest.get("version"):
        raise ValueError("manifest.version is missing")
    server = manifest["server"]
    config = server["mcp_config"]
    if server["entry_point"] != "uoink_mcp.py":
        raise ValueError("entry_point must be uoink_mcp.py")
    if manifest["compatibility"]["platforms"] != [platform]:
        raise ValueError("Unexpected MCPB platform")
    if platform == "darwin":
        # A system shell can explain a missing install before exec of its Python.
        if config["command"] != "/bin/bash" or config["args"] != [
                "${__dirname}/launch-macos.sh", "${user_config.uoink_dir}"]:
            raise ValueError("Darwin MCPB must use the checked install launcher")
        if manifest["user_config"]["uoink_dir"]["default"] != "/Applications/Uoink.app":
            raise ValueError("Unexpected Darwin install default")
    elif not config["command"].endswith("python/python.exe") or "uoink_mcp.py" not in " ".join(config["args"]):
        raise ValueError("Manifest must invoke installed python.exe and uoink_mcp.py")


if __name__ == "__main__":
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    validate(manifest, sys.argv[2] if len(sys.argv) > 2 else "win32")
    print(manifest["version"])

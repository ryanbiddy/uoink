"""Start the real stdio server using only disposable container state."""
from pathlib import Path
import os
import sys


def main():
    app = Path(__file__).resolve().parents[1]
    root = Path("/tmp/uoink")
    # Explicit isolation must exist before importing any product module.
    paths = {
        "HOME": root / "home",
        "XDG_DATA_HOME": root / "xdg",
        "LOCALAPPDATA": root / "appdata",
        "UOINK_ISOLATED_PROFILE": root / "profile",
        "UOINK_ISOLATED_APP_DIR": root / "app",
        "UOINK_OUTPUT_DIR": root / "profile/output",
    }
    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)
    os.environ.update(
        UOINK_ISOLATED_PORT="5180", UOINK_USAGE_ENDPOINT="",
        PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1", PYTHONUTF8="1",
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
    )
    # Glama introspects the ordinary default toolset. No helper is launched.
    os.environ.pop("UOINK_MCP_TOOLSET", None)
    os.execv(sys.executable, [sys.executable, "-B", str(app / "uoink_mcp.py")])


if __name__ == "__main__":
    main()

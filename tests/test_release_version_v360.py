"""Cross-file release version contract for v3.6.0.

Run: python tests/test_release_version_v330.py
     (or via pytest -- test_release_version() enforces the same contract)
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXPECTED = "3.6.0"


def match(path: str, pattern: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    found = re.search(pattern, text)
    if not found:
        raise AssertionError(f"{path}: version pattern missing")
    return found.group(1)


def collect() -> dict:
    return {
        "VERSION": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "helper/_version.py": match("helper/_version.py", r'__version__\s*=\s*"([^"]+)"'),
        "extension/manifest.json": json.loads(
            (ROOT / "extension" / "manifest.json").read_text(encoding="utf-8")
        )["version"],
        "installer/uoink.iss": match("installer/uoink.iss", r'#define AppVersion\s+"([^"]+)"'),
        "tauri-ui/src-tauri/src/main.rs": match(
            "tauri-ui/src-tauri/src/main.rs", r"Uoink-Setup-([0-9.]+)\.exe"
        ),
        "README.md": match("README.md", r"Uoink-Setup-([0-9.]+)\.exe"),
        # M-2: the .mcpb bundle is a shipped distribution surface too. Enforce
        # it here so it can't drift the way it did into the 3.6.0 cycle (it was
        # left at 3.2.8). build-mcpb.* also derives the bundle version from
        # VERSION at build time; this parity check is the CI backstop.
        ".mcpb/manifest.json": json.loads(
            (ROOT / ".mcpb" / "manifest.json").read_text(encoding="utf-8")
        )["version"],
    }


def test_release_version():
    values = collect()
    bad = {path: value for path, value in values.items() if value != EXPECTED}
    assert not bad, f"release version drift: {bad}"


def main() -> int:
    values = collect()
    bad = {path: value for path, value in values.items() if value != EXPECTED}
    if bad:
        raise AssertionError(f"release version drift: {bad}")
    print(f"ok  {len(values)} release version surfaces agree on {EXPECTED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

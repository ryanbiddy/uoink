"""Cross-file release version contract for v3.2.8.

Run: python tests/test_release_version_v327.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXPECTED = "3.2.8"


def match(path: str, pattern: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    found = re.search(pattern, text)
    if not found:
        raise AssertionError(f"{path}: version pattern missing")
    return found.group(1)


def main() -> int:
    values = {
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
    }
    bad = {path: value for path, value in values.items() if value != EXPECTED}
    if bad:
        raise AssertionError(f"release version drift: {bad}")
    print(f"ok  six release version surfaces agree on {EXPECTED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

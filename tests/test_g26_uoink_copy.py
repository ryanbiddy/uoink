"""G-26 visible-copy sweep for the Uoink rename.

Run: python tests/test_g26_uoink_copy.py
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

EXTENSION_VISIBLE_FILES = [
    "extension/background.js",
    "extension/content.js",
    "extension/lib/mock-api.js",
    "extension/manifest.json",
    "extension/popup.html",
    "extension/setup.html",
    "extension/setup.js",
]

WIRE_OR_COMPAT_PATTERNS = [
    "X-Yoink-Token",
    "X-Yoink-Client",
    "YOINK_",
    "LAST_YOINK_",
    "AUTO_YOINK_",
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _legacy_visible_lines(rel: str) -> list[str]:
    hits: list[str] = []
    for lineno, line in enumerate(_read(rel).splitlines(), 1):
        if not re.search(r"\bYoink\b|YOINK|Start Yoink", line):
            continue
        if any(allowed in line for allowed in WIRE_OR_COMPAT_PATTERNS):
            continue
        hits.append(f"{rel}:{lineno}: {line.strip()}")
    return hits


def test_extension_visible_copy_is_uoink() -> None:
    hits: list[str] = []
    for rel in EXTENSION_VISIBLE_FILES:
        hits.extend(_legacy_visible_lines(rel))
    _assert(not hits, "legacy visible extension copy:\n" + "\n".join(hits))
    print("ok  extension visible copy has no legacy Yoink strings")


def test_installer_start_menu_copy_is_uoink() -> None:
    text = _read("installer/uoink.iss")
    _assert("DefaultGroupName=Uoink" in text, "Start Menu group should be Uoink")
    _assert('Name: "{group}\\Uoink"' in text, "launcher shortcut should be Uoink")
    _assert('Name: "{group}\\Stop Uoink"' in text, "stop shortcut should be Stop Uoink")
    _assert("Start Yoink" not in text and "Yoink Server" not in text,
            "visible Start Menu copy should not say Yoink")
    print("ok  installer Start Menu copy is Uoink")


def main() -> int:
    test_extension_visible_copy_is_uoink()
    test_installer_start_menu_copy_is_uoink()
    print("\nALL G-26 UOINK COPY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

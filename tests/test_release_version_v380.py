"""Cross-file source-build version contract for v3.18.1.

Run: python -m pytest tests/test_release_version_v380.py

The installer, GitHub release and uoink.app go live with v3.18.1. Download pointers are
guarded separately by test_installer_download_accuracy.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = "3.18.1"


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
        # M-2: the .mcpb bundle is a shipped distribution surface too. Enforce
        # it here so it can't drift the way it did into the 3.6.0 cycle (it was
        # left at 3.2.8). build-mcpb.* also derives the bundle version from
        # VERSION at build time; this parity check is the CI backstop.
        ".mcpb/manifest.json": json.loads(
            (ROOT / ".mcpb" / "manifest.json").read_text(encoding="utf-8")
        )["version"],
    }


def test_helper_reads_semver_from_the_version_file(tmp_path, monkeypatch):
    import sys
    import server

    monkeypatch.setitem(sys.modules, "helper._version", None)
    monkeypatch.setattr(server, "HERE", tmp_path)
    stamp = tmp_path / "VERSION"
    for value in ("3.18.1-rc.1", "3.18.1-01a.0+build.007", "3.18.1+07"):
        stamp.write_text(value + "\n", encoding="utf-8")
        assert server._read_version() == value
    for value in ("03.18.1", "3.018.1", "3.18.01", "3.18.1-rc.01", "3.18.1-rc..2", "3.18.1-"):
        stamp.write_text(value, encoding="utf-8")
        with pytest.raises(RuntimeError, match="Invalid VERSION"):
            server._read_version()


def test_release_version():
    values = collect()
    bad = {path: value for path, value in values.items() if value != EXPECTED}
    assert not bad, f"release version drift: {bad}"


@pytest.mark.parametrize("path", ["CHANGELOG.md", "docs/release/RELEASE-NOTES-3.10.0.md"])
def test_release_has_no_orchestrator_placeholders(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert "TODO-ORCH" not in text, f"{path}: replace TODO-ORCH with confirmed client test results before release"


def main() -> int:
    values = collect()
    bad = {path: value for path, value in values.items() if value != EXPECTED}
    if bad:
        raise AssertionError(f"release version drift: {bad}")
    print(f"ok  {len(values)} release version surfaces agree on {EXPECTED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

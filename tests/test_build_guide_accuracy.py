"""Executable accuracy checks for the installer build guide."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "build-installer.md"


def test_every_local_script_command_in_build_guide_exists() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    commands = set(
        re.findall(
            r"(?<!\w)(\.(?:/|\\)[A-Za-z0-9_.\\/-]+\.(?:bat|ps1|sh))",
            text,
        )
    )

    assert commands, "build guide must retain at least one executable command"
    missing = [
        command
        for command in sorted(commands)
        if not (ROOT / command[2:].replace("\\", "/")).is_file()
    ]
    assert missing == [], f"build guide references missing scripts: {missing}"


def test_build_guide_does_not_promise_an_absent_mac_artifact() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / ".github" / "workflows").glob("*.yml")
    )

    if "build-mac.sh" not in workflows:
        retired_claims = (
            "## Quick start (macOS)",
            "./build.sh",
            "automates the macOS packaging process",
            "Uoink-Setup-2.1.0.dmg",
            "The resulting artifact is output",
        )
        present = [claim for claim in retired_claims if claim in text]
        assert present == [], f"unverified macOS build claims remain: {present}"
        assert "There is no working macOS build command" in text
        assert "[mac-install.md](mac-install.md)" in text

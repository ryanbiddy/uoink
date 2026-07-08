"""Guard: every first-party module server.py imports at module top MUST be
listed in installer/uoink.iss [Files] and staged by build.ps1.

This is the recurring "broken on launch" class of bug: a new module gets
imported by server.py but not added to the installer file list, so the
shipped helper crashes with ModuleNotFoundError before it binds the port
(hit by x_extractor in v3.2.6, taste_scoring in v3.3.0, x_article_extractor
in v3.3.x). This test makes that impossible to ship silently.

Run: python tests/test_installer_files_complete.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
ISS = (ROOT / "installer" / "uoink.iss").read_text(encoding="utf-8")
BUILD = (ROOT / "build.ps1").read_text(encoding="utf-8")


def first_party_imports() -> list[str]:
    """Top-level `import X` / `from X import ...` where X.py exists in the repo root."""
    mods = set()
    for m in re.finditer(r"^(?:import|from)\s+([a-z_][a-z0-9_]*)", SERVER, re.M):
        name = m.group(1)
        if (ROOT / f"{name}.py").is_file():
            mods.add(name)
    return sorted(mods)


def test_every_server_import_is_in_installer_and_staging() -> None:
    missing_iss = []
    missing_build = []
    for mod in first_party_imports():
        fn = f"{mod}.py"
        if fn not in ISS:
            missing_iss.append(fn)
        if fn not in BUILD:
            missing_build.append(fn)
    problems = []
    if missing_iss:
        problems.append(f"NOT in installer/uoink.iss [Files]: {missing_iss}")
    if missing_build:
        problems.append(f"NOT staged by build.ps1: {missing_build}")
    if problems:
        raise AssertionError(
            "Modules server.py imports but the installer would ship without "
            "(helper crashes on launch): " + "; ".join(problems)
        )


def main() -> int:
    test_every_server_import_is_in_installer_and_staging()
    print("ok  every server.py first-party import is staged + in installer [Files]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

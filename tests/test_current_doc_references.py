from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def test_readme_local_images_resolve() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing: list[str] = []
    for target in LOCAL_IMAGE.findall(readme):
        if "://" in target or target.startswith("data:"):
            continue
        if not (ROOT / target).is_file():
            missing.append(target)

    assert missing == [], f"README references missing local images: {missing}"


def test_current_install_docs_do_not_name_retired_internal_files() -> None:
    mac = (ROOT / "docs" / "mac-install.md").read_text(encoding="utf-8")
    bundle = (ROOT / "docs" / "mcpb-bundle.md").read_text(encoding="utf-8")

    assert "RB-4-mac-plan.md" not in mac
    assert "[MAC-BUILD-PLAN.md](MAC-BUILD-PLAN.md)" in mac
    assert "handoff/DISTRIBUTION-CHECKLIST-2026-07-07.md" not in bundle
    assert "does not ship one today" in bundle


def test_mcpb_guide_uses_inbox_windows_powershell() -> None:
    bundle = (ROOT / "docs" / "mcpb-bundle.md").read_text(encoding="utf-8")
    command = (
        "powershell -NoProfile -ExecutionPolicy Bypass "
        "-File .\\scripts\\build-mcpb.ps1"
    )

    assert "pwsh scripts\\build-mcpb.ps1" not in bundle
    assert bundle.count(command) == 2

"""Keep the shipped installer link and live checklists tied to reality."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_VERSION = "3.4.0"
PUBLISHED_ASSET = f"Uoink-Setup-{PUBLISHED_VERSION}.exe"


def test_setup_page_points_to_the_verified_published_installer() -> None:
    script = (ROOT / "extension" / "setup.js").read_text(encoding="utf-8")
    html = (ROOT / "extension" / "setup.html").read_text(encoding="utf-8")

    declaration = (
        f'const PUBLISHED_INSTALLER_VERSION = "{PUBLISHED_VERSION}";'
    )
    assert declaration in script
    assert (
        "const installerName = "
        "`Uoink-Setup-${PUBLISHED_INSTALLER_VERSION}.exe`;"
    ) in script
    assert (
        "`https://github.com/ryanbiddy/uoink/releases/download/"
        "v${PUBLISHED_INSTALLER_VERSION}/${installerName}`"
    ) in script
    assert "data-win-only" in html
    assert "Uoink-Setup-3.2.2.exe" not in script + html


def test_current_release_checklists_name_real_controls() -> None:
    current = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "docs" / "build-installer.md",
            ROOT / "docs" / "store" / "SUBMISSION-CHECKLIST.md",
        )
    )
    assert "INSTALLER_PUBLISHED" not in current
    assert "git tag v2.0.0" not in current
    assert "PUBLISHED_INSTALLER_VERSION" in current
    tracked_docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "docs").rglob("*.md")
    )
    assert "INSTALLER_PUBLISHED" not in tracked_docs
    assert "Uoink-Setup-2.1.0.exe" not in tracked_docs


def test_superseded_v2_launch_instructions_are_marked_historical() -> None:
    historical = (
        ROOT / "docs" / "store-listing.md",
        ROOT / "docs" / "v2-smoke-test.md",
    )
    for path in historical:
        opening = path.read_text(encoding="utf-8")[:500].lower()
        assert "status: historical" in opening, path
        assert "do not use" in opening, path

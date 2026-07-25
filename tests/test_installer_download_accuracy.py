"""Keep the shipped installer link and live checklists tied to reality."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _tracked_docs() -> list[Path]:
    """Markdown under docs/ that is actually committed.

    Walking the filesystem instead picks up gitignored local files -- docs/launch/
    is ignored, so a real working checkout has scratch files there that a fresh
    clone does not. That made this guard fail locally while passing in CI, which
    is the worst failure mode for a guard: it trains you to ignore it.

    Fall back to a filesystem walk outside a git checkout, e.g. an unpacked sdist.
    """
    try:
        listing = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", "docs"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return sorted((ROOT / "docs").rglob("*.md"))
    return [ROOT / name for name in listing.split("\0") if name.endswith(".md")]
PUBLISHED_VERSION = "3.7.0"
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


def test_current_install_docs_name_the_published_asset() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    bundle_doc = (ROOT / "docs" / "mcpb-bundle.md").read_text(encoding="utf-8")
    bundle_map = (
        ROOT / "docs" / "surface-maps" / "mcpb-bundle.md"
    ).read_text(encoding="utf-8")

    assert f"Download `{PUBLISHED_ASSET}`" in readme
    # The source build runs ahead of the published installer. Guard the current
    # source version by reading it, so this can't rot into checking a version
    # nobody ships anymore. Skipped when the two have converged (right after a
    # publish), since then the asset legitimately appears in the README.
    source_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if source_version != PUBLISHED_VERSION:
        assert f"Uoink-Setup-{source_version}.exe" not in readme
    assert "Uoink-Setup-3.6.0.exe" not in readme
    assert "dist/uoink-3.3.0.mcpb" not in bundle_doc
    assert "currently 3.3.0" not in bundle_map
    assert "test_release_version_v330.py" not in bundle_map
    assert "tests/test_release_version_v370.py" in bundle_map


def test_manual_setup_is_a_current_source_install_path() -> None:
    manual = (ROOT / "REQUIREMENTS.md").read_text(encoding="utf-8")
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    match = re.search(r"\$YTDLP_VERSION\s*=\s*'([^']+)'", build)

    assert "published v3.7.0 installer" in manual
    assert "python -m pip install -r requirements.txt" in manual
    assert match is not None
    assert f'python -m pip install "yt-dlp=={match.group(1)}"' in manual
    assert "python server.py" in manual
    assert "Until then" not in manual


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
    docs = _tracked_docs()
    assert docs, "no tracked docs found -- the listing is broken, not the docs"
    tracked_docs = "\n".join(
        path.read_text(encoding="utf-8") for path in docs
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

"""Pin the installer-only release-link rewrite.

Development builds keep pointing at the latest public release. Release builds
must stage their own version before Inno packages the extension; otherwise an
immutable installer offers the previous release after publication.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "set_release_installer_link.ps1"


def _powershell() -> str:
    for name in ("pwsh", "powershell", "powershell.exe"):
        executable = shutil.which(name)
        if executable:
            return executable
    pytest.skip("PowerShell is required to execute the Windows release guard")


def _run_guard(setup_script: Path, expected_version: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _powershell(),
            "-NoLogo",
            "-NoProfile",
            "-File",
            os.fspath(SCRIPT),
            "-SetupScript",
            os.fspath(setup_script),
            "-ExpectedVersion",
            expected_version,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_release_guard_rewrites_only_the_staged_version(tmp_path: Path) -> None:
    source = (
        "// keep this comment\n"
        'const PUBLISHED_INSTALLER_VERSION = "3.4.0";\n'
        "const anotherSetting = true;\n"
    )
    setup_script = tmp_path / "setup.js"
    setup_script.write_text(source, encoding="utf-8")

    result = _run_guard(setup_script, "3.7.0")

    assert result.returncode == 0, result.stdout + result.stderr
    expected = source.replace('"3.4.0"', '"3.7.0"')
    assert setup_script.read_text(encoding="utf-8") == expected
    assert not setup_script.read_bytes().startswith(b"\xef\xbb\xbf")


def test_release_guard_fails_closed_on_ambiguous_declarations(
    tmp_path: Path,
) -> None:
    source = (
        'const PUBLISHED_INSTALLER_VERSION = "3.4.0";\n'
        'const PUBLISHED_INSTALLER_VERSION = "3.6.0";\n'
    )
    setup_script = tmp_path / "setup.js"
    setup_script.write_text(source, encoding="utf-8")

    result = _run_guard(setup_script, "3.7.0")

    assert result.returncode != 0
    assert "requires exactly one" in result.stdout + result.stderr
    assert setup_script.read_text(encoding="utf-8") == source


def test_release_mode_is_wired_between_extension_staging_and_inno() -> None:
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "build-installer.md").read_text(encoding="utf-8")

    assert "[switch]$Release" in build
    release_block = re.search(
        r"if \(\$Release\) \{\s+"
        r"\$stagedSetupScript = .*?\s+"
        r"& \$setReleaseInstallerLink .*?\s+\}",
        build,
        flags=re.DOTALL,
    )
    assert release_block is not None
    copy_offset = build.index(
        "Copy-Item (Join-Path $RepoRoot 'extension')"
    )
    rewrite_offset = build.index("& $setReleaseInstallerLink")
    compile_offset = build.index("& $iscc /Q")
    assert copy_offset < rewrite_offset < compile_offset
    assert r".\build.ps1 -Release" in guide

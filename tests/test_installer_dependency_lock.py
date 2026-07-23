from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements-installer-lock.txt"
VERIFY = ROOT / "scripts" / "verify_installer_lock.py"

spec = importlib.util.spec_from_file_location("verify_installer_lock", VERIFY)
assert spec is not None and spec.loader is not None
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def test_installer_lock_is_complete_and_exact() -> None:
    locked = verify.read_lock(LOCK)

    assert len(locked) >= 100
    assert locked["yt-dlp"] == "2026.7.4"
    assert locked["pillow"] == "10.4.0"
    assert locked["mcp"] == "1.27.1"
    assert locked["faster-whisper"] == "1.2.1"
    assert locked["whisperx"] == "3.8.6"
    assert locked["torch"] == "2.8.0"
    assert "tomli" not in locked
    assert "wcwidth" not in locked


def test_installer_lock_matches_the_committed_notice_inventory() -> None:
    locked = verify.read_lock(LOCK)
    notice = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    noticed = {
        verify.canonical_name(line.split("|")[1].strip())
        for line in notice.splitlines()
        if line.startswith("| ") and not line.startswith("| Package ")
    }

    assert noticed == set(locked)


def test_installer_lock_parser_rejects_ranges_and_duplicates(
    tmp_path: Path,
) -> None:
    ranged = tmp_path / "ranged.txt"
    ranged.write_text("example>=1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact name==version pin"):
        verify.read_lock(ranged)

    duplicate = tmp_path / "duplicate.txt"
    duplicate.write_text("Example==1\nexample==1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate package"):
        verify.read_lock(duplicate)


def test_inventory_diff_detects_every_drift_shape() -> None:
    missing, unexpected, changed = verify.inventory_diff(
        {"kept": "1", "missing": "1", "changed": "1"},
        {"kept": "1", "unexpected": "1", "changed": "2"},
    )

    assert missing == ["missing"]
    assert unexpected == ["unexpected"]
    assert changed == ["changed"]


def test_build_uses_and_verifies_the_installer_lock() -> None:
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "uoink.iss").read_text(encoding="utf-8")
    build_doc = (ROOT / "docs" / "build-installer.md").read_text(encoding="utf-8")
    security = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")

    assert "$InstallerLock" in build
    assert "--constraint $InstallerLock" in build
    assert "scripts\\verify_installer_lock.py" in build
    assert "& $embedPython $verifyInstallerLock $InstallerLock" in build
    assert build.index("--constraint $InstallerLock") < build.index(
        "& $embedPython $verifyInstallerLock $InstallerLock"
    )
    assert "requirements-installer-lock.txt" in build
    assert "pip-licenses prettytable tomli wcwidth" in build
    for tool_pin in (
        "$PIP_VERSION",
        "$SETUPTOOLS_VERSION",
        "$WHEEL_VERSION",
        "$PACKAGING_VERSION",
    ):
        assert tool_pin in build
    assert build.count("--no-build-isolation") == 2
    assert build.count("--no-cache-dir") == 3
    assert "$GETPIP_COMMIT  = '5e84c8360eaf92009551b3eec69d734137f31cec'" in build
    assert (
        '"https://raw.githubusercontent.com/pypa/get-pip/'
        '$GETPIP_COMMIT/public/get-pip.py"'
    ) in build
    assert "a341e1a43e38001c551a1508a73ff23636a11970b61d901d9a1cad2a18f57055" in build
    assert "Remove-Item -Recurse -Force $pythonScripts" in build
    assert "'^(?:\\.\\./)+Scripts/'" in build
    assert build.index("Staged smoke OK") < build.index(
        "Final staging cleanup left"
    )
    assert build.index("generate_bitmaps.py") < build.index(
        "Final staging cleanup left"
    )
    assert "Join-Path $StagingDir 'token.txt'" in build
    assert "Final staging cleanup left token.txt" in build
    assert "SOURCE_DATE_EPOCH" in build
    assert "--format=%ct HEAD" in build
    assert "\"$candidate\" -match '^\\d+$'" in build
    assert "$epochText = '946684800'" in build
    assert "LastWriteTimeUtc = $packageTimestampUtc" in build
    assert "Copy-Item (Join-Path $InstallerDir 'upgrade_prep.ps1')" in build
    assert "staging\\upgrade_prep.ps1" in installer
    assert "staging\\installer-assets\\wizard-large-100.bmp" in installer
    assert "SetupIconFile=staging\\uoink.ico" in installer
    assert build.index("Final staging cleanup left") < build.index(
        "Write-Step 'Compiling installer'"
    )
    assert build.index("LastWriteTimeUtc = $packageTimestampUtc") < build.index(
        "Write-Step 'Compiling installer'"
    )
    for current_doc in (build_doc, security):
        assert "transitive graph" in current_doc
        assert "not hash-locked" in current_doc
        assert "build tooling" in current_doc
    assert "version-pinned but not hash-locked yet" not in build_doc
    assert "version-pinned but not hash-locked yet" not in security

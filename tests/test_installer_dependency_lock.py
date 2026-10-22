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
    assert locked["yt-dlp"] == "2026.8.19"
    assert locked["pillow"] == "12.3.0"
    assert locked["mcp"] == "2.3.0"
    assert locked["mcp-types"] == "2.3.0"
    assert locked["httpx2"] == locked["httpcore2"] == "2.10.0"
    assert locked["truststore"] == "0.10.5"
    assert not {"httpx", "httpcore", "httpx-sse", "pydantic-settings", "python-dotenv"} & locked.keys()
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
    assert "--constraint $InstallerConstraints" in build
    assert "$verifyInstallerLock $InstallerLock --write-constraints $InstallerConstraints" in build
    assert "scripts\\verify_installer_lock.py" in build
    assert "& $embedPython $verifyInstallerLock $InstallerLock" in build
    install_at = build.index("--constraint $InstallerConstraints")
    verify_at = build.index("& $embedPython $verifyInstallerLock $InstallerLock", install_at)
    assert build.index("--write-constraints $InstallerConstraints") < install_at < verify_at
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


def test_sdk2_hash_rows_and_version_constraint_export(tmp_path):
    import re
    locked = verify.read_lock(LOCK)
    hashes = dict(re.findall(r"^([\w.-]+)==\S+ --hash=sha256:([0-9a-f]{64})$",
                             LOCK.read_text(), re.MULTILINE))
    assert hashes == {
        "mcp": "dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377",
        "mcp-types": "968efdbdaedfab06adae40d378a34395f1090c5921d4be3c9cde283aaf76d91d",
        "httpx2": "5e3194a432701e1cc6f69a8b1b2fa199ef907013fede8d9a09a2c5b7b8141a18",
        "httpcore2": "7df06cfb34070cae4f7c89be69dc1095eca138e9704ceffb98d25c1912ab6f01",
        "truststore": "9aaaedaefaf06d8b206278cf8b5012bc897f485a874503501e12d776df78951c",
    }
    destination = tmp_path / "constraints.txt"
    assert verify.main([str(LOCK), "--write-constraints", str(destination)]) == 0
    assert verify.read_lock(destination) == locked
    assert "--hash" not in destination.read_text()
    for bad in ("", "f" * 63, "g" * 64, "f" * 65):
        destination.write_text(f"mcp==2.3.0 --hash=sha256:{bad}\n")
        with pytest.raises(ValueError, match="exact name==version pin"):
            verify.read_lock(destination)


def test_sdk2_hash_lock_is_compatible_with_qualification_readers():
    import importlib.util

    locked = verify.read_lock(LOCK)
    for path, reader in (("scripts/mac/qualify_deps.py", "read_pins"),
                         ("scripts/check_runtime_graph.py", "parse_lock")):
        spec = importlib.util.spec_from_file_location("sdk2_lock_reader", ROOT / path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parsed = dict(getattr(module, reader)(LOCK))
        assert {verify.canonical_name(k): v for k, v in parsed.items()} == locked
    portable = verify.read_lock(ROOT / "scripts/mac/portable-tests.txt")
    for name in ("mcp", "mcp-types", "httpx2", "httpcore2", "truststore"):
        assert portable[name] == locked[name]

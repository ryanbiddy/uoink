from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_MODULES = {"uoink_mcp.py", "uoink_mcp_tools.py", "uoink_agent_runtime.py"}


def test_bundle_scripts_stage_the_same_files() -> None:
    posix = (ROOT / "scripts/build-mcpb.sh").read_text(encoding="utf-8")
    powershell = (ROOT / "scripts/build-mcpb.ps1").read_text(encoding="utf-8")
    posix_modules = re.search(r"for f in (.+); do", posix).group(1).split()
    powershell_modules = re.findall(
        r'"([^"]+)"', re.search(r"foreach \(\$f in @\((.+)\)\)", powershell).group(1))
    assert set(posix_modules) == set(powershell_modules) == BUNDLE_MODULES
    assert 'cp "$REPO_ROOT/$f" "$BUILD_DIR/$f"' in posix
    assert '$p = Join-Path $RepoRoot $f' in powershell
    assert 'Copy-Item $p (Join-Path $BuildDir $f)' in powershell
    assert 'cp "$MANIFEST" "$BUILD_DIR/manifest.json"' in posix
    assert '(Join-Path $BuildDir "manifest.json"), $stagedJson' in powershell
    for source, destination in (("$SRC_DIR/README.md", "README.md"),
                                ("$REPO_ROOT/assets/logo-mark-256.png", "icon.png")):
        assert f'cp "{source}" "$BUILD_DIR/{destination}"' in posix
    assert 'Join-Path $SrcDir "README.md"' in powershell
    assert 'Join-Path $RepoRoot "assets\\logo-mark-256.png"' in powershell
    assert 'Copy-Item $bundleReadme (Join-Path $BuildDir "README.md")' in powershell
    assert 'Copy-Item $icon (Join-Path $BuildDir "icon.png")' in powershell


@pytest.mark.skipif(os.name == "nt", reason="POSIX build-script execution")
def test_posix_build_falls_back_to_python_without_mcpb_or_zip(
    tmp_path: Path,
) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.fail("bash is required by the POSIX MCPB build contract")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    commands = {
        "python3": sys.executable,
        **{
            command: shutil.which(command)
            for command in ("cp", "dirname", "mkdir", "rm", "tr")
        },
    }
    for command, target in commands.items():
        assert target is not None, f"required POSIX command is missing: {command}"
        (fake_bin / command).symlink_to(target)

    output_dir = tmp_path / "dist"
    result = subprocess.run(
        [bash, str(ROOT / "scripts" / "build-mcpb.sh"), str(output_dir)],
        cwd=ROOT,
        env={**os.environ, "PATH": str(fake_bin)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "packing with Python stdlib" in result.stdout
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    bundle = output_dir / f"uoink-{version}.mcpb"
    assert bundle.is_file()
    with zipfile.ZipFile(bundle) as archive:
        assert set(archive.namelist()) == {
            "README.md",
            "icon.png",
            "manifest.json",
        } | BUNDLE_MODULES

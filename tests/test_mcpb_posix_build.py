from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


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
            "uoink_mcp.py",
            "uoink_mcp_tools.py",
        }

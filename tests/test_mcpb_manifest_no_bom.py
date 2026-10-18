"""The .mcpb manifest must be written without a UTF-8 BOM.

Windows PowerShell 5.1's ``Set-Content -Encoding utf8`` prepends EF BB BF, and
the official ``mcpb validate`` rejects such a manifest ("Invalid JSON ...
Unexpected token"). Found while qualifying 3.8.1: the 3.8.0 bundle carried a BOM.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_source_manifest_has_no_bom():
    assert not (ROOT / ".mcpb" / "manifest.json").read_bytes().startswith(b"\xef\xbb\xbf")


def test_powershell_packer_writes_staged_manifest_without_bom():
    script = (ROOT / "scripts" / "build-mcpb.ps1").read_text(encoding="utf-8")
    code = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
    manifest_writes = [line for line in code if '"manifest.json"' in line and "BuildDir" in line]
    assert manifest_writes, "packer no longer stages manifest.json"
    for line in manifest_writes:
        assert "Set-Content" not in line and "Out-File" not in line, line
    assert any("UTF8Encoding]::new($false)" in line for line in manifest_writes), manifest_writes

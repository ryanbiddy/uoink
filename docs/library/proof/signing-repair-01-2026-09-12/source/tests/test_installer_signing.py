"""Signing policy at mocked OS boundaries; these do not sign release artifacts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows signing toolchain")
THUMB = "A" * 40


def ps_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    script = tmp_path / "case.ps1"
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        + ". " + ps_quote(ROOT / "scripts/installer_signing.ps1") + "\n"
        + body + "\n", encoding="utf-8"
    )
    return subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
    )


def setup_signer(tmp_path: Path) -> tuple[str, str]:
    folder = tmp_path / "SDK with spaces"
    folder.mkdir()
    tool = folder / "signtool.exe"
    tool.write_bytes(b"NOT EXECUTABLE: configuration-only test fixture")
    payload = tmp_path / "synthetic payload.txt"
    payload.write_bytes(b"synthetic")
    return ps_quote(tool), ps_quote(payload)


def test_inno_command_quotes_paths_and_uses_fixed_callback(tmp_path: Path) -> None:
    tool, _ = setup_signer(tmp_path)
    result = run_ps(tmp_path,
        f"Get-UoinkInnoSignCommand {ps_quote(POWERSHELL)} "
        f"{ps_quote(ROOT / 'scripts/sign_installer.ps1')} '{THUMB}' https://timestamp.example.test/rfc3161 {tool}")
    assert result.returncode == 0, result.stderr
    command = result.stdout.strip()
    assert command.startswith('/Suoinkrelease=$q')
    assert ' -FilePath $f ' in command
    assert ' -SignToolPath $q' in command and command.endswith('$q')
    assert 'SDK with spaces' in command
    assert '-Command' not in command and '/p ' not in command and '/a ' not in command


@pytest.mark.parametrize("endpoint", [
    "http://timestamp.example.test", "https://user:secret@example.test",
    "https://example.test/?token=secret", "https://example.test/#fragment",
    "https://example.test/;exit", "https://example.test/$(exit)",
])
def test_timestamp_configuration_rejects_unsafe_values(tmp_path: Path, endpoint: str) -> None:
    tool, _ = setup_signer(tmp_path)
    result = run_ps(tmp_path,
        f"Assert-UoinkSigningConfiguration '{THUMB}' {ps_quote(endpoint)} {tool}")
    assert result.returncode != 0
    assert "TimestampUrl must be" in result.stderr


@pytest.mark.parametrize("unsafe", ['C:relative/signtool.exe', 'C:/bad&path/signtool.exe', 'C:/bad%path/signtool.exe'])
def test_tool_path_cannot_be_relative_or_command_expansion(tmp_path: Path, unsafe: str) -> None:
    result = run_ps(tmp_path,
        f"Assert-UoinkSigningConfiguration '{THUMB}' https://timestamp.example.test {ps_quote(unsafe)}")
    assert result.returncode != 0


@pytest.mark.parametrize("status,signer,timestamp,expected", [
    ("Valid", THUMB, True, 0),
    ("Valid", "B" * 40, True, 1),
    ("NotTrusted", THUMB, True, 1),
    ("HashMismatch", THUMB, True, 1),
    ("NotSigned", None, False, 1),
    ("Valid", THUMB, False, 1),
])
def test_signature_requires_trust_identity_and_timestamp(
    tmp_path: Path, status: str, signer: str | None, timestamp: bool, expected: int,
) -> None:
    tool, payload = setup_signer(tmp_path)
    signer_ps = "$null" if signer is None else f"[pscustomobject]@{{Thumbprint='{signer}'; Subject='Synthetic publisher'}}"
    time_ps = "[pscustomobject]@{Thumbprint='synthetic timestamp'}" if timestamp else "$null"
    result = run_ps(tmp_path, f"""
function Invoke-UoinkSignTool {{
    param($SignToolPath, $Arguments)
    if (($Arguments -join '|') -notlike 'verify|/pa|/all|/tw|*') {{ throw 'Wrong verification policy' }}
}}
function Get-AuthenticodeSignature {{
    param($LiteralPath, $ErrorAction)
    [pscustomobject]@{{Status='{status}'; SignerCertificate={signer_ps}; TimeStamperCertificate={time_ps}}}
}}
Assert-UoinkSignedFile {payload} '{THUMB}' {tool} | ConvertTo-Json
""")
    assert (result.returncode != 0) == bool(expected), result.stderr
    if not expected:
        receipt = json.loads(result.stdout)
        assert receipt['signature_verified'] is True
        assert receipt['release_ready'] is False
        assert receipt['bytes'] == len(b'synthetic')


@pytest.mark.parametrize("private,expired,eku", [(False, False, True), (True, True, True), (True, False, False)])
def test_certificate_requires_private_key_validity_and_signing_eku(tmp_path: Path, private: bool, expired: bool, eku: bool) -> None:
    result = run_ps(tmp_path, f"""
function Get-Item {{
    param($LiteralPath, $ErrorAction)
    [pscustomobject]@{{HasPrivateKey=${str(private).lower()}; NotBefore=[DateTime]::UtcNow.AddDays(-2);
        NotAfter=[DateTime]::UtcNow.AddDays({-1 if expired else 2});
        EnhancedKeyUsageList=@([pscustomobject]@{{ObjectId=[pscustomobject]@{{Value='{'1.3.6.1.5.5.7.3.3' if eku else '1.2.3'}'}}}})}}
}}
Assert-UoinkSigningCertificate '{THUMB}'
""")
    assert result.returncode != 0


def test_missing_certificate_stops_before_signing(tmp_path: Path) -> None:
    tool, payload = setup_signer(tmp_path)
    result = run_ps(tmp_path, f"""
function Assert-UoinkSigningCertificate {{ throw 'Synthetic missing certificate' }}
function Invoke-UoinkSignTool {{ throw 'SHOULD NOT RUN' }}
Invoke-UoinkSignFile {payload} '{THUMB}' https://timestamp.example.test {tool}
""")
    assert result.returncode != 0
    assert 'Synthetic missing certificate' in result.stderr
    assert 'SHOULD NOT RUN' not in result.stderr


def test_sign_then_verify_has_explicit_algorithms_and_certificate(tmp_path: Path) -> None:
    tool, payload = setup_signer(tmp_path)
    result = run_ps(tmp_path, f"""
function Assert-UoinkSigningCertificate {{ }}
$script:calls = [Collections.Generic.List[object]]::new()
function Invoke-UoinkSignTool {{ param($SignToolPath, $Arguments); $script:calls.Add($Arguments) }}
function Get-AuthenticodeSignature {{
    param($LiteralPath, $ErrorAction)
    [pscustomobject]@{{Status='Valid'; SignerCertificate=[pscustomobject]@{{Thumbprint='{THUMB}'; Subject='Synthetic'}};
        TimeStamperCertificate=[pscustomobject]@{{Thumbprint='synthetic'}}}}
}}
$receipt = Invoke-UoinkSignFile {payload} '{THUMB}' https://timestamp.example.test {tool}
ConvertTo-Json -InputObject @($script:calls.ToArray()) -Depth 4
""")
    assert result.returncode == 0, result.stderr
    calls = json.loads(result.stdout)
    assert calls[0][:-1] == ['sign', '/sha1', THUMB, '/s', 'My', '/fd', 'SHA256', '/tr', 'https://timestamp.example.test', '/td', 'SHA256']
    assert calls[1][:-1] == ['verify', '/pa', '/all', '/tw']


@pytest.mark.parametrize("exit_code", [1, 2])
def test_signtool_errors_and_warnings_are_not_success(tmp_path: Path, exit_code: int) -> None:
    fake = tmp_path / 'fake-tool.ps1'
    fake.write_text(f"$global:LASTEXITCODE = {exit_code}\n", encoding='utf8')
    result = run_ps(tmp_path, f"Invoke-UoinkSignTool {ps_quote(fake)} @('synthetic')")
    assert result.returncode != 0
    assert f'SignTool returned {exit_code}' in result.stderr


@pytest.mark.parametrize("arguments", ["-ReleaseSigned -StageSourceOnly", "-TimestampUrl https://timestamp.example.test"])
def test_build_refuses_invalid_mode_before_staging(tmp_path: Path, arguments: str) -> None:
    result = run_ps(tmp_path, f"& {ps_quote(ROOT / 'build.ps1')} {arguments}")
    assert result.returncode != 0
    assert 'requires a complete installer build' in result.stderr or 'require -ReleaseSigned' in result.stderr


def test_signing_files_parse_and_compiler_uses_fresh_uninstaller_cache(tmp_path: Path) -> None:
    for name in ('build.ps1', 'scripts/installer_signing.ps1', 'scripts/sign_installer.ps1'):
        result = run_ps(tmp_path, f"""
$tokens = $null; $errors = $null
[void][Management.Automation.Language.Parser]::ParseFile({ps_quote(ROOT / name)}, [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ throw ($errors | Out-String) }}
""")
        assert result.returncode == 0, result.stderr
    build = (ROOT / 'build.ps1').read_text(encoding='utf8')
    installer = (ROOT / 'installer/uoink.iss').read_text(encoding='utf8')
    assert '& $iscc /Q @signingArgs $issGenerated' in build
    assert "[Guid]::NewGuid()" in build
    assert 'SignedUninstallerDir={#ReleaseSigningDir}' in installer
    assert 'SignTool=uoinkrelease' in installer
    assert 'SignedUninstaller=yes' in installer
    assert 'SignToolRetryCount=0' in installer

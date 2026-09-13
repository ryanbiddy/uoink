"""Build-attempt persistence and hash binding; no artifact is actually signed."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOST = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
THUMB = 'A' * 40
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows signing build')


def quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    script = tmp_path / 'case.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n. " + quote(ROOT / 'scripts/installer_signing.ps1') + '\n' + body, encoding='utf8')
    return subprocess.run([str(HOST), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)], text=True, capture_output=True, timeout=30)


@pytest.mark.parametrize('final_status', ['failed', 'unsigned'])
def test_attempt_preserves_old_bytes_and_revokes_current_success(tmp_path: Path, final_status: str) -> None:
    artifact = tmp_path / 'setup.exe'
    artifact.write_bytes(b'previous installer')
    old_receipt = b'{"signature_verified":true,"historical":true}'
    Path(str(artifact) + '.signature.json').write_bytes(old_receipt)
    result = run(tmp_path, f"""
$attempt = New-UoinkBuildAttempt {quote(artifact)}
$pending = Get-Content -LiteralPath $attempt.receipt_path -Raw | ConvertFrom-Json
if ($pending.status -ne 'pending' -or $pending.signature_verified) {{ throw 'Stale success survived' }}
[IO.File]::WriteAllText($attempt.path, 'incomplete new compiler output')
Set-UoinkBuildAttemptReceipt $attempt '{final_status}' @{{error='synthetic compiler failure'}}
$attempt | ConvertTo-Json
""")
    assert result.returncode == 0, result.stderr
    attempt = json.loads(result.stdout)
    directory = Path(attempt['directory'])
    assert (directory / 'previous.exe').read_bytes() == b'previous installer'
    assert (directory / 'previous.signature.json').read_bytes() == old_receipt
    receipt = json.loads(Path(attempt['receipt_path']).read_text(encoding='utf8'))
    assert receipt['status'] == final_status
    assert receipt['signature_verified'] is False and receipt['release_ready'] is False
    assert (directory / 'pending.json').is_file()
    assert (directory / (final_status + '.json')).is_file()


@pytest.mark.parametrize('scenario', ['valid', 'missing', 'failed', 'changed', 'no_uninstaller'])
def test_final_verification_requires_complete_matching_callbacks(tmp_path: Path, scenario: str) -> None:
    artifact = tmp_path / 'setup.exe'
    artifact.write_bytes(b'installer')
    uninstaller_dir = tmp_path / 'uninstallers'
    uninstaller_dir.mkdir()
    uninstaller = uninstaller_dir / 'unins.e32'
    if scenario != 'no_uninstaller':
        uninstaller.write_bytes(b'uninstaller')
    result = run(tmp_path, f"""
function Assert-UoinkSignedFile {{
    param($FilePath, $CertificateThumbprint, $SignToolPath)
    return @{{path=$FilePath; sha256=(Get-UoinkFileSha256 $FilePath); signer_thumbprint=$CertificateThumbprint; signature_verified=$true}}
}}
$attempt = New-UoinkBuildAttempt {quote(artifact)}
$installer = Assert-UoinkSignedFile $attempt.path '{THUMB}' 'unused'
Write-UoinkSigningCallbackReceipt $attempt.callbacks @{{status='verified'; receipt=$installer}}
if ('{scenario}' -ne 'missing') {{
    $uninstaller = @{{sha256='unavailable'; signer_thumbprint='{THUMB}'; signature_verified=$true}}
    if (Test-Path -LiteralPath {quote(uninstaller)}) {{ $uninstaller = Assert-UoinkSignedFile {quote(uninstaller)} '{THUMB}' 'unused' }}
    $state = if ('{scenario}' -eq 'failed') {{ 'failed' }} else {{ 'verified' }}
    Write-UoinkSigningCallbackReceipt $attempt.callbacks @{{status=$state; receipt=$uninstaller}}
}}
if ('{scenario}' -eq 'changed') {{ [IO.File]::WriteAllText($attempt.path, 'changed after callback') }}
$details = Get-UoinkVerifiedBuildSignatures $attempt {quote(uninstaller_dir)} '{THUMB}' 'unused'
Set-UoinkBuildAttemptReceipt $attempt 'verified' $details
Get-Content -LiteralPath $attempt.receipt_path -Raw
""")
    assert (result.returncode == 0) is (scenario == 'valid'), result.stderr
    if scenario == 'valid':
        receipt = json.loads(result.stdout)
        assert receipt['signature_verified'] is True and receipt['release_ready'] is False
        assert len(receipt['details']['uninstallers']) == 1
        assert receipt['details']['callback_count'] == 2
    else:
        receipt = json.loads(Path(str(artifact) + '.signature.json').read_text(encoding='utf8'))
        assert receipt['status'] == 'pending' and receipt['signature_verified'] is False
        expected = {'missing': 'callback evidence', 'failed': 'callback evidence', 'changed': 'callback hash', 'no_uninstaller': 'cache is empty'}
        assert expected[scenario] in result.stderr


def test_callback_certificate_refusal_has_durable_error(tmp_path: Path) -> None:
    artifact = tmp_path / 'unsigned synthetic file.txt'
    artifact.write_bytes(b'synthetic; not an executable')
    sdk = tmp_path / 'signtool.exe'
    sdk.write_bytes(b'not executable; certificate refusal must happen first')
    receipts = tmp_path / 'receipts'
    receipts.mkdir()
    result = subprocess.run([str(HOST), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'scripts/sign_installer.ps1'), '-FilePath', str(artifact), '-CertificateThumbprint', '0' * 40, '-TimestampUrl', 'https://timestamp.example.test', '-SignToolPath', str(sdk), '-ReceiptDirectory', str(receipts)], text=True, capture_output=True, timeout=30)
    assert result.returncode != 0
    files = list(receipts.glob('*.json'))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding='utf8'))
    assert record['status'] == 'failed' and record['signature_verified'] is False
    assert 'Cannot find path' in record['error']
    assert artifact.read_bytes() == b'synthetic; not an executable'


def test_receipt_writer_never_overwrites_an_exclusive_record(tmp_path: Path) -> None:
    destination = tmp_path / 'existing.json'
    destination.write_bytes(b'original receipt')
    result = run(tmp_path, f"Write-UoinkSigningJson {quote(destination)} @{{status='replacement'}}")
    assert result.returncode != 0
    assert destination.read_bytes() == b'original receipt'
    assert list(tmp_path.glob('existing.json.*.tmp')) == []


def test_signtool_failure_retains_diagnostics_and_exit(tmp_path: Path) -> None:
    fake = tmp_path / 'fake-signer.ps1'
    fake.write_text("Write-Output 'Synthetic timestamp failure detail'\n$global:LASTEXITCODE=2\n", encoding='utf8')
    result = run(tmp_path, f"""
$script:UoinkSigningDiagnostics = [Collections.Generic.List[object]]::new()
try {{ Invoke-UoinkSignTool {quote(fake)} @('sign') }} catch {{ }}
ConvertTo-Json -InputObject @($script:UoinkSigningDiagnostics.ToArray()) -Depth 5
""")
    assert result.returncode == 0, result.stderr
    start = result.stdout.index('[')
    diagnostics = json.loads(result.stdout[start:])
    assert diagnostics == [{'exit': 2, 'operation': 'sign', 'output': ['Synthetic timestamp failure detail']}]

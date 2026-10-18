"""Host compatibility and preflight trust checks without signing any artifact."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
WINPS = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows signing host')


def quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run(tmp_path: Path, host: str, body: str) -> subprocess.CompletedProcess[str]:
    script = tmp_path / 'read-only-case.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n. " + quote(ROOT / 'scripts/installer_signing.ps1') + '\n' + body, encoding='utf8')
    return subprocess.run([host, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)], capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize('host_name', ['WindowsPowerShell', 'pwsh'])
def test_callback_resolves_windows_powershell_from_both_shells(tmp_path: Path, host_name: str) -> None:
    host = str(WINPS) if host_name == 'WindowsPowerShell' else shutil.which('pwsh')
    if not host:
        pytest.skip('PowerShell 7 unavailable')
    result = run(tmp_path, host, """
$callbackHost = Get-UoinkSigningPowerShellPath
$version = & $callbackHost -NoProfile -NonInteractive -Command '$PSVersionTable.PSVersion.ToString()'
if ($LASTEXITCODE -ne 0) { throw 'Selected host failed to start' }
@{path=$callbackHost; version=$version} | ConvertTo-Json
""")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert Path(data['path']).is_file()
    assert data['version'].startswith('5.1.')


@pytest.mark.parametrize('trusted', [True, False])
def test_chain_refusal_precedes_any_signing_work(tmp_path: Path, trusted: bool) -> None:
    result = run(tmp_path, str(WINPS), f"""
function Get-Item {{
    param($LiteralPath, $ErrorAction)
    $certificate = [pscustomobject]@{{HasPrivateKey=$true; NotBefore=[DateTime]::UtcNow.AddDays(-1);
        NotAfter=[DateTime]::UtcNow.AddDays(1);
        EnhancedKeyUsageList=@([pscustomobject]@{{ObjectId=[pscustomobject]@{{Value='1.3.6.1.5.5.7.3.3'}}}})}}
    $certificate | Add-Member -MemberType ScriptMethod -Name Verify -Value {{ return ${str(trusted).lower()} }}
    return $certificate
}}
Assert-UoinkSigningCertificate '{'A' * 40}'
""")
    assert (result.returncode == 0) is trusted, result.stderr
    if not trusted:
        assert 'trust-chain verification failed' in result.stderr

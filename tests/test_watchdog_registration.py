"""Execute the real PowerShell registrar with every OS mutation shadowed."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell registration contracts')
@pytest.mark.parametrize('scenario,events,failed', [
    ('clean', ['register'], False),
    ('upgrade', ['register', 'remove-run'], False),
    ('update', ['register', 'remove-run'], False),
    ('legacy-task', ['register', 'disable-old', 'unregister-old'], False),
    ('register-failure', ['register'], True),
    ('remove-failure', ['register', 'remove-run', 'restore-run'], True),
    ('unregister', ['unregister', 'remove-run'], False), ('absent', [], False),
    ('disable', ['disable', 'remove-run'], False), ('status', [], False),
    ('foreign', [], True), ('whatif', [], False),
    ('unregister-preview', [], False),
    ('ownership', [], False), ('ownership-disabled', [], False),
    ('ownership-absent', [], False), ('ownership-foreign', [], True),
])
def test_registration_arguments_and_migration_order(tmp_path, scenario, events, failed):
    app = tmp_path / 'Install with spaces'
    (app / 'python').mkdir(parents=True)
    (app / 'python/pythonw.exe').touch()
    (app / 'uoink_supervisor.py').touch()
    result = subprocess.run([
        shutil.which('powershell.exe'), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', str(ROOT / 'tests/watchdog_fixture.ps1'),
        '-Script', str(ROOT / 'scripts/install-watchdog.ps1'),
        '-InstallDir', str(app), '-Scenario', scenario], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload['events'] == events
    assert payload['failed'] is failed
    if scenario in {'ownership', 'ownership-disabled'}:
        assert payload['result'] == 'owned'
    if scenario == 'ownership-absent':
        assert payload['result'] == 'absent'


def test_powershell_sources_parse_without_execution():
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('PowerShell parser unavailable')
    files = ['scripts/install-watchdog.ps1', 'installer/upgrade_prep.ps1',
             'installer/verify_install.ps1', 'installer/templates/stop-server.ps1', 'tests/watchdog_fixture.ps1',
             'tests/upgrade_prep_fixture.ps1']
    for name in files:
        # Paths are repository-owned, never user-provided shell fragments.
        command = "$tokens=$null; $errors=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('" + str(ROOT / name).replace("'", "''") + "', [ref]$tokens, [ref]$errors); if ($errors) { $errors | Out-String | Write-Error; exit 1 }"
        result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr

"""Run upgrade prep control flow with every OS boundary mocked."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell control flow')
@pytest.mark.parametrize('scenario,exit_code,events', [
    ('stop-fails', 1, ['stop-intent']),
    ('still-bound', 1, ['stop-intent', 'process-query', 'kill-owned']),
    ('kill-frees', 0, ['stop-intent', 'process-query', 'kill-owned', 'clear-sentinel']),
    ('free', 0, ['stop-intent', 'process-query', 'kill-owned', 'clear-sentinel']),
])
def test_upgrade_prep_blocks_setup_when_stop_or_port_release_fails(tmp_path, scenario, exit_code, events):
    app = tmp_path / 'Install with spaces'
    app.mkdir()
    (app / 'uoink_supervisor.py').touch()
    appdata = tmp_path / 'appdata'
    (appdata / 'Uoink').mkdir(parents=True)
    (appdata / 'Uoink/.first-run-done').touch()
    events_path = tmp_path / 'events.txt'
    result = subprocess.run([
        shutil.which('powershell.exe'), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', str(ROOT / 'tests/upgrade_prep_fixture.ps1'), '-Script', str(ROOT / 'installer/upgrade_prep.ps1'),
        '-InstallDir', str(app), '-Scenario', scenario, '-EventsPath', str(events_path)],
        env={**os.environ, 'LOCALAPPDATA': str(appdata), 'TEMP': str(tmp_path)},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == exit_code, result.stdout + result.stderr
    actual = events_path.read_text().splitlines()
    assert [event for event in actual if event != 'port-probe'] == events
    if scenario == 'stop-fails':
        assert 'port-probe' not in actual
    if exit_code:
        assert 'Upgrade stopped:' in (tmp_path / 'uoink-upgrade-prep.log').read_text(encoding='utf-8-sig')

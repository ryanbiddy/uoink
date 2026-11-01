"""Silent installs and upgrades start the helper again, quietly.

No setup, task, registry, installed helper or port 5179. The supervisor runs
disposable children, the Pascal callback runs through the recovery harness and
upgrade_prep.ps1 runs with its OS boundaries mocked.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

import uoink_supervisor as recovery
from inno_recovery_harness import InstallerCallbacks
from test_helper_recovery import supervisor

ROOT = Path(__file__).resolve().parents[1]
ISS = (ROOT / 'installer/uoink.iss').read_text(encoding='utf-8')
PREP = (ROOT / 'installer/upgrade_prep.ps1').read_text(encoding='utf-8')
SERVER = (ROOT / 'server.py').read_text(encoding='utf-8')


def run_entries():
    section = ISS.split('\n[Run]', 1)[1].split('\n[UninstallRun]', 1)[0]
    lines = [line for line in section.splitlines() if not line.startswith(';')]
    entries = re.split(r'\n(?=Filename:)', '\n'.join(lines).strip())
    return [entry for entry in entries if entry.startswith('Filename:')]


def test_interactive_entry_is_unchanged_and_silent_entry_is_quiet():
    interactive, silent = run_entries()
    assert 'Flags: postinstall nowait skipifsilent' in interactive
    assert 'Check: not IsolatedInstall' in interactive
    assert '--quiet' not in interactive
    # Runs only when setup is silent, never on the finish page.
    assert 'Flags: nowait skipifnotsilent;' in silent
    assert 'postinstall' not in silent
    assert '"""{app}\\uoink_supervisor.py"" --quiet"' in silent
    assert '{app}\\python\\pythonw.exe' in silent
    assert '--show-dashboard' not in silent and '--startup' not in silent
    assert 'Check: SilentHelperStartWanted' in silent


def test_silent_start_check_excludes_isolated_installs():
    body = ISS.split('function SilentHelperStartWanted(): Boolean;', 1)[1].split('end;', 1)[0]
    assert 'Result := HelperStartWanted and (not IsolatedInstall());' in body
    for isolated, wanted, expected in [(False, True, True), (True, True, False), (False, False, False)]:
        installer = InstallerCallbacks(ISS, {'isolatedinstall': lambda: isolated,
                                             'helperstartwanted': wanted, 'true': True}, None)
        assert installer.call('SilentHelperStartWanted') is expected


def prepare(*, previous_install, marker_written, isolated=False):
    logs, params_seen = [], []

    def execute(executable, params, cwd, show, wait, code):
        params_seen.append(params)
        return True, 0

    def fileexists(path):
        if 'uoink-helper-restart.txt' in path:
            return marker_written
        if path.endswith(('\\uoink_supervisor.py', '\\server.py')):
            return previous_install
        return True

    externals = dict(
        expandconstant=lambda s: s.replace('{tmp}', 'TMP').replace('{app}', 'APP'),
        isolatedinstall=lambda: isolated, isolatedvalidatetargetdir=lambda *a: True,
        isolatedcloseswitchesvalid=lambda: True, isolatedvalidatedeclaredinputs=lambda: True,
        log=logs.append, inttostr=str, extracttemporaryfile=lambda name: None,
        fileexists=fileexists, deletefile=lambda p: True, sw_hide='hidden',
        ewwaituntilterminated='wait', isolatederrortext='',
    )
    installer = InstallerCallbacks(ISS, externals, execute)
    assert installer.call('PrepareToInstall', needsrestart=False) == ''
    return logs, params_seen


@pytest.mark.parametrize('previous_install,marker_written,wanted', [
    (False, False, True),   # Fresh install: matches the default-checked box.
    (True, True, True),     # Upgrade over a running helper.
    (True, False, False),   # Upgrade over a stopped helper stays stopped.
])
def test_prepare_decides_the_silent_start(previous_install, marker_written, wanted):
    logs, params = prepare(previous_install=previous_install, marker_written=marker_written)
    assert ('PrepareToInstall: a silent install starts the helper after setup' in logs) is wanted
    assert params and '-RestartMarker "TMP\\uoink-helper-restart.txt"' in params[0]


def test_isolated_prepare_never_runs_prep_or_wants_a_start():
    logs, params = prepare(previous_install=False, marker_written=True, isolated=True)
    assert params == []
    assert not any('silent install starts' in line for line in logs)


def test_upgrade_stop_does_not_block_same_login_startup(tmp_path):
    supervisor(tmp_path, 'exit0').run()
    recovery.request_stop(tmp_path, reason=recovery.UPGRADE_STOP)
    supervisor(tmp_path, 'exit0', startup=True).run()
    assert (tmp_path / 'starts').read_text().splitlines() == ['start', 'start']
    assert not (tmp_path / recovery.STOP_FILE).exists()


@pytest.mark.parametrize('body', ['{"reason": "quit"}', '{"reason": "uninstall"}', 'not json', '{}'])
def test_user_quit_still_blocks_same_login_startup(tmp_path, body):
    supervisor(tmp_path, 'exit0').run()
    (tmp_path / recovery.STOP_FILE).write_text(body)
    supervisor(tmp_path, 'exit0', startup=True).run()
    assert (tmp_path / 'starts').read_text().splitlines() == ['start']
    assert (tmp_path / recovery.STOP_FILE).exists()


def test_quiet_flag_reaches_every_helper_start(monkeypatch, tmp_path):
    seen = {}

    class Fake:
        owned = True

        def __init__(self, root, command, url, **kw):
            seen['command'] = command
            seen['first_args'] = kw['first_args']

        def run(self):
            return 0

    monkeypatch.setattr(recovery, 'Supervisor', Fake)
    monkeypatch.setattr(recovery, 'login_session', lambda: 'fixture')
    monkeypatch.setattr(recovery, 'data_root', lambda: tmp_path)
    assert recovery.main(['--quiet']) == 0
    assert seen['command'][-1] == '--quiet' and seen['command'][-2].endswith('server.py')
    assert '--show-dashboard' not in seen['command'] + seen['first_args']
    assert recovery.main([]) == 0
    assert '--quiet' not in seen['command']


def test_quiet_server_start_skips_splash_and_ready_toast():
    assert 'def main(*, show_dashboard: bool = False, quiet: bool = False):' in SERVER
    assert SERVER.count('if not quiet and _splash_should_spawn(') == 2
    assert 'quiet="--quiet" in argv' in SERVER
    toast = SERVER.split('    if quiet:\n        log.info("toast: skipped ready toast for a quiet start")', 1)
    assert len(toast) == 2 and toast[1].lstrip().startswith('elif splash_spawned:')


def test_prep_reads_the_user_stop_before_its_own_stop():
    assert PREP.index('$userStopped = Test-UserStopFile $stopPath') < PREP.index("--stop\n")
    assert 'reason -ne \'upgrade\'' in PREP
    assert 'New-Object System.Text.UTF8Encoding $false' in PREP


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell control flow')
@pytest.mark.parametrize('scenario,prior_stop,marker,reason', [
    ('kill-frees', None, True, 'upgrade'),       # Running helper: restart, relabel.
    ('free', None, False, 'upgrade'),            # Not running: no restart, but no Quit either.
    ('free', 'quit', False, 'quit'),             # The user's Quit is kept.
    ('free', 'upgrade', False, 'upgrade'),       # An old upgrade stop is not a Quit.
])
def test_prep_marks_restart_and_relabels_its_own_stop(tmp_path, scenario, prior_stop, marker, reason):
    app = tmp_path / 'Install with spaces'
    app.mkdir()
    (app / 'uoink_supervisor.py').touch()
    data = tmp_path / 'appdata' / 'Uoink'
    data.mkdir(parents=True)
    stop_path = data / 'helper-stop.json'
    if prior_stop:
        stop_path.write_text(json.dumps({'reason': prior_stop}))
    marker_path = tmp_path / 'setup tmp' / 'uoink-helper-restart.txt'
    marker_path.parent.mkdir()
    result = subprocess.run([
        shutil.which('powershell.exe'), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', str(ROOT / 'tests/upgrade_prep_fixture.ps1'), '-Script', str(ROOT / 'installer/upgrade_prep.ps1'),
        '-InstallDir', str(app), '-Scenario', scenario, '-EventsPath', str(tmp_path / 'events.txt'),
        '-RestartMarker', str(marker_path)],
        env={**os.environ, 'LOCALAPPDATA': str(tmp_path / 'appdata'), 'TEMP': str(tmp_path)},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert marker_path.exists() is marker
    # The supervisor reads it with Python's json: no BOM.
    assert json.loads(stop_path.read_bytes().decode('utf-8'))['reason'] == reason
    assert recovery.stop_reason(data) == reason

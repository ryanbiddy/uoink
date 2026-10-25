"""Recovery callback ordering, with no setup, task, registry or port access."""
from pathlib import Path

import pytest

from inno_recovery_harness import InstallerCallbacks

ROOT = Path(__file__).resolve().parents[1]
ISS = (ROOT / 'installer/uoink.iss').read_text(encoding='utf-8')


class Aborted(Exception):
    pass


def callbacks(*, removal_ok=True, preview_ok=True, isolated=False, prep_ok=True,
              prep_code=0, script_present=True, extract_ok=True):
    events = []
    def abort():
        events.append('abort')
        raise Aborted()
    def extract(name):
        assert name == 'upgrade_prep.ps1'
        if not extract_ok:
            raise OSError('fixture extraction failure')
    def execute(executable, params, cwd, show, wait, code):
        assert executable == 'powershell.exe' and show == 'hidden' and wait == 'wait'
        if '-Mode Unregister' in params:
            assert 'scripts\\install-watchdog.ps1' in params
            preview = '-WhatIf' in params
            events.append('probe' if preview else 'unregister')
            return True, 0 if (preview_ok if preview else removal_ok) else 1
        assert 'upgrade_prep.ps1' in params and '-InstallDir' in params
        events.append('prepare')
        return prep_ok, prep_code
    externals = dict(
        expandconstant=lambda s: s, getpreviousdata=lambda *a: '', trim=str.strip,
        comparetext=lambda a, b: 0 if a.lower() == b.lower() else -1,
        isolatedmarkerfileexists=lambda *a: False, isolatedinstall=lambda: isolated,
        isolatedvalidatetargetdir=lambda *a: True, isolatedcloseswitchesvalid=lambda: True,
        isolatedvalidatedeclaredinputs=lambda: True,
        suppressiblemsgbox=lambda *a: events.append('error'), log=lambda *a: None,
        removeagentpath=lambda: events.append('remove-path'), abort=abort,
        sw_hide='hidden', ewwaituntilterminated='wait', mbinformation=0, mb_ok=0, idok=0,
        usuninstall='confirmed', inttostr=str, extracttemporaryfile=extract,
        fileexists=lambda p: script_present if 'upgrade_prep.ps1' in p else True,
        deletefile=lambda p: events.append('delete-sentinel') or True,
    )
    return InstallerCallbacks(ISS, externals, execute), events


@pytest.mark.parametrize('confirmed', [False, True])
def test_startup_removal_only_after_uninstall_confirmation(confirmed):
    installer, events = callbacks()
    assert installer.call('InitializeUninstall') is True
    assert events == ['probe']
    # Closing or declining the confirmation never dispatches usUninstall.
    if confirmed:
        installer.call('CurUninstallStepChanged', curuninstallstep='confirmed')
        assert events == ['probe', 'unregister', 'remove-path']
    for step in ['mutex-check', 'post-uninstall', 'done']:
        before = list(events)
        installer.call('CurUninstallStepChanged', curuninstallstep=step)
        assert events == before


def test_failed_removal_aborts_confirmed_uninstall_before_path_or_files():
    installer, events = callbacks(removal_ok=False)
    assert installer.call('InitializeUninstall') is True
    with pytest.raises(Aborted):
        installer.call('CurUninstallStepChanged', curuninstallstep='confirmed')
    assert events == ['probe', 'unregister', 'error', 'abort']


def test_failed_preflight_never_removes_startup():
    installer, events = callbacks(preview_ok=False)
    assert installer.call('InitializeUninstall') is False
    assert events == ['probe', 'error']


def test_isolated_confirmed_uninstall_skips_ordinary_startup():
    installer, events = callbacks(isolated=True)
    installer.call('CurUninstallStepChanged', curuninstallstep='confirmed')
    assert events == ['remove-path']


@pytest.mark.parametrize('options,allowed', [({}, True), ({'prep_ok': False}, False),
    ({'prep_code': 1}, False), ({'script_present': False}, False), ({'extract_ok': False}, False)])
def test_upgrade_preparation_failure_blocks_file_replacement(options, allowed):
    installer, events = callbacks(**options)
    result = installer.call('PrepareToInstall', needsrestart=False)
    assert (result == '') is allowed
    assert ('delete-sentinel' in events) is allowed
    if not allowed:
        assert 'setup' in result and 'again' in result

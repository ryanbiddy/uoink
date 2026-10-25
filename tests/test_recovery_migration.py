"""Startup migration uses the registrar's read-only ownership result."""
from contextlib import nullcontext
import subprocess
import sys
from types import SimpleNamespace

import pytest

import migrate_install as migration


@pytest.fixture
def installed(tmp_path, monkeypatch):
    app = tmp_path / 'App with spaces'
    (app / 'scripts').mkdir(parents=True)
    (app / 'scripts/install-watchdog.ps1').touch()
    (app / 'python').mkdir()
    (app / 'python/pythonw.exe').touch()
    monkeypatch.setattr(migration, 'sys', SimpleNamespace(platform='win32'))
    writes = []
    legacy = []
    monkeypatch.setattr(migration, '_remove_legacy_run_key', lambda dry_run: legacy.append(dry_run) or 'legacy removed')
    expected = f'"{app / "python/pythonw.exe"}" "{app / "server.py"}"'
    monkeypatch.setitem(sys.modules, 'winreg', SimpleNamespace(
        HKEY_CURRENT_USER=1, KEY_READ=2, KEY_SET_VALUE=4, REG_SZ=1,
        OpenKey=lambda *a: nullcontext('key'),
        SetValueEx=lambda *a: writes.append(a), QueryValueEx=lambda *a: (expected, 1)))
    return app, writes, legacy


@pytest.mark.parametrize('answer,code,expected', [('owned', 0, True), ('absent', 0, False),
                                              ('owned', 1, None), ('unexpected', 0, None)])
def test_ownership_uses_exact_registrar_command(installed, monkeypatch, answer, code, expected):
    app, _, _ = installed
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=code, stdout=answer + '\n')
    monkeypatch.setattr(migration.subprocess, 'run', run)
    assert migration._supervisor_owns_startup(app) is expected
    assert calls == [([
        'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', str(app / 'scripts/install-watchdog.ps1'), '-InstallDir', str(app), '-Mode', 'Ownership'],
        dict(capture_output=True, text=True, timeout=30, creationflags=0x08000000))]


@pytest.mark.parametrize('answer,code,write,remove', [('owned', 0, False, True),
    ('absent', 0, True, True), ('', 1, False, False), ('unexpected', 0, False, False)])
@pytest.mark.parametrize('dry_run', [False, True])
def test_run_migration_respects_task_ownership(installed, monkeypatch, answer, code, write, remove, dry_run):
    app, writes, legacy = installed
    monkeypatch.setattr(migration.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=code, stdout=answer))
    migration._migrate_run_key(app, dry_run)
    assert bool(writes) is (write and not dry_run)
    assert legacy == ([dry_run] if remove else [])


def test_authoritative_data_path_does_not_restore_run_value(installed, monkeypatch, tmp_path):
    import uoink_install_isolation
    app, writes, legacy = installed
    old, new = tmp_path / 'old', tmp_path / 'new'
    old.mkdir()
    new.mkdir()
    (new / 'index.db').touch()
    monkeypatch.setattr(uoink_install_isolation, 'current_binding', lambda: None)
    monkeypatch.setattr(migration, '_old_data_root', lambda: old)
    monkeypatch.setattr(migration, '_new_data_root', lambda: new)
    monkeypatch.setattr(migration, '_migrate_keyring', lambda _: 'mocked')
    monkeypatch.setattr(migration, '_maybe_cleanup_old_root', lambda *a: 'retained')
    monkeypatch.setattr(migration.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='owned'))
    result = migration.run_migration(app_dir=app)
    assert result['outcome'] == 'uoink_authoritative'
    assert writes == [] and legacy == [False]


def test_ownership_probe_failure_preserves_startup(installed, monkeypatch):
    app, writes, legacy = installed
    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired('mocked', 30)
    monkeypatch.setattr(migration.subprocess, 'run', timeout)
    assert 'startup retained' in migration._migrate_run_key(app, False)
    assert writes == legacy == []

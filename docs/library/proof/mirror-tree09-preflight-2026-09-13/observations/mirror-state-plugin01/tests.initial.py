"""Synthetic observer verification: no library_mirror import, processes or gates."""
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import threading

import pytest

from _scratch import mirror_state_receipt_plugin as p


def report(nodeid='tests/test_phase4_dummy.py::test_dummy', when='teardown', outcome='passed'):
    return SimpleNamespace(nodeid=nodeid, when=when, outcome=outcome, failed=outcome == 'failed')


def records(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


@pytest.fixture
def dummy_module(monkeypatch):
    class Untouchable:
        def __getattribute__(self, name):
            raise AssertionError('observer invoked object getter: ' + name)
        def physically_alive(self):
            raise AssertionError('observer invoked liveness')
        def terminate(self):
            raise AssertionError('observer invoked cleanup')
        def poll(self):
            raise AssertionError('observer invoked process poll')
    def stored(**fields):
        obj = Untouchable()
        object.__getattribute__(obj, '__dict__').update(fields)
        return obj
    thread = stored(_ident=threading.get_ident(), _native_id=123, _name='inert-owner',
                    _is_stopped=False, _started=stored(_flag=True), _daemonic=True)
    proc = stored(pid=101, returncode=0)
    session = stored(proc=proc, dest='synthetic-vault', writer_pid=202, created_ms=11,
                     writer_created_ms=22, _dead=False, _launching=True, _popen_in_progress=False,
                     _owned_created={101: 11, 202: 22, 303: None},
                     _owned_exe={303: 'synthetic-child.exe'}, _origin_thread=thread,
                     _origin_thread_id=threading.get_ident())
    owner = stored(dest='synthetic-vault', key='synthetic-gate', held=True, _exclusive_holds=1,
                   _stop=stored(_flag=False), _done=stored(_flag=False), _acquired=stored(_flag=True),
                   _thread=thread, sessions={session})
    object.__getattribute__(session, '__dict__')['_exclusion_owner'] = owner
    module = ModuleType('library_mirror')
    module._live_owners = {owner}
    module._retained_sessions = {session}
    module._dest_holds = {'synthetic-gate': 123}
    monkeypatch.setitem(p.sys.modules, 'library_mirror', module)
    return module, owner, session


def test_raw_capture_bypasses_all_product_getters_and_methods(dummy_module):
    module, owner, session = dummy_module
    before = dict(object.__getattribute__(session, '__dict__'))
    state = p.capture_state()
    row = state['owners'][0]
    assert row['held'] is True and row['exclusive_holds'] == 1
    assert row['stop_flag'] is False and row['done_flag'] is False
    assert row['thread']['ident'] == threading.get_ident()
    observed = row['sessions'][0]
    assert observed['proc_pid'] == 101 and observed['proc_returncode'] == 0
    assert observed['_owned_created'][-1] == {'key': 303, 'value': None}
    assert observed['_owned_exe'] == [{'key': 303, 'value': 'synthetic-child.exe'}]
    assert observed['_launching'] is True and observed['_popen_in_progress'] is False
    assert observed['owner_id'] == id(owner)
    assert state['retained_sessions'][0] == observed
    assert object.__getattribute__(session, '__dict__') == before
    assert module._live_owners == {owner}


def test_stacks_are_opt_in_and_contain_no_frame_locals(dummy_module, monkeypatch):
    actual = p.sys._current_frames
    def forbidden():
        raise AssertionError('stacks accessed while disabled')
    monkeypatch.setattr(p.sys, '_current_frames', forbidden)
    assert 'thread_stack' not in p.capture_state()['owners'][0]
    monkeypatch.setattr(p.sys, '_current_frames', actual)
    row = p.capture_state(True)['owners'][0]
    assert row['thread_frame_present'] is True
    assert row['thread_stack']['frames_innermost_first']
    assert set(row['thread_stack']['frames_innermost_first'][0]) == {'file', 'line', 'function'}


def test_module_absence_does_not_import_product(monkeypatch):
    monkeypatch.delitem(p.sys.modules, 'library_mirror', raising=False)
    assert p.capture_state() == {'module_loaded': False}
    assert 'library_mirror' not in p.sys.modules


def test_report_selection_and_original_outcomes_are_unchanged(tmp_path, dummy_module):
    path = tmp_path/'selection.jsonl'
    observer = p.Observer(path)
    untouched = report(when='call')
    original = vars(untouched).copy()
    observer.observe_report(untouched)
    observer.observe_report(report(nodeid='tests/test_elsewhere.py::test_ok'))
    observer.observe_report(report(nodeid='tests/library_work_astra/test_phase4_dummy.py::test_ok'))
    failure = report(nodeid='tests/test_elsewhere.py::test_failure', when='setup', outcome='failed')
    observer.observe_report(failure)
    observer.finish(1, 4, 1)
    rows = records(path)
    assert [row['event'] for row in rows] == ['observer_started', 'mirror_state', 'mirror_state', 'observer_finished']
    assert rows[1]['trigger'] == 'phase4_teardown' and rows[2]['trigger'] == 'failure'
    assert rows[-1]['pytest_exitstatus'] == 1 and rows[-1]['observer_errors'] == 0
    assert rows[-1]['diagnostic_complete'] is True
    assert vars(untouched) == original and failure.outcome == 'failed'


@pytest.mark.parametrize('kind', ['relative', 'outside', 'parent_escape', 'wrong_suffix'])
def test_invalid_paths_are_rejected_before_open(tmp_path, monkeypatch, kind):
    paths = {'relative': Path('relative.jsonl'), 'outside': p.SCRATCH.parent/'elsewhere.jsonl',
             'parent_escape': p.SCRATCH/'..'/'escape.jsonl', 'wrong_suffix': tmp_path/'wrong.txt'}
    def forbidden_open(*args, **kwargs):
        raise AssertionError('invalid destination reached open')
    monkeypatch.setattr(Path, 'open', forbidden_open)
    with pytest.raises(ValueError):
        p.Observer(paths[kind])


def test_existing_receipt_is_never_reused(tmp_path):
    path = tmp_path/'existing.jsonl'
    path.write_text('preserve me\n', encoding='utf-8')
    with pytest.raises(FileExistsError):
        p.Observer(path)
    assert path.read_text(encoding='utf-8') == 'preserve me\n'


def test_reparse_parent_is_refused_without_real_link(tmp_path, monkeypatch):
    actual = Path.lstat
    def inert_stat(path):
        if path == tmp_path:
            return SimpleNamespace(st_mode=p.stat.S_IFDIR, st_file_attributes=0x400)
        return actual(path)
    monkeypatch.setattr(Path, 'lstat', inert_stat)
    with pytest.raises(ValueError, match='reparse'):
        p.Observer(tmp_path/'reparse.jsonl')
    assert not (tmp_path/'reparse.jsonl').exists()


def test_capture_error_is_reported_separately_from_test_outcome(tmp_path, monkeypatch, capsys):
    observer = p.Observer(tmp_path/'capture-error.jsonl')
    def broken(*args):
        raise RuntimeError('synthetic snapshot failure')
    monkeypatch.setattr(p, 'capture_state', broken)
    original = report()
    observer.observe_report(original)
    observer.finish(0, 1, 0)
    rows = records(observer.path)
    assert rows[1]['event'] == 'observer_error' and rows[1]['stage'] == 'capture'
    assert rows[-1]['pytest_exitstatus'] == 0 and rows[-1]['pytest_tests_failed'] == 0
    assert rows[-1]['observer_errors'] == 1 and rows[-1]['diagnostic_complete'] is False
    assert original.outcome == 'passed'
    assert 'pytest outcomes unchanged' in capsys.readouterr().err


def test_write_error_is_visible_when_receipt_itself_cannot_record_it(tmp_path, capsys):
    observer = p.Observer(tmp_path/'write-error.jsonl')
    observer.stream.close()
    observer.observe_report(report())
    assert [row['stage'] for row in observer.errors] == ['state_record_write', 'error_record_write']
    assert 'MIRROR STATE OBSERVER ERROR' in capsys.readouterr().err
    observer.finish(0, 1, 0)
    assert observer.closed and len(observer.errors) >= 4


def test_pytest_hooks_preserve_status_and_surface_instrument_health(tmp_path, monkeypatch):
    observer = p.Observer(tmp_path/'hooks.jsonl')
    monkeypatch.setattr(p, '_OBSERVER', observer)
    monkeypatch.delitem(p.sys.modules, 'library_mirror', raising=False)
    sample = report(outcome='failed')
    p.pytest_runtest_logreport(sample)
    session = SimpleNamespace(testscollected=1, testsfailed=1, exitstatus=1)
    p.pytest_sessionfinish(session, 1)
    lines = []
    terminal = SimpleNamespace(write_line=lambda text, **kwargs: lines.append(text))
    p.pytest_terminal_summary(terminal)
    assert session.exitstatus == 1 and session.testsfailed == 1 and sample.outcome == 'failed'
    assert '1 observations, no observer errors' in lines[-1]
    observer.errors.append({'stage': 'synthetic terminal error'})
    p.pytest_terminal_summary(terminal)
    assert 'diagnostic receipt incomplete' in lines[-1]


def test_configure_refusal_is_explicit_observer_usage_error(monkeypatch, tmp_path):
    path = tmp_path/'used.jsonl'
    path.write_text('existing\n', encoding='utf-8')
    monkeypatch.setenv('IG_MIRROR_STATE_RECEIPT_PATH', str(path))
    with pytest.raises(pytest.UsageError, match='mirror state observer setup failed'):
        p.pytest_configure(SimpleNamespace())

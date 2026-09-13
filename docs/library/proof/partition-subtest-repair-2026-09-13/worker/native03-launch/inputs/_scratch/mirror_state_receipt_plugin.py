"""Passive mirror snapshots. Observer errors never replace pytest outcomes."""
import json
import os
from pathlib import Path
import stat
import sys
import threading
import time

import pytest


SCRATCH = Path(__file__).absolute().parent
_OBSERVER = None


def _fields(value):
    """Read storage, bypassing product properties and __getattribute__ hooks."""
    if value is None:
        return {}
    fields = object.__getattribute__(value, '__dict__')
    if type(fields) is not dict:
        raise TypeError('observer requires an ordinary instance dictionary')
    return fields


def _raw(value):
    """Serialize ordinary stored values without repr or arbitrary descriptors."""
    kind = type(value)
    if value is None or kind in (str, int, bool, float):
        return value
    if kind in (list, tuple):
        return [_raw(item) for item in value]
    if kind is dict:
        return [{'key': _raw(key), 'value': _raw(item)} for key, item in value.items()]
    return {'python_type': kind.__name__, 'object_id': id(value)}


def _flag(event):
    return _raw(_fields(event).get('_flag'))


def _thread_row(thread):
    fields = _fields(thread)
    return {
        'object_id': id(thread) if thread is not None else None,
        'ident': _raw(fields.get('_ident')),
        'native_id': _raw(fields.get('_native_id')),
        'name': _raw(fields.get('_name')),
        'is_stopped_flag': _raw(fields.get('_is_stopped')),
        'started_flag': _flag(fields.get('_started')),
        'daemon_flag': _raw(fields.get('_daemonic')),
    }


def _session_row(session):
    fields = _fields(session)
    proc = fields.get('proc')
    process = _fields(proc)
    owner = fields.get('_exclusion_owner')
    result = {name: _raw(fields.get(name)) for name in (
        'dest', 'writer_pid', 'created_ms', 'writer_created_ms', '_dead',
        '_launching', '_popen_in_progress', '_origin_thread_id', '_owned_created',
        '_owned_exe', 'job', '_lease_written',
    )}
    result.update(
        object_id=id(session),
        owner_id=id(owner) if owner is not None else None,
        proc_object_id=id(proc) if proc is not None else None,
        proc_pid=_raw(process.get('pid')),
        proc_returncode=_raw(process.get('returncode')),
        origin_thread=_thread_row(fields.get('_origin_thread')),
    )
    return result


def _stack(frame):
    rows = []
    while frame is not None and len(rows) < 100:
        rows.append({'file': frame.f_code.co_filename,
                     'line': frame.f_lineno, 'function': frame.f_code.co_name})
        frame = frame.f_back
    return {'frames_innermost_first': rows, 'truncated': frame is not None}


def capture_state(include_stacks=False):
    module = sys.modules.get('library_mirror')
    if module is None:
        return {'module_loaded': False}
    fields = _fields(module)
    owners = list(fields.get('_live_owners', ()))
    retained = list(fields.get('_retained_sessions', ()))
    frames = sys._current_frames() if include_stacks else {}
    rows = []
    for owner in sorted(owners, key=id):
        stored = _fields(owner)
        thread = _thread_row(stored.get('_thread'))
        row = {
            'object_id': id(owner),
            'dest': _raw(stored.get('dest')), 'key': _raw(stored.get('key')),
            'held': _raw(stored.get('held')),
            'exclusive_holds': _raw(stored.get('_exclusive_holds')),
            'stop_flag': _flag(stored.get('_stop')),
            'done_flag': _flag(stored.get('_done')),
            'acquired_flag': _flag(stored.get('_acquired')),
            'thread': thread,
            'sessions': [_session_row(item) for item in sorted(list(stored.get('sessions', ())), key=id)],
        }
        if include_stacks:
            ident = thread['ident']
            frame = frames.get(ident) if type(ident) is int else None
            row['thread_frame_present'] = frame is not None
            if frame is not None:
                row['thread_stack'] = _stack(frame)
        rows.append(row)
    return {
        'module_loaded': True,
        'consistency': 'unlocked sequential snapshot; fields may span concurrent transitions',
        'liveness_basis': 'raw Python fields only; no physical process liveness query',
        'owners': rows,
        'retained_sessions': [_session_row(item) for item in sorted(retained, key=id)],
        'dest_holds': _raw(fields.get('_dest_holds')),
    }


def _open_fresh(destination):
    path = Path(destination)
    # Reject lexical escapes before resolving or inspecting any supplied path.
    if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(SCRATCH):
        raise ValueError('observer output must be an absolute path below checkout _scratch')
    if path == SCRATCH or path.suffix.lower() != '.jsonl':
        raise ValueError('observer output must name a fresh .jsonl file')
    current = path.parent
    while True:
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
            raise ValueError('observer output parent must not be a link or reparse point')
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('observer output parent must be an existing directory')
        if current == SCRATCH:
            break
        current = current.parent
    if not path.parent.resolve().is_relative_to(SCRATCH.resolve()):
        raise ValueError('observer resolved output escapes checkout _scratch')
    # Exclusive creation also rejects an existing file, dangling link or directory.
    return path, path.open('x', encoding='utf-8', newline='\n')


class Observer:
    def __init__(self, destination, include_stacks=False):
        self.path, self.stream = _open_fresh(destination)
        self.include_stacks = include_stacks
        self.errors = []
        self.observations = 0
        self.closed = False
        self._write({'event': 'observer_started', 'schema': 1,
                     'include_stacks': include_stacks,
                     'outcome_policy': 'pytest outcomes are unchanged; observer errors invalidate this diagnostic receipt'})

    def _write(self, row):
        self.stream.write(json.dumps(row, ensure_ascii=True, allow_nan=False) + '\n')
        self.stream.flush()

    def _failure(self, stage, error, context=None):
        row = {'event': 'observer_error', 'stage': stage,
               'error_type': type(error).__name__, 'message': str(error),
               'context': context}
        self.errors.append(row)
        try:
            self._write(row)
        except Exception as write_error:
            self.errors.append({'event': 'observer_error', 'stage': 'error_record_write',
                                'error_type': type(write_error).__name__, 'message': str(write_error)})
        sys.stderr.write('MIRROR STATE OBSERVER ERROR: diagnostic receipt is incomplete; pytest outcomes unchanged. '
                         + stage + ': ' + type(error).__name__ + '\n')

    def observe_report(self, report):
        nodeid = report.nodeid
        file_name = nodeid.split('::', 1)[0].replace('\\', '/').rsplit('/', 1)[-1]
        phase4_teardown = report.when == 'teardown' and file_name.startswith('test_phase4')
        if not (phase4_teardown or report.failed):
            return
        context = {'nodeid': nodeid, 'when': report.when, 'outcome': report.outcome}
        self.observations += 1
        try:
            state = capture_state(self.include_stacks)
        except Exception as error:
            self._failure('capture', error, context)
            return
        try:
            self._write({'event': 'mirror_state', 'report': context,
                         'trigger': 'failure' if report.failed else 'phase4_teardown',
                         'monotonic': time.monotonic(),
                         'observer_thread_ident': threading.get_ident(), 'state': state})
        except Exception as error:
            self._failure('state_record_write', error, context)

    def finish(self, exitstatus, tests_collected, tests_failed):
        try:
            self._write({'event': 'observer_finished', 'pytest_exitstatus': int(exitstatus),
                         'pytest_tests_collected': tests_collected, 'pytest_tests_failed': tests_failed,
                         'observation_attempts': self.observations, 'observer_errors': len(self.errors),
                         'diagnostic_complete': not self.errors})
        except Exception as error:
            self._failure('finish_record_write', error)
        finally:
            try:
                self.stream.close()
            except Exception as error:
                self._failure('stream_close', error)
            self.closed = True


def pytest_configure(config):
    global _OBSERVER
    try:
        destination = os.environ['IG_MIRROR_STATE_RECEIPT_PATH']
        flag = os.environ.get('IG_MIRROR_STATE_INCLUDE_STACKS', '0')
        if flag not in ('0', '1'):
            raise ValueError('IG_MIRROR_STATE_INCLUDE_STACKS must be 0 or 1')
        _OBSERVER = Observer(destination, include_stacks=flag == '1')
    except Exception as error:
        raise pytest.UsageError('mirror state observer setup failed: ' + str(error)) from error


@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report):
    # Native pytest may promote a parent call after a failed subtest in its
    # ordinary terminal hook. Observe that final outcome without changing it.
    if _OBSERVER is not None:
        _OBSERVER.observe_report(report)


def pytest_sessionfinish(session, exitstatus):
    if _OBSERVER is not None:
        _OBSERVER.finish(exitstatus, session.testscollected, session.testsfailed)


def pytest_terminal_summary(terminalreporter):
    if _OBSERVER is None:
        return
    if _OBSERVER.errors:
        terminalreporter.write_line(
            'MIRROR STATE OBSERVER ERROR: %d observer errors; diagnostic receipt incomplete; pytest outcomes unchanged.'
            % len(_OBSERVER.errors), red=True)
    else:
        terminalreporter.write_line('Mirror state observer: %d observations, no observer errors.' % _OBSERVER.observations)


def pytest_unconfigure(config):
    if _OBSERVER is not None and not _OBSERVER.closed:
        _OBSERVER._failure('session_incomplete', RuntimeError('pytest sessionfinish was not observed'))
        _OBSERVER.finish(-1, None, None)

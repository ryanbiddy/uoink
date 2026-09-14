"""Unexecuted controls: actual lifecycle extension with an inert trusted port.

No backend, IPC, media decoder, model, file or process implementation is supplied.
Hooks run inline to choose the lock winner; they are not OS concurrency evidence.
"""
from dataclasses import FrozenInstanceError
import unittest

import snapshot_lifecycle as lifecycle


class InfoPort:
    def __init__(self, values):
        self.values = list(values)
        self.worker = object()
        self.cursor = object()
        self.ticket = object()
        self.protection = object()
        self.generation = object()
        self.generation_live = True
        self.backend_language = 'fr'
        self.contract = None
        self.info = None
        self.issued = None
        self.permit = None
        self.events = []
        self.get_hook = None
        self.issue_hook = None
        self.quarantine_error = None
        self.manager = None

    def acquire_read(self, key):
        self.events.append('acquire')
        return self.protection

    def start_owned_worker(self, protection, permit, profile):
        assert protection is self.protection
        self.permit = permit
        self.events.append('start')
        return self.worker

    def admit_media_request(self, worker, permit, ticket):
        assert worker is self.worker and permit is self.permit and ticket is self.ticket
        self.contract = lifecycle.MediaResultContract(permit, ticket, 16000, 32000, 4, 4, 128)
        return self.contract

    def is_issued_media_contract(self, worker, permit, contract):
        return worker is self.worker and permit is self.permit and contract is self.contract

    def begin_transcription(self, worker, contract, request):
        assert worker is self.worker and contract is self.contract
        self.request = request
        return self.cursor

    def next_segment(self, worker, cursor):
        assert worker is self.worker and cursor is self.cursor
        self.events.append('next')
        if self.values:
            return self.values.pop(0)
        # The fixed fake backend result is independent of request.language.
        with self.manager._lock:
            assert self.manager._lock._is_owned()
            self.info = lifecycle.TranscriptionInfo(self.permit, self.cursor, self.backend_language)
            self.issued = (self.worker, self.permit, self.cursor, self.generation, self.info)
        return None

    def get_transcription_info(self, worker, cursor):
        assert worker is self.worker and cursor is self.cursor
        assert not self.manager._lock._is_owned()
        self.events.append('get_info')
        if self.get_hook is not None:
            self.get_hook()
        return self.info

    def is_issued_transcription_info(self, worker, permit, cursor, info):
        assert self.manager._lock._is_owned()
        self.events.append('is_issued')
        if self.issue_hook is not None:
            self.issue_hook()
        return (self.generation_live and self.issued is not None
                and all(actual is expected for actual, expected in zip(
                    (worker, permit, cursor, self.generation, info), self.issued)))

    def cancel_transcription(self, worker, cursor):
        assert worker is self.worker and cursor is self.cursor
        self.events.append('cancel')
        return True

    def close_and_join(self, worker, permit):
        assert worker is self.worker and permit is self.permit
        self.events.append('join')
        return True

    def confirm_quiescent(self, protection, worker, permit):
        assert protection is self.protection and worker is self.worker and permit is self.permit
        return True

    def release_read(self, protection):
        assert protection is self.protection
        self.events.append('release')
        return True

    def quarantine(self, key, protection, permit, reason):
        self.events.append('quarantine')
        if self.quarantine_error is not None:
            raise self.quarantine_error
        return True


class Fixture:
    def __init__(self, *, empty=False, language=None):
        values = [] if empty else [lifecycle.Segment(0.0, 1.0, 'bonjour', ())]
        self.port = InfoPort(values)
        self.manager = lifecycle.SnapshotLifecycle(self.port)
        self.port.manager = self.manager
        self.lease = self.manager.read_lease('inert-root', 'inert-choice', 'inert-revision')
        self.lease.__enter__()
        self.permit = self.lease.begin_native_session()
        self.session = lifecycle.OwnedRuntimeFactory(self.manager).open_owned_session('inert-profile', self.permit)
        self.stream = self.session.operations().transcribe(
            lifecycle.TranscribeRequest(self.port.ticket, language=language))

    def eof(self):
        return list(self.stream)

    def finish(self):
        assert self.session.close_and_join() is True
        self.lease.confirm_native_closed()
        self.lease.__exit__(None, None, None)


class CompletionInfoContracts(unittest.TestCase):
    def test_actual_eof_issues_immutable_backend_language_inside_context(self):
        f = Fixture(language='de')
        self.assertEqual([s.text for s in f.eof()], ['bonjour'])
        next_count = f.port.events.count('next')
        info = f.stream.completion_info()
        self.assertIs(info, f.port.info)
        self.assertEqual(info.language, 'fr')
        self.assertEqual(f.port.request.language, 'de')
        self.assertIs(info.permit_identity, f.permit.identity)
        self.assertIs(info.cursor_identity, f.port.cursor)
        with self.assertRaises(FrozenInstanceError):
            info.language = 'en'
        self.assertIs(f.stream.completion_info(), info)
        self.assertEqual(f.port.events.count('next'), next_count)
        self.assertEqual(f.port.events[-4:], ['get_info', 'is_issued', 'get_info', 'is_issued'])
        f.finish()
        self.assertEqual(info.language, 'fr')  # Retained passive data is not a capability.
        with self.assertRaises(lifecycle.SessionClosed):
            f.stream.completion_info()
        self.assertIs(f.session._record.phase, lifecycle.Phase.RELEASED)

    def test_empty_natural_eof_has_no_language_fallback(self):
        f = Fixture(empty=True)
        self.assertEqual(f.eof(), [])
        self.assertIsNone(f.port.request.language)
        self.assertEqual(f.stream.completion_info().language, 'fr')
        f.finish()

    def test_incomplete_cancelled_and_closed_streams_refuse_before_metadata_io(self):
        for mode in ('incomplete', 'cancelled', 'closed_after_eof', 'closed_session'):
            with self.subTest(mode=mode):
                f = Fixture()
                expected = lifecycle.LifecycleUnavailable
                if mode == 'cancelled':
                    f.stream.close()
                    expected = lifecycle.SessionClosed
                    self.assertFalse(f.stream._completed)
                elif mode == 'closed_after_eof':
                    f.eof()
                    f.stream.close()
                    expected = lifecycle.SessionClosed
                    self.assertTrue(f.stream._completed)
                elif mode == 'closed_session':
                    f.eof()
                    f.finish()
                    expected = lifecycle.SessionClosed
                with self.assertRaises(expected):
                    f.stream.completion_info()
                self.assertNotIn('get_info', f.port.events)
                self.assertNotIn('is_issued', f.port.events)
                if mode != 'closed_session':
                    f.finish()

    def test_constructed_dataclass_is_not_issuance_authority(self):
        f = Fixture()
        f.eof()
        original = f.port.info
        f.port.info = lifecycle.TranscriptionInfo(original.permit_identity, original.cursor_identity, original.language)
        with self.assertRaises(lifecycle.LifecycleUnavailable):
            f.stream.completion_info()
        self.assertEqual(f.port.events[-3:], ['get_info', 'is_issued', 'quarantine'])
        self.assertIs(f.session._record.owner, f.session)
        self.assertIs(f.session._record.protection, f.port.protection)
        self.assertIs(f.session._record.phase, lifecycle.Phase.QUARANTINED)

    def test_invalid_passive_values_fail_before_issuance_lookup(self):
        makers = (
            lambda f: object(),
            lambda f: lifecycle.TranscriptionInfo(object(), f.port.cursor, 'fr'),
            lambda f: lifecycle.TranscriptionInfo(f.permit.identity, object(), 'fr'),
            lambda f: lifecycle.TranscriptionInfo(f.permit.identity, f.port.cursor, ''),
            lambda f: lifecycle.TranscriptionInfo(f.permit.identity, f.port.cursor, 'EN'),
            lambda f: lifecycle.TranscriptionInfo(f.permit.identity, f.port.cursor, None),
            lambda f: lifecycle.TranscriptionInfo(f.permit.identity, f.port.cursor, 'a' * 33),
        )
        for index, make in enumerate(makers):
            with self.subTest(index=index):
                f = Fixture()
                f.eof()
                f.port.info = make(f)
                with self.assertRaises(lifecycle.LifecycleUnavailable):
                    f.stream.completion_info()
                self.assertNotIn('is_issued', f.port.events)
                self.assertIs(f.session._record.phase, lifecycle.Phase.QUARANTINED)

    def test_missing_port_method_refuses_without_fallback_or_worker_call(self):
        for name in ('get_transcription_info', 'is_issued_transcription_info'):
            with self.subTest(name=name):
                f = Fixture()
                f.eof()
                setattr(f.port, name, None)
                with self.assertRaises(lifecycle.LifecycleUnavailable):
                    f.stream.completion_info()
                self.assertNotIn('get_info', f.port.events)
                self.assertIs(f.session._record.phase, lifecycle.Phase.NATIVE_RUNNING)
                f.finish()

    def test_stream_close_winning_either_port_boundary_prevents_publication(self):
        for boundary in ('get_hook', 'issue_hook'):
            with self.subTest(boundary=boundary):
                f = Fixture()
                f.eof()
                setattr(f.port, boundary, f.stream.close)
                with self.assertRaises(lifecycle.SessionClosed):
                    f.stream.completion_info()
                self.assertTrue(f.stream._info_closed)
                self.assertEqual(f.session._active, 0)
                self.assertNotIn('cancel', f.port.events)  # Natural EOF was already observed.
                f.finish()

    def test_session_close_winning_port_boundary_prevents_publication(self):
        for boundary in ('get_hook', 'issue_hook'):
            with self.subTest(boundary=boundary):
                f = Fixture()
                f.eof()
                def close_in_flight():
                    self.assertFalse(f.session.close_and_join())
                setattr(f.port, boundary, close_in_flight)
                with self.assertRaises(lifecycle.SessionClosed):
                    f.stream.completion_info()
                self.assertTrue(f.session._revoked)
                self.assertEqual(f.session._active, 0)
                self.assertIs(f.session._record.phase, lifecycle.Phase.QUARANTINED)

    def test_private_generation_revocation_or_replacement_refuses(self):
        for mode in ('revoked', 'replaced'):
            with self.subTest(mode=mode):
                f = Fixture()
                f.eof()
                def change_generation():
                    with f.manager._lock:
                        if mode == 'revoked':
                            f.port.generation_live = False
                        else:
                            f.port.generation = object()
                f.port.get_hook = change_generation
                with self.assertRaises(lifecycle.LifecycleUnavailable):
                    f.stream.completion_info()
                self.assertEqual(f.port.events.count('is_issued'), 1)
                self.assertIs(f.session._record.phase, lifecycle.Phase.QUARANTINED)

    def test_bound_identity_changes_before_publication_refuse(self):
        for target in ('permit', 'cursor', 'contract', 'owner', 'record_membership', 'worker'):
            with self.subTest(target=target):
                f = Fixture()
                f.eof()
                record = f.session._record
                def replace():
                    if target == 'permit':
                        record.permit = object()
                    elif target == 'cursor':
                        f.stream._cursor = object()
                    elif target == 'contract':
                        f.stream._contract = object()
                    elif target == 'owner':
                        record.owner = object()
                    elif target == 'record_membership':
                        f.manager._records[record.key] = object()
                    else:
                        f.session._worker = object()
                f.port.issue_hook = replace
                with self.assertRaises(lifecycle.LifecycleUnavailable):
                    f.stream.completion_info()
                self.assertEqual(f.session._active, 0)
                self.assertIs(record.phase, lifecycle.Phase.QUARANTINED)

    def test_reentrant_metadata_operation_refuses_before_second_port_call(self):
        f = Fixture()
        f.eof()
        def overlap():
            with self.assertRaises(lifecycle.SnapshotBusy):
                f.stream.completion_info()
        f.port.get_hook = overlap
        self.assertIs(f.stream.completion_info(), f.port.info)
        self.assertEqual(f.port.events.count('get_info'), 1)
        self.assertEqual(f.port.events.count('is_issued'), 1)
        self.assertEqual(f.session._active, 0)
        f.finish()

    def test_port_errors_preserve_first_error_when_quarantine_also_fails(self):
        for boundary in ('get_hook', 'issue_hook'):
            for fail_quarantine in (False, True):
                with self.subTest(boundary=boundary, fail_quarantine=fail_quarantine):
                    f = Fixture()
                    f.eof()
                    first = RuntimeError('original metadata failure')
                    def fail():
                        raise first
                    setattr(f.port, boundary, fail)
                    if fail_quarantine:
                        f.port.quarantine_error = RuntimeError('secondary quarantine failure')
                    with self.assertRaises(RuntimeError) as caught:
                        f.stream.completion_info()
                    self.assertIs(caught.exception, first)
                    self.assertEqual(f.port.events.count('quarantine'), 1)
                    self.assertEqual(f.session._active, 0)
                    self.assertIs(f.session._record.phase, lifecycle.Phase.QUARANTINED)
                    self.assertEqual(f.session._record.quarantine_persisted, not fail_quarantine)
                    if fail_quarantine:
                        self.assertTrue(first.__notes__)

    def test_interruption_uses_existing_call_quarantine_once(self):
        f = Fixture()
        f.eof()
        first = KeyboardInterrupt('inert interruption')
        def interrupt():
            raise first
        f.port.get_hook = interrupt
        with self.assertRaises(KeyboardInterrupt) as caught:
            f.stream.completion_info()
        self.assertIs(caught.exception, first)
        self.assertEqual(f.port.events.count('quarantine'), 1)
        self.assertEqual(f.session._active, 0)
        self.assertIs(f.session._record.phase, lifecycle.Phase.QUARANTINED)

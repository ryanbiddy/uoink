"""Dormant caller controls: actual reliability helper, facade and SegmentStream.

The session-provider stand-in uses the actual base lifecycle with inert kernel
methods. It does not qualify the durable adapter, a decoder, or native cleanup.
No files are created/read by these bodies; Path.is_file is an explicit fixture.
"""
from contextlib import contextmanager, ExitStack
from pathlib import Path
import unittest
from unittest.mock import patch

import asr_loading_adapter as adapter
import snapshot_lifecycle as life
import uoink_reliability as rel


def unexpected(*args, **kwargs):
    raise AssertionError("Unexpected path, model or acquisition activity")


class InertTicketSource:
    def __init__(self, fixture):
        self.fixture = fixture
        self.override = self
        self.stale = False

    def ticket_for_session(self, operations, audio):
        f = self.fixture
        assert type(operations) is life.OperationFacade and operations is f.facade
        with operations._session._manager._lock:
            operations._session._require_live()
        f.events.append("ticket_lookup")
        f.audio_argument = audio
        if self.stale:
            f.issued_permit = object()
        return f.ticket if self.override is self else self.override


class InertKernel:
    def __init__(self, fixture):
        self.f = fixture

    def acquire_read(self, key):
        self.f.events.append("acquire")
        return self.f.protection

    def start_owned_worker(self, protection, permit, profile):
        f = self.f
        assert protection is f.protection
        f.events.append("start")
        f.issued_permit = permit
        return f.worker

    def admit_media_request(self, worker, permit, ticket):
        f = self.f
        assert worker is f.worker
        f.events.append("admit")
        if ticket is not f.ticket or permit is not f.issued_permit:
            raise life.LifecycleUnavailable("Unissued or stale inert media ticket")
        f.contract = life.MediaResultContract(permit, object(), 16000, 160000, 4, 32, 1024)
        return f.contract

    def is_issued_media_contract(self, worker, permit, contract):
        f = self.f
        assert worker is f.worker
        return permit is f.issued_permit and contract is f.contract

    def begin_transcription(self, worker, contract, request):
        f = self.f
        assert worker is f.worker and contract is f.contract
        assert type(request) is life.TranscribeRequest
        f.events.append("begin")
        f.request = request
        return f.cursor

    def next_segment(self, worker, cursor):
        f = self.f
        assert worker is f.worker and cursor is f.cursor
        f.events.append("next")
        if f.iteration_error is not None and f.offset == f.fail_at:
            raise f.iteration_error
        if f.offset == len(f.segments):
            return None
        result = f.segments[f.offset]
        f.offset += 1
        return result

    def cancel_transcription(self, worker, cursor):
        f = self.f
        assert worker is f.worker and cursor is f.cursor
        f.events.append("cancel")
        if f.cancel_error is not None:
            raise f.cancel_error
        return True

    def close_and_join(self, worker, permit):
        f = self.f
        assert worker is f.worker and permit is f.owner._record.permit
        f.events.append("join")
        return f.join_result

    def confirm_quiescent(self, protection, worker, permit):
        f = self.f
        assert protection is f.protection and worker is f.worker
        f.events.append("quiet")
        return True

    def release_read(self, protection):
        assert protection is self.f.protection
        self.f.events.append("release")
        return True

    def quarantine(self, key, protection, permit, reason):
        self.f.events.append("quarantine")
        return True


class CallerFixture:
    def __init__(self):
        self.events = []
        self.ticket, self.cursor, self.worker, self.protection = (object() for _ in range(4))
        self.ticket_source = InertTicketSource(self)
        self.manager = life.SnapshotLifecycle(InertKernel(self))
        self.factory = life.OwnedRuntimeFactory(self.manager)
        self.owner = self.facade = self.request = self.contract = None
        self.retained_stream = None
        self.offset = 0
        self.iteration_error = self.cancel_error = self.entry_error = None
        self.fail_at = 0
        self.join_result = True
        self.segments = (
            life.Segment(0.0, 1.6, "The their quarterly results", (
                life.Word(0.0, 0.2, " The ", 0.98),
                life.Word(0.2, 0.5, " their, ", 0.30),
                life.Word(0.5, 1.1, "quarterly!", 0.40),
                life.Word(1.1, 1.6, "results", 0.95))),
            life.Segment(2.0, 2.6, "Xanadu", (life.Word(2.0, 2.6, "Xanadu.", 0.20),)),
        )

    @contextmanager
    def session(self, choice, *, model_root, usage):
        self.events.append("session_enter")
        assert choice == "tiny" and model_root == "generated-model-root"
        assert usage == "reliability"
        if self.entry_error is not None:
            raise self.entry_error
        with self.manager.read_lease("inert-store", choice, "inert-revision") as lease:
            permit = lease.begin_native_session()
            self.owner = self.factory.open_owned_session(object(), permit)
            self.facade = self.owner.operations()
            primary = None
            try:
                yield self.facade
            except BaseException as error:
                primary = error
                raise
            finally:
                self.events.append("session_exit")
                try:
                    if self.owner.close_and_join() is not True:
                        raise life.CleanupUnconfirmed("Inert session cleanup unconfirmed")
                    lease.confirm_native_closed()
                except BaseException as cleanup:
                    if primary is None:
                        raise
                    BaseException.add_note(primary, "Inert adapter-context cleanup: " + type(cleanup).__name__)

    @contextmanager
    def installed(self):
        normalizer = rel._words_from_segments

        def observe_normalization(stream):
            assert type(stream) is life.SegmentStream
            assert stream._session is self.owner
            assert "session_exit" not in self.events
            self.retained_stream = stream
            self.events.append("normalize")
            return normalizer(stream)

        with ExitStack() as stack:
            stack.enter_context(patch.object(rel, "_RELIABILITY_MEDIA_TICKETS", self.ticket_source))
            stack.enter_context(patch.object(adapter, "faster_whisper_session", self.session))
            stack.enter_context(patch.object(Path, "is_file", lambda path: True))
            stack.enter_context(patch.object(rel, "_load_model", unexpected))
            stack.enter_context(patch.object(rel, "_words_from_segments", observe_normalization))
            yield self

    def call(self, threshold=0.5):
        return rel.detect_unreliable_spans(
            "unused alignment text", "generated-audio-not-opened.wav", threshold,
            model_name="tiny", model_root="generated-model-root")


class ReliabilityRequestStreamContracts(unittest.TestCase):
    def test_closed_dependency_refuses_before_path_or_model_activity(self):
        with patch.object(rel, "_RELIABILITY_MEDIA_TICKETS", None), \
                patch.object(rel, "Path", unexpected), \
                patch.object(adapter, "faster_whisper_session", unexpected), \
                patch.object(rel, "_load_model", unexpected):
            with self.assertRaisesRegex(rel.ReliabilityUnavailableError, "media admission"):
                rel.detect_unreliable_spans("t", "never-inspected.wav")
            with self.assertRaisesRegex(rel.ReliabilityUnavailableError, "media admission"):
                rel._request_reliability_words("never-inspected.wav", "tiny", None)

    def test_local_only_false_refuses_before_ticket_or_session(self):
        with patch.object(rel, "_RELIABILITY_MEDIA_TICKETS", None), \
                patch.object(adapter, "faster_whisper_session", unexpected):
            for value in (False, 0, 1, None, "true"):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(rel.ReliabilityUnavailableError, "acquisition"):
                        rel._request_reliability_words("unused", "tiny", None, local_files_only=value)

    def test_actual_caller_consumes_words_inside_context_and_preserves_spans(self):
        f = CallerFixture()
        with f.installed():
            spans = f.call()
        self.assertEqual([span.to_dict() for span in spans], [
            dict(start_word_idx=1, end_word_idx=2, confidence=0.35,
                 reason="homophone_likely", text="their quarterly", start=0.2, end=1.1),
            dict(start_word_idx=4, end_word_idx=4, confidence=0.2,
                 reason="proper_noun_suspect", text="Xanadu", start=2.0, end=2.6),
        ])
        self.assertIs(f.request.media_ticket, f.ticket)
        self.assertEqual((f.request.language, f.request.word_timestamps, f.request.vad_filter,
                          f.request.beam_size, f.request.best_of), ("en", True, False, 1, 1))
        self.assertEqual(f.audio_argument, "generated-audio-not-opened.wav")
        self.assertEqual(f.events, ["session_enter", "acquire", "start", "ticket_lookup",
                                   "admit", "begin", "normalize", "next", "next", "next",
                                   "session_exit", "join", "quiet", "release"])
        self.assertTrue(f.retained_stream._exhausted)
        with self.assertRaises(life.SessionClosed):
            next(f.retained_stream)
        with self.assertRaises(life.SessionClosed):
            f.facade.transcribe(f.request)

    def test_threshold_clamping_and_passive_word_text_are_preserved(self):
        for threshold, expected in ((-10.0, []), (10.0, ["their quarterly", "Xanadu"])):
            with self.subTest(threshold=threshold):
                f = CallerFixture()
                with f.installed():
                    spans = f.call(threshold)
                self.assertEqual([span.text for span in spans], expected)

    def test_path_missing_and_custom_injected_runner_keep_their_contract(self):
        seen = []
        with patch.object(rel, "_RELIABILITY_MEDIA_TICKETS", None), \
                patch.object(Path, "is_file", lambda path: True), \
                patch.object(adapter, "faster_whisper_session", unexpected):
            spans = rel.detect_unreliable_spans("t", "injected.wav", _transcribe=lambda path:
                seen.append(path) or [{"words": [{"word": " their!", "probability": 0.25,
                                                  "start": 1.23456, "end": 2.34567}]}])
        self.assertEqual(seen, ["injected.wav"])
        self.assertEqual(spans[0].to_dict(), dict(start_word_idx=0, end_word_idx=0,
                         confidence=0.25, reason="homophone_likely", text="their",
                         start=1.235, end=2.346))
        with patch.object(Path, "is_file", lambda path: False):
            with self.assertRaises(FileNotFoundError):
                rel.detect_unreliable_spans("t", "missing.wav", _transcribe=unexpected)

    def test_filename_none_foreign_and_stale_tickets_never_begin(self):
        for fault in ("filename", "bytes", "path", "none", "foreign", "stale"):
            with self.subTest(fault=fault):
                f = CallerFixture()
                if fault == "stale":
                    f.ticket_source.stale = True
                else:
                    f.ticket_source.override = {"filename": "generated-audio-not-opened.wav",
                        "bytes": b"path", "path": Path("path"), "none": None,
                        "foreign": object()}[fault]
                with f.installed():
                    with self.assertRaises((rel.ReliabilityUnavailableError, life.LifecycleUnavailable)):
                        f.call()
                self.assertNotIn("begin", f.events)
                self.assertNotIn("next", f.events)
                self.assertIsNone(f.request)
                self.assertEqual(f.events[-3:], ["join", "quiet", "release"])

    def test_iteration_and_cancel_failures_preserve_first_error_and_custody(self):
        f = CallerFixture()
        original = ValueError("inert iteration failure")
        f.iteration_error, f.fail_at = original, 1
        f.cancel_error = RuntimeError("inert cancellation failure")
        with f.installed():
            with self.assertRaises(ValueError) as caught:
                f.call()
        self.assertIs(caught.exception, original)
        self.assertTrue(any("Owned reliability stream cleanup" in note for note in original.__notes__))
        self.assertIn("cancel", f.events)
        self.assertNotIn("release", f.events)
        self.assertIs(f.owner._record.phase, life.Phase.QUARANTINED)
        self.assertIs(f.owner._record.protection, f.protection)

    def test_normalization_failure_cancels_before_context_exit(self):
        f = CallerFixture()
        original = ValueError("inert normalization failure")
        with f.installed(), patch.object(rel, "_words_from_segments", side_effect=original):
            with self.assertRaises(ValueError) as caught:
                f.call()
        self.assertIs(caught.exception, original)
        self.assertLess(f.events.index("cancel"), f.events.index("session_exit"))
        self.assertEqual(f.events[-3:], ["join", "quiet", "release"])

    def test_context_cleanup_failure_prevents_returning_completed_spans(self):
        f = CallerFixture()
        f.join_result = False
        with f.installed():
            with self.assertRaises(life.CleanupUnconfirmed):
                f.call()
        self.assertNotIn("release", f.events)
        self.assertIs(f.owner._record.phase, life.Phase.QUARANTINED)
        self.assertTrue(f.retained_stream._exhausted)

    def test_session_entry_refusals_preserve_error_before_ticket_lookup(self):
        for original in (adapter.AssetConsentRequired("inert local assets refused"),
                         RuntimeError("inert constructor refused")):
            with self.subTest(error=type(original).__name__):
                f = CallerFixture()
                f.entry_error = original
                with f.installed():
                    with self.assertRaises(type(original)) as caught:
                        f.call()
                self.assertIs(caught.exception, original)
                self.assertEqual(f.events, ["session_enter"])

    def test_actual_adapter_remains_closed_without_release_authority(self):
        self.assertIsNone(adapter.RELEASE_AUTHORITY)
        self.assertIsNone(adapter.resolver.REAL_APPROVAL)
        with patch.object(rel, "_RELIABILITY_MEDIA_TICKETS", object()), \
                patch.object(rel, "_load_model", unexpected):
            with self.assertRaises(adapter.AdapterUnavailable):
                rel._request_reliability_words(Path("not-opened.wav"), "tiny", None)

"""Fixed driver/observer controls; no native worker or filesystem operations."""
from types import SimpleNamespace
import unittest

import generated_adapter_flow as flow
import test_windows_reservations as fixtures
from snapshot_lifecycle import Segment
from snapshot_reservations import encode_next
from win32_worker_connection import FileIdentity

KernelUnconfirmed = flow.operation_flow.adoption_flow.KernelUnconfirmed


class FixedCursor:
    def __init__(self, port, fault=None, error=None):
        self.port, self.fault, self.error = port, fault, error
        self.reads = self.closes = 0
        self.first = Segment(0.0, 0.5, "fixed generated segment", ())
    def __next__(self):
        self.reads += 1
        if self.reads == 1:
            self.port._next_index = 1
            self.port.operation_events.append("next_generated_segment")
            return self.first
        if self.fault == "second_result":
            return Segment(0.5, 1.0, "forbidden second result", ())
        if self.fault == "wire_after_cancel":
            self.port.operation_events.append("unexpected_wire_event")
        raise StopIteration
    def close(self):
        self.closes += 1
        if self.error is not None:
            raise self.error
        self.port._cursor_state = "active" if self.fault == "no_ack" else "cancelled"
        self.port.operation_events.append("cancel_generated_cursor")


class JournalCancelContracts(unittest.TestCase):
    def cursor(self, fault=None, error=None):
        port = SimpleNamespace(operation_mode="cancel", _cursor_state="active", _next_index=0,
            operation_events=["admit_generated_media", "begin_generated_transcription"])
        return port, FixedCursor(port, fault, error)

    def port(self, mode):
        f = fixtures.Fixture()
        expected = tuple((path, FileIdentity("\\\\?\\" + path, 7, bytes([20 + i]) * 16,
                         len(flow.GENERATED[name]), 1, False))
                         for i, (name, path) in enumerate(zip(flow.NAMES, flow.fixed_paths(f.snapshot.path))))
        return flow.GeneratedLifecyclePort(f.primitives, SimpleNamespace(), expected,
            "unused-generated-executable", (), f.snapshot.path, (), "1" * 64, "a" * 64,
            flow.namespace_digest(), "b" * 64, b"k" * 32, b"p" * 32, "positive", operation_mode=mode)

    def bound(self):
        f = fixtures.Fixture()
        gate, journal, head = f.clean()
        raw = bytes(f.disk.data)
        raw = journal.append_confirmed(raw, encode_next(raw, f.physical, f.semantic, "1" * 64, "RESERVED"))
        raw = journal.append_confirmed(raw, encode_next(raw, f.physical, f.semantic, "1" * 64,
                                       "WORKER_BOUND", process=[100, 200]))
        worker = object()  # Passive identity only; no worker authority is claimed by this seam.
        token = SimpleNamespace(phase="WORKER_BOUND", revoked=False, pending=None, worker=worker,
            physical=f.physical, gate=gate, journal=journal, raw=raw)
        port = SimpleNamespace(key=object(), worker=worker, _physical=f.physical,
            lifecycle=SimpleNamespace(_token=lambda key: token), reservations=SimpleNamespace(gates=f.gates))
        return f, port, token

    def test_exact_constructor_modes_preserve_drain_and_add_cancel(self):
        for mode in ("drain", "cancel"):
            with self.subTest(mode=mode):
                port = self.port(mode)
                self.assertIs(type(port), flow.GeneratedLifecyclePort)
                self.assertEqual(port.operation_mode, mode)
                self.assertIsNone(port.worker)
                self.assertIsNone(port.adapter_startup)
                self.assertIsNone(port._contender)
        class DerivedCancel(str):
            pass
        with self.assertRaisesRegex(KernelUnconfirmed, "exact_actual_adapter_cancel_mode"):
            self.port(DerivedCancel("cancel"))
        with self.assertRaisesRegex(KernelUnconfirmed, "one_actual_adapter_drain_scope"):
            self.port("interrupt")

    def test_single_segment_cancel_is_acknowledged_once(self):
        port, stream = self.cursor()
        result = flow._consume_one_then_cancel(port, stream)
        self.assertEqual(result, [stream.first])
        self.assertEqual((stream.reads, stream.closes), (2, 1))
        self.assertEqual(port._next_index, 1)
        self.assertEqual(port._cursor_state, "cancelled")
        self.assertEqual(port.operation_events, ["admit_generated_media", "begin_generated_transcription",
                         "next_generated_segment", "cancel_generated_cursor"])

    def test_cancel_close_exception_is_preserved_without_followup_read(self):
        original = RuntimeError("fixed cancellation failure")
        port, stream = self.cursor(error=original)
        with self.assertRaises(RuntimeError) as caught:
            flow._consume_one_then_cancel(port, stream)
        self.assertIs(caught.exception, original)
        self.assertEqual((stream.reads, stream.closes), (1, 1))
        self.assertEqual(port._cursor_state, "active")

    def test_missing_cancel_acknowledgement_refuses_before_followup(self):
        port, stream = self.cursor(fault="no_ack")
        with self.assertRaisesRegex(KernelUnconfirmed, "adapter_cancel_stops_before_second_generated_segment"):
            flow._consume_one_then_cancel(port, stream)
        self.assertEqual((stream.reads, stream.closes), (1, 1))

    def test_cancelled_cursor_cannot_publish_second_segment(self):
        port, stream = self.cursor(fault="second_result")
        with self.assertRaisesRegex(AssertionError, "must not yield another segment"):
            flow._consume_one_then_cancel(port, stream)
        self.assertEqual((stream.reads, stream.closes), (2, 1))

    def test_cancelled_iteration_cannot_emit_another_wire_event(self):
        port, stream = self.cursor(fault="wire_after_cancel")
        with self.assertRaisesRegex(KernelUnconfirmed, "cancelled_adapter_stream_has_no_wire_use"):
            flow._consume_one_then_cancel(port, stream)
        self.assertEqual((stream.reads, stream.closes), (2, 1))

    def test_bound_observer_returns_same_confirmed_open_owner_without_io(self):
        f, port, token = self.bound()
        before = tuple(f.primitives.api.calls)
        observed, raw, handle = flow._bound_cancel_journal(port)
        self.assertIs(observed, token)
        self.assertIs(raw, token.raw)
        self.assertIs(handle, f.gates.attempts[f.physical].handle)
        self.assertFalse(handle.closed)
        self.assertEqual(tuple(f.primitives.api.calls), before)

    def test_bound_observer_refuses_uncertain_or_retired_fields_without_io(self):
        for fault in ("phase", "revoked", "pending", "worker", "absent_none_gate", "other_gate",
                      "attempt_failure", "closed", "unconfirmed", "bytes", "revision", "poison"):
            with self.subTest(fault=fault):
                f, port, token = self.bound()
                attempt = f.gates.attempts[f.physical]
                if fault == "phase": token.phase = "CLEARED"
                elif fault == "revoked": token.revoked = True
                elif fault == "pending": token.pending = object()
                elif fault == "worker": token.worker = object()
                elif fault == "absent_none_gate":
                    del f.gates._held[f.physical]
                    token.gate = attempt.token = None
                elif fault == "other_gate": f.gates._held[f.physical] = object()
                elif fault == "attempt_failure": attempt.failure = "unconfirmed"
                elif fault == "closed": attempt.handle.closed = True
                elif fault == "unconfirmed": attempt.handle.unconfirmed = True
                elif fault == "bytes": token.journal.confirmed_bytes = b"changed"
                elif fault == "revision": token.journal._stream.write_revision += 1
                else: token.journal._stream.poisoned = True
                before = tuple(f.primitives.api.calls)
                with self.assertRaisesRegex(KernelUnconfirmed, "confirmed_bound_journal_held_during_cancel"):
                    flow._bound_cancel_journal(port)
                self.assertEqual(tuple(f.primitives.api.calls), before)

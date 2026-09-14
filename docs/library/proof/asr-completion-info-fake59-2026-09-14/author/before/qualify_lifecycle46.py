"""UNEXECUTED synthetic proposal; no Windows/kernel/model ports exist here."""
import sys

# Root's module-name diagnostic found winreg present before setup imports.
# Bind that exact built-in object; neither import nor invoke a registry API.
BASELINE_WINREG = sys.modules.get("winreg")
assert BASELINE_WINREG is not None
assert getattr(BASELINE_WINREG, "__name__", None) == "winreg"
assert getattr(getattr(BASELINE_WINREG, "__spec__", None), "origin", None) == "built-in"
assert not hasattr(BASELINE_WINREG, "__file__")
REGISTRY_NAMESPACE = dict(vars(BASELINE_WINREG))
REGISTRY_DENIALS = []


def deny_registry(*args, **kwargs):
    REGISTRY_DENIALS.append("registry_callable")
    raise AssertionError("Registry operations are prohibited")


REGISTRY_TRAPS = tuple((name, value, deny_registry) for name, value in sorted(REGISTRY_NAMESPACE.items())
                      if not name.startswith("_") and callable(value))
assert 1 <= len(REGISTRY_TRAPS) <= 64
for name, original, installed in REGISTRY_TRAPS:
    setattr(BASELINE_WINREG, name, installed)


def registry_audit(event, args):
    if event.startswith("winreg."):
        REGISTRY_DENIALS.append(event)
        raise AssertionError("Registry audit operation is prohibited")


REGISTRY_AUDIT = registry_audit
sys.addaudithook(REGISTRY_AUDIT)

import dataclasses
import enum
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import types

assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS = ("snapshot_lifecycle.py", "qualify_lifecycle.py")
READS = {os.path.normcase(os.path.join(HERE, name)) for name in INPUTS}
HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2",
         "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy", "ctypes", "subprocess", "socket", "winreg"}
assert HEAVY.intersection(name.split(".")[0] for name in sys.modules) == {"winreg"}
ALLOWED_IMPORTS = set(sys.modules) | {"snapshot_lifecycle"}
DENIALS = []
CONTENT_OPEN = True


def audit(event, args):
    allowed = True
    if event == "open":
        path, mode, flags = args
        allowed = CONTENT_OPEN and isinstance(path, str) and os.path.normcase(os.path.abspath(path)) in READS
        allowed = allowed and not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
    elif event == "import":
        allowed = args[0] in ALLOWED_IMPORTS and args[0].split(".")[0] not in HEAVY
    elif event.startswith(("os.", "socket.", "subprocess.", "ctypes.", "winreg.")):
        allowed = False
    if not allowed:
        DENIALS.append(event)
        raise AssertionError("Synthetic lifecycle boundary refused " + event)


sys.addaudithook(audit)
RAW = {}
for name in INPUTS:
    with open(os.path.join(HERE, name), "rb") as stream:
        RAW[name] = stream.read(1048577)
        assert len(RAW[name]) <= 1048576
CONTENT_OPEN = False
HASHES = {name: hashlib.sha256(raw).hexdigest() for name, raw in RAW.items()}


def deny_metadata(*args, **kwargs):
    DENIALS.append("metadata")
    raise AssertionError("No filesystem metadata is permitted")


TRAPS = []
for owner, names in ((Path, ("stat", "lstat", "resolve", "exists", "is_file", "is_dir")),
                     (os, ("stat", "lstat", "fstat", "scandir", "listdir")),
                     (os.path, ("realpath",))):
    for name in names:
        setattr(owner, name, deny_metadata)
        TRAPS.append((owner, name, deny_metadata))
TRAPS = tuple(TRAPS)


class BoundedCapture:
    def __init__(self):
        self.parts = []
        self.count = 0
        self.overflow = False

    def write(self, value):
        if type(value) is not str or len(value) > 8192 - self.count:
            self.overflow = True
            raise AssertionError("Synthetic output capture exceeded 8192 characters")
        self.parts.append(value)
        self.count += len(value)
        return len(value)

    def flush(self):
        pass


OUTPUT = sys.stdout
CAPTURE_OUT, CAPTURE_ERR = BoundedCapture(), BoundedCapture()
sys.stdout, sys.stderr = CAPTURE_OUT, CAPTURE_ERR
module = types.ModuleType("snapshot_lifecycle")
module.__file__ = os.path.join(HERE, "snapshot_lifecycle.py")
sys.modules["snapshot_lifecycle"] = module
exec(compile(RAW["snapshot_lifecycle.py"], module.__file__, "exec"), module.__dict__)
M = module


class TestInterrupt(BaseException):
    pass


class FakeKernel:
    def __init__(self):
        self.events = []
        self.actions = {}
        self.media = object()
        self.protection = object()
        self.worker = object()
        self.cursor = object()
        self.issued = []
        self.values = []
        self.contract_changes = {}

    def act(self, name, default):
        self.events.append(name)
        value = self.actions.get(name, default)
        if isinstance(value, BaseException):
            raise value
        return value() if callable(value) else value

    def acquire_read(self, key):
        return self.act("acquire", self.protection)

    def quarantine(self, key, protection, permit, reason):
        return self.act("quarantine", True)

    def release_read(self, protection):
        assert protection is self.protection
        return self.act("release", True)

    def start_owned_worker(self, protection, permit, profile):
        assert protection is self.protection
        self.permit = permit
        return self.act("start", self.worker)

    def close_and_join(self, worker, permit):
        assert worker is self.worker and permit is self.permit
        return self.act("join", True)

    def confirm_quiescent(self, protection, worker, permit):
        assert protection is self.protection and worker is self.worker and permit is self.permit
        return self.act("quiet", True)

    def admit_media_request(self, worker, permit, ticket):
        self.events.append("media")
        if worker is not self.worker or permit is not self.permit or ticket is not self.media:
            raise M.LifecycleUnavailable("Synthetic media ticket not owned")
        contract = M.MediaResultContract(permit, self.media, 16000, 160000, 8, 32, 256)
        contract = dataclasses.replace(contract, **self.contract_changes)
        self.issued.append(contract)
        return contract

    def is_issued_media_contract(self, worker, permit, contract):
        actual = worker is self.worker and permit is self.permit and any(item is contract for item in self.issued)
        return self.act("issued", actual)

    def begin_transcription(self, worker, contract, request):
        assert worker is self.worker and any(item is contract for item in self.issued)
        return self.act("begin", self.cursor)

    def next_segment(self, worker, cursor):
        assert worker is self.worker and cursor is self.cursor
        return self.act("next", self.values.pop(0) if self.values else None)

    def cancel_transcription(self, worker, cursor):
        assert worker is self.worker and cursor is self.cursor
        return self.act("cancel", True)


class Rig:
    def __init__(self):
        self.kernel = FakeKernel()
        self.manager = M.SnapshotLifecycle(self.kernel)
        self.lease = self.manager.read_lease("SYNTHETIC_STORE_NOT_A_PATH", "tiny", "a" * 40)
        self.factory = M.OwnedRuntimeFactory(self.manager)
        self.owner = None

    def enter(self):
        self.lease.__enter__()
        return self

    def start(self):
        permit = self.lease.begin_native_session()
        self.owner = self.factory.open_owned_session(object(), permit)
        return self

    def stream(self):
        return self.owner.operations().transcribe(M.TranscribeRequest(self.kernel.media))

    def finish(self):
        assert self.owner.close_and_join() is True
        self.lease.confirm_native_closed()
        assert self.lease.__exit__(None, None, None) is False

    def assert_quarantined(self):
        assert self.lease._record.phase is M.Phase.QUARANTINED
        assert self.lease._record.protection is self.kernel.protection or self.lease._record.protection is None
        assert "release" not in self.kernel.events
        refused(M.SnapshotBusy, lambda: self.manager.read_lease("SYNTHETIC_STORE_NOT_A_PATH", "tiny", "a" * 40).__enter__())
        refused(M.SnapshotBusy, lambda: self.manager.require_writer_protection("SYNTHETIC_STORE_NOT_A_PATH", "tiny", "a" * 40))


def refused(error, fn, original=None):
    try:
        fn()
    except BaseException as caught:
        assert isinstance(caught, error), (type(caught).__name__, error.__name__)
        if original is not None:
            assert caught is original
        return caught
    raise AssertionError("Expected refusal did not occur")


CASES = []


def case(name):
    def add(fn):
        CASES.append((name, fn))
        return fn
    return add


@case("real_port_absent_refuses_before_any_io")
def closed_port():
    refused(M.LifecycleUnavailable, lambda: M.SnapshotLifecycle().read_lease("not-a-path", "tiny", "a" * 40))


@case("plain_read_lease_holds_then_releases_once")
def plain_lease():
    rig = Rig().enter()
    assert rig.kernel.events == ["acquire"]
    assert rig.lease.__exit__(None, None, None) is False
    assert rig.kernel.events == ["acquire", "release"]
    refused(M.SnapshotBusy, rig.lease.__enter__)


@case("duplicate_reader_and_writer_refused_while_leased")
def duplicate_lease():
    rig = Rig().enter()
    refused(M.SnapshotBusy, lambda: rig.manager.read_lease("SYNTHETIC_STORE_NOT_A_PATH", "tiny", "a" * 40).__enter__())
    refused(M.SnapshotBusy, lambda: rig.manager.require_writer_protection("SYNTHETIC_STORE_NOT_A_PATH", "tiny", "a" * 40))
    assert rig.kernel.events == ["acquire"]
    rig.lease.__exit__(None, None, None)


@case("native_permit_is_single_use")
def single_use():
    rig = Rig().enter()
    permit = rig.lease.begin_native_session()
    refused(M.SessionClosed, rig.lease.begin_native_session)
    rig.owner = rig.factory.open_owned_session(object(), permit)
    refused(M.SessionClosed, lambda: rig.factory.open_owned_session(object(), permit))
    rig.finish()


@case("forged_or_foreign_permit_refused")
def forged():
    rig = Rig().enter()
    permit = rig.lease.begin_native_session()
    fake = M._NativePermit(rig.manager, permit.record, object())
    refused(M.SessionClosed, lambda: rig.factory.open_owned_session(object(), fake))
    other = M.OwnedRuntimeFactory(M.SnapshotLifecycle(FakeKernel()))
    refused(M.LifecycleUnavailable, lambda: other.open_owned_session(object(), permit))
    rig.owner = rig.factory.open_owned_session(object(), permit)
    rig.finish()


@case("cannot_confirm_native_closed_before_join")
def early_confirm():
    rig = Rig().enter().start()
    refused(M.CleanupUnconfirmed, rig.lease.confirm_native_closed)
    assert "release" not in rig.kernel.events
    rig.finish()


@case("unowned_native_reservation_quarantines")
def no_owner():
    rig = Rig().enter()
    rig.lease.begin_native_session()
    refused(M.CleanupUnconfirmed, lambda: rig.lease.__exit__(None, None, None))
    rig.assert_quarantined()


@case("full_stream_lifetime_then_verified_release")
def success():
    rig = Rig().enter().start()
    value = M.Segment(0.0, 1.0, "one", (M.Word(0.0, 1.0, "one", 0.9),))
    rig.kernel.values = [value]
    stream = rig.stream()
    assert next(stream) is value and "release" not in rig.kernel.events
    refused(StopIteration, lambda: next(stream))
    rig.finish()
    assert rig.kernel.events[-3:] == ["join", "quiet", "release"]


@case("retained_facade_and_stream_refuse_after_close")
def stale():
    rig = Rig().enter().start()
    facade = rig.owner.operations()
    stream = rig.stream()
    rig.finish()
    before = list(rig.kernel.events)
    refused(M.SessionClosed, lambda: facade.transcribe(M.TranscribeRequest(rig.kernel.media)))
    refused(M.SessionClosed, lambda: next(stream))
    refused(M.SessionClosed, lambda: iter(stream))
    stream.close()
    assert rig.kernel.events == before


@case("one_transcription_per_session_bounds_cursor_count")
def one_cursor():
    rig = Rig().enter().start()
    rig.stream()
    refused(M.SnapshotBusy, rig.stream)
    assert rig.kernel.events.count("begin") == 1
    rig.finish()


@case("unowned_media_ticket_refused_before_begin")
def unowned_media():
    rig = Rig().enter().start()
    refused(M.LifecycleUnavailable, lambda: rig.owner.operations().transcribe(M.TranscribeRequest(object())))
    assert "begin" not in rig.kernel.events
    rig.finish()


@case("shape_valid_but_unissued_contract_refused")
def unissued():
    rig = Rig().enter().start()
    rig.kernel.actions["issued"] = False
    refused(M.LifecycleUnavailable, rig.stream)
    assert "begin" not in rig.kernel.events
    rig.finish()


for stage in ("acquire", "start", "join", "quiet", "release"):
    for interrupt in (False, True):
        def failure(stage=stage, interrupt=interrupt):
            rig = Rig()
            original = TestInterrupt(stage) if interrupt else RuntimeError(stage)
            rig.kernel.actions[stage] = original
            if stage == "acquire":
                refused(type(original), rig.enter, original)
            elif stage == "start":
                rig.enter()
                refused(type(original), rig.start, original)
            elif stage == "release":
                rig.enter()
                refused(type(original), lambda: rig.lease.__exit__(None, None, None), original)
                assert rig.lease._record.phase is M.Phase.QUARANTINED
                assert rig.kernel.events.count("release") == 1
                return
            else:
                rig.enter().start()
                refused(type(original), rig.owner.close_and_join, original)
            rig.assert_quarantined()
        case(stage + ("_baseexception_quarantines_preserving_error" if interrupt else "_exception_quarantines_preserving_error"))(failure)


for result, label in ((False, "false"), (None, "none"), (1, "integer1")):
    def failed_join(result=result):
        rig = Rig().enter().start()
        rig.kernel.actions["join"] = result
        assert rig.owner.close_and_join() is False
        rig.assert_quarantined()
    case("nontrue_join_" + label + "_retains_protection")(failed_join)


for failure, label in ((False, "false"), (RuntimeError("cancel"), "exception"), (TestInterrupt("cancel"), "baseexception")):
    def failed_cancel(failure=failure):
        rig = Rig().enter().start()
        stream = rig.stream()
        rig.kernel.actions["cancel"] = failure
        if isinstance(failure, BaseException):
            refused(type(failure), stream.close, failure)
        else:
            refused(M.CleanupUnconfirmed, stream.close)
        rig.assert_quarantined()
        before = rig.kernel.events.count("cancel")
        stream.close()
        assert rig.kernel.events.count("cancel") == before
    case("cancel_" + label + "_quarantines_and_revokes")(failed_cancel)


@case("failed_quarantine_preserves_original_interruption")
def failed_persistence():
    rig = Rig()
    original = TestInterrupt("acquire")
    rig.kernel.actions.update(acquire=original, quarantine=RuntimeError("journal"))
    refused(TestInterrupt, rig.enter, original)
    assert rig.lease._record.quarantine_persisted is False
    assert rig.lease._record.quarantine_failure_type == "RuntimeError"
    assert original.__notes__ and "quarantine" in original.__notes__[0]
    rig.assert_quarantined()


@case("release_interrupt_preserves_existing_context_error")
def context_error():
    rig = Rig().enter()
    original = ValueError("caller")
    rig.kernel.actions["release"] = TestInterrupt("release")
    assert rig.lease.__exit__(ValueError, original, None) is False
    assert rig.lease._record.phase is M.Phase.QUARANTINED
    assert original.__notes__ and "TestInterrupt" in original.__notes__[-1]


@case("concurrent_quarantine_is_not_cleared_by_late_join")
def late_join():
    rig = Rig().enter().start()
    def join():
        refused(M.CleanupUnconfirmed, lambda: rig.lease.__exit__(None, None, None))
        return True
    rig.kernel.actions["join"] = join
    assert rig.owner.close_and_join() is False
    rig.assert_quarantined()


@case("inflight_operation_during_close_keeps_quarantine")
def in_flight():
    rig = Rig().enter().start()
    stream = rig.stream()
    def next_value():
        assert rig.owner.close_and_join() is False
        return None
    rig.kernel.actions["next"] = next_value
    refused(M.SessionClosed, lambda: next(stream))
    rig.assert_quarantined()


@case("ordinary_operation_error_can_be_cleaned_and_released")
def ordinary_error():
    rig = Rig().enter().start()
    stream = rig.stream()
    error = RuntimeError("inference")
    rig.kernel.actions["next"] = error
    refused(RuntimeError, lambda: next(stream), error)
    rig.finish()


@case("operation_interruption_quarantines_immediately")
def interrupted():
    rig = Rig().enter().start()
    stream = rig.stream()
    error = TestInterrupt("operation")
    rig.kernel.actions["next"] = error
    refused(TestInterrupt, lambda: next(stream), error)
    rig.assert_quarantined()


@case("concurrent_stream_next_refused_without_second_worker_call")
def serial_stream():
    rig = Rig().enter().start()
    stream = rig.stream()
    def nested():
        refused(M.SnapshotBusy, lambda: next(stream))
        return None
    rig.kernel.actions["next"] = nested
    refused(StopIteration, lambda: next(stream))
    assert rig.kernel.events.count("next") == 1
    rig.finish()


INVALID_OUTPUTS = (
    ("past_media_duration", [M.Segment(9.0, 11.0, "x", ())], {}),
    ("negative_time", [M.Segment(-1.0, 1.0, "x", ())], {}),
    ("nonfinite_time", [M.Segment(0.0, float("inf"), "x", ())], {}),
    ("segment_backtrack", [M.Segment(1.0, 2.0, "x", ()), M.Segment(1.5, 3.0, "y", ())], {}),
    ("word_overlap", [M.Segment(0.0, 2.0, "x", (M.Word(0.0, 1.5, "a", .9), M.Word(1.0, 2.0, "b", .8)))], {}),
    ("segment_count_budget", [M.Segment(0.0, 1.0, "x", ()), M.Segment(1.0, 2.0, "y", ())], {"max_segments": 1}),
    ("word_count_budget", [M.Segment(0.0, 2.0, "x", (M.Word(0.0, 1.0, "a", .9), M.Word(1.0, 2.0, "b", .8)))], {"max_words": 1}),
    ("aggregate_text_budget", [M.Segment(0.0, 1.0, "ab", ()), M.Segment(1.0, 2.0, "cd", ())], {"max_text_chars": 3}),
)
for name, values, changes in INVALID_OUTPUTS:
    def invalid_output(values=values, changes=changes):
        rig = Rig().enter().start()
        rig.kernel.values = list(values)
        rig.kernel.contract_changes = changes
        stream = rig.stream()
        refused(M.LifecycleUnavailable, lambda: list(stream))
        rig.assert_quarantined()
    case(name + "_refused_before_invalid_yield")(invalid_output)


@case("duration_and_aggregate_limits_accept_exact_boundary")
def exact_boundary():
    rig = Rig().enter().start()
    rig.kernel.contract_changes = {"sample_count": 16000, "max_segments": 1, "max_words": 1, "max_text_chars": 2}
    value = M.Segment(0.0, 1.0, "a", (M.Word(0.0, 1.0, "a", 1.0),))
    rig.kernel.values = [value]
    assert list(rig.stream()) == [value]
    rig.finish()


@case("session_close_during_validation_refuses_publication")
def close_during_validation():
    rig = Rig().enter().start()
    value = M.Segment(0.0, 1.0, "x", ())
    rig.kernel.values = [value]
    stream = rig.stream()
    original = M._validate_segment
    def validate(item):
        result = original(item)
        assert rig.owner.close_and_join() is True
        return result
    M._validate_segment = validate
    try:
        refused(M.SessionClosed, lambda: next(stream))
    finally:
        M._validate_segment = original
    assert (stream._segments, stream._words, stream._text_chars, stream._last_end) == (0, 0, 0, 0)
    assert rig.lease._record.phase is M.Phase.NATIVE_STOPPED
    assert "quarantine" not in rig.kernel.events
    rig.lease.confirm_native_closed()
    assert rig.lease.__exit__(None, None, None) is False


@case("stream_cancel_during_validation_refuses_publication")
def cancel_during_validation():
    rig = Rig().enter().start()
    value = M.Segment(0.0, 1.0, "x", ())
    rig.kernel.values = [value]
    stream = rig.stream()
    original = M._validate_segment
    def validate(item):
        result = original(item)
        stream.close()
        return result
    M._validate_segment = validate
    try:
        refused(M.SessionClosed, lambda: next(stream))
    finally:
        M._validate_segment = original
    assert (stream._segments, stream._words, stream._text_chars, stream._last_end) == (0, 0, 0, 0)
    assert rig.kernel.events.count("cancel") == 1
    assert rig.lease._record.phase is M.Phase.NATIVE_RUNNING
    assert "quarantine" not in rig.kernel.events
    rig.finish()


EXPECTED_CASES = (
    "real_port_absent_refuses_before_any_io",
    "plain_read_lease_holds_then_releases_once",
    "duplicate_reader_and_writer_refused_while_leased",
    "native_permit_is_single_use",
    "forged_or_foreign_permit_refused",
    "cannot_confirm_native_closed_before_join",
    "unowned_native_reservation_quarantines",
    "full_stream_lifetime_then_verified_release",
    "retained_facade_and_stream_refuse_after_close",
    "one_transcription_per_session_bounds_cursor_count",
    "unowned_media_ticket_refused_before_begin",
    "shape_valid_but_unissued_contract_refused",
    "acquire_exception_quarantines_preserving_error",
    "acquire_baseexception_quarantines_preserving_error",
    "start_exception_quarantines_preserving_error",
    "start_baseexception_quarantines_preserving_error",
    "join_exception_quarantines_preserving_error",
    "join_baseexception_quarantines_preserving_error",
    "quiet_exception_quarantines_preserving_error",
    "quiet_baseexception_quarantines_preserving_error",
    "release_exception_quarantines_preserving_error",
    "release_baseexception_quarantines_preserving_error",
    "nontrue_join_false_retains_protection",
    "nontrue_join_none_retains_protection",
    "nontrue_join_integer1_retains_protection",
    "cancel_false_quarantines_and_revokes",
    "cancel_exception_quarantines_and_revokes",
    "cancel_baseexception_quarantines_and_revokes",
    "failed_quarantine_preserves_original_interruption",
    "release_interrupt_preserves_existing_context_error",
    "concurrent_quarantine_is_not_cleared_by_late_join",
    "inflight_operation_during_close_keeps_quarantine",
    "ordinary_operation_error_can_be_cleaned_and_released",
    "operation_interruption_quarantines_immediately",
    "concurrent_stream_next_refused_without_second_worker_call",
    "past_media_duration_refused_before_invalid_yield",
    "negative_time_refused_before_invalid_yield",
    "nonfinite_time_refused_before_invalid_yield",
    "segment_backtrack_refused_before_invalid_yield",
    "word_overlap_refused_before_invalid_yield",
    "segment_count_budget_refused_before_invalid_yield",
    "word_count_budget_refused_before_invalid_yield",
    "aggregate_text_budget_refused_before_invalid_yield",
    "duration_and_aggregate_limits_accept_exact_boundary",
    "session_close_during_validation_refuses_publication",
    "stream_cancel_during_validation_refuses_publication",
)
assert tuple(name for name, _ in CASES) == EXPECTED_CASES
assert len(CASES) == 46
assert len({name for name, _ in CASES}) == len(CASES)
results = []
started = time.perf_counter()
for name, fn in CASES:
    try:
        fn()
        results.append({"name": name, "passed": True})
    except BaseException as exc:
        results.append({"name": name, "passed": False, "exception": type(exc).__name__, "message": str(exc)[:512]})
elapsed = time.perf_counter() - started
heavy = sorted((HEAVY - {"winreg"}).intersection(name.split(".")[0] for name in sys.modules))
registry_identity = (sys.modules.get("winreg") is BASELINE_WINREG
                     and getattr(getattr(BASELINE_WINREG, "__spec__", None), "origin", None) == "built-in"
                     and not hasattr(BASELINE_WINREG, "__file__"))
registry_expected = dict(REGISTRY_NAMESPACE)
for name, original, installed in REGISTRY_TRAPS:
    registry_expected[name] = installed
registry_namespace_unchanged = (set(vars(BASELINE_WINREG)) == set(registry_expected)
                                and all(vars(BASELINE_WINREG)[name] is value for name, value in registry_expected.items()))
registry_traps_installed = (bool(REGISTRY_TRAPS)
                            and registry_audit is REGISTRY_AUDIT
                            and all(getattr(BASELINE_WINREG, name, None) is installed for name, original, installed in REGISTRY_TRAPS))
traps_installed = len(TRAPS) == 12 and all(getattr(owner, name, None) is installed for owner, name, installed in TRAPS)
captures_installed = sys.stdout is CAPTURE_OUT and sys.stderr is CAPTURE_ERR
capture_valid = not CAPTURE_OUT.overflow and not CAPTURE_ERR.overflow and CAPTURE_OUT.count == CAPTURE_ERR.count == 0
valid = (not DENIALS and not heavy and traps_installed and CONTENT_OPEN is False and captures_installed and capture_valid
         and registry_identity and registry_namespace_unchanged and registry_traps_installed and not REGISTRY_DENIALS)
passed = sum(row["passed"] for row in results)
exit_code = 0 if passed == len(results) and valid else 1
payload = json.dumps({"schema": "uoink.lifecycle-state-synthetic.v1", "cases": results, "passed": passed,
                  "failed": len(results) - passed, "input_sha256": HASHES, "guard_denials": DENIALS,
                  "heavy_roots_loaded": heavy, "metadata_traps_installed": traps_installed,
                  "metadata_trap_count": len(TRAPS), "content_reads_closed": CONTENT_OPEN is False,
                  "baseline_winreg_identity_unchanged": registry_identity,
                  "registry_namespace_unchanged": registry_namespace_unchanged,
                  "registry_traps_installed": registry_traps_installed,
                  "registry_trap_names": [name for name, original, installed in REGISTRY_TRAPS],
                  "registry_trap_count": len(REGISTRY_TRAPS), "registry_denials": REGISTRY_DENIALS,
                  "captures_installed": captures_installed, "capture_valid": capture_valid,
                  "stdout_capture": "".join(CAPTURE_OUT.parts), "stderr_capture": "".join(CAPTURE_ERR.parts),
                  "guard_valid": valid, "native_exit": exit_code, "count": len(results), "skipped": 0,
                  "elapsed_seconds": elapsed, "expected_cases": EXPECTED_CASES,
                  "scope": "In-memory fake ports only; no Windows or native model qualification"}, indent=2)
assert len(payload.encode("utf-8")) <= 131072
OUTPUT.write(payload + "\n")
OUTPUT.flush()
sys.exit(exit_code)

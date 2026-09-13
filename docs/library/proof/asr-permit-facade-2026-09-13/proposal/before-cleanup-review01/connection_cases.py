"""Six unexecuted connection cases for an existing guarded source harness.

The caller supplies exact reviewed in-memory modules. No real resolver function,
asset, native package, filesystem, downloader or process is used by these cases.
"""
from contextlib import contextmanager, ExitStack
from types import SimpleNamespace

EXPECTED_CASES = (
    "exact_lease_permit_and_usage_reach_owned_startup",
    "retained_facade_refuses_after_context_close",
    "lazy_segments_require_live_owned_lease",
    "foreign_factory_refused_before_native_reservation",
    "rebind_failure_never_starts_owned_worker",
    "unconfirmed_close_keeps_snapshot_quarantined",
)


def define_cases(adapter, lifecycle, real_resolver):
    """Definitions only. The reviewed outer harness chooses when to run them."""
    assert real_resolver.REAL_APPROVAL is None
    original_resolver_functions = (real_resolver.load_manifest, real_resolver.admit_snapshot,
                                   real_resolver.bind_for_constructor)
    revision = real_resolver.MODEL_SPECS["base"][1]
    root = r"E:\uoink-inert-context-never-created"
    store = root + r"\model_assets\asr"
    snapshot = store + "\\base\\" + revision

    @contextmanager
    def patch(owner, name, value):
        old = getattr(owner, name)
        setattr(owner, name, value)
        try:
            yield
        finally:
            setattr(owner, name, old)

    def expect(error_type, callback):
        try:
            callback()
        except error_type as error:
            return error
        raise AssertionError("Expected " + error_type.__name__)

    def enter(context):
        with context:
            pass

    class InertKernel:
        def __init__(self, rig):
            self.rig = rig
            self.protection = object()
            self.worker = None
            self.quiet = False
            self.contract = None
            self.cursor = None
            self.delivered = False

        def acquire_read(self, key):
            assert (key.store_root, key.choice, key.revision) == (store, "base", revision)
            self.rig.events.append("lease.acquire")
            return self.protection

        def start_owned_worker(self, protection, permit, profile):
            record = self.rig.record()
            assert protection is self.protection and permit is record.permit
            assert record.phase is lifecycle.Phase.NATIVE_RESERVED
            assert type(profile) is adapter._OwnedASRStart
            assert profile.policy is self.rig.profile and profile.binding is self.rig.binding
            assert self.rig.events[-1] == "binding.recheck"
            self.rig.events.append("worker.start")
            self.rig.observed_permit, self.rig.startup = permit, profile
            self.worker = object()
            return self.worker

        def admit_media_request(self, worker, permit, ticket):
            assert worker is self.worker and permit is self.rig.record().permit and ticket is self.rig.ticket
            assert self.rig.record().phase is lifecycle.Phase.NATIVE_RUNNING
            self.rig.events.append("media.admit")
            self.contract = lifecycle.MediaResultContract(permit, ticket, 16000, 16000, 2, 2, 64)
            return self.contract

        def is_issued_media_contract(self, worker, permit, contract):
            return worker is self.worker and permit is self.rig.record().permit and contract is self.contract

        def begin_transcription(self, worker, contract, request):
            assert worker is self.worker and contract is self.contract and request.media_ticket is self.rig.ticket
            self.rig.events.append("transcription.begin")
            self.cursor = object()
            return self.cursor

        def next_segment(self, worker, cursor):
            assert worker is self.worker and cursor is self.cursor
            assert self.rig.record().phase is lifecycle.Phase.NATIVE_RUNNING
            self.rig.events.append("segment.next")
            if self.delivered:
                return None
            self.delivered = True
            return lifecycle.Segment(0.0, 0.25, "generated", ())

        def cancel_transcription(self, worker, cursor):
            assert worker is self.worker and cursor is self.cursor
            self.rig.events.append("segment.cancel")
            return True

        def close_and_join(self, worker, permit):
            assert worker is self.worker and permit is self.rig.record().permit
            self.rig.events.append("worker.close")
            if self.rig.fault == "close_unconfirmed":
                return False
            self.quiet = True
            return True

        def confirm_quiescent(self, protection, worker, permit):
            assert protection is self.protection and worker is self.worker and permit is self.rig.record().permit
            self.rig.events.append("worker.confirm")
            return self.quiet

        def release_read(self, protection):
            assert protection is self.protection and (self.worker is None or self.quiet)
            self.rig.events.append("lease.release")
            return True

        def quarantine(self, key, protection, permit, reason):
            assert protection is self.protection
            self.rig.events.append("lease.quarantine")
            # Inert port acknowledgement only, not durable/native evidence.
            return True

    class Rig:
        def __init__(self, fault=None):
            self.fault, self.events = fault, []
            self.kernel = InertKernel(self)
            self.manager = lifecycle.SnapshotLifecycle(self.kernel)
            self.factory = lifecycle.OwnedRuntimeFactory(self.manager)
            self.ticket = object()
            self.profile = adapter.RuntimeProfile("inert-policy", "cpu", "int8", "inert-fixed-vad", "inert-capture-vad")
            self.authority = SimpleNamespace(runtime_profile_id="inert-policy",
                manifest_approval=SimpleNamespace(manifest_sha256="d" * 64))
            self.admission = SimpleNamespace(snapshot=snapshot)
            self.binding = real_resolver.LocalBinding(snapshot, "base", revision, "d" * 64, ())
            self.startup = self.observed_permit = None

        def record(self):
            values = tuple(self.manager._records.values())
            assert len(values) == 1
            return values[0]

        def bind(self, admission):
            assert admission is self.admission and self.record().phase is lifecycle.Phase.NATIVE_RESERVED
            assert real_resolver.REAL_APPROVAL is None
            self.events.append("binding.recheck")
            if self.fault == "rebind":
                raise real_resolver.AdmissionRefusal("inert rebind refused")
            return self.binding

        @contextmanager
        def leased(self, choice, caller_root, *, root_kind, consent_given):
            assert choice == "base" and type(consent_given) is bool
            assert root_kind in ("transcription", "reliability")
            # This visible test seam bypasses only real authority/file admission.
            # It enters the unchanged concrete lifecycle and changes no resolver
            # REAL_APPROVAL or real resolver method.
            with self.manager.read_lease(store, choice, revision) as lease:
                yield self.authority, lease, self.admission

        def __enter__(self):
            self.stack = ExitStack()
            replacements = {
                "_leased_admission": self.leased,
                "resolver": SimpleNamespace(LocalBinding=real_resolver.LocalBinding, bind_for_constructor=self.bind),
                "RUNTIME_PROFILE": self.profile, "SNAPSHOT_LIFECYCLE": self.manager, "RUNTIME_FACTORY": self.factory,
            }
            for name, value in replacements.items():
                self.stack.enter_context(patch(adapter, name, value))
            return self

        def __exit__(self, *args):
            self.stack.close()
            assert real_resolver.REAL_APPROVAL is None
            assert (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor) == original_resolver_functions
            return False

        def context(self, usage="reliability"):
            return adapter._model_session("base", root, usage=usage,
                root_kind="transcription" if usage == "whisperx" else "reliability", consent_given=False)

    def exact_lease_permit_and_usage_reach_owned_startup():
        for usage in ("whisperx", "reliability", "capture_fallback"):
            with Rig() as rig:
                with rig.context(usage) as facade:
                    assert type(facade) is lifecycle.OperationFacade
                    assert facade._session._record is rig.record()
                    assert rig.startup.usage == usage and rig.startup.binding is rig.binding
                    assert rig.observed_permit is rig.record().permit
                    assert rig.events == ["lease.acquire", "binding.recheck", "worker.start"]
                    assert not any(hasattr(facade, name) for name in ("whisperx_load_model", "faster_whisper_model", "make_fixed_vad"))
                assert rig.record().phase is lifecycle.Phase.RELEASED
                assert rig.events[-3:] == ["worker.close", "worker.confirm", "lease.release"]

    def retained_facade_refuses_after_context_close():
        with Rig() as rig:
            with rig.context() as facade:
                assert type(facade) is lifecycle.OperationFacade
            before = tuple(rig.events)
            expect(lifecycle.SessionClosed, lambda: facade.transcribe(lifecycle.TranscribeRequest(rig.ticket)))
            assert tuple(rig.events) == before and rig.record().phase is lifecycle.Phase.RELEASED

    def lazy_segments_require_live_owned_lease():
        with Rig() as rig:
            with rig.context() as facade:
                stream = facade.transcribe(lifecycle.TranscribeRequest(rig.ticket))
                assert next(stream) == lifecycle.Segment(0.0, 0.25, "generated", ())
                assert rig.record().phase is lifecycle.Phase.NATIVE_RUNNING and "lease.release" not in rig.events
            before = tuple(rig.events)
            expect(lifecycle.SessionClosed, lambda: next(stream))
            assert tuple(rig.events) == before and rig.record().phase is lifecycle.Phase.RELEASED

    def foreign_factory_refused_before_native_reservation():
        with Rig() as rig:
            foreign = lifecycle.OwnedRuntimeFactory(lifecycle.SnapshotLifecycle(object()))
            with patch(adapter, "RUNTIME_FACTORY", foreign):
                expect(adapter.AdapterUnavailable, lambda: enter(rig.context()))
            assert rig.record().permit is None and rig.record().phase is lifecycle.Phase.RELEASED
            assert rig.events == ["lease.acquire", "lease.release"]

    def rebind_failure_never_starts_owned_worker():
        with Rig("rebind") as rig:
            expect(adapter.NativeCleanupUnconfirmed, lambda: enter(rig.context()))
            assert rig.record().phase is lifecycle.Phase.QUARANTINED and rig.kernel.worker is None
            assert "binding.recheck" in rig.events and "worker.start" not in rig.events
            assert "lease.quarantine" in rig.events and "lease.release" not in rig.events

    def unconfirmed_close_keeps_snapshot_quarantined():
        with Rig("close_unconfirmed") as rig:
            expect(adapter.NativeCleanupUnconfirmed, lambda: enter(rig.context()))
            assert rig.record().phase is lifecycle.Phase.QUARANTINED
            assert "worker.close" in rig.events and "lease.quarantine" in rig.events
            assert "worker.confirm" not in rig.events and "lease.release" not in rig.events

    functions = (exact_lease_permit_and_usage_reach_owned_startup, retained_facade_refuses_after_context_close,
        lazy_segments_require_live_owned_lease, foreign_factory_refused_before_native_reservation,
        rebind_failure_never_starts_owned_worker, unconfirmed_close_keeps_snapshot_quarantined)
    assert tuple(function.__name__ for function in functions) == EXPECTED_CASES
    return tuple(zip(EXPECTED_CASES, functions))

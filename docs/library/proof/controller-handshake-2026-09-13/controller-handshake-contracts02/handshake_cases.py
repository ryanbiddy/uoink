"""Eight proposed handshake contracts using real local lifecycle, fake kernel."""
M = sys.modules["snapshot_lifecycle"]
P = sys.modules["owned_generation_protocol"]
CASES = []


def case(name):
    def decorate(function):
        CASES.append((name, function))
        return function
    return decorate


def refused(function, reason):
    try:
        function()
    except P.ProtocolRefusal as error:
        assert reason in str(error)
        return error
    raise AssertionError("Expected ControllerHandshake refusal")


class FakeKernel:
    def __init__(self):
        self.protection = object()
        self.before_challenge = self.after_ready = None
        self.released = self.quarantined = False

    def acquire_read(self, key):
        self.key = key
        return self.protection

    def start_owned_worker(self, protection, permit, profile):
        assert protection is self.protection
        record = self.manager._records[self.key]
        assert record.phase is M.Phase.NATIVE_RESERVED and record.permit is permit
        self.worker = types.SimpleNamespace(read_set=protection, assigned=True, unconfirmed=False,
            shutdown_started=False, creation_time=123)
        self.primitives = types.SimpleNamespace(workers=[self.worker])
        binding = P.GenerationBinding("1" * 64, "2" * 64, "3" * 64, "4" * 64, 123)
        self.controller = P.GenerationChannel(binding, b"x" * 32, "controller")
        self.peer = P.GenerationChannel(binding, b"x" * 32, "worker")
        self.handshake = P.ControllerHandshake(self.controller, record.owner, permit, self.primitives, self.worker)
        if self.before_challenge:
            self.before_challenge(self, record)
        operation, payload = self.peer.decode(self.handshake.challenge())
        assert operation == "challenge" and payload == {"generation": "1" * 64, "namespace_sha256": "3" * 64}
        self.ready = self.peer.encode("ready", payload)
        self.handshake.accept_ready(self.ready)
        if self.after_ready:
            self.after_ready(self, record)
        return self.worker

    def close_and_join(self, worker, permit):
        assert worker is self.worker and permit is self.handshake._permit
        return True

    def confirm_quiescent(self, protection, worker, permit):
        assert protection is self.protection and worker is self.worker and permit is self.handshake._permit
        return True

    def release_read(self, protection):
        assert protection is self.protection
        self.released = True
        return True

    def quarantine(self, key, protection, permit, reason):
        self.quarantined = True
        return True  # Explicit fake port, not a durable or kernel claim.


class Rig:
    def __init__(self):
        self.kernel = FakeKernel()
        self.manager = M.SnapshotLifecycle(self.kernel)
        self.kernel.manager = self.manager
        self.lease = self.manager.read_lease("synthetic-root", "generated", "f" * 64).__enter__()
        self.permit = self.lease.begin_native_session()

    def open(self):
        self.session = M.OwnedRuntimeFactory(self.manager).open_owned_session(object(), self.permit)
        return self

    def finish(self):
        assert self.session.close_and_join() is True
        self.lease.confirm_native_closed()
        assert self.lease.__exit__(None, None, None) is False
        assert self.lease._record.phase is M.Phase.RELEASED and self.kernel.released


@case("handshake_real_lifecycle_reserved_ready_running_begin")
def connected():
    rig = Rig().open()
    assert rig.lease._record.owner is rig.session and rig.lease._record.permit is rig.permit.identity
    assert rig.lease._record.phase is M.Phase.NATIVE_RUNNING
    frame = rig.session._call(lambda worker: rig.kernel.handshake.begin())
    assert rig.kernel.peer.decode(frame) == ("begin", {"manifest_sha256": "2" * 64})
    assert rig.kernel.handshake._begun and rig.session._active == 0
    rig.finish()


@case("handshake_begin_during_reserved_startup_refused")
def begin_early():
    rig = Rig()
    def before(kernel, record):
        refused(kernel.handshake.begin, "controller_phase")
        assert kernel.controller._send_sequence == 0
    rig.kernel.before_challenge = before
    rig.open()
    assert rig.kernel.handshake._ready and not rig.kernel.handshake._begun
    rig.finish()


@case("handshake_foreign_local_permit_refused_before_frame")
def foreign_permit():
    rig = Rig()
    rig.kernel.before_challenge = lambda kernel, record: setattr(kernel.handshake, "_permit", object())
    refused(rig.open, "controller_permit_identity")
    assert rig.kernel.controller._send_sequence == 0 and rig.kernel.quarantined


@case("handshake_unregistered_worker_refused_before_frame")
def foreign_worker():
    rig = Rig()
    rig.kernel.before_challenge = lambda kernel, record: kernel.primitives.workers.clear()
    refused(rig.open, "owned_process_generation_binding")
    assert rig.kernel.controller._send_sequence == 0 and rig.kernel.quarantined


@case("handshake_wrong_lifecycle_phase_refused_before_frame")
def wrong_phase():
    rig = Rig()
    rig.kernel.before_challenge = lambda kernel, record: setattr(record, "phase", M.Phase.PROTECTED)
    refused(rig.open, "controller_phase")
    assert rig.kernel.controller._send_sequence == 0 and rig.kernel.quarantined


@case("handshake_substituted_registry_record_refused")
def wrong_record():
    rig = Rig()
    def replace(kernel, record):
        kernel.manager._records[record.key] = dataclasses.replace(record)
    rig.kernel.before_challenge = replace
    refused(rig.open, "controller_owner_identity")
    assert rig.kernel.controller._send_sequence == 0 and rig.kernel.quarantined


@case("handshake_repeated_ready_refused_while_reserved")
def ready_twice():
    rig = Rig()
    def again(kernel, record):
        refused(lambda: kernel.handshake.accept_ready(kernel.ready), "ready_order")
        assert kernel.controller._receive_sequence == 1
    rig.kernel.after_ready = again
    rig.open()
    rig.finish()


@case("handshake_begin_after_owned_session_close_refused")
def closed():
    rig = Rig().open()
    assert rig.session.close_and_join() is True
    refused(rig.kernel.handshake.begin, "controller_permit_identity")
    assert rig.kernel.controller._send_sequence == 1 and not rig.kernel.handshake._begun
    rig.lease.confirm_native_closed()
    rig.lease.__exit__(None, None, None)
    assert rig.kernel.released

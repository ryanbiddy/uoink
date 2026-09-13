"""Generated lifecycle connection; no native implementation or execution.

The existing lifecycle source remains byte-identical. This connection requires
a trusted fixed kernel with create_suspended/resume/stop_start_failure and
completion_evidence methods; it cannot adapt a combined create+resume call.
"""
from snapshot_lifecycle import (SnapshotLifecycle, SnapshotKey, OwnedSession,
    _NativePermit, Phase, LifecycleUnavailable, SessionClosed, CleanupUnconfirmed, SnapshotBusy)
from snapshot_reservations import ReservationService, ReservationRefused


class DurableSnapshotLifecycle(SnapshotLifecycle):
    def __init__(self, kernel, reservations, binding_lookup):
        if kernel is None or type(reservations) is not ReservationService:
            raise LifecycleUnavailable("Generated owned kernel and reservation service required")
        self._reservations = reservations
        self._bindings = binding_lookup
        self._tokens = {}
        self._delegate = kernel
        super().__init__(_DurableKernel(self))

    def read_lease(self, store_root, choice, revision):
        inner = super().read_lease(store_root, choice, revision)
        # Binding lookup is a trusted bootstrap registry, not a filesystem or
        # caller profile. It supplies physical identity + approved semantics.
        binding = self._bindings(store_root, choice, revision)
        return _DurableLease(self, inner, binding)

    def _token(self, key):
        token = self._tokens.get(key)
        if token is None:
            raise LifecycleUnavailable("Durable reservation is absent")
        return token

    def _flush_quarantine(self, key, original=None):
        token = self._token(key)
        try:
            with self._lock:
                pending = self._kernel._pending_quarantine.pop(key, None)
            if pending is not None:
                self._delegate.quarantine(key, *pending)
            persisted = self._reservations.quarantine(token, "operation_failed")
            with self._lock:
                record = self._records.get(key)
                if record is not None:
                    record.quarantine_persisted = persisted is True
                    record.quarantine_failure_type = None if persisted is True else "PendingTransition"
            if persisted is not True:
                raise CleanupUnconfirmed("Quarantine append is pending or unconfirmed")
        except BaseException as error:
            if original is None:
                raise
            original.add_note("Durable quarantine remains unconfirmed: " + type(error).__name__)


class _DurableLease:
    def __init__(self, manager, inner, binding):
        self.manager, self.inner, self.binding = manager, inner, binding
        self.token = None
        self._finalization_started = False

    def __enter__(self):
        manager = self.manager
        with manager._lock:
            if self.inner._entered or self.inner._exited:
                raise SnapshotBusy("Lease object cannot be reused")
        physical, semantic, generation, creation = self.binding
        # Persistence is outside the lifecycle lock and precedes member guard
        # acquisition and all worker creation. Failed begin retains its gate.
        self.token = manager._reservations.begin(physical, semantic, generation, creation)
        with manager._lock:
            manager._tokens[self.inner._key] = self.token
        try:
            self.inner.__enter__()
            return self
        except BaseException as original:
            manager._flush_quarantine(self.inner._key, original)
            raise

    def begin_native_session(self):
        return self.inner.begin_native_session()

    def confirm_native_closed(self):
        return self.inner.confirm_native_closed()

    def __exit__(self, exc_type, exc_value, traceback):
        manager, key = self.manager, self.inner._key
        with manager._lock:
            if self._finalization_started:
                return False
            self._finalization_started = True
        try:
            result = self.inner.__exit__(exc_type, exc_value, traceback)
        except BaseException as original:
            manager._flush_quarantine(key, original)
            raise
        with manager._lock:
            record = self.inner._record
            released = record is not None and record.phase is Phase.RELEASED
        if not released:
            manager._flush_quarantine(key, exc_value)
            return result
        try:
            # The fixed kernel retains its completed teardown observations;
            # this is not a journal/process-field-to-capability conversion.
            evidence = manager._delegate.completion_evidence(self.token.worker)
            manager._reservations.complete(self.token, evidence)
        except BaseException as original:
            with manager._lock:
                record.phase = Phase.QUARANTINED
                record.reason = "Final durable completion was not confirmed"
                record.quarantine_persisted = False
                record.quarantine_failure_type = type(original).__name__
            if isinstance(exc_value, BaseException):
                exc_value.add_note("Final durable completion failed: " + type(original).__name__)
                return False
            raise
        return result


class DurableOwnedRuntimeFactory:
    def __init__(self, lifecycle):
        if type(lifecycle) is not DurableSnapshotLifecycle:
            raise LifecycleUnavailable("Exact durable lifecycle required")
        self.manager = lifecycle

    def open_owned_session(self, profile, permit):
        manager = self.manager
        if type(permit) is not _NativePermit or permit.manager is not manager:
            raise LifecycleUnavailable("The active lease's native permit is required")
        with manager._lock:
            record = permit.record
            if (manager._records.get(record.key) is not record or record.permit is not permit.identity
                    or record.phase is not Phase.NATIVE_RESERVED or record.owner is not None):
                raise SessionClosed("Native permit is stale or already consumed")
            owner = OwnedSession(manager, record)
            record.owner = owner
        worker = None
        try:
            # Pending start remains NATIVE_RESERVED with its owner set. Other
            # entrants cannot start it; lease exit can revoke without waiting
            # for the journal flush or suspended-process preparation.
            worker = manager._kernel.start_owned_worker(record.protection, permit.identity, profile)
            with manager._lock:
                if record.phase is not Phase.NATIVE_RESERVED or owner._revoked:
                    raise SessionClosed("Worker start was revoked before publication")
                owner._worker = worker
                record.phase = Phase.NATIVE_RUNNING
                return owner
        except BaseException as original:
            if worker is not None:
                # A resumed worker may lose publication to lease revocation.
                # owner._worker is still None here; retain/use this exact owner.
                manager._kernel.stop_unpublished(worker, permit.identity, original)
            with manager._lock:
                manager._quarantine_preserving(record, "Owned worker start did not complete", original)
            manager._flush_quarantine(record.key, original)
            raise


class _DurableKernel:
    def __init__(self, manager):
        self.manager = manager
        self._starts = {}
        self._pending_quarantine = {}

    def acquire_read(self, key):
        self.manager._token(key)
        return self.manager._delegate.acquire_read(key)

    def _record(self, protection, permit):
        with self.manager._lock:
            matches = [r for r in self.manager._records.values()
                       if r.protection is protection and r.permit is permit and r.owner is not None]
            if len(matches) != 1:
                raise LifecycleUnavailable("Exact current owned record required")
            return matches[0]

    def start_owned_worker(self, protection, permit, profile):
        manager = self.manager
        record = self._record(protection, permit)
        token = manager._token(record.key)
        worker = None
        try:
            worker = manager._delegate.create_suspended(protection, permit, profile)
            if worker is None:
                raise LifecycleUnavailable("Suspended worker was not returned")
            self._starts[permit] = worker
            manager._reservations.bind_worker(token, worker)
            # Shared lock order is manager state, then reservation state. The
            # fixed resume callback must be nonblocking; no file I/O here.
            with manager._lock:
                if record.phase is not Phase.NATIVE_RESERVED or record.owner._revoked:
                    raise SessionClosed("Start revoked before resume")
                manager._reservations.resume_owned(token, manager._delegate.resume)
            return worker
        except BaseException as original:
            try:
                manager._reservations.revoke_local(token)
            except BaseException as revoke_error:
                original.add_note("Local revocation raised: " + type(revoke_error).__name__)
            if worker is not None:
                self.stop_unpublished(worker, permit, original)
            raise

    def stop_unpublished(self, worker, permit, original):
        """Retained identity, not PID data or owner publication, authorizes stop."""
        try:
            if worker is None or self._starts.get(permit) is not worker:
                raise LifecycleUnavailable("Exact retained unpublished worker required")
            if self.manager._delegate.stop_start_failure(worker) is not True:
                original.add_note("Exact worker stop remains unconfirmed")
        except BaseException as stop_error:
            original.add_note("Exact worker stop raised: " + type(stop_error).__name__)

    def quarantine(self, key, protection, permit, reason):
        # The base calls here with its state lock held. Revoke without file I/O;
        # its false result accurately marks durable quarantine as pending.
        self.manager._reservations.revoke_local(self.manager._token(key))
        self._pending_quarantine[key] = (protection, permit, reason)
        return False

    def release_read(self, protection):
        return self.manager._delegate.release_read(protection)

    def close_and_join(self, worker, permit):
        return self.manager._delegate.close_and_join(worker, permit)

    def confirm_quiescent(self, protection, worker, permit):
        return self.manager._delegate.confirm_quiescent(protection, worker, permit)

    def admit_media_request(self, worker, permit, media):
        return self.manager._delegate.admit_media_request(worker, permit, media)

    def is_issued_media_contract(self, worker, permit, contract):
        return self.manager._delegate.is_issued_media_contract(worker, permit, contract)

    def begin_transcription(self, worker, contract, request):
        return self.manager._delegate.begin_transcription(worker, contract, request)

    def next_segment(self, worker, cursor):
        return self.manager._delegate.next_segment(worker, cursor)

    def cancel_transcription(self, worker, cursor):
        return self.manager._delegate.cancel_transcription(worker, cursor)

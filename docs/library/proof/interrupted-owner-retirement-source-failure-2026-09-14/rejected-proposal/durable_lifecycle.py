"""Generated lifecycle connection; no native implementation or execution.

The existing lifecycle source remains byte-identical. This connection requires
a trusted fixed kernel with create_suspended/resume/stop_start_failure and
completion_evidence methods; it cannot adapt a combined create+resume call.
"""
from snapshot_lifecycle import (SnapshotLifecycle, SnapshotKey, OwnedSession,
    _NativePermit, Phase, LifecycleUnavailable, SessionClosed, CleanupUnconfirmed, SnapshotBusy)
from snapshot_reservations import ReservationService, ReservationRefused, Reservation, decode_journal
from dataclasses import dataclass


@dataclass(frozen=True)
class _RetiredRecovery:
    manager: object
    record: object
    owner: object
    token: object
    service: object
    gates: object
    worker: object
    permit: object
    gate: object
    journal: object
    raw: bytes
    head: str
    revision: int


@dataclass(frozen=True)
class _InterruptedRetirement:
    manager: object
    record: object
    owner: object
    token: object
    service: object
    gates: object
    worker: object
    permit: object
    protection: object
    gate: object
    journal: object
    raw: bytes
    head: str
    revision: int
    delegate: object


class DurableSnapshotLifecycle(SnapshotLifecycle):
    def __init__(self, kernel, reservations, binding_lookup):
        if kernel is None or type(reservations) is not ReservationService:
            raise LifecycleUnavailable("Generated owned kernel and reservation service required")
        self._reservations = reservations
        self._bindings = binding_lookup
        self._tokens = {}
        self._entering = {}
        self._retired_recoveries = {}
        self._interrupted_retirements = {}
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

    def reconcile_retired_owner(self, owner):
        """Private live-object recovery after verified retirement, never restart.

        The fixed service observer must inspect the exact retained dead worker
        and retired guards before any clear write. No caller supplies evidence.
        This manager reserves publication only; its lock is not an OS gate.
        """
        if (type(self) is not DurableSnapshotLifecycle or type(owner) is not OwnedSession
                or owner._manager is not self):
            raise LifecycleUnavailable("Exact retained owner and manager required")
        with self._lock:
            record = owner._record
            key = record.key
            if (self._records.get(key) is not record or record.owner is not owner
                    or key in self._entering or key in self._retired_recoveries
                    or key in self._interrupted_retirements
                    or record.phase is not Phase.QUARANTINED or record.protection is not None
                    or record.permit is None or owner._worker is None
                    or owner._revoked is not True or owner._closed_verified is not True
                    or owner._closing is not True or type(owner._active) is not int or owner._active != 0):
                raise CleanupUnconfirmed("Current already-retired quarantined owner required")
            service, token = self._reservations, self._tokens.get(key)
            if (type(service) is not ReservationService or type(token) is not Reservation
                    or token.service is not service or token.worker is not owner._worker):
                raise LifecycleUnavailable("Exact retained reservation connection required")
            with token._lock:
                service._owned(token)
                if (token.phase != "QUARANTINED" or token.revoked is not True
                        or token.pending is not None or token.journal is None):
                    raise CleanupUnconfirmed("Quarantined idle reservation required")
                rows, head = decode_journal(token.raw)
                if (rows[-1]["phase"] not in ("WORKER_BOUND", "QUARANTINED")
                        or rows[-1]["generation"] != token.generation or rows[-1]["process"] is None):
                    raise CleanupUnconfirmed("Retained bound-worker journal required")
                attempt = _RetiredRecovery(self, record, owner, token, service, service.gates,
                    owner._worker, record.permit, token.gate, token.journal, token.raw, head, token.revision)
                self._retired_recoveries[key] = attempt
        try:
            # Reconciliation, including journal I/O and native journal close,
            # runs outside the manager lock. The old owner stays revoked.
            if service.reconcile_live(token) is not True:
                raise CleanupUnconfirmed("Retired reservation reconciliation was not confirmed")
            with self._lock:
                with token._lock:
                    after, head = decode_journal(token.raw)
                    if (self._retired_recoveries.get(key) is not attempt
                            or self._records.get(key) is not record or record.owner is not owner
                            or owner._record is not record or owner._manager is not self
                            or self._tokens.get(key) is not token or self._reservations is not service
                            or service.gates is not attempt.gates or token.service is not service
                            or token.worker is not attempt.worker or owner._worker is not attempt.worker
                            or record.permit is not attempt.permit or token.gate is not attempt.gate
                            or token.journal is not attempt.journal or token.revision != attempt.revision
                            or record.phase is not Phase.QUARANTINED or record.protection is not None
                            or owner._revoked is not True or owner._closed_verified is not True
                            or owner._closing is not True or type(owner._active) is not int or owner._active != 0
                            or token.revoked is not True or token.phase != "CLEARED" or token.pending is not None
                            or token.gate in service._live or token.physical in attempt.gates._held
                            or attempt.gates._known_clean.get(token.physical) != head
                            or not token.raw.startswith(attempt.raw) or token.raw == attempt.raw
                            or after[-1]["phase"] != "CLEARED" or after[-1]["previous"] != attempt.head):
                        raise CleanupUnconfirmed("Retired recovery changed before manager publication")
                    record.phase = Phase.RELEASED
                    record.reason = "Explicit retired-owner reconciliation confirmed"
                    record.quarantine_failure_type = None
                    # No authority is restored to this owner, permit or facade.
                    return True
        except BaseException as original:
            with self._lock:
                owner._revoked = True
                if self._records.get(key) is record and record.owner is owner:
                    record.phase = Phase.QUARANTINED
                    record.reason = "Retired-owner reconciliation was not published"
                    record.quarantine_failure_type = type(original).__name__
            # Preserve the service's actual gate/poison state, including a gate
            # already released before a later manager-publication refusal.
            raise
        finally:
            with self._lock:
                if self._retired_recoveries.get(key) is attempt:
                    del self._retired_recoveries[key]

    def retire_and_reconcile_interrupted_owner(self, owner):
        """Private manager-owned retirement and reconciliation after interruption.

        The operation was interrupted while running; the owner was quarantined.
        Wait for process exit and empty job, close endpoint, worker and read-set
        handles, and record a distinct witness before service reconciliation.
        """
        if (type(self) is not DurableSnapshotLifecycle or type(owner) is not OwnedSession
                or owner._manager is not self):
            raise LifecycleUnavailable("Exact retained owner and manager required")
        with self._lock:
            record = owner._record
            if record is None:
                raise CleanupUnconfirmed("Current quarantined owner required")
            key = record.key
            if (self._records.get(key) is not record or record.owner is not owner
                    or owner._record is not record or owner._manager is not self
                    or key in self._entering or key in self._retired_recoveries
                    or key in self._interrupted_retirements
                    or record.phase is not Phase.QUARANTINED
                    or record.protection is None or record.permit is None
                    or owner._worker is None or owner._revoked is not True
                    or owner._closed_verified is True or owner._closing is True
                    or type(owner._active) is not int or owner._active != 0):
                raise CleanupUnconfirmed("Current unretired quarantined owner required")
            service, token = self._reservations, self._tokens.get(key)
            if (type(service) is not ReservationService or type(token) is not Reservation
                    or token.service is not service or token.worker is not owner._worker):
                raise LifecycleUnavailable("Exact retained reservation connection required")
            delegate = self._delegate
            if delegate is None:
                raise LifecycleUnavailable("Exact retained delegate required")
            with token._lock:
                service._owned(token)
                if (token.phase != "QUARANTINED" or token.revoked is not True
                        or token.pending is not None or token.journal is None):
                    raise CleanupUnconfirmed("Quarantined idle reservation required")
                rows, head = decode_journal(token.raw)
                if (len(rows) != 4 or [r["phase"] for r in rows] != ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED"]
                        or rows[-1]["generation"] != token.generation or rows[-1]["process"] is None):
                    raise CleanupUnconfirmed("Retained quarantined four-frame journal required")
                pair = getattr(delegate, "pair", None)
                if pair is None or pair.active or pair.operations:
                    raise CleanupUnconfirmed("Idle exact pipe pair with empty I/O required")
                if pair.closed or pair.unconfirmed:
                    raise CleanupUnconfirmed("Retained unclosed confirmed pipe pair required")
                primitives = getattr(delegate, "primitives", None)
                if primitives is None:
                    raise CleanupUnconfirmed("Primitives owner required")
                worker = owner._worker
                protection = record.protection
                handles_to_check = [pair.server, worker.process, worker.thread, worker.job, *protection.members]
                if pair.client is not None and not pair.client.closed:
                    handles_to_check.append(pair.client)
                for h in handles_to_check:
                    if (h is None or not any(item is h for item in primitives.handles)
                            or h.closed or h.unconfirmed):
                        raise CleanupUnconfirmed("Retained confirmed live handle required")
                attempt = _InterruptedRetirement(
                    self, record, owner, token, service, service.gates,
                    owner._worker, record.permit, record.protection,
                    token.gate, token.journal, token.raw, head, token.revision,
                    delegate
                )
                self._interrupted_retirements[key] = attempt
        try:
            # Waits, closure and journal I/O run outside the manager lock.
            exit_obs = delegate.retire_interrupted_worker(attempt)
            with self._lock:
                if (self._interrupted_retirements.get(key) is not attempt
                        or self._records.get(key) is not record or record.owner is not owner
                        or owner._record is not record or owner._manager is not self
                        or self._tokens.get(key) is not token
                        or record.phase is not Phase.QUARANTINED or record.protection is not attempt.protection
                        or owner._revoked is not True or owner._closed_verified is True
                        or owner._closing is True or type(owner._active) is not int or owner._active != 0):
                    raise CleanupUnconfirmed("Interrupted attempt state changed before retirement publication")
                owner._closed_verified = True
                owner._closing = True
                record.protection = None
            if service.reconcile_live(token) is not True:
                raise CleanupUnconfirmed("Interrupted reservation reconciliation was not confirmed")
            with self._lock:
                with token._lock:
                    after, head = decode_journal(token.raw)
                    if (self._interrupted_retirements.get(key) is not attempt
                            or self._records.get(key) is not record or record.owner is not owner
                            or owner._record is not record or owner._manager is not self
                            or self._tokens.get(key) is not token or self._reservations is not service
                            or service.gates is not attempt.gates or token.service is not service
                            or token.worker is not attempt.worker or owner._worker is not attempt.worker
                            or record.permit is not attempt.permit or token.gate is not attempt.gate
                            or token.journal is not attempt.journal or token.revision != attempt.revision
                            or record.phase is not Phase.QUARANTINED or record.protection is not None
                            or owner._revoked is not True or owner._closed_verified is not True
                            or owner._closing is not True or type(owner._active) is not int or owner._active != 0
                            or token.revoked is not True or token.phase != "CLEARED" or token.pending is not None
                            or token.gate in service._live or token.physical in attempt.gates._held
                            or attempt.gates._known_clean.get(token.physical) != head
                            or not token.raw.startswith(attempt.raw) or token.raw == attempt.raw
                            or len(after) != 5
                            or [r["phase"] for r in after] != ["INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED", "CLEARED"]
                            or after[-1]["phase"] != "CLEARED" or after[-1]["previous"] != attempt.head):
                        raise CleanupUnconfirmed("Interrupted retirement changed before manager publication")
                    record.phase = Phase.RELEASED
                    record.reason = "Interrupted-owner retirement and reconciliation confirmed"
                    record.quarantine_failure_type = None
                    return True
        except BaseException as original:
            with self._lock:
                owner._revoked = True
                if self._records.get(key) is record and record.owner is owner:
                    record.phase = Phase.QUARANTINED
                    record.reason = "Interrupted-owner retirement was not published"
                    record.quarantine_failure_type = type(original).__name__
            raise
        finally:
            with self._lock:
                if self._interrupted_retirements.get(key) is attempt:
                    del self._interrupted_retirements[key]

    reconcile_interrupted_owner = retire_and_reconcile_interrupted_owner

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
        key = self.inner._key
        with manager._lock:
            if self.inner._entered or self.inner._exited:
                raise SnapshotBusy("Lease object cannot be reused")
            old = manager._records.get(key)
            if key in manager._entering or old is not None and old.phase is not Phase.RELEASED:
                raise SnapshotBusy("Semantic snapshot already entering, leased or quarantined")
            entry = object()
            manager._entering[key] = entry
        installed = False
        try:
            physical, semantic, generation, creation = self.binding
            # The semantic entry slot prevents token replacement while journal
            # I/O occurs outside the state lock. Physical exclusion is separate.
            self.token = manager._reservations.begin(physical, semantic, generation, creation)
            with manager._lock:
                old = manager._records.get(key)
                if (manager._entering.get(key) is not entry
                        or old is not None and old.phase is not Phase.RELEASED):
                    raise SnapshotBusy("Semantic entry changed before token publication")
                manager._tokens[key] = self.token
                installed = True
            self.inner.__enter__()
            return self
        except BaseException as original:
            if self.token is not None:
                if installed:
                    manager._flush_quarantine(key, original)
                else:
                    try:
                        manager._reservations.quarantine(self.token, "acquire_failed")
                    except BaseException as error:
                        original.add_note("Unpublished reservation quarantine unconfirmed: " + type(error).__name__)
            raise
        finally:
            with manager._lock:
                if manager._entering.get(key) is entry:
                    del manager._entering[key]

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
            # Pipe bootstrap, adoption and policy acknowledgement may block.
            # They complete outside both manager and reservation state locks.
            if manager._delegate.finish_start(worker, permit, profile) is not True:
                raise LifecycleUnavailable("Owned startup completion unconfirmed")
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

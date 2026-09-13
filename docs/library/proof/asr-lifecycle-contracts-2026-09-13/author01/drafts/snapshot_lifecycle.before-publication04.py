"""Unexecuted state/facade proposal. No Windows, process or model implementation.

The kernel port is trusted bootstrap infrastructure, not caller data. Its real
implementation is absent. These in-memory checks are not filesystem exclusion.
"""
from dataclasses import dataclass
from enum import Enum, auto
from math import isfinite
from threading import RLock


class LifecycleUnavailable(RuntimeError):
    pass


class SnapshotBusy(RuntimeError):
    pass


class SessionClosed(RuntimeError):
    pass


class CleanupUnconfirmed(RuntimeError):
    pass


class Phase(Enum):
    ACQUIRING = auto()
    PROTECTED = auto()
    NATIVE_RESERVED = auto()
    NATIVE_RUNNING = auto()
    NATIVE_STOPPED = auto()
    NATIVE_CLOSED = auto()
    QUARANTINED = auto()
    RELEASED = auto()


@dataclass(frozen=True)
class SnapshotKey:
    store_root: str
    choice: str
    revision: str


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str
    probability: float


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    words: tuple


@dataclass(frozen=True)
class TranscribeRequest:
    # An opaque ticket issued and checked by the future owned decoder/worker.
    # Possessing an arbitrary object or filename does not authorize media I/O.
    media_ticket: object
    language: str | None = None
    word_timestamps: bool = False
    vad_filter: bool = False
    beam_size: int = 1
    best_of: int = 1


@dataclass(frozen=True)
class MediaResultContract:
    # Only an exact object in the trusted worker-control port's issued registry
    # is accepted. Constructing this dataclass is not evidence or authority.
    permit_identity: object
    media_identity: object
    sample_rate: int
    sample_count: int
    max_segments: int
    max_words: int
    max_text_chars: int


def _validate_contract(contract, permit):
    if type(contract) is not MediaResultContract or contract.permit_identity is not permit:
        raise LifecycleUnavailable("Owned media/result contract is not bound to this session")
    if contract.media_identity is None or type(contract.sample_rate) is not int or contract.sample_rate != 16000:
        raise LifecycleUnavailable("Owned mono 16-kHz media contract required")
    if type(contract.sample_count) is not int or not 0 < contract.sample_count <= 16000 * 86400:
        raise LifecycleUnavailable("Owned media duration is outside the proposed bound")
    for value, maximum in ((contract.max_segments, 100000), (contract.max_words, 1000000),
                           (contract.max_text_chars, 8000000)):
        if type(value) is not int or not 0 < value <= maximum:
            raise LifecycleUnavailable("Owned output budget is outside the proposed bound")
    return contract


def _finite(value):
    return type(value) in (int, float) and -1e12 <= value <= 1e12 and isfinite(value)


def _validate_segment(value):
    if type(value) is not Segment or type(value.words) is not tuple or len(value.words) > 2048:
        raise LifecycleUnavailable("Worker returned an invalid passive segment")
    if not (_finite(value.start) and _finite(value.end) and 0 <= value.start <= value.end):
        raise LifecycleUnavailable("Worker returned invalid segment times")
    if type(value.text) is not str or len(value.text) > 65536:
        raise LifecycleUnavailable("Worker returned invalid segment text")
    for word in value.words:
        if type(word) is not Word or type(word.text) is not str or len(word.text) > 4096:
            raise LifecycleUnavailable("Worker returned an invalid passive word")
        if not (_finite(word.start) and _finite(word.end) and value.start <= word.start <= word.end <= value.end):
            raise LifecycleUnavailable("Worker returned invalid word times")
        if not (_finite(word.probability) and 0 <= word.probability <= 1):
            raise LifecycleUnavailable("Worker returned invalid word probability")
    return value


@dataclass
class _Record:
    key: SnapshotKey
    phase: Phase = Phase.ACQUIRING
    protection: object = None
    permit: object = None
    owner: object = None
    reason: str | None = None
    quarantine_persisted: bool = False
    quarantine_failure_type: str | None = None


class SnapshotLifecycle:
    """Exclusive per-snapshot policy, pending a real kernel protection port."""

    def __init__(self, kernel_port=None):
        self._kernel = kernel_port
        self._lock = RLock()
        self._records = {}

    def read_lease(self, store_root, choice, revision):
        if self._kernel is None:
            raise LifecycleUnavailable("Windows snapshot protection is unavailable")
        if any(type(value) is not str or not value or len(value) > 4096
               for value in (store_root, choice, revision)):
            raise LifecycleUnavailable("Snapshot identity refused")
        # Canonical root/ancestor containment, identity and writer exclusion
        # remain mandatory kernel-port checks before acquire_read can return.
        return _Lease(self, SnapshotKey(store_root, choice, revision))

    def _quarantine(self, record, reason):
        # Caller holds _lock. Keep protection/permit/owner references alive.
        record.phase = Phase.QUARANTINED
        record.reason = reason
        record.quarantine_persisted = False
        if record.owner is not None:
            record.owner._revoked = True
        try:
            recorded = self._kernel.quarantine(record.key, record.protection, record.permit, reason)
        except BaseException as exc:
            record.quarantine_failure_type = type(exc).__name__
            if not isinstance(exc, Exception):
                raise
            raise CleanupUnconfirmed("Quarantine persistence is unconfirmed; local record remains blocked") from exc
        if recorded is not True:
            record.quarantine_failure_type = "UnconfirmedReturn"
            raise CleanupUnconfirmed("Quarantine persistence is unconfirmed; local record remains blocked")
        record.quarantine_persisted = True
        record.quarantine_failure_type = None

    def _quarantine_preserving(self, record, reason, original):
        # Keep the first error/interruption while recording failed persistence.
        try:
            self._quarantine(record, reason)
        except BaseException as quarantine_error:
            original.add_note("Snapshot remains locally quarantined; durable quarantine attempt failed: "
                              + type(quarantine_error).__name__)

    def require_writer_protection(self, store_root, choice, revision):
        key = SnapshotKey(store_root, choice, revision)
        with self._lock:
            record = self._records.get(key)
            if record is not None and record.phase is not Phase.RELEASED:
                raise SnapshotBusy("Snapshot is leased or quarantined")
        # No successful path until an actual writer/publish/delete port exists.
        raise LifecycleUnavailable("Writer protection and publication are not implemented")


class _Lease:
    def __init__(self, manager, key):
        self._manager = manager
        self._key = key
        self._record = None
        self._entered = False
        self._exited = False

    def __enter__(self):
        manager = self._manager
        with manager._lock:
            if self._entered or self._exited:
                raise SnapshotBusy("Lease object cannot be reused")
            old = manager._records.get(self._key)
            if old is not None and old.phase is not Phase.RELEASED:
                raise SnapshotBusy("Snapshot is already protected or quarantined")
            self._entered = True
            record = _Record(self._key)
            self._record = record
            manager._records[self._key] = record
            try:
                record.protection = manager._kernel.acquire_read(self._key)
                if record.protection is None:
                    raise LifecycleUnavailable("Kernel port returned no snapshot protection")
                record.phase = Phase.PROTECTED
                return self
            except BaseException as exc:
                manager._quarantine_preserving(record, "acquire_read did not complete", exc)
                raise

    def begin_native_session(self):
        manager = self._manager
        with manager._lock:
            record = self._record
            if self._exited or record is None or record.phase is not Phase.PROTECTED:
                raise SessionClosed("Native session cannot begin on this lease")
            # The identity is a local capability only, never model approval.
            record.permit = object()
            record.phase = Phase.NATIVE_RESERVED
            return _NativePermit(manager, record, record.permit)

    def confirm_native_closed(self):
        manager = self._manager
        with manager._lock:
            record = self._record
            if (self._exited or record is None or record.phase is not Phase.NATIVE_STOPPED
                    or record.owner is None or record.owner._closed_verified is not True
                    or record.owner._active != 0):
                raise CleanupUnconfirmed("Owned worker quiescence is not confirmed")
            record.phase = Phase.NATIVE_CLOSED

    def __exit__(self, exc_type, exc_value, traceback):
        manager = self._manager
        with manager._lock:
            if self._exited:
                return False
            self._exited = True
            record = self._record
            if record is None:
                return False
            if record.phase not in (Phase.PROTECTED, Phase.NATIVE_CLOSED):
                if isinstance(exc_value, BaseException):
                    manager._quarantine_preserving(record, "Lease exited with native work or protection unconfirmed", exc_value)
                    return False
                manager._quarantine(record, "Lease exited with native work or protection unconfirmed")
                raise CleanupUnconfirmed("Snapshot remains quarantined")
            try:
                released = manager._kernel.release_read(record.protection)
            except BaseException as release_error:
                original = exc_value if isinstance(exc_value, BaseException) else release_error
                manager._quarantine_preserving(record, "Snapshot protection release raised", original)
                if isinstance(exc_value, BaseException):
                    original.add_note("Snapshot protection release raised: " + type(release_error).__name__)
                    return False
                raise
            if released is not True:
                if isinstance(exc_value, BaseException):
                    manager._quarantine_preserving(record, "Snapshot protection release was not confirmed", exc_value)
                    return False
                manager._quarantine(record, "Snapshot protection release was not confirmed")
                raise CleanupUnconfirmed("Snapshot remains quarantined")
            record.phase = Phase.RELEASED
            record.protection = None
            return False


@dataclass(frozen=True)
class _NativePermit:
    manager: SnapshotLifecycle
    record: _Record
    identity: object


class OwnedRuntimeFactory:
    def __init__(self, lifecycle):
        self._lifecycle = lifecycle

    def open_owned_session(self, profile, permit):
        manager = self._lifecycle
        if type(permit) is not _NativePermit or permit.manager is not manager:
            raise LifecycleUnavailable("The active lease's native permit is required")
        with manager._lock:
            record = permit.record
            if (manager._records.get(record.key) is not record or record.permit is not permit.identity
                    or record.phase is not Phase.NATIVE_RESERVED or record.owner is not None):
                raise SessionClosed("Native permit is stale or already consumed")
            owner = OwnedSession(manager, record)
            record.owner = owner
            try:
                # The port must reserve crash-recoverable ownership before it
                # creates a process or lets native code reopen protected paths.
                owner._worker = manager._kernel.start_owned_worker(record.protection, permit.identity, profile)
                if owner._worker is None:
                    raise LifecycleUnavailable("Worker ownership was not returned")
                record.phase = Phase.NATIVE_RUNNING
                return owner
            except BaseException as exc:
                manager._quarantine_preserving(record, "Owned worker start did not complete", exc)
                raise


class OwnedSession:
    def __init__(self, manager, record):
        self._manager = manager
        self._record = record
        self._worker = None
        self._active = 0
        self._revoked = False
        self._closing = False
        self._closed_verified = False
        self._facade = OperationFacade(self)
        self._transcription_started = False

    def operations(self):
        with self._manager._lock:
            self._require_live()
            return self._facade

    def _require_live(self):
        if self._revoked or self._closing or self._record.phase is not Phase.NATIVE_RUNNING:
            raise SessionClosed("Owned session has closed or been quarantined")

    def _call(self, method, *args):
        manager = self._manager
        with manager._lock:
            self._require_live()
            if self._active:
                raise SnapshotBusy("Owned worker operations must be serial")
            self._active += 1
        try:
            # Fixed methods only; callers cannot select an arbitrary method.
            result = method(self._worker, *args)
            with manager._lock:
                self._require_live()
            return result
        except BaseException as exc:
            if not isinstance(exc, Exception):
                with manager._lock:
                    manager._quarantine_preserving(self._record, "Owned operation interrupted", exc)
            raise
        finally:
            with manager._lock:
                self._active -= 1

    def close_and_join(self):
        manager = self._manager
        with manager._lock:
            if self._closed_verified:
                return True
            if self._closing or self._record.phase is Phase.QUARANTINED:
                return False
            self._closing = True
            self._revoked = True
            worker = self._worker
        try:
            # No raw model/generator reference is present in this process.
            joined = manager._kernel.close_and_join(worker, self._record.permit)
            quiet = joined is True and manager._kernel.confirm_quiescent(
                self._record.protection, worker, self._record.permit) is True
        except BaseException as exc:
            with manager._lock:
                manager._quarantine_preserving(self._record, "Owned worker shutdown raised", exc)
            raise
        with manager._lock:
            if self._record.phase is not Phase.NATIVE_RUNNING:
                # A concurrent lease exit/quarantine cannot be cleared by a
                # later successful join result. Recovery is a separate port.
                return False
            if not quiet or self._active != 0:
                manager._quarantine(self._record, "Owned worker or in-flight operations are not quiescent")
                return False
            self._closed_verified = True
            self._record.phase = Phase.NATIVE_STOPPED
            return True


class OperationFacade:
    """Only fixed operations; no raw-model access or arbitrary attribute proxy."""

    def __init__(self, session):
        self._session = session

    def transcribe(self, request):
        if type(request) is not TranscribeRequest or request.media_ticket is None:
            raise LifecycleUnavailable("Owned media request required")
        if request.language is not None and (type(request.language) is not str or len(request.language) > 32):
            raise LifecycleUnavailable("Language option refused")
        if type(request.word_timestamps) is not bool or type(request.vad_filter) is not bool:
            raise LifecycleUnavailable("Boolean transcription options required")
        if type(request.beam_size) is not int or type(request.best_of) is not int or request.beam_size != 1 or request.best_of != 1:
            raise LifecycleUnavailable("Unqualified decoding options refused")
        session = self._session
        with session._manager._lock:
            session._require_live()
            if session._transcription_started:
                raise SnapshotBusy("One bounded transcription is permitted per owned session")
            session._transcription_started = True
        # The trusted control port admits an already-owned media ticket, using
        # decoder-origin sample metadata. Caller/model shape claims cannot do so.
        contract = session._call(session._manager._kernel.admit_media_request,
                                 session._record.permit, request.media_ticket)
        contract = _validate_contract(contract, session._record.permit)
        issued = session._call(session._manager._kernel.is_issued_media_contract,
                               session._record.permit, contract)
        if issued is not True:
            raise LifecycleUnavailable("Media/result contract was not issued by the owned worker control port")
        cursor = session._call(session._manager._kernel.begin_transcription, contract, request)
        if cursor is None:
            raise LifecycleUnavailable("Worker returned no transcription cursor")
        return SegmentStream(session, cursor, contract)


class SegmentStream:
    def __init__(self, session, cursor, contract):
        self._session = session
        self._cursor = cursor
        self._exhausted = False
        self._contract = contract
        self._segments = 0
        self._words = 0
        self._text_chars = 0
        self._last_end = 0
        self._next_active = False

    def __iter__(self):
        with self._session._manager._lock:
            self._session._require_live()
        return self

    def __next__(self):
        session = self._session
        with session._manager._lock:
            session._require_live()
            if self._exhausted:
                raise StopIteration
            if self._next_active:
                raise SnapshotBusy("Concurrent stream consumption refused")
            self._next_active = True
        try:
            return self._next_segment()
        finally:
            with session._manager._lock:
                self._next_active = False

    def _next_segment(self):
        session = self._session
        value = session._call(session._manager._kernel.next_segment, self._cursor)
        if value is None:
            self._exhausted = True
            raise StopIteration
        try:
            value = _validate_segment(value)
            duration = self._contract.sample_count / self._contract.sample_rate
            if value.start < self._last_end or value.end > duration:
                raise LifecycleUnavailable("Segment chronology or owned-media duration was violated")
            word_end = value.start
            for word in value.words:
                if word.start < word_end:
                    raise LifecycleUnavailable("Word chronology was violated")
                word_end = word.end
            segments = self._segments + 1
            words = self._words + len(value.words)
            text_chars = self._text_chars + len(value.text) + sum(len(word.text) for word in value.words)
            if (segments > self._contract.max_segments or words > self._contract.max_words
                    or text_chars > self._contract.max_text_chars):
                raise LifecycleUnavailable("Owned transcript aggregate budget was exceeded")
            self._segments, self._words, self._text_chars = segments, words, text_chars
            self._last_end = value.end
            return value
        except BaseException as exc:
            self._exhausted = True
            with session._manager._lock:
                session._manager._quarantine_preserving(session._record, "Worker output contract failed", exc)
            raise

    def close(self):
        session = self._session
        with session._manager._lock:
            if self._exhausted:
                return
            self._exhausted = True
            if session._revoked or session._closing:
                return
        try:
            cancelled = session._call(session._manager._kernel.cancel_transcription, self._cursor)
        except BaseException as exc:
            with session._manager._lock:
                session._manager._quarantine_preserving(session._record, "Transcription cursor cancellation raised", exc)
            raise
        if cancelled is not True:
            with session._manager._lock:
                session._manager._quarantine(session._record, "Transcription cursor cancellation unconfirmed")
            raise CleanupUnconfirmed("Snapshot remains quarantined")

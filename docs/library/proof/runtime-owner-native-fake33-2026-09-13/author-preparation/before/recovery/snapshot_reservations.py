"""Bounded reservation grammar and live tokens; no file/process/model access."""
from dataclasses import dataclass
import hashlib
import json
import struct
from threading import RLock

MAGIC = b"UORS1\n"
MAX_FRAME = 4096
MAX_JOURNAL = 4 * 1024 * 1024
MAX_FRAMES = 4096
ZERO = "0" * 64
PHASES = frozenset({"INITIALIZED", "RESERVED", "WORKER_BOUND", "QUARANTINED", "CLEARED"})
REASONS = frozenset({"acquire_failed", "start_failed", "operation_failed", "close_failed", "persistence_failed", "unknown_restart"})
FIELDS = frozenset({"schema", "sequence", "physical", "semantics", "generation", "phase", "reason", "process", "previous"})


class ReservationRefused(RuntimeError):
    pass


def _require(condition, reason):
    if not condition:
        raise ReservationRefused(reason)


def _hex(value, size=64):
    return type(value) is str and len(value) == size and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class PhysicalSnapshot:
    volume: int
    file_id: str

    def wire(self):
        _require(type(self.volume) is int and 0 <= self.volume < 1 << 64 and _hex(self.file_id, 32), "physical_snapshot_identity")
        return [self.volume, self.file_id]


@dataclass(frozen=True)
class SnapshotSemantics:
    store_volume: int
    store_file_id: str
    choice: str
    revision: str
    manifest: str

    def wire(self):
        _require(type(self.store_volume) is int and 0 <= self.store_volume < 1 << 64, "store_volume")
        _require(_hex(self.store_file_id, 32) and _hex(self.manifest), "store_and_manifest_identity")
        _require(all(type(v) is str and 0 < len(v) <= 128 and all(32 <= ord(c) < 127 for c in v)
                     for v in (self.choice, self.revision)), "snapshot_semantics")
        return [self.store_volume, self.store_file_id, self.choice, self.revision, self.manifest]


def _shape(row):
    _require(type(row) is dict and set(row) == FIELDS, "journal_fields")
    _require(type(row["schema"]) is int and row["schema"] == 1, "journal_schema")
    _require(type(row["sequence"]) is int and 0 <= row["sequence"] < MAX_FRAMES, "journal_sequence")
    physical, semantic = row["physical"], row["semantics"]
    _require(type(physical) is list and len(physical) == 2, "journal_physical")
    PhysicalSnapshot(*physical).wire()
    _require(type(semantic) is list and len(semantic) == 5, "journal_semantics")
    SnapshotSemantics(*semantic).wire()
    _require(type(row["phase"]) is str and row["phase"] in PHASES, "journal_phase")
    _require(row["generation"] is None or _hex(row["generation"]), "journal_generation")
    _require(row["reason"] is None or type(row["reason"]) is str and row["reason"] in REASONS, "journal_reason")
    process = row["process"]
    _require(process is None or type(process) is list and len(process) == 2
             and type(process[0]) is int and 0 < process[0] < 1 << 32
             and type(process[1]) is int and 0 < process[1] < 1 << 64, "journal_process_observation")
    _require(_hex(row["previous"]), "journal_previous")


def _transition(prior, row, generations):
    _shape(row)
    if prior is None:
        _require(row["sequence"] == 0 and row["previous"] == ZERO and row["phase"] == "INITIALIZED"
                 and row["generation"] is None and row["process"] is None and row["reason"] is None, "journal_initialization")
        return
    _require(row["sequence"] == prior["sequence"] + 1 and row["physical"] == prior["physical"], "journal_order_or_identity")
    phase = row["phase"]
    if phase == "RESERVED":
        _require(prior["phase"] in ("INITIALIZED", "CLEARED") and _hex(row["generation"])
                 and row["generation"] not in generations and row["process"] is None and row["reason"] is None, "journal_reservation_transition")
        generations.add(row["generation"])
        return
    _require(row["generation"] == prior["generation"] and row["semantics"] == prior["semantics"], "journal_generation_binding")
    if phase == "WORKER_BOUND":
        _require(prior["phase"] == "RESERVED" and row["process"] is not None and row["reason"] is None, "journal_worker_transition")
    elif phase == "QUARANTINED":
        _require(prior["phase"] in ("RESERVED", "WORKER_BOUND", "QUARANTINED")
                 and row["process"] == prior["process"] and row["reason"] in REASONS, "journal_quarantine_transition")
    elif phase == "CLEARED":
        _require(prior["phase"] in ("RESERVED", "WORKER_BOUND", "QUARANTINED")
                 and row["process"] == prior["process"] and row["reason"] is None, "journal_clear_transition")
    else:
        raise ReservationRefused("journal_transition")


def decode_journal(raw):
    _require(type(raw) is bytes and len(MAGIC) < len(raw) <= MAX_JOURNAL and raw.startswith(MAGIC), "journal_size_or_magic")
    offset, previous, rows, generations = len(MAGIC), ZERO, [], set()
    def pairs(items):
        out = {}
        for key, value in items:
            _require(key not in out, "journal_duplicate_key")
            out[key] = value
        return out
    while offset < len(raw):
        _require(len(rows) < MAX_FRAMES and len(raw) - offset >= 4, "journal_truncated_or_count")
        length = struct.unpack_from("!I", raw, offset)[0]
        offset += 4
        _require(0 < length <= MAX_FRAME and len(raw) - offset >= length + 32, "journal_frame_bound")
        payload, digest = raw[offset:offset + length], raw[offset + length:offset + length + 32]
        offset += length + 32
        _require(hashlib.sha256(payload).digest() == digest, "journal_checksum")
        try:
            row = json.loads(payload, object_pairs_hook=pairs)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ReservationRefused("journal_json") from exc
        _transition(rows[-1] if rows else None, row, generations)
        _require(row["previous"] == previous, "journal_predecessor")
        rows.append(row)
        previous = digest.hex()
    return rows, previous


def encode_next(raw, physical, semantic, generation, phase, reason=None, process=None):
    _require(type(raw) is bytes, "exact_journal_bytes")
    _require(type(physical) is PhysicalSnapshot and type(semantic) is SnapshotSemantics, "exact_identity_types")
    rows, previous = ([], ZERO) if raw == b"" else decode_journal(raw)
    row = dict(schema=1, sequence=len(rows), physical=physical.wire(), semantics=semantic.wire(),
               generation=generation, phase=phase, reason=reason, process=process, previous=previous)
    generations = {r["generation"] for r in rows if r["phase"] == "RESERVED"}
    _transition(rows[-1] if rows else None, row, generations)
    payload = json.dumps(row, separators=(",", ":"), sort_keys=True, ensure_ascii=True, allow_nan=False).encode("ascii")
    _require(len(payload) <= MAX_FRAME, "encoded_frame_bound")
    frame = (MAGIC if not rows else b"") + struct.pack("!I", len(payload)) + payload + hashlib.sha256(payload).digest()
    _require(len(raw) + len(frame) <= MAX_JOURNAL, "journal_total_bound")
    return frame


class GeneratedGateRegistry:
    """One trusted generated bootstrap instance; process-local exclusion only.

    This is the injectable functional gate for source qualification. It is not
    the unimplemented cross-process Windows gate or restart recovery service.
    """
    def __init__(self, confirm_new_snapshot, confirm_reconciliation):
        self._lock, self._held, self._known_clean = RLock(), {}, {}
        self._new = {}
        self._confirm_new = confirm_new_snapshot
        self._confirm_reconciliation = confirm_reconciliation

    def register_generated_creation(self, physical, evidence):
        # The observer is a trusted bootstrap service fixed at construction;
        # arbitrary client fields cannot replace it with a permissive callback.
        _require(type(physical) is PhysicalSnapshot, "exact_physical_key")
        physical.wire()
        _require(self._confirm_new(physical, evidence) is True, "new_snapshot_not_observed")
        with self._lock:
            _require(physical not in self._held and physical not in self._new
                     and physical not in self._known_clean, "snapshot_already_registered")
            issued = object()
            self._new[physical] = issued
            return issued

    def consume_creation(self, physical, gate, issued):
        with self._lock:
            self.require(physical, gate)
            _require(issued is not None and self._new.get(physical) is issued, "new_snapshot_creation_evidence_required")
            del self._new[physical]

    def known_clean(self, physical, gate, head):
        with self._lock:
            self.require(physical, gate)
            return self._known_clean.get(physical) == head

    def reconcile_current(self, physical, gate, head, generation, evidence):
        self.require(physical, gate)
        _require(_hex(head) and self._confirm_reconciliation(physical, head, generation, evidence) is True,
                 "current_reconciliation_evidence_required")
        with self._lock:
            self.require(physical, gate)
            # Do not publish clean-head credit yet. The caller must still
            # persist the clear transition successfully before gate release.
            return True

    def acquire(self, physical):
        _require(type(physical) is PhysicalSnapshot, "exact_physical_key")
        physical.wire()
        with self._lock:
            _require(physical not in self._held, "physical_snapshot_busy")
            token = object()
            self._held[physical] = token
            return token

    def require(self, physical, token):
        with self._lock:
            _require(token is not None and physical in self._held
                     and self._held[physical] is token, "gate_owner_required")

    def release(self, physical, token, clean_head):
        with self._lock:
            self.require(physical, token)
            _require(_hex(clean_head), "clean_head_required")
            self._known_clean[physical] = clean_head
            del self._held[physical]


class Reservation:
    def __init__(self, service, physical, semantic, generation, gate, journal, raw):
        self.service, self.physical, self.semantic, self.generation = service, physical, semantic, generation
        self.gate, self.journal, self.raw = gate, journal, raw
        self.worker = None
        self.phase = "RESERVED"
        self.persistence_failure = None
        self.revoked = False
        self.pending = None
        self.revision = 0
        self.resume_attempted = False
        self._lock = RLock()


class ReservationService:
    """Ports belong to trusted generated bootstrap, never serialized profiles.

    open_journal(physical) returns an already-retained journal port.
    observe_worker(worker) validates a live retained owner and returns PID/time.
    confirm_teardown(worker, evidence) must independently validate exact live
    ownership, zero pending work and completed guard retirement. No disk value
    is passed as evidence. Real versions of these ports are not implemented.

    confirm_live_reconciliation(worker, physical, generation, head, attempt) is
    a separate trusted observer fixed at construction. It must freshly confirm
    the exact retained owner is stopped, no work/I/O remains, and guards have
    retired. It binds these observations to this unique attempt and current
    physical/generation/head. Recorded identities and earlier receipts cannot
    satisfy it. This callback does not acquire ownership from a recorded PID.
    """
    def __init__(self, gates, open_journal, observe_worker, confirm_teardown,
                 confirm_live_reconciliation=None):
        self.gates, self._open, self._observe, self._finish = gates, open_journal, observe_worker, confirm_teardown
        self._reconcile_live = confirm_live_reconciliation
        self._live = {}

    def begin(self, physical, semantic, generation, new_snapshot_evidence=None):
        gate = self.gates.acquire(physical)
        token = Reservation(self, physical, semantic, generation, gate, None, b"")
        self._live[gate] = token
        try:
            token.journal = self._open(physical)
            token.raw = token.journal.read_all()
            # Empty state requires a private bootstrap registry entry; no
            # caller-provided dataclass/profile can register a new snapshot.
            if token.raw == b"":
                self.gates.consume_creation(physical, gate, new_snapshot_evidence)
                token.raw = token.journal.append_confirmed(b"", encode_next(b"", physical, semantic, None, "INITIALIZED"))
            else:
                rows, head = decode_journal(token.raw)
                _require(rows[-1]["physical"] == physical.wire(), "physical_record_mismatch")
                _require(rows[-1]["phase"] in ("INITIALIZED", "CLEARED") and self.gates.known_clean(physical, gate, head),
                         "restart_reconciliation_required")
            token.raw = token.journal.append_confirmed(token.raw, encode_next(token.raw, physical, semantic, generation, "RESERVED"))
            with token._lock:
                self._owned(token)
                _require(not token.revoked and token.phase == "RESERVED", "reservation_revoked_before_publication")
                return token
        except BaseException as exc:
            token.phase, token.persistence_failure = "QUARANTINED", type(exc).__name__
            token.revoked = True
            # Keep both gate and any partial journal ownership. No fake unlock.
            raise

    def _owned(self, token):
        _require(type(token) is Reservation and token.service is self and self._live.get(token.gate) is token,
                 "live_reservation_required")
        self.gates.require(token.physical, token.gate)

    def retained_failure(self, physical):
        """Trusted bootstrap lookup after begin raised; never release credit.

        Access to this service is private bootstrap authority, not an IPC
        endpoint accepting a public physical-identity claim.
        """
        _require(type(physical) is PhysicalSnapshot, "exact_physical_key")
        physical.wire()
        matches = [token for token in tuple(self._live.values()) if token.physical == physical]
        _require(len(matches) == 1, "one_retained_reservation_required")
        token = matches[0]
        with token._lock:
            self._owned(token)
            _require(token.phase == "QUARANTINED" and token.revoked, "retained_failure_required")
            return token

    def recover_existing(self, physical, evidence):
        """Explicit restart reconciliation; no worker is opened or controlled.

        The trusted reconciliation callback must bind evidence by identity to
        the physical snapshot, exact journal head and prior generation. Old
        PID/time fields are never converted into native ownership. Corrupt
        journals remain blocked, including when an observer claims quiet.
        """
        gate = self.gates.acquire(physical)
        token = Reservation(self, physical, None, None, gate, None, b"")
        token.revoked, token.phase = True, "QUARANTINED"
        operation = token.pending = object()
        revision = token.revision
        self._live[gate] = token
        try:
            token.journal = self._open(physical)
            token.raw = token.journal.read_all()
            rows, head = decode_journal(token.raw)
            last = rows[-1]
            _require(last["physical"] == physical.wire(), "recovery_physical_mismatch")
            token.semantic = SnapshotSemantics(*last["semantics"])
            token.generation = last["generation"]
            self.gates.reconcile_current(physical, gate, head, token.generation, evidence)
            if last["phase"] in ("RESERVED", "WORKER_BOUND", "QUARANTINED"):
                frame = encode_next(token.raw, physical, token.semantic, token.generation,
                                    "CLEARED", process=last["process"])
                token.raw = token.journal.append_confirmed(token.raw, frame)
                _, head = decode_journal(token.raw)
            else:
                _require(last["phase"] in ("INITIALIZED", "CLEARED"), "recovery_transition")
                token.raw = token.journal.confirm_current(token.raw)
            with token._lock:
                self._owned(token)
                _require(token.pending is operation and token.revision == revision,
                         "recovery_revoked_before_release")
                self.gates.release(physical, gate, head)
                token.pending = None
                token.phase = "CLEARED"
                del self._live[gate]
                return True
        except BaseException as exc:
            with token._lock:
                if token.pending is operation:
                    token.pending = None
                token.persistence_failure = type(exc).__name__
            raise

    def bind_worker(self, token, worker):
        self._owned(token)
        with token._lock:
            self._owned(token)
            _require(token.phase == "RESERVED" and not token.revoked and token.pending is None
                     and token.worker is None, "worker_binding_order")
            token.worker = worker
            operation = token.pending = object()
        try:
            observed = self._observe(worker)
            frame = encode_next(token.raw, token.physical, token.semantic, token.generation,
                                "WORKER_BOUND", process=observed)
            after = token.journal.append_confirmed(token.raw, frame)
            with token._lock:
                self._owned(token)
                token.raw, token.pending = after, None
                _require(not token.revoked and token.phase == "RESERVED", "worker_binding_revoked_before_publication")
                token.phase = "WORKER_BOUND"
        except BaseException as exc:
            with token._lock:
                if token.pending is operation:
                    token.pending = None
                token.revoked = True
                token.phase, token.persistence_failure = "QUARANTINED", type(exc).__name__
            raise

    def require_resume(self, token):
        self._owned(token)
        with token._lock:
            self._owned(token)
            _require(token.phase == "WORKER_BOUND" and token.pending is None and not token.revoked,
                     "durable_worker_binding_required_before_resume")

    def resume_owned(self, token, resume_callback):
        # The callback is the trusted fixed nonblocking native-resume port,
        # not an operation selected from IPC. No journal I/O occurs here.
        self._owned(token)
        with token._lock:
            self._owned(token)
            self.require_resume(token)
            _require(not token.resume_attempted, "single_owned_resume_attempt")
            token.resume_attempted = True
            try:
                _require(resume_callback(token.worker) is True, "owned_resume_unconfirmed")
            except BaseException:
                token.revoked, token.phase = True, "QUARANTINED"
                token.revision += 1
                raise

    def revoke_local(self, token):
        self._owned(token)
        with token._lock:
            self._owned(token)
            token.revoked, token.phase = True, "QUARANTINED"
            token.revision += 1

    def quarantine(self, token, reason):
        self._owned(token)
        with token._lock:
            self._owned(token)
            token.revoked, token.phase = True, "QUARANTINED"
            token.revision += 1
            if token.pending is not None:
                token.persistence_failure = "PendingTransition"
                return False
            operation = token.pending = object()
        try:
            rows, _ = decode_journal(token.raw)
            frame = encode_next(token.raw, token.physical, token.semantic, token.generation,
                                "QUARANTINED", reason=reason, process=rows[-1]["process"])
            after = token.journal.append_confirmed(token.raw, frame)
            with token._lock:
                self._owned(token)
                token.raw, token.pending = after, None
                token.persistence_failure = None
            return True
        except BaseException as exc:
            with token._lock:
                if token.pending is operation:
                    token.pending = None
                token.persistence_failure = type(exc).__name__
            raise

    def complete(self, token, evidence):
        """Ordinary completion never clears quarantine or prior revocation."""
        return self._clear(token, evidence, reconciling=False)

    def reconcile_live(self, token):
        """Explicit reconciliation using fresh observations by a trusted port.

        No caller-supplied evidence or observer is accepted. Poisoned journals
        still refuse; this entry does not repair/truncate uncertain disk bytes.
        """
        return self._clear(token, None, reconciling=True)

    def _clear(self, token, evidence, *, reconciling):
        self._owned(token)
        with token._lock:
            self._owned(token)
            _require(token.pending is None, "completion_order")
            if reconciling:
                _require(token.phase == "QUARANTINED" and token.revoked
                         and self._reconcile_live is not None, "live_reconciliation_required")
            else:
                _require(token.phase in ("RESERVED", "WORKER_BOUND") and not token.revoked,
                         "ordinary_completion_requires_unrevoked_owner")
            operation = token.pending = object()
            revision = token.revision
            token.phase = "CLEAR_PENDING"
        try:
            rows, previous = decode_journal(token.raw)
            if reconciling:
                _require(self._reconcile_live(token.worker, token.physical, token.generation,
                                              previous, operation) is True,
                         "fresh_live_reconciliation_unconfirmed")
            else:
                _require(self._finish(token.worker, evidence) is True, "current_teardown_evidence_required")
            if reconciling and rows[-1]["phase"] in ("INITIALIZED", "CLEARED"):
                after = token.journal.confirm_current(token.raw)
            else:
                frame = encode_next(token.raw, token.physical, token.semantic, token.generation,
                                    "CLEARED", process=rows[-1]["process"])
                after = token.journal.append_confirmed(token.raw, frame)
            _, head = decode_journal(after)
            with token._lock:
                self._owned(token)
                token.raw, token.pending = after, None
                _require(token.revision == revision and token.phase == "CLEAR_PENDING", "completion_revoked_before_release")
                self.gates.release(token.physical, token.gate, head)
                token.phase = "CLEARED"
                del self._live[token.gate]
                return True
        except BaseException as exc:
            with token._lock:
                if token.pending is operation:
                    token.pending = None
                token.revoked = True
                token.phase, token.persistence_failure = "QUARANTINED", type(exc).__name__
            raise


def real_reservation_service(*args, **kwargs):
    raise ReservationRefused("real_reservation_recovery_and_namespace_are_not_admitted")

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
    def __init__(self):
        self._lock, self._held, self._known_clean = RLock(), {}, {}

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
            _require(self._held.get(physical) is token, "gate_owner_required")

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
        self._lock = RLock()


class ReservationService:
    """Ports belong to trusted generated bootstrap, never serialized profiles.

    open_journal(physical) returns an already-retained journal port.
    observe_worker(worker) validates a live retained owner and returns PID/time.
    confirm_teardown(worker, evidence) must independently validate exact live
    ownership, zero pending work and completed guard retirement. No disk value
    is passed as evidence. Real versions of these ports are not implemented.
    """
    def __init__(self, gates, open_journal, observe_worker, confirm_teardown):
        self.gates, self._open, self._observe, self._finish = gates, open_journal, observe_worker, confirm_teardown
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
                _require(new_snapshot_evidence is not None and self.gates._known_clean.get(physical) is new_snapshot_evidence,
                         "new_snapshot_creation_evidence_required")
                token.raw = token.journal.append_confirmed(b"", encode_next(b"", physical, semantic, None, "INITIALIZED"))
            else:
                rows, head = decode_journal(token.raw)
                _require(rows[-1]["physical"] == physical.wire(), "physical_record_mismatch")
                _require(rows[-1]["phase"] in ("INITIALIZED", "CLEARED") and self.gates._known_clean.get(physical) == head,
                         "restart_reconciliation_required")
            token.raw = token.journal.append_confirmed(token.raw, encode_next(token.raw, physical, semantic, generation, "RESERVED"))
            return token
        except BaseException as exc:
            token.phase, token.persistence_failure = "QUARANTINED", type(exc).__name__
            # Keep both gate and any partial journal ownership. No fake unlock.
            raise

    def _owned(self, token):
        _require(type(token) is Reservation and token.service is self and self._live.get(token.gate) is token,
                 "live_reservation_required")
        self.gates.require(token.physical, token.gate)

    def bind_worker(self, token, worker):
        self._owned(token)
        with token._lock:
            _require(token.phase == "RESERVED" and token.worker is None, "worker_binding_order")
            token.worker = worker
            try:
                observed = self._observe(worker)
                frame = encode_next(token.raw, token.physical, token.semantic, token.generation,
                                    "WORKER_BOUND", process=observed)
                token.raw = token.journal.append_confirmed(token.raw, frame)
                token.phase = "WORKER_BOUND"
            except BaseException as exc:
                token.phase, token.persistence_failure = "QUARANTINED", type(exc).__name__
                raise

    def quarantine(self, token, reason):
        self._owned(token)
        with token._lock:
            token.phase = "QUARANTINED"
            try:
                rows, _ = decode_journal(token.raw)
                frame = encode_next(token.raw, token.physical, token.semantic, token.generation,
                                    "QUARANTINED", reason=reason, process=rows[-1]["process"])
                token.raw = token.journal.append_confirmed(token.raw, frame)
                return True
            except BaseException as exc:
                token.persistence_failure = type(exc).__name__
                raise

    def complete(self, token, evidence):
        self._owned(token)
        with token._lock:
            _require(self._finish(token.worker, evidence) is True, "current_teardown_evidence_required")
            try:
                rows, _ = decode_journal(token.raw)
                frame = encode_next(token.raw, token.physical, token.semantic, token.generation,
                                    "CLEARED", process=rows[-1]["process"])
                token.raw = token.journal.append_confirmed(token.raw, frame)
                _, head = decode_journal(token.raw)
                self.gates.release(token.physical, token.gate, head)
                token.phase = "CLEARED"
                del self._live[token.gate]
            except BaseException as exc:
                token.phase, token.persistence_failure = "QUARANTINED", type(exc).__name__
                raise


def real_reservation_service(*args, **kwargs):
    raise ReservationRefused("real_reservation_recovery_and_namespace_are_not_admitted")

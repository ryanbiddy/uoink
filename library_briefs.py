"""library_briefs.py - client-produced daily briefs (contract phase4-v1-2026-09-08).

Uoink prepares a bounded, hashed input packet for a client-run report job and
validates/persists the artifact the client submits. No model, no scheduler,
no sampling request, no fallback cognition: a clock alone never produces a
document. Run AV-2 (2026-09-08), claude worker. Frozen interface:
``docs/library/PHASE4-AV2-BRIEF-2026-09-08.md``.

Contract rules this module does not implement exactly, and why
--------------------------------------------------------------
1. ``submission_key`` grammar is *stricter* than Phase 2's operation-key
   grammar (1-200 characters, stripped, no control characters): it also
   refuses interior whitespace, which the P4-08 fixture requires
   (``"sub key with spaces"`` must be ``invalid_request``). Every key Phase
   2 accepts without whitespace is accepted here unchanged.
2. The prepared packet is not persisted by ``prepare_input`` ("no lease or
   persistent mutation"): the client job record retains it and presents it
   as ``input_packet`` at publication, where it is stored with the artifact.
   Publication therefore never depends on server-side packet retention.
3. ``run_id`` need not name an existing Phase 2 run: a report over a run the
   service has not recorded binds ``run: {found: false}`` with an empty run
   queue digest, and coverage says so. Refusing would make the brief job
   impossible on installations without a Phase 2 run.
4. The evidence sample (up to five default Librarian cards) is the most
   recent eligible items of the whole library by capture time descending,
   then item id, not only items captured inside the UTC day. Captures,
   applied changes and shelf revisions are counted inside the day's covered
   interval ``[day_start, as_of]``. Items whose card cannot be rendered
   safely are excluded from the sample and listed with their refusal code.
5. Cross-process writer serialization uses an exclusive lock file under the
   brief directory (``.publish.lock``, stale after 60 s) with a bounded wait
   measured on the real monotonic clock; a writer that cannot acquire it
   inside the wait refuses ``rate_limited`` (reason ``concurrency``).

Storage layout under ``DATA_ROOT/reach/briefs/``::

    {date}/{brief_hash}/manifest.json   binding (hashes, timestamps, identity, usage)
    {date}/{brief_hash}/document.md     the submitted document, byte-exact
    {date}/{brief_hash}/citations.json  the submitted citations
    {date}/{brief_hash}/packet.json     the bound input packet body
    {date}/.tmp-*                       interrupted publications (never advertised)
    jobs/{job_key}.json                 first accepted artifact for a job (hashes only)
    submissions/{sha256(submission_key)}.json   idempotency record (hashes + receipt)
    receipts/{brief_hash}.json          content-free receipt; survives hard purge

Everything the client reads back is untrusted data inside the shared fence.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import json
import logging
import math
import os
import re
import secrets
import shutil
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterator

import library_cards
import library_resources
from library_resources import (
    CONTRACT_VERSION,
    LIMITS,
    MIME_TYPE,
    SCHEMA_VERSION,
    URI_PREFIX,
    LibraryReader,
    ReadGuard,
    ResourceError,
    _document_body,
    _invalid,
    _success,
    card_uri,
    excerpt_uri,
    label,
    render_document,
    wire_bytes,
)

log = logging.getLogger("uoink.library_briefs")

BRIEF_DIR = "reach/briefs"                      # under data_root

BRIEF_LIMITS: dict[str, Any] = {
    "max_packet_bytes": 24576,
    "max_request_bytes": 65536,
    "max_document_bytes": 8192,
    "max_citations": 20,
    "max_quote_codepoints": 500,
    "max_work_rows": 20,
    "max_queue_exclusions": 20,
    "max_cards": 5,
    "max_usage_keys": 32,
    "max_client_identity_chars": 64,
    "max_key_chars": 200,
    "writer_wait_s": 2.0,
    "stale_lock_s": 60.0,
    "max_discovery_dates": 7,
}

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DIGITS_RE = re.compile(r"^[0-9]{1,20}$")
_EVIDENCE_KINDS = ("timed_clip", "text_only")
_CITATION_KEYS = ("item_id", "video_id", "source_revision", "card_hash", "excerpt_id",
                  "quote", "kind", "evidence_kind", "start", "end")
_PACKET_ENVELOPE_KEYS = ("ok", "job_key", "input_hash")
_EXCLUSION_DISPOSITIONS = ("rejected", "unmapped", "unsupported", "deleted", "changed", "cancelled")
_WORK_STATES = ("ready", "leased", "accepted", "unmapped", "unsupported", "blocked", "cancelled")
_DISPOSITIONS = ("waiting", "accepted", "rejected", "unmapped", "unsupported", "pinned",
                 "deleted", "changed", "cancelled")


# --------------------------------------------------------------------------
# Canonical forms
# --------------------------------------------------------------------------
def canonical(value) -> str:
    """The contract's canonical serialization (``library_cards.serialize_card``:
    sorted keys, UTF-8, finite, ``<>&``` escaped), used for every brief hash
    (packet ``input_hash``, ``job_key``, request, citation and artifact
    hashes) and for the stored JSON files (AW-D06). One serializer, one
    address space, under one contract version."""
    return library_cards.serialize_card(value)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def packet_body(packet: dict) -> dict:
    """The hashed part of a packet: everything but the envelope flag and the
    two values derived from it (``job_key``, ``input_hash``)."""
    return {k: v for k, v in packet.items() if k not in _PACKET_ENVELOPE_KEYS}


def job_key_for(date: str, run_id: str, input_hash: str) -> str:
    return digest([date, run_id, input_hash])


def brief_uri(date: str, brief_hash: str) -> str:
    return f"{URI_PREFIX}briefs/{date}/{brief_hash}"


def _normalize_text(text: str) -> str:
    """Phase 2's quote matching rule: NFC, whitespace collapsed."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def _iso(moment: _dt.datetime) -> str:
    return moment.astimezone(_dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_stamp(value) -> _dt.datetime | None:
    """Phase 2 millisecond stamps, ISO strings (naive treated as UTC), or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)) or value < 0:
            return None
        try:
            return _dt.datetime.fromtimestamp(float(value) / 1000.0, tz=_dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if _DIGITS_RE.match(text):
        return _parse_stamp(int(text))
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_dt.timezone.utc)
    return moment.astimezone(_dt.timezone.utc)


def _has_control(text: str, *, allow_whitespace: bool = True) -> bool:
    for ch in text:
        if unicodedata.category(ch) == "Cc":
            if allow_whitespace and ch in "\t\n\r":
                continue
            return True
    return False


# --------------------------------------------------------------------------
# Argument validation
# --------------------------------------------------------------------------
def validate_date(value, name: str = "date") -> str:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise _invalid("bad_date", field=name)
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        raise _invalid("bad_date", field=name) from None
    return value


def validate_id(value, name: str) -> str:
    """Phase 2 id grammar: 1-200 characters, stripped, no control characters."""
    if not isinstance(value, str):
        raise _invalid("bad_string", field=name)
    if not 1 <= len(value) <= BRIEF_LIMITS["max_key_chars"]:
        raise _invalid("string_length", field=name, maximum=BRIEF_LIMITS["max_key_chars"])
    if value != value.strip() or _has_control(value, allow_whitespace=False):
        raise _invalid("malformed_identifier", field=name)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _invalid("string_encoding", field=name) from None
    return value


def validate_submission_key(value) -> str:
    """Phase 2's operation-key grammar plus "no whitespace" (module rule 1)."""
    key = validate_id(value, "submission_key")
    if any(ch.isspace() for ch in key):
        raise _invalid("malformed_identifier", field="submission_key")
    return key


def validate_client_identity(value) -> str:
    if not isinstance(value, str):
        raise _invalid("bad_string", field="client_identity")
    if not 1 <= len(value) <= BRIEF_LIMITS["max_client_identity_chars"]:
        raise _invalid("string_length", field="client_identity",
                       maximum=BRIEF_LIMITS["max_client_identity_chars"])
    if value != value.strip() or _has_control(value, allow_whitespace=False):
        raise _invalid("malformed_identifier", field="client_identity")
    return value


def _hash_field(value, name: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.match(value):
        raise _invalid("bad_hash", field=name)
    return value


def _number_or_none(value, name: str):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid("bad_number", field=name)
    if isinstance(value, float) and not math.isfinite(value):
        raise _invalid("non_finite_number", field=name)
    return float(value)


def validate_document(value) -> str:
    if not isinstance(value, str):
        raise _invalid("bad_string", field="document")
    try:
        raw = value.encode("utf-8")
    except UnicodeEncodeError:
        raise _invalid("string_encoding", field="document") from None
    if len(raw) > BRIEF_LIMITS["max_document_bytes"]:
        raise ResourceError("resource_too_large", details={
            "what": "document", "bytes": len(raw), "limit_bytes": BRIEF_LIMITS["max_document_bytes"]})
    if not value.strip():
        raise _invalid("string_empty", field="document")
    if _has_control(value):
        raise _invalid("string_control_character", field="document")
    return value


def validate_citations(value) -> list[dict]:
    if not isinstance(value, list):
        raise _invalid("bad_array", field="citations")
    if len(value) > BRIEF_LIMITS["max_citations"]:
        raise _invalid("too_many_citations", maximum=BRIEF_LIMITS["max_citations"])
    citations = []
    for position, raw in enumerate(value):
        field = f"citations[{position}]"
        if not isinstance(raw, dict):
            raise _invalid("bad_object", field=field)
        # AW-D04: unknown (client-controlled) names are counted, never echoed.
        unknown_count = sum(1 for k in raw if k not in _CITATION_KEYS)
        if unknown_count:
            raise _invalid("unknown_field", field=field, unknown_field_count=unknown_count,
                           allowed_fields=list(_CITATION_KEYS))
        item_id = raw.get("item_id", raw.get("video_id"))
        if item_id is None:
            raise _invalid("missing_field", field=field, fields=["item_id"])
        validate_id(item_id, f"{field}.item_id")
        if "video_id" in raw and raw["video_id"] != item_id:
            raise _invalid("citation_item_mismatch", field=field)
        for name in ("source_revision", "card_hash", "excerpt_id"):
            if name not in raw:
                raise _invalid("missing_field", field=field, fields=[name])
            _hash_field(raw[name], f"{field}.{name}")
        quote = raw.get("quote")
        if not isinstance(quote, str):
            raise _invalid("bad_string", field=f"{field}.quote")
        if len(quote) > BRIEF_LIMITS["max_quote_codepoints"]:
            raise _invalid("string_too_long", field=f"{field}.quote",
                           maximum_codepoints=BRIEF_LIMITS["max_quote_codepoints"])
        if not quote.strip() or _has_control(quote):
            raise _invalid("citation_quote_empty" if not quote.strip() else "string_control_character",
                           field=f"{field}.quote")
        kind = raw.get("evidence_kind", raw.get("kind"))
        if kind is not None and kind not in _EVIDENCE_KINDS:
            raise _invalid("bad_evidence_kind", field=field)
        if "kind" in raw and "evidence_kind" in raw and raw["kind"] != raw["evidence_kind"]:
            raise _invalid("citation_kind_mismatch", field=field)
        citations.append({
            "item_id": item_id,
            "source_revision": raw["source_revision"],
            "card_hash": raw["card_hash"],
            "excerpt_id": raw["excerpt_id"],
            "quote": quote,
            "evidence_kind": kind,
            "start": _number_or_none(raw.get("start"), f"{field}.start"),
            "end": _number_or_none(raw.get("end"), f"{field}.end"),
        })
    return citations


def normalize_usage(usage, *, document: str, citations: list[dict]) -> dict:
    """Reported usage is kept verbatim; missing usage is ``unavailable`` and
    never becomes zero tokens or a cost. Local byte counts are separate."""
    local = {"document_bytes": len(document.encode("utf-8")), "citation_count": len(citations)}
    if usage is None:
        return {"status": "unavailable", "reported": None, "local": local}
    if not isinstance(usage, dict):
        raise _invalid("bad_object", field="usage")
    if len(usage) > BRIEF_LIMITS["max_usage_keys"]:
        raise _invalid("too_many_fields", field="usage", maximum=BRIEF_LIMITS["max_usage_keys"])
    reported: dict[str, Any] = {}
    # AW-D04: usage keys are client-controlled; refusals report the entry's
    # position, never the key text.
    for position, (key, value) in enumerate(usage.items()):
        if not isinstance(key, str) or not 1 <= len(key) <= 64 or _has_control(key, allow_whitespace=False):
            raise _invalid("bad_field_name", field="usage", position=position)
        if isinstance(value, bool) or value is None or isinstance(value, int):
            pass
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise _invalid("non_finite_number", field="usage", position=position)
        elif isinstance(value, str):
            if len(value) > 200 or _has_control(value, allow_whitespace=False):
                raise _invalid("bad_string", field="usage", position=position)
        else:
            raise _invalid("bad_value", field="usage", position=position)
        if key.endswith("_tokens") and value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise _invalid("bad_integer", field="usage", position=position)
        reported[key] = value
    status = reported.get("status")
    if status is None:
        status = "reported"
    elif not isinstance(status, str) or status not in ("reported", "estimated", "unavailable", "partial"):
        raise _invalid("bad_value", field="usage.status")
    return {"status": status, "reported": reported, "local": local}


def _receipt_usage(usage: dict) -> dict:
    reported = usage.get("reported")
    if isinstance(reported, dict):
        return {**reported, "status": usage.get("status", "reported"), "local": dict(usage.get("local") or {})}
    return {"status": "unavailable", "local": dict(usage.get("local") or {})}


# --------------------------------------------------------------------------
# Atomic files
# --------------------------------------------------------------------------
def _write_bytes_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".tmp-{path.name}-{os.getpid()}-{secrets.token_hex(4)}")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _write_json_atomic(path: Path, value) -> None:
    _write_bytes_atomic(path, canonical(value).encode("utf-8"))


def _read_json(path: Path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


# --------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------
class BriefStore:
    """Prepare bounded brief input and validate/persist client artifacts.

    Reads go through :class:`library_resources.LibraryReader` (one admission
    and one 2 s deadline per operation, the same guard, cards, safety checks
    and renderer as every other bounded read). Writes are the contract's
    atomic-replace, first-accepted-wins, idempotent publication.
    """

    def __init__(self, index, work_service, *, data_root, clock: Callable[[], float] | None = None,
                 wall_clock: Callable[[], float] | None = None, guard: ReadGuard | None = None,
                 reader: LibraryReader | None = None):
        self.work_service = work_service
        self.data_root = Path(data_root) if data_root is not None else None
        self.root = (self.data_root / BRIEF_DIR) if self.data_root is not None else None
        self.reader = reader or LibraryReader(index, data_root=self.data_root, clock=clock,
                                              wall_clock=wall_clock, guard=guard)
        self._local_lock = threading.Lock()

    @classmethod
    def for_reader(cls, reader: LibraryReader, work_service=None) -> "BriefStore":
        """A store sharing an existing request-scoped reader (its index
        binding, admission and deadline)."""
        return cls(None, work_service, data_root=reader.data_root, reader=reader)

    # ---- helpers ------------------------------------------------------
    @property
    def index(self):
        return self.reader.index

    def _require_root(self) -> Path:
        if self.root is None:
            raise ResourceError("feature_unavailable", details={"what": "briefs", "reason": "no_data_root"})
        return self.root

    def _utc_now(self) -> _dt.datetime:
        return self.reader.utc_now().replace(microsecond=0)

    @staticmethod
    def _day_bounds(date: str) -> tuple[_dt.datetime, _dt.datetime]:
        day = _dt.date.fromisoformat(date)
        start = _dt.datetime(day.year, day.month, day.day, tzinfo=_dt.timezone.utc)
        return start, start + _dt.timedelta(days=1)

    def _artifact_dir(self, date: str, brief_hash: str) -> Path:
        return self._require_root() / date / brief_hash

    def _record_path(self, kind: str, key: str) -> Path:
        return self._require_root() / kind / f"{key}.json"

    def _load_record(self, kind: str, key: str) -> dict | None:
        path = self._record_path(kind, key)
        try:
            value = _read_json(path)
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            log.warning("unreadable brief record %s/%s", kind, key[:16])
            return None
        return value if isinstance(value, dict) else None

    def _save_record(self, kind: str, key: str, value: dict) -> None:
        path = self._record_path(kind, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path, value)

    # ---- public surface ----------------------------------------------
    def prepare_input(self, date: str, run_id: str) -> dict:
        date = validate_date(date)
        run_id = validate_id(run_id, "run_id")
        with self.reader._operation() as op:
            now = self._utc_now()
            day_start, day_end = self._day_bounds(date)
            if day_start > now:
                raise _invalid("future_date", field="date")
            as_of = min(now, day_end)
            packet = self._build_packet(op, date, run_id, as_of)
        return packet

    def publish(self, *, job_key: str, input_hash: str, input_packet: dict, submission_key: str,
                document: str, citations: list[dict], usage: dict | None,
                client_identity: str) -> dict:
        with self.reader._operation() as op:
            self._require_root()
            request = self._validate_publish_request(
                job_key=job_key, input_hash=input_hash, input_packet=input_packet,
                submission_key=submission_key, document=document, citations=citations,
                usage=usage, client_identity=client_identity)
            with self._writer_lock(op):
                receipt = self._publish(op, request)
            if isinstance(receipt, dict) and receipt.get("ok") and receipt.get("brief_hash"):
                try:
                    import server
                    hook = getattr(server, "_mirror_event", None)
                    if hook is not None and callable(hook):
                        hook("brief_published", brief_hash=receipt["brief_hash"])
                except Exception:
                    pass
            return receipt

    def validated_dependencies(self, date: str, brief_hash: str) -> list[str]:
        date = validate_date(date)
        brief_hash = _hash_field(brief_hash, "brief_hash")
        with self.reader._operation() as op:
            self._require_root()
            manifest, _document, _citations, packet = self._load_artifact(date, brief_hash)
            op.check()
            self._check_dependencies(op, manifest, packet=packet)
            return [d["item_id"] for d in manifest.get("dependencies") or [] if isinstance(d, dict) and d.get("item_id")]

    def latest_valid(self, utc_date: str) -> dict | None:
        utc_date = validate_date(utc_date, "utc_date")
        with self.reader._operation() as op:
            return self._latest_valid(op, utc_date)

    def read(self, date: str, brief_hash: str) -> dict:
        date = validate_date(date)
        brief_hash = _hash_field(brief_hash, "brief_hash")
        with self.reader._operation() as op:
            manifest, text = self._render(op, date, brief_hash)
        return _success(uri=brief_uri(date, brief_hash), date=date, brief_hash=brief_hash,
                        accepted_at=manifest.get("accepted_at"),
                        contents=[{"uri": brief_uri(date, brief_hash), "mimeType": MIME_TYPE, "text": text}])

    def purge_dependents(self, video_id: str) -> dict:
        video_id = validate_id(video_id, "video_id")
        with self.reader._operation() as op:
            self._require_root()
            with self._writer_lock(op):
                return self._purge(op, video_id)

    # ---- reader seams (same admission as the calling reader) ----------
    def render_for_reader(self, op, date: str, brief_hash: str) -> str:
        _manifest, text = self._render(op, date, brief_hash)
        return text

    def latest_valid_entry(self, op) -> dict | None:
        """The curated list's "latest valid brief": the newest valid artifact
        among the most recent dates, bounded work."""
        root = self.root
        if root is None or not root.is_dir():
            return None
        try:
            dates = sorted((p.name for p in root.iterdir() if p.is_dir() and _DATE_RE.match(p.name)), reverse=True)
        except OSError:
            return None
        for date in dates[:BRIEF_LIMITS["max_discovery_dates"]]:
            op.check()
            try:
                validate_date(date)
            except ResourceError:
                continue
            found = self._latest_valid(op, date)
            if found is not None:
                return found
        return None

    # ---- packet ---------------------------------------------------------
    def _sql(self, sql: str, params: tuple = ()) -> list[dict]:
        return self.reader._sql(sql, params)

    def _has_tables(self, names: tuple[str, ...]) -> bool:
        return self.reader._has_tables(names)

    def _build_packet(self, op, date: str, run_id: str, as_of: _dt.datetime) -> dict:
        with self.reader._lock(op):
            return self._locked_build_packet(op, date, run_id, as_of)

    def _locked_build_packet(self, op, date: str, run_id: str, as_of: _dt.datetime) -> dict:
        day_start, day_end = self._day_bounds(date)

        def covered(moment: _dt.datetime | None) -> bool:
            return moment is not None and day_start <= moment <= as_of and moment < day_end

        coverage: dict[str, Any] = {
            "captures": "complete",
            "capture_time_note": "Naive capture stamps are treated as UTC.",
        }
        counts: dict[str, Any] = {}
        bindings: dict[str, Any] = {"run": {"run_id": run_id, "found": False, "run_revision": None,
                                            "manifest_hash": None, "state": None, "version_id": None}}
        work_rows: list[dict] = []
        exclusions: list[dict] = []

        # Captures inside the covered interval.
        rows = self._sql("SELECT video_id, yoinked_at FROM yoinks WHERE deleted_at IS NULL")
        op.check()
        counts["captures"] = sum(1 for row in rows if covered(_parse_stamp(row.get("yoinked_at"))))

        phase2 = ("library_meta", "shelf_versions", "library_runs", "library_work",
                  "library_manifest", "library_applies")
        if self._has_tables(phase2):
            meta = self._sql("SELECT projection_revision, active_version_id, last_operation_sequence, "
                             "recovery_state FROM library_meta WHERE singleton=1")
            op.check()
            meta_row = meta[0] if meta else {}
            taxonomy_revision = None
            if meta_row.get("active_version_id"):
                version = self._sql("SELECT revision_hash FROM shelf_versions WHERE version_id=?",
                                    (meta_row["active_version_id"],))
                taxonomy_revision = version[0]["revision_hash"] if version else None
            bindings["projection_revision"] = int(meta_row.get("projection_revision") or 0)
            bindings["taxonomy_revision"] = taxonomy_revision
            bindings["active_version_id"] = meta_row.get("active_version_id")
            bindings["recovery_state"] = meta_row.get("recovery_state")

            run = self._sql("SELECT run_id, version_id, manifest_hash, run_revision, state "
                            "FROM library_runs WHERE run_id=?", (run_id,))
            op.check()
            if run:
                bindings["run"] = {"run_id": run_id, "found": True, "run_revision": int(run[0]["run_revision"]),
                                   "manifest_hash": run[0]["manifest_hash"], "state": run[0]["state"],
                                   "version_id": run[0]["version_id"]}
            queue = self._sql("SELECT work_id, video_id, state, packet_generation, packet_hash, attempts, "
                              "priority, created_at, updated_at FROM library_work WHERE run_id=? "
                              "ORDER BY state, priority, created_at, work_id", (run_id,))
            op.check()
            manifest = self._sql("SELECT video_id, source_revision, disposition, reason FROM library_manifest "
                                 "WHERE run_id=? ORDER BY video_id", (run_id,))
            op.check()
            bindings["queue_digest"] = digest({"work": queue, "manifest": manifest})
            counts["run_queue_by_state"] = {state: sum(1 for w in queue if w["state"] == state)
                                            for state in _WORK_STATES}
            counts["run_dispositions"] = {d: sum(1 for m in manifest if m["disposition"] == d)
                                          for d in _DISPOSITIONS}
            counts["work_rows_total"] = len(queue)
            work_rows = [{"work_id": w["work_id"], "item_id": w["video_id"], "state": w["state"],
                          "packet_generation": w["packet_generation"], "packet_hash": w["packet_hash"],
                          "attempts": w["attempts"], "priority": w["priority"],
                          "created_at": w["created_at"], "updated_at": w["updated_at"]}
                         for w in queue[:BRIEF_LIMITS["max_work_rows"]]]
            exclusions = [{"item_id": m["video_id"], "disposition": m["disposition"],
                           "reason": label(m.get("reason"), 200) or None}
                          for m in manifest if m["disposition"] in _EXCLUSION_DISPOSITIONS]
            counts["exclusions_total"] = len(exclusions)
            exclusions = exclusions[:BRIEF_LIMITS["max_queue_exclusions"]]
            global_queue = self._sql("SELECT state, COUNT(*) AS n FROM library_work GROUP BY state")
            op.check()
            counts["queue_by_state"] = {state: 0 for state in _WORK_STATES}
            for row in global_queue:
                if row["state"] in counts["queue_by_state"]:
                    counts["queue_by_state"][row["state"]] = int(row["n"])

            applies = self._sql("SELECT apply_id, kind, operation_sequence, created_at FROM library_applies")
            op.check()
            latest_sequence = 0
            applied = 0
            for row in applies:
                moment = _parse_stamp(row.get("created_at"))
                if moment is not None and moment <= as_of:
                    latest_sequence = max(latest_sequence, int(row.get("operation_sequence") or 0))
                if covered(moment):
                    applied += 1
            bindings["latest_covered_operation_sequence"] = latest_sequence
            counts["applied_changes"] = applied
            versions = self._sql("SELECT version_id, created_at, approved_at FROM shelf_versions")
            op.check()
            counts["shelf_revisions"] = sum(
                1 for row in versions if covered(_parse_stamp(row.get("approved_at") or row.get("created_at"))))
            coverage["queue"] = "complete"
            coverage["applied_changes"] = "complete"
            coverage["shelf_revisions"] = "complete"
            coverage["run"] = "complete" if bindings["run"]["found"] else "run_not_recorded"
        else:
            bindings.update(projection_revision=None, taxonomy_revision=None, active_version_id=None,
                            recovery_state=None, queue_digest=digest({"work": [], "manifest": []}),
                            latest_covered_operation_sequence=0)
            counts.update(run_queue_by_state=None, run_dispositions=None, work_rows_total=0,
                          exclusions_total=0, queue_by_state=None, applied_changes=None, shelf_revisions=None)
            coverage.update(queue="unavailable", applied_changes="unavailable", shelf_revisions="unavailable",
                            run="unavailable",
                            gap="Coverage gap: Phase 2 tables are not present, so queue state, applied "
                                "changes and shelf revisions are not covered. Captures are complete.")

        # Evidence sample: recent eligible items by capture time descending, then item id.
        candidates = self._sql("SELECT video_id FROM yoinks WHERE deleted_at IS NULL "
                               "ORDER BY yoinked_at DESC, video_id ASC LIMIT ?",
                               (BRIEF_LIMITS["max_cards"] * 4,))
        op.check()
        cards: list[dict] = []
        omitted: list[dict] = []
        for row in candidates:
            op.check()
            if len(cards) >= BRIEF_LIMITS["max_cards"]:
                break
            item_id = row["video_id"]
            bundle = self.reader._bundle(op, item_id)
            if bundle.error is not None:
                omitted.append({"item_id": item_id, "reason": bundle.error.code})
                continue
            card = bundle.card
            cards.append({"item_id": item_id, "source_revision": card["source_revision"],
                          "card_hash": card["card_hash"], "card_uri": card_uri(item_id, card),
                          "card": card})
        counts["sampled_items"] = len(cards)
        counts["sample_candidates"] = len(candidates)

        body: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "date": date,
            "run_id": run_id,
            "as_of": _iso(as_of),
            "interval": {"start": _iso(day_start), "end": _iso(day_end), "covered_end": _iso(as_of),
                         "rule": "[start, end) selected by UTC date; covered through as_of"},
            "bindings": bindings,
            "counts": counts,
            "coverage": coverage,
            "work_rows": work_rows,
            "queue_exclusions": exclusions,
            "cards": cards,
            "sampling": {
                "rule": "recent eligible items by capture time descending, then item id; "
                        "at most 5 default Librarian cards; whole cards omitted to fit 24,576 bytes",
                "sampled_items": [c["item_id"] for c in cards],
                "omitted_items": omitted,
                "omitted_for_size": [],
                "work_rows_omitted": max(0, counts.get("work_rows_total", 0) - len(work_rows)),
                "exclusions_omitted": max(0, counts.get("exclusions_total", 0) - len(exclusions)),
            },
        }
        return self._fit_packet(body)

    @staticmethod
    def _seal(body: dict) -> dict:
        input_hash = digest(body)
        packet = {"ok": True, **body, "input_hash": input_hash,
                  "job_key": job_key_for(body["date"], body["run_id"], input_hash)}
        return packet

    def _fit_packet(self, body: dict) -> dict:
        limit = BRIEF_LIMITS["max_packet_bytes"]
        while True:
            packet = self._seal(body)
            size = len(json.dumps(packet, ensure_ascii=False).encode("utf-8"))
            if size <= limit:
                return packet
            if body["cards"]:
                dropped = body["cards"].pop()
                body["sampling"]["omitted_for_size"].append(dropped["item_id"])
                body["sampling"]["sampled_items"] = [c["item_id"] for c in body["cards"]]
                body["counts"]["sampled_items"] = len(body["cards"])
                continue
            if body["work_rows"]:
                body["work_rows"].pop()
                body["sampling"]["work_rows_omitted"] += 1
                continue
            if body["queue_exclusions"]:
                body["queue_exclusions"].pop()
                body["sampling"]["exclusions_omitted"] += 1
                continue
            raise ResourceError("resource_too_large", details={"what": "brief_input", "bytes": size, "limit_bytes": limit})

    # ---- publication ----------------------------------------------------
    def _validate_publish_request(self, *, job_key, input_hash, input_packet, submission_key, document,
                                  citations, usage, client_identity) -> dict:
        submission_key = validate_submission_key(submission_key)
        client_identity = validate_client_identity(client_identity)
        job_key = _hash_field(job_key, "job_key")
        input_hash = _hash_field(input_hash, "input_hash")
        if not isinstance(input_packet, dict):
            raise _invalid("bad_object", field="input_packet")
        document = validate_document(document)
        citations = validate_citations(citations)
        usage_record = normalize_usage(usage, document=document, citations=citations)
        request = {"job_key": job_key, "input_hash": input_hash, "input_packet": input_packet,
                   "submission_key": submission_key, "document": document, "citations": citations,
                   "usage": usage}
        try:
            size = wire_bytes(request)
        except (TypeError, ValueError):
            raise _invalid("bad_object", field="input_packet") from None
        if size > BRIEF_LIMITS["max_request_bytes"]:
            raise ResourceError("resource_too_large", details={
                "what": "publish_library_brief", "bytes": size, "limit_bytes": BRIEF_LIMITS["max_request_bytes"]})
        body = packet_body(input_packet)
        if input_packet.get("ok") not in (None, True):
            raise _invalid("bad_packet", reason="not_a_success_packet")
        request_hash = digest({"job_key": job_key, "input_hash": input_hash, "input_packet": body,
                               "document": document, "citations": citations, "usage": usage,
                               "client_identity": client_identity})
        return {
            "job_key": job_key, "input_hash": input_hash, "packet_body": body,
            "submission_key": submission_key,
            "submission_key_hash": hashlib.sha256(submission_key.encode("utf-8")).hexdigest(),
            "document": document, "citations": citations, "usage": usage_record,
            "client_identity": client_identity, "request_hash": request_hash,
        }

    @contextlib.contextmanager
    def _writer_lock(self, op) -> Iterator[None]:
        """Serialize publication across threads and processes (rule 5)."""
        root = self._require_root()
        wait_s = BRIEF_LIMITS["writer_wait_s"]
        if not self._local_lock.acquire(timeout=wait_s):
            raise ResourceError("rate_limited", details={"reason": "concurrency", "retry_after_ms": 250,
                                                         "what": "brief_writer"})
        lock_path = root / ".publish.lock"
        fd = None
        try:
            root.mkdir(parents=True, exist_ok=True)
            started = time.monotonic()
            while True:
                try:
                    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.write(fd, str(os.getpid()).encode("ascii"))
                    break
                except FileExistsError:
                    try:
                        age = time.time() - os.stat(lock_path).st_mtime
                    except OSError:
                        age = 0.0
                    if age > BRIEF_LIMITS["stale_lock_s"]:
                        with contextlib.suppress(OSError):
                            os.unlink(lock_path)
                        continue
                    if time.monotonic() - started > wait_s:
                        raise ResourceError("rate_limited", details={
                            "reason": "concurrency", "retry_after_ms": 250, "what": "brief_writer"})
                    time.sleep(0.02)
                except OSError as exc:
                    raise ResourceError("library_unavailable", details={"storage": type(exc).__name__}) from exc
            op.check()
            yield
        finally:
            if fd is not None:
                with contextlib.suppress(OSError):
                    os.close(fd)
                with contextlib.suppress(OSError):
                    os.unlink(lock_path)
            self._local_lock.release()

    def _find_job_winner(self, job_key: str, date: str | None) -> dict | None:
        record = self._load_record("jobs", job_key)
        if record is not None:
            return record
        if date is None:
            return None
        # A publication interrupted between the artifact and its job record
        # still counts: the artifact is complete and discoverable.
        for manifest in self._manifests(date):
            if manifest.get("job_key") == job_key:
                return {"job_key": job_key, "brief_hash": manifest.get("brief_hash"),
                        "request_hash": manifest.get("request_hash"), "date": date,
                        "accepted_at": manifest.get("accepted_at")}
        return None

    def _publish(self, op, request: dict) -> dict:
        # 1. Recorded receipt identity comes before freshness.
        record = self._load_record("submissions", request["submission_key_hash"])
        if record is not None:
            if record.get("request_hash") == request["request_hash"] and isinstance(record.get("receipt"), dict):
                return _success(**record["receipt"])
            raise ResourceError("idempotency_conflict", details={"next_step": "use a new submission_key"})

        # 2. The packet must be the one this store sealed: hash and job key rebuilt from it.
        body = request["packet_body"]
        try:
            date = validate_date(body.get("date"))
            run_id = validate_id(body.get("run_id"), "run_id")
            as_of = _parse_stamp(body.get("as_of"))
        except ResourceError:
            raise _invalid("bad_packet", reason="packet_identity") from None
        if as_of is None:
            raise _invalid("bad_packet", reason="packet_as_of")
        if digest(body) != request["input_hash"]:
            raise _invalid("input_hash_mismatch")
        if job_key_for(date, run_id, request["input_hash"]) != request["job_key"]:
            raise _invalid("job_key_mismatch")
        day_start, day_end = self._day_bounds(date)
        now = self._utc_now()
        if not (day_start <= as_of <= day_end) or as_of > now:
            raise _invalid("bad_packet", reason="as_of_out_of_range")
        op.check()

        # 3. First accepted artifact for the job wins.
        winner = self._find_job_winner(request["job_key"], date)
        if winner is not None:
            if winner.get("request_hash") == request["request_hash"] and winner.get("brief_hash"):
                # The same request already won (records may be missing after
                # an interrupted publication): answer with its receipt.
                receipt = self._load_record("receipts", winner["brief_hash"])
                if receipt is not None and isinstance(receipt.get("receipt"), dict):
                    return _success(**receipt["receipt"])
                try:
                    manifest, _document, _citations, _packet = self._load_artifact(date, winner["brief_hash"])
                except ResourceError:
                    manifest = None
                if manifest is not None:
                    receipt = self._receipt_from_manifest(manifest)
                    self._save_records(request, receipt)
                    return _success(**receipt)
            raise ResourceError("brief_conflict", details={"accepted_brief_hash": winner.get("brief_hash"),
                                                           "next_step": "read the accepted brief"})

        # 4. Freshness: rebuild against current authoritative data with the original date/as_of.
        fresh = packet_body(self._build_packet(op, date, run_id, as_of))
        if canonical(fresh) != canonical(body):
            raise ResourceError("stale_brief", details={"next_step": "get_library_brief_input"})
        op.check()

        # 5. Citations bind supplied evidence only.
        cards = {entry["item_id"]: entry for entry in fresh.get("cards") or []}
        bound_citations = [self._bind_citation(position, citation, cards)
                           for position, citation in enumerate(request["citations"])]

        # 6. Persist: artifact directory first (atomic rename), then the records.
        accepted = self._utc_now()
        dependencies = [{"item_id": entry["item_id"], "source_revision": entry["source_revision"],
                         "card_hash": entry["card_hash"]} for entry in cards.values()]
        document = request["document"]
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "date": date,
            "run_id": run_id,
            "as_of": body["as_of"],
            "job_key": request["job_key"],
            "input_hash": request["input_hash"],
            "request_hash": request["request_hash"],
            "submission_key_hash": request["submission_key_hash"],
            "client_identity": request["client_identity"],
            "accepted_at": _iso(accepted),
            "accepted_at_ms": int(accepted.timestamp() * 1000),
            "document_hash": hashlib.sha256(document.encode("utf-8")).hexdigest(),
            "document_bytes": len(document.encode("utf-8")),
            "citations_hash": digest(bound_citations),
            "citation_count": len(bound_citations),
            "dependencies": dependencies,
            "usage": request["usage"],
        }
        brief_hash = digest({"manifest": manifest, "document": document, "citations": bound_citations,
                             "packet": body})
        manifest["brief_hash"] = brief_hash
        self._write_artifact(date, brief_hash, manifest, document, bound_citations, body, op=op)
        receipt = self._receipt_from_manifest(manifest)
        self._save_records(request, receipt)
        op.check()
        return _success(**receipt)

    @staticmethod
    def _receipt_from_manifest(manifest: dict) -> dict:
        """The content-free receipt: hashes, status, timestamps and usage."""
        return {
            "brief_hash": manifest["brief_hash"],
            "date": manifest["date"],
            "uri": brief_uri(manifest["date"], manifest["brief_hash"]),
            "job_key": manifest["job_key"],
            "input_hash": manifest["input_hash"],
            "request_hash": manifest["request_hash"],
            "accepted_at": manifest["accepted_at"],
            "status": "accepted",
            "document_hash": manifest["document_hash"],
            "citations_hash": manifest["citations_hash"],
            "citation_count": manifest["citation_count"],
            "usage": _receipt_usage(manifest.get("usage") or {}),
        }

    def _save_records(self, request: dict, receipt: dict) -> None:
        brief_hash = receipt["brief_hash"]
        self._save_record("jobs", request["job_key"], {
            "job_key": request["job_key"], "brief_hash": brief_hash, "request_hash": request["request_hash"],
            "date": receipt["date"], "accepted_at": receipt["accepted_at"]})
        self._save_record("submissions", request["submission_key_hash"], {
            "submission_key_hash": request["submission_key_hash"], "request_hash": request["request_hash"],
            "brief_hash": brief_hash, "receipt": receipt})
        self._save_record("receipts", brief_hash, {
            "brief_hash": brief_hash, "job_key": request["job_key"], "date": receipt["date"],
            "request_hash": request["request_hash"], "accepted_at": receipt["accepted_at"],
            "status": "accepted", "receipt": receipt})

    @staticmethod
    def _bind_citation(position: int, citation: dict, cards: dict[str, dict]) -> dict:
        field = f"citations[{position}]"
        entry = cards.get(citation["item_id"])
        if entry is None:
            raise _invalid("citation_item_not_supplied", field=field)
        if citation["source_revision"] != entry["source_revision"]:
            raise _invalid("citation_revision_mismatch", field=field)
        if citation["card_hash"] != entry["card_hash"]:
            raise _invalid("citation_card_hash_mismatch", field=field)
        excerpt = next((e for e in entry["card"].get("excerpts") or []
                        if e.get("excerpt_id") == citation["excerpt_id"]), None)
        if excerpt is None:
            raise _invalid("citation_excerpt_unknown", field=field)
        kind = excerpt.get("evidence_kind")
        if citation["evidence_kind"] is not None and citation["evidence_kind"] != kind:
            raise _invalid("citation_kind_mismatch", field=field)
        for bound in ("start", "end"):
            expected = excerpt.get(bound)
            given = citation.get(bound)
            if given is None and expected is None:
                continue
            if given is None or expected is None or abs(float(given) - float(expected)) > 1e-6:
                raise _invalid("citation_bounds_mismatch", field=field)
        needle = _normalize_text(citation["quote"])
        haystack = _normalize_text(excerpt.get("text") or "")
        if not needle or needle not in haystack:
            raise _invalid("citation_quote_not_found", field=field)
        return {
            "item_id": citation["item_id"], "source_revision": citation["source_revision"],
            "card_hash": citation["card_hash"], "excerpt_id": citation["excerpt_id"],
            "quote": citation["quote"], "evidence_kind": kind,
            "start": expected_bound(excerpt.get("start")), "end": expected_bound(excerpt.get("end")),
        }

    def _write_artifact(self, date: str, brief_hash: str, manifest: dict, document: str,
                        citations: list[dict], packet: dict, op=None) -> None:
        root = self._require_root()
        final = root / date / brief_hash
        if final.is_dir() and (final / "manifest.json").is_file():
            return  # same hash means byte-identical content: already accepted
        tmp = root / date / f".tmp-{brief_hash[:16]}-{os.getpid()}-{secrets.token_hex(4)}"
        try:
            tmp.mkdir(parents=True, exist_ok=False)
            _write_bytes_atomic(tmp / "document.md", document.encode("utf-8"))
            _write_json_atomic(tmp / "citations.json", citations)
            _write_json_atomic(tmp / "packet.json", packet)
            _write_json_atomic(tmp / "manifest.json", manifest)
            if op is None:
                with self.reader._operation() as fresh_op:
                    with self.reader._lock(fresh_op):
                        self._recheck_publication_bindings(fresh_op, packet, manifest)
                        os.replace(tmp, final)
            else:
                with self.reader._lock(op):
                    # Recheck every source/queue/run/taxonomy/projection binding at the atomic publication step
                    self._recheck_publication_bindings(op, packet, manifest)
                    os.replace(tmp, final)
        except ResourceError:
            with contextlib.suppress(OSError):
                shutil.rmtree(tmp, ignore_errors=True)
            raise
        except OSError as exc:
            with contextlib.suppress(OSError):
                shutil.rmtree(tmp, ignore_errors=True)
            if final.is_dir() and (final / "manifest.json").is_file():
                return
            raise ResourceError("library_unavailable", details={"storage": type(exc).__name__}) from exc

    def _recheck_publication_bindings(self, op, packet: dict, manifest: dict) -> None:
        """Recheck all source/queue/run/taxonomy/projection bindings immediately before atomic publication."""
        if op is None:
            with self.reader._operation() as fresh_op:
                return self._recheck_publication_bindings(fresh_op, packet, manifest)

        with self.reader._lock(op):
            # 1. Recheck every source card dependency
            for dependency in manifest.get("dependencies") or []:
                op.check()
                item_id = dependency.get("item_id")
                try:
                    self.reader._snapshot_item(op, item_id)
                except ResourceError:
                    raise ResourceError("stale_brief", details={
                        "reason": "source_deleted", "item_id": item_id, "next_step": "get_library_brief_input"})
                if hasattr(op, "cache"):
                    op.cache.pop(("bundle", item_id), None)
                bundle = self.reader._bundle(op, item_id)
                if bundle.error is not None:
                    raise ResourceError("stale_brief", details={
                        "reason": "source_deleted", "item_id": item_id, "next_step": "get_library_brief_input"})
                card = bundle.card
                if (card.get("card_hash") != dependency.get("card_hash")
                        or card.get("source_revision") != dependency.get("source_revision")):
                    raise ResourceError("stale_brief", details={
                        "reason": "source_changed", "item_id": item_id, "next_step": "get_library_brief_input"})

            # 2. Phase 2 bindings
            bindings = packet.get("bindings") or {}
            phase2 = ("library_meta", "shelf_versions", "library_runs", "library_work", "library_manifest", "library_applies")
            if self._has_tables(phase2):
                meta = self._sql("SELECT projection_revision, active_version_id, last_operation_sequence, recovery_state FROM library_meta WHERE singleton=1")
                meta_row = meta[0] if meta else {}
                if int(meta_row.get("projection_revision") or 0) != bindings.get("projection_revision"):
                    raise ResourceError("stale_brief", details={"reason": "projection_changed", "next_step": "get_library_brief_input"})
                if meta_row.get("active_version_id") != bindings.get("active_version_id"):
                    raise ResourceError("stale_brief", details={"reason": "active_version_changed", "next_step": "get_library_brief_input"})
                if meta_row.get("recovery_state") != bindings.get("recovery_state"):
                    raise ResourceError("stale_brief", details={"reason": "recovery_state_changed", "next_step": "get_library_brief_input"})

                taxonomy_revision = None
                if meta_row.get("active_version_id"):
                    version = self._sql("SELECT revision_hash FROM shelf_versions WHERE version_id=?", (meta_row["active_version_id"],))
                    taxonomy_revision = version[0]["revision_hash"] if version else None
                if taxonomy_revision != bindings.get("taxonomy_revision"):
                    raise ResourceError("stale_brief", details={"reason": "taxonomy_changed", "next_step": "get_library_brief_input"})

                run_id = packet.get("run_id")
                run = self._sql("SELECT run_id, version_id, manifest_hash, run_revision, state FROM library_runs WHERE run_id=?", (run_id,))
                bound_run = bindings.get("run") or {}
                if bound_run.get("found"):
                    if not run:
                        raise ResourceError("stale_brief", details={"reason": "run_deleted", "next_step": "get_library_brief_input"})
                    if (int(run[0]["run_revision"]) != bound_run.get("run_revision") or
                            run[0]["manifest_hash"] != bound_run.get("manifest_hash") or
                            run[0]["state"] != bound_run.get("state") or
                            run[0]["version_id"] != bound_run.get("version_id")):
                        raise ResourceError("stale_brief", details={"reason": "run_changed", "next_step": "get_library_brief_input"})
                else:
                    if run:
                        raise ResourceError("stale_brief", details={"reason": "run_created", "next_step": "get_library_brief_input"})

                queue = self._sql("SELECT work_id, video_id, state, packet_generation, packet_hash, attempts, priority, created_at, updated_at FROM library_work WHERE run_id=? ORDER BY state, priority, created_at, work_id", (run_id,))
                manifest_rows = self._sql("SELECT video_id, source_revision, disposition, reason FROM library_manifest WHERE run_id=? ORDER BY video_id", (run_id,))
                if digest({"work": queue, "manifest": manifest_rows}) != bindings.get("queue_digest"):
                    raise ResourceError("stale_brief", details={"reason": "queue_changed", "next_step": "get_library_brief_input"})

    # ---- reading ---------------------------------------------------------
    def _manifests(self, date: str) -> list[dict]:
        root = self.root
        if root is None:
            return []
        day = root / date
        manifests: list[dict] = []
        try:
            entries = list(day.iterdir())
        except OSError:
            return []
        for entry in entries:
            if not entry.is_dir() or not _HEX64_RE.match(entry.name):
                continue
            try:
                manifest = _read_json(entry / "manifest.json")
            except (OSError, ValueError):
                continue
            if isinstance(manifest, dict) and manifest.get("brief_hash") == entry.name:
                manifests.append(manifest)
        return manifests

    def _load_artifact(self, date: str, brief_hash: str) -> tuple[dict, str, list[dict], dict]:
        folder = self._artifact_dir(date, brief_hash)
        try:
            manifest = _read_json(folder / "manifest.json")
            document = (folder / "document.md").read_bytes().decode("utf-8")
            citations = _read_json(folder / "citations.json")
            packet = _read_json(folder / "packet.json")
        except FileNotFoundError:
            receipt = self._load_record("receipts", brief_hash)
            if receipt is not None and receipt.get("date") == date and receipt.get("status") in ("purged", "deleted"):
                raise ResourceError("resource_deleted", details={"what": "brief"}) from None
            raise ResourceError("resource_not_found", details={"what": "brief"}) from None
        except (OSError, ValueError) as exc:
            raise ResourceError("library_unavailable", details={"storage": type(exc).__name__}) from exc
        if not isinstance(manifest, dict) or not isinstance(citations, list) or not isinstance(packet, dict):
            raise ResourceError("internal_error", details={"reason": "artifact_shape"})
        check = {k: v for k, v in manifest.items() if k != "brief_hash"}
        if digest({"manifest": check, "document": document, "citations": citations, "packet": packet}) != brief_hash \
                or manifest.get("brief_hash") != brief_hash or manifest.get("date") != date:
            raise ResourceError("internal_error", details={"reason": "artifact_integrity"})
        return manifest, document, citations, packet

    def _check_dependencies(self, op, manifest: dict, packet: dict | None = None) -> None:
        """Source deletion, changed card, or changed projection revision makes the brief unavailable now."""
        for dependency in manifest.get("dependencies") or []:
            op.check()
            item_id = dependency.get("item_id")
            if not isinstance(item_id, str):
                raise ResourceError("internal_error", details={"reason": "dependency_shape"})
            bundle = self.reader._bundle(op, item_id)
            if bundle.error is not None:
                if bundle.error.code in ("resource_not_found", "resource_deleted"):
                    raise ResourceError("resource_deleted", details={"what": "brief_dependency"})
                raise ResourceError("revision_unavailable", details={"reason": "dependency_unreadable",
                                                                     "next_step": "get_library_brief_input"})
            card = bundle.card
            if (card.get("card_hash") != dependency.get("card_hash")
                    or card.get("source_revision") != dependency.get("source_revision")):
                raise ResourceError("revision_unavailable", details={"reason": "dependency_changed",
                                                                     "next_step": "get_library_brief_input"})

        if packet is None:
            try:
                date = manifest.get("date")
                b_hash = manifest.get("brief_hash")
                if date and b_hash:
                    packet = _read_json(self._artifact_dir(date, b_hash) / "packet.json")
            except Exception:
                packet = None

        if isinstance(packet, dict):
            bindings = packet.get("bindings") or {}
            bound_proj = bindings.get("projection_revision")
            if bound_proj is not None and self._has_tables(("library_meta",)):
                meta = self._sql("SELECT projection_revision FROM library_meta WHERE singleton=1")
                if meta:
                    curr_proj = int(meta[0]["projection_revision"])
                    if curr_proj != bound_proj:
                        raise ResourceError("revision_unavailable", details={
                            "reason": "projection_changed", "expected": bound_proj,
                            "actual": curr_proj, "next_step": "get_library_brief_input"})
            bound_tax = bindings.get("taxonomy_revision")
            if bound_tax is not None and self._has_tables(("library_meta", "shelf_versions")):
                meta = self._sql("SELECT active_version_id FROM library_meta WHERE singleton=1")
                if meta and meta[0].get("active_version_id"):
                    version = self._sql("SELECT revision_hash FROM shelf_versions WHERE version_id=?",
                                        (meta[0]["active_version_id"],))
                    curr_tax = version[0]["revision_hash"] if version else None
                    if curr_tax != bound_tax:
                        raise ResourceError("revision_unavailable", details={
                            "reason": "taxonomy_changed", "expected": bound_tax,
                            "actual": curr_tax, "next_step": "get_library_brief_input"})
            bound_run = bindings.get("run") or {}
            if bound_run.get("found") and self._has_tables(("library_runs",)):
                run_id = bound_run.get("run_id") or packet.get("run_id")
                if run_id:
                    run = self._sql("SELECT run_id, run_revision, manifest_hash, state, version_id FROM library_runs WHERE run_id=?", (run_id,))
                    if not run:
                        raise ResourceError("revision_unavailable", details={
                            "reason": "run_deleted", "next_step": "get_library_brief_input"})
                    if (int(run[0]["run_revision"]) != bound_run.get("run_revision") or
                            run[0]["manifest_hash"] != bound_run.get("manifest_hash") or
                            run[0]["state"] != bound_run.get("state") or
                            run[0]["version_id"] != bound_run.get("version_id")):
                        raise ResourceError("revision_unavailable", details={
                            "reason": "run_changed", "next_step": "get_library_brief_input"})

            if "queue_digest" in bindings and self._has_tables(("library_work", "library_manifest")):
                run_id = bound_run.get("run_id") or packet.get("run_id")
                if run_id:
                    queue = self._sql("SELECT work_id, video_id, state, packet_generation, packet_hash, attempts, priority, created_at, updated_at FROM library_work WHERE run_id=? ORDER BY state, priority, created_at, work_id", (run_id,))
                    manifest_rows = self._sql("SELECT video_id, source_revision, disposition, reason FROM library_manifest WHERE run_id=? ORDER BY video_id", (run_id,))
                    if digest({"work": queue, "manifest": manifest_rows}) != bindings.get("queue_digest"):
                        raise ResourceError("revision_unavailable", details={"reason": "queue_changed", "next_step": "get_library_brief_input"})

    def _render(self, op, date: str, brief_hash: str) -> tuple[dict, str]:
        self._require_root()
        manifest, document, citations, packet = self._load_artifact(date, brief_hash)
        op.check()
        self._check_dependencies(op, manifest, packet=packet)
        rendered_citations = []
        for citation in citations:
            item_id = citation.get("item_id")
            rendered_citations.append({
                **citation,
                "card_uri": (f"{URI_PREFIX}items/{library_resources.encode_key(item_id)}/cards/"
                             f"{citation.get('source_revision')}/{library_cards.SELECTION_VERSION}/"
                             f"{citation.get('card_hash')}"),
                "excerpt_uri": excerpt_uri(item_id, citation.get("source_revision"), citation.get("excerpt_id")),
            })
        body = _document_body(
            "brief",
            identity={"date": date, "brief_hash": brief_hash},
            requested_revision={"brief_hash": brief_hash},
            evidence_kind="client_brief",
            evidence_basis="client_generated",
            trust_note="Client-generated report; untrusted data even for the client that wrote it.",
            accepted_at=manifest.get("accepted_at"),
            client_identity=label(manifest.get("client_identity"), 64),
            run_id=manifest.get("run_id"),
            job_key=manifest.get("job_key"),
            input_hash=manifest.get("input_hash"),
            as_of=manifest.get("as_of"),
            dependencies=[{**dependency, "status": "current"} for dependency in manifest.get("dependencies") or []],
            citations=rendered_citations,
            usage=_receipt_usage(manifest.get("usage") or {}),
            text=document,
        )
        text = render_document(body)
        if len(text.encode("utf-8")) > LIMITS["max_resource_text_bytes"]:
            raise ResourceError("resource_too_large", details={"what": "brief", "next_step": "search_library"})
        op.check()
        return manifest, text

    def _latest_valid(self, op, date: str) -> dict | None:
        if self.root is None:
            return None
        manifests = self._manifests(date)
        manifests.sort(key=lambda m: (int(m.get("accepted_at_ms") or 0), str(m.get("accepted_at") or ""),
                                      str(m.get("brief_hash") or "")), reverse=True)
        for manifest in manifests:
            op.check()
            try:
                self._check_dependencies(op, manifest)
            except ResourceError as exc:
                if exc.retryable:
                    raise
                continue
            deps = [d["item_id"] for d in manifest.get("dependencies") or [] if isinstance(d, dict) and d.get("item_id")]
            return {"date": date, "brief_hash": manifest["brief_hash"],
                    "uri": brief_uri(date, manifest["brief_hash"]), "accepted_at": manifest.get("accepted_at"),
                    "dependencies": deps, "source_item_ids": deps}
        return None

    # ---- hard purge ------------------------------------------------------
    def _purge(self, op, video_id: str) -> dict:
        root = self._require_root()
        purged: list[str] = []
        interrupted = 0
        if not root.is_dir():
            return _success(video_id=video_id, purged_count=0, purged=[], interrupted_removed=0)
        try:
            dates = [p for p in root.iterdir() if p.is_dir() and _DATE_RE.match(p.name)]
        except OSError as exc:
            raise ResourceError("library_unavailable", details={"storage": type(exc).__name__}) from exc
        for day in sorted(dates):
            op.check()
            try:
                entries = list(day.iterdir())
            except OSError:
                continue
            for entry in entries:
                op.check()
                if not entry.is_dir():
                    continue
                if entry.name.startswith(".tmp-"):
                    # Interrupted publications are never advertised; remove
                    # those that name the item or cannot be inspected.
                    depends = True
                    try:
                        manifest = _read_json(entry / "manifest.json")
                        depends = any(d.get("item_id") == video_id for d in manifest.get("dependencies") or [])
                    except (OSError, ValueError):
                        depends = True
                    if depends:
                        shutil.rmtree(entry, ignore_errors=True)
                        if entry.exists():
                            raise ResourceError("library_unavailable", details={"storage": "purge_incomplete"})
                        interrupted += 1
                    continue
                if not _HEX64_RE.match(entry.name):
                    continue
                try:
                    manifest = _read_json(entry / "manifest.json")
                    depends = any(d.get("item_id") == video_id for d in manifest.get("dependencies") or [])
                except (OSError, ValueError):
                    depends = True
                if not depends:
                    continue
                shutil.rmtree(entry, ignore_errors=True)
                if entry.exists():
                    raise ResourceError("library_unavailable", details={"storage": "purge_incomplete"})
                purged.append(entry.name)
                record = self._load_record("receipts", entry.name) or {"brief_hash": entry.name, "date": day.name}
                record["status"] = "purged"
                record["purged_at"] = _iso(self._utc_now())
                receipt = record.get("receipt")
                if isinstance(receipt, dict):
                    receipt["status"] = "purged"
                self._save_record("receipts", entry.name, record)
        return _success(video_id=video_id, purged_count=len(purged), purged=purged,
                        interrupted_removed=interrupted)


def expected_bound(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Tool adapter (shared by the HTTP registry and stdio)
# --------------------------------------------------------------------------
TOOL_NAMES = library_resources.BRIEF_TOOL_NAMES
# One source for the strict schemas and descriptions (stdio and the HTTP
# registry both read them from library_resources).
TOOL_SCHEMAS: dict[str, dict] = {name: library_resources.TOOL_SCHEMAS[name] for name in TOOL_NAMES}
TOOL_DESCRIPTIONS: dict[str, str] = {name: library_resources.TOOL_DESCRIPTIONS[name] for name in TOOL_NAMES}


def call_tool(name: str, args, store: BriefStore, *, client_identity: str = "mcp-client") -> dict:
    """Run one brief tool. Returns the success or refusal envelope."""
    try:
        if name == "get_library_brief_input":
            args = library_resources._strict_arguments(args, ("date", "run_id"), ("date", "run_id"))
            return store.prepare_input(args["date"], args["run_id"])
        if name == "publish_library_brief":
            args = library_resources._strict_arguments(
                args, ("job_key", "input_hash", "input_packet", "submission_key", "document", "citations", "usage"),
                ("job_key", "input_hash", "input_packet", "submission_key", "document", "citations"))
            result = store.publish(
                job_key=args["job_key"], input_hash=args["input_hash"], input_packet=args["input_packet"],
                submission_key=args["submission_key"], document=args["document"], citations=args["citations"],
                usage=args.get("usage"), client_identity=client_identity)
            library_resources._check_wire(result, what="publish_library_brief", next_step="read_library_resource")
            return result
        raise _invalid("unknown_tool")
    except ResourceError as exc:
        return exc.envelope()
    except Exception:  # pragma: no cover -- defensive: no raw exception leaves the boundary
        log.exception("brief tool %s raised", name)
        return ResourceError("internal_error").envelope()


def dispatch_tool(name: str, args, backend, *, client_identity: str = "registry") -> dict:
    """Registry handler body: a request-scoped reader (existing storage only)
    and a store over the backend's data root."""
    try:
        reader = library_resources.make_reader(backend)
    except ResourceError as exc:
        return exc.envelope()
    store = BriefStore.for_reader(reader)
    return call_tool(name, args, store, client_identity=client_identity)

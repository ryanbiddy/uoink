"""Phase 6 media depth (contract ``phase6-v1``): chapters, local speaker
labels and cited ranges for the living library.

One offline validator/projector shared by capture, rebuild and export. It
imports only the pure ``clips``, ``library_cards`` and ``library_resources``
modules: no helper, no inference runtime, no network, no subprocess. Reads
never load or download a model. Every hash is SHA-256 over
``library_cards.serialize_card`` UTF-8 output.

BC-2 (2026-09-08) notes -- what this increment implements differently from
the literal BD-0 wording, read before relying on the behaviour:

1. **Publication fence.** Ownership is a per-item publication ledger
   (``.media-inputs/publication.json``: generation, current media revision,
   the revisions it superseded and the artifacts the current target
   references). ``begin_publication`` mints a ``PublicationTicket`` naming
   the base (generation, media revision) a publisher built against and the
   non-owned sidecar keys present at mint time; ``publish_transcript``
   rechecks deletion, corpus bytes, the sidecar's snapshot and that base
   under ``BEGIN IMMEDIATE`` before touching a file, writes the ledger
   claim first and the complete sidecar last, and a retry whose target the
   ledger already names completes from any file/DB boundary. Both entry
   points require that original build-time ticket: an omitted ticket is
   refused at ``Index.publish_media_snapshot`` and at raw
   ``publish_transcript``. The publisher never mints a ticket. An
   idempotent retry carries the original ticket. There is no empty,
   first-publication, or evaluation-helper exception. Production callers
   (``podcasts.episode_to_corpus``, ``server._index_yoink``) acquire the
   ticket before building. Reconstruction consults the same ledger and
   will not restore a superseded sidecar while disk still names the
   current publication. Non-owned sidecar keys, including a key another
   owner removed, are merged onto the carrier and revalidated at the
   final sidecar write after ledger/artifact work. User-edited corpus
   bytes are protected even before the first media block exists. The
   ledger keeps the 256 most recent superseded revisions. A ledger that
   is not parseable refuses ``invalid_source_data`` rather than guessing.
2. **Phase 2 invalidation** is invoked by ``Index.publish_media_snapshot``
   and ``Index.rebuild_media_item`` (the raw helpers here take a connection
   and cannot reach the service); an invalidation failure surfaces as a
   retryable ``library_unavailable`` after the committed, replayable
   publication. ``Index.store_media_snapshot`` remains for legacy callers
   and invalidates through the same path; ``podcasts.episode_to_corpus``
   still invokes ``Index.insert_citations`` after the yoink row on first
   publication because the Phase 3 durability suite injects its crash at
   that seam (row before citations). Replacement does not write the new
   cues there: the fenced publisher commits them with the snapshot, so a
   projector failure cannot present new citations bound to the old media.
3. **Artifact retention** prunes owned ``.media-inputs/<sha256>.json`` files
   only after a committed publication (``prune_artifacts``), keeping the
   current DB snapshot's references, every retained run record's artifact,
   the on-disk sidecar's references and the ledger's in-flight target.
   Files not named by a digest, or whose bytes do not hash to their name,
   belong to another owner and are never touched. A failed unlink reports
   ``cleanup_pending`` and the next settlement or ``prune_artifacts`` call
   retries. Hard purge of the item folder (server trash purge) removes the
   directory; ``purge_artifacts`` does the owned part on request.
4. **Seek kind ``media_fragment``** has no production player path; podcast
   publication records ``seek_kind="none"``, a null seek URL and a null
   exported player command. Fixture blocks may carry ``media_fragment``.
5. **Export** validates referenced artifacts by bytes (bounded read, digest,
   JSON object, descriptor locator and the contract's source-record match)
   through ``_verify_artifacts``, shared with publication and rebuild.
   Claimed source and run labels must appear on the matching producer
   record; digest validity alone does not attribute speech. The coherent
   read runs in one deferred SQLite transaction with the connection's busy
   timeout bounded by the remaining Phase 4 deadline. The final item/media
   recheck then takes a new snapshot so a second WAL connection's committed
   deletion or source/media change is visible (rollback-journal writers
   still cannot commit while the coherent read is open). The
   registry/stdio adapter (``export_cited_range_tool``) admits through the
   Phase 4 process guard, binds only an existing index and waits for the
   index lock no longer than that deadline.
6. **Virtual view**: ``unsupported``/``not_materialized`` only for items
   whose source type is prose-eligible and that have no cues; an empty or
   failed timed capture stays ``absent``/``not_materialized`` with transcript
   kind ``none``.
7. **Sidecar link fields**: entries carrying explicit ``source_url`` and
   ``source_deep_link`` bind only through those values (a mismatch refuses
   ``invalid_source_data``); legacy conventions are tried only when every
   entry lacks both fields, and only an exact cue-revision match is
   accepted. The compatibility ``youtube_deep_link`` value is persisted when
   present (including null) and mirrors ``source_deep_link`` (or ``""``)
   only for legacy entries.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
import time
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import clips as _clips
import library_cards as _cards
import library_resources as _resources

CONTRACT_VERSION = "phase6-v1"
SCHEMA_MIGRATION = "0030_media_depth"
SCHEMA_VERSION = 1
RENDER_VERSION = "media-markdown-v1"

MAX_TIME_SECONDS = 31536000
MAX_LABEL_CODEPOINTS = 128
MAX_LABEL_BYTES = 512
MAX_TITLE_CODEPOINTS = 512
MAX_TITLE_BYTES = 2048
MAX_CHAPTERS = 2048
MAX_ARTIFACT_BYTES = 16777216
MAX_RANGE_SECONDS = 120.0
MAX_RANGE_CUES = 200
MAX_EXPORT_CODEPOINTS = 2000
MEDIA_INPUTS_DIR = ".media-inputs"
PUBLICATION_LEDGER = "publication.json"
LEDGER_HISTORY_LIMIT = 256
PHASE6_TRANSCRIPT_KEYS = ("diarization_run", "diarization_run_id", "media_depth")
# Keys this publisher replaces on the sidecar. Every other top-level member
# belongs to another owner or to the carrier identity and is snapshotted on
# the ticket so an intervening edit can be merged instead of clobbered.
SIDECAR_PUBLICATION_KEYS = frozenset({"media_depth", "transcript"})

CHAPTER_STATES = ("present", "absent", "invalid", "unsupported")
SPEAKER_STATES = ("present", "partial", "absent", "invalid", "unsupported")
DIARIZATION_STATES = ("not_requested", "succeeded", "failed", "legacy_reported")
RUN_STATUSES = ("succeeded", "failed", "legacy_reported")
ABSENCE_REASONS = ("not_materialized", "not_supplied", "adapter_unsupported",
                   "diarization_off", "diarization_failed", "unlabeled_cues",
                   "unverified_legacy_label", "invalid_metadata")
TRANSCRIPT_KINDS = ("captions", "local_asr", "legacy_unknown", "none")
PROVIDERS = ("youtube_metadata", "embedded_transcript", "supplied_metadata")
SEEK_KINDS = ("youtube", "media_fragment", "none")
REFUSAL_CODES = frozenset({
    "invalid_request", "invalid_source_data", "revision_unavailable",
    "coarse_timing", "not_materialized", "library_unavailable",
    "resource_not_found", "resource_deleted", "resource_too_large",
    "rate_limited", "deadline_exceeded", "invalid_encoding",
    "feature_unavailable",
})
_RETRYABLE = frozenset({"library_unavailable", "deadline_exceeded", "rate_limited"})

CORE_FIELDS = ("seq", "timestamp_start", "timestamp_end", "text", "source_url", "source_deep_link")
BLOCK_KEYS = ("schema_version", "contract_version", "video_id", "source_revision",
              "cue_revision", "media_revision", "chapter_state", "speaker_state",
              "diarization_state", "provenance", "playback", "chapters", "runs", "cues")
PROVENANCE_KEYS = ("chapter_source", "transcript_source", "active_diarization_run_id",
                   "absence_reason", "corpus_revision")
TRANSCRIPT_SOURCE_KEYS = ("kind", "artifact_sha256", "provider", "model", "language")
DESCRIPTOR_KEYS = ("origin", "provider", "artifact_sha256", "record_locator", "recorded_at")
PLAYBACK_KEYS = ("source_url", "seek_url", "seek_kind")
CHAPTER_KEYS = ("seq", "start", "end", "title", "provenance")
RUN_KEYS = ("run_id", "cue_revision", "status", "producer", "producer_version", "model",
            "generated_at", "input_media_sha256", "artifact_sha256", "parameters")
CUE_KEYS = ("seq", "cue_hash", "speaker", "speaker_provenance")
SPEAKER_PROVENANCE_KEYS = ("origin", "cue_revision", "cue_hash", "source", "run_id")
CLIP_COLUMNS = ("seq", "start", "end", "text", "speaker", "source_deep_link", "cue_count",
                "media_revision", "speaker_state", "speaker_labels_json", "speaker_spans_json",
                "chapter_seq", "chapter_seqs_json")

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
# Markdown punctuation escaped in titles and labels (intraword "_" never
# opens emphasis in CommonMark, so SPEAKER_00 stays readable); "<>&" become
# entities so no source HTML or fence can be rendered.
_MD_ESCAPE = set("\\`*[](){}#!|~")
_REASON_TEXT = {
    "not_materialized": "not materialized",
    "not_supplied": "not supplied",
    "adapter_unsupported": "unavailable from this adapter",
    "diarization_off": "diarization off",
    "diarization_failed": "diarization failed",
    "unlabeled_cues": "some cues unlabeled",
    "unverified_legacy_label": "unverified labels in the original transcript, not attributed",
    "invalid_metadata": "invalid metadata",
}
_MESSAGES = dict(_resources._MESSAGES)
_MESSAGES.update({
    "coarse_timing": "The selected timing is too coarse for a precise range export.",
    "not_materialized": "This item has no materialized media snapshot.",
})


# --------------------------------------------------------------------------
# Errors and refusal envelopes
# --------------------------------------------------------------------------
class MediaError(Exception):
    """A domain refusal. ``code`` is one of the contract's refusal codes."""

    def __init__(self, code: str, message: str | None = None, *, details: dict | None = None):
        if code not in REFUSAL_CODES:
            code = "invalid_source_data"
        self.code = code
        self.message = message or _MESSAGES.get(code, "The media operation failed.")
        self.details = dict(details or {})
        if code == "revision_unavailable":
            self.details.setdefault("next_step", "get_library_item")
        super().__init__(self.message)

    @property
    def retryable(self) -> bool:
        return self.code in _RETRYABLE

    def envelope(self) -> dict:
        return _refuse(self.code, details=self.details, message=self.message)


def _refuse(code: str, *, details: dict | None = None, message: str | None = None) -> dict:
    details = dict(details or {})
    if code == "rate_limited":
        details["retry_after_ms"] = _resources._retry_after_ms(details.get("retry_after_ms", 0))
    return {
        "ok": False,
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "error": {
            "code": code,
            "message": message or _MESSAGES.get(code, "The media operation failed."),
            "retryable": code in _RETRYABLE,
            "details": details,
        },
    }


def _invalid(reason: str, **details) -> MediaError:
    return MediaError("invalid_source_data", details={"reason": reason, **details})


def _request(reason: str, **details) -> MediaError:
    return MediaError("invalid_request", details={"reason": reason, **details})


def _stale(reason: str, **details) -> MediaError:
    return MediaError("revision_unavailable", details={"reason": reason, **details})


# --------------------------------------------------------------------------
# Hashing and bindings
# --------------------------------------------------------------------------
def _json(value) -> str:
    return _cards.serialize_card(value)


def canonical_json(value) -> str:
    """The one serialization used for every stored JSON column and hash."""
    return _json(value)


def _walk_finite(value, path: str = "$") -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise _invalid("non_finite_number", path=path)
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _invalid("non_string_key", path=path)
            _walk_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _walk_finite(item, f"{path}[{i}]")


def _hash(value) -> str:
    _walk_finite(value)
    try:
        return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        raise _invalid("unserializable_value") from None


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def cue_core(cue: dict) -> dict:
    """The exact stored citation core: no row ID, no speaker, values as stored."""
    return {key: cue.get(key) for key in CORE_FIELDS}


def cue_hash(video_id: str, core: dict) -> str:
    return _hash(["phase6-cue-v1", video_id, core])


def cue_revision(video_id: str, cores: list[dict]) -> str:
    return _hash(["phase6-cues-v1", video_id, list(cores)])


def media_revision(block: dict) -> str:
    """Hash of the canonical block excluding only its own ``media_revision``."""
    if not isinstance(block, dict):
        raise _invalid("block_type")
    return _hash({key: value for key, value in block.items() if key != "media_revision"})


def transcript_artifact_bytes(transcript: dict) -> bytes:
    """Canonical bytes of a transcript JSON without Phase 6 run/provenance
    members: this is what a new transcription archives and hashes before the
    run record refers to it (no self-hash cycle). Matches the runner's file
    layout (two-space indent, unescaped Unicode)."""
    core = {key: value for key, value in transcript.items() if key not in PHASE6_TRANSCRIPT_KEYS}
    return json.dumps(core, indent=2, ensure_ascii=False).encode("utf-8")


# --------------------------------------------------------------------------
# Shape validation
# --------------------------------------------------------------------------
def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_hash(value) -> bool:
    return isinstance(value, str) and bool(_HEX64.match(value))


def _text_or_none(value) -> bool:
    return value is None or isinstance(value, str)


def _keys_exactly(obj, keys: tuple, what: str) -> None:
    if not isinstance(obj, dict) or set(obj) != set(keys):
        raise _invalid(what + "_shape")


def _valid_label(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if len(value) > MAX_LABEL_CODEPOINTS:
        return False
    try:
        if len(value.encode("utf-8")) > MAX_LABEL_BYTES:
            return False
    except UnicodeEncodeError:
        return False
    return not any(unicodedata.category(ch) == "Cc" for ch in value)


def _valid_title(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if len(value) > MAX_TITLE_CODEPOINTS:
        return False
    try:
        return len(value.encode("utf-8")) <= MAX_TITLE_BYTES
    except UnicodeEncodeError:
        return False


def _validate_identity(video_id) -> None:
    try:
        _resources._validate_identity(video_id)
    except _resources.ResourceError:
        raise _invalid("video_id_grammar") from None


def _validate_descriptor(descriptor, what: str) -> None:
    _keys_exactly(descriptor, DESCRIPTOR_KEYS, what)
    if descriptor["origin"] != "source_metadata":
        raise _invalid(what + "_origin")
    if descriptor["provider"] not in PROVIDERS:
        raise _invalid(what + "_provider")
    if not _is_hash(descriptor["artifact_sha256"]):
        raise _invalid(what + "_artifact")
    locator = descriptor["record_locator"]
    if not isinstance(locator, list):
        raise _invalid(what + "_locator")
    for step in locator:
        if isinstance(step, bool) or not (isinstance(step, str) or (isinstance(step, int) and step >= 0)):
            raise _invalid(what + "_locator")
    if not _text_or_none(descriptor["recorded_at"]):
        raise _invalid(what + "_recorded_at")


def _validate_transcript_source(source) -> None:
    _keys_exactly(source, TRANSCRIPT_SOURCE_KEYS, "transcript_source")
    if source["kind"] not in TRANSCRIPT_KINDS:
        raise _invalid("transcript_source_kind")
    if source["artifact_sha256"] is not None and not _is_hash(source["artifact_sha256"]):
        raise _invalid("transcript_source_artifact")
    for key in ("provider", "model", "language"):
        if not _text_or_none(source[key]):
            raise _invalid("transcript_source_" + key)


def _validate_playback(playback) -> None:
    _keys_exactly(playback, PLAYBACK_KEYS, "playback")
    if playback["seek_kind"] not in SEEK_KINDS:
        raise _invalid("playback_seek_kind")
    for key in ("source_url", "seek_url"):
        value = playback[key]
        if value is not None and (not isinstance(value, str) or _resources.safe_url(value) != value):
            raise _invalid("playback_" + key)
    if playback["seek_kind"] == "none" and playback["seek_url"] is not None:
        raise _invalid("playback_seek_url_without_kind")
    if playback["seek_kind"] != "none" and playback["seek_url"] is None:
        raise _invalid("playback_seek_kind_without_url")


def _validate_chapters(chapters) -> None:
    if not isinstance(chapters, list):
        raise _invalid("chapters_type")
    if len(chapters) > MAX_CHAPTERS:
        raise _invalid("chapters_too_many", limit=MAX_CHAPTERS)
    previous_end = None
    for index, chapter in enumerate(chapters):
        _keys_exactly(chapter, CHAPTER_KEYS, "chapter")
        if isinstance(chapter["seq"], bool) or chapter["seq"] != index:
            raise _invalid("chapter_seq", index=index)
        start, end = chapter["start"], chapter["end"]
        if not _is_number(start) or not _is_number(end):
            raise _invalid("chapter_time_type", index=index)
        if not (0 <= start < end <= MAX_TIME_SECONDS):
            raise _invalid("chapter_bounds", index=index)
        if previous_end is not None and start < previous_end:
            raise _invalid("chapter_order", index=index)
        previous_end = end
        if not _valid_title(chapter["title"]):
            raise _invalid("chapter_title", index=index)
        _validate_descriptor(chapter["provenance"], "chapter_provenance")


def _validate_run(run, block_cue_revision: str) -> None:
    _keys_exactly(run, RUN_KEYS, "run")
    if not isinstance(run["run_id"], str) or not _RUN_ID.match(run["run_id"]):
        raise _invalid("run_id_grammar")
    if run["cue_revision"] != block_cue_revision:
        raise _invalid("run_cue_revision")
    if run["status"] not in RUN_STATUSES:
        raise _invalid("run_status")
    if not isinstance(run["producer"], str) or not run["producer"].strip():
        raise _invalid("run_producer")
    for key in ("producer_version", "model", "generated_at"):
        if not _text_or_none(run[key]):
            raise _invalid("run_" + key)
    if run["input_media_sha256"] is not None and not _is_hash(run["input_media_sha256"]):
        raise _invalid("run_input_media_sha256")
    if not _is_hash(run["artifact_sha256"]):
        raise _invalid("run_artifact_sha256")
    if not isinstance(run["parameters"], dict) or any(not isinstance(k, str) for k in run["parameters"]):
        raise _invalid("run_parameters")
    if run["status"] == "legacy_reported":
        if run["run_id"] != "legacy_" + run["artifact_sha256"]:
            raise _invalid("legacy_run_id")
        if run["producer"] != "legacy_transcript":
            raise _invalid("legacy_run_producer")
        if any(run[key] is not None for key in ("producer_version", "model", "generated_at", "input_media_sha256")):
            raise _invalid("legacy_run_fields")
    elif run["run_id"].startswith("legacy_"):
        raise _invalid("run_id_reserved_prefix")


def validate_media_block(block: dict) -> dict:
    """Validate one ``media_depth`` block (sidecar or in-memory) against the
    contract's shapes, enums, bindings and semantic rules. Returns the same
    object unchanged; raises ``MediaError(invalid_source_data)``."""
    if not isinstance(block, dict):
        raise _invalid("block_type")
    if set(block) != set(BLOCK_KEYS):
        raise _invalid("block_keys")
    if type(block["schema_version"]) is not int or block["schema_version"] != SCHEMA_VERSION:
        raise _invalid("block_schema_version")
    if block["contract_version"] != CONTRACT_VERSION:
        raise _invalid("block_contract_version")
    video_id = block["video_id"]
    _validate_identity(video_id)
    for key in ("source_revision", "cue_revision", "media_revision"):
        if not _is_hash(block[key]):
            raise _invalid("block_" + key)
    chapter_state, speaker_state, diarization_state = (
        block["chapter_state"], block["speaker_state"], block["diarization_state"])
    if chapter_state not in CHAPTER_STATES:
        raise _invalid("chapter_state")
    if speaker_state not in SPEAKER_STATES:
        raise _invalid("speaker_state")
    if diarization_state not in DIARIZATION_STATES:
        raise _invalid("diarization_state")

    provenance = block["provenance"]
    _keys_exactly(provenance, PROVENANCE_KEYS, "provenance")
    if provenance["chapter_source"] is not None:
        _validate_descriptor(provenance["chapter_source"], "chapter_source")
    _validate_transcript_source(provenance["transcript_source"])
    active = provenance["active_diarization_run_id"]
    if active is not None and (not isinstance(active, str) or not _RUN_ID.match(active)):
        raise _invalid("active_run_id")
    absence = provenance["absence_reason"]
    _keys_exactly(absence, ("chapters", "speakers"), "absence_reason")
    for key in ("chapters", "speakers"):
        if absence[key] is not None and absence[key] not in ABSENCE_REASONS:
            raise _invalid("absence_reason_" + key)
    if provenance["corpus_revision"] is not None and not _is_hash(provenance["corpus_revision"]):
        raise _invalid("corpus_revision")
    _validate_playback(block["playback"])

    chapters = block["chapters"]
    _validate_chapters(chapters)
    if (chapter_state == "present") != bool(chapters):
        raise _invalid("chapter_state_mismatch")
    if chapter_state == "present" and provenance["chapter_source"] is None:
        raise _invalid("chapter_source_missing")
    if chapter_state in ("absent", "unsupported") and provenance["chapter_source"] is not None:
        raise _invalid("chapter_source_unexpected")
    if (absence["chapters"] is None) != (chapter_state == "present"):
        raise _invalid("chapter_reason_mismatch")

    runs = block["runs"]
    if not isinstance(runs, list):
        raise _invalid("runs_type")
    run_by_id: dict[str, dict] = {}
    previous_id = None
    for run in runs:
        _validate_run(run, block["cue_revision"])
        if previous_id is not None and run["run_id"] <= previous_id:
            raise _invalid("runs_order")
        previous_id = run["run_id"]
        run_by_id[run["run_id"]] = run
    if active is not None and active not in run_by_id:
        raise _invalid("active_run_unknown")

    cues = block["cues"]
    if not isinstance(cues, list):
        raise _invalid("cues_type")
    labeled = 0
    referenced_runs: set[str] = set()
    for index, cue in enumerate(cues):
        _keys_exactly(cue, CUE_KEYS, "cue")
        if isinstance(cue["seq"], bool) or cue["seq"] != index:
            raise _invalid("cue_seq", index=index)
        if not _is_hash(cue["cue_hash"]):
            raise _invalid("cue_hash", index=index)
        speaker, source = cue["speaker"], cue["speaker_provenance"]
        if speaker is None:
            if source is not None:
                raise _invalid("speaker_provenance_without_label", index=index)
            continue
        if not _valid_label(speaker):
            raise _invalid("speaker_label", index=index)
        _keys_exactly(source, SPEAKER_PROVENANCE_KEYS, "speaker_provenance")
        if source["cue_revision"] != block["cue_revision"]:
            raise _invalid("speaker_provenance_cue_revision", index=index)
        if source["cue_hash"] != cue["cue_hash"]:
            raise _invalid("speaker_provenance_cue_hash", index=index)
        if source["origin"] == "source_metadata":
            if source["run_id"] is not None:
                raise _invalid("source_label_with_run", index=index)
            _validate_descriptor(source["source"], "speaker_source")
        elif source["origin"] == "diarization_run":
            if source["source"] is not None:
                raise _invalid("run_label_with_source", index=index)
            run_id = source["run_id"]
            if not isinstance(run_id, str) or run_id not in run_by_id:
                raise _invalid("run_label_unknown_run", index=index)
            if run_by_id[run_id]["status"] not in ("succeeded", "legacy_reported"):
                raise _invalid("run_label_from_failed_run", index=index)
            if run_id != active:
                raise _invalid("run_label_not_active", index=index)
            referenced_runs.add(run_id)
        else:
            raise _invalid("speaker_provenance_origin", index=index)
        labeled += 1

    if speaker_state == "present" and not (cues and labeled == len(cues)):
        raise _invalid("speaker_state_mismatch")
    if speaker_state == "partial" and not (0 < labeled < len(cues)):
        raise _invalid("speaker_state_mismatch")
    if speaker_state in ("absent", "invalid") and labeled:
        raise _invalid("speaker_state_mismatch")
    if speaker_state == "unsupported" and (labeled or cues):
        raise _invalid("speaker_state_mismatch")
    if (absence["speakers"] is None) != (speaker_state == "present"):
        raise _invalid("speaker_reason_mismatch")
    kind = provenance["transcript_source"]["kind"]
    if (kind == "none") != (not cues):
        raise _invalid("transcript_source_kind_mismatch")

    if diarization_state == "not_requested":
        if active is not None or runs:
            raise _invalid("diarization_state_mismatch")
    else:
        if active is None:
            raise _invalid("diarization_state_mismatch")
        expected = {"succeeded": "succeeded", "failed": "failed",
                    "legacy_reported": "legacy_reported"}[diarization_state]
        if run_by_id[active]["status"] != expected:
            raise _invalid("diarization_state_mismatch")
    for run_id in run_by_id:
        if run_id != active and run_id not in referenced_runs:
            raise _invalid("unreferenced_run", run_id=run_id)

    if media_revision(block) != block["media_revision"]:
        raise _invalid("media_revision_mismatch")
    return block


# --------------------------------------------------------------------------
# Items, cues and bindings
# --------------------------------------------------------------------------
def _metadata(item: dict) -> dict:
    try:
        meta = json.loads(item.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _item_url(item: dict) -> str | None:
    url = item.get("url")
    if not isinstance(url, str) or not url.strip():
        url = _metadata(item).get("url")
    return url if isinstance(url, str) and url.strip() else None


def _merge_item(item: dict) -> dict:
    """The item dict the merger and card builder read: DB columns plus the
    metadata URL as ``url`` (what ``clips._item_for`` supplies)."""
    merged = dict(item)
    merged["url"] = _item_url(item) or ""
    return merged


def _item_duration(item: dict) -> float | None:
    meta = _metadata(item)
    for key in ("duration", "duration_seconds"):
        value = meta.get(key)
        if _is_number(value) and value > 0:
            return float(value)
    return None


def _youtube_video_id(url) -> str | None:
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
        return candidate or None
    if host in _YOUTUBE_HOSTS and parsed.path.rstrip("/") in ("/watch", ""):
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key == "v":
                return value or None
    return None


def _check_playback_identity(playback: dict, video_id: str) -> None:
    if playback["seek_kind"] == "youtube" and _youtube_video_id(playback["seek_url"]) != video_id:
        raise _invalid("playback_identity")


def _check_chapter_duration(chapters: list[dict], item: dict) -> None:
    duration = _item_duration(item)
    if duration is None:
        return
    for chapter in chapters:
        if chapter["end"] > duration:
            raise _invalid("chapter_beyond_duration", seq=chapter["seq"])


def _bind_cues(block: dict, cues: list[dict], *, stale_code: str = "revision_unavailable") -> list[dict]:
    """Verify that ``block`` binds exactly these cue cores. Returns the cores."""
    video_id = block["video_id"]
    cores = [cue_core(cue) for cue in cues]
    revision = cue_revision(video_id, cores)
    if revision != block["cue_revision"]:
        raise MediaError(stale_code, details={"reason": "cue_revision_mismatch"})
    if len(block["cues"]) != len(cores):
        raise _invalid("cue_count_mismatch")
    for annotation, core in zip(block["cues"], cores):
        if annotation["seq"] != core["seq"]:
            raise _invalid("cue_seq_mismatch", seq=core["seq"])
        if annotation["cue_hash"] != cue_hash(video_id, core):
            raise _invalid("cue_hash_mismatch", seq=core["seq"])
    return cores


def chapter_at(chapters: list[dict], t: float) -> dict | None:
    """Half-open point lookup: the chapter with ``start <= t < end``."""
    try:
        t = float(t)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(t):
        return None
    for chapter in chapters or []:
        if chapter["start"] <= t < chapter["end"]:
            return chapter
    return None


def _overlapping(chapters: list[dict], start, end) -> list[dict]:
    return [chapter for chapter in chapters or []
            if chapter["start"] < end and start < chapter["end"]]


# --------------------------------------------------------------------------
# Deterministic cue-to-clip projection
# --------------------------------------------------------------------------
def project_clips(cues: list[dict], item: dict, *, annotations: dict | None) -> list[dict]:
    """Run ``clips.merge_cues`` unchanged and annotate each window with its
    contributing cue spans, local labels, chapter overlap and media binding.
    Core fields are byte-identical to the merger's output."""
    if not isinstance(cues, list) or not isinstance(item, dict):
        raise _invalid("projection_input")
    video_id = item.get("video_id")
    block = None
    if annotations is not None:
        block = validate_media_block(annotations)
        if block["video_id"] != video_id:
            raise _invalid("cross_item_annotations")
        _bind_cues(block, cues)
        _check_chapter_duration(block["chapters"], item)
        _check_playback_identity(block["playback"], video_id)
    trace: list = []
    merged = _clips.merge_cues(cues, _merge_item(item), trace=trace)
    chapters = block["chapters"] if block else []
    annotated = block["cues"] if block else None
    out = []
    for clip, contributions in zip(merged, trace):
        labels: list[dict] = []
        spans: list[dict] = []
        for cue_index, text_start, text_end in contributions:
            cue = cues[cue_index]
            annotation = annotated[cue_index] if annotated is not None else None
            label_index = None
            if annotation is not None and annotation["speaker"] is not None:
                entry = {"label": annotation["speaker"],
                         "provenance": {k: v for k, v in annotation["speaker_provenance"].items()
                                        if k != "cue_hash"}}
                if entry in labels:
                    label_index = labels.index(entry)
                else:
                    labels.append(entry)
                    label_index = len(labels) - 1
            spans.append({
                "cue_seq": cue.get("seq"),
                "cue_hash": annotation["cue_hash"] if annotation is not None
                else cue_hash(video_id, cue_core(cue)),
                "start": cue.get("timestamp_start"),
                "end": cue.get("timestamp_end"),
                "text_start": text_start,
                "text_end": text_end,
                "label_index": label_index,
            })
        attributed = sum(1 for span in spans if span["label_index"] is not None)
        if spans and attributed == len(spans):
            state = "present"
        elif attributed:
            state = "partial"
        elif block is not None and block["speaker_state"] in ("invalid", "unsupported"):
            state = block["speaker_state"]
        else:
            state = "absent"
        speaker = labels[0]["label"] if state == "present" and len(labels) == 1 else None
        start_chapter = chapter_at(chapters, clip["start"])
        row = dict(clip)
        row.update(
            speaker=speaker,
            speaker_state=state,
            speaker_labels_json=_json(labels),
            speaker_spans_json=_json(spans),
            chapter_seq=start_chapter["seq"] if start_chapter else None,
            chapter_seqs_json=_json([c["seq"] for c in _overlapping(chapters, clip["start"], clip["end"])]),
            media_revision=block["media_revision"] if block else None,
        )
        out.append(row)
    return out


# --------------------------------------------------------------------------
# Markdown corpus rendering (media-markdown-v1)
# --------------------------------------------------------------------------
def _display_time(seconds) -> str:
    try:
        total_ms = int(round(float(seconds) * 1000.0))
    except (TypeError, ValueError, OverflowError):
        total_ms = 0
    total_ms = max(0, total_ms)
    hours, rest = divmod(total_ms, 3600000)
    minutes, rest = divmod(rest, 60000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def _escape_markdown(value, limit: int = MAX_TITLE_CODEPOINTS * 2) -> str:
    text = _resources.label(value, limit=limit)
    out = []
    for ch in text:
        if ch == "&":
            out.append("&amp;")
        elif ch == "<":
            out.append("&lt;")
        elif ch == ">":
            out.append("&gt;")
        elif ch in _MD_ESCAPE:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _seek_link(playback: dict | None, video_id: str, start) -> tuple[str | None, int | None]:
    """Seek link and player command from validated playback metadata only."""
    if not playback or start is None or not _is_number(start):
        return None, None
    seconds = math.floor(start)
    url = playback.get("seek_url")
    kind = playback.get("seek_kind")
    if kind == "youtube" and _resources.safe_url(url) == url and _youtube_video_id(url) == video_id:
        parts = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in ("v", "t")]
        query = [("v", video_id)] + query + [("t", f"{seconds}s")]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), "")), seconds
    if kind == "media_fragment" and _resources.safe_url(url) == url:
        return f"{url.split('#', 1)[0]}#t={seconds}", seconds
    return None, None


def _span_text(start, end, link: str | None) -> str:
    span = f"{_display_time(start)}–{_display_time(end)}"
    return f"[{span}]({link})" if link else span


def render_markdown(item: dict, cues: list[dict], *, chapters, annotations) -> str:
    """Render the Phase 6 media sections: a ``## Chapters`` list and a
    ``## Transcript`` with every raw cue exactly once. Labels, titles and
    provenance are escaped data outside the quoted text; no revision hash is
    rendered (it would be self-referential)."""
    block = validate_media_block(annotations) if annotations is not None else None
    video_id = item.get("video_id")
    if block is not None and block["video_id"] != video_id:
        raise _invalid("cross_item_annotations")
    chapters = list(chapters or [])
    _validate_chapters(chapters)
    if block is not None and len(block["cues"]) != len(cues):
        raise _invalid("cue_count_mismatch")
    playback = block["playback"] if block else None
    provenance = block["provenance"] if block else None
    lines: list[str] = ["## Chapters", ""]
    if chapters:
        for chapter in chapters:
            link, _ = _seek_link(playback, video_id, chapter["start"])
            lines.append(f"- {_span_text(chapter['start'], chapter['end'], link)}: "
                         f"{_escape_markdown(chapter['title'])}")
    else:
        reason = provenance["absence_reason"]["chapters"] if provenance else "not_materialized"
        lines.append("Chapters: " + _REASON_TEXT.get(reason or "not_supplied", "not supplied"))
    lines.extend(["", "## Transcript", ""])
    if block is None:
        lines.extend(["Speaker labels: not materialized", ""])
    elif block["speaker_state"] != "present":
        reason = provenance["absence_reason"]["speakers"]
        lines.extend(["Speaker labels: " + _REASON_TEXT.get(reason or "not_supplied", "not supplied"), ""])
    run_by_id = {run["run_id"]: run for run in block["runs"]} if block else {}
    annotated = block["cues"] if block else None
    for index, cue in enumerate(cues):
        link = _resources.safe_url(cue.get("source_deep_link"))
        heading = "### " + _span_text(cue.get("timestamp_start"), cue.get("timestamp_end"), link)
        annotation = annotated[index] if annotated is not None else None
        if annotation is not None and annotation["speaker"] is not None:
            heading += " — " + _escape_markdown(annotation["speaker"])
        lines.extend([heading, ""])
        if annotation is not None and annotation["speaker_provenance"] is not None:
            source = annotation["speaker_provenance"]
            if source["origin"] == "source_metadata":
                detail = f"source metadata ({_escape_markdown(source['source']['provider'])})"
            else:
                run = run_by_id.get(source["run_id"], {})
                if run.get("status") == "legacy_reported":
                    detail = f"legacy transcript report; run {source['run_id']}"
                else:
                    detail = f"local diarization; run {source['run_id']}"
            lines.extend([f"**Speaker provenance:** {detail}.", ""])
        text = cue.get("text")
        lines.extend([str(text) if text is not None else "", ""])
    return "\n".join(lines).rstrip("\n") + "\n"


# --------------------------------------------------------------------------
# Storage helpers (read side)
# --------------------------------------------------------------------------
def _pairs_hook(pairs):
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate object member: " + key)
        out[key] = value
    return out


def _parse_json_object(raw: bytes, what: str) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_hook)
    except (UnicodeDecodeError, ValueError):
        raise _invalid(what + "_json") from None
    if not isinstance(value, dict):
        raise _invalid(what + "_json")
    return value


def _json_object_column(raw, what: str) -> dict:
    if not isinstance(raw, str):
        raise _invalid(what + "_json")
    return _parse_json_object(raw.encode("utf-8"), what)


def _read_bytes(path: Path, *, required: bool) -> bytes | None:
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        if required:
            raise MediaError("library_unavailable", details={"reason": "artifact_missing"}) from None
        return None
    except OSError:
        raise MediaError("library_unavailable", details={"reason": "artifact_unreadable"}) from None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def schema_ready(conn: sqlite3.Connection) -> bool:
    """True once migration 0030 has been applied to this database."""
    try:
        return _has_column(conn, "clips", "speaker_spans_json") and _has_column(conn, "citations", "speaker")
    except sqlite3.Error:
        return False


def _load_item(conn: sqlite3.Connection, video_id: str) -> dict:
    row = conn.execute("SELECT * FROM yoinks WHERE video_id=?", (video_id,)).fetchone()
    if row is None:
        raise MediaError("resource_not_found")
    item = dict(row) if not isinstance(row, dict) else row
    if item.get("deleted_at"):
        raise MediaError("resource_deleted")
    return item


def _load_cues(conn: sqlite3.Connection, video_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM citations WHERE video_id=? AND kind='transcript_chunk' ORDER BY seq",
        (video_id,)).fetchall()
    return [dict(row) for row in rows]


def _load_clips(conn: sqlite3.Connection, video_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM clips WHERE video_id=? ORDER BY seq", (video_id,)).fetchall()
    return [dict(row) for row in rows]


def current_cue_revision(conn: sqlite3.Connection, video_id: str) -> str:
    """The cue revision of the item's current transcript citations."""
    return cue_revision(video_id, [cue_core(cue) for cue in _load_cues(conn, video_id)])


def _media_row(conn: sqlite3.Connection, video_id: str) -> dict | None:
    if not _has_column(conn, "clips", "speaker_spans_json"):
        return None
    row = conn.execute("SELECT * FROM media_depth WHERE video_id=?", (video_id,)).fetchone()
    return dict(row) if row is not None else None


def _block_from_db(conn: sqlite3.Connection, item: dict, cues: list[dict], row: dict) -> dict:
    """Reconstruct the current snapshot's block from DB rows. Only runs
    referenced by the snapshot are included; historical runs stay in the
    ledger without entering the hash."""
    video_id = item["video_id"]
    provenance = _json_object_column(row["provenance_json"], "provenance")
    playback = _json_object_column(row["playback_json"], "playback")
    chapters = []
    for chapter in conn.execute(
            "SELECT seq, start, end, title, provenance_json FROM chapters "
            "WHERE video_id=? AND source_revision=? ORDER BY seq",
            (video_id, row["source_revision"])):
        chapters.append({"seq": chapter[0], "start": chapter[1], "end": chapter[2], "title": chapter[3],
                         "provenance": _json_object_column(chapter[4], "chapter_provenance")})
    runs_all: dict[str, dict] = {}
    for run in conn.execute("SELECT * FROM diarization_runs WHERE video_id=?", (video_id,)):
        record = dict(run)
        record.pop("video_id", None)
        record["parameters"] = _json_object_column(record.pop("parameters_json"), "run_parameters")
        runs_all[record["run_id"]] = record
    annotated = []
    referenced: set[str] = set()
    active = provenance.get("active_diarization_run_id") if isinstance(provenance, dict) else None
    if isinstance(active, str):
        referenced.add(active)
    for cue in cues:
        speaker = cue.get("speaker")
        raw = cue.get("speaker_provenance_json")
        source = _json_object_column(raw, "speaker_provenance") if raw is not None else None
        if isinstance(source, dict) and isinstance(source.get("run_id"), str):
            referenced.add(source["run_id"])
        annotated.append({"seq": cue.get("seq"), "cue_hash": cue_hash(video_id, cue_core(cue)),
                          "speaker": speaker, "speaker_provenance": source})
    runs = [runs_all[run_id] for run_id in sorted(referenced) if run_id in runs_all]
    return {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
        "video_id": video_id, "source_revision": row["source_revision"],
        "cue_revision": row["cue_revision"], "media_revision": row["media_revision"],
        "chapter_state": row["chapter_state"], "speaker_state": row["speaker_state"],
        "diarization_state": row["diarization_state"],
        "provenance": provenance, "playback": playback,
        "chapters": chapters, "runs": runs, "cues": annotated,
    }


def _virtual_block(item: dict, cues: list[dict], source_revision: str, corpus_revision: str | None) -> dict:
    """The legacy/unmaterialized view: current bindings, no annotations."""
    video_id = item["video_id"]
    cores = [cue_core(cue) for cue in cues]
    url = _resources.safe_url(_item_url(item))
    if url and _youtube_video_id(url) == video_id:
        playback = {"source_url": url, "seek_url": url, "seek_kind": "youtube"}
    else:
        playback = {"source_url": url, "seek_url": None, "seek_kind": "none"}
    # Only a prose item (text-only source type, no cues) is unsupported for
    # timed annotations; an empty or failed timed capture is absent, not prose.
    text_only = not cues and item.get("source_type") in _cards.PROSE_ELIGIBLE_SOURCES
    state = "unsupported" if text_only else "absent"
    block = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
        "video_id": video_id, "source_revision": source_revision,
        "cue_revision": cue_revision(video_id, cores), "media_revision": "0" * 64,
        "chapter_state": state, "speaker_state": state, "diarization_state": "not_requested",
        "provenance": {
            "chapter_source": None,
            "transcript_source": {"kind": "legacy_unknown" if cues else "none", "artifact_sha256": None,
                                  "provider": None, "model": None, "language": None},
            "active_diarization_run_id": None,
            "absence_reason": {"chapters": "not_materialized", "speakers": "not_materialized"},
            "corpus_revision": corpus_revision,
        },
        "playback": playback,
        "chapters": [], "runs": [],
        "cues": [{"seq": core["seq"], "cue_hash": cue_hash(video_id, core), "speaker": None,
                  "speaker_provenance": None} for core in cores],
    }
    block["media_revision"] = media_revision(block)
    return block


def _referenced_artifacts(block: dict) -> set[str]:
    out: set[str] = set()
    provenance = block["provenance"]
    if provenance["chapter_source"]:
        out.add(provenance["chapter_source"]["artifact_sha256"])
    if provenance["transcript_source"]["artifact_sha256"]:
        out.add(provenance["transcript_source"]["artifact_sha256"])
    for chapter in block["chapters"]:
        out.add(chapter["provenance"]["artifact_sha256"])
    for run in block["runs"]:
        out.add(run["artifact_sha256"])
    for cue in block["cues"]:
        source = cue["speaker_provenance"]
        if source and source.get("source"):
            out.add(source["source"]["artifact_sha256"])
    return out


def _item_folder(item: dict) -> Path:
    return Path(item["corpus_path"]).parent


def _artifact_path(folder: Path, digest: str) -> Path:
    return folder / MEDIA_INPUTS_DIR / (digest + ".json")


def _read_artifact_bytes(path: Path, *, limit: int | None = None) -> bytes:
    """Bounded read of one referenced artifact: at most ``limit`` bytes are
    admitted; a longer file is invalid, a missing one ``library_unavailable``."""
    limit = MAX_ARTIFACT_BYTES if limit is None else limit
    try:
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
    except FileNotFoundError:
        raise MediaError("library_unavailable", details={"reason": "artifact_missing"}) from None
    except OSError:
        raise MediaError("library_unavailable", details={"reason": "artifact_unreadable"}) from None
    if len(data) > limit:
        raise _invalid("artifact_too_large", limit=limit)
    return data


def _file_signature(path: Path):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


_MISSING = object()


def _locate(artifact, locator: list):
    node = artifact
    for step in locator:
        if isinstance(step, str) and isinstance(node, dict) and step in node:
            node = node[step]
        elif isinstance(step, int) and not isinstance(step, bool) and isinstance(node, list) \
                and 0 <= step < len(node):
            node = node[step]
        else:
            return _MISSING
    return node


def _number_equal(left, right) -> bool:
    return _is_number(left) and _is_number(right) and float(left) == float(right)


def _chapter_record_matches(record, chapter: dict) -> bool:
    """The source element named by a chapter descriptor must carry the
    stored chapter's times and title (YouTube metadata uses
    ``start_time``/``end_time``; supplied metadata ``start``/``end``)."""
    if not isinstance(record, dict):
        return False
    start = record.get("start", record.get("start_time"))
    end = record.get("end", record.get("end_time"))
    return _number_equal(start, chapter["start"]) and _number_equal(end, chapter["end"]) \
        and record.get("title") == chapter["title"]


def _cue_record_matches(record, cue: dict, *, speaker=_MISSING) -> bool:
    """The producer element named by a cue descriptor (or the run
    assignment at the same ``seq``) must carry the stored cue's text and
    times. When ``speaker`` is supplied, that claimed label must be
    explicit on the same record; digest validity is not attribution."""
    if not isinstance(record, dict):
        return False
    if record.get("text") != cue.get("text") \
            or not _number_equal(record.get("start"), cue.get("timestamp_start")) \
            or not _number_equal(record.get("end"), cue.get("timestamp_end")):
        return False
    if speaker is _MISSING:
        return True
    return record.get("speaker") == speaker


def _run_assignment_collection(artifact):
    """Ordered assignment list in a diarization-run artifact. Fixtures
    archive ``transcript``; production WhisperX output uses ``segments``."""
    if not isinstance(artifact, dict):
        return None
    for key in ("transcript", "segments"):
        value = artifact.get(key)
        if isinstance(value, list):
            return value
    return None


def _verify_artifacts(folder: Path, block: dict, cues: list[dict], *,
                      owned: dict | None = None) -> dict[str, tuple]:
    """Shared artifact validator for publication, rebuild and export: every
    referenced ``.media-inputs`` artifact must exist, hash to its digest,
    parse as a JSON object and, for each producer descriptor, contain the
    record its locator names with the stored chapter/cue values. A claimed
    source or run label must be present on that producer record. Returns
    ``{digest: (size, mtime_ns) | None}`` signatures for a later recheck."""
    folder = Path(folder)
    parsed: dict[str, dict] = {}
    signatures: dict[str, tuple] = {}
    total = 0
    for digest in sorted(_referenced_artifacts(block)):
        path = _artifact_path(folder, digest)
        data = owned.get(path) if owned else None
        if data is None:
            data = _read_artifact_bytes(path)
        if _sha256(data) != digest:
            raise _invalid("artifact_digest_mismatch")
        total += len(data)
        parsed[digest] = _parse_json_object(data, "artifact")
        signatures[digest] = _file_signature(path)
    if total > MAX_ARTIFACT_BYTES:
        raise _invalid("artifacts_too_large", limit=MAX_ARTIFACT_BYTES)
    provenance = block["provenance"]
    source = provenance.get("chapter_source")
    if source and _locate(parsed[source["artifact_sha256"]], source["record_locator"]) is _MISSING:
        raise _invalid("chapter_source_record_missing")
    for chapter in block["chapters"]:
        descriptor = chapter["provenance"]
        record = _locate(parsed[descriptor["artifact_sha256"]], descriptor["record_locator"])
        if record is _MISSING or not _chapter_record_matches(record, chapter):
            raise _invalid("chapter_record_mismatch", seq=chapter["seq"])
    by_seq = {cue.get("seq"): cue for cue in cues}
    run_by_id = {run["run_id"]: run for run in block["runs"]}
    for annotation in block["cues"]:
        provenance = annotation.get("speaker_provenance") or {}
        seq = annotation["seq"]
        cue = by_seq.get(seq)
        speaker = annotation.get("speaker")
        descriptor = provenance.get("source")
        if descriptor:
            collection = _locate(parsed[descriptor["artifact_sha256"]], descriptor["record_locator"])
            if not isinstance(collection, list) or cue is None or not (0 <= seq < len(collection)) \
                    or not _cue_record_matches(collection[seq], cue, speaker=speaker):
                raise _invalid("cue_record_mismatch", seq=seq)
            continue
        if speaker is None or provenance.get("origin") != "diarization_run":
            continue
        run = run_by_id.get(provenance.get("run_id"))
        collection = _run_assignment_collection(
            parsed.get(run["artifact_sha256"]) if run else None)
        if not isinstance(collection, list) or cue is None or not (0 <= seq < len(collection)) \
                or not _cue_record_matches(collection[seq], cue, speaker=speaker):
            raise _invalid("run_assignment_mismatch", seq=seq)
    return signatures


def _evidence_row(clip: dict, index: int) -> dict:
    return {"start": clip.get("start"), "end": clip.get("end"), "text": clip.get("text") or "",
            "deep_link": _cards._web_link(clip.get("source_deep_link")),
            "seq": clip.get("seq", index), "timing": _clips.timing_kind(clip)}


def _clip_evidence(video_id: str, clip_rows: list[dict]) -> list[tuple[str, dict]]:
    """``(excerpt_id, clip_row)`` for every clip with text, in clip order,
    using the shared card builder's exact evidence normalisation."""
    out = []
    for index, clip in enumerate(clip_rows):
        if not _cards._string(clip.get("text")):
            continue
        out.append((_hash([video_id, _evidence_row(clip, index)]), clip))
    return out


class _Snapshot:
    __slots__ = ("item", "cues", "clip_rows", "block", "materialized", "source_revision",
                 "head", "prose", "corpus_bytes", "corpus_sha", "sidecar_signature",
                 "artifact_signatures")

    def __init__(self):
        self.item = None
        self.cues = []
        self.clip_rows = []
        self.block = None
        self.materialized = False
        self.source_revision = None
        self.head = ""
        self.prose = ""
        self.corpus_bytes = None
        self.corpus_sha = None
        self.sidecar_signature = None
        self.artifact_signatures = {}


def _read_snapshot(conn: sqlite3.Connection, video_id: str) -> _Snapshot:
    """One coherent current read: item, cues, clips, corpus head and the
    validated block (materialized or virtual). Stale bindings refuse
    ``revision_unavailable``; malformed persisted data ``invalid_source_data``."""
    snap = _Snapshot()
    item = _load_item(conn, video_id)
    snap.item = item
    snap.cues = _load_cues(conn, video_id)
    snap.clip_rows = _load_clips(conn, video_id)
    corpus_bytes = _read_bytes(Path(item["corpus_path"]), required=False)
    snap.corpus_bytes = corpus_bytes
    snap.corpus_sha = _sha256(corpus_bytes) if corpus_bytes is not None else None
    snap.head = (corpus_bytes or b"")[:_cards.CORPUS_READ_BYTES].decode("utf-8", "replace")
    snap.prose = _cards.opening_prose(snap.head)
    card = _cards.build_card(_merge_item(item), snap.clip_rows, corpus_text=snap.head)
    snap.source_revision = card["source_revision"]
    cue_rev = cue_revision(video_id, [cue_core(cue) for cue in snap.cues])
    row = _media_row(conn, video_id)
    if row is None:
        snap.block = _virtual_block(item, snap.cues, snap.source_revision, snap.corpus_sha)
        return snap
    if row["cue_revision"] != cue_rev:
        raise _stale("cue_revision_changed")
    if row["source_revision"] != snap.source_revision:
        raise _stale("source_revision_changed")
    sidecar_path = Path(item["sidecar_path"])
    sidecar = _parse_json_object(_read_bytes(sidecar_path, required=True), "sidecar")
    snap.sidecar_signature = _file_signature(sidecar_path)
    side_block = sidecar.get("media_depth")
    if not isinstance(side_block, dict) or side_block.get("media_revision") != row["media_revision"]:
        raise _stale("sidecar_snapshot_mismatch")
    block = validate_media_block(_block_from_db(conn, item, snap.cues, row))
    if block["media_revision"] != row["media_revision"]:
        raise _invalid("media_revision_mismatch")
    if block["provenance"]["corpus_revision"] != snap.corpus_sha:
        raise _stale("corpus_revision_changed")
    # Original artifacts are evidence only when their bytes verify (digest,
    # JSON, locator and source-record match); a hash-shaped descriptor is not.
    snap.artifact_signatures = _verify_artifacts(_item_folder(item), block, snap.cues)
    snap.block = block
    snap.materialized = True
    return snap


def _recheck_snapshot(conn: sqlite3.Connection, snap: _Snapshot) -> None:
    """Final source/media recheck after the export body is built: the item
    is still current, the corpus bytes, the sidecar and every referenced
    artifact are unchanged since the coherent read began. Must run on a
    fresh SQLite snapshot (not the deferred read that built the body) so a
    second WAL connection's committed deletion or revision is visible."""
    item = _load_item(conn, snap.item["video_id"])
    if item.get("title") != snap.item.get("title") or item.get("corpus_path") != snap.item.get("corpus_path") \
            or item.get("metadata_json") != snap.item.get("metadata_json"):
        raise _stale("source_changed")
    corpus_bytes = _read_bytes(Path(item["corpus_path"]), required=False)
    if (_sha256(corpus_bytes) if corpus_bytes is not None else None) != snap.corpus_sha:
        raise _stale("corpus_revision_changed")
    if not snap.materialized:
        if _media_row(conn, item["video_id"]) is not None:
            raise _stale("media_revision_changed")
        return
    row = _media_row(conn, item["video_id"])
    if row is None or row["media_revision"] != snap.block["media_revision"]:
        raise _stale("media_revision_changed")
    # Another owner may rewrite the sidecar around an unchanged snapshot;
    # only a different (or missing) snapshot is a stale read, so the sidecar
    # is re-read rather than compared by signature.
    sidecar = _parse_json_object(_read_bytes(Path(item["sidecar_path"]), required=True), "sidecar")
    side_block = sidecar.get("media_depth")
    if not isinstance(side_block, dict) or side_block.get("media_revision") != snap.block["media_revision"]:
        raise _stale("sidecar_snapshot_mismatch")
    folder = _item_folder(item)
    for digest, signature in snap.artifact_signatures.items():
        if _file_signature(_artifact_path(folder, digest)) != signature:
            raise _stale("artifact_changed")


def chapters_for(conn, video_id: str, *, revision: str | None = None) -> list[dict]:
    """Current published chapter rows, optionally pinned to a source revision."""
    try:
        _load_item(conn, video_id)
        row = _media_row(conn, video_id)
        if row is None:
            if revision is not None:
                raise _stale("no_snapshot")
            return []
        if revision is not None and revision != row["source_revision"]:
            raise _stale("source_revision_mismatch")
        out = []
        for chapter in conn.execute(
                "SELECT seq, start, end, title, provenance_json FROM chapters "
                "WHERE video_id=? AND source_revision=? ORDER BY seq",
                (video_id, row["source_revision"])):
            out.append({"seq": chapter[0], "start": chapter[1], "end": chapter[2], "title": chapter[3],
                        "provenance": _json_object_column(chapter[4], "chapter_provenance"),
                        "video_id": video_id, "source_revision": row["source_revision"]})
        return out
    except sqlite3.Error:
        raise MediaError("library_unavailable") from None


# --------------------------------------------------------------------------
# Storage helpers (write side)
# --------------------------------------------------------------------------
def _cues_from_sidecar(sidecar: dict, block: dict | None, item: dict) -> list[dict]:
    """Recover citation rows from the sidecar transcript and re-bind them to
    the block's cue hashes. Entries with explicit link fields bind only
    through those values (a mismatch is ``invalid_source_data``); legacy
    entries without any link field try the recorded conventions and only an
    exact cue-revision match is accepted."""
    entries = sidecar.get("transcript") or []
    if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
        raise _invalid("sidecar_transcript")
    video_id = item["video_id"]
    meta = sidecar.get("metadata") if isinstance(sidecar.get("metadata"), dict) else {}
    url = (meta.get("url") or sidecar.get("source_url") or sidecar.get("url") or _item_url(item))
    url = url if isinstance(url, str) and url.strip() else None
    flags = [("source_url" in e, "source_deep_link" in e) for e in entries]
    explicit = bool(entries) and all(a and b for a, b in flags)
    if entries and not explicit and any(a or b for a, b in flags):
        raise _invalid("sidecar_link_fields_mixed")

    def seconds(value):
        try:
            return max(0, int(float(value)))
        except (TypeError, ValueError):
            return 0

    def rows(mode: str, coerce: bool) -> list[dict]:
        out = []
        for index, entry in enumerate(entries):
            start, end = entry.get("start"), entry.get("end")
            if coerce:
                start = float(start) if _is_number(start) else start
                end = float(end) if _is_number(end) else end
            if mode == "explicit":
                source_url, deep = entry.get("source_url"), entry.get("source_deep_link")
            elif mode == "same":
                source_url, deep = url, url
            elif mode == "fragment":
                source_url = url
                deep = f"{url.split('#', 1)[0]}#t={seconds(start)}" if url else None
            else:
                source_url = url or f"https://youtube.com/watch?v={video_id}"
                deep = f"https://youtube.com/watch?v={video_id}&t={seconds(start)}s"
            youtube_link = entry.get("youtube_deep_link") if "youtube_deep_link" in entry else (deep or "")
            out.append({"kind": "transcript_chunk", "seq": index, "timestamp_start": start,
                        "timestamp_end": end, "text": entry.get("text"), "file_path": None,
                        "youtube_deep_link": youtube_link, "source_url": source_url,
                        "source_deep_link": deep, "speaker": entry.get("speaker"),
                        "speaker_provenance": entry.get("speaker_provenance")})
        return out

    modes = ["explicit"] if explicit else ["same", "fragment", "youtube"]
    if block is None:
        chosen = rows(modes[0] if explicit else ("youtube" if item.get("platform") in (None, "youtube") else "fragment"), False)
    else:
        chosen = None
        for mode in modes:
            for coerce in (False, True):
                candidate = rows(mode, coerce)
                if cue_revision(video_id, [cue_core(c) for c in candidate]) == block["cue_revision"]:
                    chosen = candidate
                    break
            if chosen is not None:
                break
        if chosen is None:
            raise _invalid("sidecar_cue_binding", explicit_links=explicit)
        for cue, annotation in zip(chosen, block["cues"]):
            if cue["speaker"] != annotation["speaker"] or cue["speaker_provenance"] != annotation["speaker_provenance"]:
                raise _invalid("sidecar_label_mismatch", seq=annotation["seq"])
    return chosen


def _insert_citations(conn: sqlite3.Connection, video_id: str, cues: list[dict], block: dict | None) -> None:
    conn.execute("DELETE FROM citations WHERE video_id=? AND kind='transcript_chunk'", (video_id,))
    labelled = _has_column(conn, "citations", "speaker")
    for index, cue in enumerate(cues):
        annotation = block["cues"][index] if block is not None else None
        speaker = annotation["speaker"] if annotation else None
        source = annotation["speaker_provenance"] if annotation else None
        columns = ["video_id", "kind", "seq", "timestamp_start", "timestamp_end", "text", "file_path",
                   "youtube_deep_link", "source_url", "source_deep_link"]
        values = [video_id, "transcript_chunk", cue.get("seq"), cue.get("timestamp_start"),
                  cue.get("timestamp_end"), cue.get("text"), cue.get("file_path"),
                  cue.get("youtube_deep_link"), cue.get("source_url"), cue.get("source_deep_link")]
        if labelled:
            columns += ["speaker", "speaker_provenance_json"]
            values += [speaker, _json(source) if source is not None else None]
        conn.execute(f"INSERT INTO citations ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                     values)


def _write_media_rows(conn: sqlite3.Connection, block: dict) -> None:
    video_id = block["video_id"]
    conn.execute("DELETE FROM media_depth WHERE video_id=?", (video_id,))
    conn.execute(
        "INSERT INTO media_depth (video_id, source_revision, cue_revision, media_revision, chapter_state, "
        "speaker_state, diarization_state, provenance_json, playback_json) VALUES (?,?,?,?,?,?,?,?,?)",
        (video_id, block["source_revision"], block["cue_revision"], block["media_revision"],
         block["chapter_state"], block["speaker_state"], block["diarization_state"],
         _json(block["provenance"]), _json(block["playback"])))
    for chapter in block["chapters"]:
        conn.execute(
            "INSERT INTO chapters (video_id, source_revision, seq, start, end, title, provenance_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (video_id, block["source_revision"], chapter["seq"], chapter["start"], chapter["end"],
             chapter["title"], _json(chapter["provenance"])))
    for run in block["runs"]:
        conn.execute(
            "INSERT OR REPLACE INTO diarization_runs (video_id, run_id, cue_revision, status, producer, "
            "producer_version, model, generated_at, input_media_sha256, artifact_sha256, parameters_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (video_id, run["run_id"], run["cue_revision"], run["status"], run["producer"],
             run["producer_version"], run["model"], run["generated_at"], run["input_media_sha256"],
             run["artifact_sha256"], _json(run["parameters"])))


def _write_clips(conn: sqlite3.Connection, video_id: str, projected: list[dict]) -> None:
    conn.execute("DELETE FROM clips WHERE video_id=?", (video_id,))
    annotated = _has_column(conn, "clips", "speaker_spans_json")
    columns = list(CLIP_COLUMNS) if annotated else ["seq", "start", "end", "text", "speaker",
                                                     "source_deep_link", "cue_count"]
    for clip in projected:
        conn.execute(
            f"INSERT INTO clips (video_id, {', '.join(columns)}) VALUES (?, {', '.join('?' * len(columns))})",
            [video_id] + [clip.get(column) for column in columns])


def project_clips_for_video(conn: sqlite3.Connection, video_id: str) -> int:
    """Replace one item's clips with the annotated projection of its current
    cues and materialized snapshot (used by ``clips.build_clips_for_video``
    once a coherent snapshot exists). No commit; returns the clip count."""
    raw = conn.execute("SELECT * FROM yoinks WHERE video_id=?", (video_id,)).fetchone()
    if raw is None:
        raise MediaError("resource_not_found")
    item = dict(raw)  # a soft-deleted row keeps its derived clips until purge
    cues = _load_cues(conn, video_id)
    row = _media_row(conn, video_id)
    block = validate_media_block(_block_from_db(conn, item, cues, row)) if row is not None else None
    if block is not None:
        _bind_cues(block, cues)
    projected = project_clips(cues, item, annotations=block)
    _write_clips(conn, video_id, projected)
    return len(projected)


def _atomic_replace(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix="." + path.name + ".",
                                         suffix=".tmp", delete=False)
    temp_name = handle.name
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass


def archive_artifact(folder: Path, data: bytes) -> str:
    """Persist original JSON bytes under ``<folder>/.media-inputs/<sha256>.json``
    (immutable; skipped when already present with the same digest). Returns
    the digest."""
    digest = _sha256(data)
    target = _artifact_path(Path(folder), digest)
    existing = _read_bytes(target, required=False)
    if existing is None or _sha256(existing) != digest:
        _atomic_replace(target, data)
    return digest


def store_snapshot(conn: sqlite3.Connection, item: dict, cues: list[dict], block: dict, *,
                   commit: bool = True) -> int:
    """Write the media rows and annotated clips for an already published
    file-side snapshot (citations are written by the caller). Returns the
    clip count."""
    block = validate_media_block(block)
    if block["video_id"] != item["video_id"]:
        raise _invalid("cross_item_annotations")
    if not _has_column(conn, "clips", "speaker_spans_json"):
        raise MediaError("library_unavailable", details={"reason": "schema_not_migrated"})
    _bind_cues(block, cues, stale_code="invalid_source_data")
    projected = project_clips(cues, item, annotations=block)
    _write_media_rows(conn, block)
    _write_clips(conn, item["video_id"], projected)
    if commit:
        conn.commit()
    return len(projected)


def rebuild_item(conn, video_id: str, *, sidecar: dict | None) -> dict:
    """Clip-only rebuild (``sidecar=None``) or reconstruction from the durable
    sidecar/artifacts. Never writes Markdown, runs a model or fetches.
    Reconstruction is fenced through the publication ledger: a sidecar that
    is not the ledger's current snapshot is refused before any DB write so
    disk and rows cannot diverge onto a superseded media revision."""
    try:
        item = _load_item(conn, video_id)
        if sidecar is None:
            cues = _load_cues(conn, video_id)
            row = _media_row(conn, video_id)
            block = None
            if row is not None:
                block = validate_media_block(_block_from_db(conn, item, cues, row))
                _bind_cues(block, cues)
            projected = project_clips(cues, item, annotations=block)
            _write_clips(conn, video_id, projected)
            conn.commit()
            return {"ok": True, "video_id": video_id, "mode": "clip_only", "clips": len(projected),
                    "cues": len(cues), "media_revision": block["media_revision"] if block else None}
        if not isinstance(sidecar, dict) or sidecar.get("video_id") != video_id:
            raise _invalid("sidecar_identity")
        block = sidecar.get("media_depth")
        if block is not None:
            block = validate_media_block(block)
            if block["video_id"] != video_id:
                raise _invalid("cross_item_annotations")
        cues = _cues_from_sidecar(sidecar, block, item)
        folder = _item_folder(item)
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        item = _load_item(conn, video_id)
        generation, current, ledger = _publication_state(conn, video_id, folder)
        sidecar_revision = block["media_revision"] if block is not None else None
        if ledger is not None:
            # Only the ledger's current snapshot may be restored. A stale
            # sidecar (BD-03) would otherwise rewrite DB annotations while
            # disk still names the newer publication.
            if sidecar_revision != current:
                raise _stale("publication_superseded", base_generation=generation,
                             current_generation=generation)
            disk_raw = _read_bytes(Path(item["sidecar_path"]), required=False)
            disk_revision = None
            if disk_raw is not None:
                try:
                    disk_block = _parse_json_object(disk_raw, "sidecar").get("media_depth")
                except MediaError:
                    disk_block = None
                if isinstance(disk_block, dict) and _is_hash(disk_block.get("media_revision")):
                    disk_revision = disk_block["media_revision"]
            if disk_revision is not None and disk_revision != current:
                raise _stale("publication_superseded", base_generation=generation,
                             current_generation=generation)
        if block is not None:
            _verify_artifacts(folder, block, cues)
            corpus_bytes = _read_bytes(Path(item["corpus_path"]), required=True)
            if block["provenance"]["corpus_revision"] != _sha256(corpus_bytes):
                raise _stale("corpus_revision_changed")
            projected = project_clips(cues, item, annotations=block)
            head = corpus_bytes[:_cards.CORPUS_READ_BYTES].decode("utf-8", "replace")
            source_now = _cards.build_card(_merge_item(item), projected, corpus_text=head)["source_revision"]
            if source_now != block["source_revision"]:
                raise _stale("source_revision_changed")
        else:
            projected = project_clips(cues, item, annotations=None)
        _insert_citations(conn, video_id, cues, block)
        if block is not None:
            if not _has_column(conn, "clips", "speaker_spans_json"):
                raise MediaError("library_unavailable", details={"reason": "schema_not_migrated"})
            _write_media_rows(conn, block)
        _write_clips(conn, video_id, projected)
        conn.commit()
        return {"ok": True, "video_id": video_id, "mode": "reconstruct", "clips": len(projected),
                "cues": len(cues), "media_revision": block["media_revision"] if block else None}
    except MediaError:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    except sqlite3.Error:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise MediaError("library_unavailable") from None


# --------------------------------------------------------------------------
# Publication ownership fence and artifact retention
# --------------------------------------------------------------------------
class PublicationTicket:
    """The base a publisher built against: the item's publication generation
    and current media revision when ``begin_publication`` ran, plus the
    non-owned sidecar keys present at that moment. Carried by the owning
    service, never by a media hash or an export input."""

    __slots__ = ("video_id", "base_generation", "base_media_revision", "sidecar_dependencies")

    def __init__(self, video_id: str, base_generation: int, base_media_revision: str | None,
                 sidecar_dependencies: dict | None = None):
        self.video_id = video_id
        self.base_generation = base_generation
        self.base_media_revision = base_media_revision
        self.sidecar_dependencies = copy.deepcopy(sidecar_dependencies or {})

    @property
    def base(self) -> tuple:
        return (self.base_generation, self.base_media_revision)


def _ledger_path(folder: Path) -> Path:
    return Path(folder) / MEDIA_INPUTS_DIR / PUBLICATION_LEDGER


def _read_ledger(folder: Path) -> dict | None:
    """The item's publication ledger, or None before its first fenced
    publication. Malformed ledgers refuse rather than being guessed at."""
    raw = _read_bytes(_ledger_path(folder), required=False)
    if raw is None:
        return None
    try:
        ledger = _parse_json_object(raw, "publication_ledger")
    except MediaError:
        raise _invalid("publication_ledger_corrupt") from None
    generation = ledger.get("generation")
    history = ledger.get("history")
    artifacts = ledger.get("artifacts")
    base = ledger.get("base_media_revision")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1 \
            or not _is_hash(ledger.get("media_revision")) \
            or (base is not None and not _is_hash(base)) \
            or not isinstance(history, list) or any(not _is_hash(h) for h in history) \
            or not isinstance(artifacts, list) or any(not _is_hash(a) for a in artifacts):
        raise _invalid("publication_ledger_corrupt")
    return ledger


def _publication_state(conn: sqlite3.Connection, video_id: str, folder: Path | None) -> tuple:
    """``(generation, current_media_revision, ledger)``: the ledger when one
    exists, else generation 0 with the DB row's media revision (legacy or
    seeded items) or None (never materialized)."""
    ledger = _read_ledger(folder) if folder is not None else None
    if ledger is not None:
        return ledger["generation"], ledger["media_revision"], ledger
    row = _media_row(conn, video_id) if _has_column(conn, "clips", "speaker_spans_json") else None
    return 0, (row["media_revision"] if row is not None else None), None


def _sidecar_dependencies_from(parsed: dict | None) -> dict:
    """Top-level sidecar members this publication does not replace."""
    if not isinstance(parsed, dict):
        return {}
    return {key: value for key, value in parsed.items() if key not in SIDECAR_PUBLICATION_KEYS}


def _read_sidecar_dependencies(path: Path | None) -> dict:
    if path is None:
        return {}
    raw = _read_bytes(Path(path), required=False)
    if raw is None:
        return {}
    try:
        return _sidecar_dependencies_from(_parse_json_object(raw, "sidecar"))
    except MediaError:
        return {}


def _sidecar_from_disk(path: Path) -> tuple[bytes | None, dict | None]:
    """Current sidecar bytes and object, or ``(None, None)`` when absent.

    An unparseable on-disk sidecar is a dependency conflict, not an empty
    carrier: refusing avoids treating a missing parse as a bulk key removal.
    """
    raw = _read_bytes(Path(path), required=False)
    if raw is None:
        return None, None
    try:
        return raw, _parse_json_object(raw, "sidecar")
    except MediaError:
        raise _stale("sidecar_dependency_changed") from None


def _apply_sidecar_dependencies(sidecar: dict, disk_side: dict | None, ticket: PublicationTicket) -> bool:
    """Overlay non-owned sidecar state from disk onto the published carrier.

    Ticket snapshot is the base. Disk values that still match the snapshot
    leave a publisher-supplied replacement in place (podcast title/speakers)
    and restore a key the publisher omitted. Disk values that changed after
    mint, keys that exist only on disk, and keys removed on disk after mint
    are taken from disk so this write neither overwrites another owner's
    edit nor resurrects a removed key. Returns True when ``sidecar`` changed.
    """
    base = ticket.sidecar_dependencies if isinstance(ticket.sidecar_dependencies, dict) else {}
    disk = disk_side if isinstance(disk_side, dict) else {}
    changed = False
    for key in list(sidecar.keys()):
        if key in SIDECAR_PUBLICATION_KEYS:
            continue
        if key in base and key not in disk:
            del sidecar[key]
            changed = True
    for key, value in disk.items():
        if key in SIDECAR_PUBLICATION_KEYS:
            continue
        unchanged = key in base and base[key] == value
        if unchanged:
            if key not in sidecar:
                sidecar[key] = copy.deepcopy(value)
                changed = True
            continue
        if key not in sidecar or sidecar[key] != value:
            sidecar[key] = copy.deepcopy(value)
            changed = True
    return changed


def _bind_sidecar_carrier(sidecar: dict, sidecar_path: Path, ticket: PublicationTicket,
                          owned: dict, video_id: str) -> bytes | None:
    """Merge the on-disk non-owned keys into ``sidecar`` and refresh owned bytes."""
    raw, disk_side = _sidecar_from_disk(sidecar_path)
    changed = _apply_sidecar_dependencies(sidecar, disk_side, ticket)
    if sidecar.get("video_id") != video_id:
        raise _invalid("sidecar_identity")
    if changed:
        owned[sidecar_path] = _json(sidecar).encode("utf-8")
    return raw


def begin_publication(conn, video_id: str, *, folder=None) -> PublicationTicket:
    """Mint the fence for one publication of ``video_id``: the base it must
    still find under the storage lock when it publishes. ``folder`` names
    the item folder for a first publication whose row does not exist yet."""
    try:
        _validate_identity(video_id)
        raw = conn.execute("SELECT * FROM yoinks WHERE video_id=?", (video_id,)).fetchone()
        item = dict(raw) if raw is not None else None
        if item is not None and item.get("deleted_at"):
            raise MediaError("resource_deleted")
        if folder is None and item is not None:
            folder = _item_folder(item)
        generation, current, _ledger = _publication_state(conn, video_id, Path(folder) if folder else None)
        sidecar_path = Path(item["sidecar_path"]) if item is not None and item.get("sidecar_path") else None
        return PublicationTicket(video_id, generation, current, _read_sidecar_dependencies(sidecar_path))
    except sqlite3.Error:
        raise MediaError("library_unavailable") from None


def _owned_artifact_digest(path: Path) -> str | None:
    """The digest a ``.media-inputs`` file is owned under, or None when the
    file is not one of ours (not hash-named, oversized or not matching)."""
    digest = path.stem
    if path.suffix != ".json" or not _is_hash(digest):
        return None
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_ARTIFACT_BYTES + 1)
    except OSError:
        return None
    if len(data) > MAX_ARTIFACT_BYTES or _sha256(data) != digest:
        return None
    return digest


def _retained_artifacts(conn: sqlite3.Connection, item: dict, folder: Path) -> set[str]:
    """Digests that must survive pruning: the current DB snapshot's
    references, every retained run record, the on-disk sidecar's snapshot
    and the ledger's in-flight target."""
    video_id = item["video_id"]
    retained: set[str] = set()
    row = _media_row(conn, video_id)
    if row is not None:
        retained |= _referenced_artifacts(_block_from_db(conn, item, _load_cues(conn, video_id), row))
    if _has_column(conn, "clips", "speaker_spans_json"):
        for run in conn.execute("SELECT artifact_sha256 FROM diarization_runs WHERE video_id=?", (video_id,)):
            if _is_hash(run[0]):
                retained.add(run[0])
    sidecar_raw = _read_bytes(Path(item["sidecar_path"]), required=False)
    if sidecar_raw is not None:
        try:
            side_block = _parse_json_object(sidecar_raw, "sidecar").get("media_depth")
            if isinstance(side_block, dict):
                retained |= _referenced_artifacts(validate_media_block(side_block))
        except MediaError:
            pass
    ledger = _read_ledger(folder)
    if ledger is not None:
        retained |= set(ledger["artifacts"])
    return retained


def prune_artifacts(conn, item: dict) -> dict:
    """Remove owned ``.media-inputs`` artifacts no longer needed after a
    committed publication. Never called by a read; a failed unlink leaves
    ``cleanup_pending`` for the next settlement or explicit call."""
    folder = _item_folder(item)
    inputs = folder / MEDIA_INPUTS_DIR
    if not inputs.is_dir():
        return {"pruned": 0, "retained": 0, "cleanup_pending": False}
    try:
        retained = _retained_artifacts(conn, item, folder)
    except sqlite3.Error:
        raise MediaError("library_unavailable") from None
    pruned, kept, pending = 0, 0, False
    try:
        candidates = sorted(inputs.iterdir())
    except OSError:
        return {"pruned": 0, "retained": len(retained), "cleanup_pending": True}
    for path in candidates:
        if path.name == PUBLICATION_LEDGER or not path.is_file():
            continue
        digest = _owned_artifact_digest(path)
        if digest is None:
            continue
        if digest in retained:
            kept += 1
            continue
        try:
            path.unlink()
            pruned += 1
        except OSError:
            pending = True
    return {"pruned": pruned, "retained": kept, "cleanup_pending": pending}


def purge_artifacts(folder) -> int:
    """Hard purge of the owned part of an item folder: every owned artifact
    and the ledger. Other owners' files stay; returns the number removed."""
    inputs = Path(folder) / MEDIA_INPUTS_DIR
    if not inputs.is_dir():
        return 0
    removed = 0
    for path in sorted(inputs.iterdir()):
        if not path.is_file():
            continue
        if path.name == PUBLICATION_LEDGER or _owned_artifact_digest(path) is not None:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    try:
        inputs.rmdir()
    except OSError:
        pass
    return removed


def publish_transcript(conn, video_id: str, *, cues, media_block, artifacts, ticket=None) -> dict:
    """Publish one coherent snapshot: validated inputs, the ownership fence
    rechecked under ``BEGIN IMMEDIATE`` before any file is touched, the
    ledger claim written first, owned files replaced atomically with the
    complete sidecar last, then the DB rows committed together and obsolete
    owned artifacts pruned. A crash between steps leaves an explicit state
    that a retry with the same durable inputs completes. ``ticket`` is the
    original build-time fence; it is never minted here."""
    try:
        if ticket is None:
            raise _request("publication_ticket_required")
        if not isinstance(ticket, PublicationTicket) or ticket.video_id != video_id:
            raise _request("ticket_identity")
        item = _load_item(conn, video_id)
        block = validate_media_block(media_block)
        if block["video_id"] != video_id:
            raise _invalid("cross_item_annotations")
        cues = [dict(cue) for cue in (cues or [])]
        _bind_cues(block, cues, stale_code="invalid_source_data")
        if not isinstance(artifacts, dict):
            raise _request("artifacts_type")
        folder = _item_folder(item).resolve()
        sidecar_path = Path(item["sidecar_path"]).resolve()
        corpus_path = Path(item["corpus_path"]).resolve()
        owned: dict[Path, bytes] = {}
        for raw_path, data in artifacts.items():
            if not isinstance(raw_path, (str, Path)) or not isinstance(data, (bytes, bytearray)):
                raise _request("artifact_bytes")
            path = Path(raw_path).resolve()
            if not path.is_relative_to(folder):
                raise _request("artifact_outside_item")
            if path == _ledger_path(folder).resolve():
                raise _request("ledger_not_publishable")
            owned[path] = bytes(data)
        sidecar_bytes = owned.get(sidecar_path)
        if sidecar_bytes is None:
            raise _request("sidecar_artifact_required")
        sidecar = _parse_json_object(sidecar_bytes, "sidecar")
        if sidecar.get("video_id") != video_id:
            raise _invalid("sidecar_identity")
        if json.loads(_json(block)) != json.loads(_json(sidecar.get("media_depth"))):
            raise _invalid("sidecar_block_mismatch")
        recovered = _cues_from_sidecar(sidecar, block, item)
        if [cue_core(c) for c in recovered] != [cue_core(c) for c in cues]:
            raise _invalid("sidecar_transcript_mismatch")
        for cue, source in zip(cues, recovered):
            for key in ("youtube_deep_link", "file_path"):
                cue.setdefault(key, source[key])
        corpus_bytes = owned.get(corpus_path)
        if corpus_bytes is None:
            corpus_bytes = _read_bytes(corpus_path, required=True)
        if block["provenance"]["corpus_revision"] != _sha256(corpus_bytes):
            raise _invalid("corpus_revision_mismatch")
        _verify_artifacts(folder, block, cues, owned=owned)
        projected = project_clips(cues, item, annotations=block)
        head = corpus_bytes[:_cards.CORPUS_READ_BYTES].decode("utf-8", "replace")
        source_now = _cards.build_card(_merge_item(item), projected, corpus_text=head)["source_revision"]
        if source_now != block["source_revision"]:
            raise _stale("source_revision_changed")

        # Current state under the item's storage lock: deletion, corpus
        # bytes, sidecar dependencies and the ownership fence are rechecked
        # here, and every conflict refuses before any file is touched.
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        item = _load_item(conn, video_id)
        target = block["media_revision"]
        current_block = None
        current_sidecar, disk_side = _sidecar_from_disk(sidecar_path)
        if isinstance(disk_side, dict):
            candidate = disk_side.get("media_depth")
            if isinstance(candidate, dict) and _is_hash(candidate.get("media_revision")):
                current_block = candidate
        disk_corpus = _read_bytes(corpus_path, required=False)
        # Protect user-edited corpus bytes even before the first media block
        # exists (BD-06). A disk file that still matches the recorded current
        # snapshot is a legitimate replacement, not an edit.
        if disk_corpus is not None and disk_corpus != corpus_bytes:
            recorded = (current_block.get("provenance") or {}).get("corpus_revision") \
                if current_block is not None and isinstance(current_block.get("provenance"), dict) else None
            if recorded != _sha256(disk_corpus):
                raise _stale("corpus_edited")
        generation, current, ledger = _publication_state(conn, video_id, folder)
        history = list(ledger["history"]) if ledger is not None else []
        # The sidecar on disk must be one this publication knows: the ledger's
        # current or in-flight base snapshot, this target, or the base the
        # ticket was minted against. Anything else belongs to another owner.
        if ledger is not None and current_block is not None and current_block["media_revision"] not in (
                current, target, ticket.base_media_revision, ledger.get("base_media_revision")):
            raise _stale("sidecar_foreign_snapshot")
        # Recheck/merge preserved sidecar dependencies before replacing the
        # full carrier (BD-05), including a key another owner removed.
        _bind_sidecar_carrier(sidecar, sidecar_path, ticket, owned, video_id)
        reread, _disk_again = _sidecar_from_disk(sidecar_path)
        if reread != current_sidecar:
            _bind_sidecar_carrier(sidecar, sidecar_path, ticket, owned, video_id)
        if current == target:
            # This publication already holds the claim (retry or idempotent
            # republication): settle it without a new generation.
            next_generation = generation
        else:
            if (generation, current) != ticket.base:
                raise _stale("publication_superseded", base_generation=ticket.base_generation,
                             current_generation=generation)
            if target in history:
                raise _stale("superseded_snapshot")
            next_generation = generation + 1
            if current is not None:
                history.append(current)
            history = history[-LEDGER_HISTORY_LIMIT:]
        if not _has_column(conn, "clips", "speaker_spans_json"):
            raise MediaError("library_unavailable", details={"reason": "schema_not_migrated"})

        # Files: the ledger claim first, then inputs, corpus, other owned
        # artifacts and the complete sidecar last.
        if current != target:
            _atomic_replace(_ledger_path(folder), _json({
                "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
                "video_id": video_id, "generation": next_generation, "media_revision": target,
                "base_media_revision": current, "history": history,
                "artifacts": sorted(_referenced_artifacts(block)),
            }).encode("utf-8"))
        ordered = ([p for p in owned if p.parent.name == MEDIA_INPUTS_DIR]
                   + ([corpus_path] if corpus_path in owned else [])
                   + [p for p in owned if p.parent.name != MEDIA_INPUTS_DIR and p not in (corpus_path, sidecar_path)])
        for path in ordered:
            data = owned[path]
            existing = _read_bytes(path, required=False)
            if existing == data:
                continue
            _atomic_replace(path, data)
        # Final carrier write: revalidate non-owned keys after ledger/artifact
        # work so an intervening edit or removal is not overwritten.
        _bind_sidecar_carrier(sidecar, sidecar_path, ticket, owned, video_id)
        sidecar_data = owned[sidecar_path]
        existing_sidecar = _read_bytes(sidecar_path, required=False)
        if existing_sidecar != sidecar_data:
            _atomic_replace(sidecar_path, sidecar_data)

        _insert_citations(conn, video_id, cues, block)
        _write_media_rows(conn, block)
        _write_clips(conn, video_id, projected)
        conn.commit()
        try:
            retention = prune_artifacts(conn, item)
        except (MediaError, OSError, KeyError, TypeError, ValueError):
            # The publication is committed; cleanup is retried at the next
            # settlement or by an explicit prune_artifacts call.
            retention = {"pruned": 0, "retained": 0, "cleanup_pending": True}
        return {"ok": True, "video_id": video_id, "source_revision": block["source_revision"],
                "media_revision": block["media_revision"], "clips": len(projected), "cues": len(cues),
                "generation": next_generation, "pruned_artifacts": retention["pruned"],
                "cleanup_pending": retention["cleanup_pending"]}
    except MediaError:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    except sqlite3.Error:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise MediaError("library_unavailable") from None


# --------------------------------------------------------------------------
# Snapshot builder for writers (local ASR transcripts)
# --------------------------------------------------------------------------
def transcript_snapshot(*, video_id: str, source_revision: str, cues: list[dict], transcript: dict,
                        transcript_bytes: bytes, corpus_revision: str, playback: dict,
                        transcript_provider: str = "whisperx", chapters: list[dict] | None = None,
                        chapter_source: dict | None = None, chapter_state: str = "unsupported",
                        chapter_reason: str | None = "adapter_unsupported",
                        timed: bool = True) -> tuple[dict, bytes]:
    """Build the sealed block for a local ASR transcript JSON. ``cues`` are
    the citation rows in seq order (``speaker`` taken from the segments).
    Returns ``(block, artifact_bytes)``; the caller archives the artifact
    under the item folder before publishing. ``timed`` says whether the
    item is a timed source (an empty timed capture stays ``absent``)."""
    cores = [cue_core(cue) for cue in cues]
    cue_rev = cue_revision(video_id, cores)
    record = transcript.get("diarization_run")
    record = record if isinstance(record, dict) else None
    core_bytes = transcript_artifact_bytes(transcript)
    invalid_record = False
    if record is not None and record.get("artifact_sha256") == _sha256(core_bytes):
        artifact = core_bytes            # new-style run: archive the pre-provenance core
    elif record is not None:
        artifact, record, invalid_record = transcript_bytes, None, True
    else:
        artifact = transcript_bytes      # legacy import archives the original file unchanged
    digest = _sha256(artifact)

    raw_labels = [cue.get("speaker") for cue in cues]
    labels_valid = all(label is None or _valid_label(label) for label in raw_labels)
    any_label = any(label is not None for label in raw_labels)
    runs: list[dict] = []
    active = None
    diarization_state = "not_requested"
    speaker_state, speaker_reason = "absent", "diarization_off"
    origin = None
    if record is not None and labels_valid:
        run = {
            "run_id": record.get("run_id"), "cue_revision": cue_rev,
            "status": "succeeded" if record.get("status") == "succeeded" else "failed",
            "producer": record.get("producer") or transcript_provider,
            "producer_version": record.get("producer_version"), "model": record.get("model"),
            "generated_at": record.get("generated_at"),
            "input_media_sha256": record.get("input_media_sha256"),
            "artifact_sha256": digest,
            "parameters": record.get("parameters") if isinstance(record.get("parameters"), dict)
            else {"language": transcript.get("language"), "alignment_model": None},
        }
        try:
            _validate_run(run, cue_rev)
        except MediaError:
            invalid_record = True
        else:
            runs, active, diarization_state = [run], run["run_id"], run["status"]
            if run["status"] == "failed":
                speaker_reason = "diarization_failed"
            elif any_label:
                origin = "run"
            else:
                speaker_reason = "unlabeled_cues"
    elif record is None and labels_valid and transcript.get("diarization_ran") is True and any_label:
        run = {"run_id": "legacy_" + digest, "cue_revision": cue_rev, "status": "legacy_reported",
               "producer": "legacy_transcript", "producer_version": None, "model": None,
               "generated_at": None, "input_media_sha256": None, "artifact_sha256": digest,
               "parameters": {"language": transcript.get("language"), "alignment_model": None}}
        runs, active, diarization_state, origin = [run], run["run_id"], "legacy_reported", "run"
    if not labels_valid or invalid_record:
        speaker_state, speaker_reason = "invalid", "invalid_metadata"
    elif origin is None and any_label:
        speaker_state, speaker_reason = "invalid", "unverified_legacy_label"

    annotated = []
    labeled = 0
    for core, label in zip(cores, raw_labels):
        digest_cue = cue_hash(video_id, core)
        entry = {"seq": core["seq"], "cue_hash": digest_cue, "speaker": None, "speaker_provenance": None}
        if origin == "run" and label is not None:
            entry["speaker"] = label
            entry["speaker_provenance"] = {"origin": "diarization_run", "cue_revision": cue_rev,
                                           "cue_hash": digest_cue, "source": None, "run_id": active}
            labeled += 1
        annotated.append(entry)
    if labeled and labeled == len(cores):
        speaker_state, speaker_reason = "present", None
    elif labeled:
        speaker_state, speaker_reason = "partial", "unlabeled_cues"
    if not cores and speaker_state == "absent":
        # A prose item is unsupported for timed annotations; an empty timed
        # capture is absent (nothing was supplied), never promoted to prose.
        speaker_state, speaker_reason = ("absent", "not_supplied") if timed else ("unsupported", "adapter_unsupported")

    # SQLite REAL columns return floats; seal the block with the same
    # representation the DB reconstruction will produce.
    chapters = [dict(chapter, start=float(chapter["start"]), end=float(chapter["end"]))
                if _is_number(chapter.get("start")) and _is_number(chapter.get("end")) else dict(chapter)
                for chapter in (chapters or [])]
    if chapters:
        chapter_state, chapter_reason = "present", None
    block = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
        "video_id": video_id, "source_revision": source_revision, "cue_revision": cue_rev,
        "media_revision": "0" * 64, "chapter_state": chapter_state, "speaker_state": speaker_state,
        "diarization_state": diarization_state,
        "provenance": {
            "chapter_source": chapter_source if chapters or chapter_state == "invalid" else None,
            "transcript_source": {"kind": "local_asr" if cores else "none",
                                  "artifact_sha256": digest if cores else None,
                                  "provider": transcript_provider if cores else None,
                                  "model": transcript.get("model") if cores else None,
                                  "language": transcript.get("language") if cores else None},
            "active_diarization_run_id": active,
            "absence_reason": {"chapters": chapter_reason, "speakers": speaker_reason},
            "corpus_revision": corpus_revision,
        },
        "playback": playback,
        "chapters": chapters, "runs": runs, "cues": annotated,
    }
    block["media_revision"] = media_revision(block)
    return validate_media_block(block), artifact


def capture_snapshot(*, video_id: str, source_revision: str, cues: list[dict], artifact_bytes: bytes,
                     corpus_revision: str, playback: dict, transcript_kind: str = "captions",
                     transcript_provider: str = "youtube_captions", language: str | None = None,
                     chapter_rows: list[dict] | None = None, chapter_provider: str = "youtube_metadata",
                     recorded_at: str | None = None, item: dict | None = None) -> tuple[dict, str]:
    """Build the sealed block for a capture whose caption cues and source
    chapter list are already held in one archived JSON artifact
    (``artifact_bytes``: the capture record whose ``chapters`` member is the
    original list ``yt_extract.chapters_from_metadata`` read). No run and
    no labels. ``chapter_rows`` are that helper's rows; an unusable list is
    recorded as ``chapter_state="invalid"`` with its descriptor, never
    guessed at. Returns ``(block, artifact_sha256)``."""
    digest = _sha256(artifact_bytes)
    cores = [cue_core(cue) for cue in cues]
    cue_rev = cue_revision(video_id, cores)
    descriptor = {"origin": "source_metadata", "provider": chapter_provider, "artifact_sha256": digest,
                  "record_locator": ["chapters"], "recorded_at": recorded_at}
    objects = []
    for row in chapter_rows or []:
        row = row if isinstance(row, dict) else {}
        start, end = row.get("start"), row.get("end")
        locator = row.get("record_locator")
        objects.append({
            "seq": row.get("seq"),
            "start": float(start) if _is_number(start) else start,
            "end": float(end) if _is_number(end) else end,
            "title": row.get("title"),
            "provenance": dict(descriptor, record_locator=list(locator) if isinstance(locator, list)
                               else ["chapters", row.get("seq")]),
        })
    chapter_state, chapter_reason, chapter_source = "absent", "not_supplied", None
    if objects:
        try:
            _validate_chapters(objects)
            if item is not None:
                _check_chapter_duration(objects, item)
        except MediaError:
            chapter_state, chapter_reason, chapter_source, objects = "invalid", "invalid_metadata", descriptor, []
        else:
            chapter_state, chapter_reason, chapter_source = "present", None, descriptor
    annotated = [{"seq": core["seq"], "cue_hash": cue_hash(video_id, core), "speaker": None,
                  "speaker_provenance": None} for core in cores]
    block = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
        "video_id": video_id, "source_revision": source_revision, "cue_revision": cue_rev,
        "media_revision": "0" * 64, "chapter_state": chapter_state, "speaker_state": "absent",
        "diarization_state": "not_requested",
        "provenance": {
            "chapter_source": chapter_source,
            "transcript_source": {"kind": transcript_kind if cores else "none",
                                  "artifact_sha256": digest if cores else None,
                                  "provider": transcript_provider if cores else None,
                                  "model": None, "language": language if cores else None},
            "active_diarization_run_id": None,
            "absence_reason": {"chapters": chapter_reason, "speakers": "diarization_off"},
            "corpus_revision": corpus_revision,
        },
        "playback": playback,
        "chapters": objects, "runs": [], "cues": annotated,
    }
    block["media_revision"] = media_revision(block)
    return validate_media_block(block), digest


# --------------------------------------------------------------------------
# Cited range export (read-only)
# --------------------------------------------------------------------------
_EXPORT_KEYS = frozenset({"video_id", "start", "end", "excerpt_id", "source_revision", "media_revision"})


def _validate_export_args(args) -> dict:
    if not isinstance(args, dict) or any(not isinstance(key, str) for key in args):
        raise _request("invalid_selector")
    if set(args) - _EXPORT_KEYS:
        raise _request("invalid_selector")
    video_id = args.get("video_id")
    try:
        _resources._validate_identity(video_id)
    except _resources.ResourceError:
        raise _request("invalid_selector") from None
    try:
        if _resources.wire_bytes(args) > _resources.LIMITS["max_request_bytes"]:
            raise _request("request_too_large")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise _request("invalid_selector") from None
    has_range = "start" in args or "end" in args
    has_excerpt = "excerpt_id" in args
    if has_range == has_excerpt:
        raise _request("invalid_selector")
    request = {"video_id": video_id, "mode": None, "start": None, "end": None, "excerpt_id": None,
               "source_revision": None, "media_revision": None}
    if has_range:
        if "start" not in args or "end" not in args:
            raise _request("invalid_selector")
        start, end = args["start"], args["end"]
        if not _is_number(start) or not _is_number(end):
            raise _request("invalid_selector")
        if not (0 <= start < end <= MAX_TIME_SECONDS):
            raise _request("invalid_selector")
        request.update(mode="range", start=float(start), end=float(end))
    else:
        excerpt_id = args["excerpt_id"]
        if not _is_hash(excerpt_id):
            raise _request("invalid_selector")
        request.update(mode="excerpt", excerpt_id=excerpt_id)
    for key in ("source_revision", "media_revision"):
        if key in args:
            if not _is_hash(args[key]):
                raise _request("invalid_selector")
            request[key] = args[key]
    return request


def _label_entry(source: dict, label: str) -> dict:
    return {"label": label, "provenance": {k: v for k, v in source.items() if k != "cue_hash"}}


def _attribution(block: dict, units: list[dict]) -> dict:
    labels: list[dict] = []
    referenced: set[str] = set()
    for unit in units:
        source = unit.get("speaker_provenance")
        if source is None:
            continue
        entry = _label_entry(source, unit["speaker"])
        if entry not in labels:
            labels.append(entry)
        if source.get("run_id"):
            referenced.add(source["run_id"])
    active = block["provenance"]["active_diarization_run_id"]
    if block["diarization_state"] == "failed" and active:
        referenced.add(active)
    runs = [run for run in block["runs"] if run["run_id"] in referenced]
    return {
        "speaker_state": block["speaker_state"],
        "diarization_state": block["diarization_state"],
        "diarization_ran": block["diarization_state"] in ("succeeded", "legacy_reported"),
        "labels": labels,
        "runs": runs,
        "chapter_state": block["chapter_state"],
        "absence_reason": dict(block["provenance"]["absence_reason"]),
    }


def _chapter_objects(block: dict, start, end) -> list[dict]:
    return [dict(chapter, video_id=block["video_id"], source_revision=block["source_revision"])
            for chapter in _overlapping(block["chapters"], start, end)]


def _clip_spans(snap: _Snapshot, clip: dict) -> list[dict]:
    """Contribution spans of one DB clip row; legacy rows without spans are
    re-projected from the current cues and matched by core."""
    try:
        spans = json.loads(clip.get("speaker_spans_json") or "[]")
    except ValueError:
        raise _invalid("clip_spans_json") from None
    if spans or not _cards._string(clip.get("text")):
        return spans
    block = snap.block if snap.materialized else None
    for projected in project_clips(snap.cues, snap.item, annotations=block):
        if all(projected.get(key) == clip.get(key) for key in ("seq", "start", "end", "text", "source_deep_link")):
            return json.loads(projected["speaker_spans_json"])
    raise _invalid("clip_projection_mismatch")


def _check_text_budget(verbatim: str, units: list[dict]) -> None:
    if len(verbatim) > MAX_EXPORT_CODEPOINTS or sum(len(u["text"]) for u in units) > MAX_EXPORT_CODEPOINTS:
        raise MediaError("resource_too_large", details={
            "reason": "text_budget", "limit_codepoints": MAX_EXPORT_CODEPOINTS,
            "next_step": "read_library_resource"})


def _export_range(snap: _Snapshot, request: dict, check) -> dict:
    block = snap.block
    start, end = request["start"], request["end"]
    if not snap.cues:
        raise _request("not_timed", timing_kind="not_timed", next_step="get_library_item")
    selected: list[int] = []
    for index, cue in enumerate(snap.cues):
        s, e = cue.get("timestamp_start"), cue.get("timestamp_end")
        if not _cards._string(cue.get("text")):
            continue
        if not (_is_number(s) and _is_number(e)):
            continue
        if s < end and start < e:
            selected.append(index)
    if not selected:
        raise _request("empty_range", requested_start=start, requested_end=end)
    previous = None
    for index in selected:
        cue = snap.cues[index]
        s, e = cue["timestamp_start"], cue["timestamp_end"]
        if e <= s or s < 0 or e > MAX_TIME_SECONDS:
            raise _invalid("cue_timing_ineligible", seq=cue.get("seq"))
        if previous is not None and s < previous:
            raise _invalid("cue_order_inconsistent", seq=cue.get("seq"))
        previous = s
    coarse = [{"start": snap.cues[i]["timestamp_start"], "end": snap.cues[i]["timestamp_end"]}
              for i in selected
              if snap.cues[i]["timestamp_end"] - snap.cues[i]["timestamp_start"] > _clips.MAX_WINDOW_SECONDS]
    if coarse:
        raise _request("coarse_timing", timing_kind="coarse", requested_start=start, requested_end=end,
                       enclosing_intervals=coarse, next_step="read_library_resource")
    if end - start > MAX_RANGE_SECONDS:
        raise MediaError("resource_too_large", details={
            "reason": "range_duration", "limit_seconds": MAX_RANGE_SECONDS, "next_step": "read_library_resource"})
    if len(selected) > MAX_RANGE_CUES:
        raise MediaError("resource_too_large", details={
            "reason": "range_cues", "limit_cues": MAX_RANGE_CUES, "next_step": "read_library_resource"})
    first_start = snap.cues[selected[0]]["timestamp_start"]
    last_end = max(snap.cues[i]["timestamp_end"] for i in selected)
    min_start = min(snap.cues[i]["timestamp_start"] for i in selected)
    if first_start != start or last_end != end or min_start < start:
        raise _request("unaligned_range", requested_start=start, requested_end=end,
                       enclosing_start=min_start, enclosing_end=last_end)
    check()
    units = []
    for index in selected:
        cue, annotation = snap.cues[index], block["cues"][index]
        units.append({"cue_seq": cue.get("seq"), "cue_hash": annotation["cue_hash"],
                      "start": cue["timestamp_start"], "end": cue["timestamp_end"],
                      "text": cue["text"], "speaker": annotation["speaker"],
                      "speaker_provenance": annotation["speaker_provenance"]})
    verbatim = "\n".join(unit["text"] for unit in units)
    _check_text_budget(verbatim, units)
    selected_hashes = {unit["cue_hash"] for unit in units}
    refs = []
    for excerpt_id, clip in _clip_evidence(snap.item["video_id"], snap.clip_rows):
        if any(span.get("cue_hash") in selected_hashes for span in _clip_spans(snap, clip)):
            ref = {"source_revision": snap.source_revision, "excerpt_id": excerpt_id}
            if ref not in refs:
                refs.append(ref)
    first = snap.cues[selected[0]]
    seek_link, seek_seconds = _seek_link(block["playback"], snap.item["video_id"], start)
    citation = {
        "evidence_kind": "transcript_range", "timing": "source_cues", "start": start, "end": end,
        "verbatim_text": verbatim, "text_basis": "stored_cues", "separator": "\n",
        "source_deep_link": _resources.safe_url(first.get("source_deep_link")),
        "seek_link": seek_link, "player_seek_seconds": seek_seconds, "truncated": False,
    }
    return {"citation": citation, "units": units, "chapters": _chapter_objects(block, start, end),
            "attribution": _attribution(block, units),
            "provenance": {"cue_revision": block["cue_revision"],
                           "transcript_source": dict(block["provenance"]["transcript_source"]),
                           "evidence_refs": refs, "render_version": RENDER_VERSION}}


def _export_excerpt(snap: _Snapshot, request: dict, check) -> dict:
    block = snap.block
    video_id = snap.item["video_id"]
    excerpt_id = request["excerpt_id"]
    match = next(((eid, clip) for eid, clip in _clip_evidence(video_id, snap.clip_rows) if eid == excerpt_id), None)
    if match is None:
        prose = snap.prose
        prose_id = _hash([video_id, "opening_prose", prose]) if prose else None
        if prose_id != excerpt_id:
            raise _stale("excerpt_not_current")
        if snap.item.get("source_type") not in _cards.PROSE_ELIGIBLE_SOURCES:
            raise _invalid("hint_is_not_evidence")
        units = [{"excerpt_id": excerpt_id, "text": prose}]
        _check_text_budget(prose, units)
        citation = {
            "evidence_kind": "text_only", "timing": "not_timed", "start": None, "end": None,
            "verbatim_text": prose, "text_basis": "opening_prose", "separator": None,
            "source_deep_link": _resources.safe_url(_item_url(snap.item)),
            "seek_link": None, "player_seek_seconds": None, "truncated": False,
        }
        return {"citation": citation, "units": units, "chapters": [],
                "attribution": _attribution(block, []),
                "provenance": {"cue_revision": None,
                               "transcript_source": dict(block["provenance"]["transcript_source"]),
                               "evidence_refs": [{"source_revision": snap.source_revision, "excerpt_id": excerpt_id}],
                               "render_version": RENDER_VERSION}}
    _, clip = match
    if _clips.timing_kind(clip) == "coarse":
        raise _request("coarse_timing", timing_kind="coarse", excerpt_id=excerpt_id,
                       enclosing_intervals=[{"start": clip["start"], "end": clip["end"]}],
                       next_step="read_library_resource")
    if _clips.timing_kind(clip) != "source_cues":
        raise _invalid("clip_timing_unknown")
    raw_link = clip.get("source_deep_link")
    link = _resources.safe_url(raw_link)
    if raw_link and link is None:
        raise _invalid("unsafe_hashed_link")
    check()
    by_seq = {annotation["seq"]: annotation for annotation in block["cues"]}
    text = clip["text"]
    units = []
    for span in _clip_spans(snap, clip):
        annotation = by_seq.get(span["cue_seq"])
        if annotation is None or annotation["cue_hash"] != span["cue_hash"]:
            raise _stale("clip_span_binding")
        units.append({"cue_seq": span["cue_seq"], "cue_hash": span["cue_hash"], "start": span["start"],
                      "end": span["end"], "text": text[span["text_start"]:span["text_end"]],
                      "text_start": span["text_start"], "text_end": span["text_end"],
                      "speaker": annotation["speaker"], "speaker_provenance": annotation["speaker_provenance"]})
    _check_text_budget(text, units)
    seek_link, seek_seconds = _seek_link(block["playback"], video_id, clip["start"])
    citation = {
        "evidence_kind": "timed_clip", "timing": "source_cues", "start": clip["start"], "end": clip["end"],
        "verbatim_text": text, "text_basis": "clip_projection", "separator": None,
        "source_deep_link": link, "seek_link": seek_link, "player_seek_seconds": seek_seconds,
        "truncated": False,
    }
    return {"citation": citation, "units": units,
            "chapters": _chapter_objects(block, clip["start"], clip["end"]),
            "attribution": _attribution(block, units),
            "provenance": {"cue_revision": block["cue_revision"],
                           "transcript_source": dict(block["provenance"]["transcript_source"]),
                           "evidence_refs": [{"source_revision": snap.source_revision, "excerpt_id": excerpt_id}],
                           "render_version": RENDER_VERSION}}


class _ReadTransaction:
    """One deferred SQLite read transaction for the coherent export body,
    with the connection's busy timeout bounded by the time left before
    ``deadline`` so a writer holding the database yields
    ``deadline_exceeded`` (via the storage error path) instead of an
    unbounded wait. Never commits. ``refresh`` drops that snapshot and
    opens a new deferred read so the final recheck can see WAL commits."""

    __slots__ = ("conn", "clock", "deadline", "began", "restore")

    def __init__(self, conn, clock, deadline: float):
        self.conn = conn
        self.clock = clock
        self.deadline = deadline
        self.began = False
        self.restore = None

    def _begin_deferred(self) -> None:
        if not self.conn.in_transaction:
            self.conn.execute("BEGIN DEFERRED")
            self.began = True

    def refresh(self) -> None:
        """End the coherent-read snapshot and begin a new deferred
        transaction. A second WAL connection's committed change is then
        visible; rollback-journal writers still cannot commit while the
        original snapshot is held."""
        if self.began and self.conn.in_transaction:
            try:
                self.conn.rollback()
            except sqlite3.Error:
                pass
            self.began = False
        self._begin_deferred()

    def __enter__(self):
        remaining_ms = max(0, int((self.deadline - float(self.clock())) * 1000.0))
        try:
            row = self.conn.execute("PRAGMA busy_timeout").fetchone()
            self.restore = int(row[0]) if row is not None else None
            # Only ever shorten the connection's own wait: the deadline is a
            # ceiling on lock waits, never a licence to wait longer.
            ceiling_ms = self.restore if self.restore is not None else \
                int(float(_resources.LIMITS["service_deadline_s"]) * 1000.0)
            self.conn.execute(f"PRAGMA busy_timeout={min(remaining_ms, ceiling_ms)}")
        except sqlite3.Error:
            self.restore = None
        self._begin_deferred()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.began and self.conn.in_transaction:
                self.conn.rollback()
        except sqlite3.Error:
            pass
        if self.restore is not None:
            try:
                self.conn.execute(f"PRAGMA busy_timeout={self.restore}")
            except sqlite3.Error:
                pass
        return False


def _export(conn, request: dict, *, clock, deadline: float) -> dict:
    def check():
        if float(clock()) > deadline:
            raise MediaError("deadline_exceeded", details={"deadline_s": _resources.LIMITS["service_deadline_s"]})

    if conn is None:
        raise MediaError("library_unavailable", details={"reason": "no_storage"})
    check()
    with _ReadTransaction(conn, clock, deadline) as tx:
        snap = _read_snapshot(conn, request["video_id"])
        check()
        block = snap.block
        for key, current in (("source_revision", snap.source_revision), ("media_revision", block["media_revision"])):
            if request[key] is not None and request[key] != current:
                raise _stale(key + "_mismatch")
        body = _export_range(snap, request, check) if request["mode"] == "range" else _export_excerpt(snap, request, check)
        check()
        # The deferred snapshot that built the body cannot see a second WAL
        # connection's commit; refresh so the final recheck can refuse it.
        tx.refresh()
        _recheck_snapshot(conn, snap)
    item = snap.item
    result = {
        "ok": True, "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION,
        "item": {"video_id": item["video_id"], "title": item.get("title"), "platform": item.get("platform"),
                 "source_type": item.get("source_type"), "source_url": _resources.safe_url(_item_url(item)),
                 "source_revision": snap.source_revision, "media_revision": block["media_revision"]},
        "selection": {"mode": request["mode"], "requested_start": request["start"],
                      "requested_end": request["end"], "excerpt_id": request["excerpt_id"]},
        **body,
    }
    check()
    rendered = _resources.render_tool_text(result)
    if len(rendered.encode("utf-8")) > _resources.LIMITS["max_resource_text_bytes"]:
        raise MediaError("resource_too_large", details={
            "reason": "rendered_text", "limit_bytes": _resources.LIMITS["max_resource_text_bytes"],
            "next_step": "read_library_resource"})
    wire = _resources.wire_bytes({"structuredContent": result, "content": [{"type": "text", "text": rendered}]})
    if wire > _resources.LIMITS["max_response_bytes"]:
        raise MediaError("resource_too_large", details={
            "reason": "response_bytes", "limit_bytes": _resources.LIMITS["max_response_bytes"],
            "next_step": "read_library_resource"})
    return result


class _BoundedIndexLock:
    """Acquire an index lock within the time left before ``deadline`` or
    refuse ``deadline_exceeded`` at once; the adapter never waits past the
    request's own deadline. ``None`` is a no-op."""

    __slots__ = ("lock", "clock", "deadline", "held")

    def __init__(self, lock, clock, deadline: float):
        self.lock = lock
        self.clock = clock
        self.deadline = deadline
        self.held = False

    def __enter__(self):
        if self.lock is None:
            return self
        remaining = self.deadline - float(self.clock())
        if remaining <= 0:
            raise MediaError("deadline_exceeded", details={
                "deadline_s": _resources.LIMITS["service_deadline_s"], "reason": "lock_wait"})
        try:
            acquired = self.lock.acquire(timeout=min(remaining, float(_resources.LIMITS["service_deadline_s"])))
        except TypeError:  # a lock double without a timeout parameter
            acquired = self.lock.acquire()
        if not acquired:
            raise MediaError("deadline_exceeded", details={
                "deadline_s": _resources.LIMITS["service_deadline_s"], "reason": "lock_wait"})
        self.held = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.held:
            self.held = False
            self.lock.release()
        return False


def _admitted_export(request: dict, *, clock, bind) -> dict:
    """One admission on the shared Phase 4 process guard (no second pool):
    the deadline runs from the admission timestamp through storage binding
    (``bind() -> (connection, lock | None)``), the bounded lock wait, the
    coherent read and the wire checks."""
    guard = _resources._PROCESS_GUARD or _resources.process_guard()
    try:
        admitted = guard.admit()
    except _resources.ResourceError as exc:
        return _refuse(exc.code, details=exc.details, message=exc.message)
    deadline = float(admitted) + float(_resources.LIMITS["service_deadline_s"])
    try:
        conn, index_lock = bind()
        with _BoundedIndexLock(index_lock, clock, deadline):
            return _export(conn, request, clock=clock, deadline=deadline)
    except MediaError as exc:
        return exc.envelope()
    except _resources.ResourceError as exc:
        return _refuse(exc.code, details=exc.details, message=exc.message)
    except sqlite3.Error:
        return _refuse("library_unavailable", details={"reason": "storage_error"})
    finally:
        guard.release()


def export_cited_range(conn, args: dict, *, clock=None) -> dict:
    """Read-only cited range export on an open connection. Strict syntax
    refusals happen before any storage access; admission, deadline and
    budgets reuse Phase 4's guard."""
    try:
        request = _validate_export_args(args)
    except MediaError as exc:
        return exc.envelope()
    return _admitted_export(request, clock=clock or time.monotonic, bind=lambda: (conn, None))


def export_cited_range_tool(args, backend, *, clock=None) -> dict:
    """Registry/stdio adapter: exact input rejection before any storage
    access, then one Phase 4 admission, lazy binding of an *existing* index
    only (``library_resources._existing_index_factory``: never created or
    recovered), a lock wait bounded by the same deadline, and the export."""
    try:
        request = _validate_export_args(args)
    except MediaError as exc:
        return exc.envelope()

    def bind():
        try:
            index = _resources._existing_index_factory(backend)()
        except _resources.ResourceError:
            raise
        except Exception as exc:
            raise MediaError("library_unavailable", details={"storage": type(exc).__name__}) from None
        if index is None:
            raise MediaError("library_unavailable", details={"storage": "no_index"})
        conn = getattr(index, "_conn", None)
        if conn is None or not hasattr(conn, "execute"):
            raise MediaError("library_unavailable", details={"storage": "no_connection"})
        lock = getattr(index, "_lock", None)
        if lock is not None and not (callable(getattr(lock, "acquire", None)) and callable(getattr(lock, "release", None))):
            lock = None
        return conn, lock

    return _admitted_export(request, clock=clock or time.monotonic, bind=bind)


EXPORT_TOOL_NAME = "export_cited_range"
EXPORT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "video_id": {"type": "string", "description": "Stable item id."},
        "start": {"type": "number", "minimum": 0,
                  "description": "Range start in seconds; must equal the first selected cue's start (with end)."},
        "end": {"type": "number", "minimum": 0,
                "description": "Range end in seconds; must equal the last selected cue's end (with start)."},
        "excerpt_id": {"type": "string", "description": "A current excerpt id (instead of start/end)."},
        "source_revision": {"type": "string", "description": "Optional pin; refuses revision_unavailable on change."},
        "media_revision": {"type": "string", "description": "Optional pin; refuses revision_unavailable on change."},
    },
    "required": ["video_id"],
    "additionalProperties": False,
}
EXPORT_TOOL_DESCRIPTION = (
    "Read-only cited export of one stored transcript range (exact cue-aligned "
    "start/end, at most 120 s and 200 cues) or one current excerpt id from a "
    "saved item: verbatim stored text, per-cue speaker labels with provenance, "
    "overlapping chapters, safe source and seek links, source/media revisions "
    "and evidence refs. Nothing is fetched, transcribed or saved; refusals "
    "carry a next_step."
)

"""library_mirror.py - Opt-in corpus mirror (contract phase4-v1-2026-09-08).

One-way generated view of Librarian cards, shelf pages and accepted briefs
under ``<vault>/Uoink/``. Vault I/O is derived delivery state: it never
owns Phase 2 pins, exclusive policies or the correction journal, never
reads ``TASTE.md`` / ``USER.md`` back, and never routes through
``memory_layer.write_user``.

Contract rules this module does not implement exactly, and why
--------------------------------------------------------------
1. Isolated worker cancellation. Vault I/O runs on a daemon thread with a
   join timeout (2 s default) so a disconnected volume cannot hold the
   caller's deadline. Python cannot abort a blocked syscall; the thread is
   abandoned on timeout and the attempt is not acknowledged without a
   receipt/manifest recheck. Reason: no portable way to cancel ``open`` on
   a hung drive without a child process, which the brief forbids.
2. Mirror-specific codes (``destination_unavailable``, ``user_edit_conflict``,
   ``unmanaged_conflict``, ``path_collision``, ``purge_blocked_user_edit``)
   are returned through ``library_resources.refusal``, not
   ``ResourceError``, because that type remaps unknown codes to
   ``internal_error``.
3. Brief artifacts are exported only when a ``brief_store`` with
   ``latest_valid`` / ``read`` / ``purge_dependents`` is supplied. The
   ``library_briefs`` import is optional so this module loads without it.
4. ``st_nlink > 1`` is treated as a containment/ownership failure on the
   destination file. Windows link counts are not always meaningful; the
   check is skipped when ``st_nlink`` is missing or zero.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import secrets
import stat
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator

import library_cards
from library_resources import (
    CONTRACT_VERSION as _RESOURCES_CONTRACT,
    LIMITS,
    RENDER_VERSION,
    SCHEMA_VERSION,
    ResourceError,
    label,
    refusal,
    safe_url,
)

try:
    import library_briefs as _library_briefs  # optional; guarded for import-time
except ImportError:
    _library_briefs = None  # type: ignore[assignment]

log = logging.getLogger("uoink.library_mirror")

CONTRACT_VERSION = "phase4-v1-2026-09-08"
MIRROR_LEDGER_DIR = "reach/mirror"
MIRROR_ROOT = "Uoink"
SCOPE_ALL = "all_current_and_future_items"

MAX_FILE_BYTES = 65536
DEFAULT_MAX_FILES = 20
DEFAULT_BUDGET_S = 2.0
VOLUME_MARKER_NAME = ".uoink-volume-marker"
MANIFEST_REL = ".uoink-mirror/manifest.json"
LIBRARY_INDEX_REL = "Library.md"
TASTE_NAME = "TASTE.md"
USER_NAME = "USER.md"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BRIEF_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-([0-9a-f]{64})\.md$")
_OUR_TMP_RE = re.compile(r"^[0-9a-f]{12,24}$")

_CONTENT_KINDS = frozenset({
    "capture", "source_refresh", "apply", "undo", "pin",
    "brief_published", "restore",
})
_TOMBSTONE_KINDS = frozenset({"soft_delete"})
_PURGE_KINDS = frozenset({"hard_purge"})

INDEXING_NOTICE = (
    "Other software with access to this vault can index its contents. "
    "Uoink does not register the vault with Basic Memory/Hermes, start "
    "another indexer, edit its configuration, turn on sync, or infer "
    "consent from an installed application. Existing third-party indexing "
    "is outside Uoink's deletion control."
)
EDITS_NOTICE = "Edits to this file are not imported."
TOMBSTONE_BODY = "This library item was deleted. Source content is not exported.\n"


# --------------------------------------------------------------------------
# Public types
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MirrorConsent:
    destination: str
    scope: str
    allowlist: tuple[str, ...]
    consented_at_ms: int
    marker: str


# --------------------------------------------------------------------------
# Small pure helpers
# --------------------------------------------------------------------------
def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_date(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def identity_hash(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def item_relpath(video_id: str) -> str:
    return f"Library/{identity_hash(video_id)}.md"


def shelf_relpath(shelf_id: str) -> str:
    return f"Shelves/{identity_hash(shelf_id)}.md"


def brief_relpath(date: str, brief_hash: str) -> str:
    return f"Briefs/{date}-{brief_hash}.md"


def item_key(video_id: str) -> str:
    return f"item:{video_id}"


def shelf_key(shelf_id: str) -> str:
    return f"shelf:{shelf_id}"


def brief_key(date: str, brief_hash: str) -> str:
    return f"brief:{date}:{brief_hash}"


def index_key() -> str:
    return "index:Library.md"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str | None:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _yaml_quote(value: str) -> str:
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f"\"{escaped}\""


def _break_injections(text: str) -> str:
    """Neutralize wikilinks and raw HTML tag openers in generated views."""
    text = text.replace("[[", "[\\[")
    text = text.replace("]]", "\\]]")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, int) and not isinstance(value, bool):
            lines.append(f"{key}: {value}")
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: {_yaml_quote(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _cap_utf8(text: str, limit: int = MAX_FILE_BYTES) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    cut = raw[:limit]
    while cut:
        try:
            return cut.decode("utf-8")
        except UnicodeDecodeError:
            cut = cut[:-1]
    return ""


def _rel_is_allowed(rel: str) -> bool:
    if rel in (LIBRARY_INDEX_REL, MANIFEST_REL):
        return True
    if rel.startswith("Library/") and rel.endswith(".md"):
        stem = rel[len("Library/"):-3]
        return bool(_HEX64_RE.match(stem))
    if rel.startswith("Shelves/") and rel.endswith(".md"):
        stem = rel[len("Shelves/"):-3]
        return bool(_HEX64_RE.match(stem))
    if rel.startswith("Briefs/") and rel.endswith(".md"):
        name = rel[len("Briefs/"):]
        return bool(_BRIEF_NAME_RE.match(name))
    return False


def _is_reparse(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attrs = getattr(info, "st_file_attributes", 0)
    return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _contained(root: Path, path: Path) -> bool:
    try:
        root_r = root.resolve()
        path_r = path.resolve()
    except OSError:
        return False
    root_s = os.path.normcase(str(root_r))
    path_s = os.path.normcase(str(path_r))
    sep = os.sep
    return path_s == root_s or path_s.startswith(root_s + sep)


def _escaping_reparse(root: Path, path: Path) -> bool:
    try:
        root_r = root.resolve()
    except OSError:
        return True
    current = path
    seen = 0
    while seen < 64:
        seen += 1
        if _is_reparse(current):
            try:
                resolved = current.resolve()
            except OSError:
                return True
            if not _contained(root_r, resolved) and resolved != root_r:
                return True
        if current == current.parent:
            break
        try:
            if current.resolve() == root_r:
                break
        except OSError:
            return True
        current = current.parent
    return False


def _hardlink_conflict(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    nlink = getattr(info, "st_nlink", 1)
    return isinstance(nlink, int) and nlink > 1


def _path_too_long(path: Path) -> bool:
    text = str(path)
    return len(text) > 240 or len(text.encode("utf-8", errors="replace")) > 240


def _mirror_refusal(code: str, message: str, *, retryable: bool = False,
                    details: dict | None = None, **extra) -> dict:
    envelope = refusal(code, message, retryable=retryable, details=details)
    envelope.update(extra)
    return envelope


def _ok(**fields) -> dict:
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        **fields,
    }


# --------------------------------------------------------------------------
# Mirror
# --------------------------------------------------------------------------
class Mirror:
    """Opt-in one-way corpus mirror. Ledger under data_root; files under vault/Uoink."""

    def __init__(self, index, reader, brief_store, *, data_root,
                 consent: MirrorConsent | None, enabled: bool,
                 clock: Callable[[], float] | None = None,
                 wall_clock: Callable[[], float] | None = None):
        self.index = index
        self.reader = reader
        self.brief_store = brief_store
        self.data_root = Path(data_root)
        self.consent = consent
        self.enabled = bool(enabled)
        self._clock = clock or time.monotonic
        self._wall = wall_clock or time.time
        self._thread_lock = threading.RLock()
        self.ledger_dir = self.data_root / MIRROR_LEDGER_DIR

    # ---- public API ----------------------------------------------------
    def preview(self, destination: str, scope: str,
                allowlist: list[str] | None = None) -> dict:
        dest = Path(destination) if destination else None
        if dest is None or not self._destination_exists(dest):
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                planned_paths=[],
                counts={"items": 0, "shelves": 0, "briefs": 0},
                notice=INDEXING_NOTICE,
                indexing=INDEXING_NOTICE,
                third_party_indexing=INDEXING_NOTICE,
                destination_unavailable=True,
            )
        allow = tuple(allowlist or ())
        items = self._in_scope_items(scope, allow)
        shelves = self._in_scope_shelves(scope, allow, items)
        briefs = self._in_scope_briefs(scope, allow)
        planned: list[str] = []
        for item in items:
            planned.append(item_relpath(item["video_id"]))
        for shelf in shelves:
            planned.append(shelf_relpath(shelf["shelf_id"]))
        for brief in briefs:
            planned.append(brief_relpath(brief["date"], brief["brief_hash"]))
        planned.append(LIBRARY_INDEX_REL)
        planned.append(MANIFEST_REL)
        uoink = dest / MIRROR_ROOT
        conflicts: list[dict] = []
        for rel in planned:
            path = uoink / rel
            try:
                if path.exists() and path.is_file():
                    conflicts.append({"path": rel, "code": "unmanaged_conflict"})
            except OSError:
                pass
        return _ok(
            planned_paths=planned,
            paths=planned,
            counts={"items": len(items), "shelves": len(shelves), "briefs": len(briefs)},
            notice=INDEXING_NOTICE,
            indexing=INDEXING_NOTICE,
            third_party_indexing=INDEXING_NOTICE,
            conflicts=conflicts,
            destination=str(dest),
            scope=scope,
        )

    def status(self) -> dict:
        if self.consent is None or not self.consent.destination:
            return _ok(
                enabled=False,
                state="disabled",
                pending=0,
                synced=0,
                stale=0,
                conflicts={},
                deletion_pending=0,
                destination_state="disabled",
                destination_available=False,
            )
        dest = Path(self.consent.destination)
        available = self._destination_exists(dest)
        ledger = self._load_ledger()
        pending = synced = stale = deletion_pending = 0
        user_edits: list[dict] = []
        for key, entry in ledger.get("entries", {}).items():
            action = entry.get("pending_action") or "none"
            status = entry.get("status") or ""
            if action in ("purge", "tombstone") or status == "deletion_pending":
                deletion_pending += 1
            elif action == "write" or status == "pending":
                pending += 1
            elif status == "stale":
                stale += 1
            elif status == "synced":
                synced += 1
            if status == "user_edit_conflict":
                user_edits.append({"key": key, "path": entry.get("relpath")})
                pending += 1
        unmanaged = []
        collisions = []
        if available:
            unmanaged, collisions, extra_edits = self._scan_conflicts(dest, ledger)
            user_edits.extend(extra_edits)
        else:
            return _ok(
                enabled=bool(self.enabled),
                state="destination_unavailable",
                pending=pending,
                synced=0,
                stale=stale,
                conflicts={"user_edit": user_edits, "unmanaged": [], "path_collision": []},
                deletion_pending=deletion_pending,
                destination_state="unavailable",
                destination_available=False,
                destination_unavailable=True,
            )
        conflicts = {
            "user_edit": user_edits,
            "unmanaged": unmanaged,
            "path_collision": collisions,
        }
        paused = bool(ledger.get("exports_paused"))
        return _ok(
            enabled=bool(self.enabled),
            state="disabled" if not self.enabled else ("paused" if paused else "ready"),
            pending=pending,
            synced=synced,
            stale=stale,
            conflicts=conflicts,
            unmanaged=unmanaged,
            deletion_pending=deletion_pending,
            destination_state="available",
            destination_available=True,
            exports_paused=paused,
        )

    def resync(self, *, max_files: int = DEFAULT_MAX_FILES, budget_s: float = DEFAULT_BUDGET_S) -> dict:
        if self.consent is None or not self.consent.destination:
            return _ok(synced=0, enabled=False, state="disabled")
        if not self.enabled:
            ledger = self._load_ledger()
            has_deletions = any(
                (e.get("pending_action") in ("purge", "tombstone") or e.get("status") == "deletion_pending")
                for e in ledger.get("entries", {}).values()
            )
            if not has_deletions:
                return _ok(synced=0, enabled=False, state="disabled")
        start = float(self._clock())
        try:
            with self._exclusive(timeout=max(0.05, float(budget_s))):
                remaining = float(budget_s) - (float(self._clock()) - start)
                return self._resync_locked(max_files=int(max_files), budget_s=max(0.0, remaining))
        except _LockTimeout:
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                synced=0,
            )

    def on_committed_event(self, kind: str, *, video_id: str | None = None,
                           shelf_id: str | None = None, brief_hash: str | None = None) -> None:
        if self.consent is None or not self.consent.destination:
            return
        if not self.enabled and kind not in _PURGE_KINDS and kind not in _TOMBSTONE_KINDS:
            return
        try:
            with self._exclusive(timeout=2.0):
                self._record_event(kind, video_id=video_id, shelf_id=shelf_id, brief_hash=brief_hash)
        except Exception:
            log.exception("mirror ledger update failed for %s", kind)

    def tombstone(self, video_id: str) -> dict:
        if self.consent is None or not self.consent.destination:
            return _ok(tombstoned=False, enabled=False)
        try:
            with self._exclusive(timeout=DEFAULT_BUDGET_S):
                self._record_event("soft_delete", video_id=video_id)
                return self._resync_locked(max_files=DEFAULT_MAX_FILES, budget_s=DEFAULT_BUDGET_S)
        except Exception as exc:
            log.exception("mirror tombstone failed")
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                details={"reason": type(exc).__name__},
            )

    def purge(self, video_id: str) -> dict:
        if self.consent is None or not self.consent.destination:
            return _ok(purged=True, enabled=False)
        try:
            with self._exclusive(timeout=DEFAULT_BUDGET_S):
                self._record_event("hard_purge", video_id=video_id)
                result = self._resync_locked(max_files=DEFAULT_MAX_FILES, budget_s=DEFAULT_BUDGET_S)
                return result
        except Exception as exc:
            log.exception("mirror purge failed")
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                details={"reason": type(exc).__name__},
            )

    def restore(self, video_id: str) -> dict:
        if not self._is_enabled():
            return _ok(restored=False, enabled=False)
        try:
            with self._exclusive(timeout=DEFAULT_BUDGET_S):
                self._record_event("restore", video_id=video_id)
                return self._resync_locked(max_files=DEFAULT_MAX_FILES, budget_s=DEFAULT_BUDGET_S)
        except Exception as exc:
            log.exception("mirror restore failed")
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                details={"reason": type(exc).__name__},
            )

    # ---- enablement / scope -------------------------------------------
    def _is_enabled(self) -> bool:
        return bool(self.enabled) and self.consent is not None

    def _in_scope_id(self, video_id: str, scope: str | None = None,
                     allowlist: tuple[str, ...] | None = None) -> bool:
        if scope is None:
            if self.consent is None:
                return False
            scope = self.consent.scope
            allowlist = self.consent.allowlist
        if scope == SCOPE_ALL:
            return True
        allowed = allowlist if allowlist is not None else ()
        return video_id in allowed

    def _destination_exists(self, dest: Path) -> bool:
        def probe() -> bool:
            try:
                return dest.exists() and dest.is_dir()
            except OSError:
                return False
        value, err = self._run_cancellable(probe, 2.0)
        return bool(value) and err is None

    # ---- index snapshots (never vault I/O) ----------------------------
    def _index_lock(self):
        lock = getattr(self.index, "_lock", None)
        return lock if lock is not None and hasattr(lock, "__enter__") else contextlib.nullcontext()

    def _sql(self, sql: str, params: tuple = ()) -> list[dict]:
        conn = getattr(self.index, "_conn", None)
        if conn is None:
            return []
        try:
            with self._index_lock():
                rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            log.debug("mirror index query failed", exc_info=True)
            return []

    def _live_items(self) -> list[dict]:
        rows = self._sql(
            "SELECT video_id, title, slug, channel, yoinked_at, deleted_at "
            "FROM yoinks WHERE deleted_at IS NULL ORDER BY yoinked_at DESC, video_id"
        )
        out = []
        for row in rows:
            vid = row.get("video_id")
            if isinstance(vid, str) and vid:
                out.append(row)
        return out

    def _in_scope_items(self, scope: str, allowlist: tuple[str, ...]) -> list[dict]:
        return [row for row in self._live_items() if self._in_scope_id(row["video_id"], scope, allowlist)]

    def _in_scope_shelves(self, scope: str, allowlist: tuple[str, ...],
                          items: list[dict]) -> list[dict]:
        allowed_ids = {row["video_id"] for row in items}
        try:
            tables = self._sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                "('library_meta','shelf_nodes','item_shelves','shelf_versions')"
            )
            names = {r.get("name") for r in tables}
            if len(names) < 4:
                return []
            meta = self._sql("SELECT projection_revision, active_version_id FROM library_meta WHERE singleton=1")
            if not meta or not meta[0].get("active_version_id"):
                return []
            version_id = meta[0]["active_version_id"]
            nodes = self._sql(
                "SELECT shelf_id, name FROM shelf_nodes WHERE version_id=? AND retired=0 ORDER BY shelf_id",
                (version_id,),
            )
            out = []
            for node in nodes:
                sid = node.get("shelf_id")
                if not isinstance(sid, str) or not sid:
                    continue
                members = self._sql(
                    "SELECT s.video_id AS video_id FROM item_shelves s "
                    "JOIN yoinks y ON y.video_id = s.video_id "
                    "WHERE s.shelf_id=? AND y.deleted_at IS NULL",
                    (sid,),
                )
                member_ids = [m["video_id"] for m in members if isinstance(m.get("video_id"), str)]
                if scope != SCOPE_ALL:
                    member_ids = [vid for vid in member_ids if vid in allowed_ids]
                    if not member_ids:
                        continue
                out.append({"shelf_id": sid, "name": node.get("name"), "members": member_ids})
            return out
        except Exception:
            return []

    def _in_scope_briefs(self, scope: str, allowlist: tuple[str, ...]) -> list[dict]:
        store = self.brief_store
        if store is None or not hasattr(store, "latest_valid"):
            return []
        date = _utc_date(self._wall())
        try:
            rec = store.latest_valid(date)
        except Exception:
            return []
        if not isinstance(rec, dict) or not rec.get("brief_hash"):
            return []
        bhash = rec["brief_hash"]
        bdate = rec.get("date") or date
        deps = []
        if hasattr(store, "validated_dependencies"):
            try:
                deps = store.validated_dependencies(bdate, bhash)
            except Exception:
                deps = []
        if not deps:
            deps = rec.get("dependencies") or rec.get("source_item_ids") or []
        if not deps:
            return []
        if scope != SCOPE_ALL:
            allowed = set(allowlist)
            if not all(dep in allowed for dep in deps):
                return []
        return [{"date": bdate, "brief_hash": bhash, "dependencies": deps}]

    def _item_snapshot(self, video_id: str) -> tuple[dict | None, list[dict]]:
        def run():
            with self._index_lock():
                row = self.index.get_yoink(video_id)
                if row is None:
                    return None, []
                clips = self.index.get_clips(video_id) if hasattr(self.index, "get_clips") else []
                return dict(row), [dict(c) for c in clips]
        try:
            return run()
        except Exception:
            log.debug("mirror item snapshot failed", exc_info=True)
            return None, []

    def _build_item_document(self, video_id: str) -> tuple[bytes | None, str | None, str | None]:
        item, clips = self._item_snapshot(video_id)
        if item is None:
            return None, None, None
        if item.get("deleted_at") is not None:
            return None, None, "deleted"
        try:
            card, _head = self.reader._build_card(item, clips)
            self.reader._assert_card_safe(card, item)
        except ResourceError:
            return None, None, "unsafe"
        except Exception:
            log.debug("mirror card build failed", exc_info=True)
            return None, None, "unsafe"
        source_link = safe_url(card.get("url"))
        generated_at = _utc_iso(self._wall())
        fields = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "kind": "item",
            "identity": video_id,
            "source_revision": card.get("source_revision") or "",
            "card_hash": card.get("card_hash") or "",
            "generated_at": generated_at,
            "notice": EDITS_NOTICE,
        }
        if source_link:
            fields["source_url"] = source_link
        body = library_cards.card_text(card)
        text = _frontmatter(fields) + "\n" + body + "\n\n" + EDITS_NOTICE + "\n"
        text = _break_injections(text)
        text = _cap_utf8(text)
        dep = str(card.get("card_hash") or card.get("source_revision") or "")
        return text.encode("utf-8"), dep, None

    def _build_tombstone_document(self, video_id: str) -> bytes:
        fields = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "kind": "item",
            "identity": video_id,
            "deleted": True,
            "deleted_at": _utc_iso(self._wall()),
            "notice": EDITS_NOTICE,
        }
        text = _frontmatter(fields) + "\n" + TOMBSTONE_BODY
        return _cap_utf8(_break_injections(text)).encode("utf-8")

    def _build_shelf_document(self, shelf_id: str, allowed: set[str] | None) -> tuple[bytes | None, str | None]:
        try:
            deadline = float(self._clock()) + DEFAULT_BUDGET_S
            op = _BudgetOp(self.reader, deadline)
            snapshot = self.reader._shelf_snapshot(op, shelf_id)
        except Exception:
            return None, None
        definition = snapshot.get("definition") or {}
        members = []
        for member in snapshot.get("members") or []:
            vid = member.get("video_id")
            if not isinstance(vid, str):
                continue
            if allowed is not None and vid not in allowed:
                continue
            members.append({
                "video_id": vid,
                "relpath": "../" + item_relpath(vid),
                "title": _break_injections(label(member.get("title") or vid)),
            })
        generated_at = _utc_iso(self._wall())
        fields = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "kind": "shelf",
            "identity": shelf_id,
            "taxonomy_revision": (snapshot.get("taxonomy") or {}).get("taxonomy_revision") or "",
            "projection_revision": (snapshot.get("taxonomy") or {}).get("projection_revision") or 0,
            "shelf_revision": snapshot.get("shelf_revision") or "",
            "generated_at": generated_at,
            "notice": EDITS_NOTICE,
        }
        name = _break_injections(label(definition.get("name") or shelf_id))
        lines = [f"# {name}", "", f"Members: {len(members)}", ""]
        for member in members[:20]:
            lines.append(f"- [{member['title']}]({member['relpath']})")
        if len(members) > 20:
            lines.append("")
            lines.append(f"Omissions: {len(members) - 20} additional members not listed.")
        lines.extend(["", EDITS_NOTICE, ""])
        text = _frontmatter(fields) + "\n" + "\n".join(lines)
        text = _cap_utf8(_break_injections(text))
        dep = str(snapshot.get("shelf_revision") or "")
        return text.encode("utf-8"), dep

    def _build_brief_document(self, date: str, brief_hash: str) -> tuple[bytes | None, list[str]]:
        store = self.brief_store
        if store is None:
            return None, []
        deps: list[str] = []
        if hasattr(store, "validated_dependencies"):
            try:
                deps = store.validated_dependencies(date, brief_hash)
            except Exception:
                deps = []
        document = None
        if hasattr(store, "read"):
            try:
                payload = store.read(date, brief_hash)
            except Exception:
                return None, []
            if isinstance(payload, dict):
                contents = payload.get("contents") or []
                if contents and isinstance(contents[0], dict) and "text" in contents[0]:
                    fenced = contents[0]["text"]
                    open_fence = "<untrusted_uoink_library_context>\n"
                    close_fence = "\n</untrusted_uoink_library_context>"
                    if open_fence in fenced and close_fence in fenced:
                        json_str = fenced.split(open_fence, 1)[1].split(close_fence, 1)[0]
                        try:
                            data = json.loads(json_str)
                            document = data.get("document") or data.get("text")
                            if not deps:
                                deps = [d["item_id"] for d in data.get("dependencies") or [] if isinstance(d, dict) and d.get("item_id")]
                        except Exception:
                            pass
                    if not document:
                        document = fenced
                if not document:
                    document = payload.get("document") or payload.get("text")
                if not deps:
                    deps = payload.get("source_item_ids") or payload.get("dependencies") or []
        if not deps:
            return None, []
        deps = [d for d in deps if isinstance(d, str)]
        allowed_ids = None
        if self.consent and self.consent.scope != SCOPE_ALL:
            allowed_ids = set(self.consent.allowlist)
        if allowed_ids is not None and not all(d in allowed_ids for d in deps):
            return None, []
        fields = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "kind": "brief",
            "identity": f"{date}/{brief_hash}",
            "date": date,
            "brief_hash": brief_hash,
            "generated_at": _utc_iso(self._wall()),
            "notice": EDITS_NOTICE,
        }
        text = _frontmatter(fields) + "\n" + _break_injections(str(document or "")) + "\n\n" + EDITS_NOTICE + "\n"
        text = _cap_utf8(text)
        return text.encode("utf-8"), deps

    def _build_library_index(self, completed: list[dict], omitted: int,
                             shelf_rows: list[dict], brief_rows: list[dict]) -> bytes:
        generated_at = _utc_iso(self._wall())
        fields = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "kind": "index",
            "generated_at": generated_at,
            "notice": EDITS_NOTICE,
        }
        lines = [
            "# Library",
            "",
            f"Items: {len(completed)}",
            f"Shelves: {len(shelf_rows)}",
            f"Briefs: {len(brief_rows)}",
            "",
            "## Recent",
            "",
        ]
        for row in completed[:20]:
            title = _break_injections(label(row.get("title") or row.get("identity") or ""))
            rel = row.get("relpath") or ""
            ident = _break_injections(label(row.get("identity") or "")).replace("`", "")
            lines.append(f"- [{title}]({rel}) `{ident}`")
        if omitted > 0 or len(completed) > 20:
            extra = omitted + max(0, len(completed) - 20)
            lines.append("")
            lines.append(f"Omissions: {extra} additional items not listed.")
        if shelf_rows:
            lines.extend(["", "## Shelves", ""])
            for row in shelf_rows[:10]:
                title = _break_injections(label(row.get("title") or row.get("identity") or ""))
                lines.append(f"- [{title}]({row.get('relpath')})")
        if brief_rows:
            lines.extend(["", "## Briefs", ""])
            for row in brief_rows[:5]:
                ident = _break_injections(label(row.get("identity") or ""))
                lines.append(f"- [{ident}]({row.get('relpath')})")
        lines.extend(["", EDITS_NOTICE, ""])
        text = _frontmatter(fields) + "\n" + "\n".join(lines)
        return _cap_utf8(_break_injections(text)).encode("utf-8")

    # ---- ledger --------------------------------------------------------
    def _ledger_path(self) -> Path:
        return self.ledger_dir / "ledger.json"

    def _empty_ledger(self) -> dict:
        dest = self.consent.destination if self.consent else ""
        marker = self.consent.marker if self.consent else ""
        return {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "destination": dest,
            "marker": marker,
            "exports_paused": False,
            "pause_reason": None,
            "entries": {},
            "purged": {},
        }

    def _load_ledger(self) -> dict:
        path = self._ledger_path()
        try:
            if not path.exists():
                return self._empty_ledger()
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self._empty_ledger()
            data.setdefault("entries", {})
            data.setdefault("purged", {})
            if not isinstance(data["entries"], dict):
                data["entries"] = {}
            if not isinstance(data["purged"], dict):
                data["purged"] = {}
            return data
        except (OSError, json.JSONDecodeError, UnicodeError, TypeError):
            return self._empty_ledger()

    def _save_ledger(self, ledger: dict) -> None:
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        path = self._ledger_path()
        payload = json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        self._atomic_local(path, payload)

    def _atomic_local(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + "." + secrets.token_hex(12) + ".tmp")
        try:
            with open(tmp, "xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
            tmp = None
        finally:
            if tmp is not None:
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _intent_dir(self) -> Path:
        return self.ledger_dir / "intents"

    def _intent_path(self, key: str) -> Path:
        name = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._intent_dir() / f"{name}.json"

    def _write_intent(self, key: str, payload: dict) -> None:
        path = self._intent_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_local(path, json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))

    def _clear_intent(self, key: str) -> None:
        try:
            self._intent_path(key).unlink()
        except OSError:
            pass

    def _load_intents(self) -> dict[str, dict]:
        folder = self._intent_dir()
        out: dict[str, dict] = {}
        try:
            if not folder.exists():
                return out
            for path in folder.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, UnicodeError):
                    continue
                if isinstance(data, dict) and isinstance(data.get("key"), str):
                    out[data["key"]] = data
        except OSError:
            return out
        return out

    def _ensure_entry(self, ledger: dict, key: str, *, kind: str, identity: str, relpath: str) -> dict:
        entries = ledger.setdefault("entries", {})
        entry = entries.get(key)
        if not isinstance(entry, dict):
            entry = {
                "kind": kind,
                "identity": identity,
                "relpath": relpath,
                "desired_generation": 0,
                "written_generation": 0,
                "dependency_hash": "",
                "last_file_hash": "",
                "status": "pending",
                "pending_action": "none",
            }
            entries[key] = entry
        entry.setdefault("relpath", relpath)
        entry.setdefault("kind", kind)
        entry.setdefault("identity", identity)
        return entry

    def _record_event(self, kind: str, *, video_id: str | None = None,
                      shelf_id: str | None = None, brief_hash: str | None = None) -> None:
        ledger = self._load_ledger()
        if self.consent:
            ledger["destination"] = self.consent.destination
            ledger["marker"] = self.consent.marker
        if kind in _PURGE_KINDS and video_id:
            self._record_purge(ledger, video_id)
        elif kind in _TOMBSTONE_KINDS and video_id:
            self._record_tombstone(ledger, video_id)
        elif kind == "restore" and video_id:
            self._record_restore(ledger, video_id)
        elif kind == "brief_published" and brief_hash:
            self._record_brief(ledger, brief_hash)
        else:
            if video_id:
                self._record_item_write(ledger, video_id, kind=kind)
            if shelf_id:
                self._record_shelf_write(ledger, shelf_id)
            if kind in ("apply", "undo", "pin") and video_id and not shelf_id:
                self._record_related_shelves(ledger, video_id)
            if kind in ("source_refresh", "apply", "undo") and not video_id:
                scope = self.consent.scope if self.consent else SCOPE_ALL
                allow = self.consent.allowlist if self.consent else ()
                for item in self._in_scope_items(scope, allow):
                    self._record_item_write(ledger, item["video_id"], kind=kind)
                for shelf in self._in_scope_shelves(scope, allow, self._in_scope_items(scope, allow)):
                    self._record_shelf_write(ledger, shelf["shelf_id"])
        self._save_ledger(ledger)

    def _record_item_write(self, ledger: dict, video_id: str, *, kind: str) -> None:
        if not self._in_scope_id(video_id):
            # Out of scope: if we previously owned a file, schedule cleanup.
            key = item_key(video_id)
            if key in ledger.get("entries", {}):
                self._record_purge(ledger, video_id)
            return
        key = item_key(video_id)
        purged = ledger.get("purged") or {}
        if key in purged and kind != "restore":
            item, _clips = self._item_snapshot(video_id)
            if item is None or item.get("deleted_at") is not None:
                return
            purged.pop(key, None)
        entry = self._ensure_entry(ledger, key, kind="item", identity=video_id, relpath=item_relpath(video_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "write"
        entry["status"] = "pending"
        self._bump_index(ledger)

    def _record_tombstone(self, ledger: dict, video_id: str) -> None:
        key = item_key(video_id)
        entry = self._ensure_entry(ledger, key, kind="item", identity=video_id, relpath=item_relpath(video_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "tombstone"
        entry["status"] = "deletion_pending"
        self._bump_index(ledger)
        self._invalidate_dependents(ledger, video_id)

    def _record_purge(self, ledger: dict, video_id: str) -> None:
        key = item_key(video_id)
        entry = self._ensure_entry(ledger, key, kind="item", identity=video_id, relpath=item_relpath(video_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "purge"
        entry["status"] = "deletion_pending"
        ledger.setdefault("purged", {})[key] = {
            "identity": video_id,
            "relpath": entry.get("relpath"),
            "generation": entry["desired_generation"],
            "purged_at": _utc_iso(self._wall()),
        }
        self._bump_index(ledger)
        self._invalidate_dependents(ledger, video_id)
        store = self.brief_store
        if store is not None and hasattr(store, "purge_dependents"):
            try:
                store.purge_dependents(video_id)
            except Exception:
                log.debug("brief_store.purge_dependents failed", exc_info=True)

    def _record_restore(self, ledger: dict, video_id: str) -> None:
        key = item_key(video_id)
        purged = ledger.get("purged") or {}
        if key in purged:
            item, _clips = self._item_snapshot(video_id)
            if item is None or item.get("deleted_at") is not None:
                return
            purged.pop(key, None)
        if not self._in_scope_id(video_id):
            return
        entry = self._ensure_entry(ledger, key, kind="item", identity=video_id, relpath=item_relpath(video_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "write"
        entry["status"] = "pending"
        self._bump_index(ledger)

    def _record_shelf_write(self, ledger: dict, shelf_id: str) -> None:
        key = shelf_key(shelf_id)
        entry = self._ensure_entry(ledger, key, kind="shelf", identity=shelf_id, relpath=shelf_relpath(shelf_id))
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "write"
        entry["status"] = "pending"
        self._bump_index(ledger)

    def _record_brief(self, ledger: dict, brief_hash: str) -> None:
        date = _utc_date(self._wall())
        rec = None
        store = self.brief_store
        if store is not None and hasattr(store, "latest_valid"):
            try:
                rec = store.latest_valid(date)
            except Exception:
                rec = None
        if isinstance(rec, dict) and rec.get("date"):
            date = rec["date"]
            brief_hash = rec.get("brief_hash") or brief_hash
        if not _DATE_RE.match(str(date)) or not _HEX64_RE.match(str(brief_hash)):
            return
        deps = []
        if store is not None and hasattr(store, "validated_dependencies"):
            try:
                deps = store.validated_dependencies(date, brief_hash)
            except Exception:
                deps = []
        if not deps and isinstance(rec, dict):
            deps = rec.get("dependencies") or rec.get("source_item_ids") or []
        key = brief_key(date, brief_hash)
        entry = self._ensure_entry(
            ledger, key, kind="brief", identity=f"{date}/{brief_hash}",
            relpath=brief_relpath(date, brief_hash),
        )
        if deps:
            entry["dependencies"] = [d for d in deps if isinstance(d, str)]
        scope = self.consent.scope if self.consent else SCOPE_ALL
        allow = self.consent.allowlist if self.consent else ()
        if scope != SCOPE_ALL and deps:
            allowed = set(allow)
            if not all(d in allowed for d in deps):
                entry["pending_action"] = "purge"
                entry["status"] = "deletion_pending"
                entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
                self._bump_index(ledger)
                return
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        entry["pending_action"] = "write"
        entry["status"] = "pending"
        entry["date"] = date
        entry["brief_hash"] = brief_hash
        self._bump_index(ledger)

    def _reconcile_desired_state(self, ledger: dict) -> None:
        if not self.consent:
            return
        scope = self.consent.scope
        allow = self.consent.allowlist
        entries = ledger.setdefault("entries", {})
        purged = ledger.get("purged") or {}

        live_items = self._live_items()
        live_by_id = {item["video_id"]: item for item in live_items}

        for vid, item in live_by_id.items():
            if not self._in_scope_id(vid, scope, allow):
                continue
            key = item_key(vid)
            if key in purged:
                continue
            entry = entries.get(key)
            if entry is None or int(entry.get("written_generation") or 0) == 0:
                self._record_item_write(ledger, vid, kind="source_refresh")

        for key, entry in list(entries.items()):
            kind = entry.get("kind")
            ident = entry.get("identity") or ""
            if kind == "item":
                if ident in live_by_id and not self._in_scope_id(ident, scope, allow):
                    if entry.get("pending_action") != "purge" and entry.get("status") != "purged":
                        self._record_purge(ledger, ident)
                elif ident not in live_by_id:
                    if entry.get("pending_action") not in ("purge", "tombstone") and entry.get("status") != "purged":
                        item_snap, _ = self._item_snapshot(ident)
                        if item_snap and item_snap.get("deleted_at") is not None:
                            self._record_tombstone(ledger, ident)
                        else:
                            self._record_purge(ledger, ident)
            elif kind == "brief":
                deps = entry.get("dependencies") or []
                if not deps and hasattr(self.brief_store, "validated_dependencies"):
                    date, bhash = ident.split("/", 1) if "/" in ident else (entry.get("date", ""), entry.get("brief_hash", ""))
                    try:
                        deps = self.brief_store.validated_dependencies(date, bhash)
                    except Exception:
                        deps = []
                if deps:
                    invalid = any(d not in live_by_id or not self._in_scope_id(d, scope, allow) for d in deps)
                    if invalid:
                        if entry.get("pending_action") != "purge":
                            entry["pending_action"] = "purge"
                            entry["status"] = "deletion_pending"
                            entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
                            self._bump_index(ledger)

    def _record_related_shelves(self, ledger: dict, video_id: str) -> None:
        rows = self._sql("SELECT DISTINCT shelf_id FROM item_shelves WHERE video_id=?", (video_id,))
        for row in rows:
            sid = row.get("shelf_id")
            if isinstance(sid, str) and sid:
                self._record_shelf_write(ledger, sid)

    def _invalidate_dependents(self, ledger: dict, video_id: str) -> None:
        self._record_related_shelves(ledger, video_id)
        for key, entry in list((ledger.get("entries") or {}).items()):
            if entry.get("kind") != "brief":
                continue
            deps = entry.get("dependencies") or []
            if video_id in deps:
                entry["pending_action"] = "purge"
                entry["status"] = "deletion_pending"
                entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1

    def _bump_index(self, ledger: dict) -> None:
        entry = self._ensure_entry(
            ledger, index_key(), kind="index", identity="Library.md", relpath=LIBRARY_INDEX_REL,
        )
        entry["desired_generation"] = int(entry.get("desired_generation") or 0) + 1
        if entry.get("pending_action") != "purge":
            entry["pending_action"] = "write"
            if entry.get("status") != "user_edit_conflict":
                entry["status"] = "pending"

    # ---- resync (under exclusive lock) --------------------------------
    def _resync_locked(self, *, max_files: int, budget_s: float) -> dict:
        dest = Path(self.consent.destination)
        if not self._destination_exists(dest):
            ledger = self._load_ledger()
            pending = sum(
                1 for e in ledger.get("entries", {}).values()
                if (e.get("pending_action") or "none") != "none"
            )
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                destination_state="unavailable",
                pending=pending,
                synced=0,
            )
        ledger = self._load_ledger()
        if self.consent:
            ledger["destination"] = self.consent.destination
            ledger["marker"] = self.consent.marker
        have_synced = any(int(e.get("written_generation") or 0) > 0 for e in ledger.get("entries", {}).values())

        marker_state = self._marker_state(dest)
        if marker_state == "mismatch" or (marker_state == "missing" and have_synced):
            reason = "volume_marker_mismatch" if marker_state == "mismatch" else "volume_marker_missing"
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                details={"reason": reason},
                synced=0,
            )
        uoink = dest / MIRROR_ROOT
        manifest_state = self._read_manifest_bytes(uoink)
        if manifest_state == "corrupt" or (manifest_state is None and have_synced):
            return _mirror_refusal(
                "invalid_request",
                "The mirror ownership manifest needs reconciliation.",
                details={"reason": "reconciliation", "what": "manifest"},
                reconciliation=True,
                synced=0,
            )
        self._reconcile_desired_state(ledger)
        paused = bool(ledger.get("exports_paused")) or not self.enabled
        plan = self._build_plan(ledger, manifest_state if isinstance(manifest_state, dict) else None, paused)
        # Persist intents before vault replacement.
        for op in plan["ops"]:
            if op["action"] in ("write", "tombstone") and op.get("content") is not None:
                self._write_intent(op["key"], {
                    "key": op["key"],
                    "relpath": op["relpath"],
                    "content_hash": _sha256_bytes(op["content"]),
                    "generation": op["generation"],
                    "action": op["action"],
                    "identity": op.get("identity"),
                    "kind": op.get("kind"),
                })
        recovered = self._load_intents()
        plan["intents"] = recovered
        plan["expected_marker"] = self.consent.marker if self.consent else ""
        plan["write_marker"] = marker_state == "missing" and not have_synced
        plan["have_synced"] = have_synced
        plan["max_files"] = max(0, int(max_files))
        plan["dest"] = str(dest)
        deadline = float(self._clock()) + max(0.0, float(budget_s))
        plan["deadline_mono"] = deadline
        cancel_event = threading.Event()
        plan["cancelled"] = cancel_event

        def work():
            return self._vault_work(plan)

        remaining = max(0.01, deadline - float(self._clock()))
        result, err = self._run_cancellable(work, remaining)
        if err == "timeout" or result is None:
            cancel_event.set()
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                synced=0,
            )
        if isinstance(err, Exception):
            cancel_event.set()
            log.exception("mirror vault worker failed")
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                synced=0,
                details={"reason": type(err).__name__},
            )
        return self._apply_receipts(ledger, result)

    def _marker_state(self, dest: Path) -> str:
        expected = (self.consent.marker if self.consent else "") or ""
        paths = [dest / VOLUME_MARKER_NAME, dest / MIRROR_ROOT / VOLUME_MARKER_NAME]

        def read_one(path: Path) -> str | None:
            try:
                if not path.exists() or not path.is_file():
                    return None
                if _is_reparse(path):
                    return None
                return path.read_text(encoding="utf-8").strip()
            except OSError:
                return None

        values = []
        for path in paths:
            value, err = self._run_cancellable(lambda p=path: read_one(p), 2.0)
            if err == "timeout":
                return "mismatch"
            if isinstance(value, str):
                values.append(value)
        if not values:
            return "missing"
        if expected and any(v != expected for v in values):
            return "mismatch"
        return "ok"

    def _read_manifest_bytes(self, uoink: Path):
        path = uoink / ".uoink-mirror" / "manifest.json"

        def load():
            if not path.exists():
                return None
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, json.JSONDecodeError, UnicodeError):
                return "corrupt"
            if not isinstance(data, dict):
                return "corrupt"
            ownership = data.get("ownership") or data.get("by_path")
            if ownership is None:
                data["ownership"] = {}
                return data
            if not isinstance(ownership, dict):
                return "corrupt"
            data["ownership"] = ownership
            return data

        value, err = self._run_cancellable(load, 2.0)
        if err == "timeout":
            return "corrupt"
        if err is not None:
            return "corrupt"
        return value

    def _build_plan(self, ledger: dict, manifest: dict | None, paused: bool) -> dict:
        ownership = (manifest or {}).get("ownership") or {}
        ops: list[dict] = []
        allowed_ids = None
        if self.consent and self.consent.scope != SCOPE_ALL:
            allowed_ids = set(self.consent.allowlist)
        # Deletions first.
        for key, entry in list(ledger.get("entries", {}).items()):
            action = entry.get("pending_action") or "none"
            if action not in ("purge", "tombstone"):
                continue
            rel = entry.get("relpath") or ""
            if not _rel_is_allowed(rel):
                continue
            owned = False
            rec = ownership.get(rel)
            if isinstance(rec, dict) and rec.get("key") == key:
                owned = True
            if entry.get("last_file_hash"):
                owned = True
            content = None
            if action == "tombstone" and entry.get("kind") == "item":
                content = self._build_tombstone_document(entry.get("identity") or "")
            ops.append({
                "action": action,
                "key": key,
                "kind": entry.get("kind"),
                "identity": entry.get("identity"),
                "relpath": rel,
                "generation": int(entry.get("desired_generation") or 0),
                "expected_hash": entry.get("last_file_hash") or (rec.get("file_hash") if isinstance(rec, dict) else ""),
                "owned": owned,
                "content": content,
            })
        if not paused:
            for key, entry in list(ledger.get("entries", {}).items()):
                action = entry.get("pending_action") or "none"
                if action != "write":
                    continue
                if entry.get("kind") == "index":
                    continue
                rel = entry.get("relpath") or ""
                if not _rel_is_allowed(rel):
                    continue
                purged = ledger.get("purged") or {}
                if key in purged and entry.get("kind") == "item":
                    continue
                content = None
                dep = entry.get("dependency_hash") or ""
                kind = entry.get("kind")
                if kind == "item":
                    vid = entry.get("identity") or ""
                    content, dep_new, reason = self._build_item_document(vid)
                    if reason == "deleted":
                        content = self._build_tombstone_document(vid)
                        ops.append({
                            "action": "tombstone",
                            "key": key,
                            "kind": kind,
                            "identity": vid,
                            "relpath": rel,
                            "generation": int(entry.get("desired_generation") or 0),
                            "expected_hash": entry.get("last_file_hash") or "",
                            "owned": bool(entry.get("last_file_hash") or ownership.get(rel)),
                            "content": content,
                        })
                        continue
                    if content is None:
                        continue
                    dep = dep_new or dep
                    entry["dependency_hash"] = dep
                elif kind == "shelf":
                    content, dep_new = self._build_shelf_document(entry.get("identity") or "", allowed_ids)
                    if content is None:
                        continue
                    dep = dep_new or dep
                    entry["dependency_hash"] = dep
                elif kind == "brief":
                    date = entry.get("date") or ""
                    bhash = entry.get("brief_hash") or ""
                    if "/" in str(entry.get("identity") or ""):
                        date, bhash = str(entry["identity"]).split("/", 1)
                    content, deps = self._build_brief_document(date, bhash)
                    if content is None:
                        continue
                    if allowed_ids is not None and deps and not all(d in allowed_ids for d in deps):
                        continue
                    entry["dependencies"] = deps
                else:
                    continue
                rec = ownership.get(rel)
                owned = isinstance(rec, dict) and rec.get("key") == key
                if entry.get("last_file_hash"):
                    owned = True
                ops.append({
                    "action": "write",
                    "key": key,
                    "kind": kind,
                    "identity": entry.get("identity"),
                    "relpath": rel,
                    "generation": int(entry.get("desired_generation") or 0),
                    "expected_hash": entry.get("last_file_hash") or (rec.get("file_hash") if isinstance(rec, dict) else ""),
                    "owned": owned,
                    "content": content,
                    "dependency_hash": dep,
                })
        catalog = []
        for key, entry in (ledger.get("entries") or {}).items():
            if entry.get("kind") != "item":
                continue
            if (entry.get("pending_action") or "none") in ("purge", "tombstone"):
                continue
            if key in (ledger.get("purged") or {}):
                continue
            title = ""
            item, _c = self._item_snapshot(entry.get("identity") or "")
            if item:
                title = item.get("title") or ""
            catalog.append({
                "key": key,
                "identity": entry.get("identity"),
                "relpath": entry.get("relpath"),
                "title": title,
            })
        shelf_catalog = []
        for key, entry in (ledger.get("entries") or {}).items():
            if entry.get("kind") == "shelf" and (entry.get("pending_action") or "none") != "purge":
                shelf_catalog.append({
                    "key": key,
                    "identity": entry.get("identity"),
                    "relpath": entry.get("relpath"),
                    "title": entry.get("identity"),
                })
        brief_catalog = []
        for key, entry in (ledger.get("entries") or {}).items():
            if entry.get("kind") == "brief" and (entry.get("pending_action") or "none") != "purge":
                brief_catalog.append({
                    "key": key,
                    "identity": entry.get("identity"),
                    "relpath": entry.get("relpath"),
                })
        index_entry = (ledger.get("entries") or {}).get(index_key())
        plan = {
            "ops": ops,
            "catalog": catalog,
            "shelf_catalog": shelf_catalog,
            "brief_catalog": brief_catalog,
            "index_expected_hash": (index_entry or {}).get("last_file_hash") or "",
            "index_generation": int((index_entry or {}).get("desired_generation") or 0),
            "rewrite_index": bool(index_entry and (index_entry.get("pending_action") == "write") and not paused),
        }
        self._save_ledger(ledger)
        return plan

    def _vault_work(self, plan: dict) -> dict:
        dest = Path(plan["dest"])
        try:
            if not dest.exists() or not dest.is_dir():
                return {"ok": False, "code": "destination_unavailable", "receipts": []}
        except OSError:
            return {"ok": False, "code": "destination_unavailable", "receipts": []}
        uoink = dest / MIRROR_ROOT
        try:
            if not uoink.exists():
                uoink.mkdir(parents=False)
        except OSError:
            return {"ok": False, "code": "destination_unavailable", "receipts": []}
        if not _contained(dest, uoink) or _escaping_reparse(dest, uoink):
            return {"ok": False, "code": "destination_unavailable", "receipts": []}
        if plan.get("write_marker"):
            marker_path = uoink / VOLUME_MARKER_NAME
            expected = plan.get("expected_marker") or ""
            if expected and not marker_path.exists():
                try:
                    marker_path.write_text(expected, encoding="utf-8")
                except OSError:
                    pass
        manifest_path = uoink / ".uoink-mirror" / "manifest.json"
        ownership, manifest_error = self._load_ownership(manifest_path)
        if manifest_error == "corrupt":
            return {"ok": False, "code": "reconciliation", "receipts": [], "synced": 0}
        receipts: list[dict] = []
        self._recover_intents(uoink, plan.get("intents") or {}, ownership, receipts)
        self._cleanup_owned_temps(uoink, ownership, plan)
        used = 0
        max_files = int(plan.get("max_files") or 0)
        deadline = float(plan.get("deadline_mono") or 0)

        def budget_left() -> bool:
            return float(self._clock()) <= deadline and used < max_files

        # Deletions / tombstones first.
        for op in plan["ops"]:
            if not budget_left():
                break
            if op["action"] not in ("purge", "tombstone"):
                continue
            receipt = self._apply_op(uoink, op, ownership, plan=plan)
            receipts.append(receipt)
            if receipt.get("counted"):
                used += 1
            if receipt.get("code") == "purge_blocked_user_edit":
                return {
                    "ok": False,
                    "code": "purge_blocked_user_edit",
                    "purge_blocked_user_edit": True,
                    "receipts": receipts,
                    "ownership": ownership,
                    "used": used,
                }
        for op in plan["ops"]:
            if not budget_left():
                break
            if op["action"] != "write":
                continue
            receipt = self._apply_op(uoink, op, ownership, plan=plan)
            receipts.append(receipt)
            if receipt.get("counted"):
                used += 1
        if plan.get("rewrite_index") and budget_left():
            live = []
            for row in plan.get("catalog") or []:
                rel = row.get("relpath") or ""
                rec = ownership.get(rel)
                path = uoink / rel
                if not isinstance(rec, dict):
                    continue
                if rec.get("key") != row.get("key"):
                    continue
                if rec.get("tombstone"):
                    continue
                try:
                    if path.exists():
                        live.append(row)
                except OSError:
                    continue
            shelves = []
            for row in plan.get("shelf_catalog") or []:
                rec = ownership.get(row.get("relpath") or "")
                if isinstance(rec, dict) and rec.get("key") == row.get("key"):
                    shelves.append(row)
            briefs = []
            for row in plan.get("brief_catalog") or []:
                rec = ownership.get(row.get("relpath") or "")
                if isinstance(rec, dict) and rec.get("key") == row.get("key"):
                    briefs.append(row)
            omitted = max(0, len(plan.get("catalog") or []) - len(live))
            content = self._build_library_index(live, omitted, shelves, briefs)
            index_op = {
                "action": "write",
                "key": index_key(),
                "kind": "index",
                "identity": "Library.md",
                "relpath": LIBRARY_INDEX_REL,
                "generation": int(plan.get("index_generation") or 0),
                "expected_hash": plan.get("index_expected_hash") or "",
                "owned": LIBRARY_INDEX_REL in ownership or bool(plan.get("index_expected_hash")),
                "content": content,
            }
            receipt = self._apply_op(uoink, index_op, ownership, plan=plan)
            receipts.append(receipt)
            if receipt.get("counted"):
                used += 1
        try:
            self._write_manifest(manifest_path, uoink, ownership)
        except OSError as exc:
            return {
                "ok": False,
                "code": "destination_unavailable",
                "manifest_failed": True,
                "receipts": receipts,
                "ownership": ownership,
                "used": used,
                "reason": type(exc).__name__,
            }
        return {"ok": True, "receipts": receipts, "ownership": ownership, "used": used}

    def _load_ownership(self, manifest_path: Path) -> tuple[dict, str | None]:
        if not manifest_path.exists():
            return {}, None
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return {}, "corrupt"
        if not isinstance(data, dict):
            return {}, "corrupt"
        ownership = data.get("ownership") or data.get("by_path") or {}
        if not isinstance(ownership, dict):
            return {}, "corrupt"
        return ownership, None

    def _write_manifest(self, manifest_path: Path, uoink: Path, ownership: dict) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "render_version": RENDER_VERSION,
            "ownership": ownership,
        }
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        self._atomic_vault(manifest_path, data, uoink, recheck=lambda: True)

    def _recover_intents(self, uoink: Path, intents: dict, ownership: dict, receipts: list) -> None:
        for key, intent in intents.items():
            rel = intent.get("relpath") or ""
            if not _rel_is_allowed(rel):
                continue
            path = uoink / rel
            try:
                if not path.exists():
                    continue
            except OSError:
                continue
            digest = _sha256_file(path)
            if digest and digest == intent.get("content_hash"):
                ownership[rel] = {
                    "key": key,
                    "kind": intent.get("kind"),
                    "identity": intent.get("identity"),
                    "file_hash": digest,
                    "generation": intent.get("generation"),
                    "tombstone": intent.get("action") == "tombstone",
                }
                receipts.append({
                    "key": key,
                    "action": "recover",
                    "ok": True,
                    "file_hash": digest,
                    "generation": intent.get("generation"),
                    "relpath": rel,
                    "counted": False,
                })

    def _cleanup_owned_temps(self, uoink: Path, ownership: dict, plan: dict) -> None:
        rels = set()
        for rel, rec in ownership.items():
            if isinstance(rel, str):
                rels.add(rel)
        for op in plan.get("ops") or []:
            if op.get("relpath"):
                rels.add(op["relpath"])
        for rel in rels:
            if not _rel_is_allowed(rel):
                continue
            dest = uoink / rel
            parent = dest.parent
            try:
                if not parent.exists():
                    continue
            except OSError:
                continue
            stem_tmp = dest.with_suffix(".tmp")
            try:
                if stem_tmp.exists() and stem_tmp.is_file() and not _is_reparse(stem_tmp):
                    if _contained(uoink, stem_tmp):
                        raw = stem_tmp.read_bytes()
                        if b"Interrupted" in raw:
                            stem_tmp.unlink()
            except OSError:
                pass
            prefix = dest.name + "."
            try:
                for child in parent.iterdir():
                    name = child.name
                    if not name.startswith(prefix) or not name.endswith(".tmp"):
                        continue
                    mid = name[len(prefix):-4]
                    if not _OUR_TMP_RE.match(mid):
                        continue
                    if _is_reparse(child):
                        continue
                    if _contained(uoink, child):
                        try:
                            child.unlink()
                        except OSError:
                            pass
            except OSError:
                pass

    def _apply_op(self, uoink: Path, op: dict, ownership: dict, plan: dict | None = None) -> dict:
        rel = op["relpath"]
        dest = uoink / rel
        key = op["key"]
        if not _rel_is_allowed(rel):
            return {"key": key, "ok": False, "code": "path_collision", "counted": False, "relpath": rel}
        if _path_too_long(dest):
            return {"key": key, "ok": False, "code": "destination_unavailable", "counted": False}
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {"key": key, "ok": False, "code": "destination_unavailable", "counted": False,
                    "reason": type(exc).__name__}
        if not _contained(uoink, dest.parent) or _escaping_reparse(uoink, dest.parent):
            return {"key": key, "ok": False, "code": "destination_unavailable", "counted": False}
        existing = dest.exists()
        current_hash = _sha256_file(dest) if existing else None
        rec = ownership.get(rel)
        owned = bool(op.get("owned"))
        if isinstance(rec, dict) and rec.get("key") == key:
            owned = True
        if isinstance(rec, dict) and rec.get("key") not in (None, key):
            return {"key": key, "ok": False, "code": "path_collision", "counted": False, "relpath": rel}
        if existing and not owned:
            return {
                "key": key, "ok": False, "code": "unmanaged_conflict",
                "unmanaged_conflict": True, "counted": False, "relpath": rel,
            }
        if existing and _hardlink_conflict(dest):
            return {"key": key, "ok": False, "code": "unmanaged_conflict", "counted": False, "relpath": rel}
        expected = op.get("expected_hash") or ""
        content = op.get("content")
        desired_hash = _sha256_bytes(bytes(content)) if isinstance(content, (bytes, bytearray)) else None
        if existing and desired_hash and current_hash == desired_hash and op["action"] in ("write", "tombstone"):
            ownership[rel] = {
                "key": key, "kind": op.get("kind"), "identity": op.get("identity"),
                "file_hash": current_hash, "generation": op.get("generation"),
                "tombstone": op["action"] == "tombstone",
            }
            return {"key": key, "ok": True, "action": op["action"], "counted": False,
                    "file_hash": current_hash, "generation": op.get("generation"), "relpath": rel,
                    "dependency_hash": op.get("dependency_hash") or ""}
        if existing and owned and expected and current_hash and current_hash != expected:
            code = "purge_blocked_user_edit" if op["action"] == "purge" else "user_edit_conflict"
            return {
                "key": key, "ok": False, "code": code,
                "user_edit_conflict": code == "user_edit_conflict",
                "purge_blocked_user_edit": code == "purge_blocked_user_edit",
                "counted": False, "relpath": rel,
            }

        if op["action"] == "purge":
            if existing:
                try:
                    dest.unlink()
                except OSError as exc:
                    return {"key": key, "ok": False, "code": "destination_unavailable",
                            "counted": False, "reason": type(exc).__name__}
            ownership.pop(rel, None)
            self._cleanup_one_temp(dest, uoink)
            return {"key": key, "ok": True, "action": "purge", "counted": True, "relpath": rel,
                    "generation": op.get("generation")}

        if not isinstance(content, (bytes, bytearray)):
            return {"key": key, "ok": False, "code": "internal_error", "counted": False}

        initial_dest_hash = current_hash

        def recheck() -> bool:
            if plan is not None:
                cancelled = plan.get("cancelled")
                if isinstance(cancelled, threading.Event) and cancelled.is_set():
                    return False
                deadline = float(plan.get("deadline_mono") or 0)
                if deadline and float(self._clock()) > deadline:
                    return False
            if not getattr(self, "_lock_acquired", False):
                return False

            # Re-read ledger generation; refuse to publish an older generation.
            try:
                data = json.loads(self._ledger_path().read_text(encoding="utf-8"))
                entry = (data.get("entries") or {}).get(key) or {}
                desired = int(entry.get("desired_generation") or 0)
                pending = entry.get("pending_action") or "none"
                if desired > int(op.get("generation") or 0):
                    return False
                if op["action"] == "write" and pending == "purge":
                    return False
            except Exception:
                pass

            # Authoritative deletion / scope / dependency check
            kind = op.get("kind")
            ident = op.get("identity") or ""
            if kind == "item":
                item_snap, _ = self._item_snapshot(ident)
                if item_snap is None or item_snap.get("deleted_at") is not None:
                    return False
                if not self._in_scope_id(ident):
                    return False
            elif kind == "brief":
                deps = op.get("dependencies") or []
                for d in deps:
                    item_snap, _ = self._item_snapshot(d)
                    if item_snap is None or item_snap.get("deleted_at") is not None:
                        return False
                    if not self._in_scope_id(d):
                        return False

            # Target bytes check immediately before replace
            now_exists = dest.exists()
            if now_exists:
                now_h = _sha256_file(dest)
                if initial_dest_hash is not None and now_h != initial_dest_hash:
                    return False
                if initial_dest_hash is None and now_h is not None:
                    return False
            elif initial_dest_hash is not None:
                return False

            return True

        try:
            digest = self._atomic_vault(dest, bytes(content), uoink, recheck=recheck)
        except _AbortedWrite:
            if dest.exists():
                now_h = _sha256_file(dest)
                if initial_dest_hash and now_h != initial_dest_hash:
                    return {
                        "key": key, "ok": False, "code": "user_edit_conflict",
                        "user_edit_conflict": True, "counted": False, "relpath": rel,
                    }
            return {"key": key, "ok": False, "code": "stale", "counted": False, "relpath": rel}
        except OSError as exc:
            return {"key": key, "ok": False, "code": "destination_unavailable",
                    "counted": False, "reason": type(exc).__name__, "relpath": rel}
        if digest is None:
            return {"key": key, "ok": False, "code": "destination_unavailable", "counted": False}
        on_disk = _sha256_file(dest)
        if on_disk != digest:
            return {"key": key, "ok": False, "code": "destination_unavailable", "counted": False}
        ownership[rel] = {
            "key": key,
            "kind": op.get("kind"),
            "identity": op.get("identity"),
            "file_hash": digest,
            "generation": op.get("generation"),
            "tombstone": op["action"] == "tombstone",
        }
        return {
            "key": key, "ok": True, "action": op["action"], "counted": True,
            "file_hash": digest, "generation": op.get("generation"), "relpath": rel,
            "dependency_hash": op.get("dependency_hash") or "",
        }

    def _cleanup_one_temp(self, dest: Path, uoink: Path) -> None:
        prefix = dest.name + "."
        try:
            parent = dest.parent
            if not parent.exists():
                return
            for child in parent.iterdir():
                name = child.name
                if not name.startswith(prefix) or not name.endswith(".tmp"):
                    continue
                mid = name[len(prefix):-4]
                if not _OUR_TMP_RE.match(mid):
                    continue
                if _is_reparse(child):
                    continue
                if _contained(uoink, child):
                    try:
                        child.unlink()
                    except OSError:
                        pass
        except OSError:
            pass

    def _atomic_vault(self, dest: Path, data: bytes, uoink: Path, *, recheck: Callable[[], bool]) -> str:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + "." + secrets.token_hex(12) + ".tmp")
        if not _contained(uoink, tmp) or _escaping_reparse(uoink, dest.parent):
            raise OSError("temp path escapes mirror root")
        if _path_too_long(tmp):
            raise OSError("temp path too long")
        try:
            with open(tmp, "xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if not recheck():
                raise _AbortedWrite()
            os.replace(tmp, dest)
            tmp = None
            return _sha256_bytes(data)
        finally:
            if tmp is not None:
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _apply_receipts(self, ledger: dict, result: dict) -> dict:
        if result.get("ok") is False and result.get("code") == "reconciliation":
            return _mirror_refusal(
                "invalid_request",
                "The mirror ownership manifest needs reconciliation.",
                details={"reason": "reconciliation"},
                reconciliation=True,
                synced=0,
            )
        if result.get("ok") is False and (result.get("code") == "destination_unavailable" or result.get("manifest_failed")):
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                synced=0,
                details={"reason": result.get("reason", "destination_unavailable")},
            )
        receipts = result.get("receipts") or []
        paused = bool(ledger.get("exports_paused"))
        synced = 0
        conflicts: list[dict] = []
        blocked = False
        for receipt in receipts:
            key = receipt.get("key")
            if not key:
                continue
            entry = (ledger.get("entries") or {}).get(key)
            if entry is None and receipt.get("ok"):
                continue
            if entry is None:
                continue
            code = receipt.get("code")
            if receipt.get("ok") and receipt.get("action") == "purge":
                entry["pending_action"] = "none"
                entry["status"] = "purged"
                entry["last_file_hash"] = ""
                entry["written_generation"] = int(receipt.get("generation") or entry.get("desired_generation") or 0)
                self._clear_intent(key)
                if receipt.get("counted"):
                    synced += 1
            elif receipt.get("ok"):
                entry["pending_action"] = "none"
                entry["status"] = "synced"
                if receipt.get("file_hash"):
                    entry["last_file_hash"] = receipt["file_hash"]
                entry["written_generation"] = int(receipt.get("generation") or entry.get("desired_generation") or 0)
                if receipt.get("dependency_hash"):
                    entry["dependency_hash"] = receipt["dependency_hash"]
                self._clear_intent(key)
                if receipt.get("counted"):
                    synced += 1
            elif code == "purge_blocked_user_edit":
                entry["status"] = "user_edit_conflict"
                ledger["exports_paused"] = True
                ledger["pause_reason"] = "purge_blocked_user_edit"
                paused = True
                blocked = True
                conflicts.append({"key": key, "code": code, "path": entry.get("relpath")})
            elif code in ("user_edit_conflict", "unmanaged_conflict", "path_collision"):
                entry["status"] = code
                conflicts.append({"key": key, "code": code, "path": entry.get("relpath")})
            elif code == "stale":
                entry["status"] = "stale"
        self._save_ledger(ledger)
        if result.get("ok") is False and result.get("code") == "reconciliation":
            return _mirror_refusal(
                "invalid_request",
                "The mirror ownership manifest needs reconciliation.",
                details={"reason": "reconciliation"},
                reconciliation=True,
                synced=0,
            )
        if result.get("code") == "destination_unavailable":
            return _mirror_refusal(
                "destination_unavailable",
                "The mirror destination is unavailable.",
                retryable=True,
                destination_unavailable=True,
                synced=0,
            )
        payload = _ok(
            synced=synced,
            conflicts=conflicts,
            exports_paused=paused,
            files=result.get("used") or 0,
        )
        if blocked:
            payload["ok"] = False
            payload["purge_blocked_user_edit"] = True
            payload["error"] = {
                "code": "purge_blocked_user_edit",
                "message": "A user-edited mirror file blocked hard purge.",
                "retryable": False,
                "details": {},
            }
        if any(c.get("code") == "user_edit_conflict" for c in conflicts):
            payload["user_edit_conflict"] = True
        if any(c.get("code") == "unmanaged_conflict" for c in conflicts):
            payload["unmanaged_conflict"] = True
        return payload

    def _scan_conflicts(self, dest: Path, ledger: dict) -> tuple[list, list, list]:
        unmanaged: list[dict] = []
        collisions: list[dict] = []
        user_edits: list[dict] = []
        uoink = dest / MIRROR_ROOT
        ownership = {}
        manifest_state = self._read_manifest_bytes(uoink)
        if isinstance(manifest_state, dict):
            ownership = manifest_state.get("ownership") or {}
        scope = self.consent.scope if self.consent else SCOPE_ALL
        allow = self.consent.allowlist if self.consent else ()
        for item in self._in_scope_items(scope, allow):
            rel = item_relpath(item["video_id"])
            path = uoink / rel
            try:
                exists = path.exists() and path.is_file()
            except OSError:
                continue
            if not exists:
                continue
            rec = ownership.get(rel)
            key = item_key(item["video_id"])
            if not isinstance(rec, dict):
                entry = (ledger.get("entries") or {}).get(key) or {}
                if entry.get("last_file_hash"):
                    digest = _sha256_file(path)
                    if digest and digest != entry.get("last_file_hash"):
                        user_edits.append({"path": rel, "identity": item["video_id"], "code": "user_edit_conflict"})
                    continue
                unmanaged.append({"path": rel, "identity": item["video_id"], "code": "unmanaged_conflict"})
            elif rec.get("key") not in (None, key):
                collisions.append({"path": rel, "identity": item["video_id"], "code": "path_collision"})
            else:
                entry = (ledger.get("entries") or {}).get(key) or {}
                expected = entry.get("last_file_hash") or rec.get("file_hash")
                digest = _sha256_file(path)
                if expected and digest and digest != expected:
                    user_edits.append({"path": rel, "identity": item["video_id"], "code": "user_edit_conflict"})
        return unmanaged, collisions, user_edits

    # ---- locking / worker ---------------------------------------------
    def _run_cancellable(self, fn: Callable[[], Any], budget_s: float) -> tuple[Any, Any]:
        box: dict[str, Any] = {}
        done = threading.Event()

        def runner() -> None:
            try:
                box["value"] = fn()
            except Exception as exc:
                box["error"] = exc
            finally:
                done.set()

        thread = threading.Thread(target=runner, name="uoink-mirror-io", daemon=True)
        thread.start()
        if not done.wait(timeout=max(0.001, float(budget_s))):
            return None, "timeout"
        if "error" in box:
            return None, box["error"]
        return box.get("value"), None

    def _lock_path(self) -> Path:
        if self.consent and self.consent.destination:
            canonical = os.path.normcase(os.path.realpath(str(self.consent.destination)))
            dest_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            lock_dir = Path(tempfile.gettempdir()) / "uoink-mirror-locks"
            lock_dir.mkdir(parents=True, exist_ok=True)
            return lock_dir / f"{dest_key}.lock"
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        return self.ledger_dir / ".writer.lock"

    @contextlib.contextmanager
    def _exclusive(self, timeout: float = 10.0) -> Iterator[None]:
        path = self._lock_path()
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            fd = os.open(path, os.O_RDWR)
        acquired = False
        try:
            try:
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
            except OSError:
                pass
            until = time.monotonic() + max(0.05, float(timeout))
            if os.name == "nt":
                import msvcrt
                while not acquired:
                    try:
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= until:
                            raise _LockTimeout()
                        time.sleep(0.01)
            else:
                import fcntl
                while not acquired:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= until:
                            raise _LockTimeout()
                        time.sleep(0.01)
            self._lock_acquired = True
            try:
                yield
            finally:
                self._lock_acquired = False
        finally:
            if acquired:
                try:
                    if os.name == "nt":
                        import msvcrt
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            try:
                os.close(fd)
            except OSError:
                pass


class _LockTimeout(Exception):
    pass


class _AbortedWrite(Exception):
    pass


class _BudgetOp:
    """Minimal operation object for reusing LibraryReader._shelf_snapshot."""

    def __init__(self, reader, deadline_at: float):
        self.reader = reader
        self.deadline_at = deadline_at
        self.cache: dict[str, Any] = {}

    def check(self) -> None:
        if float(self.reader._clock()) > self.deadline_at:
            raise ResourceError("deadline_exceeded", details={"deadline_s": getattr(self.reader, "deadline_s", 2.0)})


# Silence unused-import lint for the optional briefs module and shared contract pin.
_ = (_library_briefs, _RESOURCES_CONTRACT, LIMITS)

"""Uoink local library index -- SQLite + FTS5.

Replaces the O(n) full-disk-scan code paths (search_uoinks, list_recent, the
post-extraction `_all-uoinks-index.md` rebuild) with an incremental SQLite
index, and absorbs jobs.json / taxonomy.json into queryable tables.

The database lives under server.py's DATA_ROOT -- ``%LOCALAPPDATA%\\Uoink``
on Windows, ``~/Library/Application Support/Uoink`` on macOS,
``$XDG_DATA_HOME/Uoink`` (else ``~/.local/share/Uoink``) on Linux -- with
the file named ``index.db``. The cross-platform resolution lives in
``_platform.user_data_dir`` (Sprint 19.5 Stage 1). Both ``sqlite3`` and
the FTS5 extension ship in the Python standard library, so this module
adds no new dependency.

This module is self-contained: it owns the schema, the migration runner, and
all query helpers. server.py and uoink_mcp_tools.py call into ``Index`` and
never touch the database directly. Internal table/column names (``yoinks``,
``yoinks_fts``, ``yoinked_at`` ...) are kept frozen across the v2.1 rename --
they are a private storage contract, never user-visible, and renaming the
FTS5 virtual table on a populated library is not worth the data-loss risk.

Schema / migrations: see the ``migrations/`` directory. ``_run_migrations``
applies any pending ``NNNN_*.sql`` file in numeric order and is idempotent.
"""

from __future__ import annotations

import uoink_usage

import errno
import hashlib
import json
import logging
import os
import re
import sqlite3
import tempfile
import threading
import time
import unicodedata
import uuid
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("uoink.index")

_MIGRATIONS_DIR = Path(__file__).parent.resolve() / "migrations"

# Soft-deleted yoinks live in _yoink-trash/ for this many days before the
# scheduled purge hard-removes them.
_TRASH_RETENTION_DAYS = 30

# Rate-limit retry queue (Sprint 19 / C4). _PENDING_MAX_ATTEMPTS is the
# strike cap: after this many failures a pending row is marked terminal.
# The retry worker (server.py) decides backoff timing.
_PENDING_MAX_ATTEMPTS = 3
_PENDING_TERMINAL_STATES = ("succeeded", "failed", "cancelled")
# Sprint 19.6 / Fix 7: enqueue_pending opportunistically deletes the
# oldest terminal rows when the table grows past this cap, so a noisy
# client (or a creator who hits YouTube's 429 wall a lot) can't grow
# pending_yoinks without bound. Live (pending / running) rows are never
# evicted -- they're load-bearing for the retry worker.
_PENDING_TABLE_CAP = 1000

# Shared with the server's in-memory Activity history.
TERMINAL_JOB_RETENTION = 200

# SQLite stores INTEGER as signed 64-bit. A row id outside this range cannot
# exist, and binding one raises OverflowError -- so callers treat out-of-range
# ids as "not found" rather than letting the bind crash (G-90 bug hunt).
_SQLITE_INT_MIN = -(2 ** 63)
_SQLITE_INT_MAX = 2 ** 63 - 1


def _valid_rowid(value) -> bool:
    """True when value is an int SQLite can bind as a rowid."""
    try:
        return _SQLITE_INT_MIN <= int(value) <= _SQLITE_INT_MAX
    except (TypeError, ValueError):
        return False

# Columns of the `yoinks` table, in declaration order. video_id is the
# primary key and is handled separately in the upsert.
# v2.5: per-row data-shape version. v2.5+ writers set CURRENT_YOINK_SCHEMA via
# the row record; v2.1.x rows default to 1 (set by migration 0006). Lets v2.5
# readers tell "this row predates facets / engagement" without inspecting
# every nullable column. Distinct from the SQL migration version (which is
# tracked by the schema_version *table*).
CURRENT_YOINK_SCHEMA = 2

# Capture-time snapshots used by local research playbooks. No schema change:
# both new captures and the bounded legacy backfill store them in metadata_json.
ENGAGEMENT_METADATA_FIELDS = (
    "view_count", "like_count", "upload_date", "comment_count",
    "channel_follower_count",
)

_YOINK_COLUMNS = (
    "video_id", "slug", "channel", "title", "topic", "hook_type",
    "yoinked_at", "corpus_path", "sidecar_path", "health_score_json",
    "metadata_json",
    "schema_version",
    "source_type",
    # Phase 2 source-agnostic taxonomy (migration 0020).
    "platform", "author",
)

_JOB_COLUMNS = (
    "job_id", "kind", "status", "slug", "title", "error",
    "started_at", "updated_at", "metadata_json",
)

_TERMINAL_JOB_STATES = ("completed", "failed", "cancelled")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


class PublicationRetryQueue:
    """File-backed publication receipts, independent of a failing SQLite DB.

    Attempts and terminal outcomes are written once; only a complete,
    parseable outcome settles a receipt, so a partial one is retried and
    replaced. Pending work survives restart; an interrupted attempt is
    reported without running twice. A
    pending request holds the capture's sidecar (transcript included) and
    yt-dlp metadata only so its one retry can run. Settling reduces it to a
    tombstone of IDs, status and timestamps, so no user content outlives the
    retry or a later library deletion, and the same request can never run again.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    @staticmethod
    def _valid_id(receipt_id: str) -> None:
        if not re.fullmatch(r"[a-f0-9]{64}", receipt_id):
            raise ValueError("invalid publication receipt ID")

    @staticmethod
    def _temporary(path: Path):
        # Temporary copies are named "<destination>.<random>.tmp", so the
        # receipt that owns one can still remove it after a failed unlink.
        return tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                           prefix=f"{path.name}.", suffix=".tmp",
                                           delete=False)

    @staticmethod
    def _replace(path: Path, record: dict) -> None:
        # Atomic replacement: a settled receipt's tombstone, or a complete
        # outcome over a partial one that settled nothing.
        temporary = None
        try:
            with PublicationRetryQueue._temporary(path) as stream:
                temporary = Path(stream.name)
                json.dump(record, stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as exc:
                    log.warning("could not remove publication temp file %s: %s", temporary, exc)

    @staticmethod
    def _create(path: Path, record: dict, *, direct_fallback: bool = True) -> None:
        # Prefer publishing a complete, flushed file. Both paths create
        # exclusively, even if another writer claims the destination first.
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with PublicationRetryQueue._temporary(path) as stream:
                temporary = Path(stream.name)
                json.dump(record, stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                path.hardlink_to(temporary)
            except FileExistsError:
                raise
            except OSError:
                # exFAT/FAT32 and some network shares cannot hard-link.
                if not direct_fallback:
                    # Requests and outcomes are never written in place: an
                    # interrupted write must not leave a partial file. Move
                    # the complete copy atomically instead. A concurrent
                    # writer of one request writes identical bytes, and
                    # outcomes are written under the capture's ownership lock.
                    if path.exists():
                        raise FileExistsError(errno.EEXIST, "publication file exists", str(path))
                    os.replace(temporary, path)
                    temporary = None
                    return
                # Keep any partial file if writing fails: never replace or
                # delete a destination another writer may now be using.
                with path.open("x", encoding="utf-8") as stream:
                    json.dump(record, stream, ensure_ascii=False, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as exc:
                    log.warning("could not remove publication temp file %s: %s", temporary, exc)

    def enqueue(self, record: dict) -> str:
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
        receipt_id = hashlib.sha256(encoded).hexdigest()
        path = self.root / f"{receipt_id}.json"
        try:
            self._create(path, record, direct_fallback=False)
        except FileExistsError:
            existing = json.loads(path.read_text(encoding="utf-8"))
            # The ID is the request's digest: its tombstone means this same
            # request already settled, and it must not be stored or run again.
            settled = (isinstance(existing, dict) and existing.get("tombstone") is True
                       and existing.get("receipt_id") == receipt_id)
            if existing != record and not settled:
                raise ValueError("publication retry receipt changed")
        return receipt_id

    def _outcome(self, receipt_id: str) -> tuple[str, dict | None]:
        """``(state, outcome)``: ``absent``, ``complete``, ``incomplete``
        (a partial or invalid file, which settles nothing) or ``unreadable``
        (it exists but cannot be read now, e.g. a sharing violation)."""
        try:
            outcome = json.loads((self.root / f"{receipt_id}.result.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return "absent", None
        except ValueError:
            return "incomplete", None
        except OSError as exc:
            log.warning("could not read publication outcome %s: %s", receipt_id, exc)
            return "unreadable", None
        if not isinstance(outcome, dict) or outcome.get("status") not in ("succeeded", "failed"):
            return "incomplete", None
        return "complete", outcome

    def is_settled(self, receipt_id: str) -> bool:
        """Only a complete outcome settles a receipt. An unreadable one is
        left alone this pass rather than run or overwritten."""
        return self._outcome(receipt_id)[0] in ("complete", "unreadable")

    def next_pending(self) -> tuple[str, dict] | None:
        for path in sorted(self.root.glob("*.json")):
            if path.name.endswith((".result.json", ".attempt.json")):
                continue
            if self.is_settled(path.stem):
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(record, dict):
                    raise ValueError("invalid publication receipt")
            except (OSError, ValueError) as exc:
                log.warning("could not read publication retry %s: %s", path, exc)
                continue
            if record.get("tombstone"):
                continue  # Settled by another worker after the result check.
            return path.stem, record
        return None

    def claim(self, receipt_id: str) -> bool:
        self._valid_id(receipt_id)
        try:
            self._create(self.root / f"{receipt_id}.attempt.json", {"started_at": _now_iso()})
        except FileExistsError:
            return False
        return True

    def settle(self, receipt_id: str, *, error: str | None = None,
               code: str | None = None) -> None:
        self._valid_id(receipt_id)
        path = self.root / f"{receipt_id}.result.json"
        outcome = {"status": "failed" if error else "succeeded", "error": error,
                   "code": (code or "publication_failed") if error else None,
                   "finished_at": _now_iso()}
        try:
            self._create(path, outcome, direct_fallback=False)
        except FileExistsError:
            state, _ = self._outcome(receipt_id)
            if state == "unreadable":
                raise OSError(errno.EBUSY, "publication outcome cannot be read", str(path))
            if state != "complete":
                # A partial outcome (an interrupted write) settles nothing.
                self._replace(path, outcome)
            # Otherwise another worker already settled this receipt. Keep it.
        try:
            self._tombstone(receipt_id)
        except (OSError, ValueError) as exc:
            # The outcome is durable and the request can no longer run.
            # compact_settled() removes the retained content on next start.
            log.warning("could not compact settled publication retry %s: %s", receipt_id, exc)

    def _tombstone(self, receipt_id: str) -> bool:
        """Replace a settled request with IDs, status and timestamps only.
        Without a complete outcome the request is not settled: it is left
        for its retry, which settles and then compacts it."""
        self._valid_id(receipt_id)
        state, outcome = self._outcome(receipt_id)
        if state != "complete":
            return False
        path = self.root / f"{receipt_id}.json"
        attempt = self.root / f"{receipt_id}.attempt.json"
        changed = False
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            record = None
        except ValueError:
            record = {}  # Unreadable content still must not be retained.
        if record is not None and not (isinstance(record, dict) and record.get("tombstone")):
            if not isinstance(record, dict):
                record = {}
            try:
                started_at = json.loads(attempt.read_text(encoding="utf-8")).get("started_at")
            except (OSError, ValueError, AttributeError):
                started_at = None
            sidecar = record.get("sidecar") if isinstance(record.get("sidecar"), dict) else {}
            self._replace(path, {
                "tombstone": True, "receipt_id": receipt_id,
                "video_id": sidecar.get("video_id"), "metadata_id": record.get("metadata_id"),
                "pending_id": record.get("pending_id"), "status": outcome.get("status"),
                "error_code": outcome.get("code") or (
                    "publication_failed" if outcome.get("status") == "failed" else None),
                "created_at": record.get("created_at"), "started_at": started_at,
                "settled_at": outcome.get("finished_at"),
            })
            changed = True
        # The claim marker and temporary copies (a failed unlink can leave the
        # complete request behind) only served the unsettled request. Each is
        # retried independently; compact_settled() repeats this at next start.
        try:
            attempt.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("could not remove publication attempt marker %s: %s", attempt, exc)
        removed = self._remove_temporaries(f"{receipt_id}.*.tmp")
        return changed or removed > 0

    def _remove_temporaries(self, pattern: str, *, older_than: float | None = None) -> int:
        removed = 0
        for temporary in sorted(self.root.glob(pattern)):
            try:
                if older_than is not None and temporary.stat().st_mtime >= older_than:
                    continue
                temporary.unlink()
                removed += 1
            except FileNotFoundError:
                continue
            except OSError as exc:
                log.warning("could not remove publication temp file %s: %s", temporary, exc)
        return removed

    def compact_settled(self, *, abandoned_after: float = 3600.0) -> int:
        """Tombstone settled requests that still hold content and remove their
        temporary copies, e.g. after a crash or a sharing violation. A copy
        whose request was never stored (its enqueue failed) has nothing to
        settle it; it is removed once no writer can still own it. Copies of a
        pending request stay until it settles: the request holds that data."""
        compacted = 0
        for result in sorted(self.root.glob("*.result.json")):
            receipt_id = result.name[:-len(".result.json")]
            if not re.fullmatch(r"[a-f0-9]{64}", receipt_id):
                continue
            try:
                compacted += self._tombstone(receipt_id)
            except (OSError, ValueError) as exc:
                log.warning("could not compact settled publication retry %s: %s", receipt_id, exc)
        owners = {temporary.name.split(".", 1)[0] for temporary in self.root.glob("*.tmp")}
        for receipt_id in sorted(owners):
            if (re.fullmatch(r"[a-f0-9]{64}", receipt_id)
                    and not (self.root / f"{receipt_id}.json").exists()
                    and not (self.root / f"{receipt_id}.result.json").exists()):
                compacted += self._remove_temporaries(
                    f"{receipt_id}.*.tmp", older_than=time.time() - abandoned_after)
        return compacted


# --------------------------------------------------------------------------
# Migration framework
# --------------------------------------------------------------------------
def _discover_migrations() -> list[tuple[int, Path]]:
    """Return (version, path) for every migrations/NNNN_*.sql file, sorted by
    version ascending."""
    out: list[tuple[int, Path]] = []
    if not _MIGRATIONS_DIR.is_dir():
        return out
    for path in _MIGRATIONS_DIR.glob("*.sql"):
        stem = path.name.split("_", 1)[0]
        try:
            version = int(stem)
        except ValueError:
            log.warning("ignoring migration with non-numeric prefix: %s", path.name)
            continue
        out.append((version, path))
    out.sort(key=lambda item: item[0])
    return out


def latest_schema_version() -> int:
    """Return the newest migration version shipped with this checkout."""
    migrations = _discover_migrations()
    return migrations[-1][0] if migrations else 0


def _current_schema_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied schema version, or 0 on a fresh database."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


def schema_migration_status(path) -> dict:
    """Inspect an existing index without creating or migrating it.

    Doctor uses this read-only path so asking whether an upgrade is pending
    cannot silently perform the upgrade it is meant to report.
    """
    db_path = Path(path)
    latest = latest_schema_version()
    if not db_path.is_file():
        return {
            "database_exists": False,
            "current": 0,
            "latest": latest,
            "pending": False,
        }

    conn = None
    try:
        uri = f"{db_path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        current = _current_schema_version(conn)
        return {
            "database_exists": True,
            "current": current,
            "latest": latest,
            "pending": current < latest,
        }
    except sqlite3.Error as exc:
        return {
            "database_exists": True,
            "current": None,
            "latest": latest,
            "pending": True,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if conn is not None:
            conn.close()


# ``ALTER TABLE ... ADD COLUMN`` has no IF NOT EXISTS form, so the runner
# routes any ALTER statement in a migration through _safe_alter_add_column,
# which gates on PRAGMA table_xinfo, including generated columns. Matched
# against complete statements yielded by _iter_sql_statements (trailing ';' optional).
_ALTER_ADD_COLUMN_RE = re.compile(
    r"\s*ALTER\s+TABLE\s+(?P<table>\w+)\s+ADD\s+(?:COLUMN\s+)?"
    r"(?P<column>\w+)\s+(?P<type>.+?);?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _safe_alter_add_column(conn: sqlite3.Connection, table: str,
                            column: str, type_sql: str) -> None:
    """Idempotent ALTER TABLE ADD COLUMN. SQLite has no IF NOT EXISTS for
    ALTER syntax, so we gate the statement on PRAGMA table_xinfo first --
    a half-applied migration re-running on the next boot is a no-op."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_xinfo({table})")}
    if column in cols:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_sql.strip()}")


def _iter_sql_statements(sql: str):
    """Yield complete SQL statements from a script. Uses
    sqlite3.complete_statement so a statement that spans multiple lines is
    reassembled correctly; line-only ``--`` comments at statement boundaries
    are dropped so they don't accidentally glue onto the next statement."""
    buf = ""
    for line in sql.splitlines(keepends=True):
        if not buf.strip() and line.lstrip().startswith("--"):
            continue
        buf += line
        if sqlite3.complete_statement(buf):
            stmt = buf.strip()
            if stmt:
                yield stmt
            buf = ""
    tail = buf.strip()
    if tail:
        yield tail


def _run_migrations(conn: sqlite3.Connection) -> int:
    """Apply every pending migration in numeric order. Idempotent + atomic:
    each migration runs inside a single explicit transaction, with every
    CREATE statement using IF NOT EXISTS and every ALTER routed through
    _safe_alter_add_column, so a crash between the DDL and the
    schema_version bump is recoverable on the next boot (the re-run sees
    the existing schema and only adds the schema_version row).

    Returns the highest applied version after the pass."""
    current = _current_schema_version(conn)
    applied = current
    # Take manual control of transactions for the duration of the run;
    # restored in `finally` so the Index's existing methods keep using
    # Python's default deferred-isolation semantics afterward.
    saved_level = conn.isolation_level
    try:
        conn.isolation_level = None
        for version, path in _discover_migrations():
            if version <= current:
                continue
            log.info("applying index migration %04d (%s)", version, path.name)
            sql = path.read_text(encoding="utf-8")
            try:
                conn.execute("BEGIN IMMEDIATE")
                for stmt in _iter_sql_statements(sql):
                    m = _ALTER_ADD_COLUMN_RE.match(stmt)
                    if m:
                        _safe_alter_add_column(
                            conn, m.group("table"),
                            m.group("column"), m.group("type"))
                    else:
                        conn.execute(stmt)
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) "
                    "VALUES (?, ?)", (version, _now_iso()),
                )
                conn.execute("COMMIT")
            except sqlite3.Error:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                log.exception("index migration %04d failed", version)
                raise
            applied = version
    finally:
        conn.isolation_level = saved_level
    return applied


def _citation_label_columns(citation: dict) -> tuple:
    """Phase 6 (phase6-v1): ``(speaker, speaker_provenance_json)`` for one
    citation dict. Accepts either a pre-serialized ``speaker_provenance_json``
    string or a ``speaker_provenance`` object; a label with no provenance
    object is stored as NULL (never promoted to attributed evidence)."""
    speaker = citation.get("speaker")
    raw = citation.get("speaker_provenance_json")
    if raw is None and isinstance(citation.get("speaker_provenance"), dict):
        raw = json.dumps(citation["speaker_provenance"], ensure_ascii=False,
                         sort_keys=True, allow_nan=False)
    if not isinstance(speaker, str) or not isinstance(raw, str):
        return (None, None)
    return (speaker, raw)


def _backfill_clips_if_needed(conn: sqlite3.Connection, schema_version: int) -> None:
    """Build the derived clip index once for an upgraded library.

    Migration 0024 creates the tables but deliberately does not run Python
    from SQL. Existing installs can already have thousands of transcript
    citations, so the first open on schema 24 fills an empty clip table from
    those rows. Fresh databases and test fixtures pinned before 0024 skip the
    check entirely.
    """
    if schema_version < 24:
        return
    import clips as _clips
    clip_count = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
    if clip_count:
        # A schema-25 index may contain merged windows past the boundary or
        # unsplit long cues. Repair once; already bounded coarse excerpts do
        # not trigger another rebuild on the next open.
        legacy = conn.execute(
            'SELECT 1 FROM clips WHERE "end" - start > ? '
            'AND (cue_count > 1 OR length(text) > ?) LIMIT 1',
            (_clips.MAX_WINDOW_SECONDS, _clips.MAX_COARSE_CHARS)).fetchone()
        if not legacy:
            return
    citation_count = conn.execute(
        "SELECT COUNT(*) FROM citations WHERE kind='transcript_chunk'"
    ).fetchone()[0]
    if not citation_count:
        return

    report = _clips.rebuild_all_clips(conn)
    log.info(
        "clip upgrade backfill: %d transcript citations -> %d clips "
        "across %d/%d items in %.3fs",
        citation_count,
        report["clip_count"],
        report["items_with_clips"],
        report["items"],
        report["seconds"],
    )


# --------------------------------------------------------------------------
# FTS query sanitisation
# --------------------------------------------------------------------------
def _fts_terms(raw: str) -> list[str]:
    """Keep Unicode words intact while excluding the FTS operator grammar."""
    terms: list[str] = []
    word: list[str] = []
    for char in unicodedata.normalize("NFC", raw or ""):
        # Combining marks belong to the preceding word, including scripts
        # where NFC cannot compose them. Bare marks are not search terms.
        if char.isalnum() or char == "_" or (word and unicodedata.category(char).startswith("M")):
            word.append(char)
        elif word:
            terms.append("".join(word))
            word = []
    if word:
        terms.append("".join(word))
    return terms


def _like_escape(value: str) -> str:
    """Escape a substring for a SQL LIKE pattern (used with ESCAPE '\\'), so a
    user query containing % or _ filters literally instead of as wildcards."""
    return (str(value or "")
            .replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_"))


SEARCH_STOPWORDS = frozenset(
    "a an the and or of to for from with on in at by as is are was were be been "
    "being it its this that these those i me my we our you your they their how "
    "what which where when who why can could would should do does did have has "
    "had find show saved about using use through into some any all just most "
    "now only very also than then want need get please".split()
)


def _search_terms(raw: str, match: str = "forgiving") -> list[str]:
    if match not in ("forgiving", "strict"):
        raise ValueError("match must be forgiving or strict")
    terms = _fts_terms(raw)
    if match == "forgiving":
        return [t for t in terms if t.casefold() not in SEARCH_STOPWORDS] or terms
    return terms


def _fts_query(raw: str, match: str = "forgiving") -> str:
    """Turn an arbitrary user string into a safe FTS5 MATCH expression.

    FTS5 MATCH has its own grammar (quotes, NEAR, column filters, ``*``),
    and a raw user string can be a syntax error. We extract bare word
    tokens and quote each one. Forgiving search drops common English words
    and ORs the rest; strict search preserves the original AND expression.
    The last term always uses prefix matching."""
    terms = _search_terms(raw, match)
    if not terms:
        return ""
    quoted = [f'"{t}"' for t in terms]
    # Prefix-match the final term so "hook" matches "hooks".
    quoted[-1] = quoted[-1][:-1] + '"*'
    return (" " if match == "strict" else " OR ").join(quoted)


def _search_title_key(title: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFC", title or "").casefold()
                   if c.isalnum())


def _entity_keyword_score(name: str, query: str) -> int:
    terms = _search_terms(query)
    words = [word.casefold() for word in _fts_terms(name)]
    return sum(any(word.startswith(term.casefold()) if i == len(terms) - 1
                   else word == term.casefold() for word in words)
               for i, term in enumerate(terms))


# Private FTS markers distinguish matched body text from title-only snippets.
_MATCH_START = "\x01" + uuid.uuid4().hex + "\x01"
_MATCH_END = "\x02" + uuid.uuid4().hex + "\x02"


def _plain_snippet(text: str) -> str:
    return (text or "").replace(_MATCH_START, "").replace(_MATCH_END, "")


def _clip_fts_expression(expression: str, video_ids=None) -> str:
    """Match passage text, optionally intersecting indexed source keys first."""
    body = f"text : ({expression})"
    if video_ids is None:
        return body
    keys = " OR ".join('"' + str(vid).encode("utf-8").hex() + '"' for vid in video_ids)
    return f"({body}) AND search_source : ({keys})"


def _fts_hits(table: str, query: str, match: str, weights: str = "", *,
              video_ids=None, ranked=True, source_keys=False) -> tuple[str, list]:
    """Rank before pagination, using only FTS-tokenized words for coverage.

    BM25 alone can put short partial hits above long complete hits. Scale it
    into (-.001, 0], then give complete hits .001 and exact titles .002.
    This preserves BM25 order within each group and guarantees both guards.
    Exact titles also enter the candidate set when punctuation splits words
    differently (for example GPT-4 and GPT4). No persistent cache is needed.
    Table and weights are internal constants, never user SQL.
    """
    assert table in ("yoinks_fts", "clips_fts")
    expression = _fts_query(query, match)
    all_terms = _fts_query(" ".join(_search_terms(query)), "strict")
    if table == "clips_fts":
        scope = video_ids if source_keys else None
        expression = _clip_fts_expression(expression, scope)
        all_terms = _clip_fts_expression(all_terms, scope)
        weights = "1.0, 0.0" if source_keys else ""
    rank = f"bm25({table}{', ' + weights if weights else ''})" if ranked else "0.0"
    # Never extract snippets in the candidate set, including strict searches.
    # Collect page clip IDs with the ordinary video_id index. A single bounded
    # FTS cursor joins those IDs. Reopening MATCH for each clip repeats prefix
    # expansion and BM25 corpus statistics even with an FTS rowid constraint.
    params = []
    scoped = ""
    source = table
    restriction = ""
    if video_ids is not None:
        assert table == "clips_fts" and video_ids
        scoped = ("scoped_clips AS MATERIALIZED (SELECT clip_id FROM clips WHERE video_id IN ("
                  + ",".join("?" for _ in video_ids) + ")), ")
        source = "clips_fts"
        restriction = ("clips_fts.rowid >= (SELECT MIN(clip_id) FROM scoped_clips) AND "
                       "clips_fts.rowid <= (SELECT MAX(clip_id) FROM scoped_clips) AND "
                       "+clips_fts.rowid IN (SELECT clip_id FROM scoped_clips) AND ")
        params.extend(video_ids)
    identity = f", {table}.video_id" if table == "yoinks_fts" else ""
    base = (f"SELECT {table}.rowid{identity}, {rank} AS _score FROM {source} "
            f"WHERE {restriction}{table} MATCH ?")
    params.append(expression)
    if match == "strict":
        return f"WITH {scoped}search_hits AS MATERIALIZED ({base}) ", params
    if table == "clips_fts":
        # Exact-title priority is constant within each source, so it cannot
        # affect which of that source's clips supplies its passage.
        complete = "1" if expression == all_terms else "rowid IN (SELECT rowid FROM all_hits)"
        all_hits = ("" if expression == all_terms else
                    f"all_hits AS MATERIALIZED (SELECT {table}.rowid FROM {source} "
                    f"WHERE {restriction}{table} MATCH ?), ")
        title_sources = ("title_sources AS MATERIALIZED (SELECT video_id FROM yoinks "
                         "WHERE search_title_key(title)=? AND deleted_at IS NULL), " if video_ids is None else "")
        return (f"WITH {scoped}word_hits AS MATERIALIZED ({base}), {title_sources}{all_hits}"
                "search_hits AS (SELECT rowid, .001 * _score / (1.0 - _score) "
                f"- .001 * ({complete}) AS _score FROM word_hits) ",
                params + ([_search_title_key(query)] if video_ids is None else [])
                + ([] if expression == all_terms else [all_terms]))
    titles = ("SELECT f.rowid, f.video_id FROM (SELECT 1 FROM title_sources LIMIT 1) t "
              "CROSS JOIN yoinks_fts f WHERE f.video_id IN (SELECT video_id FROM title_sources)")
    sql = (
        f"WITH {scoped}word_hits AS MATERIALIZED ({base}), "
        "title_sources AS MATERIALIZED (SELECT video_id FROM yoinks "
        "WHERE search_title_key(title)=? AND deleted_at IS NULL), "
        f"title_hits AS MATERIALIZED ({titles}), "
        + ("all_hits AS (SELECT rowid FROM word_hits), " if all_terms == expression else
           f"all_hits AS MATERIALIZED (SELECT {table}.rowid FROM {source} WHERE {restriction}{table} MATCH ?), ") +
        "candidates AS (SELECT * FROM word_hits UNION ALL "
        "SELECT rowid, video_id, 0.0 FROM title_hits WHERE rowid NOT IN (SELECT rowid FROM word_hits)), "
        "search_hits AS (SELECT candidates.rowid, candidates.video_id, "
        ".001 * _score / (1.0 - _score) "
        + ("- .001 " if expression == all_terms else "- .001 * (rowid IN (SELECT rowid FROM all_hits)) ") +
        "- .002 * (rowid IN (SELECT rowid FROM title_hits)) AS _score FROM candidates) "
    )
    return sql, params + [_search_title_key(query)] + ([] if all_terms == expression else [all_terms])


def _fts_page(prefix: str, tail: str, order: str, *, offset=False, total=False, snippets=True) -> str:
    """Materialize the filtered page before asking FTS to extract snippets."""
    page = " LIMIT ? OFFSET ?" if offset else " LIMIT ?"
    outer_order = order.replace("h.", "p.").replace("y.", "p.")
    page_sql = (prefix.rstrip() + ", page_hits AS MATERIALIZED ("
            "SELECT y.*, h._score, h.rowid AS _fts_rowid "
            + (", COUNT(*) OVER () AS _total " if total else "")
            + tail + " ORDER BY " + order + page + ") ")
    if not snippets:
        return (page_sql + "SELECT p.*, f.content AS _content, '' AS _snippet, 1 AS _snippet_pending "
                "FROM page_hits p JOIN yoinks_fts f ON f.rowid=p._fts_rowid ORDER BY " + outer_order)
    return (page_sql.rstrip() + ", page_snippets AS MATERIALIZED ("
            f"SELECT yoinks_fts.rowid AS _fts_rowid, snippet(yoinks_fts, 6, '{_MATCH_START}', '{_MATCH_END}', '…', 12) AS _snippet "
            "FROM yoinks_fts WHERE yoinks_fts MATCH ? AND +rowid IN (SELECT _fts_rowid FROM page_hits)) "
            "SELECT p.*, f.content AS _content, COALESCE(s._snippet, '') AS _snippet "
            "FROM page_hits p JOIN yoinks_fts f ON f.rowid=p._fts_rowid "
            "LEFT JOIN page_snippets s ON s._fts_rowid=p._fts_rowid ORDER BY " + outer_order)


# --------------------------------------------------------------------------
# Entity graph (Sprint 16)
# --------------------------------------------------------------------------
# Allowed entity `type` values. Constrained here, not by a SQL CHECK: an
# unknown type from the extraction worker is folded to 'other', not rejected.
ENTITY_TYPES = ("person", "tool", "product", "topic", "company", "other")


def normalize_entity_name(name: str) -> str:
    """The matching key for the entities table: the name lowercased with all
    punctuation and whitespace removed. 'GPT-4o' -> 'gpt4o',
    'New York' -> 'newyork'. str.isalnum() is unicode-aware, so accented
    letters survive while spaces and punctuation drop out."""
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _entity_deep_link(video_id: str, seconds, *, platform: str | None = None,
                      metadata_json: str | None = None, source_url=None) -> str | None:
    """Return a source-aware timestamp link for an entity mention."""
    vid = (video_id or "").strip()
    if source_url is None and metadata_json:
        try:
            metadata = json.loads(metadata_json)
            source_url = metadata.get("url") if isinstance(metadata, dict) else None
        except (TypeError, json.JSONDecodeError):
            pass
    try:
        t = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        t = 0
    if platform and platform != "youtube":
        if isinstance(source_url, str) and source_url.startswith(("http://", "https://")):
            return f"{source_url.split('#', 1)[0]}#t={t}"
        return None
    return f"https://youtube.com/watch?v={vid}&t={t}s"


# --------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------
class Index:
    """Thread-safe connection wrapper around index.db. Writes share a
    re-entrant lock; search uses independent WAL readers. In-memory indexes
    retain the shared connection because they have no file to reopen.

    Open with ``Index.open(path)`` (runs migrations) or
    ``Index.open_or_recover(path)`` (also handles a corrupt file). The
    instance is usable as a context manager."""

    def __init__(self, conn: sqlite3.Connection, path: Path):
        from functools import lru_cache
        self._conn = conn
        conn.create_function("search_title_key", 1, lru_cache(maxsize=16384)(_search_title_key), deterministic=True)
        conn.create_function("entity_keyword_score", 2, lru_cache(maxsize=16384)(_entity_keyword_score), deterministic=True)
        self._path = path
        self._lock = threading.RLock()
        self._insert_count = 0
        self._local_search = None
        self._source_change_callback = None
        # Existing-only readers also support databases from before this index.
        try:
            self._clip_metadata_index = bool(conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='idx_clips_search_metadata' AND type='index'"
            ).fetchone())
            self._clip_source_keys = any(row[1] == "search_source" for row in conn.execute("PRAGMA table_info(clips_fts)"))
        except sqlite3.Error:
            self._clip_metadata_index = False  # surface storage errors at the read boundary
            self._clip_source_keys = False
        # Explicit write-transaction owner: (id(connection), thread ident).
        # Bound only by write_transaction(); BriefStore uses this instead of
        # guessing native sqlite3* pointers.
        self._write_txn_owner = None
        self._existing_read_only = False
        self._pending_cancel_events: dict[int, threading.Event] = {}
        self._search_local = threading.local()
        self._search_pool = []
        self._search_pool_lock = threading.Lock()
        self._closed = False
        self._search_in_memory = not conn.execute("PRAGMA database_list").fetchone()[2]

    # ---- lifecycle -------------------------------------------------------
    @classmethod
    def open_existing(cls, path) -> "Index":
        """Read existing storage without migrations, backfills or recovery."""
        path = Path(path).resolve()
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True,
                               check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            idx = cls(conn, path)
            idx._existing_read_only = True
            return idx
        except BaseException:
            conn.close()
            raise

    def initialize_for_write(self) -> None:
        """Promote an existing-only handle on an explicit ordinary operation.

        Readers share this Index lock, so no read can observe the connection
        swap. Keep the original connection usable if initialization fails.
        """
        from functools import lru_cache
        with self._lock:
            if not self._existing_read_only:
                return
            previous = self._conn
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
            try:
                conn.create_function("search_title_key", 1, lru_cache(maxsize=16384)(_search_title_key), deterministic=True)
                conn.create_function("entity_keyword_score", 2, lru_cache(maxsize=16384)(_entity_keyword_score), deterministic=True)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                version = _run_migrations(conn)
                _backfill_clips_if_needed(conn, version)
                self._conn = conn
                self._clip_metadata_index = True
                try:
                    from provenance import backfill_source_types
                    backfill_source_types(self)
                except Exception:
                    log.exception("source_type provenance backfill failed")
                has_meta = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='library_meta'").fetchone()
                if has_meta and ((self._path.parent / "library").is_dir() or conn.execute(
                        "SELECT last_operation_sequence FROM library_meta WHERE singleton=1").fetchone()[0]):
                    self.library_service()
            except BaseException:
                self._conn = previous
                if hasattr(self, "_library_work_service"):
                    del self._library_work_service
                conn.close()
                raise
            self._existing_read_only = False
            previous.close()

    @classmethod
    def open(cls, path) -> "Index":
        """Open (creating if needed) the index database and run migrations."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        # sqlite3.connect() is lazy -- a corrupt file only errors on the
        # first real operation below. If anything fails, close the
        # connection so the file handle is released and open_or_recover()
        # can rename the corrupt file aside.
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            schema_version = _run_migrations(conn)
            _backfill_clips_if_needed(conn, schema_version)
        except Exception:
            conn.close()
            raise
        idx = cls(conn, path)
        try:
            from provenance import backfill_source_types
            backfill_source_types(idx)
        except Exception:
            log.exception("source_type provenance backfill failed")
        # Records are local authority. Replay only an existing store; opening a
        # fresh index does not seed a taxonomy, work, pins, or enabled apply flag.
        has_library_meta = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='library_meta'").fetchone()
        if has_library_meta and ((path.parent / "library").is_dir() or conn.execute(
                "SELECT last_operation_sequence FROM library_meta WHERE singleton=1").fetchone()[0]):
            idx.library_service()
        return idx

    @classmethod
    def open_or_recover(cls, path) -> tuple["Index", bool]:
        """Like ``open``, but quarantine verified corruption and start fresh.

        The database and its WAL/SHM are moved into a unique sibling directory
        named ``index.db.corrupt-<ts>-<random>``. Operational errors and failed
        quarantine moves propagate without deleting any files.

        Returns ``(index, recovered)`` where ``recovered`` is True if the old
        file had to be quarantined -- the caller should then trigger a full
        backfill scan and surface ``index_recovering`` in /health."""
        path = Path(path)
        try:
            return cls.open(path), False
        except sqlite3.DatabaseError as exc:
            # Busy/locked, full disks, I/O failures and SQL errors are not
            # evidence of corruption. Prefer SQLite's code (including extended
            # codes); older Python versions may only supply the message.
            if isinstance(exc, sqlite3.OperationalError):
                raise
            code = getattr(exc, "sqlite_errorcode", None)
            if code is not None:
                corrupt = (code & 0xff) in (sqlite3.SQLITE_CORRUPT,
                                           sqlite3.SQLITE_NOTADB)
            else:
                corrupt = str(exc).lower() in (
                    "file is not a database", "database disk image is malformed")
            if not corrupt:
                raise

            # Stat explicitly: permission/I/O errors must not be mistaken for
            # missing files. Move the database last so it stays at its original
            # path if a sidecar cannot be quarantined.
            path.stat()
            sources = []
            for suffix in ("-wal", "-shm"):
                sibling = path.with_name(path.name + suffix)
                try:
                    sibling.stat()
                except FileNotFoundError:
                    continue
                sources.append(sibling)
            sources.append(path)
            quarantine = Path(tempfile.mkdtemp(
                prefix=f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}-",
                dir=path.parent))
            moved = []
            try:
                for source in sources:
                    saved = quarantine / source.name
                    source.rename(saved)
                    moved.append((source, saved))
            except OSError:
                # A hard link restores the original name without ever replacing
                # a file that appeared there meanwhile. Keep the saved copy even
                # if restoration fails; never delete on a quarantine failure.
                for source, saved in reversed(moved):
                    try:
                        source.hardlink_to(saved)
                    except OSError:
                        log.exception("could not restore %s; preserved at %s",
                                      source, saved)
                log.exception("index quarantine failed; files preserved at %s "
                              "and %s", path.parent, quarantine)
                raise
            log.error("corrupt index and sidecars quarantined at %s; "
                      "rebuilding from disk", quarantine)
            return cls.open(path), True

    def close(self) -> None:
        with self._lock:
            self._conn.close()
        with self._search_pool_lock:
            self._closed = True
            for db in self._search_pool:
                db.close()
            self._search_pool.clear()

    def schema_version(self) -> int:
        """Return the newest migration applied to this open index."""
        with self._lock:
            return _current_schema_version(self._conn)

    def __enter__(self) -> "Index":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @contextmanager
    def write_transaction(self):
        """Run one durable write unit without absorbing unrelated state.

        Helper modules share this connection. Refuse to enter while another
        caller has left a transaction open instead of accidentally committing
        that caller's work. The re-entrant Index lock keeps the boundary
        exclusive across worker threads. An open transaction here cannot be
        told apart from a caller up the stack that still owns it, so it is
        never rolled back on that caller's behalf; legacy writers roll back
        their own failures through _rollback_on_error().
        """
        with self._lock:
            if self._conn.in_transaction:
                raise RuntimeError(
                    "cannot start a write transaction while another "
                    "transaction is active"
                )
            owner = (id(self._conn), threading.get_ident())
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._write_txn_owner = owner
                yield self._conn
                self._conn.commit()
            except BaseException:
                with suppress(BaseException):
                    if self._conn.in_transaction:
                        self._conn.rollback()
                raise
            finally:
                if self._write_txn_owner == owner:
                    self._write_txn_owner = None

    @contextmanager
    def _rollback_on_error(self):
        """Roll back the implicit transaction if a legacy write raises.

        Legacy writers commit on success but used to leave a failed DML's
        implicit BEGIN open, which wedged every later write_transaction and
        read_snapshot on this shared connection (for example a backfill
        hitting UNIQUE(yoinks.slug)). Callers hold self._lock. Rollback is
        best effort so its own failure never hides the original exception.
        """
        try:
            yield
        except BaseException:
            with suppress(BaseException):
                if self._conn.in_transaction:
                    self._conn.rollback()
            raise

    @contextmanager
    def read_snapshot(self):
        """Hold Index lock and an explicit read transaction across reading."""
        with self._lock:
            if self._conn.in_transaction:
                raise RuntimeError(
                    "cannot start a read snapshot while another "
                    "transaction is active"
                )
            try:
                self._conn.execute("BEGIN DEFERRED")
                yield self._conn
            finally:
                with suppress(BaseException):
                    if self._conn.in_transaction:
                        self._conn.rollback()

    snapshot = read_snapshot
    read_transaction = read_snapshot

    @contextmanager
    def detached_snapshot(self):
        """Read committed WAL data without holding the capture connection lock."""
        conn = sqlite3.connect(self._path.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN DEFERRED")
            yield conn
        finally:
            conn.close()

    @contextmanager
    def search_read(self, *, deadline_at=None, clock=time.monotonic):
        """A request-local WAL reader. Ranking never owns the capture lock.

        Nested search helpers share the transaction and its deadline. Each
        thread owns its connection, including its SQLite progress handler.
        """
        from functools import lru_cache
        current = getattr(self._search_local, "db", None)
        if current is not None:
            yield current
            return
        if self._search_in_memory:
            acquired = (self._lock.acquire() if deadline_at is None else
                        self._lock.acquire(timeout=max(0, deadline_at - clock())))
            if not acquired:
                raise sqlite3.OperationalError("interrupted")
            self._search_local.db = self._conn
            try:
                if deadline_at is not None:
                    self._conn.set_progress_handler(lambda: int(clock() > deadline_at), 1000)
                yield self._conn
            finally:
                self._search_local.db = None
                if deadline_at is not None:
                    self._conn.set_progress_handler(None, 0)
                self._lock.release()
            return
        with self._search_pool_lock:
            db = self._search_pool.pop() if self._search_pool else None
        if db is None:
            db = sqlite3.connect(self._path.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
            db.row_factory = sqlite3.Row
            db.create_function("search_title_key", 1, lru_cache(maxsize=16384)(_search_title_key), deterministic=True)
            db.create_function("entity_keyword_score", 2, lru_cache(maxsize=16384)(_entity_keyword_score), deterministic=True)
        try:
            db.execute("BEGIN DEFERRED")
            if deadline_at is not None:
                remaining = max(0, deadline_at - clock())
                db.execute("PRAGMA busy_timeout=" + str(int(remaining * 1000)))
                db.set_progress_handler(lambda: int(clock() > deadline_at), 1000)
            self._search_local.db = db
            try:
                yield db
            finally:
                self._search_local.db = None
        finally:
            db.set_progress_handler(None, 0)
            db.rollback()
            with self._search_pool_lock:
                if not self._closed and len(self._search_pool) < 4:
                    self._search_pool.append(db)
                else:
                    db.close()

    @staticmethod
    def _search_error(error, query, surface):
        if getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT or "interrupted" in str(error).lower():
            log.warning("%s deadline exceeded", surface)
            raise error
        log.warning("%s rejected query %r", surface, query)

    def source_stamp(self):
        with self._lock:
            return (self._conn.total_changes, self._conn.execute("PRAGMA data_version").fetchone()[0])

    def library_service(self):
        """One service seam, shared by transports and corpus lifecycle hooks."""
        service = getattr(self, "_library_work_service", None)
        if service is None:
            from library_work import LibraryWorkService
            event_hook = None
            try:
                import server as _server
                event_hook = getattr(_server, "_mirror_event", None)
            except Exception:
                event_hook = None
            service = LibraryWorkService(self, event_hook=event_hook)
        return service

    def rebuild_library_state(self) -> dict:
        """Call after rebuilding corpus identities/clips to restore local pins.

        Missing/deleted item corrections remain authoritative orphan records.
        This does not rebuild or resurrect any source content.
        """
        from library_work import RequestContext
        return self.library_service().rebuild_library_state(
            RequestContext(authenticated=True, operator=True), {})

    def _invalidate_library_sources(self, video_ids) -> None:
        # Keep old installed trees importable until they package the service;
        # no service import is needed when no assignment run exists.
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='library_runs'").fetchone()
            if not exists or not self._conn.execute("SELECT 1 FROM library_runs LIMIT 1").fetchone():
                return
        from library_work import RequestContext
        result = self.library_service().invalidate_source_items(
            RequestContext(authenticated=True, operator=True), {"video_ids": list(video_ids)})
        if not result["ok"]:
            log.error("library source invalidation failed: %s", result["error"]["code"])

    # ---- yoinks ----------------------------------------------------------
    def set_local_search(self, engine) -> None:
        self._local_search = engine
        self._source_change_callback = engine.update_source

    def _notify_source_changed(self, video_id: str) -> None:
        if self._source_change_callback is not None:
            try:
                self._source_change_callback(video_id)
            except Exception:
                log.warning("Semantic search update failed; saved source is intact")

    @uoink_usage.search(query_arg="query")
    def search_mode(self, query: str, limit: int = 50, *, mode="auto", offset=0,
                    match="forgiving", filters=None, clips_only=False, video_id=None,
                    source_types=None, keyword=None, passages=True) -> dict:
        from uoink_core.search_service import search
        filters = dict(filters or {})
        if keyword is None:
            def keyword(count, start, override):
                if clips_only:
                    rows = self.search_clips(query, count + start, video_id=video_id,
                                             match=override or match, **filters)
                    return {"total": len(rows), "results": rows[start:start + count]}
                return self.search_yoinks_for_memory(q=query, limit=count, offset=start,
                                                     match=override or match, passages=False, **filters)
        return search(self, query, mode=mode, limit=limit, offset=offset, filters=filters,
                      source_types=source_types, source_id=video_id,
                      clips_only=clips_only, keyword=keyword, passages=passages, match=match)

    def search_embedding(self, query: str, limit: int = 10, **filters) -> dict:
        return self.search_mode(query, limit, mode="semantic", filters=filters)

    def search_hybrid(self, query: str, limit: int = 10, **filters) -> dict:
        return self.search_mode(query, limit, mode="hybrid", filters=filters)

    def upsert_yoink(self, record: dict, *, content: str = "") -> None:
        """Insert or update one yoink row, and refresh its FTS5 entry.

        ``record`` carries the ``yoinks`` columns. ``content`` is the corpus
        text indexed for full-text search (not stored in the yoinks table)."""
        video_id = record.get("video_id")
        if not video_id:
            raise ValueError("upsert_yoink: record requires a video_id")
        # v2.5: stamp the per-row data-shape version on every new write. If a
        # caller already set it (e.g., a backfill writing an older shape on
        # purpose) honour that; otherwise default to CURRENT_YOINK_SCHEMA so
        # the NOT NULL column always has a value.
        if record.get("schema_version") is None:
            record = {**record, "schema_version": CURRENT_YOINK_SCHEMA}
        if not str(record.get("source_type") or "").strip():
            from provenance import derive_source_type
            record = {
                **record,
                "source_type": derive_source_type(
                    platform=record.get("platform"),
                    metadata_json=record.get("metadata_json"),
                    sidecar_path=record.get("sidecar_path"),
                ),
            }
        values = [record.get(col) for col in _YOINK_COLUMNS]
        placeholders = ", ".join("?" * len(_YOINK_COLUMNS))
        update_set = ", ".join(
            f"{col}=excluded.{col}" for col in _YOINK_COLUMNS if col != "video_id"
        )
        with self._lock, self._rollback_on_error():
            self._conn.execute(
                f"INSERT INTO yoinks ({', '.join(_YOINK_COLUMNS)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT(video_id) DO UPDATE SET {update_set}",
                values,
            )
            # FTS5 has no UPSERT; delete-then-insert keeps it in sync.
            self._conn.execute("DELETE FROM yoinks_fts WHERE video_id=?", (video_id,))
            self._conn.execute(
                "INSERT INTO yoinks_fts "
                "(video_id, slug, channel, title, topic, hook_type, content) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (video_id, record.get("slug"), record.get("channel"),
                 record.get("title"), record.get("topic"),
                 record.get("hook_type"), content or ""),
            )
            # v2.5 P3 your-channel recognition. Imported lazily so the
            # index module stays standalone for callers that do not need
            # P3 (e.g., the backfill smoke tools).
            try:
                from channels import tag_if_self  # noqa: WPS433
                # Join this yoink write. A nested write_transaction would
                # raise, and the handler below would drop the tag.
                tag_if_self(self, video_id, record.get("channel"), self._conn)
            except Exception as e:  # pragma: no cover -- defensive
                # Recognition failure must not block a yoink write.
                import logging
                logging.getLogger("uoink.index").warning(
                    "self-channel recognition skipped: %s", e)
            self._conn.commit()
        self._invalidate_library_sources([video_id])
        self._notify_source_changed(video_id)

    def delete_yoink(self, video_id: str) -> None:
        """Delete a yoink and its citations (FK cascade) and FTS row."""
        with self._lock, self._rollback_on_error():
            self._conn.execute("DELETE FROM yoinks WHERE video_id=?", (video_id,))
            self._conn.execute("DELETE FROM yoinks_fts WHERE video_id=?", (video_id,))
            self._conn.commit()
        self._invalidate_library_sources([video_id])
        self._notify_source_changed(video_id)

    def get_yoink(self, video_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM yoinks WHERE video_id=?", (video_id,)
            ).fetchone()
        return dict(row) if row else None

    def has_yoink(self, video_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM yoinks WHERE video_id=?", (video_id,)
            ).fetchone()
        return row is not None

    def has_slug(self, slug: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM yoinks WHERE slug=?", (slug,)
            ).fetchone()
        return row is not None

    def get_by_slug(self, slug: str) -> dict | None:
        """Look up a live yoink by its folder slug (Sprint 19.6 / Fix 5).
        Excludes soft-deleted rows -- a slug parked in _yoink-trash/ must
        not resolve here, otherwise MCP tools would happily return content
        the user just deleted. Used by yoink_mcp_tools._find_yoink to skip
        the O(disk) rglob walk that pre-Sprint-19.6 MCP calls did."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM yoinks WHERE slug=? AND deleted_at IS NULL",
                (slug,),
            ).fetchone()
        return dict(row) if row else None

    def all_video_ids(self) -> set[str]:
        with self._lock:
            rows = self._conn.execute("SELECT video_id FROM yoinks").fetchall()
        return {r["video_id"] for r in rows}

    # bm25() column weights for yoinks_fts, in column order
    # (0:video_id 1:slug 2:channel 3:title 4:topic 5:hook_type 6:content).
    # Living library phase 1: a term in the title says far more about what
    # an item *is* than the same term buried once in a long transcript, so
    # title dominates (8), channel and topic are strong identity signals (3),
    # slug is a lossy copy of the title (2), hook_type and the body count
    # once (1), and video_id -- an opaque id -- never matches on purpose (0).
    _YOINKS_BM25_WEIGHTS = "0.0, 2.0, 3.0, 8.0, 3.0, 1.0, 1.0"

    def _ranked_source_page(self, db, query, limit, offset, where, params):
        """Exact forgiving page from native rank streams, before content reads.

        Complete hits precede partial hits. Consume score ties for stable ID
        ordering, but retain only limit + offset candidates. Exact-title queries
        use the general path, including titles absent from the FTS word hits.
        """
        if db.execute("SELECT 1 FROM yoinks y WHERE " + where
                      + " AND search_title_key(y.title)=? LIMIT 1",
                      [*params, _search_title_key(query)]).fetchone():
            return None
        expression = _fts_query(query, "forgiving")
        complete = _fts_query(" ".join(_search_terms(query)), "strict")
        count = limit + offset
        selected = []
        for tier, source_expression in enumerate(dict.fromkeys((complete, expression))):
            excluded = {row[1] for row in selected}
            needed = count - len(selected)
            best, boundary = {}, None
            cursor = db.execute(
                "SELECT yoinks_fts.rowid, yoinks_fts.video_id, yoinks_fts.rank "
                "FROM yoinks_fts CROSS JOIN yoinks y ON y.video_id=yoinks_fts.video_id "
                "WHERE yoinks_fts MATCH ? AND rank MATCH ? AND " + where
                + " ORDER BY yoinks_fts.rank",
                [source_expression, "bm25(" + self._YOINKS_BM25_WEIGHTS + ")", *params])
            cursor.row_factory = None
            try:
                for rowid, vid, raw in cursor:
                    if boundary is not None and raw > boundary:
                        break
                    if vid in excluded:
                        continue
                    best[vid] = (raw, vid, rowid)
                    if len(best) > needed:
                        del best[max(best, key=best.get)]
                    if len(best) == needed:
                        boundary = max(row[0] for row in best.values())
            finally:
                cursor.close()
            selected.extend((.001 * raw / (1 - raw) - .001 * (tier == 0), vid, rowid)
                            for raw, vid, rowid in best.values())
            if len(selected) == count:
                break
        page = sorted(selected)[offset:offset + limit]
        if not page:
            return []
        return db.execute(
            "WITH chosen(_score, video_id, _fts_rowid) AS (VALUES "
            + ",".join("(?,?,?)" for _ in page) + ") "
            "SELECT y.*, p._score, p._fts_rowid, f.content AS _content, '' AS _snippet, 1 AS _snippet_pending "
            "FROM chosen p JOIN yoinks y ON y.video_id=p.video_id "
            "JOIN yoinks_fts f ON f.rowid=p._fts_rowid ORDER BY p._score, p.video_id",
            [value for row in page for value in row]).fetchall()

    @uoink_usage.search
    def search(self, query: str, limit: int = 10, *,
               channel: str | None = None,
               hook_type: str | None = None,
               match: str = "forgiving", passages: bool = True) -> list[dict]:
        """Full-text search across indexed corpora. Returns yoink rows ranked
        by weighted FTS5 bm25 (best first; see _YOINKS_BM25_WEIGHTS),
        optionally filtered by channel/hook_type."""
        if not _fts_query(query, match):
            return []
        # snippet() column index 6 == the `content` column of yoinks_fts
        # (0:video_id 1:slug 2:channel 3:title 4:topic 5:hook_type 6:content).
        # Each result row carries `_snippet` (a match excerpt) and `_score`
        # (bm25; lower is a better match) alongside the yoinks columns.
        prefix, params = _fts_hits("yoinks_fts", query, match, self._YOINKS_BM25_WEIGHTS)
        native_params = []
        tail = ("FROM search_hits h CROSS JOIN yoinks y ON y.video_id = h.video_id "
               "WHERE y.deleted_at IS NULL ")
        if channel:
            tail += "AND y.channel = ? "
            params.append(channel)
            native_params.append(channel)
        if hook_type:
            tail += "AND y.hook_type = ? "
            params.append(hook_type)
            native_params.append(hook_type)
        params.append(max(1, int(limit)))
        sql = _fts_page(prefix, tail, "h._score, y.video_id", snippets=passages)
        if passages:
            params.append(_fts_query(query, match))
        with self.search_read() as db:
            try:
                rows = (self._ranked_source_page(db, query, max(1, int(limit)), 0,
                        tail.partition("WHERE ")[2], native_params) if match == "forgiving" else None)
                if rows is None:
                    rows = db.execute(sql, params).fetchall()
            except sqlite3.OperationalError as error:
                # Defensive: a MATCH expression FTS5 still rejects.
                self._search_error(error, query, "FTS search")
                return []
        rows = [dict(r) for r in rows]
        return self._search_passages(rows, query, match) if passages else rows

    def source_score_lower_bound(self, query: str) -> float:
        """A conservative best possible forgiving source score.

        FTS5 BM25 caps each phrase contribution at (k1 + 1) * IDF, with
        k1=1.2. Column weights change frequency, not that cap. A globally
        absent term contributes zero. Include coverage and exact-title guards
        so callers can skip a source scan only when every returned clip wins.
        """
        from math import log
        terms = _search_terms(query)
        if not terms:
            return float("inf")
        expressions = [f'"{term}"' + ("*" if i == len(terms) - 1 else "")
                       for i, term in enumerate(terms)]
        counts = ", ".join("(SELECT COUNT(*) FROM yoinks_fts WHERE yoinks_fts MATCH ?)" for _ in terms)
        with self.search_read() as db:
            values = db.execute(
                "SELECT EXISTS(SELECT 1 FROM yoinks WHERE deleted_at IS NULL AND search_title_key(title)=?), "
                # FTS5's normal docsize table has one row per document. Counting
                # its keys avoids loading the large inline FTS content records.
                "(SELECT COUNT(*) FROM yoinks_fts_docsize), "
                "EXISTS(SELECT 1 FROM yoinks_fts WHERE yoinks_fts MATCH ? LIMIT 1), " + counts,
                [_search_title_key(query), _fts_query(" ".join(terms), "strict"), *expressions]).fetchone()
        if values[0]:
            return float("-inf")  # exact titles must enter the candidate pool
        total = values[1]
        magnitude = 2.2 * sum(max(1e-6, log((total - n + .5) / (n + .5))) for n in values[3:] if n)
        return -.001 * magnitude / (1 + magnitude) - .001 * bool(values[2]) - 1e-12

    def _search_passages(self, rows: list[dict], query: str, match: str) -> list[dict]:
        """One indexed clip query for the returned page, never one per row."""
        if not rows:
            return []
        pending = [row for row in rows if "_content" in row]
        if not pending:
            return rows
        identities = list(dict.fromkeys(row["video_id"] for row in pending if "_matched_clip" not in row))
        deferred = [row for row in pending if row.get("_snippet_pending")]
        if deferred:
            ids = [row["_fts_rowid"] for row in deferred]
            with self.search_read() as db:
                snippets = db.execute(
                    f"SELECT yoinks_fts.rowid, snippet(yoinks_fts, 6, '{_MATCH_START}', '{_MATCH_END}', '…', 12) "
                    "FROM yoinks_fts WHERE yoinks_fts MATCH ? AND rowid>=? AND rowid<=? "
                    "AND +rowid IN (" + ",".join("?" for _ in ids) + ")",
                    [_fts_query(query, match), min(ids), max(ids), *ids]).fetchall()
            by_rowid = {row[0]: row[1] for row in snippets}
            for row in deferred:
                row["_snippet"] = by_rowid.get(row["_fts_rowid"], "")
                row.pop("_snippet_pending", None)
        clips = self.search_clips(query, len(identities), match=match,
                                  group_sources=True, _video_ids=identities, _snippets=False) if identities else []
        by_source = {clip["video_id"]: clip for clip in clips}
        return [self._search_passage({**row, "_matched_clip": row.get("_matched_clip", by_source.get(row["video_id"]))},
                                     query, match) if "_content" in row else row for row in rows]

    def _search_passage(self, row: dict, query: str, match: str) -> dict:
        """Attach a stored clip, or exact character span in indexed content.

        FTS snippets may contain ellipses, so they are discovery text. The
        optional passage is the verbatim text an agent can quote instead.
        """
        row.pop("_fts_rowid", None)
        content = row.pop("_content", "") or ""
        marked_snippet = row.get("_snippet") or ""
        row["_snippet"] = _plain_snippet(marked_snippet)
        # A source can match metadata or text outside its stored clips.
        # Never substitute the first clip or the opening of the content.
        clip = row.pop("_matched_clip", None)
        if clip:
            row["passage"] = {key: clip.get(key) for key in
                              ("video_id", "clip_id", "text", "start", "end", "timing")}
        elif content:
            for chunk in sorted(marked_snippet.split("…"), key=len, reverse=True):
                if _MATCH_START not in chunk or _MATCH_END not in chunk:
                    continue
                excerpt = _plain_snippet(chunk).strip()
                start = content.find(excerpt) if excerpt else -1
                if start < 0:
                    continue
                row["passage"] = {"video_id": row["video_id"], "text": excerpt,
                                  "char_start": start, "char_end": start + len(excerpt),
                                  "field": "content", "timing": "not_timed"}
                break
        row["passage_verified"] = bool(row.get("passage"))
        from uoink_core.search_service import citation_fields
        return citation_fields(row)

    # ---- clips (living library phase 1; see clips.py) --------------------
    def library_search_candidates(self, query, limit):
        """Share source ranking and verified clips for longer keyword queries."""
        if len(_search_terms(query)) < 8:
            return None
        pool_size = max(32, limit)
        with self.search_read() as db:
            sources = self.search(query, pool_size, passages=False)
            if len(sources) < pool_size or any(
                    _search_title_key(row["title"]) == _search_title_key(query) for row in sources):
                return None  # retain the sparse and exact-title clip paths
            clips = self.search_clips(query, pool_size, group_sources=True,
                _video_ids=[row["video_id"] for row in sources], _snippets=False)
            by_source = {row["video_id"]: row for row in clips}
            partial = [row["video_id"] for row in clips if row["_score"] > -.001]
            covered = self._clip_coverage_for_page(db, query, partial)
            for row in clips:
                if row["video_id"] in covered:
                    row["_score"] -= .001
            ranked = sorted(clips, key=lambda row: (row["_score"], row["video_id"]))[:limit]
            if len(ranked) < limit:
                ranked = self.search_clips(query, limit, group_sources=True, _snippets=False)
            for row in sources[:limit]:
                # The scoped query examined every source in this pool. A None
                # here also avoids repeating verification for a prose-only hit.
                row["_matched_clip"] = by_source.get(row["video_id"])
            return ranked, sources[:limit]

    def _ranked_clip_page(self, db, query, limit, match, grouped, channel):
        """Stream a bounded rank prefix before grouping or loading clip text.

        Complete passages form the first tier. If that tier cannot fill the
        page, inspect a prefix of partial sources for coverage across clips.
        Exact titles are handled separately so no prefix can hide them.
        Consume score ties to keep source and sequence ordering deterministic.
        """
        expression = _fts_query(query, match)
        complete = _fts_query(" ".join(_search_terms(query)), "strict") if match == "forgiving" else expression
        hint = " INDEXED BY idx_clips_search_metadata" if self._clip_metadata_index else ""

        def stream(expr, count, excluded=()):
            sql = ("SELECT c.clip_id, c.video_id, c.seq, clips_fts.rank AS raw_score "
                   "FROM clips_fts CROSS JOIN clips c" + hint + " ON c.clip_id=clips_fts.rowid "
                   "CROSS JOIN yoinks y ON y.video_id=c.video_id "
                   "WHERE clips_fts MATCH ? AND y.deleted_at IS NULL ")
            args = [_clip_fts_expression(expr)]
            if channel:
                sql += "AND y.channel=? "
                args.append(channel)
            sql += "ORDER BY clips_fts.rank"
            cursor = db.execute(sql, args)
            cursor.row_factory = None
            best, boundary = {}, None
            try:
                for clip_id, vid, seq, raw in cursor:
                    if boundary is not None and raw > boundary:
                        break
                    key = vid if grouped else clip_id
                    if key in excluded:
                        continue
                    row = (raw, vid, seq, clip_id)
                    if key not in best or row < best[key]:
                        best[key] = row
                    if len(best) > count:
                        del best[max(best, key=best.get)]
                    if len(best) == count:
                        boundary = max(value[0] for value in best.values())
            finally:
                cursor.close()
            return [{"clip_id": clip_id, "video_id": vid, "seq": seq, "raw": raw}
                    for raw, vid, seq, clip_id in sorted(best.values())]

        titles = []
        if match == "forgiving":
            title_ids = [r[0] for r in db.execute(
                "SELECT video_id FROM yoinks WHERE deleted_at IS NULL AND search_title_key(title)=?"
                + (" AND channel=?" if channel else ""),
                [_search_title_key(query)] + ([channel] if channel else []))]
            if title_ids:
                titles = self.search_clips(query, limit, match=match, group_sources=grouped,
                                           _video_ids=title_ids, _snippets=False)
                for row in titles:
                    row["_score"] -= .002
        key = "video_id" if grouped else "clip_id"
        if match == "forgiving":
            # Bound passage ranking by a source BM25 page. In a large library
            # most sources cover common terms; grouping their entire clip
            # posting lists before LIMIT makes the cost grow with transcripts.
            # Small/sparse source sets still use the clip stream below, which
            # also finds clips whose text is absent from the source FTS body.
            pool_size = max(32, limit)
            identities = []
            # FTS's native rank stream computes scores without loading every
            # source's inline content to read video_id. Only the bounded prefix
            # joins metadata. Complete and partial tiers preserve coverage;
            # exact titles were admitted separately above.
            for source_expression in dict.fromkeys((complete, expression)):
                candidate_sql = (
                    "SELECT yoinks_fts.video_id FROM yoinks_fts CROSS JOIN yoinks y "
                    "ON y.video_id=yoinks_fts.video_id WHERE yoinks_fts MATCH ? "
                    "AND rank MATCH ? AND y.deleted_at IS NULL ")
                args = [source_expression, "bm25(" + self._YOINKS_BM25_WEIGHTS + ")"]
                if channel:
                    candidate_sql += "AND y.channel=? "
                    args.append(channel)
                candidate_sql += "ORDER BY yoinks_fts.rank LIMIT ?"
                for row in db.execute(candidate_sql, [*args, pool_size + len(identities)]):
                    if row[0] not in identities:
                        identities.append(row[0])
                    if len(identities) == pool_size:
                        break
                if len(identities) == pool_size:
                    break
            if len(identities) == pool_size:
                candidates = self.search_clips(query, pool_size if grouped else limit,
                    match=match, group_sources=grouped, _video_ids=identities, _snippets=False)
                if len(candidates) >= limit:
                    if grouped:
                        partial_ids = [row["video_id"] for row in candidates if row["_score"] > -.001]
                        covered = self._clip_coverage_for_page(db, query, partial_ids)
                        for row in candidates:
                            if row["video_id"] in covered:
                                row["_score"] -= .001
                    chosen = {row[key]: row for row in candidates}
                    chosen.update({row[key]: row for row in titles})
                    return sorted(chosen.values(), key=lambda row: (row["_score"], row["video_id"]))[:limit]
        excluded = {r[key] for r in titles}
        rows = stream(complete, limit, excluded)
        for row in rows:
            raw = row.pop("raw")
            row["_score"] = .001 * raw / (1 - raw) - .001 if match == "forgiving" else raw
        if match == "forgiving" and complete != expression and len(rows) + len(titles) < limit:
            excluded.update(r[key] for r in rows)
            terms = _search_terms(query)
            expressions = ['"' + term + '"' + ("*" if i == len(terms) - 1 else "")
                           for i, term in enumerate(terms)]
            present = [bool(db.execute("SELECT 1 FROM clips_fts WHERE clips_fts MATCH ? LIMIT 1", (_clip_fts_expression(expr),)).fetchone())
                       for expr in expressions]
            expression = " OR ".join(expr for expr, found in zip(expressions, present) if found)
            if not expression:
                return sorted(titles + rows, key=lambda row: (row["_score"], row["video_id"]))[:limit]
            partial = stream(expression, max(64, limit * 4) if grouped else limit, excluded)
            covered = (self._clip_coverage_for_page(db, query, list(dict.fromkeys(r["video_id"] for r in partial)))
                       if grouped and partial and all(present) else set())
            for row in partial:
                raw = row.pop("raw")
                row["_score"] = .001 * raw / (1 - raw) - .001 * (row["video_id"] in covered)
            rows.extend(partial)
        rows.extend(titles)
        return sorted(rows, key=lambda row: (row["_score"], row["video_id"], row.get("seq", 0), row["clip_id"]))[:limit]

    def _clip_coverage_for_page(self, db, query, identities):
        """Coverage only for bounded candidate sources with no complete clip."""
        if not identities:
            return set()
        terms = _search_terms(query)
        expressions = ['"' + term + '"' + ("*" if i == len(terms) - 1 else "") for i, term in enumerate(terms)]
        probes = []
        for expression in reversed(expressions):
            # A bounded posting count finds selective terms without scanning a
            # common term's whole list. Eliminate sources with rare terms first.
            count = db.execute("SELECT COUNT(*) FROM (SELECT 1 FROM clips_fts "
                               "WHERE clips_fts MATCH ? LIMIT 1024)", (_clip_fts_expression(expression),)).fetchone()[0]
            if not count:
                return set()
            probes.append((count, expression))
        covered = set(identities)
        for _, expression in sorted(probes, key=lambda value: value[0]):
            # Materialize page clip IDs first. One FTS cursor intersects those
            # IDs before loading source identities. Per-clip MATCH probes would
            # repeatedly expand the final prefix, even without BM25.
            selected = sorted(covered)
            covered = {r[0] for r in db.execute(
                "WITH scoped AS MATERIALIZED (SELECT clip_id FROM clips WHERE video_id IN ("
                + ",".join("?" for _ in selected) + ")), hits AS MATERIALIZED ("
                "SELECT rowid FROM clips_fts WHERE clips_fts MATCH ? "
                "AND rowid>=(SELECT MIN(clip_id) FROM scoped) AND rowid<=(SELECT MAX(clip_id) FROM scoped) "
                "AND +rowid IN (SELECT clip_id FROM scoped)) "
                "SELECT DISTINCT video_id FROM clips WHERE clip_id IN (SELECT rowid FROM hits)",
                [*selected, _clip_fts_expression(expression, selected if self._clip_source_keys else None)])}
            if not covered:
                break
        return covered

    @uoink_usage.search
    def search_clips(self, query: str, limit: int = 20, *,
                     video_id: str | None = None,
                     channel: str | None = None,
                     match: str = "forgiving", group_sources: bool = False,
                     _video_ids=None, _snippets=True) -> list[dict]:
        """Rank clip IDs first, then load only the returned page's passages."""
        if not _fts_query(query, match):
            return []
        limit = max(1, int(limit))
        identities = [video_id] if video_id else _video_ids
        with self.search_read() as db:
            try:
                if identities is None:
                    page = self._ranked_clip_page(db, query, limit, match, group_sources, channel)
                    if not page:
                        return []
                    page_sql = " UNION ALL ".join("SELECT ? AS clip_id, ? AS video_id, ? AS _score" for _ in page)
                    params = [v for r in page for v in (r["clip_id"], r["video_id"], r["_score"])]
                else:
                    if not identities:
                        return []
                    prefix, params = _fts_hits("clips_fts", query, match, video_ids=identities,
                                              source_keys=self._clip_source_keys)
                    hint = " INDEXED BY idx_clips_search_metadata" if self._clip_metadata_index else ""
                    candidates = (prefix + "SELECT c.clip_id, c.video_id, c.seq, h._score FROM search_hits h "
                                  "JOIN clips c" + hint + " ON c.clip_id=h.rowid "
                                  "JOIN yoinks y ON y.video_id=c.video_id WHERE y.deleted_at IS NULL ")
                    if channel:
                        candidates += "AND y.channel=? "
                        params.append(channel)
                    if group_sources:
                        page_sql = ("WITH scored_clips AS MATERIALIZED (" + candidates + "), "
                                    "best AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY video_id ORDER BY _score, seq, clip_id) AS n "
                                    "FROM scored_clips) SELECT clip_id, video_id, _score FROM best WHERE n=1 "
                                    "ORDER BY _score, video_id LIMIT ?")
                    else:
                        page_sql = candidates + "ORDER BY h._score, c.video_id, c.seq LIMIT ?"
                    params.append(limit)
                sql = ("WITH clip_page AS MATERIALIZED (" + page_sql + ") "
                       "SELECT p.clip_id, p.video_id, p._score, y.slug, y.title, y.channel, "
                       "c.start, c.end, c.text, c.source_deep_link, '' AS _snippet "
                       "FROM clip_page p JOIN clips c ON c.clip_id=p.clip_id JOIN yoinks y ON y.video_id=p.video_id "
                       "ORDER BY p._score, p.video_id, c.seq")
                rows = [dict(row) for row in db.execute(sql, params)]
                if _snippets and rows:
                    ids = [row["clip_id"] for row in rows]
                    snippets = db.execute(
                        f"SELECT clips_fts.rowid, snippet(clips_fts, 0, '{_MATCH_START}', '{_MATCH_END}', '…', 16) "
                        "FROM clips_fts WHERE clips_fts MATCH ? AND rowid>=? AND rowid<=? "
                        "AND +rowid IN (" + ",".join("?" for _ in ids) + ")",
                        [_clip_fts_expression(_fts_query(query, match),
                            list(dict.fromkeys(row["video_id"] for row in rows)) if self._clip_source_keys else None),
                         min(ids), max(ids), *ids]).fetchall()
                    by_id = {row[0]: row[1] for row in snippets}
                    for row in rows:
                        row["_snippet"] = by_id.get(row["clip_id"], "")
            except sqlite3.OperationalError as error:
                self._search_error(error, query, "clips FTS search")
                return []
        from clips import timing_kind
        from uoink_core.search_service import citation_fields
        return [citation_fields({**r, "_snippet": _plain_snippet(r["_snippet"]),
                                 "passage_verified": True, "timing": timing_kind(r)}) for r in rows]

    def get_clips(self, video_id: str) -> list[dict]:
        """Every clip for one item, in timeline order."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT clip_id, video_id, seq, start, \"end\", text, speaker, "
                "source_deep_link, cue_count FROM clips WHERE video_id=? "
                "ORDER BY seq", (video_id,)).fetchall()
        from clips import timing_kind
        return [{**dict(r), "timing": timing_kind(dict(r))} for r in rows]

    def rebuild_clips(self) -> dict:
        """Re-derive every item's clips from its citations (clips.py)."""
        import clips as _clips  # noqa: WPS433 -- keeps index importable alone
        with self._lock:
            result = _clips.rebuild_all_clips(self._conn)
        identities = self.all_video_ids()
        self._invalidate_library_sources(identities)
        for identity in identities:
            self._notify_source_changed(identity)
        return result

    def clip_coverage(self) -> dict:
        """``{items_with_clips, items_without_clips, clip_count}`` over the
        live (non-deleted) library."""
        import clips as _clips  # noqa: WPS433
        with self._lock:
            return _clips.clip_coverage(self._conn)

    def count_corpus(self) -> int:
        """Total non-deleted yoinks in the library, ignoring every filter.

        Backs the Library state contract (G-11): the search handler compares
        this against a filtered result count so the frontend can tell an
        *empty corpus* apart from a *query that matched nothing*, instead of
        collapsing both into ``total: 0``."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM yoinks WHERE deleted_at IS NULL"
            ).fetchone()
        return int(row["n"]) if row else 0

    def list_content_paths(self) -> list[dict]:
        """Every non-deleted row's (video_id, corpus_path, sidecar_path),
        for the C-05 path-integrity check and heal."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT video_id, corpus_path, sidecar_path FROM yoinks "
                "WHERE deleted_at IS NULL"
            ).fetchall()
        return [dict(r) for r in rows]

    def update_content_paths(self, video_id: str, *, corpus_path: str,
                             sidecar_path: str) -> None:
        """Re-point one row's on-disk paths (C-05 stale-path heal)."""
        with self._lock, self._rollback_on_error():
            self._conn.execute(
                "UPDATE yoinks SET corpus_path=?, sidecar_path=? "
                "WHERE video_id=?",
                (corpus_path, sidecar_path, video_id),
            )
            self._conn.commit()

    def engagement_backfill_batch(self, after_video_id: str = "") -> list[dict]:
        """At most 25 live rows, keyset-paged without retaining the library."""
        with self.read_snapshot() as conn:
            rows = conn.execute(
                "SELECT video_id, sidecar_path, yoinked_at, metadata_json "
                "FROM yoinks WHERE deleted_at IS NULL AND video_id > ? "
                "AND sidecar_path IS NOT NULL AND sidecar_path != '' "
                "ORDER BY video_id LIMIT 25", (after_video_id,)).fetchall()
        return [dict(row) for row in rows]

    def backfill_engagement_metadata(self, snapshot: dict, values: dict) -> bool:
        """Fill missing metrics only; preserve concurrent edits and all other data.

        The file read happens outside the index lock. Recheck the capture's
        identity and deletion state here so an old file cannot fill a newer
        capture. This deliberately avoids upsert_yoink's FTS/media side effects.
        """
        with self.write_transaction() as conn:
            row = conn.execute(
                "SELECT metadata_json FROM yoinks WHERE video_id=? "
                "AND deleted_at IS NULL AND sidecar_path IS ? AND yoinked_at IS ?",
                (snapshot["video_id"], snapshot["sidecar_path"],
                 snapshot["yoinked_at"])).fetchone()
            if row is None:
                return False
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except (TypeError, ValueError, RecursionError):
                return False
            if not isinstance(metadata, dict):
                return False
            additions = {
                key: values[key] for key in ENGAGEMENT_METADATA_FIELDS
                if metadata.get(key) is None and values.get(key) is not None
            }
            if not additions:
                return False
            metadata.update(additions)
            conn.execute(
                "UPDATE yoinks SET metadata_json=? WHERE video_id=?",
                (json.dumps(metadata, ensure_ascii=False), snapshot["video_id"]))
        return True

    # ---- Phase 2 taxonomy backfill (migration 0020) --------------------
    def rows_for_taxonomy_backfill(self) -> list[dict]:
        """Every live row's taxonomy-relevant fields, for the sidecar
        backfill (page_extractor.backfill_platform_author). Includes rows that
        already look fine; the backfill itself decides what to touch so it can
        report accurate before/after counts."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT video_id, source_type, platform, channel, author, "
                "sidecar_path FROM yoinks WHERE deleted_at IS NULL"
            ).fetchall()
        return [dict(r) for r in rows]

    def update_taxonomy(self, video_id: str, *, platform: str | None,
                        author: str | None, channel: str | None) -> None:
        """Set platform / author / channel on one row and refresh the FTS
        `channel` term so a corrected author is searchable. Used only by the
        Phase 2 backfill; new writes go through upsert_yoink."""
        with self._lock, self._rollback_on_error():
            self._conn.execute(
                "UPDATE yoinks SET platform=?, author=?, channel=? "
                "WHERE video_id=?",
                (platform, author, channel, video_id),
            )
            # Keep FTS in sync so a corrected author name is findable.
            self._conn.execute(
                "UPDATE yoinks_fts SET channel=? WHERE video_id=?",
                (channel, video_id),
            )
            self._conn.commit()

    def list_recent(self, limit: int = 20) -> list[dict]:
        """Most-recently-yoinked rows, newest first. Excludes soft-deleted
        (deleted_at IS NOT NULL) rows."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM yoinks WHERE deleted_at IS NULL "
                "ORDER BY yoinked_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- C-03 (CRIT-3): export / import of the SQLite-only user data ----
    # The corpus .md/.json files live on disk and are already user-owned;
    # these six tables existed ONLY inside index.db, so a lost or corrupt
    # database silently ate engagement history, tags, taste, drafts,
    # workspaces, and style anchors. Export writes them to a portable JSON
    # payload; import restores it (fresh-restore exact, merge conservative).
    EXPORT_TABLES = ("engagement_events", "yoink_tags", "memory_layer",
                     "writing_drafts", "workspaces", "style_anchors")
    EXPORT_FORMAT = "uoink-corpus-export"
    EXPORT_FORMAT_VERSION = 1

    def export_payload(self) -> dict:
        tables: dict[str, list[dict]] = {}
        with self._lock:
            for table in self.EXPORT_TABLES:
                rows = self._conn.execute(f"SELECT * FROM {table}").fetchall()
                tables[table] = [dict(r) for r in rows]
        return {
            "format": self.EXPORT_FORMAT,
            "format_version": self.EXPORT_FORMAT_VERSION,
            "exported_at": _now_iso(),
            "tables": tables,
        }

    def import_payload(self, payload: dict) -> dict:
        """Restore an export. Merge rules, conservative on purpose:

        - engagement_events: surrogate id dropped; a row identical on
          (video_id, event_type, ts_utc, source) is skipped.
        - memory_layer: newer updated_at wins; older imports never clobber.
        - id-keyed tables (drafts, workspaces, style_anchors): skipped when
          the id already exists (never overwrite local work with imports).
        - yoink_tags: INSERT OR IGNORE on the (video_id, tag) PK.

        Returns {table: {imported, skipped}} per table."""
        if not isinstance(payload, dict) \
                or payload.get("format") != self.EXPORT_FORMAT:
            raise ValueError("not a uoink corpus export")
        if int(payload.get("format_version") or 0) > self.EXPORT_FORMAT_VERSION:
            raise ValueError(
                "this export was written by a newer Uoink; update first")
        report: dict[str, dict] = {}
        with self._lock, self._rollback_on_error():
            for table in self.EXPORT_TABLES:
                rows = (payload.get("tables") or {}).get(table) or []
                table_cols = {r[1] for r in self._conn.execute(
                    f"PRAGMA table_info({table})")}
                imported = skipped = 0
                for row in rows:
                    if not isinstance(row, dict):
                        skipped += 1
                        continue
                    data = {k: v for k, v in row.items() if k in table_cols}
                    if not data:
                        skipped += 1
                        continue
                    if table == "engagement_events":
                        data.pop("id", None)
                        exists = self._conn.execute(
                            "SELECT 1 FROM engagement_events WHERE video_id=? "
                            "AND event_type=? AND ts_utc=? AND source=?",
                            (data.get("video_id"), data.get("event_type"),
                             data.get("ts_utc"), data.get("source"))
                        ).fetchone()
                        if exists:
                            skipped += 1
                            continue
                    elif table == "memory_layer":
                        existing = self._conn.execute(
                            "SELECT updated_at FROM memory_layer WHERE key=?",
                            (data.get("key"),)).fetchone()
                        if existing and str(existing["updated_at"] or "") \
                                >= str(data.get("updated_at") or ""):
                            skipped += 1
                            continue
                        self._conn.execute(
                            "INSERT INTO memory_layer (key, value, updated_at) "
                            "VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET "
                            "value=excluded.value, "
                            "updated_at=excluded.updated_at",
                            (data.get("key"), data.get("value"),
                             data.get("updated_at")))
                        imported += 1
                        continue
                    elif data.get("id") is not None:
                        exists = self._conn.execute(
                            f"SELECT 1 FROM {table} WHERE id=?",
                            (data["id"],)).fetchone()
                        if exists:
                            skipped += 1
                            continue
                    columns = ", ".join(data.keys())
                    marks = ", ".join("?" for _ in data)
                    try:
                        cur = self._conn.execute(
                            f"INSERT OR IGNORE INTO {table} ({columns}) "
                            f"VALUES ({marks})", tuple(data.values()))
                        if cur.rowcount:
                            imported += 1
                        else:
                            skipped += 1
                    except sqlite3.Error:
                        skipped += 1
                report[table] = {"imported": imported, "skipped": skipped}
            self._conn.commit()
        return report

    def enrich_yoinks(self, rows: list[dict]) -> list[dict]:
        """Batch-annotate a page of yoink rows with index-side enrichment
        (Sprint 19.6 / Fix 4). Adds, in place:

        * ``hook_type`` -- resolved from the taxonomy table (authoritative;
          the hook worker updates taxonomy, not yoinks, when it finishes)
          falling back to the yoinks row's own value.
        * ``hook_type_confidence`` -- int or None.
        * ``entity_count`` -- distinct entities mentioned in the video.
        * ``top_entities`` -- up to five entity names, most-mentioned first.

        Runs exactly three IN-list queries regardless of page size, in
        place of the per-row reach-into-self._conn pattern that used to
        be N+1 from the popup / Memory page. Callers that also want
        sidecar-fresh ``health`` or filesystem-derived fields like the
        thumbnail path layer those on outside the index."""
        if not rows:
            return rows
        video_ids = [r.get("video_id") for r in rows if r.get("video_id")]
        if not video_ids:
            return rows
        placeholders = ", ".join("?" * len(video_ids))
        with self._lock:
            # 1. Hook Type + confidence from the taxonomy table.
            tax_rows = self._conn.execute(
                f"SELECT video_id, hook_type, confidence FROM taxonomy "
                f"WHERE video_id IN ({placeholders})",
                video_ids,
            ).fetchall()
            tax_map = {t["video_id"]: t for t in tax_rows}
            # 2. Entity count -- distinct entity_id per video.
            ec_rows = self._conn.execute(
                f"SELECT video_id, COUNT(DISTINCT entity_id) AS c "
                f"FROM entity_mentions WHERE video_id IN ({placeholders}) "
                f"GROUP BY video_id",
                video_ids,
            ).fetchall()
            ec_map = {r["video_id"]: int(r["c"] or 0) for r in ec_rows}
            # 3. Top entities -- per-video name list, ordered by mention
            # count. Pull every (video_id, entity, count) once and
            # partition in Python so we don't fire one query per video.
            te_rows = self._conn.execute(
                f"SELECT em.video_id AS video_id, e.name AS name, "
                f"       COUNT(*) AS n "
                f"FROM entity_mentions em "
                f"JOIN entities e ON e.entity_id = em.entity_id "
                f"WHERE em.video_id IN ({placeholders}) "
                f"GROUP BY em.video_id, em.entity_id "
                f"ORDER BY em.video_id, n DESC",
                video_ids,
            ).fetchall()
        te_map: dict[str, list[str]] = {}
        for r in te_rows:
            bucket = te_map.setdefault(r["video_id"], [])
            if len(bucket) < 5:
                bucket.append(r["name"])

        for r in rows:
            vid = r.get("video_id")
            tax = tax_map.get(vid)
            confidence = None
            if tax:
                if tax["hook_type"]:
                    r["hook_type"] = tax["hook_type"]
                if tax["confidence"] is not None:
                    confidence = int(tax["confidence"])
            r["hook_type_confidence"] = confidence
            r["entity_count"] = ec_map.get(vid, 0)
            r["top_entities"] = te_map.get(vid, [])
        return rows

    # ---- v2.5 S2 engagement memory ----------------------------------------
    # Pure local instrumentation. NO outbound calls. Value score is a
    # time-decayed weighted sum:
    #
    #   weights:
    #     opened       1.0    -- corpus markdown opened
    #     search_hit   0.3    -- appeared in a search results page
    #     search_click 1.5    -- clicked through from search
    #     paste        3.0    -- corpus pasted somewhere (strong signal of use)
    #     cite         4.0    -- cited by name in a user doc (strongest)
    #     recent_open  0.5    -- opened via the Recent list
    #
    #   decay: half-life = 30 days. decayed = weight * exp(-ln(2) * age_days/30)
    #
    # Formula is decoupled from the row write -- log_engagement appends an
    # event; engagement_signal()/top_engaged() compute the score on read so we
    # can tune the formula without rewriting history.

    _ENGAGEMENT_EVENT_TYPES = (
        "opened", "search_hit", "search_click", "paste", "cite", "recent_open",
    )
    _ENGAGEMENT_SOURCES = ("popup", "dashboard", "mcp", "extension")
    _ENGAGEMENT_WEIGHTS = {
        "opened": 1.0, "search_hit": 0.3, "search_click": 1.5,
        "paste": 3.0, "cite": 4.0, "recent_open": 0.5,
    }
    _ENGAGEMENT_HALF_LIFE_DAYS = 30.0

    def log_engagement(self, video_id: str, event_type: str, source: str,
                       *, ts_utc: str | None = None) -> int:
        """Append an engagement event. Returns the new row id."""
        if not video_id:
            raise ValueError("log_engagement: video_id required")
        if event_type not in self._ENGAGEMENT_EVENT_TYPES:
            raise ValueError(f"event_type must be one of {self._ENGAGEMENT_EVENT_TYPES}")
        if source not in self._ENGAGEMENT_SOURCES:
            raise ValueError(f"source must be one of {self._ENGAGEMENT_SOURCES}")
        ts = ts_utc or _now_iso()
        with self._lock, self._rollback_on_error():
            cur = self._conn.execute(
                "INSERT INTO engagement_events (video_id, event_type, ts_utc, source) "
                "VALUES (?, ?, ?, ?)",
                (video_id, event_type, ts, source))
            # C-03 (CRIT-3): without this commit the event sat in an open
            # transaction until some other write path happened to commit,
            # and a process kill silently dropped it.
            self._conn.commit()
            return cur.lastrowid or 0

    def ingest_suite_engagement(self, events: list[dict]) -> dict:
        """Ingest one validated cross-product batch atomically.

        The caller validates the exact wire envelope before this method.
        Item resolution and event-id idempotency happen under the same
        database lock and transaction as the accepted inserts.
        """
        import engagement_contract

        submitted = len(events)
        accepted = 0
        duplicates = 0
        rejected: list[dict] = []
        with self._lock:
            saved_level = self._conn.isolation_level
            try:
                self._conn.isolation_level = None
                self._conn.execute("BEGIN IMMEDIATE")
                for event in events:
                    event_id = event["event_id"]
                    duplicate = self._conn.execute(
                        "SELECT 1 FROM engagement_events WHERE event_id=?",
                        (event_id,),
                    ).fetchone()
                    if duplicate is not None:
                        duplicates += 1
                        continue
                    item_id = engagement_contract.item_id_from_ref(
                        event["item_ref"]
                    )
                    item = self._conn.execute(
                        "SELECT 1 FROM yoinks "
                        "WHERE video_id=? AND deleted_at IS NULL",
                        (item_id,),
                    ).fetchone()
                    if item is None:
                        rejected.append(
                            {
                                "event_id": event_id,
                                "code": "not_found",
                                "message": "corpus item not found",
                                "retryable": False,
                            }
                        )
                        continue
                    self._conn.execute(
                        "INSERT INTO engagement_events "
                        "(event_id, video_id, event_type, ts_utc, source) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            event_id,
                            item_id,
                            event["event_type"],
                            event["occurred_at"],
                            event["source_product"],
                        ),
                    )
                    accepted += 1
                self._conn.execute("COMMIT")
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            finally:
                self._conn.isolation_level = saved_level
        return {
            "submitted": submitted,
            "accepted": accepted,
            "duplicates": duplicates,
            "rejected": rejected,
        }

    def _decayed(self, weight: float, age_days: float) -> float:
        import math
        return weight * math.exp(-math.log(2.0) * max(age_days, 0.0)
                                  / self._ENGAGEMENT_HALF_LIFE_DAYS)

    def engagement_signal(self, video_id: str) -> dict:
        """Compute the time-decayed value_score + per-type counts + last event
        timestamp for one video. Pure read; never touches the network."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT event_type, ts_utc FROM engagement_events "
                "WHERE video_id=? ORDER BY ts_utc",
                (video_id,)).fetchall()
        if not rows:
            return {"video_id": video_id, "value_score": 0.0,
                    "event_counts": {}, "last_event_ts": None,
                    "total_events": 0}
        counts: dict[str, int] = {}
        score = 0.0
        last_ts = None
        for r in rows:
            etype = r["event_type"]
            counts[etype] = counts.get(etype, 0) + 1
            last_ts = r["ts_utc"]
            try:
                ts = datetime.fromisoformat(r["ts_utc"])
                # Native events predate the suite contract and use local,
                # timezone-naive timestamps. Suite events are RFC 3339 UTC
                # (`...Z`) and parse as timezone-aware. Subtract like from
                # like so both histories decay on the same 30-day curve.
                now = (datetime.now(ts.tzinfo)
                       if ts.tzinfo is not None else datetime.now())
                age_days = (now - ts).total_seconds() / 86400.0
            except (ValueError, TypeError):
                age_days = 0.0
            score += self._decayed(self._ENGAGEMENT_WEIGHTS.get(etype, 0.0),
                                    age_days)
        return {"video_id": video_id,
                "value_score": round(score, 4),
                "event_counts": counts,
                "last_event_ts": last_ts,
                "total_events": len(rows)}

    def top_engaged(self, limit: int = 20) -> list[dict]:
        """Top-N videos by current value_score. Computed in Python because the
        formula uses exp() decay -- SQLite scalar funcs would work too, but
        Python's clarity beats SQLite math at our scale (low-thousands events
        on a personal corpus)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT video_id FROM engagement_events").fetchall()
        scored = [self.engagement_signal(r["video_id"]) for r in rows]
        scored.sort(key=lambda s: s["value_score"], reverse=True)
        return scored[: max(1, min(int(limit), 500))]

    def get_health(self, video_id: str) -> dict | None:
        """Return the parsed health-score dict for a video, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT health_score_json FROM yoinks WHERE video_id=?",
                (video_id,),
            ).fetchone()
        if not row or not row["health_score_json"]:
            return None
        try:
            return json.loads(row["health_score_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    # ---- v2.5 S1 facets / tags ---------------------------------------------
    _FACET_COLS = ("format", "performance_tier", "production_style",
                   "length_bucket", "topic", "hook_type")

    def set_facets(self, video_id: str, **fields) -> int:
        """Update facet columns on one yoink row. None values are skipped so
        a partial classification doesn't blow away previously-set fields.
        Returns the number of columns updated (0 if no changes)."""
        pairs = [(k, v) for k, v in fields.items()
                 if k in self._FACET_COLS and v is not None]
        if not pairs:
            return 0
        set_sql = ", ".join(f"{k}=?" for k, _ in pairs)
        params = [v for _, v in pairs] + [video_id]
        with self._lock, self._rollback_on_error():
            self._conn.execute(
                f"UPDATE yoinks SET {set_sql} WHERE video_id=?", params)
            self._conn.commit()  # C-03: facets must survive a kill
        return len(pairs)

    def add_tags(self, video_id: str, tags, *, source: str = "agent") -> int:
        """Append free-form tags to a yoink (idempotent via the (video_id, tag)
        PK). Empty/whitespace tags are dropped; tags are lower-cased on store
        so a query for 'mcp' matches 'MCP'. Returns count of new rows inserted."""
        if isinstance(tags, str):
            tags = [tags]
        now = _now_iso()
        added = 0
        with self.write_transaction() as conn:
            for raw in tags or []:
                t = (raw or "").strip().lower()
                if not t:
                    continue
                try:
                    conn.execute(
                        "INSERT INTO yoink_tags (video_id, tag, source, added_at) "
                        "VALUES (?, ?, ?, ?)", (video_id, t, source, now))
                    added += 1
                except sqlite3.IntegrityError:
                    pass
        return added

    def get_tags(self, video_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tag FROM yoink_tags WHERE video_id=? ORDER BY added_at",
                (video_id,)).fetchall()
        return [r[0] for r in rows]

    def query_by_facets(self, *, format: str | None = None,
                        performance_tier: str | None = None,
                        hook_type: str | None = None, topic: str | None = None,
                        length_bucket: str | None = None,
                        tag: str | None = None,
                        limit: int = 50) -> list[dict]:
        """Filter yoinks by facet values. All filters AND-combined; None =
        ignore. Newest first; limit clamped to a sane upper bound."""
        wheres: list[str] = []
        params: list = []
        for col, val in (("format", format),
                         ("performance_tier", performance_tier),
                         ("hook_type", hook_type),
                         ("topic", topic),
                         ("length_bucket", length_bucket)):
            if val:
                wheres.append(f"y.{col}=?")
                params.append(val)
        if tag:
            wheres.append("EXISTS (SELECT 1 FROM yoink_tags t "
                          "WHERE t.video_id=y.video_id AND t.tag=?)")
            params.append(tag.strip().lower())
        where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
        params.append(max(1, min(int(limit), 500)))
        cols = ("video_id", "slug", "channel", "title", "topic", "hook_type",
                "format", "performance_tier", "production_style",
                "length_bucket", "yoinked_at")
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {', '.join(cols)} FROM yoinks y{where_sql} "
                f"ORDER BY yoinked_at DESC LIMIT ?", params).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def corpus_facets(self) -> dict:
        """Corpus-wide facet values with counts, plus the yoinked_at date
        bounds. Backs the Library filter chips (G-12 / QA #14): filters must
        reflect the whole corpus, not just the cards currently loaded on the
        page, so a channel with no card in the first 50 rows still filters.

        Every facet is a list of ``{value, count}`` newest-usage-agnostic,
        ordered by count desc then value. Soft-deleted rows are excluded.
        ``date_bounds`` is ``{min, max}`` (yoinked_at) or nulls on an empty
        corpus."""
        # Phase 2: platform / source_type / author are the source-first facets
        # (every source maps into them); the video-only facets (format,
        # performance_tier, length_bucket) are kept but the UI shows them only
        # when Platform=YouTube. `channel` stays for backward compatibility.
        facet_cols = ("platform", "source_type", "author", "channel",
                      "format", "performance_tier",
                      "length_bucket", "topic", "hook_type")
        out: dict = {}
        with self._lock:
            for col in facet_cols:
                rows = self._conn.execute(
                    f"SELECT {col} AS v, COUNT(*) AS n FROM yoinks "
                    f"WHERE deleted_at IS NULL AND {col} IS NOT NULL "
                    f"AND {col} != '' "
                    f"GROUP BY {col} ORDER BY n DESC, v ASC",
                ).fetchall()
                out[col] = [{"value": r["v"], "count": int(r["n"])}
                            for r in rows]
            bounds = self._conn.execute(
                "SELECT MIN(yoinked_at) AS lo, MAX(yoinked_at) AS hi "
                "FROM yoinks WHERE deleted_at IS NULL"
            ).fetchone()
        out["date_bounds"] = {
            "min": bounds["lo"] if bounds else None,
            "max": bounds["hi"] if bounds else None,
        }
        return out

    def channel_view_counts(self, channel: str) -> list[int]:
        """View counts for a channel pulled from metadata_json. Used by the
        performance-tier heuristic (channel-relative percentile rank)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT metadata_json FROM yoinks "
                "WHERE channel=? AND metadata_json IS NOT NULL",
                (channel,)).fetchall()
        out: list[int] = []
        for (raw,) in rows:
            try:
                d = json.loads(raw) if raw else {}
                v = d.get("views") or d.get("view_count")
                if isinstance(v, (int, float)):
                    out.append(int(v))
            except (json.JSONDecodeError, TypeError):
                pass
        return out

    # ---- smart-input pickers (G-21) -------------------------------------
    def corpus_channels(self, *, q: str | None = None,
                        limit: int = 200) -> list[dict]:
        """Channels present across the captured corpus, with a count and the
        most-recent corpus_path per channel (so the caller can resolve a
        representative thumbnail). Backs the channel picker (G-21).

        Distinct from the registered-channels list (that's the user's own
        channels); this is every channel appearing in saved uoinks. Optional
        ``q`` is a case-insensitive substring filter for type-ahead. Bounded
        by ``limit`` (top by count) so a large corpus never returns thousands
        of rows. Soft-deleted rows are excluded."""
        clauses = ["deleted_at IS NULL", "channel IS NOT NULL", "channel != ''"]
        params: list = []
        if q:
            clauses.append("channel LIKE ? ESCAPE '\\'")
            params.append("%" + _like_escape(q) + "%")
        where = " AND ".join(clauses)
        params.append(max(1, min(int(limit), 500)))
        with self._lock:
            rows = self._conn.execute(
                "SELECT channel, COUNT(*) AS n, MAX(yoinked_at) AS recent, "
                "(SELECT corpus_path FROM yoinks y2 "
                " WHERE y2.channel = y.channel AND y2.deleted_at IS NULL "
                " ORDER BY yoinked_at DESC LIMIT 1) AS corpus_path "
                f"FROM yoinks y WHERE {where} "
                "GROUP BY channel ORDER BY n DESC, channel ASC LIMIT ?",
                params,
            ).fetchall()
        return [{"channel": r["channel"], "count": int(r["n"]),
                 "corpus_path": r["corpus_path"] or ""} for r in rows]

    def recent_ctas(self, *, limit: int = 20) -> list[dict]:
        """Distinct CTAs used in past scripts, most-recent first, for the CTA
        picker (G-21). Returns ``[{text, last_used}]``. Empty when the scripts
        table is empty or the column is unused."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT cta AS text, MAX(generated_at) AS last_used "
                "FROM scripts WHERE cta IS NOT NULL AND TRIM(cta) != '' "
                "GROUP BY cta ORDER BY last_used DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [{"text": r["text"], "last_used": r["last_used"]} for r in rows]

    # ---- memory / soft delete (Sprint 18) -------------------------------
    @uoink_usage.search(query_arg="q")
    def search_yoinks_for_memory(self, *, q: str | None = None,
                                 channel: str | None = None,
                                 topic: str | None = None,
                                 hook_type: str | None = None,
                                 platform: str | None = None,
                                 source_type: str | None = None,
                                 author: str | None = None,
                                 date_from: str | None = None,
                                 date_to: str | None = None,
                                 limit: int = 50,
                                 offset: int = 0,
                                 match: str = "forgiving", passages: bool = True) -> dict:
        """Filtered query backing the memory page. All filters are optional
        and combinable. Returns ``{total, results}`` where ``total`` is the
        match count before limit/offset (for pagination). Soft-deleted rows
        (deleted_at IS NOT NULL) are excluded.

        With ``q`` the rows are ranked by FTS5 bm25; without it they are
        ordered newest-first. ``date_from`` / ``date_to`` are inclusive
        YYYY-MM-DD bounds on yoinked_at."""
        limit = max(1, min(200, int(limit)))
        offset = max(0, int(offset))

        clauses = ["y.deleted_at IS NULL"]
        params: list = []
        if channel:
            clauses.append("y.channel = ?")
            params.append(channel)
        if platform:
            clauses.append("y.platform = ?")
            params.append(platform)
        if source_type:
            clauses.append("y.source_type = ?")
            params.append(source_type)
        if author:
            clauses.append("y.author = ?")
            params.append(author)
        if topic:
            clauses.append("y.topic = ?")
            params.append(topic)
        if hook_type:
            clauses.append("y.hook_type = ?")
            params.append(hook_type)
        if date_from:
            clauses.append("y.yoinked_at >= ?")
            params.append(date_from)
        if date_to:
            # Inclusive upper bound on a YYYY-MM-DD date: yoinked_at carries
            # a time component, so match anything strictly before the next
            # day rather than <= the bare date string.
            try:
                nxt = (datetime.strptime(date_to, "%Y-%m-%d")
                       + timedelta(days=1)).strftime("%Y-%m-%d")
                clauses.append("y.yoinked_at < ?")
                params.append(nxt)
            except ValueError:
                log.warning("memory search: bad date_to %r ignored", date_to)
        where = " AND ".join(clauses)

        expression = _fts_query(q, match)
        with self.search_read() as db:
            try:
                if expression:
                    prefix, search_params = _fts_hits(
                        "yoinks_fts", q, match, self._YOINKS_BM25_WEIGHTS if match == "forgiving" else "")
                    # Keep FTS candidates first. Driving this join from the
                    # deleted_at index repeats every hit for every live row.
                    tail = ("FROM search_hits h CROSS JOIN yoinks y ON y.video_id = h.video_id "
                            "WHERE " + where)
                    # For large pages, one ranked scan with COUNT OVER is
                    # cheaper than a rank stream followed by a separate count.
                    rows = (self._ranked_source_page(db, q, limit, offset, where, params)
                            if match == "forgiving" and limit + offset < 128 else None)
                    if rows is not None:
                        cnt = db.execute(
                            "SELECT COUNT(*) FROM yoinks_fts CROSS JOIN yoinks y "
                            "ON y.video_id=yoinks_fts.video_id WHERE yoinks_fts MATCH ? AND " + where,
                            [expression, *params]).fetchone()
                        total = int(cnt[0])
                    else:
                        rows = db.execute(
                            _fts_page(prefix, tail, "h._score, y.video_id", offset=True, total=True, snippets=passages),
                            search_params + params + [limit, offset] + ([expression] if passages else [])).fetchall()
                        total = int(rows[0]["_total"]) if rows else 0
                        if not rows and offset:
                            # An out-of-range page still needs the filtered count.
                            count_prefix, count_params = _fts_hits("yoinks_fts", q, match, ranked=False)
                            cnt = db.execute(
                                count_prefix + "SELECT COUNT(*) AS n " + tail, count_params + params
                            ).fetchone()
                            total = int(cnt["n"]) if cnt else 0
                elif q:
                    # q was given but yielded no usable FTS terms.
                    return {"total": 0, "results": []}
                else:
                    cnt = db.execute(
                        "SELECT COUNT(*) AS n FROM yoinks y WHERE " + where,
                        params,
                    ).fetchone()
                    total = int(cnt["n"]) if cnt else 0
                    rows = db.execute(
                        "SELECT y.* FROM yoinks y WHERE " + where
                        + " ORDER BY y.yoinked_at DESC LIMIT ? OFFSET ?",
                        params + [limit, offset],
                    ).fetchall()
            except sqlite3.OperationalError as error:
                # Defensive: a MATCH expression FTS5 still rejects.
                self._search_error(error, q, "memory search")
                return {"total": 0, "results": []}
        rows = [{key: r[key] for key in r.keys() if key != "_total"} for r in rows]
        return {"total": total, "results": self._search_passages(rows, q, match) if q and passages else rows}

    def soft_delete_yoink(self, video_id: str) -> dict | None:
        """Mark a yoink soft-deleted (deleted_at = now). Returns the updated
        row, or None if there is no such yoink."""
        with self._lock, self._rollback_on_error():
            self._conn.execute(
                "UPDATE yoinks SET deleted_at=? WHERE video_id=?",
                (_now_iso(), video_id),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM yoinks WHERE video_id=?", (video_id,)
            ).fetchone()
        self._invalidate_library_sources([video_id])
        self._notify_source_changed(video_id)
        return dict(row) if row else None

    def restore_yoink(self, video_id: str) -> dict | None:
        """Clear a yoink's deleted_at. Returns the updated row, or None."""
        with self._lock, self._rollback_on_error():
            self._conn.execute(
                "UPDATE yoinks SET deleted_at=NULL WHERE video_id=?",
                (video_id,),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM yoinks WHERE video_id=?", (video_id,)
            ).fetchone()
        self._notify_source_changed(video_id)
        return dict(row) if row else None

    def prune_trash(self, now: datetime) -> list[str]:
        """Return the video_ids whose deleted_at is older than the 30-day
        trash-retention window. The caller (server.py) hard-removes each
        trash folder and then the index row via delete_yoink."""
        cutoff = (now - timedelta(days=_TRASH_RETENTION_DAYS)).strftime(
            "%Y-%m-%dT%H:%M:%S")
        with self._lock:
            rows = self._conn.execute(
                "SELECT video_id FROM yoinks "
                "WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,)
            ).fetchall()
        return [r["video_id"] for r in rows]

    # ---- rate-limit retry queue (Sprint 19 / C4) ------------------------
    def enqueue_pending_once(self, url: str, interval: int,
                             retry_after: str, long_video_mode: str = "full") -> tuple[int, bool]:
        """Return (pending_id, inserted), reusing an active row for this URL.

        The helper and stdio server have separate connections and locks.
        BEGIN IMMEDIATE holds SQLite's write reservation across the check and
        enqueue_pending's insert/commit. Ordinary enqueue_pending callers keep
        their unconditional-insert behavior and terminal-row cleanup.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT pending_id FROM pending_yoinks WHERE url=? "
                    "AND status IN ('pending','running') ORDER BY pending_id DESC LIMIT 1",
                    (url,),
                ).fetchone()
                if row is not None:
                    self._conn.commit()
                    return row["pending_id"], False
                return self.enqueue_pending(url, interval, retry_after, long_video_mode), True
            except BaseException:
                self._conn.rollback()
                raise

    def enqueue_pending(self, url: str, interval: int,
                        retry_after: str, long_video_mode: str = "full") -> int:
        """Add a rate-limited URL to the queue with status='pending' and
        attempt_count=0. Returns the new pending_id.

        Sprint 19.6 / Fix 7: before the insert, drop the oldest terminal
        rows when the table is at or above the cap. Live rows (pending /
        running) are never evicted; only succeeded / failed / cancelled
        rows past the retention window. Typical users have <10 pending at
        a time, so the cap (1000) only kicks in for noisy clients or a
        rough YouTube rate-limit day."""
        terminal_placeholders = ", ".join("?" * len(_PENDING_TERMINAL_STATES))
        with self._lock, self._rollback_on_error():
            total = self._conn.execute(
                "SELECT COUNT(*) FROM pending_yoinks"
            ).fetchone()[0]
            over = total - _PENDING_TABLE_CAP + 1  # +1 for the row we're about to add
            if over > 0:
                # Delete the oldest `over` terminal rows by queued_at. The
                # subquery has to materialise the id list first because
                # SQLite doesn't allow modifying a table inside a self-
                # selecting DELETE on the same table.
                self._conn.execute(
                    f"DELETE FROM pending_yoinks WHERE pending_id IN ("
                    f"  SELECT pending_id FROM pending_yoinks "
                    f"  WHERE status IN ({terminal_placeholders}) "
                    f"  ORDER BY queued_at ASC LIMIT ?"
                    f")",
                    (*_PENDING_TERMINAL_STATES, over),
                )
            cur = self._conn.execute(
                "INSERT INTO pending_yoinks "
                "(url, interval_seconds, queued_at, retry_after, "
                " attempt_count, status, long_video_mode) "
                "VALUES (?, ?, ?, ?, 0, 'pending', ?)",
                (url, int(interval or 30), _now_iso(), retry_after,
                 str(long_video_mode or "full")),
            )
            self._conn.commit()
            return cur.lastrowid

    def next_pending(self, now: str) -> dict | None:
        """The next pending row whose retry_after has arrived (oldest
        queued_at first), or None when the queue is empty / not yet
        eligible."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM pending_yoinks "
                "WHERE status='pending' AND retry_after <= ? "
                "ORDER BY queued_at LIMIT 1",
                (now,),
            ).fetchone()
        return dict(row) if row else None

    def set_pending_error(self, pending_id: int, error: str) -> None:
        """Store the initial refusal without counting it as a retry."""
        with self._lock, self._rollback_on_error():
            self._conn.execute(
                "UPDATE pending_yoinks SET last_error=? "
                "WHERE pending_id=? AND status='pending' AND attempt_count=0",
                (error, pending_id),
            )
            self._conn.commit()

    def mark_pending_running(self, pending_id: int, *,
                             cancel_event: threading.Event | None = None) -> bool:
        """Mark a pending row in flight. The retry worker calls this before
        the actual extract so a parallel call to next_pending won't pick the
        same row twice."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE pending_yoinks SET status='running' "
                "WHERE pending_id=? AND status='pending'",
                (pending_id,),
            )
            try:
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            if cur.rowcount and cancel_event is not None:
                # Register under the same lock as cancellation, so a cancel
                # between selection and ownership acquisition cannot be lost.
                self._pending_cancel_events[pending_id] = cancel_event
            return cur.rowcount > 0

    def release_pending_cancel_event(self, pending_id: int,
                                     cancel_event: threading.Event) -> None:
        """Release only this worker's event, including on exceptional exits."""
        with self._lock:
            if self._pending_cancel_events.get(pending_id) is cancel_event:
                self._pending_cancel_events.pop(pending_id)

    def pending_status(self, pending_id: int) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM pending_yoinks WHERE pending_id=?", (pending_id,),
            ).fetchone()
            return row["status"] if row else None

    def mark_pending_publishing(self, pending_id: int, *,
                                expected_status: str | None = "running") -> bool:
        """Fence cancellation before indexing or handing off a save receipt.

        Re-entering publication is harmless. Receipts may also claim a failed
        handoff or a manually requeued row, but never a cancelled or completed row.
        """
        with self._lock:
            try:
                cur = self._conn.execute(
                    "UPDATE pending_yoinks SET status='publishing' "
                    "WHERE pending_id=? AND status IN ('pending','running','publishing','failed') "
                    "AND (? IS NULL OR status IN (?, 'publishing'))",
                    (pending_id, expected_status, expected_status),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return cur.rowcount > 0

    def fail_pending_publication(self, pending_id: int, error: str) -> bool:
        """Settle a local save retry without counting another download attempt."""
        with self._lock:
            try:
                cur = self._conn.execute(
                    "UPDATE pending_yoinks SET status='failed', last_error=? "
                    "WHERE pending_id=? AND status='publishing'",
                    (error, pending_id),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return cur.rowcount > 0

    def defer_pending(self, pending_id: int, retry_after: str) -> bool:
        """Wait for an unfinished broadcast without consuming a failure attempt."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE pending_yoinks SET status='pending', retry_after=? "
                "WHERE pending_id=? AND status='running'",
                (retry_after, pending_id),
            )
            try:
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return cur.rowcount > 0

    def mark_pending_succeeded(self, pending_id: int,
                                succeeded_job_id: str | None, *,
                                expected_status: str | None = None) -> bool:
        """Mark a pending row terminally succeeded and record the resulting
        single-extract job_id (so the UI can deep-link to the result).

        Workers require their expected running or publishing state. Without
        that constraint, callers may unlink a settled job, but can never
        overwrite cancellation. Returns False when the expected state no
        longer matches."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE pending_yoinks "
                "SET status='succeeded', succeeded_job_id=?, last_error=NULL "
                "WHERE pending_id=? AND status != 'cancelled' "
                "AND (? IS NULL OR status=?)",
                (succeeded_job_id, pending_id, expected_status, expected_status),
            )
            try:
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return cur.rowcount > 0

    def mark_pending_failed(self, pending_id: int, error: str,
                             retry_after: str, *,
                             force_final: bool = False,
                             expected_status: str | None = None) -> str:
        """Record one failed attempt. Increments attempt_count, then either
        re-queues with the supplied retry_after (status='pending') if under
        the strike cap, or marks the row terminally 'failed' (when the cap
        is reached, or when force_final=True for non-recoverable errors).
        Workers pass their expected running or publishing state; legacy
        callers may also record an initial failure while the row is pending.

        Returns the resulting status so the caller can tell a re-queue from
        a strike-out without a second query: 'pending' when the row will be
        retried, 'failed' when it went terminal, '' for an unknown or stale
        pending_id (G-43 / E2E D5 -- the retry worker used to log a phantom
        'retry at ...' after the final attempt because it couldn't see the
        strike-out happen)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT attempt_count, status FROM pending_yoinks "
                "WHERE pending_id=? AND status != 'cancelled' AND status IN (?, ?)",
                (pending_id, expected_status or "pending", expected_status or "running"),
            ).fetchone()
            if row is None:
                return ""
            attempts = (row["attempt_count"] or 0) + 1
            if force_final or attempts >= _PENDING_MAX_ATTEMPTS:
                cur = self._conn.execute(
                    "UPDATE pending_yoinks "
                    "SET status='failed', attempt_count=?, last_error=? "
                    "WHERE pending_id=? AND status=?",
                    (attempts, error, pending_id, row["status"]),
                )
                status = "failed"
            else:
                cur = self._conn.execute(
                    "UPDATE pending_yoinks "
                    "SET status='pending', attempt_count=?, last_error=?, "
                    "    retry_after=? "
                    "WHERE pending_id=? AND status=?",
                    (attempts, error, retry_after, pending_id, row["status"]),
                )
                status = "pending"
            try:
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return status if cur.rowcount else ""

    def cancel_pending(self, pending_id: int) -> bool:
        """Mark a pending row terminally cancelled. Returns True when a row
        actually changed (False for unknown / terminal / publishing rows)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE pending_yoinks SET status='cancelled' "
                "WHERE pending_id=? AND status IN ('pending','running')",
                (pending_id,),
            )
            try:
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            if cur.rowcount:
                event = self._pending_cancel_events.get(pending_id)
                if event is not None:
                    event.set()
            return cur.rowcount > 0

    def retry_pending_now(self, pending_id: int) -> bool:
        """User-initiated 'try this one now': bumps retry_after to now and,
        for a 'failed' row, flips it back to 'pending'. No-op for
        'succeeded' / 'cancelled' / 'running' / 'publishing' rows.
        Returns True when a row changed."""
        with self._lock, self._rollback_on_error():
            cur = self._conn.execute(
                "UPDATE pending_yoinks "
                "SET status='pending', retry_after=? "
                "WHERE pending_id=? AND status IN ('pending','failed')",
                (_now_iso(), pending_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def list_pending(self, limit: int = 50, *,
                     include_terminal: bool = False) -> list[dict]:
        """Recent queue rows, newest queued first. By default hides
        succeeded / failed / cancelled rows."""
        if include_terminal:
            sql = ("SELECT * FROM pending_yoinks "
                   "ORDER BY queued_at DESC LIMIT ?")
            params: list = [max(1, int(limit))]
        else:
            placeholders = ", ".join("?" * len(_PENDING_TERMINAL_STATES))
            sql = (f"SELECT * FROM pending_yoinks "
                   f"WHERE status NOT IN ({placeholders}) "
                   f"ORDER BY queued_at DESC LIMIT ?")
            params = [*_PENDING_TERMINAL_STATES, max(1, int(limit))]
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def pending_counts(self) -> dict:
        """Counts grouped by status plus the earliest retry_after among
        'pending' rows -- feeds /queue/status without paging the table."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM pending_yoinks "
                "GROUP BY status"
            ).fetchall()
            next_row = self._conn.execute(
                "SELECT MIN(retry_after) AS m FROM pending_yoinks "
                "WHERE status='pending'"
            ).fetchone()
        counts = {r["status"]: int(r["n"]) for r in rows}
        return {
            "counts": counts,
            "next_retry_at": next_row["m"] if next_row else None,
        }

    def reset_running_pending(self) -> int:
        """Crash recovery at startup: any row stuck in 'running' (the helper
        died mid-retry) is flipped back to 'pending' with retry_after=now so
        the retry worker picks it up again. Interrupted publication is failed
        visibly and left to its save receipt. Returns the count requeued."""
        with self._lock:
            # Publication may have committed before a crash. Do not turn it
            # into another automatic download; a durable receipt, if present,
            # owns recovery. Otherwise leave a visible failure and keep files.
            try:
                self._conn.execute(
                    "UPDATE pending_yoinks SET status='failed', last_error=? "
                    "WHERE status='publishing'",
                    ("Capture publication was interrupted. Saved files were kept; "
                     "any queued publication receipt will retry the local save.",),
                )
                cur = self._conn.execute(
                    "UPDATE pending_yoinks SET status='pending', retry_after=? "
                    "WHERE status='running'",
                    (_now_iso(),),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return cur.rowcount

    # ---- citations -------------------------------------------------------
    def insert_citations(self, video_id: str, citations: list[dict]) -> int:
        """Bulk insert citation rows. Idempotent per (video_id, kind, seq):
        re-yoinking a video rewrites its rows via INSERT OR REPLACE. Returns
        the number of rows written.

        Callers pass a kind's complete, contiguous seq range, so any row of
        that kind with a seq past the batch's highest is a leftover from an
        earlier, longer extraction (a raw caption track re-yoinked into a
        few long paragraph chunks left ~700 stale cues behind on two live
        items). Those are removed so the citation map stays time-ordered.
        An empty list is an explicit empty replacement: every citation for
        the video is removed and clips are rebuilt in the same commit
        (BD-09).

        Living library phase 1: the video's clips are re-derived from the
        fresh citations in the same commit (clips.build_clips_for_video)."""
        rows = [
            (video_id, c.get("kind"), c.get("seq"),
             c.get("timestamp_start"), c.get("timestamp_end"),
             c.get("text"), c.get("file_path"), c.get("youtube_deep_link"),
             c.get("source_url"), c.get("source_deep_link"))
            for c in citations
        ]
        if not rows:
            import clips as _clips  # noqa: WPS433 -- keeps index importable alone
            with self._lock, self._rollback_on_error():
                self._conn.execute(
                    "DELETE FROM citations WHERE video_id=?", (video_id,))
                try:
                    _clips.build_clips_for_video(self._conn, video_id, commit=False)
                except sqlite3.Error:
                    log.exception("clip build failed for %s", video_id)
                self._conn.commit()
            self._invalidate_library_sources([video_id])
            self._notify_source_changed(video_id)
            return 0
        max_seq_by_kind: dict = {}
        for r in rows:
            kind, seq = r[1], r[2]
            if isinstance(seq, int) and kind is not None:
                max_seq_by_kind[kind] = max(max_seq_by_kind.get(kind, -1), seq)
        import clips as _clips  # noqa: WPS433 -- keeps index importable alone
        with self._lock, self._rollback_on_error():
            # Phase 6 (phase6-v1): once migration 0030 exists, each cue's local
            # label and its provenance object travel in the same write. A
            # label without provenance is never stored as attributed evidence.
            labelled = any(r[1] == "speaker" for r in
                           self._conn.execute("PRAGMA table_info(citations)"))
            if labelled:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO citations "
                    "(video_id, kind, seq, timestamp_start, timestamp_end, "
                    " text, file_path, youtube_deep_link, source_url, "
                    " source_deep_link, speaker, speaker_provenance_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [row + _citation_label_columns(c)
                     for row, c in zip(rows, citations)],
                )
            else:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO citations "
                    "(video_id, kind, seq, timestamp_start, timestamp_end, "
                    " text, file_path, youtube_deep_link, source_url, "
                    " source_deep_link) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
            for kind, max_seq in max_seq_by_kind.items():
                self._conn.execute(
                    "DELETE FROM citations WHERE video_id=? AND kind=? "
                    "AND seq > ?", (video_id, kind, max_seq))
            try:
                _clips.build_clips_for_video(self._conn, video_id, commit=False)
            except sqlite3.Error:
                # Clips are derived data; never let them block a citation
                # write. --build-clips re-derives everything.
                log.exception("clip build failed for %s", video_id)
            # MediaError and other escaping failures reach the rollback
            # guard, preserving the existing citations, snapshot and clips.
            self._conn.commit()
        self._invalidate_library_sources([video_id])
        self._notify_source_changed(video_id)
        return len(rows)

    # ---- Phase 6 media publication (phase6-v1, BC-2) ----------------------
    def _invalidate_after_publication(self, video_id: str) -> None:
        """Phase 2 invalidation as part of the publication operation: the
        committed snapshot is durable and replayable, so a failure here is a
        retryable ``library_unavailable`` rather than a silent log line."""
        self._notify_source_changed(video_id)
        import library_media as _media  # noqa: WPS433 -- keeps index importable alone
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='library_runs'").fetchone()
            if not exists or not self._conn.execute("SELECT 1 FROM library_runs LIMIT 1").fetchone():
                return
        try:
            from library_work import RequestContext
            result = self.library_service().invalidate_source_items(
                RequestContext(authenticated=True, operator=True), {"video_ids": [video_id]})
        except _media.MediaError:
            raise
        except Exception as exc:
            log.error("library source invalidation failed for %s: %s", video_id, type(exc).__name__)
            raise _media.MediaError("library_unavailable", details={
                "reason": "invalidation_failed", "next_step": "retry_publication"}) from exc
        if not result.get("ok"):
            log.error("library source invalidation failed: %s", result["error"]["code"])
            raise _media.MediaError("library_unavailable", details={
                "reason": "invalidation_failed", "service_error": result["error"]["code"],
                "next_step": "retry_publication"})

    def begin_media_publication(self, video_id: str, *, folder=None, capture_binding=None,
                                input_files=None):
        """Mint the publication ticket (ownership fence) a caller must carry
        into ``publish_media_snapshot``. See library_media.begin_publication."""
        import library_media as _media  # noqa: WPS433 -- keeps index importable alone
        with self._lock:
            return _media.begin_publication(
                self._conn, video_id, folder=folder, capture_binding=capture_binding,
                input_files=input_files)

    def publish_media_snapshot(self, video_id: str, *, cues: list[dict], media_block: dict,
                               artifacts: dict, ticket=None) -> dict:
        """The complete publication operation: one coherent source/citation/
        media/clip snapshot committed under the index lock through
        ``library_media.publish_transcript`` (ownership fence, owned files,
        DB rows, artifact retention), then Phase 2 invalidation. Raises
        ``library_media.MediaError`` with a recoverable state on refusal.
        ``ticket`` is the build-time fence from ``begin_media_publication``;
        an omitted ticket is refused rather than minted here. Classification
        of omitted versus superseded committed input is the publisher's."""
        import library_media as _media  # noqa: WPS433 -- keeps index importable alone
        with self._lock:
            if self._conn.in_transaction:
                raise _media.MediaError("library_unavailable", details={"reason": "transaction_active"})
            result = _media.publish_transcript(self._conn, video_id, cues=cues, media_block=media_block,
                                               artifacts=artifacts, ticket=ticket)
        self._invalidate_after_publication(video_id)
        return result

    def rebuild_media_item(self, video_id: str, *, sidecar: dict | None) -> dict:
        """Reconstruction (or clip-only rebuild) as a complete operation:
        ``library_media.rebuild_item`` under the index lock, then Phase 2
        invalidation."""
        import library_media as _media  # noqa: WPS433 -- keeps index importable alone
        with self._lock:
            if self._conn.in_transaction:
                raise _media.MediaError("library_unavailable", details={"reason": "transaction_active"})
            result = _media.rebuild_item(self._conn, video_id, sidecar=sidecar)
        self._invalidate_after_publication(video_id)
        return result

    def prune_media_artifacts(self, video_id: str) -> dict:
        """Retry artifact retention cleanup for one item (never a read)."""
        import library_media as _media  # noqa: WPS433 -- keeps index importable alone
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM yoinks WHERE video_id=?", (video_id,)).fetchone()
            if row is None:
                raise _media.MediaError("resource_not_found")
            return _media.prune_artifacts(self._conn, dict(row))

    def store_media_snapshot(self, video_id: str, cues: list[dict], block: dict) -> int:
        """Phase 6 (phase6-v1): persist the validated media block's rows and
        the annotated clip projection for ``video_id`` after its citations
        were written, then invalidate Phase 2 work. Returns the clip count.
        Raises ``library_media.MediaError`` on a binding mismatch. Legacy
        seam: production publication goes through ``publish_media_snapshot``."""
        import library_media as _media  # noqa: WPS433 -- keeps index importable alone
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM yoinks WHERE video_id=?", (video_id,)).fetchone()
            if row is None:
                raise _media.MediaError("resource_not_found")
            count = _media.store_snapshot(self._conn, dict(row), cues, block, commit=True)
        self._invalidate_after_publication(video_id)
        return count

    def get_citations(self, video_id: str) -> list[dict]:
        """All citations for a video, ordered by kind then seq."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM citations WHERE video_id=? ORDER BY kind, seq",
                (video_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- jobs ------------------------------------------------------------
    def upsert_job(self, record: dict) -> None:
        """Insert or update one job row. ``metadata_json`` must already be a
        JSON string and must NOT contain combined_md_text / corpus payloads."""
        job_id = record.get("job_id")
        if not job_id:
            raise ValueError("upsert_job: record requires a job_id")
        record = dict(record)
        record.setdefault("updated_at", _now_iso())
        values = [record.get(col) for col in _JOB_COLUMNS]
        placeholders = ", ".join("?" * len(_JOB_COLUMNS))
        update_set = ", ".join(
            f"{col}=excluded.{col}" for col in _JOB_COLUMNS if col != "job_id"
        )
        with self._lock, self._rollback_on_error():
            self._conn.execute(
                f"INSERT INTO jobs ({', '.join(_JOB_COLUMNS)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT(job_id) DO UPDATE SET {update_set}",
                values,
            )
            self._conn.commit()
            self._insert_count += 1
        # Opportunistic retention: prune terminal jobs every 50 writes.
        if self._insert_count % 50 == 0:
            self.prune_jobs()

    def get_job(self, job_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_jobs(self, *, kind: str | None = None,
                  limit: int = 100) -> list[dict]:
        """Jobs newest-first, optionally filtered by kind."""
        sql = "SELECT * FROM jobs "
        params: list = []
        if kind:
            sql += "WHERE kind=? "
            params.append(kind)
        sql += "ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def delete_job(self, job_id: str) -> int:
        """Remove one job row by id. Returns the number of rows deleted (0 if
        the id was unknown). Used to supersede a stale terminal job when a
        fresh attempt for the same source replaces it (G-14)."""
        if not job_id:
            return 0
        with self._lock, self._rollback_on_error():
            cur = self._conn.execute(
                "DELETE FROM jobs WHERE job_id=?", (job_id,))
            self._conn.commit()
            return cur.rowcount

    def prune_jobs(self, keep_terminal: int = TERMINAL_JOB_RETENTION) -> int:
        """Keep at most ``keep_terminal`` most-recent terminal jobs; non-
        terminal jobs (pending/running) are always retained. Returns the
        number of rows deleted."""
        placeholders = ", ".join("?" * len(_TERMINAL_JOB_STATES))
        with self._lock, self._rollback_on_error():
            cur = self._conn.execute(
                f"DELETE FROM jobs WHERE status IN ({placeholders}) "
                f"AND job_id NOT IN ("
                f"  SELECT job_id FROM jobs WHERE status IN ({placeholders}) "
                f"  ORDER BY updated_at DESC, job_id DESC LIMIT ?"
                f")",
                (*_TERMINAL_JOB_STATES, *_TERMINAL_JOB_STATES, keep_terminal),
            )
            self._conn.commit()
            return cur.rowcount

    # ---- taxonomy --------------------------------------------------------
    def upsert_taxonomy(self, record: dict) -> None:
        """Insert or replace one taxonomy row, deduplicated by video_id.

        ``confidence`` (1-5, Sprint 17) is optional -- a record without it
        stores NULL, which is also the pre-Sprint-17 state."""
        video_id = record.get("video_id")
        if not video_id:
            raise ValueError("upsert_taxonomy: record requires a video_id")
        with self._lock, self._rollback_on_error():
            self._conn.execute(
                "INSERT OR REPLACE INTO taxonomy "
                "(video_id, hook_type, hook_explanation, channel, title, "
                " classified_at, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (video_id, record.get("hook_type"),
                 record.get("hook_explanation"), record.get("channel"),
                 record.get("title"),
                 record.get("classified_at") or _now_iso(),
                 record.get("confidence")),
            )
            self._conn.commit()

    def query_taxonomy(self, *, channel: str | None = None,
                       hook_type: str | None = None,
                       limit: int = 50) -> list[dict]:
        """Taxonomy rows, newest classification first, optional filters."""
        sql = "SELECT * FROM taxonomy "
        clauses: list[str] = []
        params: list = []
        if channel:
            # Case-insensitive to match the pre-index taxonomy query.
            clauses.append("channel = ? COLLATE NOCASE")
            params.append(channel)
        if hook_type:
            clauses.append("hook_type = ?")
            params.append(hook_type)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY classified_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ---- taxonomy corrections (Sprint 17) -------------------------------
    # Few-shot anchor budget: at most this many past corrections are fed
    # back into a classification prompt.
    _CORRECTION_FEWSHOT_CAP = 8

    def upsert_taxonomy_correction(self, video_id: str, original: str,
                                   corrected: str, user_reason: str | None = None,
                                   channel: str | None = None,
                                   topic: str | None = None) -> int:
        """Record a user's hook-type correction (append-only -- a video may
        be corrected more than once) and promote the corrected value to
        taxonomy.hook_type, so the corrected classification is canonical.
        channel / topic are denormalized in for similarity matching. Returns
        the new correction_id."""
        if not video_id:
            raise ValueError("upsert_taxonomy_correction: video_id required")
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO taxonomy_corrections "
                    "(video_id, original_hook_type, corrected_hook_type, "
                    " user_reason, corrected_at, channel, topic) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (video_id, original, corrected, user_reason or None,
                     _now_iso(), channel, topic),
                )
                correction_id = cur.lastrowid
                # The corrected value becomes the canonical classification.
                self._conn.execute(
                    "UPDATE taxonomy SET hook_type=? WHERE video_id=?",
                    (corrected, video_id),
                )
                self._conn.commit()
            except sqlite3.Error:
                self._conn.rollback()
                raise
        return correction_id

    def list_corrections(self, limit: int = 50, *,
                          channel: str | None = None,
                          topic: str | None = None) -> list[dict]:
        """Recent corrections, newest first, with the yoink title joined in.
        Optional channel / topic filters. Feeds the corrections-review
        surface."""
        sql = ("SELECT c.*, y.title AS title FROM taxonomy_corrections c "
               "LEFT JOIN yoinks y ON y.video_id = c.video_id ")
        clauses: list[str] = []
        params: list = []
        if channel:
            clauses.append("c.channel = ?")
            params.append(channel)
        if topic:
            clauses.append("c.topic = ?")
            params.append(topic)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY c.corrected_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def similar_corrections(self, video_id: str, limit: int = 8) -> list[dict]:
        """The corrections most relevant to ``video_id``, used as few-shot
        calibration anchors when re-classifying it.

        Relevance order: same channel (the creator's own style), then same
        topic (the broader category), then most-recent overall. Deduplicated
        and capped at 8. A video's own past corrections are intentionally
        included -- re-classifying a corrected video should see that the
        user already fixed it."""
        limit = max(1, min(self._CORRECTION_FEWSHOT_CAP, int(limit)))
        base = ("SELECT c.*, y.title AS title FROM taxonomy_corrections c "
                "LEFT JOIN yoinks y ON y.video_id = c.video_id ")
        out: list[dict] = []
        seen: set[int] = set()

        def _absorb(rows) -> bool:
            for r in rows:
                cid = r["correction_id"]
                if cid in seen:
                    continue
                seen.add(cid)
                out.append(dict(r))
                if len(out) >= limit:
                    return True
            return False

        with self._lock:
            vrow = self._conn.execute(
                "SELECT channel, topic FROM yoinks WHERE video_id=?",
                (video_id,),
            ).fetchone()
            channel = vrow["channel"] if vrow else None
            topic = vrow["topic"] if vrow else None
            # Pass 1: same channel.
            if channel:
                rows = self._conn.execute(
                    base + "WHERE c.channel = ? "
                    "ORDER BY c.corrected_at DESC LIMIT ?",
                    (channel, limit),
                ).fetchall()
                if _absorb(rows):
                    return out
            # Pass 2: same topic.
            if topic:
                rows = self._conn.execute(
                    base + "WHERE c.topic = ? "
                    "ORDER BY c.corrected_at DESC LIMIT ?",
                    (topic, limit),
                ).fetchall()
                if _absorb(rows):
                    return out
            # Pass 3: fill remaining slots with the most recent corrections.
            rows = self._conn.execute(
                base + "ORDER BY c.corrected_at DESC LIMIT ?", (limit,),
            ).fetchall()
            _absorb(rows)
        return out

    # ---- entities (Sprint 16) -------------------------------------------
    def record_entities(self, video_id: str, entities: list[dict], *,
                         source: str = "transcript") -> int:
        """Write one extraction's worth of entities + mentions for a video.

        Idempotent per video: a re-yoink first drops the video's previous
        entity_mentions (and rolls their mention_count back) so re-running
        the extraction worker never double-counts. Each entity is deduped on
        (name_normalized, type) via INSERT OR IGNORE; an unrecognised type
        folds to 'other'. The whole read-modify-write is one transaction.

        ``entities`` is the worker's parsed list of
        ``{name, type, mentions: [{timestamp, context}]}`` dicts. Returns the
        number of mention rows written."""
        if not video_id:
            raise ValueError("record_entities: video_id is required")
        now = _now_iso()
        written = 0
        with self._lock:
            try:
                # Idempotent re-yoink: clear this video's prior mentions and
                # decrement the affected entities' denormalised counters.
                prior = self._conn.execute(
                    "SELECT entity_id, COUNT(*) AS n FROM entity_mentions "
                    "WHERE video_id=? GROUP BY entity_id", (video_id,)
                ).fetchall()
                if prior:
                    self._conn.execute(
                        "DELETE FROM entity_mentions WHERE video_id=?", (video_id,)
                    )
                    for r in prior:
                        self._conn.execute(
                            "UPDATE entities "
                            "SET mention_count = MAX(0, mention_count - ?) "
                            "WHERE entity_id=?", (r["n"], r["entity_id"])
                        )
                for ent in entities or []:
                    if not isinstance(ent, dict):
                        continue
                    name = str(ent.get("name") or "").strip()
                    norm = normalize_entity_name(name)
                    if not name or not norm:
                        continue
                    etype = str(ent.get("type") or "other").strip().lower()
                    if etype not in ENTITY_TYPES:
                        etype = "other"
                    self._conn.execute(
                        "INSERT OR IGNORE INTO entities "
                        "(name, name_normalized, type, first_seen, last_seen, "
                        " mention_count) VALUES (?, ?, ?, ?, ?, 0)",
                        (name, norm, etype, now, now),
                    )
                    row = self._conn.execute(
                        "SELECT entity_id FROM entities "
                        "WHERE name_normalized=? AND type=?", (norm, etype)
                    ).fetchone()
                    if row is None:
                        continue
                    entity_id = row["entity_id"]
                    added = 0
                    for m in ent.get("mentions") or []:
                        if not isinstance(m, dict):
                            continue
                        ts = m.get("timestamp")
                        try:
                            ts = float(ts) if ts is not None else None
                        except (TypeError, ValueError):
                            ts = None
                        ctx = m.get("context")
                        ctx = str(ctx)[:500] if ctx else None
                        self._conn.execute(
                            "INSERT INTO entity_mentions "
                            "(entity_id, video_id, source, timestamp, context) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (entity_id, video_id, source, ts, ctx),
                        )
                        added += 1
                    if added:
                        self._conn.execute(
                            "UPDATE entities "
                            "SET mention_count = mention_count + ?, last_seen=? "
                            "WHERE entity_id=?", (added, now, entity_id)
                        )
                    written += added
                self._conn.commit()
            except sqlite3.Error:
                self._conn.rollback()
                raise
        return written

    def find_mentions(self, name: str, limit: int = 50, *, match: str = "forgiving") -> list[dict]:
        """Recorded mentions ranked by entity name, with newest first for ties.

        Strict keeps the original normalized-name lookup. Forgiving also
        matches useful words in recorded names. Rows carry source identity,
        stored timestamps, and a clip passage when the context quotes one.
        Soft-deleted yoinks are excluded."""
        norm = normalize_entity_name(name)
        _search_terms(name, match)
        if not norm:
            return []
        sql = (
            "SELECT y.video_id AS video_id, y.slug AS slug, y.title AS title, "
            "       y.channel AS channel, y.platform AS platform, "
            "       y.metadata_json AS metadata_json, "
            "       em.source AS source, "
            "       em.mention_id AS mention_id, em.timestamp AS timestamp, em.context AS context, "
            "       e.name AS _entity_name "
            "FROM entities e "
            "CROSS JOIN entity_mentions em ON em.entity_id = e.entity_id "
            "CROSS JOIN yoinks y ON y.video_id = em.video_id "
        )
        mention_select = sql
        if match == "strict":
            sql += ("WHERE e.name_normalized = ? AND y.deleted_at IS NULL "
                    "ORDER BY em.mention_id DESC LIMIT ?")
            params = [norm, max(1, int(limit))]
        else:
            # This is an entity-name lookup, not transcript FTS. Preserve
            # exact normalized names, then admit any useful name word.
            # Compute each entity's rank once before expanding its mentions.
            sql = ("WITH matched_entities AS MATERIALIZED (SELECT entity_id, name, "
                   "(name_normalized=?) AS exact, entity_keyword_score(name, ?) AS word_score "
                   "FROM entities WHERE name_normalized=? OR entity_keyword_score(name, ?)>0) "
                   + sql.replace("FROM entities e ", "FROM matched_entities e "))
            sql += ("WHERE y.deleted_at IS NULL ORDER BY (search_title_key(y.title)=?) DESC, "
                    "e.exact DESC, e.word_score DESC, "
                    "em.mention_id DESC LIMIT ?")
            params = [norm, name, norm, name, _search_title_key(name), max(1, int(limit))]
        with self.search_read() as db:
            if match == "forgiving":
                entities = db.execute(
                    "SELECT entity_id FROM entities WHERE name_normalized=? OR entity_keyword_score(name, ?)>0",
                    (norm, name)).fetchall()
                if len(entities) == 1 and not db.execute(
                        "SELECT 1 FROM yoinks WHERE deleted_at IS NULL AND search_title_key(title)=? LIMIT 1",
                        (_search_title_key(name),)).fetchone():
                    # With one name and no exact title, ranking is simply the
                    # newest mentions. Traverse its entity index backwards and
                    # stop at the page instead of sorting all its mentions.
                    sql = mention_select + ("WHERE e.entity_id=? AND y.deleted_at IS NULL "
                                            "ORDER BY em.mention_id DESC LIMIT ?")
                    params = [entities[0][0], max(1, int(limit))]
            cursor = db.execute(sql, params)
            keys = [column[0] for column in cursor.description]
            cursor.row_factory = None
            rows = [dict(zip(keys, values)) for values in cursor]
            identities = list(dict.fromkeys(r["video_id"] for r in rows))
            if not identities:
                return []
            patterns = {entity: re.compile(
                r"(?<!\w)" + r"[\W_]*".join(re.escape(t) for t in _fts_terms(entity)) + r"(?!\w)",
                re.IGNORECASE) for entity in {r["_entity_name"] for r in rows}}
            contexts = {}
            for row in rows:
                if row["context"]:
                    pair = (row["video_id"], row["context"])
                    contexts[pair] = (contexts.get(pair, True)
                                      and bool(patterns[row["_entity_name"]].search(row["context"])))
            clips = {}
            if contexts:
                # Verify only this page's literal quotes. The video_id index
                # bounds the text checks; no common-entity FTS posting list is
                # visited and BM25 is irrelevant to verifying a stored quote.
                for quoted_entity in (True, False):
                    selected = [pair for pair, quoted in contexts.items() if quoted == quoted_entity]
                    if not selected:
                        continue
                    # When the quote includes the entity, the first literal
                    # match is sufficient. Other annotations may require a
                    # later clip containing both the quote and entity name.
                    tail = ("SELECT DISTINCT found.* FROM page_contexts p CROSS JOIN clips found "
                            "ON found.clip_id=(SELECT c.clip_id FROM clips c WHERE c.video_id=p.video_id "
                            "AND instr(c.text,p.context)>0 ORDER BY c.seq, c.clip_id LIMIT 1) "
                            "ORDER BY found.video_id, found.seq" if quoted_entity else
                            "SELECT DISTINCT c.* FROM page_contexts p CROSS JOIN clips c "
                            "ON c.video_id=p.video_id WHERE instr(c.text,p.context)>0 ORDER BY c.video_id, c.seq")
                    for clip in db.execute(
                            "WITH page_contexts(video_id, context) AS (VALUES "
                            + ",".join("(?,?)" for _ in selected) + ") " + tail,
                            [value for pair in selected for value in pair]):
                        clips.setdefault(clip["video_id"], []).append(dict(clip))
                for candidates in clips.values():
                    candidates.sort(key=lambda clip: (clip["seq"], clip["clip_id"]))
            content_ids = list({r["video_id"] for r in rows
                                if patterns[r["_entity_name"]].search(r["context"] or "")
                                and not any(r["context"] in c["text"] for c in clips.get(r["video_id"], ()))})
            # Only unresolved quotes need source prose. MATCH avoids scanning
            # all FTS content for absent entities such as unverified annotations.
            expression = " OR ".join("(" + _fts_query(entity, "strict") + ")" for entity in patterns)
            contents = ({r["video_id"]: r["content"] for r in db.execute(
                "SELECT video_id, content FROM yoinks_fts WHERE yoinks_fts MATCH ? AND video_id IN ("
                + ",".join("?" for _ in content_ids) + ")", [expression, *content_ids])} if content_ids else {})
        from clips import timing_kind
        from uoink_core.search_service import citation_fields
        out = []
        for r in rows:
            d = r  # this method owns the dictionaries materialized above
            metadata_json = d.pop("metadata_json", None)
            video_id = d["video_id"]
            entity = d.pop("_entity_name")
            # Context is an entity annotation. When it quotes a stored clip,
            # carry that clip's identity and actual timing for exact quoting.
            context = d["context"]
            if context:
                candidates = clips.get(video_id)
                clip = next((c for c in candidates
                             if context in c["text"] and patterns[entity].search(c["text"])), None) if candidates else None
                if clip:
                    clip["timing"] = timing_kind(clip)
                    d["passage"] = {"video_id": video_id, **{
                        key: clip.get(key) for key in ("clip_id", "text", "start", "end", "timing")}}
                elif video_id in contents and patterns[entity].search(context):
                    start = (contents[video_id] or "").find(context)
                    if start >= 0:
                        d["passage"] = {"video_id": video_id, "text": context,
                                        "char_start": start, "char_end": start + len(context),
                                        "field": "content"}
                if "passage" in d:
                    d["passage_verified"] = True
            d = citation_fields(d, copy_row=False)
            # Keep the v1 annotation timestamp and link. Verified coordinates
            # live only in the additive passage and timestamp_seconds fields.
            d["deep_link"] = _entity_deep_link(
                video_id, d["timestamp"], platform=d["platform"], metadata_json=metadata_json)
            out.append(d)
        return out

    # ---- writing drafts (v3.2.5 / G-03) ----------------------------------
    def save_writing_draft(self, *, draft_id: int | None = None,
                           yoink_id: str | None = None, kind: str = "tweet",
                           title: str | None = None, body: str = "",
                           source_credit_line: str | None = None) -> dict:
        """Insert (draft_id is None) or update a writing draft, returning the
        stored row. Drafts hold composer state so a reload can recover it;
        unlike writing_pieces there is no credit or Voice DNA gate here.

        Raises ValueError for an empty body or an unknown draft_id, so the
        server can answer 400/404 instead of quietly saving nothing."""
        body = str(body or "")
        if not body.strip():
            raise ValueError("draft body required")
        now = _now_iso()
        with self.write_transaction() as conn:
            if draft_id is None:
                cur = conn.execute(
                    "INSERT INTO writing_drafts "
                    "(yoink_id, kind, title, body, source_credit_line, "
                    " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (yoink_id, str(kind or "tweet"), title, body,
                     source_credit_line, now, now),
                )
                draft_id = cur.lastrowid
            elif not _valid_rowid(draft_id):
                # An id SQLite can't hold can't match a row -> not found,
                # not a 500 from the failed bind (G-90).
                raise ValueError(f"draft {draft_id} not found")
            else:
                cur = conn.execute(
                    "UPDATE writing_drafts SET yoink_id=?, kind=?, title=?, "
                    "body=?, source_credit_line=?, updated_at=? WHERE id=?",
                    (yoink_id, str(kind or "tweet"), title, body,
                     source_credit_line, now, int(draft_id)),
                )
                if cur.rowcount == 0:
                    raise ValueError(f"draft {draft_id} not found")
        draft = self.get_writing_draft(int(draft_id))
        if draft is None:  # pragma: no cover -- row written above
            raise ValueError(f"draft {draft_id} not found")
        return draft

    def get_writing_draft(self, draft_id: int) -> dict | None:
        """One stored draft as a dict, or None when the id is unknown."""
        if not _valid_rowid(draft_id):
            return None  # out-of-range id can't exist (G-90)
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM writing_drafts WHERE id=?",
                (int(draft_id),),
            ).fetchone()
        return dict(row) if row else None

    def latest_writing_draft(self) -> dict | None:
        """The most recently touched draft, or None when none exist. Powers
        the R-02 "resume where you left off" card: the draft the user was
        last editing is the obvious thing to reopen. Ordered by updated_at,
        with id as a stable tiebreaker for drafts saved in the same second."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM writing_drafts "
                "ORDER BY updated_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

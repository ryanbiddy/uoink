"""Yoink local library index -- SQLite + FTS5.

Replaces the O(n) full-disk-scan code paths (search_yoinks, list_recent, the
post-extraction `_all-yoinks-index.md` rebuild) with an incremental SQLite
index, and absorbs jobs.json / taxonomy.json into queryable tables.

The database lives at ``%LOCALAPPDATA%\\Yoink\\index.db``. Both ``sqlite3``
and the FTS5 extension ship in the Python standard library, so this adds no
new dependency.

This module is self-contained: it owns the schema, the migration runner, and
all query helpers. server.py and yoink_mcp_tools.py call into ``Index`` and
never touch the database directly.

Schema / migrations: see the ``migrations/`` directory. ``_run_migrations``
applies any pending ``NNNN_*.sql`` file in numeric order and is idempotent.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("yoink.index")

_MIGRATIONS_DIR = Path(__file__).parent.resolve() / "migrations"

# Soft-deleted yoinks live in _yoink-trash/ for this many days before the
# scheduled purge hard-removes them.
_TRASH_RETENTION_DAYS = 30

# Rate-limit retry queue (Sprint 19 / C4). _PENDING_MAX_ATTEMPTS is the
# strike cap: after this many failures a pending row is marked terminal.
# The retry worker (server.py) decides backoff timing.
_PENDING_MAX_ATTEMPTS = 3
_PENDING_TERMINAL_STATES = ("succeeded", "failed", "cancelled")

# Columns of the `yoinks` table, in declaration order. video_id is the
# primary key and is handled separately in the upsert.
_YOINK_COLUMNS = (
    "video_id", "slug", "channel", "title", "topic", "hook_type",
    "yoinked_at", "corpus_path", "sidecar_path", "health_score_json",
    "metadata_json",
)

_JOB_COLUMNS = (
    "job_id", "kind", "status", "slug", "title", "error",
    "started_at", "updated_at", "metadata_json",
)

_TERMINAL_JOB_STATES = ("completed", "failed", "cancelled")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


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


def _current_schema_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied schema version, or 0 on a fresh database."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


# ``ALTER TABLE ... ADD COLUMN`` has no IF NOT EXISTS form, so the runner
# routes any ALTER statement in a migration through _safe_alter_add_column,
# which gates on PRAGMA table_info. Matched against complete statements as
# yielded by _iter_sql_statements (trailing ';' optional).
_ALTER_ADD_COLUMN_RE = re.compile(
    r"\s*ALTER\s+TABLE\s+(?P<table>\w+)\s+ADD\s+(?:COLUMN\s+)?"
    r"(?P<column>\w+)\s+(?P<type>.+?);?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _safe_alter_add_column(conn: sqlite3.Connection, table: str,
                            column: str, type_sql: str) -> None:
    """Idempotent ALTER TABLE ADD COLUMN. SQLite has no IF NOT EXISTS for
    ALTER syntax, so we gate the statement on PRAGMA table_info first --
    a half-applied migration re-running on the next boot is a no-op."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
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


# --------------------------------------------------------------------------
# FTS query sanitisation
# --------------------------------------------------------------------------
_FTS_TERM_RE = re.compile(r"[A-Za-z0-9_]+")


def _fts_query(raw: str) -> str:
    """Turn an arbitrary user string into a safe FTS5 MATCH expression.

    FTS5 MATCH has its own grammar (quotes, NEAR, column filters, ``*``),
    and a raw user string can be a syntax error. We extract bare word
    tokens, quote each one, and AND them together. A trailing ``*`` is kept
    on the last token for prefix matching so partial words still hit."""
    terms = _FTS_TERM_RE.findall(raw or "")
    if not terms:
        return ""
    quoted = [f'"{t}"' for t in terms]
    # Prefix-match the final term so "hook" matches "hooks".
    quoted[-1] = quoted[-1][:-1] + '"*'
    return " ".join(quoted)


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


def _entity_deep_link(video_id: str, seconds) -> str:
    """A timestamped watch URL for an entity mention. Mirrors server.py's
    _youtube_deep_link; duplicated here so index.py stays self-contained."""
    vid = (video_id or "").strip()
    try:
        t = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        t = 0
    return f"https://youtube.com/watch?v={vid}&t={t}s"


# --------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------
class Index:
    """Connection wrapper around index.db. Thread-safe: every public method
    serialises through a single re-entrant lock, which keeps SQLite write
    semantics simple for the helper's many worker threads.

    Open with ``Index.open(path)`` (runs migrations) or
    ``Index.open_or_recover(path)`` (also handles a corrupt file). The
    instance is usable as a context manager."""

    def __init__(self, conn: sqlite3.Connection, path: Path):
        self._conn = conn
        self._path = path
        self._lock = threading.RLock()
        self._insert_count = 0

    # ---- lifecycle -------------------------------------------------------
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
            _run_migrations(conn)
        except Exception:
            conn.close()
            raise
        return cls(conn, path)

    @classmethod
    def open_or_recover(cls, path) -> tuple["Index", bool]:
        """Like ``open``, but if the file is a corrupt SQLite database, rename
        it aside (``index.db.corrupt-<ts>``) and start fresh.

        Returns ``(index, recovered)`` where ``recovered`` is True if the old
        file had to be quarantined -- the caller should then trigger a full
        backfill scan and surface ``index_recovering`` in /health."""
        path = Path(path)
        try:
            return cls.open(path), False
        except sqlite3.DatabaseError:
            log.error("index.db is corrupt or unreadable -- quarantining and "
                      "rebuilding from disk")
            if path.exists():
                quarantine = path.with_name(
                    f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"
                )
                try:
                    path.replace(quarantine)
                    log.error("corrupt index quarantined at %s", quarantine)
                except OSError:
                    log.exception("could not rename corrupt index; deleting")
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        log.exception("could not delete corrupt index either")
            # WAL/shm siblings of the corrupt file would poison the new DB.
            for suffix in ("-wal", "-shm"):
                sibling = path.with_name(path.name + suffix)
                try:
                    sibling.unlink(missing_ok=True)
                except OSError:
                    pass
            return cls.open(path), True

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "Index":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- yoinks ----------------------------------------------------------
    def upsert_yoink(self, record: dict, *, content: str = "") -> None:
        """Insert or update one yoink row, and refresh its FTS5 entry.

        ``record`` carries the ``yoinks`` columns. ``content`` is the corpus
        text indexed for full-text search (not stored in the yoinks table)."""
        video_id = record.get("video_id")
        if not video_id:
            raise ValueError("upsert_yoink: record requires a video_id")
        values = [record.get(col) for col in _YOINK_COLUMNS]
        placeholders = ", ".join("?" * len(_YOINK_COLUMNS))
        update_set = ", ".join(
            f"{col}=excluded.{col}" for col in _YOINK_COLUMNS if col != "video_id"
        )
        with self._lock:
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
            self._conn.commit()

    def delete_yoink(self, video_id: str) -> None:
        """Delete a yoink and its citations (FK cascade) and FTS row."""
        with self._lock:
            self._conn.execute("DELETE FROM yoinks WHERE video_id=?", (video_id,))
            self._conn.execute("DELETE FROM yoinks_fts WHERE video_id=?", (video_id,))
            self._conn.commit()

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

    def search(self, query: str, limit: int = 10, *,
               channel: str | None = None,
               hook_type: str | None = None) -> list[dict]:
        """Full-text search across indexed corpora. Returns yoink rows ranked
        by FTS5 bm25 (best first), optionally filtered by channel/hook_type."""
        match = _fts_query(query)
        if not match:
            return []
        # snippet() column index 6 == the `content` column of yoinks_fts
        # (0:video_id 1:slug 2:channel 3:title 4:topic 5:hook_type 6:content).
        # Each result row carries `_snippet` (a match excerpt) and `_score`
        # (bm25; lower is a better match) alongside the yoinks columns.
        sql = ("SELECT y.*, "
               "snippet(yoinks_fts, 6, '', '', '…', 12) AS _snippet, "
               "bm25(yoinks_fts) AS _score "
               "FROM yoinks_fts f "
               "JOIN yoinks y ON y.video_id = f.video_id "
               "WHERE yoinks_fts MATCH ? AND y.deleted_at IS NULL ")
        params: list = [match]
        if channel:
            sql += "AND y.channel = ? "
            params.append(channel)
        if hook_type:
            sql += "AND y.hook_type = ? "
            params.append(hook_type)
        sql += "ORDER BY bm25(yoinks_fts) LIMIT ?"
        params.append(max(1, int(limit)))
        with self._lock:
            try:
                rows = self._conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                # Defensive: a MATCH expression FTS5 still rejects.
                log.warning("FTS search rejected query %r", query)
                return []
        return [dict(r) for r in rows]

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

    # ---- memory / soft delete (Sprint 18) -------------------------------
    def search_yoinks_for_memory(self, *, q: str | None = None,
                                 channel: str | None = None,
                                 topic: str | None = None,
                                 hook_type: str | None = None,
                                 date_from: str | None = None,
                                 date_to: str | None = None,
                                 limit: int = 50,
                                 offset: int = 0) -> dict:
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

        match = _fts_query(q) if q else ""
        with self._lock:
            try:
                if match:
                    tail = ("FROM yoinks_fts f "
                            "JOIN yoinks y ON y.video_id = f.video_id "
                            "WHERE yoinks_fts MATCH ? AND " + where)
                    cnt = self._conn.execute(
                        "SELECT COUNT(*) AS n " + tail, [match] + params
                    ).fetchone()
                    total = int(cnt["n"]) if cnt else 0
                    rows = self._conn.execute(
                        "SELECT y.* " + tail
                        + " ORDER BY bm25(yoinks_fts) LIMIT ? OFFSET ?",
                        [match] + params + [limit, offset],
                    ).fetchall()
                elif q:
                    # q was given but yielded no usable FTS terms.
                    return {"total": 0, "results": []}
                else:
                    cnt = self._conn.execute(
                        "SELECT COUNT(*) AS n FROM yoinks y WHERE " + where,
                        params,
                    ).fetchone()
                    total = int(cnt["n"]) if cnt else 0
                    rows = self._conn.execute(
                        "SELECT y.* FROM yoinks y WHERE " + where
                        + " ORDER BY y.yoinked_at DESC LIMIT ? OFFSET ?",
                        params + [limit, offset],
                    ).fetchall()
            except sqlite3.OperationalError:
                # Defensive: a MATCH expression FTS5 still rejects.
                log.warning("memory search rejected query %r", q)
                return {"total": 0, "results": []}
        return {"total": total, "results": [dict(r) for r in rows]}

    def soft_delete_yoink(self, video_id: str) -> dict | None:
        """Mark a yoink soft-deleted (deleted_at = now). Returns the updated
        row, or None if there is no such yoink."""
        with self._lock:
            self._conn.execute(
                "UPDATE yoinks SET deleted_at=? WHERE video_id=?",
                (_now_iso(), video_id),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM yoinks WHERE video_id=?", (video_id,)
            ).fetchone()
        return dict(row) if row else None

    def restore_yoink(self, video_id: str) -> dict | None:
        """Clear a yoink's deleted_at. Returns the updated row, or None."""
        with self._lock:
            self._conn.execute(
                "UPDATE yoinks SET deleted_at=NULL WHERE video_id=?",
                (video_id,),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM yoinks WHERE video_id=?", (video_id,)
            ).fetchone()
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
    def enqueue_pending(self, url: str, interval: int,
                        retry_after: str) -> int:
        """Add a rate-limited URL to the queue with status='pending' and
        attempt_count=0. Returns the new pending_id."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO pending_yoinks "
                "(url, interval_seconds, queued_at, retry_after, "
                " attempt_count, status) "
                "VALUES (?, ?, ?, ?, 0, 'pending')",
                (url, int(interval or 30), _now_iso(), retry_after),
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

    def mark_pending_running(self, pending_id: int) -> None:
        """Mark a pending row in flight. The retry worker calls this before
        the actual extract so a parallel call to next_pending won't pick the
        same row twice."""
        with self._lock:
            self._conn.execute(
                "UPDATE pending_yoinks SET status='running' WHERE pending_id=?",
                (pending_id,),
            )
            self._conn.commit()

    def mark_pending_succeeded(self, pending_id: int,
                                succeeded_job_id: str) -> None:
        """Mark a pending row terminally succeeded and record the resulting
        single-extract job_id (so the UI can deep-link to the result)."""
        with self._lock:
            self._conn.execute(
                "UPDATE pending_yoinks "
                "SET status='succeeded', succeeded_job_id=? "
                "WHERE pending_id=?",
                (succeeded_job_id, pending_id),
            )
            self._conn.commit()

    def mark_pending_failed(self, pending_id: int, error: str,
                             retry_after: str, *,
                             force_final: bool = False) -> None:
        """Record one failed attempt. Increments attempt_count, then either
        re-queues with the supplied retry_after (status='pending') if under
        the strike cap, or marks the row terminally 'failed' (when the cap
        is reached, or when force_final=True for non-recoverable errors).
        No-op for an unknown pending_id."""
        with self._lock:
            row = self._conn.execute(
                "SELECT attempt_count FROM pending_yoinks WHERE pending_id=?",
                (pending_id,),
            ).fetchone()
            if row is None:
                return
            attempts = (row["attempt_count"] or 0) + 1
            if force_final or attempts >= _PENDING_MAX_ATTEMPTS:
                self._conn.execute(
                    "UPDATE pending_yoinks "
                    "SET status='failed', attempt_count=?, last_error=? "
                    "WHERE pending_id=?",
                    (attempts, error, pending_id),
                )
            else:
                self._conn.execute(
                    "UPDATE pending_yoinks "
                    "SET status='pending', attempt_count=?, last_error=?, "
                    "    retry_after=? "
                    "WHERE pending_id=?",
                    (attempts, error, retry_after, pending_id),
                )
            self._conn.commit()

    def cancel_pending(self, pending_id: int) -> bool:
        """Mark a pending row terminally cancelled. Returns True when a row
        actually changed (False for unknown / already-terminal rows)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE pending_yoinks SET status='cancelled' "
                "WHERE pending_id=? AND status NOT IN ('succeeded','failed','cancelled')",
                (pending_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def retry_pending_now(self, pending_id: int) -> bool:
        """User-initiated 'try this one now': bumps retry_after to now and,
        for a 'failed' row, flips it back to 'pending'. No-op for
        'succeeded' / 'cancelled' rows. Returns True when a row changed."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE pending_yoinks "
                "SET status='pending', retry_after=? "
                "WHERE pending_id=? AND status IN ('pending','failed','running')",
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
        the retry worker picks it up again. Returns the count reset."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE pending_yoinks SET status='pending', retry_after=? "
                "WHERE status='running'",
                (_now_iso(),),
            )
            self._conn.commit()
            return cur.rowcount

    # ---- citations -------------------------------------------------------
    def insert_citations(self, video_id: str, citations: list[dict]) -> int:
        """Bulk insert citation rows. Idempotent per (video_id, kind, seq):
        re-yoinking a video rewrites its rows via INSERT OR REPLACE. Returns
        the number of rows written."""
        rows = [
            (video_id, c.get("kind"), c.get("seq"),
             c.get("timestamp_start"), c.get("timestamp_end"),
             c.get("text"), c.get("file_path"), c.get("youtube_deep_link"))
            for c in citations
        ]
        if not rows:
            return 0
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO citations "
                "(video_id, kind, seq, timestamp_start, timestamp_end, "
                " text, file_path, youtube_deep_link) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()
        return len(rows)

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
        with self._lock:
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

    def prune_jobs(self, keep_terminal: int = 200) -> int:
        """Keep at most ``keep_terminal`` most-recent terminal jobs; non-
        terminal jobs (pending/running) are always retained. Returns the
        number of rows deleted."""
        placeholders = ", ".join("?" * len(_TERMINAL_JOB_STATES))
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM jobs WHERE status IN ({placeholders}) "
                f"AND job_id NOT IN ("
                f"  SELECT job_id FROM jobs WHERE status IN ({placeholders}) "
                f"  ORDER BY updated_at DESC LIMIT ?"
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
        with self._lock:
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

    def find_mentions(self, name: str, limit: int = 50) -> list[dict]:
        """Every recorded mention of an entity, newest first.

        Matches on the normalised name (case/punctuation-insensitive) across
        every type the name was tagged as, joining through to the yoink for
        its slug/title/channel. Each row carries a timestamped deep link.
        Soft-deleted yoinks are excluded. Returns [] for an unknown entity."""
        norm = normalize_entity_name(name)
        if not norm:
            return []
        sql = (
            "SELECT y.video_id AS video_id, y.slug AS slug, y.title AS title, "
            "       y.channel AS channel, em.source AS source, "
            "       em.timestamp AS timestamp, em.context AS context "
            "FROM entity_mentions em "
            "JOIN entities e ON e.entity_id = em.entity_id "
            "JOIN yoinks   y ON y.video_id  = em.video_id "
            "WHERE e.name_normalized = ? AND y.deleted_at IS NULL "
            "ORDER BY em.mention_id DESC LIMIT ?"
        )
        with self._lock:
            rows = self._conn.execute(sql, (norm, max(1, int(limit)))).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["deep_link"] = _entity_deep_link(d.get("video_id"), d.get("timestamp"))
            out.append(d)
        return out

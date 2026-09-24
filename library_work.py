"""Living Library service. No model, network, or client-process execution.

Adapters pass RequestContext (constructed after authentication) and JSON arguments
to LibraryWorkService. Only a local confirmation route may grant user authority.
Use an explicit store_root for tests; the default is next to the index database.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from pathlib import Path

import library_cards

CONTRACT_VERSION = "phase2-v1.2-2026-09-04"
SCHEMA_VERSION = 1
CLAIM_BYTE_BUDGET = 122880
TAXONOMY_BYTE_BUDGET = 16384
_MISSING = object()


class LibraryError(Exception):
    def __init__(self, code, message, *, retryable=False, **details):
        super().__init__(message)
        self.response = dict(ok=False, schema_version=1, error=dict(
            code=code, message=message, retryable=retryable, details=details))


def fail(code, message, **details):
    raise LibraryError(code, message, **details)


def success(**values):
    return {"ok": True, "schema_version": 1, **values}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("validation_error", "Duplicate JSON key", field=key)
        result[key] = value
    return result


def decode_json(raw):
    """The sole transport decoder; rejects duplicates and non-finite numbers."""
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: fail("validation_error", "Non-finite number"))
    except (ValueError, TypeError, RecursionError):
        fail("validation_error", "Invalid JSON")


def _json(value, depth=0):
    if depth > 30:
        fail("validation_error", "JSON nesting limit exceeded")
    if value is None or type(value) in (str, bool, int):
        if type(value) is int and not -(2**63) <= value < 2**63:
            fail("validation_error", "Integer is outside supported range")
        if type(value) is str:
            try:
                value.encode("utf-8")
            except UnicodeError:
                fail("validation_error", "Invalid Unicode")
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for child in value:
            _json(child, depth + 1)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for key, child in value.items():
            _json(key, depth + 1)
            _json(child, depth + 1)
        return
    fail("validation_error", "Expected finite JSON values")


def _check(value, schema, defs, field="arguments"):
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        _check(value, defs[name], defs, field)
        if name in {"id", "client", "key"} and (
                value != value.strip() or any(ord(c) < 32 for c in value)):
            fail("validation_error", "Malformed identifier", field=field)
        return
    if "oneOf" in schema:
        count = 0
        for branch in schema["oneOf"]:
            try:
                _check(value, branch, defs, field)
                count += 1
            except LibraryError:
                pass
        if count != 1:
            fail("validation_error", "Value must match one allowed shape", field=field)
        return
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    if kind in types and type(value) is not types[kind]:
        fail("validation_error", "Unexpected value type", field=field)
    if kind == "number" and (type(value) not in (int, float) or (type(value) is float and not math.isfinite(value))):
        fail("validation_error", "Expected finite number", field=field)
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        fail("validation_error", "Unexpected constant", field=field)
    if "enum" in schema and value not in schema["enum"]:
        fail("validation_error", "Unexpected choice", field=field)
    if kind == "object":
        props = schema.get("properties", {})
        if set(schema.get("required", [])) - value.keys():
            fail("validation_error", "Missing fields", field=field)
        if schema.get("additionalProperties") is False and value.keys() - props.keys():
            fail("validation_error", "Unknown fields", field=field)
        for key, child in value.items():
            if key in props:
                _check(child, props[key], defs, field + "." + key)
    if kind in {"array", "string"}:
        lo, hi = ("minItems", "maxItems") if kind == "array" else ("minLength", "maxLength")
        if len(value) < schema.get(lo, 0) or len(value) > schema.get(hi, 2**31):
            fail("validation_error", "Invalid length", field=field)
        if kind == "array":
            for i, child in enumerate(value):
                _check(child, schema["items"], defs, f"{field}[{i}]")
        elif "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            fail("validation_error", "Invalid format", field=field)
    if kind in {"integer", "number"}:
        if not schema.get("minimum", -math.inf) <= value <= schema.get("maximum", math.inf):
            fail("validation_error", "Number out of range", field=field)


def validate_arguments(tool, args):
    _json(args)
    schema = _SCHEMAS[tool]
    _check(args, schema, schema["$defs"])
    return copy.deepcopy(args)


@dataclass(frozen=True)
class RequestContext:
    authenticated: bool = False
    client_id: str | None = None
    session_id: str | None = None
    operator: bool = False
    local_user_confirmed: bool = False


def endpoint(fn):
    @wraps(fn)
    def call(self, context, args=_MISSING):
        try:
            if not isinstance(context, RequestContext) or context.authenticated is not True:
                fail("unauthorized", "Authenticated request context required")
            args = {} if args is _MISSING else args
            if isinstance(args, (str, bytes)):
                args = decode_json(args)
            _json(args)
            if type(args) is not dict:
                fail("validation_error", "Arguments must be an object")
            return fn(self, context, copy.deepcopy(args))
        except LibraryError as exc:
            if exc.response["error"]["code"] == "recovery_pending" and getattr(self, "_pending_record", None):
                self._mark_pending()
            return exc.response
        except (sqlite3.Error, OSError):
            if getattr(self, "_pending_record", None):
                self._mark_pending()
                return LibraryError("recovery_pending", "Operation is durable; replay is required", retryable=True).response
            return LibraryError("storage_error", "Library storage is unavailable", retryable=True).response
    return call


def _fields(args, required, optional=()):
    if set(required) - args.keys() or args.keys() - set(required) - set(optional):
        fail("validation_error", "Missing or unknown fields")


def _id(value):
    _check(value, {"$ref": "#/$defs/id"}, _SCHEMAS["list_library_work"]["$defs"])
    return value


def _operator(context):
    if context.operator is not True:
        fail("forbidden", "Trusted local operator required")


def _owner(context, args):
    if not context.client_id or context.client_id != args["client_id"]:
        fail("forbidden", "Client does not match authenticated owner")


_STORE_LOCKS = {}
_STORE_LOCKS_GUARD = threading.Lock()


class LibraryWorkService:
    def __init__(self, index, store_root=None, *, clock=None,
                 librarian_apply_enabled=False, crash_hook=None, event_hook=None):
        self.index = index
        self.store_root = Path(store_root) if store_root is not None else index._path.parent / "library"
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.librarian_apply_enabled = librarian_apply_enabled is True
        self.crash_hook = crash_hook or (lambda boundary: None)
        self.event_hook = event_hook or (lambda kind, **kwargs: None)
        self._pending_record = None
        with _STORE_LOCKS_GUARD:
            self._store_lock = _STORE_LOCKS.setdefault(str(self.store_root.resolve()), threading.RLock())
        index._library_work_service = self
        self.startup_status = success(recovery_state="ready")
        with index._lock:
            checkpoint = self._meta(index._conn)["last_operation_sequence"]
        if checkpoint or (self.store_root / "journal").exists() or (self.store_root / "taxonomies").exists() or (self.store_root / "pins.json").exists():
            self.startup_status = self.recover_operations(RequestContext(authenticated=True, operator=True), {})

    def _now(self):
        return int(self.clock())

    def _emit_mirror_event(self, kind, **kwargs):
        """One-line corpus-mirror seam. Default event_hook is a no-op."""
        try:
            self.event_hook(kind, **kwargs)
        except Exception:
            return

    def _stamp(self):
        return str(self._now())

    @staticmethod
    def _rules(policy):
        return {key: policy[key] for key in ("min_confidence", "max_memberships", "max_churn_percent",
                                             "prompt_hash", "selection_version", "card_schema")}

    @staticmethod
    def _manifest_hash(entries, exclusions):
        return digest(dict(items=[[entry["video_id"], entry["source_revision"]] for entry in entries],
                           exclusions=exclusions))

    def _run(self, conn, run_id):
        row = conn.execute("SELECT * FROM library_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            fail("not_found", "Run not found")
        return dict(row)

    def _meta(self, conn):
        return dict(conn.execute("SELECT * FROM library_meta WHERE singleton=1").fetchone())

    def _ready(self, conn):
        state = self._meta(conn)["recovery_state"]
        if state != "ready":
            fail("recovery_conflict" if state == "conflict" else "recovery_pending",
                 "Recover authoritative records before mutation", retryable=state == "pending")

    def _card(self, conn, video_id, profile="librarian"):
        row = conn.execute("SELECT * FROM yoinks WHERE video_id=? AND deleted_at IS NULL", (video_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        clips = [dict(c) for c in conn.execute("SELECT * FROM clips WHERE video_id=? ORDER BY seq", (video_id,))]
        return library_cards.build_card(item, clips, profile=profile,
            corpus_text=library_cards.read_corpus_head(item.get("corpus_path")))

    def _taxonomy(self, conn, version_id):
        row = conn.execute("SELECT * FROM shelf_versions WHERE version_id=?", (version_id,)).fetchone()
        if row is None or row["status"] not in {"approved", "active", "superseded"}:
            fail("taxonomy_conflict", "Approved taxonomy required")
        path = self.store_root / "taxonomies" / (row["revision_hash"] + ".json")
        if not path.is_file():
            fail("recovery_pending", "Authoritative taxonomy is missing")
        try:
            taxonomy = decode_json(path.read_bytes())
            if digest(taxonomy["nodes"]) != row["revision_hash"] or taxonomy["version_id"] != version_id:
                fail("recovery_conflict", "Authoritative taxonomy hash mismatch")
        except (KeyError, TypeError, ValueError, LibraryError):
            fail("recovery_conflict", "Corrupt authoritative taxonomy")
        actual = [dict(shelf_id=n["shelf_id"], parent_shelf_id=n["parent_shelf_id"], name=n["name"],
            path=decode_json(n["path_json"]), definition=n["definition"], include=decode_json(n["include_json"]),
            exclude=decode_json(n["exclude_json"]), retired=bool(n["retired"])) for n in
            conn.execute("SELECT * FROM shelf_nodes WHERE version_id=?", (version_id,))]
        actual.sort(key=lambda n: (len(n["path"]), n["path"], n["shelf_id"]))
        if actual != taxonomy["nodes"]:
            fail("taxonomy_conflict", "Approved taxonomy projection was altered")
        return taxonomy

    @endpoint
    def approve_taxonomy(self, context, args):
        _operator(context)
        _fields(args, ("version_id", "nodes"), ("parent_version_id",))
        _id(args["version_id"])
        nodes = args["nodes"]
        if type(nodes) is not list or not nodes:
            fail("validation_error", "Taxonomy requires nodes")
        ids, paths = set(), set()
        normalized = []
        for node in nodes:
            if type(node) is not dict:
                fail("validation_error", "Invalid shelf node")
            _fields(node, ("shelf_id", "path", "definition", "include", "exclude"),
                    ("name", "parent_shelf_id", "retired"))
            _id(node["shelf_id"])
            path = node["path"]
            if type(path) is not list or not 1 <= len(path) <= 3 or any(
                    type(p) is not str or not p.strip() or p != p.strip() or len(p) > 100 for p in path):
                fail("validation_error", "Shelf path requires 1-3 nonempty segments")
            path = [unicodedata.normalize("NFC", p) for p in path]
            if node["shelf_id"] in ids or tuple(path) in paths:
                fail("validation_error", "Duplicate shelf identity or path")
            if type(node["definition"]) is not str or not node["definition"].strip():
                fail("validation_error", "Shelf definition required")
            for key in ("include", "exclude"):
                if type(node[key]) is not list or any(type(v) is not str or not v.strip() for v in node[key]):
                    fail("validation_error", "Cues must be arrays of nonempty strings")
            if "retired" in node and type(node["retired"]) is not bool:
                fail("validation_error", "Retired must be boolean")
            if node.get("name", path[-1]) != path[-1]:
                fail("validation_error", "Shelf name must match path")
            ids.add(node["shelf_id"])
            paths.add(tuple(path))
            normalized.append(dict(node, path=path, name=path[-1], retired=node.get("retired", False)))
        by_path = {tuple(n["path"]): n["shelf_id"] for n in normalized}
        for node in normalized:
            parent = by_path.get(tuple(node["path"][:-1])) if len(node["path"]) > 1 else None
            if len(node["path"]) > 1 and parent is None:
                fail("validation_error", "Parent shelf is missing")
            if node.get("parent_shelf_id", parent) != parent:
                fail("validation_error", "Parent does not match path")
            node["parent_shelf_id"] = parent
        normalized.sort(key=lambda n: (len(n["path"]), n["path"], n["shelf_id"]))
        taxonomy = dict(schema_version=1, version_id=args["version_id"], nodes=normalized,
                        parent_version_id=args.get("parent_version_id"), revision_hash=digest(normalized))
        if len(canonical(taxonomy).encode()) > TAXONOMY_BYTE_BUDGET:
            fail("packet_too_large", "Taxonomy exceeds 16384 bytes")
        if taxonomy["parent_version_id"] is not None:
            _id(taxonomy["parent_version_id"])
        with self._locked_store(), self.index.write_transaction() as conn:
            self._ready(conn)
            old = conn.execute("SELECT revision_hash FROM shelf_versions WHERE version_id=?", (args["version_id"],)).fetchone()
            if old:
                if self._taxonomy(conn, args["version_id"]) != taxonomy:
                    fail("taxonomy_conflict", "Approved revisions are immutable")
                return success(**taxonomy)
            if taxonomy["parent_version_id"] is not None:
                self._taxonomy(conn, taxonomy["parent_version_id"])
            if conn.execute("SELECT 1 FROM shelf_versions WHERE revision_hash=?", (taxonomy["revision_hash"],)).fetchone():
                fail("taxonomy_conflict", "Definitions already have an approved version identity")
            self._publish_taxonomy(taxonomy)
            self._load_taxonomy(conn, taxonomy, context.session_id or context.client_id or "operator")
        return success(**taxonomy)

    def _load_taxonomy(self, conn, taxonomy, actor="recovery"):
        version = taxonomy["version_id"]
        old = conn.execute("SELECT revision_hash FROM shelf_versions WHERE version_id=?", (version,)).fetchone()
        if old:
            if old[0] != taxonomy["revision_hash"]:
                fail("recovery_conflict", "Taxonomy identity collision")
            return
        conn.execute("INSERT INTO shelf_versions VALUES(?,?,?,?,?,?,?)", (version,
            taxonomy.get("parent_version_id"), taxonomy["revision_hash"], "approved", self._stamp(), actor, self._stamp()))
        for node in taxonomy["nodes"]:
            conn.execute("INSERT OR IGNORE INTO shelves VALUES(?,?)", (node["shelf_id"], self._stamp()))
            conn.execute("INSERT INTO shelf_nodes VALUES(?,?,?,?,?,?,?,?,?)", (version, node["shelf_id"],
                node["parent_shelf_id"], node["name"], canonical(node["path"]), node["definition"],
                canonical(node["include"]), canonical(node["exclude"]), int(node["retired"])))

    @endpoint
    def prepare_run(self, context, args):
        _operator(context)
        _fields(args, ("run_id", "version_id", "video_ids", "prompt_hash"),
                ("exclusions", "previous_run_id", "reason", "policy"))
        _id(args["run_id"])
        _id(args["version_id"])
        _check(args["prompt_hash"], {"$ref": "#/$defs/hash"}, _SCHEMAS["list_library_work"]["$defs"])
        targets = args["video_ids"]
        if type(targets) is not list or not targets:
            fail("validation_error", "A nonempty target manifest is required")
        for video_id in targets:
            _id(video_id)
        if len(set(targets)) != len(targets):
            fail("validation_error", "Duplicate target identity")
        exclusions = args.get("exclusions", {})
        if type(exclusions) is not dict or exclusions.keys() - set(targets):
            fail("validation_error", "Exclusions must name target identities")
        for value in exclusions.values():
            if type(value) is not str or not value.strip() or len(value) > 500:
                fail("validation_error", "Exclusion reason required")
        if args.get("policy", {}) != {}:
            fail("validation_error", "This contract uses fixed server policy")
        if "previous_run_id" in args:
            _id(args["previous_run_id"])
            if type(args.get("reason")) is not str or not args["reason"].strip():
                fail("validation_error", "Operator retry requires a reason")
        with self.index.write_transaction() as conn:
            self._ready(conn)
            taxonomy = self._taxonomy(conn, args["version_id"])
            if "previous_run_id" in args:
                self._run(conn, args["previous_run_id"])
            if conn.execute("SELECT 1 FROM library_runs WHERE run_id=?", (args["run_id"],)).fetchone():
                fail("idempotency_conflict", "Run identity already exists")
            policy = dict(min_confidence=0.60, max_memberships=3, max_churn_percent=15,
                prompt_hash=args["prompt_hash"], selection_version=library_cards.SELECTION_VERSION,
                card_schema=1, previous_run_id=args.get("previous_run_id"), reason=args.get("reason"),
                exclusions=exclusions, manifest_order=targets)
            entries = []
            for video_id in targets:
                card = self._card(conn, video_id)
                pinned = conn.execute("SELECT 1 FROM item_shelves WHERE video_id=? AND locked=1", (video_id,)).fetchone()
                disposition = "deleted" if card is None else "pinned" if pinned else "unsupported" if video_id in exclusions else "waiting"
                entries.append(dict(video_id=video_id, source_revision=card["source_revision"] if card else "0" * 64,
                    disposition=disposition, reason=exclusions.get(video_id), card=card))
            policy["corpus_head_hashes"] = {}
            for entry in entries:
                row = conn.execute("SELECT corpus_path FROM yoinks WHERE video_id=?", (entry["video_id"],)).fetchone()
                head = library_cards.read_corpus_head(row[0]) if row else ""
                policy["corpus_head_hashes"][entry["video_id"]] = hashlib.sha256(head.encode()).hexdigest()
            manifest_hash = self._manifest_hash(entries, exclusions)
            conn.execute("INSERT INTO library_runs VALUES(?,?,?,?,?,?,?)", (args["run_id"], args["version_id"],
                manifest_hash, 1, "collecting", canonical(policy), self._stamp()))
            for entry in entries:
                conn.execute("INSERT INTO library_manifest VALUES(?,?,?,?,?)", (args["run_id"], entry["video_id"],
                    entry["source_revision"], entry["disposition"], entry["reason"]))
                packet = dict(schema_version=1, video_id=entry["video_id"], source_revision=entry["source_revision"],
                    taxonomy_revision=taxonomy["revision_hash"], policy_hash=digest(self._rules(policy)), card=entry["card"])
                state = "ready" if entry["disposition"] == "waiting" else "unsupported" if entry["disposition"] == "unsupported" else "blocked"
                conn.execute("INSERT INTO library_work(work_id,run_id,video_id,packet_json,packet_hash,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (secrets.token_urlsafe(24), args["run_id"], entry["video_id"], canonical(packet), digest(packet), state, self._stamp(), self._stamp()))
        return success(run_id=args["run_id"], run_revision=1, manifest_hash=manifest_hash, target_count=len(entries))

    def _invalidate(self, conn, work, disposition, reason):
        conn.execute("UPDATE library_attempts SET state='invalidated' WHERE work_id=? AND state='current'", (work["work_id"],))
        conn.execute("DELETE FROM library_proposals WHERE run_id=? AND video_id=?", (work["run_id"], work["video_id"]))
        conn.execute("UPDATE library_work SET state='blocked',updated_at=? WHERE work_id=?", (self._stamp(), work["work_id"]))
        conn.execute("UPDATE library_manifest SET disposition=?,reason=? WHERE run_id=? AND video_id=?",
                     (disposition, reason, work["run_id"], work["video_id"]))
        conn.execute("UPDATE library_runs SET run_revision=run_revision+1 WHERE run_id=?", (work["run_id"],))
        conn.execute("DELETE FROM library_previews WHERE run_id=?", (work["run_id"],))

    def _fresh(self, conn, work):
        packet = decode_json(work["packet_json"])
        card = self._card(conn, work["video_id"])
        run = self._run(conn, work["run_id"])
        taxonomy = self._taxonomy(conn, run["version_id"])
        if card is None:
            self._invalidate(conn, work, "deleted", "Source item deleted")
            return False
        if card["source_revision"] != packet["source_revision"] or taxonomy["revision_hash"] != packet["taxonomy_revision"]:
            self._invalidate(conn, work, "changed", "Frozen input changed")
            return False
        if conn.execute("SELECT 1 FROM item_shelves WHERE video_id=? AND locked=1", (work["video_id"],)).fetchone():
            self._invalidate(conn, work, "pinned", "User membership is preserved")
            return False
        return True

    def _expire(self, conn):
        rows = conn.execute("SELECT a.*,w.attempts FROM library_attempts a JOIN library_work w USING(work_id) WHERE a.state='current' AND a.lease_expires_ms<=?", (self._now(),)).fetchall()
        for row in rows:
            conn.execute("UPDATE library_attempts SET state='expired' WHERE attempt_token=?", (row["attempt_token"],))
            conn.execute("UPDATE library_work SET state=?,updated_at=? WHERE work_id=?",
                ("ready" if row["attempts"] < 3 else "blocked", self._stamp(), row["work_id"]))
        return len(rows)

    @endpoint
    def expire_attempts(self, context, args):
        _operator(context)
        _fields(args, ())
        with self.index.write_transaction() as conn:
            self._ready(conn)
            return success(expired=self._expire(conn))

    @endpoint
    def list_work(self, context, args):
        args = validate_arguments("list_library_work", args)
        with self.index.write_transaction() as conn:
            try:
                self._ready(conn)
            except LibraryError as exc:
                if exc.response["error"]["code"] not in {"recovery_pending", "recovery_conflict"}:
                    raise
                # Recovery freezes leases, but their stored status remains visible.
            else:
                self._expire(conn)
            clauses, params = [], []
            if "run_id" in args:
                clauses.append("run_id=?")
                params.append(args["run_id"])
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            counts = {r[0]: r[1] for r in conn.execute("SELECT state,COUNT(*) FROM library_work" + where + " GROUP BY state", params)}
            dispositions = {r[0]: r[1] for r in conn.execute("SELECT disposition,COUNT(*) FROM library_manifest" + where + " GROUP BY disposition", params)}
            if args.get("state", "all") != "all":
                clauses.append("state=?")
                params.append(args["state"])
            if "cursor" in args:
                clauses.append("work_id>?")
                params.append(args["cursor"])
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            limit = args.get("limit", 25)
            items = [dict(r) for r in conn.execute("SELECT work_id,run_id,video_id,state,attempts,packet_generation FROM library_work" + where + " ORDER BY work_id LIMIT ?", params + [limit + 1])]
            revision = self._run(conn, args["run_id"])["run_revision"] if "run_id" in args else None
            return success(contract_version=CONTRACT_VERSION, run_revision=revision,
                counts=counts, manifest_counts=dispositions, items=items[:limit],
                next_cursor=items[limit - 1]["work_id"] if len(items) > limit else None,
                waiting_for_client=bool(counts.get("ready", 0) and not counts.get("leased", 0)),
                recovery_state=self._meta(conn)["recovery_state"])

    @endpoint
    def claim_work(self, context, args):
        args = validate_arguments("claim_library_work", args)
        _owner(context, args)
        if args["action"] != "claim":
            return {"renew": self.renew_attempt, "release": self.release_attempt, "cancel": self.cancel_attempt}[args["action"]](context, args)
        with self.index.write_transaction() as conn:
            self._ready(conn)
            self._expire(conn)
            run = self._run(conn, args["run_id"])
            taxonomy = self._taxonomy(conn, run["version_id"])
            response = success(work=[], taxonomy=taxonomy, rules=decode_json(run["policy_json"]), blocked=[])
            # Corpus hashes and exclusion reasons are run metadata, not prompt rules.
            response["rules"] = self._rules(response["rules"])
            rows = conn.execute("SELECT * FROM library_work WHERE run_id=? AND state='ready' AND attempts<3 ORDER BY priority,created_at,work_id", (args["run_id"],)).fetchall()
            for raw in rows:
                work = dict(raw)
                if len(response["work"]) >= args.get("max_items", 12):
                    break
                if not self._fresh(conn, work):
                    continue
                packet = decode_json(work["packet_json"])
                token = secrets.token_urlsafe(32)
                now = self._now()
                deadline = now + args.get("lease_seconds", 900) * 1000
                claimed = dict(work_id=work["work_id"], video_id=work["video_id"], attempt_token=token,
                    attempt_number=work["attempts"] + 1, lease_expires_ms=deadline, source_revision=packet["source_revision"],
                    taxonomy_revision=packet["taxonomy_revision"], packet_hash=work["packet_hash"], card=packet["card"])
                candidate = dict(response, work=response["work"] + [claimed])
                if len(json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode()) > CLAIM_BYTE_BUDGET:
                    if not response["work"]:
                        self._invalidate(conn, work, "rejected", "packet_too_large")
                        return LibraryError("packet_too_large", "One complete packet exceeds claim budget", work_id=work["work_id"]).response
                    break
                conn.execute("INSERT INTO library_attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (token, work["work_id"],
                    work["attempts"] + 1, work["packet_generation"], args["client_id"], packet["source_revision"],
                    packet["taxonomy_revision"], deadline, now + 3600000, "current"))
                conn.execute("UPDATE library_work SET state='leased',attempts=attempts+1,updated_at=? WHERE work_id=?", (self._stamp(), work["work_id"]))
                response = candidate
            return response

    def _attempt(self, conn, args):
        row = conn.execute("SELECT * FROM library_attempts WHERE attempt_token=? AND work_id=? AND client_id=?",
            (args["attempt_token"], args["work_id"], args["client_id"])).fetchone()
        if row is None or row["state"] != "current" or self._now() >= row["lease_expires_ms"]:
            fail("stale_attempt", "Attempt is no longer current", retryable=True)
        return dict(row)

    def _lease_action(self, context, args, action):
        args = validate_arguments("claim_library_work", args)
        _owner(context, args)
        if args["action"] != action:
            fail("validation_error", "Wrong lease action")
        with self.index.write_transaction() as conn:
            self._ready(conn)
            self._expire(conn)
            try:
                attempt = self._attempt(conn, args)
            except LibraryError as exc:
                return exc.response
            work = dict(conn.execute("SELECT * FROM library_work WHERE work_id=?", (args["work_id"],)).fetchone())
            if not self._fresh(conn, work):
                return LibraryError("stale_attempt", "Frozen input changed", retryable=True).response
            state = "leased"
            deadline = attempt["lease_expires_ms"]
            if action == "renew":
                deadline = min(self._now() + args["lease_seconds"] * 1000, attempt["lease_max_ms"])
                conn.execute("UPDATE library_attempts SET lease_expires_ms=? WHERE attempt_token=?", (deadline, args["attempt_token"]))
            else:
                state = "cancelled" if action == "cancel" else "ready" if work["attempts"] < 3 else "blocked"
                conn.execute("UPDATE library_attempts SET state='cancelled' WHERE attempt_token=?", (args["attempt_token"],))
                conn.execute("UPDATE library_work SET state=?,updated_at=? WHERE work_id=?", (state, self._stamp(), args["work_id"]))
                conn.execute("UPDATE library_manifest SET disposition=?,reason=? WHERE run_id=? AND video_id=?",
                    ("cancelled" if action == "cancel" else "waiting", args["reason"], work["run_id"], work["video_id"]))
            return success(work_id=args["work_id"], state=state, remaining_attempts=3-work["attempts"], lease_expires_ms=deadline)

    @endpoint
    def renew_attempt(self, context, args):
        return self._lease_action(context, args, "renew")

    @endpoint
    def release_attempt(self, context, args):
        return self._lease_action(context, args, "release")

    @endpoint
    def cancel_attempt(self, context, args):
        return self._lease_action(context, args, "cancel")

    def _validate_result(self, conn, args, work):
        schema = _SCHEMAS["submit_library_result"]
        _check(args, schema, schema["$defs"])
        packet = decode_json(work["packet_json"])
        for key, expected in (("video_id", work["video_id"]), ("packet_hash", work["packet_hash"]),
                              ("source_revision", packet["source_revision"]), ("taxonomy_revision", packet["taxonomy_revision"])):
            if args[key] != expected:
                fail("identity_mismatch", "Result does not match frozen packet", field=key)
        result = args["result"]
        if result["outcome"] != "assigned":
            return []
        run = self._run(conn, work["run_id"])
        nodes = {n["shelf_id"]: n for n in self._taxonomy(conn, run["version_id"])["nodes"] if not n["retired"]}
        memberships, seen = [], set()
        for i, membership in enumerate(result["memberships"]):
            shelf_id = membership["shelf_id"]
            if shelf_id in seen or shelf_id not in nodes or nodes[shelf_id]["path"] != membership["shelf_path"]:
                fail("invalid_shelf", "Shelf identity/path is not unique and approved", field=f"result.memberships[{i}]")
            seen.add(shelf_id)
            if membership["confidence"] < .60:
                fail("low_confidence", "Assignment requires confidence at least 0.60", field=f"result.memberships[{i}].confidence")
            evidence = membership["evidence"]
            card = packet["card"] if evidence["basis"] == "packet" else self._card(conn, work["video_id"], "full")
            if card is None or card["source_revision"] != args["source_revision"] or card["card_hash"] != evidence["card_hash"]:
                fail("invalid_evidence", "Evidence card does not match item revision", field="evidence.card_hash")
            excerpt = next((e for e in card["excerpts"] if e["excerpt_id"] == evidence["excerpt_id"]), None)
            normalize = lambda text: " ".join(unicodedata.normalize("NFC", text).split())
            quote = normalize(evidence["quote"])
            if not 1 <= len(quote.split()) <= 24:
                fail("invalid_evidence", "Quote must contain 1 to 24 words after NFC and whitespace normalization",
                     field=f"result.memberships[{i}].evidence.quote")
            if not excerpt or evidence["kind"] != excerpt["evidence_kind"] or not quote or quote not in normalize(excerpt["text"]):
                fail("invalid_evidence", "Quote must occur in one specified excerpt", field="evidence.quote")
            # Description/summary prose cannot be promoted to original source evidence.
            if evidence["kind"] == "text_only" and card.get("source_type") not in {"page", "x_article", "x_thread", "reddit_thread", "note"}:
                fail("unsupported_evidence", "Source origin does not support original-prose evidence", field="evidence.kind")
            memberships.append(dict(membership, evidence=dict(evidence, start=excerpt["start"], end=excerpt["end"],
                timing=excerpt["timing"], truncated=excerpt["truncated"])))
        return memberships

    @endpoint
    def validate_result(self, context, args):
        validate_arguments("submit_library_result", args)
        _owner(context, args)
        with self.index._lock:
            conn = self.index._conn
            row = conn.execute("SELECT * FROM library_work WHERE work_id=?", (args["work_id"],)).fetchone()
            if row is None:
                fail("not_found", "Work not found")
            return success(accepted_memberships=self._validate_result(conn, args, dict(row)))

    @endpoint
    def submit_result(self, context, args):
        # Only an identifiable, well-formed envelope can consume an attempt.
        schema = copy.deepcopy(_SCHEMAS["submit_library_result"])
        schema["properties"]["result"] = {}
        schema["properties"]["usage"] = {}
        _check(args, schema, schema["$defs"])
        _owner(context, args)
        request_hash = digest(args)
        with self.index.write_transaction() as conn:
            receipt = conn.execute("SELECT * FROM library_submissions WHERE submission_key=?", (args["submission_key"],)).fetchone()
            if receipt:
                if receipt["request_hash"] != request_hash:
                    fail("idempotency_conflict", "Submission key already has different content")
                return decode_json(receipt["response_json"])
            consumed = conn.execute("SELECT 1 FROM library_submissions WHERE attempt_token=?", (args["attempt_token"],)).fetchone()
            if consumed:
                fail("idempotency_conflict", "Attempt already submitted")
            self._ready(conn)
            self._expire(conn)
            try:
                self._attempt(conn, args)
            except LibraryError as exc:
                return exc.response
            work = dict(conn.execute("SELECT * FROM library_work WHERE work_id=?", (args["work_id"],)).fetchone())
            if not self._fresh(conn, work):
                return LibraryError("stale_attempt", "Frozen input changed", retryable=True).response
            rejected, memberships = [], []
            try:
                memberships = self._validate_result(conn, args, work)
                outcome = "accepted" if args["result"]["outcome"] == "assigned" else args["result"]["outcome"]
                if outcome == "error":
                    rejected = [dict(code="client_error", field="result", reason=args["result"]["reason"])]
            except LibraryError as exc:
                error = exc.response["error"]
                outcome = "rejected"
                rejected = [dict(code=error["code"], field=error["details"].get("field", "result"), reason=error["message"])]
            retryable = outcome in {"rejected", "error"} and work["attempts"] < 3
            state = ("ready" if retryable else "blocked") if rejected else outcome
            response = success(work_id=work["work_id"], video_id=work["video_id"], outcome=outcome,
                accepted_memberships=memberships, rejected=rejected, retryable=retryable)
            conn.execute("INSERT INTO library_submissions VALUES(?,?,?,?,?,?,?,?)", (args["submission_key"],
                args["attempt_token"], request_hash, outcome, canonical(args["result"]), canonical(response), canonical(args["usage"]), self._stamp()))
            conn.execute("UPDATE library_attempts SET state='submitted' WHERE attempt_token=?", (args["attempt_token"],))
            conn.execute("UPDATE library_work SET state=?,updated_at=? WHERE work_id=?", (state, self._stamp(), work["work_id"]))
            conn.execute("UPDATE library_manifest SET disposition=?,reason=? WHERE run_id=? AND video_id=?",
                ("rejected" if rejected else outcome, canonical(rejected) if rejected else args["result"].get("reason"), work["run_id"], work["video_id"]))
            run = self._run(conn, work["run_id"])
            for i, membership in enumerate(memberships):
                conn.execute("INSERT INTO library_proposals VALUES(?,?,?,?,?,?,?,?)", (work["run_id"], work["video_id"],
                    membership["shelf_id"], run["version_id"], args["submission_key"], int(i == 0), membership["confidence"], canonical(membership["evidence"])))
            conn.execute("UPDATE library_runs SET run_revision=run_revision+1 WHERE run_id=?", (work["run_id"],))
            conn.execute("DELETE FROM library_previews WHERE run_id=?", (work["run_id"],))
            return response

    @endpoint
    def refresh_run_item(self, context, args):
        _operator(context)
        _fields(args, ("run_id", "video_id", "reason"))
        _id(args["run_id"])
        _id(args["video_id"])
        if type(args["reason"]) is not str or not args["reason"].strip():
            fail("validation_error", "Refresh reason required")
        with self.index.write_transaction() as conn:
            self._ready(conn)
            row = conn.execute("SELECT * FROM library_work WHERE run_id=? AND video_id=?", (args["run_id"], args["video_id"])).fetchone()
            if row is None:
                fail("not_found", "Work not found")
            work = dict(row)
            if work["attempts"] >= 3:
                fail("attempts_exhausted", "Create a new operator retry run")
            run = self._run(conn, args["run_id"])
            taxonomy = self._taxonomy(conn, run["version_id"])
            card = self._card(conn, args["video_id"])
            self._invalidate(conn, work, "changed" if card else "deleted", args["reason"])
            policy = decode_json(run["policy_json"])
            source = conn.execute("SELECT corpus_path FROM yoinks WHERE video_id=?", (args["video_id"],)).fetchone()
            head = library_cards.read_corpus_head(source[0]) if source else ""
            policy["corpus_head_hashes"][args["video_id"]] = hashlib.sha256(head.encode()).hexdigest()
            policy["exclusions"].pop(args["video_id"], None)
            if card:
                packet = dict(schema_version=1, video_id=args["video_id"], source_revision=card["source_revision"],
                    taxonomy_revision=taxonomy["revision_hash"], policy_hash=digest(self._rules(policy)), card=card)
                conn.execute("UPDATE library_work SET packet_json=?,packet_hash=?,packet_generation=packet_generation+1,state='ready' WHERE work_id=?",
                    (canonical(packet), digest(packet), work["work_id"]))
                conn.execute("UPDATE library_manifest SET source_revision=?,disposition='waiting' WHERE run_id=? AND video_id=?",
                    (card["source_revision"], args["run_id"], args["video_id"]))
            by_id = {r["video_id"]: dict(r) for r in conn.execute("SELECT video_id,source_revision FROM library_manifest WHERE run_id=?", (args["run_id"],))}
            entries = [by_id[video_id] for video_id in policy["manifest_order"]]
            conn.execute("UPDATE library_runs SET manifest_hash=?,policy_json=? WHERE run_id=?",
                (self._manifest_hash(entries, policy["exclusions"]), canonical(policy), args["run_id"]))
            return success(work_id=work["work_id"], run_revision=self._run(conn, args["run_id"])["run_revision"])

    @contextmanager
    def _locked_store(self):
        """Exclusive-create the lock inode once; OS locking releases on process death.

        Never unlink/recreate a live lock inode: that would permit two owners.
        The file persists across crashes; only the kernel-held lock is authority.
        """
        with self._store_lock:
            self.store_root.mkdir(parents=True, exist_ok=True)
            path = self.store_root / ".library.lock"
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            except FileExistsError:
                fd = os.open(path, os.O_RDWR)
            acquired = False
            try:
                if os.name == "nt":
                    import msvcrt
                    until = time.monotonic() + 10
                    while not acquired:
                        try:
                            os.lseek(fd, 0, os.SEEK_SET)
                            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                            acquired = True
                        except OSError:
                            if time.monotonic() >= until:
                                fail("store_busy", "Library store is locked", retryable=True)
                            time.sleep(.01)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    acquired = True
                yield
            finally:
                if acquired:
                    if os.name == "nt":
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _atomic_file(self, path, data, *, immutable=False, before_publish=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        if immutable and path.exists():
            if path.read_bytes() != data:
                fail("recovery_conflict", "Immutable authoritative record differs")
            return
        temp = path.with_name(path.name + "." + secrets.token_hex(12) + ".tmp")
        try:
            with open(temp, "xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if before_publish:
                before_publish()
            if os.name == "nt":
                # MOVEFILE_WRITE_THROUGH makes the rename synchronous on Windows.
                import ctypes
                move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
                move.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
                move.restype = ctypes.c_int
                if not move(str(temp.resolve()), str(path.resolve()), 0x8 | (0 if immutable else 0x1)):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                os.replace(temp, path)
                fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            temp.unlink(missing_ok=True)

    def _publish_taxonomy(self, taxonomy):
        path = self.store_root / "taxonomies" / (taxonomy["revision_hash"] + ".json")
        self._atomic_file(path, (canonical(taxonomy) + "\n").encode(), immutable=True)

    def _conflict_details(self, conn, expected):
        pins = conn.execute("SELECT s.video_id,s.shelf_id,CASE WHEN p.exclusive_move=1 THEN 'move' "
            "ELSE 'pin' END AS pin_kind FROM item_shelves s LEFT JOIN library_item_policy p "
            "USING(video_id) WHERE s.locked=1 ORDER BY s.video_id,s.shelf_id")
        return dict(expected_revision=expected, current_revision=self._meta(conn)["projection_revision"],
                    conflicts=[dict(row) for row in pins])

    def _revision(self, conn, expected, *, include_pins=False):
        current = self._meta(conn)["projection_revision"]
        if current != expected:
            details = self._conflict_details(conn, expected) if include_pins else dict(
                expected_revision=expected, current_revision=current)
            fail("revision_conflict", "Projection revision changed", **details)
        return current

    def _snapshot(self, conn):
        items = {}
        for row in conn.execute("SELECT * FROM item_shelves ORDER BY video_id,shelf_id"):
            items.setdefault(row["video_id"], []).append(dict(row))
        policies = {r["video_id"]: dict(r) for r in conn.execute("SELECT * FROM library_item_policy ORDER BY video_id")}
        return dict(items=items, policies=policies, active_version_id=self._meta(conn)["active_version_id"])

    @staticmethod
    def _delta(before, after):
        ids = sorted(before["items"].keys() | after["items"].keys() | before["policies"].keys() | after["policies"].keys())
        forward, inverse = dict(items={}, policies={}), dict(items={}, policies={})
        for video_id in ids:
            old, new = before["items"].get(video_id, []), after["items"].get(video_id, [])
            if old != new:
                forward["items"][video_id], inverse["items"][video_id] = new, old
            old, new = before["policies"].get(video_id), after["policies"].get(video_id)
            if old != new:
                forward["policies"][video_id], inverse["policies"][video_id] = new, old
        if before["active_version_id"] != after["active_version_id"]:
            forward["active_version_id"] = after["active_version_id"]
            inverse["active_version_id"] = before["active_version_id"]
        return forward, inverse

    @staticmethod
    def _changed(delta):
        return bool(delta["items"] or delta["policies"] or "active_version_id" in delta)

    def _compute_preview(self, conn, run_id, activate):
        run = self._run(conn, run_id)
        taxonomy = self._taxonomy(conn, run["version_id"])
        baseline = self._snapshot(conn)
        target = copy.deepcopy(baseline)
        manifest = [dict(r) for r in conn.execute("SELECT * FROM library_manifest WHERE run_id=? ORDER BY video_id", (run_id,))]
        sources, accepted, reasons, dispositions = {}, {}, [], []
        for entry in manifest:
            video_id = entry["video_id"]
            card = self._card(conn, video_id)
            sources[video_id] = card["source_revision"] if card else None
            disposition = entry["disposition"]
            old = baseline["items"].get(video_id, [])
            if card is None:
                disposition = "deleted"
                target["items"].pop(video_id, None)
                target["policies"].pop(video_id, None)
            elif card["source_revision"] != entry["source_revision"]:
                disposition = "changed"
            elif any(r["locked"] for r in old):
                disposition = "pinned"
            elif disposition == "accepted":
                rows = [dict(r) for r in conn.execute("SELECT p.*,s.request_hash FROM library_proposals p JOIN library_submissions s USING(submission_key) WHERE p.run_id=? AND p.video_id=? ORDER BY p.shelf_id", (run_id, video_id))]
                if not rows:
                    disposition = "rejected"
                else:
                    target["items"][video_id] = []
                    for proposal in rows:
                        accepted[proposal["submission_key"]] = proposal["request_hash"]
                        membership = dict(video_id=video_id, shelf_id=proposal["shelf_id"], version_id=proposal["version_id"],
                            source_revision=entry["source_revision"], source="agent", locked=0, is_primary=proposal["is_primary"],
                            confidence=proposal["confidence"], evidence_json=proposal["evidence_json"], assigned_at=run["created_at"])
                        previous = next((r for r in old if r["shelf_id"] == membership["shelf_id"]), None)
                        if previous and all(previous[k] == v for k, v in membership.items() if k != "assigned_at"):
                            membership["assigned_at"] = previous["assigned_at"]
                        target["items"][video_id].append(membership)
            if disposition not in {"accepted", "unmapped", "unsupported", "pinned", "deleted"}:
                reasons.append(dict(code="incomplete_manifest", video_id=video_id, disposition=disposition))
            dispositions.append(dict(video_id=video_id, disposition=disposition, reason=entry["reason"]))
        if activate:
            target["active_version_id"] = run["version_id"]
            available = {n["shelf_id"] for n in taxonomy["nodes"] if not n["retired"]}
            for video_id, rows in baseline["items"].items():
                if any(r["locked"] and r["shelf_id"] not in available for r in rows):
                    reasons.append(dict(code="retired_pin", video_id=video_id))
        forward, inverse = self._delta(baseline, target)
        live = {r[0] for r in conn.execute("SELECT video_id FROM yoinks WHERE deleted_at IS NULL")}
        baseline_ids = {video_id for video_id, rows in baseline["items"].items() if rows and video_id in live}
        identity = lambda rows: (sorted(r["shelf_id"] for r in rows), next((r["shelf_id"] for r in rows if r["is_primary"]), None))
        changed = [video_id for video_id in sorted(baseline_ids) if identity(baseline["items"][video_id]) != identity(target["items"].get(video_id, []))]
        initial = [video_id for video_id, rows in target["items"].items() if rows and not baseline["items"].get(video_id) and video_id in live]
        denominator = len(baseline_ids)
        details = []
        for entry in dispositions:
            video_id = entry["video_id"]
            before, after = baseline["items"].get(video_id, []), target["items"].get(video_id, [])
            b, a = {r["shelf_id"]: r for r in before}, {r["shelf_id"]: r for r in after}
            details.append(dict(entry, additions=[a[k] for k in sorted(a.keys()-b.keys())],
                deletions=[b[k] for k in sorted(b.keys()-a.keys())],
                replacements=[dict(before=b[k], after=a[k]) for k in sorted(a.keys() & b.keys()) if a[k] != b[k]],
                primary_before=identity(before)[1], primary_after=identity(after)[1], unchanged=before == after,
                preserved_pins=[r for r in before if r["locked"]]))
        binding = dict(run_id=run_id, run_revision=run["run_revision"], manifest_hash=run["manifest_hash"],
            manifest=manifest, accepted_submission_hashes=accepted, source_revisions=sources,
            taxonomy_revision=taxonomy["revision_hash"], policy=decode_json(run["policy_json"]),
            expected_projection_revision=self._meta(conn)["projection_revision"], baseline_hash=digest(baseline),
            activate_version=activate, forward=forward, inverse=inverse)
        summary = dict(items=details, exclusions=[e for e in dispositions if e["disposition"] != "accepted"],
            changed_items=len(changed), baseline_items=denominator, changed_item_ids=changed,
            churn_percent=(100 * len(changed) / denominator) if denominator else 0.0,
            initial_filing=denominator == 0, initial_filing_items=initial,
            activation=dict(before=baseline["active_version_id"], after=target["active_version_id"]),
            blocking_reasons=reasons)
        return binding, forward, inverse, summary

    @endpoint
    def preview_apply(self, context, args):
        args = validate_arguments("apply_reshelving", args)
        if args.get("mode", "preview") != "preview":
            fail("validation_error", "Expected preview mode")
        with self._locked_store(), self.index.write_transaction() as conn:
            self._ready(conn)
            self._revision(conn, args["expected_projection_revision"], include_pins=True)
            binding, forward, inverse, summary = self._compute_preview(conn, args["run_id"], args.get("activate_version", False))
            preview_id = secrets.token_urlsafe(24)
            delta_hash, expiry = digest(binding), self._now() + 900000
            conn.execute("INSERT INTO library_previews(preview_id,run_id,expected_projection_revision,delta_hash,binding_json,forward_json,inverse_json,summary_json,expires_ms) VALUES(?,?,?,?,?,?,?,?,?)",
                (preview_id, args["run_id"], args["expected_projection_revision"], delta_hash, canonical(binding), canonical(forward), canonical(inverse), canonical(summary), expiry))
            reasons = list(summary["blocking_reasons"])
            if not self.librarian_apply_enabled:
                reasons.append(dict(code="apply_disabled"))
            reasons.append(dict(code="preview_approval_required"))
            if 100 * summary["changed_items"] > 15 * summary["baseline_items"]:
                reasons.append(dict(code="churn_approval_required"))
            return success(preview_id=preview_id, expected_projection_revision=args["expected_projection_revision"],
                delta_hash=delta_hash, expires_ms=expiry, delta=forward, inverse=inverse, summary=summary,
                manifest_exclusions=summary["exclusions"], changed_items=summary["changed_items"], baseline_items=summary["baseline_items"],
                churn_percent=summary["churn_percent"], initial_filing=summary["initial_filing"], can_apply=False, reasons=reasons)

    def _preview(self, conn, preview_id, expected_revision):
        row = conn.execute("SELECT * FROM library_previews WHERE preview_id=?", (preview_id,)).fetchone()
        if row is None:
            fail("preview_conflict", "Preview is missing or invalidated",
                 **self._conflict_details(conn, expected_revision))
        row = dict(row)
        if self._now() >= row["expires_ms"]:
            fail("preview_expired", "Preview approval window expired")
        return row

    def _recheck_preview(self, conn, preview, args):
        self._revision(conn, args["expected_projection_revision"], include_pins=True)
        if preview["delta_hash"] != args["delta_hash"] or preview["expected_projection_revision"] != args["expected_projection_revision"]:
            fail("preview_conflict", "Preview binding differs")
        binding = decode_json(preview["binding_json"])
        actual, forward, inverse, summary = self._compute_preview(conn, preview["run_id"], binding["activate_version"])
        if (digest(actual) != preview["delta_hash"] or actual != binding or
                canonical(forward) != preview["forward_json"] or canonical(inverse) != preview["inverse_json"]):
            fail("preview_conflict", "Preview inputs or delta changed")
        if summary["blocking_reasons"]:
            fail("incomplete_manifest", "All targets must have an accounted disposition", affected=summary["blocking_reasons"])
        return forward, inverse, summary

    @endpoint
    def approve_preview(self, context, args):
        _operator(context)
        if context.local_user_confirmed is not True or not context.session_id:
            fail("user_intent_required", "Local confirmation of the displayed preview required")
        _fields(args, ("preview_id", "delta_hash", "operation_key", "expected_projection_revision"), ("approved_churn_percent",))
        validate_arguments("apply_reshelving", dict(mode="apply", **{k: v for k, v in args.items() if k != "approved_churn_percent"}))
        ceiling = args.get("approved_churn_percent", 15)
        if type(ceiling) is not int or not 15 <= ceiling <= 100:
            fail("validation_error", "Approval ceiling must be an integer between 15 and 100")
        with self._locked_store(), self.index.write_transaction() as conn:
            self._ready(conn)
            preview = self._preview(conn, args["preview_id"], args["expected_projection_revision"])
            _, _, summary = self._recheck_preview(conn, preview, args)
            if 100 * summary["changed_items"] > ceiling * summary["baseline_items"]:
                fail("churn_limit", "Displayed delta exceeds approved ceiling")
            summary["approval"] = dict(operation_key=args["operation_key"], session_hash=digest(context.session_id))
            conn.execute("UPDATE library_previews SET approved_by=?,approved_at=?,approved_churn_percent=?,summary_json=? WHERE preview_id=?",
                (digest(context.session_id), self._stamp(), ceiling, canonical(summary), args["preview_id"]))
            return success(preview_id=args["preview_id"], delta_hash=args["delta_hash"], operation_key=args["operation_key"],
                           expires_ms=preview["expires_ms"], approved_churn_percent=ceiling)

    def _operation_retry(self, conn, args):
        row = conn.execute("SELECT * FROM library_operation_receipts WHERE operation_key=?", (args["operation_key"],)).fetchone()
        if row:
            if row["request_hash"] != digest(args):
                fail("idempotency_conflict", "Operation key already has different content")
            return decode_json(row["receipt_json"])
        return None

    @endpoint
    def apply_preview(self, context, args):
        args = validate_arguments("apply_reshelving", args)
        if args.get("mode") != "apply":
            fail("validation_error", "Expected apply mode")
        with self._locked_store():
            self._recover_locked()
            with self.index.write_transaction() as conn:
                retry = self._operation_retry(conn, args)
                if retry:
                    return retry
                self._ready(conn)
                if not self.librarian_apply_enabled:
                    fail("apply_disabled", "Librarian apply is disabled")
                preview = self._preview(conn, args["preview_id"], args["expected_projection_revision"])
                forward, inverse, summary = self._recheck_preview(conn, preview, args)
                stored_summary = decode_json(preview["summary_json"])
                if not preview["approved_by"] or stored_summary.get("approval", {}).get("operation_key") != args["operation_key"]:
                    fail("preview_approval_required", "Locally approved operation key required")
                ceiling = preview["approved_churn_percent"]
                if ceiling is None or 100 * summary["changed_items"] > ceiling * summary["baseline_items"]:
                    fail("churn_limit", "Delta exceeds local approval ceiling")
                record = self._publish_operation(conn, args, "apply", forward, inverse)
            receipt = self._project_published(record)
            self._emit_mirror_event("apply")  # seam: apply
            return receipt

    @endpoint
    def mint_user_intent(self, context, args):
        """Dashboard-only seam; never expose as a model registry tool.

        args = {kind: 'pin'|'undo', operation: <complete request minus token>}.
        CSRF, origin and displayed-delta checks belong to the confirmation route.
        """
        if context.local_user_confirmed is not True or not context.session_id:
            fail("user_intent_required", "Authenticated local dashboard confirmation required")
        _fields(args, ("kind", "operation"))
        if type(args["kind"]) is not str or args["kind"] not in {"pin", "undo"} or type(args["operation"]) is not dict:
            fail("validation_error", "Invalid intent operation")
        operation = args["operation"]
        if "user_intent_token" in operation:
            fail("validation_error", "Operation must exclude its capability token")
        tool = "pin_shelf" if args["kind"] == "pin" else "undo_library_apply"
        validate_arguments(tool, dict(operation, user_intent_token="x" * 43))
        token = secrets.token_urlsafe(32)
        with self._locked_store():
            self._recover_locked()
            with self.index.write_transaction() as conn:
                self._ready(conn)
                self._revision(conn, operation["expected_projection_revision"])
                # Validate and return the concrete inverse/forward delta for display.
                if args["kind"] == "pin":
                    forward, inverse = self._pin_delta(conn, operation)
                else:
                    forward, inverse = self._undo_delta(conn, operation)
                expires = self._now() + 300000
                conn.execute("INSERT INTO library_user_intents VALUES(?,?,?,?,?,NULL)",
                    (digest(token), args["kind"], digest(operation), digest(context.session_id), expires))
                return success(user_intent_token=token, expires_ms=expires, delta=forward, inverse=inverse,
                               delta_hash=digest(dict(forward=forward, inverse=inverse)))

    def _intent(self, conn, context, args, kind):
        if not context.session_id:
            fail("user_intent_required", "User session required")
        token_hash = digest(args["user_intent_token"])
        row = conn.execute("SELECT * FROM library_user_intents WHERE token_hash=?", (token_hash,)).fetchone()
        request = {k: v for k, v in args.items() if k != "user_intent_token"}
        if row is None or row["kind"] != kind or row["request_hash"] != digest(request) or row["session_hash"] != digest(context.session_id):
            fail("invalid_user_intent", "Capability does not bind this operation and session")
        if row["consumed_by"] is not None or self._now() >= row["expires_ms"]:
            fail("invalid_user_intent", "Capability is expired or consumed")
        return token_hash

    def _pin_delta(self, conn, args):
        self._revision(conn, args["expected_projection_revision"])
        video_id, shelf_id = args["video_id"], args["shelf_id"]
        card = self._card(conn, video_id)
        if card is None:
            fail("not_found", "Live item required")
        before = self._snapshot(conn)
        after = copy.deepcopy(before)
        rows = after["items"].setdefault(video_id, [])
        row = next((r for r in rows if r["shelf_id"] == shelf_id), None)
        policy = after["policies"].get(video_id)
        if args["action"] == "unpin":
            if row and row["locked"]:
                row["locked"] = 0
                if policy and policy["exclusive_move"]:
                    after["policies"].pop(video_id, None)
        else:
            if args["action"] == "pin" and policy and policy["exclusive_move"] and not row:
                fail("exclusive_move_conflict", "Unpin or explicitly move this exclusive item first")
            # Prefer active taxonomy; otherwise choose the newest approved revision.
            active = before["active_version_id"]
            shelf = conn.execute("SELECT n.* FROM shelf_nodes n JOIN shelf_versions v ON v.version_id=n.version_id WHERE n.shelf_id=? AND n.retired=0 AND v.status IN ('approved','active','superseded') ORDER BY (n.version_id=?) DESC,v.created_at DESC,n.version_id DESC LIMIT 1", (shelf_id, active)).fetchone()
            if shelf is None:
                fail("invalid_shelf", "Approved, nonretired shelf required")
            self._taxonomy(conn, shelf["version_id"])
            if args["action"] == "move":
                if (policy and policy["exclusive_move"] and len(rows) == 1 and row and row["locked"]
                        and row["is_primary"] and row["source"] == "user"):
                    return self._delta(before, before)
                rows = after["items"][video_id] = []
                row = None
                after["policies"][video_id] = dict(video_id=video_id, exclusive_move=1)
            if row is None:
                row = dict(video_id=video_id, shelf_id=shelf_id, version_id=shelf["version_id"],
                    source_revision=card["source_revision"], source="user", locked=1,
                    is_primary=int(not any(r["is_primary"] for r in rows)), confidence=None,
                    evidence_json=None, assigned_at=self._stamp())
                rows.append(row)
            else:
                row.update(source="user", locked=1, confidence=None)
            rows.sort(key=lambda r: r["shelf_id"])
        return self._delta(before, after)

    @endpoint
    def pin_shelf(self, context, args):
        args = validate_arguments("pin_shelf", args)
        with self._locked_store():
            self._recover_locked()
            with self.index.write_transaction() as conn:
                retry = self._operation_retry(conn, args)
                if retry:
                    self._retry_session(conn, context, args)
                    return retry
                self._ready(conn)
                token_hash = self._intent(conn, context, args, "pin")
                forward, inverse = self._pin_delta(conn, args)
                record = self._publish_operation(conn, args, "pin", forward, inverse,
                    intent=dict(token_hash=token_hash, session_hash=digest(context.session_id)))
            receipt = self._project_published(record)
            self._emit_mirror_event(  # seam: pin
                "pin", video_id=args.get("video_id"), shelf_id=args.get("shelf_id"))
            return receipt

    def _undo_delta(self, conn, args):
        current = self._revision(conn, args["expected_projection_revision"])
        row = conn.execute("SELECT * FROM library_applies WHERE apply_id=?", (args["apply_id"],)).fetchone()
        if row is None:
            fail("not_found", "Reversible apply not found")
        if row["after_revision"] != current:
            fail("revision_conflict", "Only the latest projection operation can be undone", expected_revision=row["after_revision"], current_revision=current)
        if conn.execute("SELECT 1 FROM library_applies WHERE undo_of=?", (args["apply_id"],)).fetchone():
            fail("undo_conflict", "Operation was already undone")
        return decode_json(row["inverse_json"]), decode_json(row["forward_json"])

    @endpoint
    def undo_apply(self, context, args):
        args = validate_arguments("undo_library_apply", args)
        with self._locked_store():
            self._recover_locked()
            with self.index.write_transaction() as conn:
                retry = self._operation_retry(conn, args)
                if retry:
                    self._retry_session(conn, context, args)
                    return retry
                self._ready(conn)
                token_hash = self._intent(conn, context, args, "undo")
                forward, inverse = self._undo_delta(conn, args)
                record = self._publish_operation(conn, args, "undo", forward, inverse, undo_of=args["apply_id"],
                    intent=dict(token_hash=token_hash, session_hash=digest(context.session_id)))
            receipt = self._project_published(record)
            self._emit_mirror_event("undo")  # seam: undo
            return receipt

    def _retry_session(self, conn, context, args):
        # Session hashes survive total DB loss in the authoritative record.
        if not context.session_id:
            fail("invalid_user_intent", "Original user session required for retry")
        record = next((r for r in self._read_records() if r["operation_key"] == args["operation_key"]), None)
        if not record or record.get("intent", {}).get("session_hash") != digest(context.session_id):
            fail("invalid_user_intent", "Original user session required for retry")

    def _read_records(self):
        """Append-only JSONL segments: one atomically published line per sequence.

        Temporary files are not committed. Published lines are never edited.
        Segments permit detecting a missing middle record and rejecting torn JSON.
        """
        directory = self.store_root / "journal"
        records, previous = [], "0" * 64
        for path in sorted(directory.glob("*.jsonl")):
            try:
                raw = path.read_bytes()
                if not raw.endswith(b"\n") or len(raw.splitlines()) != 1:
                    fail("recovery_conflict", "Incomplete committed journal record")
                record = decode_json(raw)
                claimed_hash = record["record_hash"]
                body = {k: v for k, v in record.items() if k != "record_hash"}
                if (digest(body) != claimed_hash or record["sequence"] != len(records) + 1 or
                        record["previous_record_hash"] != previous or record["schema_version"] != 1 or
                        path.name != self._record_name(record["sequence"], record["operation_key"])):
                    fail("recovery_conflict", "Committed journal hash or sequence mismatch")
                if record["before_revision"] != (records[-1]["after_revision"] if records else 0):
                    fail("recovery_conflict", "Journal projection revision discontinuity")
            except (KeyError, TypeError, ValueError, LibraryError):
                fail("recovery_conflict", "Corrupt committed journal record")
            records.append(record)
            previous = claimed_hash
        snapshot_path = self.store_root / "pins.json"
        if snapshot_path.is_file():
            try:
                checkpoint = decode_json(snapshot_path.read_bytes())
                seq = checkpoint["operation_sequence"]
                if type(seq) is not int or seq < 0 or seq > len(records):
                    fail("recovery_conflict", "Journal tail is missing below the pins checkpoint")
                if checkpoint["record_hash"] != (records[seq - 1]["record_hash"] if seq else "0" * 64):
                    fail("recovery_conflict", "Pins checkpoint hash does not match journal")
            except (KeyError, TypeError, ValueError):
                fail("recovery_conflict", "Invalid pins checkpoint")
        return records

    @staticmethod
    def _record_name(sequence, key):
        return f"{sequence:020d}-{digest(key)}.jsonl"

    def _publish_operation(self, conn, args, kind, forward, inverse, *, undo_of=None, intent=None):
        meta = self._meta(conn)
        records = self._read_records()
        if meta["last_operation_sequence"] != len(records):
            fail("recovery_pending", "Replay durable operations before mutation")
        sequence = len(records) + 1
        changed = self._changed(forward)
        apply_id = secrets.token_urlsafe(24)
        before, after = meta["projection_revision"], meta["projection_revision"] + int(changed)
        delta_hash = args.get("delta_hash") or digest(dict(forward=forward, inverse=inverse))
        receipt = success(operation_key=args["operation_key"], apply_id=apply_id if changed else None,
            before_revision=before, after_revision=after, delta_hash=delta_hash,
            undo_target=apply_id if changed else None, no_change=not changed, operation_sequence=sequence)
        versions = set()
        for delta in (forward, inverse):
            for rows in delta["items"].values():
                versions.update(r["version_id"] for r in rows)
            if delta.get("active_version_id"):
                versions.add(delta["active_version_id"])
        taxonomies = [self._taxonomy(conn, v)["revision_hash"] for v in sorted(versions)]
        record = dict(schema_version=1, operation_id=apply_id, operation_key=args["operation_key"], request_hash=digest(args),
            kind=kind, sequence=sequence, previous_record_hash=records[-1]["record_hash"] if records else "0" * 64,
            before_revision=before, after_revision=after, forward=forward, inverse=inverse,
            taxonomy_hashes=taxonomies, receipt=receipt, undo_of=undo_of, intent=intent, created_at=self._stamp())
        record["record_hash"] = digest(record)
        self._atomic_file(self.store_root / "journal" / self._record_name(sequence, args["operation_key"]),
            (canonical(record) + "\n").encode(), immutable=True,
            before_publish=lambda: self.crash_hook("before_file_publication"))
        # Once published, later failure cannot make this operation uncommitted.
        self._pending_record = record
        try:
            self.crash_hook("after_publication_before_db_commit")
            # Keep BEGIN IMMEDIATE from source revalidation through DB projection.
            self._project_record(conn, record)
        except Exception:
            fail("recovery_pending", "Operation is durable; replay is required", retryable=True)
        return record

    def _project_delta(self, conn, delta):
        for video_id, rows in delta["items"].items():
            conn.execute("DELETE FROM item_shelves WHERE video_id=?", (video_id,))
            if not conn.execute("SELECT 1 FROM yoinks WHERE video_id=? AND deleted_at IS NULL", (video_id,)).fetchone():
                continue
            for row in rows:
                conn.execute("INSERT INTO item_shelves VALUES(?,?,?,?,?,?,?,?,?,?)", tuple(row[k] for k in
                    ("video_id", "shelf_id", "version_id", "source_revision", "source", "locked", "is_primary", "confidence", "evidence_json", "assigned_at")))
        for video_id, policy in delta["policies"].items():
            conn.execute("DELETE FROM library_item_policy WHERE video_id=?", (video_id,))
            if policy is not None and conn.execute("SELECT 1 FROM yoinks WHERE video_id=? AND deleted_at IS NULL", (video_id,)).fetchone():
                conn.execute("INSERT INTO library_item_policy VALUES(?,?)", (video_id, policy["exclusive_move"]))
        if "active_version_id" in delta:
            conn.execute("UPDATE shelf_versions SET status='superseded' WHERE status='active'")
            if delta["active_version_id"]:
                conn.execute("UPDATE shelf_versions SET status='active' WHERE version_id=?", (delta["active_version_id"],))
            conn.execute("UPDATE library_meta SET active_version_id=? WHERE singleton=1", (delta["active_version_id"],))

    def _project_record(self, conn, record):
        meta = self._meta(conn)
        if meta["last_operation_sequence"] + 1 != record["sequence"] or meta["projection_revision"] != record["before_revision"]:
            fail("recovery_conflict", "Database checkpoint does not match journal")
        self._project_delta(conn, record["forward"])
        conn.execute("INSERT INTO library_operation_receipts VALUES(?,?,?,?,?)", (record["operation_key"], record["request_hash"],
            record["sequence"], record["record_hash"], canonical(record["receipt"])))
        if record["after_revision"] != record["before_revision"]:
            conn.execute("INSERT INTO library_applies VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (record["operation_id"],
                record["operation_key"], record["request_hash"], record["kind"], record["before_revision"], record["after_revision"],
                record["sequence"], record["record_hash"], canonical(record["forward"]), canonical(record["inverse"]),
                canonical(record["receipt"]), record["undo_of"], record["created_at"]))
        if record.get("intent"):
            conn.execute("UPDATE library_user_intents SET consumed_by=? WHERE token_hash=?", (record["operation_key"], record["intent"]["token_hash"]))
        if record["kind"] in {"pin", "undo"}:
            for video_id in record["forward"]["items"]:
                pinned = conn.execute("SELECT 1 FROM item_shelves WHERE video_id=? AND locked=1", (video_id,)).fetchone()
                works = conn.execute("SELECT * FROM library_work WHERE video_id=?", (video_id,)).fetchall()
                for work in works:
                    self._invalidate(conn, dict(work), "pinned" if pinned else "changed", "User projection decision changed")
        conn.execute("UPDATE library_meta SET projection_revision=?,last_operation_sequence=?,recovery_state='ready' WHERE singleton=1",
            (record["after_revision"], record["sequence"]))

    def _project_published(self, record):
        try:
            self._write_pins(self._read_records())
        except (sqlite3.Error, OSError, LibraryError):
            with self.index.write_transaction() as conn:
                conn.execute("UPDATE library_meta SET recovery_state='pending' WHERE singleton=1")
            fail("recovery_pending", "Operation is durable; replay is required", retryable=True,
                 operation_key=record["operation_key"])
        self._pending_record = None
        self.crash_hook("after_db_commit_before_response")
        return record["receipt"]

    def _mark_pending(self):
        with self.index.write_transaction() as conn:
            conn.execute("UPDATE library_meta SET recovery_state='pending' WHERE singleton=1")

    @staticmethod
    def _fold_records(records):
        state = dict(items={}, policies={}, active_version_id=None)
        for record in records:
            delta = record["forward"]
            for video_id, rows in delta["items"].items():
                if rows:
                    state["items"][video_id] = rows
                else:
                    state["items"].pop(video_id, None)
            for video_id, policy in delta["policies"].items():
                if policy is None:
                    state["policies"].pop(video_id, None)
                else:
                    state["policies"][video_id] = policy
            if "active_version_id" in delta:
                state["active_version_id"] = delta["active_version_id"]
        return state

    def _write_pins(self, records):
        state = self._fold_records(records)
        pins = {video_id: [r for r in rows if r["source"] == "user"] for video_id, rows in state["items"].items()}
        snapshot = dict(schema_version=1, operation_sequence=len(records),
            record_hash=records[-1]["record_hash"] if records else "0" * 64,
            pins={k: v for k, v in pins.items() if v}, policies=state["policies"])
        self._atomic_file(self.store_root / "pins.json", (canonical(snapshot) + "\n").encode())

    def _load_taxonomies(self, conn):
        path = self.store_root / "taxonomies"
        pending = []
        if path.exists():
            for file in sorted(path.glob("*.json")):
                try:
                    taxonomy = decode_json(file.read_bytes())
                    if taxonomy["revision_hash"] != digest(taxonomy["nodes"]) or file.stem != taxonomy["revision_hash"]:
                        fail("recovery_conflict", "Taxonomy hash mismatch")
                    pending.append(taxonomy)
                except (KeyError, TypeError, ValueError, LibraryError):
                    fail("recovery_conflict", "Corrupt authoritative taxonomy")
        while pending:
            progress = False
            for taxonomy in list(pending):
                parent = taxonomy.get("parent_version_id")
                if parent is None or conn.execute("SELECT 1 FROM shelf_versions WHERE version_id=?", (parent,)).fetchone():
                    self._load_taxonomy(conn, taxonomy)
                    pending.remove(taxonomy)
                    progress = True
            if not progress:
                fail("recovery_conflict", "Missing taxonomy parent or cycle")

    def _recover_locked(self, *, rebuild=False):
        try:
            records = self._read_records()
            with self.index.write_transaction() as conn:
                self._load_taxonomies(conn)
                meta = self._meta(conn)
                if meta["last_operation_sequence"] > len(records):
                    fail("recovery_conflict", "Committed journal record is missing")
                checkpoint_revision = records[meta["last_operation_sequence"] - 1]["after_revision"] if meta["last_operation_sequence"] else 0
                if meta["projection_revision"] != checkpoint_revision:
                    fail("recovery_conflict", "Projection revision differs from journal checkpoint")
                for record in records:
                    for revision_hash in record["taxonomy_hashes"]:
                        if (not (self.store_root / "taxonomies" / (revision_hash + ".json")).is_file() or
                                not conn.execute("SELECT 1 FROM shelf_versions WHERE revision_hash=?", (revision_hash,)).fetchone()):
                            fail("recovery_conflict", "Referenced taxonomy is missing")
                    if record["sequence"] <= meta["last_operation_sequence"]:
                        receipt = conn.execute("SELECT * FROM library_operation_receipts WHERE operation_sequence=?", (record["sequence"],)).fetchone()
                        if receipt is None or receipt["authoritative_record_hash"] != record["record_hash"] or receipt["receipt_json"] != canonical(record["receipt"]):
                            fail("recovery_conflict", "Database receipt differs from authority")
                    else:
                        self._project_record(conn, record)
                if rebuild:
                    # Corpus rebuild runs first. Reproject known identities only;
                    # orphan corrections stay in the authoritative stream.
                    conn.execute("DELETE FROM item_shelves")
                    conn.execute("DELETE FROM library_item_policy")
                    self._project_delta(conn, self._fold_records(records))
                conn.execute("UPDATE library_meta SET recovery_state='ready' WHERE singleton=1")
            self._write_pins(records)
            self._pending_record = None
            with self.index._lock:
                live = {r[0] for r in self.index._conn.execute("SELECT video_id FROM yoinks WHERE deleted_at IS NULL")}
            state = self._fold_records(records)
            orphans = sorted(video_id for video_id, rows in state["items"].items() if video_id not in live and any(r["source"] == "user" for r in rows))
            return success(replayed=max(0, len(records)-meta["last_operation_sequence"]),
                operation_sequence=len(records), projection_revision=records[-1]["after_revision"] if records else 0,
                orphaned_items=orphans, orphaned_count=len(orphans), recovery_state="ready")
        except (KeyError, TypeError, ValueError):
            with self.index.write_transaction() as conn:
                conn.execute("UPDATE library_meta SET recovery_state='conflict' WHERE singleton=1")
            fail("recovery_conflict", "Malformed authoritative state")
        except (LibraryError, sqlite3.Error, OSError):
            with self.index.write_transaction() as conn:
                conn.execute("UPDATE library_meta SET recovery_state='conflict' WHERE singleton=1")
            raise

    @endpoint
    def invalidate_source_items(self, context, args):
        _operator(context)
        _fields(args, ("video_ids",))
        if type(args["video_ids"]) is not list:
            fail("validation_error", "Expected source identity array")
        for video_id in args["video_ids"]:
            _id(video_id)
        count = 0
        with self.index.write_transaction() as conn:
            for video_id in args["video_ids"]:
                card = self._card(conn, video_id)
                for row in conn.execute("SELECT w.*,m.disposition FROM library_work w JOIN library_manifest m USING(run_id,video_id) WHERE w.video_id=?", (video_id,)).fetchall():
                    work = dict(row)
                    frozen = decode_json(work["packet_json"])["source_revision"]
                    disposition = "deleted" if card is None else "changed"
                    if (card is None or card["source_revision"] != frozen) and work["disposition"] != disposition:
                        self._invalidate(conn, work, disposition, "Source committed a new revision")
                        count += 1
        return success(invalidated=count)

    @endpoint
    def recover_operations(self, context, args):
        _operator(context)
        _fields(args, ())
        with self._locked_store():
            return self._recover_locked()

    @endpoint
    def rebuild_library_state(self, context, args):
        _operator(context)
        _fields(args, ())
        with self._locked_store():
            return self._recover_locked(rebuild=True)

    @endpoint
    def export_library_state(self, context, args):
        _operator(context)
        _fields(args, ())
        with self._locked_store():
            status = self._recover_locked()
            records = self._read_records()
            taxonomies = [decode_json(p.read_bytes()) for p in sorted((self.store_root / "taxonomies").glob("*.json"))]
            # Only hashes of request/session/token identities enter records.
            return success(records=records, taxonomies=taxonomies, state=self._fold_records(records),
                orphaned_count=status["orphaned_count"], projection_revision=status["projection_revision"])


class LibraryPreviewReader:
    """Pure preview checks, without work-service startup or write endpoints.

    Share the exact binding, taxonomy, evidence and delta checks with apply;
    this object neither attaches itself to the index nor recovers the store.
    The caller owns admission, the read transaction and its deadline.
    """

    def __init__(self, index, *, clock=None):
        self.store_root = index._path.parent / "library"
        self.clock = clock or (lambda: int(time.time() * 1000))

    _now = LibraryWorkService._now
    _run = LibraryWorkService._run
    _meta = LibraryWorkService._meta
    _card = LibraryWorkService._card
    _taxonomy = LibraryWorkService._taxonomy
    _snapshot = LibraryWorkService._snapshot
    _delta = staticmethod(LibraryWorkService._delta)
    _conflict_details = LibraryWorkService._conflict_details
    _revision = LibraryWorkService._revision
    _compute_preview = LibraryWorkService._compute_preview
    _recheck_preview = LibraryWorkService._recheck_preview


# Module functions and class methods use the same authenticated service seam.
# Adapters never construct HTTP handlers or reproduce domain validation.

def approve_taxonomy(index, context, args=_MISSING):
    return index.library_service().approve_taxonomy(context, args)


def prepare_run(index, context, args=_MISSING):
    return index.library_service().prepare_run(context, args)


def refresh_run_item(index, context, args=_MISSING):
    return index.library_service().refresh_run_item(context, args)


def list_work(index, context, args=_MISSING):
    return index.library_service().list_work(context, args)


def claim_work(index, context, args=_MISSING):
    return index.library_service().claim_work(context, args)


def renew_attempt(index, context, args=_MISSING):
    return index.library_service().renew_attempt(context, args)


def release_attempt(index, context, args=_MISSING):
    return index.library_service().release_attempt(context, args)


def cancel_attempt(index, context, args=_MISSING):
    return index.library_service().cancel_attempt(context, args)


def expire_attempts(index, context, args=_MISSING):
    return index.library_service().expire_attempts(context, args)


def validate_result(index, context, args=_MISSING):
    return index.library_service().validate_result(context, args)


def submit_result(index, context, args=_MISSING):
    return index.library_service().submit_result(context, args)


def preview_apply(index, context, args=_MISSING):
    return index.library_service().preview_apply(context, args)


def approve_preview(index, context, args=_MISSING):
    return index.library_service().approve_preview(context, args)


def apply_preview(index, context, args=_MISSING):
    return index.library_service().apply_preview(context, args)


def mint_user_intent(index, context, args=_MISSING):
    return index.library_service().mint_user_intent(context, args)


def pin_shelf(index, context, args=_MISSING):
    return index.library_service().pin_shelf(context, args)


def undo_apply(index, context, args=_MISSING):
    return index.library_service().undo_apply(context, args)


def recover_operations(index, context, args=_MISSING):
    return index.library_service().recover_operations(context, args)


def export_library_state(index, context, args=_MISSING):
    return index.library_service().export_library_state(context, args)


def rebuild_library_state(index, context, args=_MISSING):
    return index.library_service().rebuild_library_state(context, args)


# Frozen schema copy; keep in sync with CONTRACT_VERSION.
_DEFS = {'id': {'type': 'string', 'minLength': 1, 'maxLength': 200},
 'client': {'type': 'string', 'minLength': 1, 'maxLength': 64},
 'key': {'type': 'string', 'minLength': 1, 'maxLength': 200},
 'hash': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
 'token': {'type': 'string', 'pattern': '^[A-Za-z0-9_-]{43,128}$'},
 'revision': {'type': 'integer', 'minimum': 0, 'maximum': 2147483647},
 'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
 'evidence': {'type': 'object',
              'properties': {'basis': {'type': 'string', 'enum': ['packet', 'fetched_full']},
                             'kind': {'type': 'string', 'enum': ['timed_clip', 'text_only']},
                             'excerpt_id': {'$ref': '#/$defs/hash'},
                             'card_hash': {'$ref': '#/$defs/hash'},
                             'quote': {'type': 'string', 'minLength': 1, 'maxLength': 1000}},
              'required': ['basis', 'kind', 'excerpt_id', 'card_hash', 'quote'],
              'additionalProperties': False},
 'membership': {'type': 'object',
                'properties': {'shelf_id': {'$ref': '#/$defs/id'},
                               'shelf_path': {'type': 'array',
                                              'items': {'type': 'string',
                                                        'minLength': 1,
                                                        'maxLength': 100},
                                              'minItems': 1,
                                              'maxItems': 3},
                               'confidence': {'$ref': '#/$defs/confidence'},
                               'evidence': {'$ref': '#/$defs/evidence'}},
                'required': ['shelf_id', 'shelf_path', 'confidence', 'evidence'],
                'additionalProperties': False},
 'result': {'oneOf': [{'type': 'object',
                       'properties': {'outcome': {'const': 'assigned'},
                                      'memberships': {'type': 'array',
                                                      'items': {'$ref': '#/$defs/membership'},
                                                      'minItems': 1,
                                                      'maxItems': 3}},
                       'required': ['outcome', 'memberships'],
                       'additionalProperties': False},
                      {'type': 'object',
                       'properties': {'outcome': {'type': 'string',
                                                  'enum': ['unmapped', 'unsupported', 'error']},
                                      'reason': {'type': 'string',
                                                 'minLength': 1,
                                                 'maxLength': 500}},
                       'required': ['outcome', 'reason'],
                       'additionalProperties': False}]},
 'usage': {'oneOf': [{'type': 'object',
                      'properties': {'status': {'const': 'reported'},
                                     'model': {'type': 'string', 'minLength': 1, 'maxLength': 200},
                                     'input_tokens': {'type': 'integer',
                                                      'minimum': 0,
                                                      'maximum': 2147483647},
                                     'output_tokens': {'type': 'integer',
                                                       'minimum': 0,
                                                       'maximum': 2147483647},
                                     'cache_read_tokens': {'type': 'integer',
                                                           'minimum': 0,
                                                           'maximum': 2147483647},
                                     'cache_create_tokens': {'type': 'integer',
                                                             'minimum': 0,
                                                             'maximum': 2147483647},
                                     'wall_time_ms': {'type': 'integer',
                                                      'minimum': 0,
                                                      'maximum': 2147483647}},
                      'required': ['status',
                                   'model',
                                   'input_tokens',
                                   'output_tokens',
                                   'wall_time_ms'],
                      'additionalProperties': False},
                     {'type': 'object',
                      'properties': {'status': {'const': 'unavailable'},
                                     'model': {'type': 'string', 'minLength': 1, 'maxLength': 200},
                                     'reason': {'type': 'string', 'minLength': 1, 'maxLength': 500},
                                     'wall_time_ms': {'type': 'integer',
                                                      'minimum': 0,
                                                      'maximum': 2147483647}},
                      'required': ['status', 'reason'],
                      'additionalProperties': False}]}}

_SCHEMAS = {'list_library_work': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                       'type': 'object',
                       'properties': {'run_id': {'$ref': '#/$defs/id'},
                                      'state': {'type': 'string',
                                                'enum': ['all',
                                                         'ready',
                                                         'leased',
                                                         'accepted',
                                                         'unmapped',
                                                         'unsupported',
                                                         'blocked',
                                                         'cancelled']},
                                      'limit': {'type': 'integer',
                                                'minimum': 1,
                                                'maximum': 100,
                                                'default': 25},
                                      'cursor': {'type': 'string',
                                                 'minLength': 1,
                                                 'maxLength': 500}},
                       'required': [],
                       'additionalProperties': False},
 'claim_library_work': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                        'oneOf': [{'type': 'object',
                                   'properties': {'action': {'const': 'claim'},
                                                  'run_id': {'$ref': '#/$defs/id'},
                                                  'client_id': {'$ref': '#/$defs/client'},
                                                  'max_items': {'type': 'integer',
                                                                'minimum': 1,
                                                                'maximum': 12,
                                                                'default': 12},
                                                  'lease_seconds': {'type': 'integer',
                                                                    'minimum': 60,
                                                                    'maximum': 900,
                                                                    'default': 900}},
                                   'required': ['action', 'run_id', 'client_id'],
                                   'additionalProperties': False},
                                  {'type': 'object',
                                   'properties': {'action': {'const': 'renew'},
                                                  'work_id': {'$ref': '#/$defs/id'},
                                                  'client_id': {'$ref': '#/$defs/client'},
                                                  'attempt_token': {'$ref': '#/$defs/token'},
                                                  'lease_seconds': {'type': 'integer',
                                                                    'minimum': 60,
                                                                    'maximum': 900}},
                                   'required': ['action',
                                                'work_id',
                                                'client_id',
                                                'attempt_token',
                                                'lease_seconds'],
                                   'additionalProperties': False},
                                  {'type': 'object',
                                   'properties': {'action': {'type': 'string',
                                                             'enum': ['release', 'cancel']},
                                                  'work_id': {'$ref': '#/$defs/id'},
                                                  'client_id': {'$ref': '#/$defs/client'},
                                                  'attempt_token': {'$ref': '#/$defs/token'},
                                                  'reason': {'type': 'string',
                                                             'minLength': 1,
                                                             'maxLength': 500}},
                                   'required': ['action',
                                                'work_id',
                                                'client_id',
                                                'attempt_token',
                                                'reason'],
                                   'additionalProperties': False}]},
 'submit_library_result': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                           'type': 'object',
                           'properties': {'work_id': {'$ref': '#/$defs/id'},
                                          'client_id': {'$ref': '#/$defs/client'},
                                          'attempt_token': {'$ref': '#/$defs/token'},
                                          'submission_key': {'$ref': '#/$defs/key'},
                                          'schema_version': {'const': 1},
                                          'video_id': {'$ref': '#/$defs/id'},
                                          'source_revision': {'$ref': '#/$defs/hash'},
                                          'taxonomy_revision': {'$ref': '#/$defs/hash'},
                                          'packet_hash': {'$ref': '#/$defs/hash'},
                                          'result': {'$ref': '#/$defs/result'},
                                          'usage': {'$ref': '#/$defs/usage'}},
                           'required': ['work_id',
                                        'client_id',
                                        'attempt_token',
                                        'submission_key',
                                        'schema_version',
                                        'video_id',
                                        'source_revision',
                                        'taxonomy_revision',
                                        'packet_hash',
                                        'result',
                                        'usage'],
                           'additionalProperties': False},
 'apply_reshelving': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                      'oneOf': [{'type': 'object',
                                 'properties': {'mode': {'const': 'preview', 'default': 'preview'},
                                                'run_id': {'$ref': '#/$defs/id'},
                                                'expected_projection_revision': {'$ref': '#/$defs/revision'},
                                                'activate_version': {'type': 'boolean',
                                                                     'default': False}},
                                 'required': ['run_id', 'expected_projection_revision'],
                                 'additionalProperties': False},
                                {'type': 'object',
                                 'properties': {'mode': {'const': 'apply'},
                                                'preview_id': {'$ref': '#/$defs/id'},
                                                'expected_projection_revision': {'$ref': '#/$defs/revision'},
                                                'delta_hash': {'$ref': '#/$defs/hash'},
                                                'operation_key': {'$ref': '#/$defs/key'}},
                                 'required': ['mode',
                                              'preview_id',
                                              'expected_projection_revision',
                                              'delta_hash',
                                              'operation_key'],
                                 'additionalProperties': False}]},
 'pin_shelf': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
               'type': 'object',
               'properties': {'video_id': {'$ref': '#/$defs/id'},
                              'shelf_id': {'$ref': '#/$defs/id'},
                              'action': {'type': 'string', 'enum': ['pin', 'unpin', 'move']},
                              'expected_projection_revision': {'$ref': '#/$defs/revision'},
                              'operation_key': {'$ref': '#/$defs/key'},
                              'user_intent_token': {'$ref': '#/$defs/token'},
                              'reason': {'type': 'string', 'minLength': 1, 'maxLength': 500}},
               'required': ['video_id',
                            'shelf_id',
                            'action',
                            'expected_projection_revision',
                            'operation_key',
                            'user_intent_token'],
               'additionalProperties': False},
 'undo_library_apply': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                        'type': 'object',
                        'properties': {'apply_id': {'$ref': '#/$defs/id'},
                                       'expected_projection_revision': {'$ref': '#/$defs/revision'},
                                       'operation_key': {'$ref': '#/$defs/key'},
                                       'user_intent_token': {'$ref': '#/$defs/token'}},
                        'required': ['apply_id',
                                     'expected_projection_revision',
                                     'operation_key',
                                     'user_intent_token'],
                        'additionalProperties': False}}
for _schema in _SCHEMAS.values():
    _schema["$defs"] = _DEFS

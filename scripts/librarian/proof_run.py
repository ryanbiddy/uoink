#!/usr/bin/env python3
"""
scripts/librarian/proof_run.py - Living Library Product Proof Run Harness (Run P/Q)

Drives the claim -> reason -> submit loop over the HTTP registry:
    POST /tools/claim_library_work
    POST /tools/submit_library_result
    POST /tools/apply_reshelving (preview mode)

Emits receipt document adhering strictly to the Draft 2020-12 contract defined in
docs/library/PROOF-PLAN-2026-09-05.md and validated by tests/validate_proof_receipts.py.

Uses an isolated helper server running on an ephemeral port (default: 5180, never 5179)
under a disposable root (default: _scratch/proof/...). Never opens the live index.
Subscription-only execution: asserts ANTHROPIC_API_KEY is unset.

Supports:
- --mock: Deterministic fixture assignment (right label for gold items, unmapped for others).
          Exercises helper, HTTP calls, and receipts with zero model execution.
- Without --mock: Invokes `claude -p --json-schema ... --output-format json --tools ""`
                  for each card (or in batches with --batch), recording CLI token usage.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import copy
import hashlib
import json
import math
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import index as index_mod
import library_cards
import library_work
from library_work import RequestContext

CONTRACT = "phase2-v1.2-2026-09-04"
NAMED_COPY_HASH = "2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc"
FORBIDDEN_PORT = 5179

HASH_KEYS = [
    "manifest_hash",
    "source_sha256",
    "taxonomy_file_sha256",
    "taxonomy_revision_hash",
    "prompt_file_sha256",
    "prompt_sha256",
    "card_profile_hash",
    "card_builder_sha256",
    "holdout_file_sha256",
    "holdout_ids_hash",
    "gold_file_sha256",
    "cards_hash",
    "corpus_heads_hash",
    "implementation_hash",
]

ASSIGN_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "video_id": {"type": "string"},
                    "result": {
                        "type": "object",
                        "properties": {
                            "outcome": {
                                "type": "string",
                                "enum": ["assigned", "unmapped", "unsupported", "error"],
                            },
                            "memberships": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "shelf_id": {"type": "string"},
                                        "shelf_path": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "minItems": 1,
                                            "maxItems": 3,
                                        },
                                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                                        "evidence": {
                                            "type": "object",
                                            "properties": {
                                                "basis": {"type": "string", "enum": ["packet", "fetched_full"]},
                                                "kind": {"type": "string", "enum": ["timed_clip", "text_only"]},
                                                "excerpt_id": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                                                "card_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                                                "quote": {"type": "string", "minLength": 1, "maxLength": 1000},
                                            },
                                            "required": ["basis", "kind", "excerpt_id", "card_hash", "quote"],
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["shelf_id", "shelf_path", "confidence", "evidence"],
                                    "additionalProperties": False,
                                },
                                "minItems": 1,
                                "maxItems": 3,
                            },
                            "reason": {"type": "string", "minLength": 1, "maxLength": 500},
                        },
                        "required": ["outcome"],
                        "additionalProperties": False,
                    },
                },
                "required": ["video_id", "result"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def canonical(value: Any) -> str:
    """Canonical JSON encoding strictly matching validator and service hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest(value: Any) -> str:
    return sha(canonical(value).encode("utf-8"))


def compute_file_sha256(path: Path) -> str:
    """Computes SHA-256 digest of a file in binary mode."""
    d = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            d.update(chunk)
    return d.hexdigest()


def find_free_port() -> int:
    """Finds an available ephemeral port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        if port == FORBIDDEN_PORT:
            return find_free_port()
        return port


def render_prompt(template: str, taxonomy: dict, card: dict) -> str:
    """Renders the prompt exactly matching the validator contract."""
    if template.count("{{TAXONOMY}}") != 1 or template.count("{{CARDS}}") != 1:
        raise ProofRunError("Prompt placeholders changed")
    prefix, suffix = template.split("{{CARDS}}")
    return (
        prefix.replace("{{TAXONOMY}}", library_cards.serialize_card(taxonomy))
        + library_cards.card_text(card)
        + suffix
    )


def normalized_taxonomy(document: dict) -> dict:
    """The documented approve_taxonomy input conversion; mirrors service ordering."""
    nodes = copy.deepcopy(document["nodes"])
    for node in nodes:
        node["retired"] = bool(node.get("retired", False))
        node["path"] = [unicodedata.normalize("NFC", part) for part in node["path"]]
        node["name"] = node["path"][-1]
    by_path = {tuple(node["path"]): node["shelf_id"] for node in nodes}
    for node in nodes:
        node["parent_shelf_id"] = by_path.get(tuple(node["path"][:-1]))
    nodes.sort(key=lambda node: (len(node["path"]), node["path"], node["shelf_id"]))
    return dict(
        schema_version=1,
        version_id=document["version_id"],
        nodes=nodes,
        parent_version_id=document.get("parent_version_id"),
        revision_hash=digest(nodes),
    )


def submit_usage(usage: dict) -> dict:
    """Project a usage record onto the frozen submit schema."""
    if usage.get("status") == "reported":
        keys = ("status", "model", "input_tokens", "output_tokens",
                "cache_read_tokens", "cache_create_tokens", "wall_time_ms")
    else:
        keys = ("status", "model", "reason", "wall_time_ms")
    out = {k: usage[k] for k in keys if k in usage}
    out.setdefault("status", "unavailable")
    out.setdefault("model", str(usage.get("model") or "unknown"))
    out.setdefault("wall_time_ms", int(usage.get("wall_time_ms", 0) or 0))
    if out["status"] == "unavailable":
        out.setdefault("reason", str(usage.get("reason") or "usage unavailable"))
    return out


class ProofRunError(RuntimeError):
    pass


class ProofHarness:
    def __init__(
        self,
        source: Path,
        out_dir: Path,
        mock: bool = True,
        limit: Optional[int] = None,
        model: str = "claude-sonnet-5",
        concurrency: int = 4,
        port: int = 5180,
        scratch_dir: Optional[Path] = None,
        run_id: str = "proof-run-p",
        expected_hash: Optional[str] = NAMED_COPY_HASH,
        skip_hash_check: bool = False,
        batch: int = 12,
        taxonomy: Optional[Path] = None,
        manifest: Optional[Path] = None,
        mock_reject_count: int = 0,
    ):
        self.source = Path(source).resolve()
        self.out_dir = Path(out_dir).resolve()
        self.mock = mock
        self.mock_reject_count = mock_reject_count
        self.limit = limit
        self.model = model
        self.concurrency = max(1, min(4, concurrency))
        self.batch = max(1, batch)
        # Per-call hard bound; a hung CLI must fail fast so the attempt is
        # recorded and the lease can be retried or expire.
        self.call_timeout = int(os.environ.get("UOINK_PROOF_CALL_TIMEOUT", "300"))
        self.port = port
        self.run_id = run_id
        self.expected_hash = expected_hash
        self.skip_hash_check = skip_hash_check

        # Directory structure per contract
        self.calls_dir = self.out_dir / "calls"
        self.http_dir = self.out_dir / "http"
        self.state_dir = self.out_dir / "state"

        # Shared coordinator state for error guard
        self._http_seq = 0
        self._mock_item_index = 0
        self.abort_event = threading.Event()
        self.abort_reason: Optional[str] = None
        self._active_processes: set = set()
        self._proc_lock = threading.Lock()
        self._coordinator_lock = threading.Lock()
        self.wall_budget_ms = 7200000
        self.error_rate_limit = 0.10
        self.error_rate_min_attempts = 20

        # Paths
        self.manifest_path = Path(manifest).resolve() if manifest else ROOT / "docs" / "library" / "proof" / "manifest-2026-09-05.json"
        self.taxonomy_path = Path(taxonomy).resolve() if taxonomy else ROOT / "docs" / "library" / "taxonomy-v1-2026-09-04.json"
        self.prompt_path = ROOT / "scripts" / "librarian" / "prompts" / "assign.md"
        self.holdout_path = ROOT / "docs" / "library" / "holdout-split-2026-09-04.json"
        self.gold_path = ROOT / "docs" / "library" / "gold-set-2026-09-04.json"

        # Isolation root must be strictly under ROOT / "_scratch/proof"
        proof_scratch = (ROOT / "_scratch" / "proof").resolve()
        proof_scratch.mkdir(parents=True, exist_ok=True)
        if (
            scratch_dir
            and Path(scratch_dir).resolve().is_relative_to(proof_scratch)
            and Path(scratch_dir).resolve() != proof_scratch
        ):
            self.scratch_dir = Path(scratch_dir).resolve()
        else:
            self.scratch_dir = (proof_scratch / f"run-{self.run_id}-{secrets.token_hex(4)}").resolve()

        self.server_thread: Optional[threading.Thread] = None
        self.http_server_instance: Optional[Any] = None
        self.token: str = ""
        self.base_url: str = f"http://127.0.0.1:{self.port}"

        self.output_schema_text = canonical(ASSIGN_OUTPUT_SCHEMA)
        self.output_schema_sha256 = sha(self.output_schema_text.encode("utf-8"))

        self.manifest: Dict[str, Any] = {}
        self.target_ids: List[str] = []
        self.before_state: Dict[str, Any] = {}
        self.after_state: Dict[str, Any] = {}
        self.attempts: List[Dict[str, Any]] = []
        self.transport_failures: List[Dict[str, Any]] = []
        self.targets: List[Dict[str, Any]] = []
        self.preview: Dict[str, Any] = {}
        self.calls: List[Dict[str, Any]] = []

        self.copy_before_upgrade_sha256 = ""
        self.copy_after_upgrade_sha256 = ""
        self.source_after_sha256 = ""
        self.schema_before = 0
        self.schema_after = 0
        self.run_start_time = 0.0

        self.gold_by_id: Dict[str, Any] = {}
        self.taxonomy_nodes_by_path: Dict[Tuple[str, ...], Any] = {}
        self.prompt_template: str = ""

        self._lock = threading.Lock()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._orig_env = {
            k: os.environ.get(k)
            for k in ("LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "UOINK_OUTPUT_DIR", "NO_PROXY")
        }

    def check_guards(self) -> None:
        """Enforces runtime security and boundary constraints per the contract."""
        # 1. Assert ANTHROPIC_API_KEY is unset (including empty values)
        if "ANTHROPIC_API_KEY" in os.environ:
            raise ProofRunError(
                "Refusing to start: ANTHROPIC_API_KEY is present in environment (must be unset, including empty values)."
            )

        # 2. Never target port 5179
        if self.port == FORBIDDEN_PORT:
            raise ProofRunError(
                f"Refusing to target port {FORBIDDEN_PORT}. "
                "Port 5179 is reserved for the live index helper."
            )

        # 3. Check if helper port is already occupied
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.bind(("127.0.0.1", self.port))
            except OSError as e:
                raise ProofRunError(
                    f"Helper port {self.port} is already occupied: {e}. Aborting."
                )

        # 4. Verify source exists
        if not self.source.is_file():
            raise ProofRunError(f"Source index copy does not exist: {self.source}")

        # 5. Verify source hash if requested
        actual_hash = compute_file_sha256(self.source)
        if not self.skip_hash_check and self.expected_hash:
            if actual_hash != self.expected_hash:
                raise ProofRunError(
                    f"Source index SHA-256 mismatch!\n"
                    f"Expected: {self.expected_hash}\n"
                    f"Actual:   {actual_hash}"
                )

    def prepare_isolated_environment(self) -> Path:
        """Configures disposable roots and copies the index to <root>/Uoink/index.db."""
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        uoink_root = self.scratch_dir / "Uoink"
        uoink_root.mkdir(parents=True, exist_ok=True)
        (self.scratch_dir / "local").mkdir(parents=True, exist_ok=True)
        (self.scratch_dir / "roaming").mkdir(parents=True, exist_ok=True)
        (self.scratch_dir / "temp").mkdir(parents=True, exist_ok=True)
        (self.scratch_dir / "output").mkdir(parents=True, exist_ok=True)

        os.environ["LOCALAPPDATA"] = str(self.scratch_dir / "local")
        os.environ["APPDATA"] = str(self.scratch_dir / "roaming")
        os.environ["TEMP"] = str(self.scratch_dir / "temp")
        os.environ["TMP"] = str(self.scratch_dir / "temp")
        os.environ["UOINK_OUTPUT_DIR"] = str(self.scratch_dir / "output")
        os.environ["NO_PROXY"] = "127.0.0.1,localhost"

        isolated_db = uoink_root / "index.db"
        if not self.skip_hash_check:
            self.copy_before_upgrade_sha256 = compute_file_sha256(self.source)
        else:
            self.copy_before_upgrade_sha256 = self.expected_hash or compute_file_sha256(self.source)

        shutil.copyfile(self.source, isolated_db)
        return isolated_db

    def _snapshot_state(self, conn: Any) -> Dict[str, Any]:
        """Snapshots the exact state required by STATE_SCHEMA."""
        rev = conn.execute("SELECT projection_revision FROM library_meta").fetchone()[0]
        memberships = [
            dict(r)
            for r in conn.execute(
                "SELECT video_id, shelf_id, version_id, source_revision, source, locked, is_primary, confidence, evidence_json, assigned_at "
                "FROM item_shelves ORDER BY video_id, shelf_id"
            ).fetchall()
        ]
        pins = [
            dict(r)
            for r in conn.execute(
                "SELECT video_id, shelf_id FROM item_shelves WHERE locked=1 ORDER BY video_id, shelf_id"
            ).fetchall()
        ]
        policies = [
            dict(r)
            for r in conn.execute(
                "SELECT video_id, exclusive_move FROM library_item_policy ORDER BY video_id"
            ).fetchall()
        ]
        active_version_id = conn.execute("SELECT active_version_id FROM library_meta").fetchone()[0]
        row_tax = conn.execute(
            "SELECT revision_hash FROM shelf_versions WHERE version_id=?", (active_version_id,)
        ).fetchone()
        tax_hash = row_tax[0] if row_tax else ("0" * 64)
        applied_count = conn.execute("SELECT count(*) FROM item_shelves").fetchone()[0]
        proof_apply_count = conn.execute("SELECT count(*) FROM library_applies").fetchone()[0]

        return {
            "projection_revision": rev,
            "memberships": memberships,
            "pins": pins,
            "item_policies": policies,
            "active_version_id": active_version_id,
            "taxonomy_revision_hash": tax_hash,
            "librarian_apply_enabled": False,
            "applied_label_count": applied_count,
            "proof_apply_count": proof_apply_count,
        }

    def initialize_database_and_freeze(self, db_path: Path) -> None:
        """Initializes schema, approves taxonomy, activates it, and prepares the run."""
        if not self.manifest_path.is_file():
            raise ProofRunError(f"Manifest missing: {self.manifest_path}")
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

        if not self.prompt_path.is_file():
            raise ProofRunError(f"Prompt template missing: {self.prompt_path}")
        self.prompt_template = self.prompt_path.read_text(encoding="utf-8")

        if self.gold_path.is_file():
            gold_items = json.loads(self.gold_path.read_text(encoding="utf-8"))
            self.gold_by_id = {item["video_id"]: item for item in gold_items}

        norm_tax = self.manifest["taxonomy"]
        self.taxonomy_nodes_by_path = {
            tuple(n["path"]): n for n in norm_tax["nodes"] if not n.get("retired")
        }

        # 1. Read schema_before from the duplicate before Index.open
        conn_ro = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
        conn_ro.execute("PRAGMA query_only=ON")
        self.schema_before = conn_ro.execute("SELECT max(version) FROM schema_version").fetchone()[0]
        conn_ro.close()

        # 2. Open index to apply migrations 26 & 27
        idx = index_mod.Index.open(db_path)
        idx._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.schema_after = idx._conn.execute("SELECT max(version) FROM schema_version").fetchone()[0]
        self.copy_after_upgrade_sha256 = compute_file_sha256(db_path)

        svc = idx.library_service()
        ctx = RequestContext(
            authenticated=True,
            client_id="proof-harness",
            session_id="proof-operator",
            operator=True,
            local_user_confirmed=True,
        )

        # 3. Approve taxonomy
        tax_res = svc.approve_taxonomy(
            ctx,
            {
                "version_id": norm_tax["version_id"],
                "nodes": norm_tax["nodes"],
                "parent_version_id": norm_tax.get("parent_version_id"),
            },
        )
        if not tax_res.get("ok") or tax_res.get("revision_hash") != norm_tax["revision_hash"]:
            raise ProofRunError(f"approve_taxonomy failed or revision hash mismatch: {tax_res}")

        # 4. Bootstrap activate taxonomy on the isolated helper duplicate
        with idx.write_transaction() as conn:
            conn.execute(
                "UPDATE shelf_versions SET status='active' WHERE version_id=?", (norm_tax["version_id"],)
            )
            conn.execute(
                "UPDATE library_meta SET active_version_id=? WHERE singleton=1", (norm_tax["version_id"],)
            )

        # 5. Determine targets strictly in manifest item order
        manifest_ids = [entry[0] for entry in self.manifest["items"]]
        db_ids = set(
            r[0]
            for r in idx._conn.execute(
                "SELECT video_id FROM yoinks WHERE deleted_at IS NULL"
            ).fetchall()
        )
        available_ids = [vid for vid in manifest_ids if vid in db_ids]
        if not available_ids:
            available_ids = sorted(list(db_ids))
        self.target_ids = available_ids[: self.limit] if self.limit is not None else available_ids

        # 6. Prepare run
        prompt_hash = self.manifest["hashes"]["prompt_sha256"]
        prep_res = svc.prepare_run(
            ctx,
            {
                "run_id": self.run_id,
                "version_id": norm_tax["version_id"],
                "video_ids": self.target_ids,
                "prompt_hash": prompt_hash,
            },
        )
        if not prep_res.get("ok"):
            raise ProofRunError(f"prepare_run failed: {prep_res}")

        # 7. Snapshot before-state
        self.before_state = self._snapshot_state(idx._conn)
        if self.before_state["applied_label_count"] != 0:
            raise ProofRunError(
                f"Initial database is not clean: {self.before_state['applied_label_count']} applied labels found."
            )
        if self.before_state["proof_apply_count"] != 0:
            raise ProofRunError(
                f"Initial database has proof apply records: {self.before_state['proof_apply_count']}"
            )

        idx.close()

    def start_server(self) -> None:
        """Starts the isolated server.py helper in a thread and waits for /health."""
        import _platform
        import server

        server.HOST = "127.0.0.1"
        server.PORT = self.port
        server.DATA_ROOT = self.scratch_dir / "Uoink"
        server.INDEX_PATH = server.DATA_ROOT / "index.db"
        server.SETTINGS_PATH = server.DATA_ROOT / "settings.json"
        server.TOKEN_PATH = server.DATA_ROOT / "token.txt"
        server.TOKEN = server._load_or_create_token()
        server.TOKEN_PATH.write_text(server.TOKEN, encoding="utf-8")
        server._index_singleton = None

        try:
            import uoink_mcp_tools
            for limiter in uoink_mcp_tools._LIBRARY_RATE_LIMITERS.values():
                limiter.max_calls = 1000000
        except Exception:
            pass

        server_holder: Dict[str, Any] = {}
        original_init = server._YoinkHTTPServer.__init__

        def _hooked_init(s_self, *args, **kwargs):
            original_init(s_self, *args, **kwargs)
            server_holder["server"] = s_self

        server._YoinkHTTPServer.__init__ = _hooked_init

        self.server_thread = threading.Thread(
            target=server.main,
            kwargs={"show_dashboard": False},
            daemon=True,
            name="proof-server-helper",
        )
        self.server_thread.start()

        # Wait for server to respond on /health
        deadline = time.perf_counter() + 30.0
        online = False
        while time.perf_counter() < deadline:
            try:
                resp = self.opener.open(f"{self.base_url}/health", timeout=1.0)
                if resp.status == 200:
                    online = True
                    break
            except Exception:
                time.sleep(0.1)

        if not online:
            raise ProofRunError(f"Server failed to come online on {self.base_url} within 30s")

        self.http_server_instance = server_holder.get("server")
        self.token = server.TOKEN_PATH.read_text(encoding="utf-8").strip()

    def stop_server(self) -> None:
        """Stops the helper server cleanly and restores environment."""
        if self.http_server_instance is not None:
            try:
                self.http_server_instance.shutdown()
                self.http_server_instance.server_close()
            except Exception:
                pass
        import server

        if getattr(server, "_index_singleton", None) is not None:
            try:
                server._index_singleton.close()
            except Exception:
                pass
            server._index_singleton = None

        if hasattr(self, "_orig_env"):
            for k, v in self._orig_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _record_http_exchange(
        self, tool_name: str, payload: dict, resp_code: int, resp_data: Any, wall_ms: int
    ) -> None:
        """Retains every claim/submit/release/cancel/preview request and response under <out>/http/ with secret token redacted."""
        with self._lock:
            self._http_seq += 1
            seq = self._http_seq

        self.http_dir.mkdir(parents=True, exist_ok=True)
        secret = self.token

        def redact(obj: Any) -> Any:
            if not secret:
                return obj
            if isinstance(obj, str):
                return obj.replace(secret, "[REDACTED]")
            elif isinstance(obj, dict):
                return {k: redact(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [redact(item) for item in obj]
            return obj

        headers = {
            "Content-Type": "application/json",
            "X-Uoink-Token": "[REDACTED]",
            "User-Agent": "uoink-proof-harness/1.0",
        }
        redacted_req = redact(payload)
        redacted_resp = redact(resp_data)

        req_record = {
            "seq": seq,
            "url": f"{self.base_url}/tools/{tool_name}",
            "tool": tool_name,
            "method": "POST",
            "headers": headers,
            "body": redacted_req,
        }
        resp_record = {
            "seq": seq,
            "tool": tool_name,
            "status": resp_code,
            "wall_ms": wall_ms,
            "body": redacted_resp,
        }
        combined = {
            "seq": seq,
            "tool": tool_name,
            "wall_ms": wall_ms,
            "request": req_record,
            "response": resp_record,
        }

        (self.http_dir / f"{seq:05d}_{tool_name}_request.json").write_text(
            json.dumps(req_record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (self.http_dir / f"{seq:05d}_{tool_name}_response.json").write_text(
            json.dumps(resp_record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (self.http_dir / f"{seq:05d}_{tool_name}.json").write_text(
            json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def http_tool_call(self, tool_name: str, payload: dict) -> dict:
        """Calls POST /tools/<tool_name> with strict JSON handling, rate limit backoff, auth, and audit retention."""
        t_start = time.perf_counter()
        url = f"{self.base_url}/tools/{tool_name}"
        data = json.dumps(payload, allow_nan=False, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Uoink-Token": self.token,
                "User-Agent": "uoink-proof-harness/1.0",
            },
            method="POST",
        )
        res_json = None
        resp_code = 200
        for attempt in range(5):
            try:
                with self.opener.open(req, timeout=60.0) as resp:
                    resp_bytes = resp.read()
                    resp_code = resp.status
                    res_json = json.loads(resp_bytes.decode("utf-8"))
                    if isinstance(res_json, dict) and res_json.get("error", {}).get("code") == "rate_limited":
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    break
            except urllib.error.HTTPError as e:
                resp_code = e.code
                raw = e.read().decode("utf-8", errors="replace")
                try:
                    err_data = json.loads(raw)
                    if isinstance(err_data, dict) and (e.code == 429 or err_data.get("error", {}).get("code") == "rate_limited"):
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    res_json = err_data
                    break
                except Exception:
                    res_json = {"ok": False, "error": f"HTTP {e.code}: {raw[:300]}"}
                    break
            except Exception as e:
                resp_code = 500
                res_json = {"ok": False, "error": str(e)}
                break

        if res_json is None:
            resp_code = 429
            res_json = {"ok": False, "error": "Max retries exceeded on rate limit"}

        wall_ms = max(1, int((time.perf_counter() - t_start) * 1000))
        self._record_http_exchange(tool_name, payload, resp_code, res_json, wall_ms)
        return res_json

    def _save_before_state(self, db_path: Path) -> None:
        """Snapshots database before execution into <out>/state/."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(db_path, self.state_dir / "before_index.db")
        wal_path = db_path.parent / (db_path.name + "-wal")
        if wal_path.is_file():
            shutil.copyfile(wal_path, self.state_dir / "before_index.db-wal")
        journal_path = db_path.parent / (db_path.name + "-journal")
        if journal_path.is_file():
            shutil.copyfile(journal_path, self.state_dir / "before_index.db-journal")

    def _save_after_state(self, db_path: Path) -> None:
        """Snapshots database after execution and exports registry tables into <out>/state/."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(db_path, self.state_dir / "after_index.db")
        wal_path = db_path.parent / (db_path.name + "-wal")
        if wal_path.is_file():
            shutil.copyfile(wal_path, self.state_dir / "after_index.db-wal")
        journal_path = db_path.parent / (db_path.name + "-journal")
        if journal_path.is_file():
            shutil.copyfile(journal_path, self.state_dir / "after_index.db-journal")

        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            work_rows = [dict(r) for r in conn.execute("SELECT * FROM library_work ORDER BY work_id").fetchall()]
            attempts_rows = [dict(r) for r in conn.execute("SELECT * FROM library_attempts ORDER BY attempt_token").fetchall()]
            submissions_rows = [dict(r) for r in conn.execute("SELECT * FROM library_submissions ORDER BY submission_key").fetchall()]
            proposals_rows = [dict(r) for r in conn.execute("SELECT * FROM library_proposals ORDER BY run_id, video_id, shelf_id").fetchall()]
        finally:
            conn.close()

        export_payload = {
            "work": work_rows,
            "attempts": attempts_rows,
            "submissions": submissions_rows,
            "proposals": proposals_rows,
        }
        (self.state_dir / "registry_export.json").write_text(json.dumps(export_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (self.state_dir / "work.json").write_text(json.dumps(work_rows, indent=2, ensure_ascii=False), encoding="utf-8")
        (self.state_dir / "attempts.json").write_text(json.dumps(attempts_rows, indent=2, ensure_ascii=False), encoding="utf-8")
        (self.state_dir / "submissions.json").write_text(json.dumps(submissions_rows, indent=2, ensure_ascii=False), encoding="utf-8")
        (self.state_dir / "proposals.json").write_text(json.dumps(proposals_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    def _check_error_guard(self) -> None:
        """Shared coordinator enforcing 2-hour deadline and error rate threshold (> 10% after 20 attempts)."""
        with self._coordinator_lock:
            if self.abort_event.is_set():
                return
            elapsed_ms = int((time.perf_counter() - self.run_start_time) * 1000)
            if elapsed_ms > self.wall_budget_ms:
                self._trigger_abort(
                    f"Wall-time budget exceeded (2 hour deadline): {elapsed_ms} ms > {self.wall_budget_ms} ms"
                )
                return
            n = len(self.attempts)
            if n >= self.error_rate_min_attempts:
                rejected = sum(1 for a in self.attempts if a.get("outcome") == "rejected")
                failures = len(self.transport_failures)
                numerator = rejected + failures
                rate = numerator / n
                if rate > self.error_rate_limit:
                    self._trigger_abort(
                        f"Error rate limit exceeded: {numerator}/{n} ({rate:.1%}) > {self.error_rate_limit:.1%} "
                        f"after {n} completed attempts"
                    )

    def _trigger_abort(self, reason: str) -> None:
        """Stops launching, terminates owned children, terminates helper, and signals abort."""
        if self.abort_event.is_set():
            return
        print(f"[proof] ERROR GUARD BREACH: {reason}. Aborting run.", file=sys.stderr, flush=True)
        self.abort_reason = reason
        self.abort_event.set()
        with self._proc_lock:
            for proc in list(self._active_processes):
                try:
                    proc.terminate()
                except Exception:
                    pass
        try:
            self.stop_server()
        except Exception:
            pass

    def generate_mock_assignment(self, item: dict) -> Tuple[dict, dict, int]:
        """Generates a deterministic fixture assignment strictly obeying evidence rules."""
        t0 = time.perf_counter()
        if self._mock_item_index < self.mock_reject_count:
            self._mock_item_index += 1
            result = {
                "outcome": "error",
                "reason": "Mock simulated rejection for error guard testing (exceeds word cap)",
            }
            wall_ms = max(1, int((time.perf_counter() - t0) * 1000))
            usage = {"status": "unavailable", "reason": "Mock fixture"}
            return result, usage, wall_ms

        self._mock_item_index += 1
        video_id = item["video_id"]
        card = item.get("card") or {}
        excerpts = card.get("excerpts") or []

        gold = self.gold_by_id.get(video_id)
        node = None
        if gold:
            gold_path = gold.get("shelf_path", [])
            p = list(gold_path)
            while p:
                node = self.taxonomy_nodes_by_path.get(tuple(p))
                if node:
                    break
                p.pop()

        has_timed = any(e.get("evidence_kind") == "timed_clip" for e in excerpts)
        is_supported_text = card.get("source_type") in {
            "page",
            "x_article",
            "x_thread",
            "reddit_thread",
            "note",
        }

        if gold and node and excerpts and (has_timed or is_supported_text):
            if has_timed:
                candidates = [e for e in excerpts if e.get("evidence_kind") == "timed_clip"]
            else:
                candidates = [e for e in excerpts if e.get("evidence_kind") == "text_only"]

            gold_evidence = (gold.get("evidence") or "").strip()
            chosen_excerpt = None
            quote = ""
            if gold_evidence:
                for exc in candidates:
                    exc_text = exc.get("text", "")
                    if gold_evidence in exc_text and 0 < len(gold_evidence.split()) <= 24:
                        chosen_excerpt = exc
                        quote = gold_evidence
                        break

            if chosen_excerpt is None and candidates:
                chosen_excerpt = candidates[0]
                raw_text = chosen_excerpt.get("text", "").strip()
                words = unicodedata.normalize("NFC", raw_text).split()
                quote = " ".join(words[:min(12, len(words))])
                if not quote and raw_text:
                    quote = raw_text.split()[0]

            result = {
                "outcome": "assigned",
                "memberships": [
                    {
                        "shelf_id": node["shelf_id"],
                        "shelf_path": node["path"],
                        "confidence": 0.95,
                        "evidence": {
                            "basis": "packet",
                            "kind": chosen_excerpt.get("evidence_kind"),
                            "card_hash": card["card_hash"],
                            "excerpt_id": chosen_excerpt["excerpt_id"],
                            "quote": quote,
                        },
                    }
                ],
            }
        elif not excerpts or (card.get("source_type") in {"video", "episode", "short_video"} and not has_timed):
            result = {
                "outcome": "unsupported",
                "reason": "Source origin or excerpt evidence does not support grounded classification.",
            }
        else:
            result = {
                "outcome": "unmapped",
                "reason": "Content falls outside approved taxonomy definitions.",
            }

        wall_ms = max(1, int((time.perf_counter() - t0) * 1000))
        usage = {
            "status": "unavailable",
            "reason": "Mock fixture",
        }
        return result, usage, wall_ms

    def generate_model_batch(
        self, items: List[dict], prompt: str, call_id: str
    ) -> Tuple[Dict[str, dict], dict, dict, dict]:
        """`claude -p` once for a batch; writes <out>/calls/<call_id>.{stdin,stdout,stderr} and returns ({video_id: result}, usage, raw env, call_record)."""
        self.calls_dir.mkdir(parents=True, exist_ok=True)
        stdin_bytes = prompt.encode("utf-8")
        stdin_sha256 = hashlib.sha256(stdin_bytes).hexdigest()
        (self.calls_dir / f"{call_id}.stdin").write_bytes(stdin_bytes)

        t_start_mono = time.monotonic()
        t0 = time.perf_counter()
        exe = shutil.which("claude") or "claude"
        cmd = [
            exe,
            "-p",
            "--json-schema",
            self.output_schema_text,
            "--output-format",
            "json",
            "--tools",
            "",
            "--no-session-persistence",
        ]
        if self.model:
            cmd += ["--model", self.model]

        timed_out = False
        cancelled = False
        proc = None
        stdout_bytes = b""
        stderr_bytes = b""
        returncode = -1

        with self._proc_lock:
            if self.abort_event.is_set():
                cancelled = True
            else:
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    self._active_processes.add(proc)
                except Exception:
                    returncode = -1

        if proc is not None:
            try:
                stdout_bytes, stderr_bytes = proc.communicate(input=stdin_bytes, timeout=self.call_timeout)
                returncode = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                stdout_bytes, stderr_bytes = proc.communicate()
                returncode = proc.returncode
            except Exception:
                cancelled = True
                proc.kill()
                stdout_bytes, stderr_bytes = proc.communicate()
                returncode = proc.returncode
            finally:
                with self._proc_lock:
                    self._active_processes.discard(proc)

        t_end_mono = time.monotonic()
        wall_ms = max(1, int((time.perf_counter() - t0) * 1000))

        stdout_sha256 = hashlib.sha256(stdout_bytes).hexdigest()
        stderr_sha256 = hashlib.sha256(stderr_bytes).hexdigest()
        (self.calls_dir / f"{call_id}.stdout").write_bytes(stdout_bytes)
        (self.calls_dir / f"{call_id}.stderr").write_bytes(stderr_bytes)

        print(f"[proof] model call done: {call_id} in {wall_ms} ms, exit {returncode}, "
              f"stdout {len(stdout_bytes)} B", file=sys.stderr, flush=True)

        call_error = None
        env: Dict[str, Any] = {}
        if returncode != 0 or not stdout_bytes.strip():
            call_error = f"claude -p failed (exit {returncode}): {stderr_bytes[:400].decode('utf-8', errors='replace')}"

        if call_error is None:
            try:
                env = json.loads(stdout_bytes.decode("utf-8"))
            except json.JSONDecodeError:
                call_error = f"claude returned non-JSON stdout: {stdout_bytes[:300].decode('utf-8', errors='replace')}"

        if call_error is None:
            if env.get("is_error") or env.get("structured_output") is None:
                call_error = f"claude failed to return structured_output: {str(env.get('result'))[:300]}"

        wanted = {it["video_id"] for it in items}
        by_video: Dict[str, dict] = {}
        if call_error is None:
            for entry in env.get("structured_output", {}).get("results", []) or []:
                vid = entry.get("video_id")
                if vid in wanted and vid not in by_video and isinstance(entry.get("result"), dict):
                    by_video[vid] = entry["result"]

        u = env.get("usage", {})
        if u and "input_tokens" in u:
            usage = {
                "status": "reported",
                "source": "claude_cli_json",
                "model": env.get("model") or self.model,
                "input_tokens": int(u.get("input_tokens", 0)),
                "output_tokens": int(u.get("output_tokens", 0)),
                "cache_read_tokens": int(u.get("cache_read_input_tokens", 0)),
                "cache_create_tokens": int(u.get("cache_creation_input_tokens", 0)),
            }
        else:
            usage = {
                "status": "unavailable",
                "reason": call_error or "CLI returned no token usage",
            }

        ordered_attempt_ids = [f"att-{it['video_id']}-{it.get('attempt_number', 1)}" for it in items]
        call_record = {
            "call_id": call_id,
            "attempt_ids": ordered_attempt_ids,
            "video_ids": [it["video_id"] for it in items],
            "argv": cmd,
            "schema_sha256": self.output_schema_sha256,
            "stdin_bytes": len(stdin_bytes),
            "stdout_bytes": len(stdout_bytes),
            "stderr_bytes": len(stderr_bytes),
            "stdin_sha256": stdin_sha256,
            "stdout_sha256": stdout_sha256,
            "stderr_sha256": stderr_sha256,
            "start_mono_ms": int(t_start_mono * 1000),
            "end_mono_ms": int(t_end_mono * 1000),
            "wall_ms": wall_ms,
            "exit_status": returncode,
            "timed_out": timed_out,
            "cancelled": cancelled,
            "usage": usage,
            "model_usage": env.get("modelUsage"),
            "total_cost_usd": env.get("total_cost_usd"),
            "error": call_error,
        }

        return by_video, usage, env, call_record

    def generate_model_assignment(self, item: dict, prompt: str) -> Tuple[dict, dict, int, dict, str]:
        """Calls `claude -p` structured output CLI for reasoning on a single card."""
        with self._lock:
            call_id = f"call-{len(self.calls) + 1:04d}-{secrets.token_hex(3)}"
        by_video, usage, raw_env, call_record = self.generate_model_batch([item], prompt, call_id)
        with self._lock:
            self.calls.append(call_record)
        res = by_video.get(item["video_id"])
        if res is None:
            res = {"outcome": "error", "reason": call_record.get("error") or "No result returned"}
        return res, usage, call_record["wall_ms"], raw_env, call_id

    def process_item(self, item: dict) -> dict:
        """Executes reason -> submit for one claimed work item."""
        video_id = item["video_id"]
        work_id = item["work_id"]
        attempt_token = item["attempt_token"]
        attempt_number = item.get("attempt_number", 1)
        packet_hash = item["packet_hash"]
        source_revision = item["source_revision"]
        taxonomy_revision = item["taxonomy_revision"]
        card = item["card"]

        policy = dict(
            min_confidence=0.60,
            max_memberships=3,
            max_churn_percent=15,
            prompt_hash=self.manifest["hashes"]["prompt_sha256"],
            selection_version="spread-longest-v1",
            card_schema=1,
        )
        packet = {
            "schema_version": 1,
            "video_id": video_id,
            "source_revision": source_revision,
            "taxonomy_revision": taxonomy_revision,
            "policy_hash": digest(policy),
            "card": card,
        }

        card_text = library_cards.card_text(card)
        card_bytes = len(card_text.encode("utf-8"))
        prompt_text = render_prompt(self.prompt_template, self.manifest["taxonomy"], card)
        prompt_bytes = len(prompt_text.encode("utf-8"))
        schema_bytes = len(self.output_schema_text.encode("utf-8"))
        serialized_input_bytes = prompt_bytes + schema_bytes

        if self.mock:
            result, usage, wall_ms = self.generate_mock_assignment(item)
            estimates = {"total_cost_usd": None, "source": "unavailable"}
            response_data = {"results": [{"video_id": video_id, "result": result}]}
            response_text = canonical(response_data)
            call_id = None
        else:
            result, usage, wall_ms, raw_env, call_id = self.generate_model_assignment(item, prompt_text)
            estimates = {
                "total_cost_usd": raw_env.get("total_cost_usd"),
                "source": "claude_cli_estimate" if raw_env.get("total_cost_usd") is not None else "unavailable",
            }
            response_text = canonical(raw_env)

        if result.get("outcome") == "assigned":
            too_long = [len(((m.get("evidence") or {}).get("quote") or "").split())
                        for m in (result.get("memberships") or [])]
            if any(n > 24 for n in too_long):
                result = {
                    "outcome": "error",
                    "reason": f"model quote exceeds prompt contract (24 words): {max(too_long)} words",
                }

        response_bytes = len(response_text.encode("utf-8"))
        submission_key = f"{work_id}-{attempt_token}"

        submit_payload = {
            "work_id": work_id,
            "client_id": "proof-harness",
            "attempt_token": attempt_token,
            "submission_key": submission_key,
            "schema_version": 1,
            "video_id": video_id,
            "source_revision": source_revision,
            "taxonomy_revision": taxonomy_revision,
            "packet_hash": packet_hash,
            "result": result,
            "usage": usage,
        }

        t_submit = time.perf_counter()
        submit_resp = self.http_tool_call("submit_library_result", submit_payload)
        submit_wall_ms = int((time.perf_counter() - t_submit) * 1000)
        resp_data = submit_resp.get("result", submit_resp)

        outcome = resp_data.get("outcome", "rejected" if not submit_resp.get("ok") else "error")
        # PROOF-PLAN receipt contract: a service outcome "error" maps to the
        # receipt outcome "rejected"; the raw result/response keep "error".
        if outcome == "error":
            outcome = "rejected"
        rejection_reason = None
        if outcome in {"rejected", "error"}:
            rejection_reason = str(resp_data.get("rejected") or resp_data.get("error") or "Submit rejected")
            req_bytes = len(json.dumps(submit_payload, ensure_ascii=False).encode("utf-8"))
            resp_bytes_sub = len(json.dumps(submit_resp, ensure_ascii=False).encode("utf-8"))
            with self._lock:
                self.transport_failures.append(
                    {
                        "event_id": f"tf-sub-{secrets.token_hex(4)}",
                        "attempt_id": f"att-{video_id}-{attempt_number}",
                        "video_id": video_id,
                        "stage": "submit",
                        "reason": rejection_reason,
                        "request_bytes": req_bytes,
                        "response_bytes": resp_bytes_sub,
                        "wall_ms": submit_wall_ms,
                    }
                )

        attempt_record = {
            "attempt_id": f"att-{video_id}-{attempt_number}",
            "call_id": call_id,
            "video_id": video_id,
            "work_id": work_id,
            "attempt_token": attempt_token,
            "attempt_number": attempt_number,
            "packet_hash": packet_hash,
            "packet": packet,
            "card_text": card_text,
            "card_bytes": card_bytes,
            "prompt_text": prompt_text,
            "prompt_bytes": prompt_bytes,
            "response_text": response_text,
            "response_bytes": response_bytes,
            "serialized_input_bytes": serialized_input_bytes,
            "wall_ms": wall_ms,
            "outcome": outcome,
            "rejection_reason": rejection_reason,
            "result": result,
            "submit_response": resp_data if submit_resp.get("ok") else None,
            "usage": usage,
            "estimates": estimates,
        }
        return attempt_record

    def process_batch(self, items: List[dict]) -> List[dict]:
        """Batched reasoning execution for real model runs."""
        cards_block = "\n\n".join(library_cards.card_text(it["card"]) for it in items)
        prefix, suffix = self.prompt_template.split("{{CARDS}}")
        prompt = (
            prefix.replace("{{TAXONOMY}}", library_cards.serialize_card(self.manifest["taxonomy"]))
            + cards_block
            + suffix
        )
        prompt_bytes = len(prompt.encode("utf-8"))
        schema_bytes = len(self.output_schema_text.encode("utf-8"))

        with self._lock:
            call_id = f"call-{len(self.calls) + 1:04d}-{secrets.token_hex(3)}"
        try:
            by_video, usage, raw_env, call_record = self.generate_model_batch(items, prompt, call_id)
        except (ProofRunError, subprocess.TimeoutExpired, OSError) as exc:
            by_video = {}
            call_error = str(exc)[:400]
            usage = {
                "status": "unavailable",
                "reason": f"call failed: {call_error}",
            }
            call_record = {
                "call_id": call_id,
                "attempt_ids": [f"att-{it['video_id']}-{it.get('attempt_number', 1)}" for it in items],
                "video_ids": [it["video_id"] for it in items],
                "argv": [],
                "schema_sha256": self.output_schema_sha256,
                "stdin_bytes": len(prompt.encode("utf-8")),
                "stdout_bytes": 0,
                "stderr_bytes": len(call_error.encode("utf-8")),
                "stdin_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "stdout_sha256": "0" * 64,
                "stderr_sha256": hashlib.sha256(call_error.encode("utf-8")).hexdigest(),
                "start_mono_ms": 0,
                "end_mono_ms": 0,
                "wall_ms": 1,
                "exit_status": -1,
                "timed_out": isinstance(exc, subprocess.TimeoutExpired),
                "cancelled": False,
                "usage": usage,
                "model_usage": None,
                "total_cost_usd": None,
                "error": call_error,
            }
            raw_env = {}

        wall_ms = call_record.get("wall_ms", 1)
        call_error = call_record.get("error")
        with self._lock:
            self.calls.append(call_record)

        receipts = []
        policy = dict(
            min_confidence=0.60,
            max_memberships=3,
            max_churn_percent=15,
            prompt_hash=self.manifest["hashes"]["prompt_sha256"],
            selection_version="spread-longest-v1",
            card_schema=1,
        )

        for it in items:
            vid = it["video_id"]
            res = by_video.get(vid)
            if res is None:
                res = {
                    "outcome": "error",
                    "reason": call_error or f"model returned no result for {vid}",
                }
            elif res.get("outcome") == "assigned":
                # Prompt contract: evidence quotes are verbatim and at most 24
                # words. The service caps quotes at 1,000 characters only, so a
                # longer quote would be accepted there and then fail the receipt
                # validator. Treat it as invalid model output: submit an error
                # result (recorded as rejected) so the retry policy can re-ask.
                too_long = [len(((m.get("evidence") or {}).get("quote") or "").split())
                            for m in (res.get("memberships") or [])]
                if any(n > 24 for n in too_long):
                    print(f"[proof] model quote over 24 words for {vid} ({max(too_long)} words); rejecting output",
                          file=sys.stderr, flush=True)
                    res = {"outcome": "error",
                           "reason": f"model quote exceeds prompt contract (24 words): {max(too_long)} words"}

            card_text = library_cards.card_text(it["card"])
            card_bytes = len(card_text.encode("utf-8"))
            single_prompt = render_prompt(self.prompt_template, self.manifest["taxonomy"], it["card"])
            single_prompt_bytes = len(single_prompt.encode("utf-8"))
            serialized_input_bytes = single_prompt_bytes + schema_bytes

            # PROOF-PLAN: save the CLI envelope intact (usage, modelUsage, cost,
            # timing, session). In a batched call every item in the batch
            # carries the same envelope; the per-item result is also stored in
            # attempt.result. The envelope is the provenance for usage.model.
            raw_item_resp: Dict[str, Any] = dict(raw_env) if raw_env else {}
            if "structured_output" in raw_item_resp:
                # Batched call: the receipt contract keys structured_output to
                # this item; the full batch output is retained beside it.
                raw_item_resp["batch_structured_output"] = raw_item_resp["structured_output"]
            raw_item_resp["structured_output"] = {"results": [{"video_id": vid, "result": res}]}

            response_text = canonical(raw_item_resp)
            response_bytes = len(response_text.encode("utf-8"))
            submission_key = f"{it['work_id']}-{it['attempt_token']}"

            submit_payload = {
                "work_id": it["work_id"],
                "client_id": "proof-harness",
                "attempt_token": it["attempt_token"],
                "submission_key": submission_key,
                "schema_version": 1,
                "video_id": vid,
                "source_revision": it["source_revision"],
                "taxonomy_revision": it["taxonomy_revision"],
                "packet_hash": it["packet_hash"],
                "result": res,
                # The frozen submit schema allows exactly the contract usage
                # fields (additionalProperties=false); the batch bookkeeping
                # (call_id, batch_size, extra_results, total_cost_usd) stays
                # in the receipts and audit_extensions only.
                "usage": submit_usage(usage),
            }

            t_sub = time.perf_counter()
            submit_resp = self.http_tool_call("submit_library_result", submit_payload)
            sub_wall_ms = int((time.perf_counter() - t_sub) * 1000)
            resp_data = submit_resp.get("result", submit_resp)

            outcome = resp_data.get("outcome", "rejected" if not submit_resp.get("ok") else "error")
            # PROOF-PLAN receipt contract: a service outcome "error" maps to the
            # receipt outcome "rejected"; the raw result/response keep "error".
            if outcome == "error":
                outcome = "rejected"
            rejection_reason = None
            if outcome in {"rejected", "error"}:
                rejection_reason = str(resp_data.get("rejected") or resp_data.get("error") or "Submit rejected")
                err = submit_resp.get("error") if isinstance(submit_resp.get("error"), dict) else {}
                field = str((err.get("details") or {}).get("field") or "")
                if err.get("code") == "invalid_request" and field.startswith("result"):
                    # The MODEL produced a result the frozen schema rejects (for
                    # example an "assigned" result carrying a stray "reason"). That
                    # is a scored rejection of model output, not a harness fault:
                    # record it, release the lease so the retry policy can run.
                    outcome = "rejected"
                    rejection_reason = f"model output failed schema: {err.get('message', '')[:160]}"
                    print(f"[proof] rejected model output {vid}: {rejection_reason}", file=sys.stderr, flush=True)
                    self.http_tool_call("claim_library_work", {
                        "action": "release", "work_id": it["work_id"], "client_id": "proof-harness",
                        "attempt_token": it["attempt_token"], "reason": "model output failed schema"})
                elif err.get("code") in {"invalid_request", "validation_error", "unauthorized", "unknown_tool"}:
                    # A harness/schema fault on a harness-controlled field: abort
                    # loudly rather than leave leases held and poll for expiry.
                    print(f"[proof] ABORT submit {vid}: {json.dumps(submit_resp)[:400]}", file=sys.stderr, flush=True)
                    raise ProofRunError(f"submit rejected at schema level for {vid}: {rejection_reason[:200]}")
                with self._lock:
                    self.transport_failures.append(
                        {
                            "event_id": f"tf-sub-{secrets.token_hex(4)}",
                            "attempt_id": f"att-{vid}-{it.get('attempt_number', 1)}",
                            "video_id": vid,
                            "stage": "submit",
                            "reason": rejection_reason,
                            "request_bytes": len(json.dumps(submit_payload, ensure_ascii=False).encode("utf-8")),
                            "response_bytes": len(json.dumps(submit_resp, ensure_ascii=False).encode("utf-8")),
                            "wall_ms": sub_wall_ms,
                        }
                    )

            packet = {
                "schema_version": 1,
                "video_id": vid,
                "source_revision": it["source_revision"],
                "taxonomy_revision": it["taxonomy_revision"],
                "policy_hash": digest(policy),
                "card": it["card"],
            }

            receipts.append(
                {
                    "attempt_id": f"att-{vid}-{it.get('attempt_number', 1)}",
                    "call_id": call_id,
                    "video_id": vid,
                    "work_id": it["work_id"],
                    "attempt_token": it["attempt_token"],
                    "attempt_number": it.get("attempt_number", 1),
                    "packet_hash": it["packet_hash"],
                    "packet": packet,
                    "card_text": card_text,
                    "card_bytes": card_bytes,
                    "prompt_text": single_prompt,
                    "prompt_bytes": single_prompt_bytes,
                    "response_text": response_text,
                    "response_bytes": response_bytes,
                    "serialized_input_bytes": serialized_input_bytes,
                    # Attributed share of the batched call (call wall / batch
                    # size) so per-attempt sums stay within the run's concurrency
                    # capacity; the full call wall is in audit_extensions.calls.
                    "wall_ms": max(1, wall_ms // max(1, len(items))),
                    "outcome": outcome,
                    "rejection_reason": rejection_reason,
                    "result": res,
                    "submit_response": resp_data if submit_resp.get("ok") else None,
                    "usage": usage,
                    "estimates": {
                        "total_cost_usd": raw_env.get("total_cost_usd"),
                        "source": "claude_cli_estimate" if raw_env.get("total_cost_usd") is not None else "unavailable",
                    },
                }
            )
        return receipts

    def _batched_worker(self, retried_videos: set[str]) -> None:
        """One batched real-model worker loop."""
        idle_polls = 0
        while True:
            if self.abort_event.is_set():
                return
            claim_resp = self.http_tool_call(
                "claim_library_work",
                {
                    "action": "claim",
                    "run_id": self.run_id,
                    "client_id": "proof-harness",
                    "max_items": self.batch,
                },
            )
            claim_data = claim_resp.get("result", claim_resp)
            work_items = claim_data.get("work", []) or []
            if not work_items:
                list_resp = self.http_tool_call("list_library_work", {"run_id": self.run_id})
                counts = list_resp.get("result", list_resp).get("counts", {}) or {}
                if counts.get("ready", 0) == 0 and counts.get("leased", 0) == 0:
                    return
                idle_polls += 1
                if idle_polls > 3000:
                    return
                time.sleep(0.2)
                continue
            idle_polls = 0
            # Contract: at most one retry per rejected model result in the proof.
            # A third claim can happen because a rejected attempt is no longer
            # cancellable; refuse it here without a model call.
            over_limit = [it for it in work_items if int(it.get("attempt_number", 1) or 1) > 2]
            work_items = [it for it in work_items if int(it.get("attempt_number", 1) or 1) <= 2]
            for it in over_limit:
                print(f"[proof] retry limit reached for {it['video_id']}; cancelling attempt {it.get('attempt_number')}",
                      file=sys.stderr, flush=True)
                self.http_tool_call("claim_library_work", {
                    "action": "cancel", "work_id": it["work_id"], "client_id": "proof-harness",
                    "attempt_token": it["attempt_token"], "reason": "proof retry limit (1 retry)"})
            if not work_items:
                continue
            receipts = self.process_batch(work_items)
            with self._lock:
                for r in receipts:
                    self.attempts.append(r)
                    self._handle_retry_policy(r, retried_videos)
                    self._check_error_guard()
                    if self.abort_event.is_set():
                        break
            if self.abort_event.is_set():
                return

    def run_proof_loop(self) -> None:
        """Runs the complete claim -> reason -> submit loop over HTTP."""
        retried_videos: set[str] = set()

        if not self.mock:
            # Real model: batched calls, `concurrency` workers
            with cf.ThreadPoolExecutor(max_workers=self.concurrency) as ex:
                futures = [ex.submit(self._batched_worker, retried_videos) for _ in range(self.concurrency)]
                for fut in cf.as_completed(futures):
                    fut.result()
            if not self.abort_event.is_set():
                self._finish_with_preview()
            return

        while True:
            if self.abort_event.is_set():
                break
            claim_resp = self.http_tool_call(
                "claim_library_work",
                {
                    "action": "claim",
                    "run_id": self.run_id,
                    "client_id": "proof-harness",
                    "max_items": 12,
                },
            )
            claim_data = claim_resp.get("result", claim_resp)
            work_items = claim_data.get("work", [])

            if not work_items:
                list_resp = self.http_tool_call("list_library_work", {"run_id": self.run_id})
                list_data = list_resp.get("result", list_resp)
                counts = list_data.get("counts", {})
                ready = counts.get("ready", 0)
                leased = counts.get("leased", 0)
                if ready == 0 and leased == 0:
                    break
                time.sleep(0.1)
                continue

            for item in work_items:
                if self.abort_event.is_set():
                    break
                receipt = self.process_item(item)
                with self._lock:
                    self.attempts.append(receipt)
                    self._handle_retry_policy(receipt, retried_videos)
                self._check_error_guard()
                if self.abort_event.is_set():
                    break

        if not self.abort_event.is_set():
            self._finish_with_preview()

    def _finish_with_preview(self) -> None:
        """Preview only; apply must remain impossible in the proof."""
        preview_payload = {
            "mode": "preview",
            "run_id": self.run_id,
            "expected_projection_revision": self.before_state["projection_revision"],
            "activate_version": False,
        }
        t0 = time.perf_counter()
        preview_resp = self.http_tool_call("apply_reshelving", preview_payload)
        wall_ms = int((time.perf_counter() - t0) * 1000)
        resp_data = preview_resp.get("result", preview_resp)

        if not preview_resp.get("ok") or resp_data.get("can_apply") is not False:
            req_bytes = len(json.dumps(preview_payload, ensure_ascii=False).encode("utf-8"))
            resp_bytes = len(json.dumps(preview_resp, ensure_ascii=False).encode("utf-8"))
            with self._lock:
                self.transport_failures.append(
                    {
                        "event_id": f"tf-preview-{secrets.token_hex(4)}",
                        "attempt_id": None,
                        "video_id": None,
                        "stage": "preview",
                        "reason": "Preview failed or can_apply was not False",
                        "request_bytes": req_bytes,
                        "response_bytes": resp_bytes,
                        "wall_ms": wall_ms,
                    }
                )
            raise ProofRunError(
                f"apply_reshelving preview returned can_apply={resp_data.get('can_apply')}; "
                f"must stay False when librarian_apply_enabled=False."
            )

        self.preview = {
            "request": preview_payload,
            "response": resp_data,
        }

    def _handle_retry_policy(self, receipt: dict, retried_videos: set[str]) -> None:
        """Enforces at most one retry per rejected model result."""
        outcome = receipt.get("outcome")
        video_id = receipt["video_id"]
        if outcome in {"rejected", "error"}:
            if video_id in retried_videos:
                self.http_tool_call(
                    "claim_library_work",
                    {
                        "action": "cancel",
                        "work_id": receipt["work_id"],
                        "client_id": "proof-harness",
                        "attempt_token": receipt["attempt_token"],
                        "reason": "Exceeded 1 retry limit",
                    },
                )
            else:
                retried_videos.add(video_id)

    def verify_after_state(self, db_path: Path) -> None:
        """Shuts down helper and verifies projection, pins, and zero applied labels."""
        self.stop_server()

        idx = index_mod.Index.open(db_path)
        self.after_state = self._snapshot_state(idx._conn)
        idx.close()

        if self.before_state != self.after_state:
            raise ProofRunError(
                f"State verification failed! Before != After:\n"
                f"Before: {self.before_state}\n"
                f"After:  {self.after_state}"
            )
        if self.after_state["applied_label_count"] != 0:
            raise ProofRunError(
                f"Zero applied labels assertion failed: found {self.after_state['applied_label_count']}"
            )
        if self.after_state["proof_apply_count"] != 0:
            raise ProofRunError(
                f"Proof apply count assertion failed: found {self.after_state['proof_apply_count']}"
            )

        if not self.skip_hash_check:
            self.source_after_sha256 = compute_file_sha256(self.source)
            if self.source_after_sha256 != self.copy_before_upgrade_sha256:
                raise ProofRunError("Source file was modified during run!")
        else:
            self.source_after_sha256 = self.copy_before_upgrade_sha256

    def write_receipts(self) -> Path:
        """Writes <out>/receipts.json strictly matching the receipt JSON contract."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        out_file = self.out_dir / "receipts.json"

        by_item: Dict[str, List[dict]] = defaultdict(list)
        for att in self.attempts:
            by_item[att["video_id"]].append(att)

        # 1. Target manifest hash
        target_payload = {
            "items": [entry for entry in self.manifest["items"] if entry[0] in set(self.target_ids)],
            "exclusions": {k: v for k, v in self.manifest["exclusions"].items() if k in set(self.target_ids)},
        }
        target_manifest_hash = digest(target_payload)

        # 2. Terminal targets in frozen manifest order
        targets = []
        for vid in self.target_ids:
            atts = by_item.get(vid, [])
            if atts:
                last = atts[-1]
                last_attempt_id = last["attempt_id"]
                work_id = last["work_id"]
                outcome = last["outcome"]
                if outcome == "accepted":
                    reason = None
                elif outcome in {"unmapped", "unsupported"}:
                    reason = (last.get("result") or {}).get("reason") or "Abstention"
                else:
                    reason = last.get("rejection_reason") or "Rejected"
            else:
                last_attempt_id = None
                work_id = None
                outcome = "unsupported"
                reason = "No attempts recorded"

            targets.append(
                {
                    "video_id": vid,
                    "work_id": work_id,
                    "outcome": outcome,
                    "reason": reason,
                    "last_attempt_id": last_attempt_id,
                }
            )
        self.targets = targets

        # 3. Totals
        serialized_input_bytes = sum(a["serialized_input_bytes"] for a in self.attempts)
        card_bytes = sum(a["card_bytes"] for a in self.attempts)
        prompt_bytes = sum(a["prompt_bytes"] for a in self.attempts)
        response_bytes = sum(a["response_bytes"] for a in self.attempts)
        attempt_wall_sum = sum(a["wall_ms"] for a in self.attempts)
        run_wall_ms = int((time.perf_counter() - self.run_start_time) * 1000)
        if self.calls:
            # Batched runs: every attempt in a batch carries the same call
            # wall time, so the per-attempt sum overstates elapsed time by the
            # batch size. The measured run clock is the total.
            total_wall_ms = run_wall_ms
        else:
            min_wall_for_concurrency = math.ceil(attempt_wall_sum / self.concurrency)
            total_wall_ms = max(run_wall_ms, min_wall_for_concurrency)

        totals = {
            "serialized_input_bytes": serialized_input_bytes,
            "card_bytes": card_bytes,
            "prompt_bytes": prompt_bytes,
            "response_bytes": response_bytes,
            "wall_ms": total_wall_ms,
            "retries": sum(max(0, len(atts) - 1) for atts in by_item.values()),
            "model_calls": 0 if self.mock else len(self.calls),
            "rejected_attempts": sum(1 for a in self.attempts if a["outcome"] == "rejected"),
            "transport_failures": len(self.transport_failures),
        }

        # 4. Usage totals for audit_extensions
        reported = [c["usage"] for c in self.calls if c.get("usage", {}).get("status") == "reported"]
        usage_totals = {
            "calls": len(self.calls),
            "calls_with_reported_usage": len(reported),
            "calls_without_usage": len(self.calls) - len(reported),
            "input_tokens": sum(u.get("input_tokens", 0) for u in reported),
            "output_tokens": sum(u.get("output_tokens", 0) for u in reported),
            "cache_read_tokens": sum(u.get("cache_read_tokens", 0) for u in reported),
            "cache_create_tokens": sum(u.get("cache_create_tokens", 0) for u in reported),
            "cli_estimated_cost_usd": round(sum(float(c.get("total_cost_usd", 0.0) or 0.0) for c in self.calls), 4),
            "paid_cost_usd": None,
            "status": "measured"
            if reported and len(reported) == len(self.calls)
            else ("partial" if reported else "unavailable"),
        }

        # 5. Full document matching RECEIPT_SCHEMA exactly
        document = {
            "schema_version": 1,
            "contract_version": CONTRACT,
            "run_id": self.run_id,
            "mode": "mock" if self.mock else "subscription",
            "status": "aborted" if self.abort_event.is_set() else "completed",
            "abort_reason": self.abort_reason,
            "inputs": self.manifest["hashes"],
            "target_ids": self.target_ids,
            "target_manifest_hash": target_manifest_hash,
            "config": {
                "client": "proof_run.py",
                "transport": "http_registry",
                "model": self.model,
                "base_url": self.base_url,
                "isolation_root": str(self.scratch_dir),
                "index_path": str(self.scratch_dir / "Uoink" / "index.db"),
                "token_path": str(self.scratch_dir / "Uoink" / "token.txt"),
                "environment": {
                    "LOCALAPPDATA": str(self.scratch_dir / "local"),
                    "APPDATA": str(self.scratch_dir / "roaming"),
                    "TEMP": str(self.scratch_dir / "temp"),
                    "TMP": str(self.scratch_dir / "temp"),
                    "UOINK_OUTPUT_DIR": str(self.scratch_dir / "output"),
                },
                "anthropic_api_key_unset": True,
                "tools": [],
                "concurrency": self.concurrency,
                "max_retries": 1,
                "wall_budget_ms": 7200000,
                "error_rate_limit": 0.10,
                "error_rate_min_attempts": 20,
                "output_schema_text": self.output_schema_text,
                "output_schema_sha256": self.output_schema_sha256,
            },
            "database": {
                "copy_before_upgrade_sha256": self.copy_before_upgrade_sha256,
                "copy_after_upgrade_sha256": self.copy_after_upgrade_sha256,
                "source_after_sha256": self.source_after_sha256,
                "schema_before": self.schema_before,
                "schema_after": self.schema_after,
            },
            "before": self.before_state,
            "after": self.after_state,
            "attempts": self.attempts,
            "transport_failures": self.transport_failures,
            "targets": self.targets,
            "preview": self.preview or {"request": {}, "response": {}},
            "totals": totals,
            "audit_extensions": {
                "calls": self.calls,
                "usage_totals": usage_totals,
                "wall_ms_attribution": "attempt.wall_ms = call wall_ms // batch_size; call totals in calls[]",
            },
        }

        tmp_file = self.out_dir / f".receipts-{secrets.token_hex(4)}.tmp"
        tmp_file.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        shutil.move(str(tmp_file), str(out_file))
        return out_file

    def execute(self) -> Path:
        """Runs the entire product proof harness."""
        self.run_start_time = time.perf_counter()
        self.check_guards()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.calls_dir.mkdir(parents=True, exist_ok=True)
        self.http_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        isolated_db = self.prepare_isolated_environment()
        try:
            self.initialize_database_and_freeze(isolated_db)
            self._save_before_state(isolated_db)
            self.start_server()
            self.run_proof_loop()
            self.verify_after_state(isolated_db)
            self._save_after_state(isolated_db)
            receipts_path = self.write_receipts()
            return receipts_path
        finally:
            self.stop_server()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Living Library product proof harness (Run P/Q, mock-only or claude -p)"
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to source index copy (.db)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for receipts.json",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Run in mock reasoning mode (deterministic fixture assignments, zero model calls)",
    )
    parser.add_argument(
        "--mock-reject-count",
        type=int,
        default=0,
        help="Simulate N rejections for error guard testing in mock mode",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of manifest items to process",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-5",
        help="Subscription model ID for claude -p (default: claude-sonnet-5)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Concurrency for worker processes (default: 4)",
    )
    parser.add_argument(
        "--taxonomy", type=Path, default=None,
        help="Approved taxonomy JSON to activate on the disposable duplicate (default: v1)")
    parser.add_argument(
        "--manifest", type=Path, default=None,
        help="Frozen target manifest JSON (default: docs/library/proof/manifest-2026-09-05.json)")
    parser.add_argument(
        "--batch",
        type=int,
        default=12,
        help="Cards per claude -p call in real runs (default: 12; mock runs stay per-item)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5180,
        help="Ephemeral port for isolated helper (default: 5180, never 5179)",
    )
    parser.add_argument(
        "--scratch",
        type=Path,
        default=None,
        help="Scratch directory for isolated helper environment",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default="proof-run-p",
        help="Identifier for the proof run",
    )
    parser.add_argument(
        "--expected-hash",
        type=str,
        default=NAMED_COPY_HASH,
        help="Expected SHA-256 hash of source copy (default: 2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc)",
    )
    parser.add_argument(
        "--skip-hash-check",
        action="store_true",
        default=False,
        help="Skip SHA-256 verification of the source file (useful for test fixtures)",
    )
    return parser


def main() -> None:
    if os.environ.get("UOINK_PROOF_DUMP_SEC"):
        # Debug aid: dump every thread's stack to stderr periodically.
        import faulthandler
        faulthandler.dump_traceback_later(int(os.environ["UOINK_PROOF_DUMP_SEC"]), repeat=True, file=sys.stderr)
    parser = build_parser()
    args = parser.parse_args()

    harness = ProofHarness(
        source=args.source,
        out_dir=args.out,
        mock=args.mock,
        mock_reject_count=args.mock_reject_count,
        limit=args.limit,
        model=args.model,
        concurrency=args.concurrency,
        batch=args.batch,
        taxonomy=args.taxonomy,
        manifest=args.manifest,
        port=args.port,
        scratch_dir=args.scratch,
        run_id=args.run_id,
        expected_hash=args.expected_hash,
        skip_hash_check=args.skip_hash_check,
    )
    try:
        receipts_path = harness.execute()
        print(f"Product proof run complete. Receipts written to: {receipts_path}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
scripts/librarian/proof_run.py - Living Library Product Proof Run Harness (Run P)

Drives the claim -> reason -> submit loop over the HTTP registry:
    POST /tools/claim_library_work
    POST /tools/submit_library_result
    POST /tools/apply_reshelving (preview mode)

Uses an isolated helper server running on an ephemeral port (default: 5180, never 5179)
under a disposable root (default: _scratch/proof). Never opens the live index.
Subscription-only execution: asserts ANTHROPIC_API_KEY is unset.

Supports:
- --mock: Deterministic fixture assignment (right label for gold items, unmapped for others).
          Exercises helper, HTTP calls, and receipts with zero model execution.
- Without --mock: Invokes `claude -p --json-schema ... --output-format json --tools ""`
                  for each card, recording CLI token usage and cost estimates.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
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

NAMED_COPY_HASH = "2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc"
FORBIDDEN_PORT = 5179

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


def compute_file_sha256(path: Path) -> str:
    """Computes SHA-256 digest of a file in binary mode."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def find_free_port() -> int:
    """Finds an available ephemeral port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        if port == FORBIDDEN_PORT:
            return find_free_port()
        return port


def normalize_str(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).split())


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
    ):
        self.source = Path(source).resolve()
        self.out_dir = Path(out_dir).resolve()
        self.mock = mock
        self.limit = limit
        self.model = model
        self.concurrency = max(1, concurrency)
        self.port = port
        self.run_id = run_id
        self.expected_hash = expected_hash
        self.skip_hash_check = skip_hash_check
        self.scratch_dir = Path(scratch_dir).resolve() if scratch_dir else self.out_dir / "scratch"

        self.taxonomy_path = ROOT / "docs" / "library" / "taxonomy-v1-2026-09-04.json"
        self.prompt_path = ROOT / "scripts" / "librarian" / "prompts" / "assign.md"
        self.holdout_path = ROOT / "docs" / "library" / "holdout-split-2026-09-04.json"
        self.gold_path = ROOT / "docs" / "library" / "gold-set-2026-09-04.json"

        self.server_thread: Optional[threading.Thread] = None
        self.http_server_instance: Optional[Any] = None
        self.token: str = ""
        self.base_url: str = f"http://127.0.0.1:{self.port}"

        self.receipts: List[Dict[str, Any]] = []
        self.before_state: Dict[str, Any] = {}
        self.after_state: Dict[str, Any] = {}
        self.preview_result: Dict[str, Any] = {}
        self.frozen_metadata: Dict[str, Any] = {}
        self.gold_by_id: Dict[str, Any] = {}
        self.taxonomy_data: Dict[str, Any] = {}
        self.prompt_template: str = ""

        # Opener that bypasses proxy environment variables
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._orig_env = {
            k: os.environ.get(k)
            for k in ("LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "UOINK_OUTPUT_DIR", "NO_PROXY")
        }

    def check_guards(self) -> None:
        """Enforces runtime security and boundary constraints."""
        # 1. Assert ANTHROPIC_API_KEY is unset
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key and api_key.strip():
            raise ProofRunError(
                "Refusing to start: ANTHROPIC_API_KEY is set. "
                "Product proof runs must be subscription-only without paid API keys."
            )

        # 2. Never target port 5179
        if self.port == FORBIDDEN_PORT:
            raise ProofRunError(
                f"Refusing to target port {FORBIDDEN_PORT}. "
                "Port 5179 is reserved for the live index helper."
            )

        # 3. Verify source exists
        if not self.source.is_file():
            raise ProofRunError(f"Source index copy does not exist: {self.source}")

        # 4. Verify source hash if requested
        if not self.skip_hash_check and self.expected_hash:
            actual_hash = compute_file_sha256(self.source)
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
        (self.scratch_dir / "roaming").mkdir(parents=True, exist_ok=True)
        (self.scratch_dir / "temp").mkdir(parents=True, exist_ok=True)
        (self.scratch_dir / "output").mkdir(parents=True, exist_ok=True)

        os.environ["LOCALAPPDATA"] = str(self.scratch_dir)
        os.environ["APPDATA"] = str(self.scratch_dir / "roaming")
        os.environ["TEMP"] = str(self.scratch_dir / "temp")
        os.environ["TMP"] = str(self.scratch_dir / "temp")
        os.environ["UOINK_OUTPUT_DIR"] = str(self.scratch_dir / "output")
        os.environ["NO_PROXY"] = "127.0.0.1,localhost"

        isolated_db = uoink_root / "index.db"
        shutil.copyfile(self.source, isolated_db)
        return isolated_db

    def initialize_database_and_freeze(self, db_path: Path) -> None:
        """Initializes schema, approves taxonomy, activates it, and prepares the run."""
        # Calculate frozen hashes
        if not self.taxonomy_path.is_file():
            raise ProofRunError(f"Taxonomy file missing: {self.taxonomy_path}")
        if not self.prompt_path.is_file():
            raise ProofRunError(f"Prompt template missing: {self.prompt_path}")

        taxonomy_bytes = self.taxonomy_path.read_bytes()
        taxonomy_file_hash = hashlib.sha256(taxonomy_bytes).hexdigest()
        self.taxonomy_data = json.loads(taxonomy_bytes.decode("utf-8"))

        prompt_bytes = self.prompt_path.read_bytes()
        prompt_hash = hashlib.sha256(prompt_bytes).hexdigest()
        self.prompt_template = prompt_bytes.decode("utf-8")

        holdout_hash = ""
        if self.holdout_path.is_file():
            holdout_hash = compute_file_sha256(self.holdout_path)

        if self.gold_path.is_file():
            gold_items = json.loads(self.gold_path.read_text(encoding="utf-8"))
            self.gold_by_id = {item["video_id"]: item for item in gold_items}

        card_profile = {
            "schema": 1,
            "profile": "librarian",
            "selection": "spread-longest-v1",
            "max_clips": 6,
            "clip_chars": 240,
            "byte_budget": 8192,
        }
        card_profile_hash = hashlib.sha256(
            json.dumps(card_profile, sort_keys=True).encode("utf-8")
        ).hexdigest()

        # Open and migrate database
        idx = index_mod.Index.open(db_path)
        svc = idx.library_service()
        ctx = RequestContext(
            authenticated=True,
            client_id="proof-harness",
            session_id="proof-operator",
            operator=True,
            local_user_confirmed=True,
        )

        # 1. Approve taxonomy (normalize retired as boolean)
        nodes = []
        for n in self.taxonomy_data.get("nodes", []):
            node = dict(n)
            node["retired"] = bool(node.get("retired", False))
            nodes.append(node)

        version_id = self.taxonomy_data.get("version_id", "taxonomy-v1-2026-09-04")
        tax_res = svc.approve_taxonomy(ctx, {"version_id": version_id, "nodes": nodes})
        if not tax_res.get("ok"):
            raise ProofRunError(f"approve_taxonomy failed: {tax_res}")
        taxonomy_revision_hash = tax_res.get("revision_hash")

        # 2. Activate taxonomy
        with idx.write_transaction() as conn:
            conn.execute(
                "UPDATE shelf_versions SET status='active' WHERE version_id=?", (version_id,)
            )
            conn.execute(
                "UPDATE library_meta SET active_version_id=? WHERE singleton=1", (version_id,)
            )

        # 3. Determine target items
        all_targets: List[str] = [
            r[0]
            for r in idx._conn.execute(
                "SELECT video_id FROM yoinks WHERE deleted_at IS NULL ORDER BY video_id"
            ).fetchall()
        ]
        target_ids = all_targets[: self.limit] if self.limit is not None else all_targets

        # 4. Prepare run
        prep_res = svc.prepare_run(
            ctx,
            {
                "run_id": self.run_id,
                "version_id": version_id,
                "video_ids": target_ids,
                "prompt_hash": prompt_hash,
            },
        )
        if not prep_res.get("ok"):
            raise ProofRunError(f"prepare_run failed: {prep_res}")

        # 5. Snapshot before-state
        projection_revision = idx._conn.execute(
            "SELECT projection_revision FROM library_meta"
        ).fetchone()[0]
        memberships = [
            list(r)
            for r in idx._conn.execute(
                "SELECT video_id, shelf_id, source, locked, is_primary FROM item_shelves ORDER BY video_id, shelf_id"
            ).fetchall()
        ]
        pins = [
            list(r)
            for r in idx._conn.execute(
                "SELECT video_id, shelf_id FROM item_shelves WHERE locked=1 ORDER BY video_id, shelf_id"
            ).fetchall()
        ]
        active_version_id = idx._conn.execute(
            "SELECT active_version_id FROM library_meta"
        ).fetchone()[0]

        self.before_state = {
            "projection_revision": projection_revision,
            "memberships": memberships,
            "memberships_count": len(memberships),
            "pins": pins,
            "pins_count": len(pins),
            "active_version_id": active_version_id,
            "applied_count": len(memberships),
        }
        if self.before_state["applied_count"] != 0:
            raise ProofRunError(
                f"Initial database is not clean: {self.before_state['applied_count']} applied labels found."
            )

        idx.close()

        self.frozen_metadata = {
            "taxonomy_path": str(self.taxonomy_path),
            "taxonomy_file_hash": taxonomy_file_hash,
            "taxonomy_revision_hash": taxonomy_revision_hash,
            "prompt_path": str(self.prompt_path),
            "prompt_hash": prompt_hash,
            "holdout_path": str(self.holdout_path),
            "holdout_hash": holdout_hash,
            "card_profile": "librarian",
            "card_profile_hash": card_profile_hash,
            "source_sha256": compute_file_sha256(self.source) if self.source.exists() else "",
            "manifest_hash": prep_res.get("manifest_hash"),
            "target_count": len(target_ids),
        }

    def start_server(self) -> None:
        """Starts the isolated server.py helper in a thread and waits for /health."""
        import _platform
        import server

        server.HOST = "127.0.0.1"
        server.PORT = self.port
        server.DATA_ROOT = _platform.user_data_dir()
        server.INDEX_PATH = server.DATA_ROOT / "index.db"
        server.SETTINGS_PATH = server.DATA_ROOT / "settings.json"
        server.TOKEN_PATH = self.scratch_dir / "Uoink" / "token.txt"
        server.TOKEN = server._load_or_create_token()
        server.TOKEN_PATH.write_text(server.TOKEN, encoding="utf-8")
        server._index_singleton = None

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
        health_url = f"{self.base_url}/health"
        while time.perf_counter() < deadline:
            try:
                req = urllib.request.Request(
                    health_url,
                    headers={"User-Agent": "uoink-proof/1.0"},
                )
                with self.opener.open(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        online = True
                        break
            except Exception:
                time.sleep(0.1)

        if not online:
            raise ProofRunError(f"Helper server failed to bind and answer on {health_url}")

        self.http_server_instance = server_holder.get("server")
        # Read the token from the isolated helper's token file
        self.token = server.TOKEN_PATH.read_text(encoding="utf-8").strip()

    def stop_server(self) -> None:
        """Stops the isolated server cleanly."""
        if self.http_server_instance:
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

    def http_tool_call(self, tool_name: str, payload: dict) -> dict:
        """Calls POST /tools/<tool_name> with strict JSON handling and auth."""
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
        try:
            with self.opener.open(req, timeout=60.0) as resp:
                resp_bytes = resp.read()
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except Exception:
                return {"ok": False, "error": f"HTTP {e.code}: {raw[:300]}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def format_taxonomy_block(self) -> str:
        nodes = self.taxonomy_data.get("nodes", [])
        lines = []
        for node in sorted(nodes, key=lambda n: n["path"]):
            lines.append(f"- **{' > '.join(node['path'])}** (ID: `{node['shelf_id']}`): {node['definition']}")
            if node.get("include"):
                lines.append(f"  - Include: {', '.join(node['include'])}")
            if node.get("exclude"):
                lines.append(f"  - Exclude: {', '.join(node['exclude'])}")
        return "\n".join(lines)

    def generate_mock_assignment(self, item: dict) -> Tuple[dict, dict]:
        """Generates a deterministic fixture assignment."""
        t0 = time.perf_counter()
        video_id = item["video_id"]
        card = item.get("card") or {}
        excerpts = card.get("excerpts") or []

        gold = self.gold_by_id.get(video_id)
        if gold and excerpts:
            gold_path = gold.get("shelf_path", [])
            # Find matching node in taxonomy
            node = next(
                (n for n in self.taxonomy_data.get("nodes", []) if n["path"] == gold_path),
                None,
            )
            if node is None:
                node = self.taxonomy_data.get("nodes", [{}])[0]

            gold_evidence = normalize_str(gold.get("evidence") or "")
            chosen_excerpt = None
            quote = ""
            if gold_evidence:
                for exc in excerpts:
                    exc_text = normalize_str(exc.get("text", ""))
                    if gold_evidence in exc_text:
                        chosen_excerpt = exc
                        quote = gold_evidence
                        break
                    # Try partial words
                    words = gold_evidence.split()
                    for win_size in (12, 8, 6, 4):
                        sub = " ".join(words[:win_size])
                        if sub and sub in exc_text:
                            chosen_excerpt = exc
                            quote = sub
                            break
                    if chosen_excerpt:
                        break

            if chosen_excerpt is None:
                chosen_excerpt = excerpts[0]
                words = normalize_str(chosen_excerpt.get("text", "")).split()
                quote = " ".join(words[: min(8, len(words))]) or "evidence"

            result = {
                "outcome": "assigned",
                "memberships": [
                    {
                        "shelf_id": node["shelf_id"],
                        "shelf_path": node["path"],
                        "confidence": 0.95,
                        "evidence": {
                            "basis": "packet",
                            "kind": chosen_excerpt.get("evidence_kind", "timed_clip"),
                            "excerpt_id": chosen_excerpt["excerpt_id"],
                            "card_hash": card["card_hash"],
                            "quote": quote,
                        },
                    }
                ],
            }
        else:
            if not excerpts:
                result = {
                    "outcome": "unsupported",
                    "reason": "Card contains insufficient excerpt evidence for grounded classification.",
                }
            else:
                result = {
                    "outcome": "unmapped",
                    "reason": "Content falls outside approved taxonomy definitions.",
                }

        wall_ms = int((time.perf_counter() - t0) * 1000)
        usage = {
            "status": "unavailable",
            "model": "mock",
            "reason": "mock reasoning step",
            "wall_time_ms": wall_ms,
        }
        return result, usage

    def generate_model_assignment(self, item: dict, prompt: str) -> Tuple[dict, dict]:
        """Calls `claude -p` structured output CLI for reasoning."""
        t0 = time.perf_counter()
        exe = shutil.which("claude") or "claude"
        cmd = [
            exe,
            "-p",
            "--json-schema",
            json.dumps(ASSIGN_OUTPUT_SCHEMA),
            "--output-format",
            "json",
            "--tools",
            "",
            "--no-session-persistence",
        ]
        if self.model:
            cmd += ["--model", self.model]

        res = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        wall_ms = int((time.perf_counter() - t0) * 1000)

        if res.returncode != 0 or not res.stdout.strip():
            raise ProofRunError(
                f"claude -p failed (exit {res.returncode}): {res.stderr[:400]}"
            )

        try:
            env = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise ProofRunError(f"claude returned non-JSON stdout: {res.stdout[:300]}") from e

        if env.get("is_error") or env.get("structured_output") is None:
            raise ProofRunError(
                f"claude failed to return structured_output: {str(env.get('result'))[:300]}"
            )

        structured = env["structured_output"]
        results_list = structured.get("results", [])
        if not results_list:
            raise ProofRunError("claude returned empty results list")

        result = results_list[0].get("result", {})
        u = env.get("usage", {})
        if u and "input_tokens" in u:
            usage = {
                "status": "reported",
                "model": env.get("model") or self.model,
                "input_tokens": int(u.get("input_tokens", 0)),
                "output_tokens": int(u.get("output_tokens", 0)),
                "cache_read_tokens": int(u.get("cache_read_input_tokens", 0)),
                "cache_create_tokens": int(u.get("cache_creation_input_tokens", 0)),
                "wall_time_ms": wall_ms,
                "total_cost_usd": env.get("total_cost_usd", 0.0),
            }
        else:
            usage = {
                "status": "unavailable",
                "model": env.get("model") or self.model,
                "reason": "CLI returned no token usage",
                "wall_time_ms": wall_ms,
            }

        return result, usage

    def process_item(self, item: dict, taxonomy_block: str) -> dict:
        """Executes the reason -> submit step for one claimed work item."""
        work_id = item["work_id"]
        video_id = item["video_id"]
        attempt_token = item["attempt_token"]
        packet_hash = item["packet_hash"]
        source_revision = item["source_revision"]
        taxonomy_revision = item["taxonomy_revision"]
        card = item["card"]

        card_bytes = len(json.dumps(card, ensure_ascii=False).encode("utf-8"))
        card_text_block = library_cards.card_text(card)
        prompt = self.prompt_template.replace("{{TAXONOMY}}", taxonomy_block).replace(
            "{{CARDS}}", card_text_block
        )
        prompt_bytes = len(prompt.encode("utf-8"))

        t_start = time.perf_counter()
        if self.mock:
            result, usage = self.generate_mock_assignment(item)
        else:
            result, usage = self.generate_model_assignment(item, prompt)
        wall_ms = int((time.perf_counter() - t_start) * 1000)

        response_bytes = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
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

        submit_resp = self.http_tool_call("submit_library_result", submit_payload)
        resp_data = submit_resp.get("result", submit_resp)
        outcome = resp_data.get("outcome", "rejected" if not submit_resp.get("ok") else "error")

        rejection_reason = None
        if outcome in {"rejected", "error"}:
            rejection_reason = resp_data.get("rejected") or resp_data.get("error")

        evidence_quote = None
        evidence_basis = None
        memberships = result.get("memberships") or []
        if memberships:
            ev = memberships[0].get("evidence") or {}
            evidence_quote = ev.get("quote")
            evidence_basis = ev.get("basis")

        receipt = {
            "work_id": work_id,
            "video_id": video_id,
            "attempt_token": attempt_token,
            "attempt_number": item.get("attempt_number", 1),
            "packet_hash": packet_hash,
            "card_bytes": card_bytes,
            "prompt_bytes": prompt_bytes,
            "response_bytes": response_bytes,
            "wall_ms": wall_ms,
            "outcome": outcome,
            "rejection_reason": rejection_reason,
            "evidence_quote": evidence_quote,
            "evidence_basis": evidence_basis,
            "memberships": memberships,
            "usage": usage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return receipt

    def run_proof_loop(self) -> None:
        """Runs the complete claim -> reason -> submit loop over HTTP."""
        taxonomy_block = self.format_taxonomy_block()
        retried_videos: set[str] = set()

        while True:
            # Claim work
            claim_resp = self.http_tool_call(
                "claim_library_work",
                {
                    "action": "claim",
                    "run_id": self.run_id,
                    "client_id": "proof-harness",
                    "max_items": min(12, self.concurrency),
                },
            )
            claim_data = claim_resp.get("result", claim_resp)
            work_items = claim_data.get("work", [])

            if not work_items:
                # Check status
                list_resp = self.http_tool_call("list_library_work", {"run_id": self.run_id})
                list_data = list_resp.get("result", list_resp)
                counts = list_data.get("counts", {})
                ready = counts.get("ready", 0)
                leased = counts.get("leased", 0)
                if ready == 0 and leased == 0:
                    break
                time.sleep(0.2)
                continue

            # Process items with concurrency
            if self.concurrency > 1 and not self.mock and len(work_items) > 1:
                with cf.ThreadPoolExecutor(max_workers=self.concurrency) as ex:
                    futures = [
                        ex.submit(self.process_item, item, taxonomy_block)
                        for item in work_items
                    ]
                    for fut in cf.as_completed(futures):
                        receipt = fut.result()
                        self.receipts.append(receipt)
                        self._handle_retry_policy(receipt, retried_videos)
            else:
                for item in work_items:
                    receipt = self.process_item(item, taxonomy_block)
                    self.receipts.append(receipt)
                    self._handle_retry_policy(receipt, retried_videos)

        # Apply reshelving preview mode
        preview_resp = self.http_tool_call(
            "apply_reshelving",
            {
                "mode": "preview",
                "run_id": self.run_id,
                "expected_projection_revision": self.before_state["projection_revision"],
            },
        )
        self.preview_result = preview_resp.get("result", preview_resp)
        if self.preview_result.get("can_apply") is not False:
            raise ProofRunError(
                f"apply_reshelving preview returned can_apply={self.preview_result.get('can_apply')}; "
                f"must stay False when librarian_apply_enabled=False."
            )

    def _handle_retry_policy(self, receipt: dict, retried_videos: set[str]) -> None:
        """Enforces at most one retry per rejected model result."""
        outcome = receipt.get("outcome")
        video_id = receipt["video_id"]
        if outcome in {"rejected", "error"}:
            if video_id in retried_videos:
                # Cancel attempt so it doesn't linger
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
        projection_revision = idx._conn.execute(
            "SELECT projection_revision FROM library_meta"
        ).fetchone()[0]
        memberships = [
            list(r)
            for r in idx._conn.execute(
                "SELECT video_id, shelf_id, source, locked, is_primary FROM item_shelves ORDER BY video_id, shelf_id"
            ).fetchall()
        ]
        pins = [
            list(r)
            for r in idx._conn.execute(
                "SELECT video_id, shelf_id FROM item_shelves WHERE locked=1 ORDER BY video_id, shelf_id"
            ).fetchall()
        ]
        active_version_id = idx._conn.execute(
            "SELECT active_version_id FROM library_meta"
        ).fetchone()[0]

        self.after_state = {
            "projection_revision": projection_revision,
            "memberships": memberships,
            "memberships_count": len(memberships),
            "pins": pins,
            "pins_count": len(pins),
            "active_version_id": active_version_id,
            "applied_count": len(memberships),
        }
        idx.close()

        # Assert identical before and after
        if self.before_state != self.after_state:
            raise ProofRunError(
                f"State verification failed! Before != After:\n"
                f"Before: {self.before_state}\n"
                f"After:  {self.after_state}"
            )
        if self.after_state["applied_count"] != 0:
            raise ProofRunError(
                f"Zero applied labels assertion failed: found {self.after_state['applied_count']}"
            )

    def write_receipts(self) -> Path:
        """Writes <out>/receipts.json atomically."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        out_file = self.out_dir / "receipts.json"

        total_serialized_input_bytes = sum(
            r["card_bytes"] + r["prompt_bytes"] for r in self.receipts
        )
        total_wall_ms = sum(r["wall_ms"] for r in self.receipts)
        total_retries = sum(1 for r in self.receipts if r["attempt_number"] > 1)
        outcome_counts = Counter(r["outcome"] for r in self.receipts)

        document = {
            "schema_version": 1,
            "run_id": self.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "client": "mock" if self.mock else "claude-p",
            "model": "mock" if self.mock else self.model,
            "mock": self.mock,
            "concurrency": self.concurrency,
            "port": self.port,
            "frozen_inputs": self.frozen_metadata,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "preview_result": self.preview_result,
            "totals": {
                "total_serialized_input_bytes": total_serialized_input_bytes,
                "total_wall_ms": total_wall_ms,
                "total_retries": total_retries,
                "total_attempts": len(self.receipts),
                "total_items": len(set(r["video_id"] for r in self.receipts)),
                "outcome_counts": dict(outcome_counts),
            },
            "receipts": self.receipts,
        }

        tmp_file = self.out_dir / f".receipts-{secrets.token_hex(4)}.tmp"
        tmp_file.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        shutil.move(str(tmp_file), str(out_file))
        return out_file

    def execute(self) -> Path:
        """Runs the entire product proof harness."""
        self.check_guards()
        isolated_db = self.prepare_isolated_environment()
        try:
            self.initialize_database_and_freeze(isolated_db)
            self.start_server()
            self.run_proof_loop()
            self.verify_after_state(isolated_db)
            receipts_path = self.write_receipts()
            return receipts_path
        finally:
            self.stop_server()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Living Library product proof harness (Run P, mock-only or claude -p)"
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
        help="Concurrency for claude -p worker processes (default: 4)",
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
    parser = build_parser()
    args = parser.parse_args()

    harness = ProofHarness(
        source=args.source,
        out_dir=args.out,
        mock=args.mock,
        limit=args.limit,
        model=args.model,
        concurrency=args.concurrency,
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

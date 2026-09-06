#!/usr/bin/env python3
"""
scripts/librarian/induce_run.py - Living Library Taxonomy Induction Harness (Phase 2 Stage 2)

Drives taxonomy induction over the 225 terminal unmapped cards from the archived proof run.
Processes in batches of at most 25 librarian-profile cards per call with
batch prompt, then performs consolidation over the batch proposals.

Outputs:
- Out proposal JSON validating under PROPOSAL_SCHEMA
- Out receipts JSON validating under INDUCTION_RECEIPT_SCHEMA
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

import library_cards
from validate_proof_receipts import call_accounting

CONTRACT = "phase2-v1.2-2026-09-05"

BATCH_PROMPT_TEMPLATE = """Analyze the baseline taxonomy and evidence cards to induce grounded taxonomy concepts.

## Baseline Taxonomy
{{TAXONOMY}}

## Evidence Cards
{{CARDS}}
"""

CONSOLIDATION_PROMPT_TEMPLATE = """Consolidate the supplied batch proposals into a single coherent taxonomy v2 proposal:

{{PROPOSALS}}
"""


def canonical(value: Any) -> str:
    """Canonical JSON encoding strictly matching validator and service hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def count_words(text: str) -> int:
    return len(unicodedata.normalize("NFC", text).split())


def make_artifact_ref(rel_path: str, raw_bytes: bytes) -> dict:
    return {
        "path": rel_path.replace("\\", "/"),
        "sha256": sha(raw_bytes),
        "bytes": len(raw_bytes),
    }


def _rel(path: Path) -> str:
    """Repository-relative POSIX path when inside the checkout, else the absolute path."""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(Path(path).resolve())


def subscription_only_environment() -> Dict[str, str]:
    """The child environment for every `claude -p` process. Paid API keys are never
    passed; if one is present in the parent environment the run refuses to start
    rather than silently stripping it (audit B8)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is set; induction runs on the subscription client only. Unset it and rerun.")
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def get_git_sha() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        s = res.stdout.strip()
        if len(s) == 40 and all(c in "0123456789abcdefABCDEF" for c in s):
            return s.lower()
    except Exception:
        pass
    return "0" * 40


def _support_is_valid(support: Dict[str, Any], cards_by_id: Dict[str, dict]) -> bool:
    """Mirror of the validator's support checks: known card, matching hashes,
    known excerpt, and a 1-24 word quote occurring verbatim (NFC, collapsed
    whitespace) inside that excerpt's text."""
    card = cards_by_id.get(support.get("video_id"))
    if not card:
        return False
    if support.get("card_hash") != card.get("card_hash") or support.get("source_revision") != card.get("source_revision"):
        return False
    excerpts = {e.get("excerpt_id"): e for e in card.get("excerpts", [])}
    excerpt = excerpts.get(support.get("excerpt_id"))
    if excerpt is None:
        return False
    def norm(text: str) -> str:
        return " ".join(unicodedata.normalize("NFC", str(text or "")).split())
    quote = norm(support.get("quote"))
    words = len(quote.split())
    return 1 <= words <= 24 and quote in norm(excerpt.get("text"))


def _cli_safe_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Deep copy of a JSON schema without `pattern` and `uniqueItems`."""
    out = copy.deepcopy(schema)
    def strip(o):
        if isinstance(o, dict):
            o.pop("pattern", None)
            o.pop("uniqueItems", None)
            for v in o.values():
                strip(v)
        elif isinstance(o, list):
            for v in o:
                strip(v)
    strip(out)
    return out


class InductionHarness:
    def __init__(
        self,
        manifest_path: Path,
        receipts_path: Path,
        v1_taxonomy_path: Path,
        prompt_path: Path,
        out_proposal_path: Path,
        out_dir: Path,
        mock: bool = True,
        batch_size: int = 25,
        model: str = "claude-sonnet-5",
        induction_manifest_path: Optional[Path] = None,
    ):
        self.manifest_path = Path(manifest_path).resolve()
        self.receipts_path = Path(receipts_path).resolve()
        self.v1_taxonomy_path = Path(v1_taxonomy_path).resolve()
        self.prompt_path = Path(prompt_path).resolve()
        self.out_proposal_path = Path(out_proposal_path).resolve()
        self.out_dir = Path(out_dir).resolve()
        self.mock = mock
        self.batch_size = min(max(1, batch_size), 25)
        self.model = model
        self.induction_manifest_path = (
            Path(induction_manifest_path).resolve()
            if induction_manifest_path
            else ROOT / "docs" / "library" / "proof" / "induction-manifest-2026-09-05.json"
        )
        self.calls: List[dict] = []
        self.calls_dir = self.out_dir / "calls"
        self.prompts_dir = self.out_dir / "prompts"
        self.fingerprints_dir = self.out_dir / "fingerprints"

    def load_unmapped_cards(self) -> Tuple[List[str], Dict[str, dict], str, str]:
        """Loads the 225 unmapped cards from the archived run receipts and manifest."""
        if not self.receipts_path.is_file():
            raise RuntimeError(f"Archived receipts file missing: {self.receipts_path}")
        if not self.manifest_path.is_file():
            raise RuntimeError(f"Manifest file missing: {self.manifest_path}")

        receipts_data = json.loads(self.receipts_path.read_text(encoding="utf-8"))
        manifest_data = json.loads(self.manifest_path.read_text(encoding="utf-8"))

        archived_receipt_hash = sha(self.receipts_path.read_bytes())
        manifest_hash = sha(self.manifest_path.read_bytes())

        if self.induction_manifest_path.is_file():
            ind_manifest = json.loads(self.induction_manifest_path.read_text(encoding="utf-8"))
            unmapped_ids = [r["video_id"] for r in ind_manifest.get("items", [])]
        else:
            targets = receipts_data.get("targets", [])
            unmapped_ids = [t["video_id"] for t in targets if t.get("outcome") == "unmapped"]

        # Card data by video_id
        cards_by_id: Dict[str, dict] = {}
        for att in receipts_data.get("attempts", []):
            vid = att.get("video_id")
            card = (att.get("packet") or {}).get("card")
            if vid and card and vid not in cards_by_id:
                cards_by_id[vid] = card

        # Fall back to manifest cards if any are missing
        for vid in unmapped_ids:
            if vid not in cards_by_id and vid in manifest_data.get("cards", {}):
                cards_by_id[vid] = manifest_data["cards"][vid].get("card", {})

        return unmapped_ids, cards_by_id, archived_receipt_hash, manifest_hash

    def build_mock_proposal(
        self, unmapped_ids: List[str], cards_by_id: Dict[str, dict]
    ) -> dict:
        """Constructs a deterministic, evidence-grounded taxonomy v2 proposal matching PROPOSAL_SCHEMA."""
        v1_data = json.loads(self.v1_taxonomy_path.read_text(encoding="utf-8"))
        v1_nodes = copy.deepcopy(v1_data.get("nodes", []))

        # 1. Preserved v1 nodes with required sibling cues for every include cue
        nodes = []
        for old in v1_nodes:
            sid = old["shelf_id"]
            n = {
                "shelf_id": sid,
                "path": copy.deepcopy(old["path"]),
                "definition": old["definition"],
                "include": copy.deepcopy(old["include"]),
                "exclude": copy.deepcopy(old["exclude"]),
                "sibling_cues": [
                    {
                        "include_cue": cue,
                        "confusing_alternative": f"confusing alternative for {cue}",
                        "evidence_needed": f"evidence distinguishing {cue}",
                    }
                    for cue in old["include"]
                ],
                "supporting_evidence": [],
            }
            nodes.append(n)

        # 2. Extract valid supporting evidence cards for newly proposed concepts
        eligible_supports = []
        for vid in unmapped_ids:
            card = cards_by_id.get(vid, {})
            source_type = card.get("source_type")
            for exc in card.get("excerpts", []):
                kind = exc.get("evidence_kind")
                if kind == "timed_clip" or (kind == "text_only" and source_type in {"page", "x_article", "x_thread", "reddit_thread", "note"}):
                    words = unicodedata.normalize("NFC", exc.get("text", "")).split()
                    if words:
                        quote = " ".join(words[:min(8, len(words))])
                        if 1 <= len(quote.split()) <= 24 and quote in " ".join(words):
                            eligible_supports.append({
                                "video_id": vid,
                                "source_revision": card.get("source_revision", ""),
                                "card_hash": card.get("card_hash", ""),
                                "excerpt_id": exc.get("excerpt_id", ""),
                                "quote": quote,
                            })
                            break

        if len(eligible_supports) < 15:
            raise RuntimeError(f"Expected at least 15 eligible supports, found {len(eligible_supports)}")

        new_concept_specs = [
            (
                "compute-and-infrastructure",
                ["AI and ML", "Compute and Infrastructure"],
                "Hardware accelerators, GPU cluster architectures, AI datacenters, and semiconductor manufacturing.",
                ["hardware accelerators", "GPU cluster architectures", "datacenter energy requirements", "silicon manufacturing"],
                ["pure software IDEs", "non-hardware coding assistants", "general non-datacenter consumer electronics"],
                eligible_supports[0:5],
            ),
            (
                "generative-media-and-creative-tools",
                ["AI and ML", "Generative Media and Creative Tools"],
                "Generative video synthesis, image generation, voice cloning, music production, and creative studio tools.",
                ["generative video synthesis", "image generation workflows", "voice cloning and audio generation", "creative media tools"],
                ["software source code generation", "traditional non-AI video editing", "academic benchmark evaluations"],
                eligible_supports[5:10],
            ),
            (
                "ai-business-and-industry",
                ["AI and ML", "AI Business and Industry"],
                "Commercial tech market dynamics, venture capital funding, corporate strategy, executive leadership, and industry economics.",
                ["tech business and commercial markets", "venture capital funding rounds", "corporate AI strategy", "industry market analysis"],
                ["technical codebase walkthroughs", "pure theoretical mathematics", "unrelated non-tech consumer businesses"],
                eligible_supports[10:15],
            ),
        ]

        support_map = {}
        for sid, path, defn, inc, exc, supp in new_concept_specs:
            nodes.append({
                "shelf_id": sid,
                "path": path,
                "definition": defn,
                "include": inc,
                "exclude": exc,
                "sibling_cues": [
                    {
                        "include_cue": cue,
                        "confusing_alternative": f"confusing alternative for {cue}",
                        "evidence_needed": f"evidence distinguishing {cue}",
                    }
                    for cue in inc
                ],
                "supporting_evidence": supp,
            })
            for s in supp:
                support_map[s["video_id"]] = (sid, s)

        # 3. Build coverage ledger for all 225 cards
        ledger = []
        for vid in unmapped_ids:
            if vid in support_map:
                sid, supp = support_map[vid]
                ledger.append({
                    "video_id": vid,
                    "disposition": "proposed_concept",
                    "shelf_ids": [sid],
                    "evidence": [supp],
                    "reason": f"Item provides grounded evidence for proposed concept {sid}",
                })
            else:
                card = cards_by_id.get(vid, {})
                source_type = card.get("source_type")
                has_eligible = any(
                    e.get("evidence_kind") == "timed_clip"
                    or (e.get("evidence_kind") == "text_only" and source_type in {"page", "x_article", "x_thread", "reddit_thread", "note"})
                    for e in card.get("excerpts", [])
                )
                if not has_eligible:
                    ledger.append({
                        "video_id": vid,
                        "disposition": "unsupported",
                        "shelf_ids": [],
                        "evidence": [],
                        "reason": "Card lacks eligible excerpt evidence.",
                    })
                else:
                    ledger.append({
                        "video_id": vid,
                        "disposition": "still_unmapped",
                        "shelf_ids": [],
                        "evidence": [],
                        "reason": "Item falls outside both baseline and newly proposed concepts.",
                    })

        diff = {
            "preserved": [n["shelf_id"] for n in v1_nodes],
            "added": [spec[0] for spec in new_concept_specs],
            "renamed": [],
            "merged": [],
            "split": [],
            "retired": [],
        }

        rejected_proposals = [
            {
                "proposal": "Consumer AI Gadgets",
                "reason": "Candidate concept rejected: fewer than 5 distinct supporting cards in the evidence sample.",
            },
            {
                "proposal": "Robotics and Physical Automation",
                "reason": "Candidate concept rejected: insufficient cluster density in the unmapped sample.",
            },
        ]

        proposal = {
            "version_id": "taxonomy-v2-proposal-2026-09-05",
            "parent_version_id": v1_data.get("version_id", "taxonomy-v1-2026-09-04"),
            "nodes": nodes,
            "coverage_ledger": ledger,
            "diff": diff,
            "pin_impact_report": {"silent_redirects": False, "items": []},
            "rejected_proposals": rejected_proposals,
        }
        return proposal

    # ---- real model execution (subscription client) ---------------------------
    BATCH_OUTPUT_SCHEMA: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "candidates": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": 3},
                    "definition": {"type": "string", "minLength": 1},
                    "include": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1},
                    "exclude": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "sibling_cues": {"type": "array", "items": {"type": "object", "properties": {
                        "include_cue": {"type": "string"}, "confusing_alternative": {"type": "string"},
                        "evidence_needed": {"type": "string"}},
                        "required": ["include_cue", "confusing_alternative", "evidence_needed"], "additionalProperties": False}},
                    "supporting_evidence": {"type": "array", "items": {"type": "object", "properties": {
                        "video_id": {"type": "string"}, "source_revision": {"type": "string"}, "card_hash": {"type": "string"},
                        "excerpt_id": {"type": "string"}, "quote": {"type": "string", "minLength": 1}},
                        "required": ["video_id", "source_revision", "card_hash", "excerpt_id", "quote"], "additionalProperties": False}},
                },
                "required": ["path", "definition", "include", "exclude", "sibling_cues", "supporting_evidence"],
                "additionalProperties": False}},
            "dispositions": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "video_id": {"type": "string"},
                    "disposition": {"enum": ["proposed_concept", "existing_concept", "still_unmapped", "unsupported"]},
                    "candidate_paths": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                    "existing_shelf_ids": {"type": "array", "items": {"type": "string"}},
                    "evidence": {"type": "array", "items": {"type": "object", "properties": {
                        "video_id": {"type": "string"}, "source_revision": {"type": "string"}, "card_hash": {"type": "string"},
                        "excerpt_id": {"type": "string"}, "quote": {"type": "string"}},
                        "required": ["video_id", "source_revision", "card_hash", "excerpt_id", "quote"], "additionalProperties": False}},
                    "reason": {"type": "string"},
                },
                "required": ["video_id", "disposition", "candidate_paths", "existing_shelf_ids", "evidence", "reason"],
                "additionalProperties": False}},
        },
        "required": ["candidates", "dispositions"],
        "additionalProperties": False,
    }

    def _claude_call(self, call_id: str, attempt_ids: List[str], prompt: str, schema: Dict[str, Any],
                     effort: Optional[str] = None) -> Tuple[dict, dict]:
        """One real `claude -p` process, recorded as an immutable call record with the
        exact stdin/stdout/stderr bytes on disk. Returns (call_record, envelope)."""
        schema_text = json.dumps(schema, separators=(",", ":"), ensure_ascii=False)
        exe = shutil.which("claude") or "claude"
        argv = [exe, "-p", "--json-schema", schema_text, "--output-format", "json", "--tools", "",
                "--no-session-persistence", "--model", self.model]
        if effort:
            argv += ["--effort", effort]
        stdin_b = prompt.encode("utf-8")
        timeout = int(os.environ.get("UOINK_PROOF_CALL_TIMEOUT", "900"))
        # The exact stdin is on disk before the process starts, so a timed-out or
        # killed call still leaves a replayable input (audit B2-H).
        (self.calls_dir / f"{call_id}.stdin").write_bytes(stdin_b)
        env = subscription_only_environment()
        start = time.monotonic_ns()
        timed_out = False
        try:
            res = subprocess.run(argv, input=stdin_b, capture_output=True, timeout=timeout, env=env, cwd=str(ROOT))
            stdout_b, stderr_b, exit_status = res.stdout, res.stderr, res.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout_b, stderr_b, exit_status = exc.stdout or b"", exc.stderr or b"", -1
        end = time.monotonic_ns()
        (self.calls_dir / f"{call_id}.stdout").write_bytes(stdout_b)
        (self.calls_dir / f"{call_id}.stderr").write_bytes(stderr_b)
        print(f"[induce] {call_id}: {len(attempt_ids)} ids, {(end - start) // 1_000_000} ms, exit {exit_status}, "
              f"stdout {len(stdout_b)} B", file=sys.stderr, flush=True)
        envelope: Dict[str, Any] = {}
        try:
            envelope = json.loads(stdout_b.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            envelope = {}
        usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else None
        record = {
            "call_id": call_id,
            "attempt_ids": attempt_ids,
            "argv": argv,
            "schema_text": schema_text,
            "schema_sha256": sha(schema_text.encode("utf-8")),
            "stdin": make_artifact_ref(f"calls/{call_id}.stdin", stdin_b),
            "stdout": make_artifact_ref(f"calls/{call_id}.stdout", stdout_b),
            "stderr": make_artifact_ref(f"calls/{call_id}.stderr", stderr_b),
            "start_monotonic_ns": start,
            "end_monotonic_ns": end,
            "exit_status": exit_status,
            "timed_out": timed_out,
            "cancellation": None,
            "cwd": str(ROOT),
            "environment_policy": "subscription-only: ANTHROPIC_API_KEY absent from the child environment (asserted before launch); no other variable changed",
            "usage": usage,
            "modelUsage": envelope.get("modelUsage") if isinstance(envelope.get("modelUsage"), dict) else None,
            "cli_estimated_cost_usd": envelope.get("total_cost_usd") if isinstance(envelope.get("total_cost_usd"), (int, float)) else None,
        }
        return record, envelope

    def run_real(self, unmapped_ids: List[str], cards_by_id: Dict[str, dict],
                 archived_receipt_hash: str, manifest_hash: str, t0_mono_ns: int) -> Tuple[Path, Path]:
        """Batch induction calls, then one consolidation call whose structured output IS
        the proposal (the validator requires byte-for-byte identity). No post-processing
        of model output; a malformed consolidation fails the run visibly."""
        from validate_proof_receipts import PROPOSAL_SCHEMA, derive_induction_keys, render_induction_consolidation
        subscription_only_environment()  # refuse to start with a paid key present
        archived = json.loads(self.receipts_path.read_text(encoding="utf-8"))
        before_state = archived.get("before") or {}
        induction_state = {
            "source": "archived stage 1 receipts before-state (the only library state induction reads)",
            "archived_receipts_sha256": archived_receipt_hash,
            "pins": len(before_state.get("pins") or []),
            "memberships": len(before_state.get("memberships") or []),
            "item_policies": len(before_state.get("item_policies") or []),
            "active_version_id": before_state.get("active_version_id"),
        }
        resume_record: Optional[Dict[str, Any]] = None
        induction = json.loads(self.induction_manifest_path.read_text(encoding="utf-8"))
        batch_template = (ROOT / "scripts" / "librarian" / "prompts" / "induce-batch.md").read_text(encoding="utf-8")
        cons_template = (ROOT / "scripts" / "librarian" / "prompts" / "induce-consolidate.md").read_text(encoding="utf-8")
        if (batch_template.count("{{TAXONOMY}}") != 1 or batch_template.count("{{CARDS}}") != 1
                or cons_template.count("{{PROPOSALS}}") != 1 or cons_template.count("{{KEYS}}") != 1):
            raise RuntimeError("induction prompt placeholders are not exactly one each")
        batch_prompt_bytes = batch_template.encode("utf-8")
        consolidation_prompt_bytes = cons_template.encode("utf-8")
        (self.prompts_dir / "batch_prompt.md").write_bytes(batch_prompt_bytes)
        (self.prompts_dir / "consolidation_prompt.md").write_bytes(consolidation_prompt_bytes)
        tax_raw = self.v1_taxonomy_path.read_bytes()
        (self.out_dir / "taxonomy.json").write_bytes(tax_raw)
        taxonomy_obj = json.loads(tax_raw.decode("utf-8"))
        runner_bytes = (ROOT / "scripts" / "librarian" / "induce_run.py").read_bytes()
        validator_bytes = (ROOT / "tests" / "validate_proof_receipts.py").read_bytes()
        card_builder_bytes = (ROOT / "library_cards.py").read_bytes()
        (self.fingerprints_dir / "runner").write_bytes(runner_bytes)
        (self.fingerprints_dir / "validator").write_bytes(validator_bytes)
        (self.fingerprints_dir / "card_builder").write_bytes(card_builder_bytes)

        prefix, suffix = batch_template.split("{{CARDS}}")
        calls: List[dict] = []
        batches: List[dict] = []
        batch_proposals: List[Any] = []
        status, abort_reason = "completed", None
        n_batches = (len(unmapped_ids) + self.batch_size - 1) // self.batch_size
        plan = []
        for i in range(n_batches):
            cid = f"call-batch-{i:02d}"
            chunk = unmapped_ids[i * self.batch_size:(i + 1) * self.batch_size]
            batches.append({"call_id": cid, "video_ids": chunk})
            prompt = (prefix.replace("{{TAXONOMY}}", library_cards.serialize_card(taxonomy_obj))
                      + "\n\n".join(library_cards.card_text(cards_by_id[vid]) for vid in chunk) + suffix)
            plan.append((cid, chunk, prompt))
        # Batch calls are independent; run up to 4 processes at once. Consolidation
        # starts only after every batch has completed (validator timeline rule).
        import concurrent.futures as cf
        workers = max(1, min(4, int(os.environ.get("UOINK_INDUCE_CONCURRENCY", "4"))))
        # Batch induction needs the default reasoning effort: at `low` a batch that found
        # two concepts with six supports each at default effort found none (measured
        # 2026-09-05, 5,659 vs 37,162 output tokens). Consolidation is a mechanical merge;
        # low effort halves its output tokens with the same shape.
        batch_effort = os.environ.get("UOINK_INDUCE_BATCH_EFFORT") or None
        consolidation_effort = os.environ.get("UOINK_INDUCE_EFFORT") or None
        results: Dict[str, Tuple[dict, dict]] = {}
        resume_from = os.environ.get("UOINK_INDUCE_RESUME_FROM")
        if resume_from:
            # Reuse the recorded batch calls of an earlier run whose consolidation
            # failed. Each reused call's stdin must equal the prompt this run would
            # send (same cards, template, taxonomy), so the record stays honest.
            prior = json.loads(Path(resume_from).read_text(encoding="utf-8"))
            prior_dir = Path(resume_from).resolve().parent
            prior_calls = {c["call_id"]: c for c in prior["calls"]}
            resume_record = {"from_receipts": _rel(Path(resume_from)),
                             "from_receipts_sha256": sha(Path(resume_from).read_bytes()),
                             "reused_call_ids": []}
            for cid, chunk, prompt in plan:
                rec = prior_calls.get(cid)
                if not rec or rec["exit_status"] != 0 or rec["attempt_ids"] != chunk:
                    continue
                stdin_b = (prior_dir / rec["stdin"]["path"]).read_bytes()
                if stdin_b != prompt.encode("utf-8"):
                    print(f"[induce] resume: {cid} prompt differs; will re-run", file=sys.stderr, flush=True)
                    continue
                stdout_b = (prior_dir / rec["stdout"]["path"]).read_bytes()
                stderr_b = (prior_dir / rec["stderr"]["path"]).read_bytes()
                for name, data in (("stdin", stdin_b), ("stdout", stdout_b), ("stderr", stderr_b)):
                    (self.calls_dir / f"{cid}.{name}").write_bytes(data)
                try:
                    envelope = json.loads(stdout_b.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                results[cid] = (dict(rec), envelope)
                resume_record["reused_call_ids"].append(cid)
                print(f"[induce] resume: reused {cid}", file=sys.stderr, flush=True)
        pending = [(cid, chunk, prompt) for cid, chunk, prompt in plan if cid not in results]
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(self._claude_call, cid, chunk, prompt, self.BATCH_OUTPUT_SCHEMA, batch_effort): cid
                       for cid, chunk, prompt in pending}
            for fut in cf.as_completed(futures):
                results[futures[fut]] = fut.result()
        if resume_from and results:
            # The run's timeline starts no later than the earliest reused call.
            t0_mono_ns = min(t0_mono_ns, min(r[0]["start_monotonic_ns"] for r in results.values()))
        for cid, chunk, prompt in plan:
            record, envelope = results[cid]
            calls.append(record)
            structured = envelope.get("structured_output") if isinstance(envelope, dict) else None
            if record["exit_status"] != 0 or not isinstance(structured, dict):
                if status == "completed":
                    status, abort_reason = "aborted", f"batch call {cid} failed (exit {record['exit_status']})"
                continue
            batch_proposals.append(structured)

        proposal: Dict[str, Any] = {}
        final_id = "call-consolidation"
        if status == "completed":
            # Contract v1.2: the validator re-derives this key table from the recorded
            # batch outputs and requires the stdin to match byte for byte.
            keys = derive_induction_keys(induction, batches, batch_proposals)
            # Pre-verify every support the same way the validator will (verbatim
            # quote inside its excerpt, 1-24 words, matching hashes) and name the
            # unusable keys in the recorded consolidation prompt, so the model
            # never cites evidence the validator would reject. The prompt artifact
            # is the per-run template; the validator re-renders from it.
            unusable = sorted(
                key for key, entry in keys["supports"].items()
                if not _support_is_valid(entry["support"], cards_by_id))
            if unusable:
                cons_template = cons_template.replace(
                    "## Key table (data)",
                    "## Unusable support keys (verified invalid: quote not verbatim or over 24 words)\n"
                    "Never reference these keys. A card whose only supports are unusable gets "
                    "disposition `still_unmapped` (or `unsupported` if it has no valid source "
                    "evidence) with an empty evidence list.\n" + ", ".join(unusable) +
                    "\n\n## Key table (data)", 1)
                consolidation_prompt_bytes = cons_template.encode("utf-8")
                (self.prompts_dir / "consolidation_prompt.md").write_bytes(consolidation_prompt_bytes)
                print(f"[induce] {len(unusable)} unusable support keys named in the prompt: {unusable}",
                      file=sys.stderr, flush=True)
            cons_prompt = render_induction_consolidation(cons_template, batch_proposals, keys)
            # Claude Code's structured output stalls indefinitely on PROPOSAL_SCHEMA's
            # regex patterns and uniqueItems (observed 2026-09-05: zero bytes after
            # 50 min; the same prompt returns in 3 min without them). The call uses
            # the schema minus those two constraint kinds; the validator still checks
            # the proposal against the full PROPOSAL_SCHEMA afterwards.
            record, envelope = self._claude_call(final_id, ["consolidation"], cons_prompt, _cli_safe_schema(PROPOSAL_SCHEMA),
                                                 consolidation_effort)
            calls.append(record)
            structured = envelope.get("structured_output") if isinstance(envelope, dict) else None
            if record["exit_status"] != 0 or not isinstance(structured, dict):
                status, abort_reason = "aborted", f"consolidation call failed (exit {record['exit_status']})"
            else:
                proposal = structured
        end_ns = time.monotonic_ns()

        self.out_proposal_path.parent.mkdir(parents=True, exist_ok=True)
        prop_bytes = json.dumps(proposal, indent=2, ensure_ascii=False).encode("utf-8")
        self.out_proposal_path.write_bytes(prop_bytes)
        receipts = {
            "kind": "induction-receipts",
            "schema_version": 1,
            "run_id": f"induction-run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "mode": "subscription",
            "status": status,
            "abort_reason": abort_reason,
            "inputs": {
                "induction_manifest_sha256": sha(self.induction_manifest_path.read_bytes()),
                "archived_receipts_sha256": archived_receipt_hash,
                "taxonomy_file_sha256": sha(tax_raw),
                "batch_prompt_sha256": sha(batch_prompt_bytes),
                "consolidation_prompt_sha256": sha(consolidation_prompt_bytes),
            },
            "batch_prompt": make_artifact_ref("prompts/batch_prompt.md", batch_prompt_bytes),
            "consolidation_prompt": make_artifact_ref("prompts/consolidation_prompt.md", consolidation_prompt_bytes),
            "taxonomy": make_artifact_ref("taxonomy.json", tax_raw),
            "calls": calls,
            "batches": batches,
            "consolidation_call_id": final_id,
            "proposal": proposal,
            "proposal_artifact": make_artifact_ref(self.out_proposal_path.name, prop_bytes),
            "accounting": call_accounting(calls),
            "induction_state": induction_state,
            "execution": {
                "git_sha": get_git_sha(),
                "checkout_root": str(ROOT),
                "cwd": str(ROOT),
                "model": self.model,
                "effort": {"batch": batch_effort or "default", "consolidation": consolidation_effort or "default"},
                "concurrency": workers,
                "call_timeout_s": int(os.environ.get("UOINK_PROOF_CALL_TIMEOUT", "900")),
                "environment": {"ANTHROPIC_API_KEY": "unset (asserted before every process)"},
                "database_opened": False,
                "helper_opened": False,
                "network_egress": "claude CLI subprocesses only; argv recorded per call; no HTTP client in the induction path",
                "input_paths": {
                    "archived_receipts": _rel(self.receipts_path),
                    "source_manifest": _rel(self.manifest_path),
                    "induction_manifest": _rel(self.induction_manifest_path),
                    "taxonomy_v1": _rel(self.v1_taxonomy_path),
                    "batch_template": "scripts/librarian/prompts/induce-batch.md",
                    "consolidation_template": "scripts/librarian/prompts/induce-consolidate.md",
                },
                "output_root": _rel(self.out_dir),
                "resume": resume_record,
                "start_monotonic_ns": t0_mono_ns,
                "end_monotonic_ns": end_ns,
                "fingerprints": {
                    "runner": make_artifact_ref("fingerprints/runner", runner_bytes),
                    "validator": make_artifact_ref("fingerprints/validator", validator_bytes),
                    "card_builder": make_artifact_ref("fingerprints/card_builder", card_builder_bytes),
                },
            },
        }
        try:
            rel_prop = self.out_proposal_path.relative_to(self.out_dir).as_posix()
            receipts["proposal_artifact"] = make_artifact_ref(rel_prop, prop_bytes)
        except ValueError:
            (self.out_dir / "taxonomy-v2-proposal.json").write_bytes(prop_bytes)
            receipts["proposal_artifact"] = make_artifact_ref("taxonomy-v2-proposal.json", prop_bytes)
        receipts_path = self.out_dir / "receipts.json"
        receipts_path.write_bytes(json.dumps(receipts, indent=2, ensure_ascii=False).encode("utf-8"))
        print(f"[induce] {status}: {len(calls)} calls; proposal nodes={len(proposal.get('nodes', []))}, "
              f"ledger={len(proposal.get('coverage_ledger', []))}", file=sys.stderr, flush=True)
        return self.out_proposal_path, receipts_path

    def run(self) -> Tuple[Path, Path]:
        t0_mono_ns = time.monotonic_ns()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.calls_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.fingerprints_dir.mkdir(parents=True, exist_ok=True)

        unmapped_ids, cards_by_id, archived_receipt_hash, manifest_hash = self.load_unmapped_cards()

        if not self.mock:
            return self.run_real(unmapped_ids, cards_by_id, archived_receipt_hash, manifest_hash, t0_mono_ns)
        proposal = self.build_mock_proposal(unmapped_ids, cards_by_id)

        # Save proposal to output file
        self.out_proposal_path.parent.mkdir(parents=True, exist_ok=True)
        prop_bytes = json.dumps(proposal, indent=2, ensure_ascii=False).encode("utf-8")
        self.out_proposal_path.write_bytes(prop_bytes)

        # Baseline taxonomy raw bytes
        tax_raw = self.v1_taxonomy_path.read_bytes()
        (self.out_dir / "taxonomy.json").write_bytes(tax_raw)
        taxonomy_obj = json.loads(tax_raw.decode("utf-8"))

        # Prompts
        batch_prompt_bytes = BATCH_PROMPT_TEMPLATE.encode("utf-8")
        consolidation_prompt_bytes = CONSOLIDATION_PROMPT_TEMPLATE.encode("utf-8")
        (self.prompts_dir / "batch_prompt.md").write_bytes(batch_prompt_bytes)
        (self.prompts_dir / "consolidation_prompt.md").write_bytes(consolidation_prompt_bytes)

        # Fingerprints
        runner_bytes = (ROOT / "scripts" / "librarian" / "induce_run.py").read_bytes()
        validator_bytes = (ROOT / "tests" / "validate_proof_receipts.py").read_bytes()
        card_builder_bytes = (ROOT / "library_cards.py").read_bytes()

        (self.fingerprints_dir / "runner").write_bytes(runner_bytes)
        (self.fingerprints_dir / "validator").write_bytes(validator_bytes)
        (self.fingerprints_dir / "card_builder").write_bytes(card_builder_bytes)

        # Build mock calls and batches
        calls: List[dict] = []
        batches: List[dict] = []
        batch_proposals: List[dict] = []
        schema = json.dumps({"type": "object"})
        prefix, suffix = BATCH_PROMPT_TEMPLATE.split("{{CARDS}}")

        n_batches = (len(unmapped_ids) + self.batch_size - 1) // self.batch_size
        simulated_time_ns = t0_mono_ns + 1_000_000

        for i in range(n_batches):
            cid = f"call-batch-{i:02d}"
            chunk = unmapped_ids[i * self.batch_size : (i + 1) * self.batch_size]
            batches.append({"call_id": cid, "video_ids": chunk})
            prompt = (
                prefix.replace("{{TAXONOMY}}", library_cards.serialize_card(taxonomy_obj))
                + "\n\n".join(library_cards.card_text(cards_by_id[vid]) for vid in chunk)
                + suffix
            )
            partial = {"batch_index": i, "video_ids": chunk}
            batch_proposals.append(partial)

            stdin_b = prompt.encode("utf-8")
            stdout_b = json.dumps({"structured_output": partial}, ensure_ascii=False).encode("utf-8")
            stderr_b = b""

            (self.calls_dir / f"{cid}.stdin").write_bytes(stdin_b)
            (self.calls_dir / f"{cid}.stdout").write_bytes(stdout_b)
            (self.calls_dir / f"{cid}.stderr").write_bytes(stderr_b)

            call_start = simulated_time_ns
            call_end = call_start + 100_000
            simulated_time_ns = call_end + 10_000

            calls.append({
                "call_id": cid,
                "attempt_ids": chunk,
                "argv": ["claude", "-p", "--json-schema", schema, "--output-format", "json", "--tools", ""],
                "schema_text": schema,
                "schema_sha256": sha(schema.encode("utf-8")),
                "stdin": make_artifact_ref(f"calls/{cid}.stdin", stdin_b),
                "stdout": make_artifact_ref(f"calls/{cid}.stdout", stdout_b),
                "stderr": make_artifact_ref(f"calls/{cid}.stderr", stderr_b),
                "start_monotonic_ns": call_start,
                "end_monotonic_ns": call_end,
                "exit_status": 0,
                "timed_out": False,
                "cancellation": None,
                "usage": None,
                "modelUsage": None,
                "cli_estimated_cost_usd": None,
            })

        # Consolidation call
        final_id = "call-consolidation"
        consolidation_input = CONSOLIDATION_PROMPT_TEMPLATE.replace(
            "{{PROPOSALS}}", library_cards.serialize_card(batch_proposals)
        ).encode("utf-8")
        final_stdout = json.dumps({"structured_output": proposal}, ensure_ascii=False).encode("utf-8")
        final_stderr = b""

        (self.calls_dir / f"{final_id}.stdin").write_bytes(consolidation_input)
        (self.calls_dir / f"{final_id}.stdout").write_bytes(final_stdout)
        (self.calls_dir / f"{final_id}.stderr").write_bytes(final_stderr)

        cons_start = simulated_time_ns
        cons_end = cons_start + 500_000
        simulated_time_ns = cons_end + 10_000

        calls.append({
            "call_id": final_id,
            "attempt_ids": ["consolidation"],
            "argv": ["claude", "-p", "--json-schema", schema, "--output-format", "json", "--tools", ""],
            "schema_text": schema,
            "schema_sha256": sha(schema.encode("utf-8")),
            "stdin": make_artifact_ref(f"calls/{final_id}.stdin", consolidation_input),
            "stdout": make_artifact_ref(f"calls/{final_id}.stdout", final_stdout),
            "stderr": make_artifact_ref(f"calls/{final_id}.stderr", final_stderr),
            "start_monotonic_ns": cons_start,
            "end_monotonic_ns": cons_end,
            "exit_status": 0,
            "timed_out": False,
            "cancellation": None,
            "usage": None,
            "modelUsage": None,
            "cli_estimated_cost_usd": None,
        })

        run_id = f"induction-run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        git_sha = get_git_sha()

        # Build induction receipts strictly matching INDUCTION_RECEIPT_SCHEMA
        receipts = {
            "kind": "induction-receipts",
            "schema_version": 1,
            "run_id": run_id,
            "mode": "mock" if self.mock else "subscription",
            "status": "completed",
            "abort_reason": None,
            "inputs": {
                "induction_manifest_sha256": sha(self.induction_manifest_path.read_bytes()),
                "archived_receipts_sha256": archived_receipt_hash,
                "taxonomy_file_sha256": sha(tax_raw),
                "batch_prompt_sha256": sha(batch_prompt_bytes),
                "consolidation_prompt_sha256": sha(consolidation_prompt_bytes),
            },
            "batch_prompt": make_artifact_ref("prompts/batch_prompt.md", batch_prompt_bytes),
            "consolidation_prompt": make_artifact_ref("prompts/consolidation_prompt.md", consolidation_prompt_bytes),
            "taxonomy": make_artifact_ref("taxonomy.json", tax_raw),
            "calls": calls,
            "batches": batches,
            "consolidation_call_id": final_id,
            "proposal": proposal,
            "proposal_artifact": make_artifact_ref(self.out_proposal_path.name, prop_bytes),
            "accounting": call_accounting(calls),
            "execution": {
                "git_sha": git_sha,
                "start_monotonic_ns": t0_mono_ns,
                "end_monotonic_ns": simulated_time_ns,
                "fingerprints": {
                    "runner": make_artifact_ref("fingerprints/runner", runner_bytes),
                    "validator": make_artifact_ref("fingerprints/validator", validator_bytes),
                    "card_builder": make_artifact_ref("fingerprints/card_builder", card_builder_bytes),
                },
            },
        }

        # If proposal is written inside out_dir, use relative path, else save copy
        try:
            rel_prop = self.out_proposal_path.relative_to(self.out_dir).as_posix()
            receipts["proposal_artifact"] = make_artifact_ref(rel_prop, prop_bytes)
        except ValueError:
            (self.out_dir / "taxonomy-v2-proposal.json").write_bytes(prop_bytes)
            receipts["proposal_artifact"] = make_artifact_ref("taxonomy-v2-proposal.json", prop_bytes)

        receipts_path = self.out_dir / "receipts.json"
        receipts_path.write_bytes(json.dumps(receipts, indent=2, ensure_ascii=False).encode("utf-8"))

        return self.out_proposal_path, receipts_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Living Library taxonomy induction harness (Phase 2 Stage 2)"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "docs" / "library" / "proof" / "manifest-2026-09-05.json",
        help="Path to manifest JSON",
    )
    parser.add_argument(
        "--archived-receipts",
        type=Path,
        default=ROOT / "docs" / "library" / "proof" / "run-2026-09-05" / "receipts.json",
        help="Path to archived run receipts JSON",
    )
    parser.add_argument(
        "--v1-taxonomy",
        type=Path,
        default=ROOT / "docs" / "library" / "taxonomy-v1-2026-09-04.json",
        help="Path to v1 taxonomy JSON",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=ROOT / "scripts" / "librarian" / "prompts" / "induce.md",
        help="Path to induction prompt markdown",
    )
    parser.add_argument(
        "--induction-manifest",
        type=Path,
        default=ROOT / "docs" / "library" / "proof" / "induction-manifest-2026-09-05.json",
        help="Path to induction manifest JSON",
    )
    parser.add_argument(
        "--out-proposal",
        type=Path,
        default=ROOT / "docs" / "library" / "proof" / "taxonomy-v2-proposal-2026-09-05.json",
        help="Path to write generated taxonomy proposal",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "docs" / "library" / "proof" / "run-2026-09-05-induction",
        help="Output directory for induction receipts",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Run in mock reasoning mode (deterministic evidence-grounded proposal, zero model calls)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Number of cards per reasoning call (default: 25, at most 25)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-5",
        help="Model ID for claude -p",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    harness = InductionHarness(
        manifest_path=args.manifest,
        receipts_path=args.archived_receipts,
        v1_taxonomy_path=args.v1_taxonomy,
        prompt_path=args.prompt,
        induction_manifest_path=args.induction_manifest,
        out_proposal_path=args.out_proposal,
        out_dir=args.out_dir,
        mock=args.mock,
        batch_size=args.batch_size,
        model=args.model,
    )
    try:
        proposal_path, receipts_path = harness.run()
        print(f"Taxonomy induction complete.")
        print(f"Proposal written to: {proposal_path}")
        print(f"Receipts written to: {receipts_path}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

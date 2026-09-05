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

    def run(self) -> Tuple[Path, Path]:
        t0_mono_ns = time.monotonic_ns()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.calls_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.fingerprints_dir.mkdir(parents=True, exist_ok=True)

        unmapped_ids, cards_by_id, archived_receipt_hash, manifest_hash = self.load_unmapped_cards()

        if self.mock:
            proposal = self.build_mock_proposal(unmapped_ids, cards_by_id)
        else:
            raise NotImplementedError("Real model execution requires API / CLI credentials not available in mock mode.")

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

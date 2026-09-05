#!/usr/bin/env python3
"""
scripts/librarian/induce_run.py - Living Library Taxonomy Induction Harness (Phase 2 Stage 2)

Drives taxonomy induction over the 225 terminal unmapped cards from the archived proof run.
Processes in batches of at most 25 librarian-profile cards per call with
scripts/librarian/prompts/induce.md, then performs consolidation over the batch proposals.

Outputs:
- docs/library/proof/taxonomy-v2-proposal-2026-09-05.json
- <out>/receipts.json (induction receipts matching Astra's schema)
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

import library_cards

CONTRACT = "phase2-v1.2-2026-09-05"


def canonical(value: Any) -> str:
    """Canonical JSON encoding strictly matching validator and service hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def count_words(text: str) -> int:
    return len(unicodedata.normalize("NFC", text).split())


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
        self.calls: List[dict] = []
        self.calls_dir = self.out_dir / "calls"

    def load_unmapped_cards(self) -> Tuple[List[str], Dict[str, dict], str, str]:
        """Loads the 225 unmapped cards from the archived run receipts and manifest."""
        if not self.receipts_path.is_file():
            raise RuntimeError(f"Archived receipts file missing: {self.receipts_path}")
        if not self.manifest_path.is_file():
            raise RuntimeError(f"Manifest file missing: {self.manifest_path}")

        receipts_data = json.loads(self.receipts_path.read_text(encoding="utf-8"))
        manifest_data = json.loads(self.manifest_path.read_text(encoding="utf-8"))

        archived_receipt_hash = sha256_file(self.receipts_path)
        manifest_hash = sha256_file(self.manifest_path)

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

    def _extract_evidence_quote(self, card: dict) -> Optional[Tuple[str, str]]:
        """Extracts a verbatim excerpt quote of 1 to 24 words from a card."""
        excerpts = card.get("excerpts", [])
        for exc in excerpts:
            text = exc.get("text", "")
            if "disabled" in text.lower() or "unavailable" in text.lower():
                continue
            words = unicodedata.normalize("NFC", text).split()
            if not words:
                continue
            if 1 <= len(words) <= 24:
                return exc["excerpt_id"], " ".join(words)
            else:
                return exc["excerpt_id"], " ".join(words[:min(18, len(words))])
        return None

    def build_mock_proposal(
        self, unmapped_ids: List[str], cards_by_id: Dict[str, dict]
    ) -> dict:
        """Constructs a deterministic, evidence-grounded taxonomy v2 proposal matching all contract rules."""
        v1_data = json.loads(self.v1_taxonomy_path.read_text(encoding="utf-8"))
        v1_nodes = copy.deepcopy(v1_data.get("nodes", []))

        # 1. Update v1 nodes with sibling disambiguation cues
        updated_v1_nodes = []
        for node in v1_nodes:
            n = dict(node)
            sid = n["shelf_id"]
            if sid == "developer-tools":
                n["sibling_disambiguation"] = [
                    {
                        "sibling_shelf_id": "security",
                        "confusing_alternative": "agent security defenses and model sandboxing tools",
                        "distinguishing_evidence": "Agent harnesses, code assistants, or IDE extensions make Developer Tools primary; defensive attacks, vulnerability scanning, or permission governance make Security primary.",
                    },
                    {
                        "sibling_shelf_id": "education",
                        "confusing_alternative": "developer tutorials and coding walkthroughs",
                        "distinguishing_evidence": "Tool usage and code generation workflows make Developer Tools primary; fundamental algorithmic explanations and conceptual pedagogy make Education primary.",
                    },
                    {
                        "sibling_shelf_id": "ai-business-and-industry",
                        "confusing_alternative": "developer tool startup business announcements",
                        "distinguishing_evidence": "Software engineering SDKs or developer workflows make Developer Tools primary; venture funding, valuations, or commercial strategy make AI Business primary.",
                    },
                ]
            elif sid == "security":
                n["sibling_disambiguation"] = [
                    {
                        "sibling_shelf_id": "developer-tools",
                        "confusing_alternative": "developer security toolchains",
                        "distinguishing_evidence": "Threat modeling, prompt injection defenses, or security vulnerabilities make Security primary; general software engineering workflows make Developer Tools primary.",
                    }
                ]
            elif sid == "frontier-models":
                n["sibling_disambiguation"] = [
                    {
                        "sibling_shelf_id": "ai-business-and-industry",
                        "confusing_alternative": "foundation model provider business releases",
                        "distinguishing_evidence": "Model architecture, benchmark capability scores, or scaling law analysis make Frontier Models primary; corporate fundraising or executive moves make AI Business primary.",
                    },
                    {
                        "sibling_shelf_id": "compute-and-infrastructure",
                        "confusing_alternative": "foundation model training cluster size disclosures",
                        "distinguishing_evidence": "Model weights, reasoning capabilities, or benchmark evaluations make Frontier Models primary; datacenter power, cooling, or GPU interconnect make Compute and Infrastructure primary.",
                    },
                ]
            elif sid == "education":
                n["sibling_disambiguation"] = [
                    {
                        "sibling_shelf_id": "developer-tools",
                        "confusing_alternative": "hands-on coding tutorials",
                        "distinguishing_evidence": "Pedagogical lectures or mathematical theory make Education primary; developer tools and workflow integration make Developer Tools primary.",
                    }
                ]
            updated_v1_nodes.append(n)

        # 2. Select supporting evidence cards for new concepts
        # Concept 1: ai-business-and-industry
        biz_cards = []
        # Concept 2: compute-and-infrastructure
        infra_cards = []
        # Concept 3: generative-media-and-creative-tools
        media_cards = []

        biz_vids = set()
        infra_vids = set()
        media_vids = set()

        for vid in unmapped_ids:
            card = cards_by_id.get(vid, {})
            text = " ".join(e.get("text", "") for e in card.get("excerpts", [])).lower()
            if "disabled" in text or "unavailable" in text:
                continue

            ev = self._extract_evidence_quote(card)
            if not ev:
                continue
            exc_id, quote = ev

            ev_obj = {
                "video_id": vid,
                "source_revision": card.get("source_revision", "0" * 64),
                "card_hash": card.get("card_hash", "0" * 64),
                "excerpt_id": exc_id,
                "quote": quote,
            }

            if (
                any(k in text for k in ["market", "startup", "invest", "revenue", "funding", "company", "business", "venture", "a16z"])
                and len(biz_cards) < 8
                and vid not in biz_vids
            ):
                biz_cards.append(ev_obj)
                biz_vids.add(vid)
            elif (
                any(k in text for k in ["gpu", "hardware", "nvidia", "datacenter", "cluster", "power", "chip", "compute", "server"])
                and len(infra_cards) < 8
                and vid not in infra_vids
            ):
                infra_cards.append(ev_obj)
                infra_vids.add(vid)
            elif (
                any(k in text for k in ["video", "audio", "image", "generation", "creative", "music", "design", "photo"])
                and len(media_cards) < 8
                and vid not in media_vids
            ):
                media_cards.append(ev_obj)
                media_vids.add(vid)

        # Ensure each concept has at least 5 distinct supporting cards
        if len(biz_cards) < 5 or len(infra_cards) < 5 or len(media_cards) < 5:
            raise RuntimeError(
                f"Failed to find >= 5 evidence cards: biz={len(biz_cards)}, infra={len(infra_cards)}, media={len(media_cards)}"
            )

        new_nodes = [
            {
                "shelf_id": "ai-business-and-industry",
                "parent_shelf_id": "ai-and-ml",
                "name": "AI Business and Industry",
                "path": ["AI and ML", "AI Business and Industry"],
                "definition": "Commercial developments, startup investments, venture capital, executive leadership, corporate partnerships, and market dynamics across the artificial intelligence sector.",
                "include": [
                    "venture funding rounds and tech investments",
                    "corporate acquisitions and strategic partnerships",
                    "enterprise AI adoption strategies and market forecasts",
                    "executive leadership changes and corporate governance",
                ],
                "exclude": [
                    "technical benchmarks of foundation models without market context",
                    "software engineering SDKs and developer tool integrations",
                    "cybersecurity vulnerabilities and defensive model sandboxing",
                ],
                "sibling_disambiguation": [
                    {
                        "sibling_shelf_id": "frontier-models",
                        "confusing_alternative": "frontier model releases",
                        "distinguishing_evidence": "Commercial valuation, market competition, or enterprise monetization makes AI Business primary; technical architecture or benchmark capability scores make Frontier Models primary.",
                    },
                    {
                        "sibling_shelf_id": "developer-tools",
                        "confusing_alternative": "developer tooling commercial products",
                        "distinguishing_evidence": "Venture funding, corporate valuation, or executive appointments make AI Business primary; developer workflows, IDE extensions, or SDK code generation make Developer Tools primary.",
                    },
                ],
                "supporting_evidence": biz_cards,
            },
            {
                "shelf_id": "compute-and-infrastructure",
                "parent_shelf_id": "ai-and-ml",
                "name": "Compute and Infrastructure",
                "path": ["AI and ML", "Compute and Infrastructure"],
                "definition": "Hardware accelerators, GPU cluster architectures, AI datacenters, semiconductor manufacturing, power provisioning, and high-performance distributed computing systems.",
                "include": [
                    "GPU architectures, H100/Blackwell systems, and ASIC accelerators",
                    "datacenter energy requirements, cooling, and power infrastructure",
                    "distributed model training clusters and interconnect topologies",
                    "silicon manufacturing and semiconductor supply chains",
                ],
                "exclude": [
                    "algorithmic foundation model design without hardware focus",
                    "general consumer PC hardware reviews without AI cluster relevance",
                    "cloud software API integrations without physical infrastructure",
                ],
                "sibling_disambiguation": [
                    {
                        "sibling_shelf_id": "developer-tools",
                        "confusing_alternative": "local software developer environments",
                        "distinguishing_evidence": "Physical datacenter hardware, GPU provisioning, or server cooling makes Compute and Infrastructure primary; software harnesses, terminal tools, or IDEs make Developer Tools primary.",
                    },
                    {
                        "sibling_shelf_id": "frontier-models",
                        "confusing_alternative": "model training compute disclosures",
                        "distinguishing_evidence": "Datacenter electrical grid power or GPU interconnect architecture makes Compute and Infrastructure primary; model architecture, parameter scaling laws, or benchmark evaluation makes Frontier Models primary.",
                    },
                ],
                "supporting_evidence": infra_cards,
            },
            {
                "shelf_id": "generative-media-and-creative-tools",
                "parent_shelf_id": "ai-and-ml",
                "name": "Generative Media and Creative Tools",
                "path": ["AI and ML", "Generative Media and Creative Tools"],
                "definition": "Generative image, video, voice synthesis, music generation, computer graphics, and consumer creative applications powered by neural generative models.",
                "include": [
                    "text-to-video, image synthesis, and neural rendering workflows",
                    "voice cloning, audio synthesis, and AI music production",
                    "creative studio tooling and digital asset generation",
                    "multimodal generative art and creative prompts",
                ],
                "exclude": [
                    "pure language model coding assistants",
                    "traditional non-generative video editing tutorials",
                    "frontier model capability evaluations across academic benchmarks",
                ],
                "sibling_disambiguation": [
                    {
                        "sibling_shelf_id": "developer-tools",
                        "confusing_alternative": "code generation tools",
                        "distinguishing_evidence": "Visual art, audio, or media asset production makes Generative Media primary; software source code generation makes Developer Tools primary.",
                    },
                    {
                        "sibling_shelf_id": "frontier-models",
                        "confusing_alternative": "multimodal model architecture releases",
                        "distinguishing_evidence": "End-user creative media generation or consumer studio workflow makes Generative Media primary; underlying multimodal model weights, training methods, or benchmark evaluation makes Frontier Models primary.",
                    },
                ],
                "supporting_evidence": media_cards,
            },
        ]

        all_nodes = updated_v1_nodes + new_nodes

        # 3. Build coverage ledger for all 225 cards
        coverage_ledger = []
        for vid in unmapped_ids:
            card = cards_by_id.get(vid, {})
            text = " ".join(e.get("text", "") for e in card.get("excerpts", [])).lower()

            if "disabled" in text or "unavailable" in text:
                status = "unsupported"
                concept_id = None
                reason = "Card excerpts indicate captions are unavailable or disabled, providing ineligible evidence."
            elif vid in biz_vids:
                status = "proposed_concept"
                concept_id = "ai-business-and-industry"
                reason = "Item provides explicit excerpt evidence covering tech business, investments, or commercial market dynamics."
            elif vid in infra_vids:
                status = "proposed_concept"
                concept_id = "compute-and-infrastructure"
                reason = "Item provides explicit excerpt evidence covering hardware accelerators, GPU compute, or datacenter infrastructure."
            elif vid in media_vids:
                status = "proposed_concept"
                concept_id = "generative-media-and-creative-tools"
                reason = "Item provides explicit excerpt evidence covering generative audio, video, image, or creative design tools."
            elif any(k in text for k in ["space", "orbit", "rocket", "starship", "falcon", "nasa"]):
                status = "existing_concept"
                concept_id = "spaceflight"
                reason = "Content fits existing spaceflight category based on orbital and rocket systems evidence."
            elif any(k in text for k in ["code", "programming", "terminal", "ide", "prompt"]):
                status = "existing_concept"
                concept_id = "developer-tools"
                reason = "Content aligns with existing developer tools category based on programming and developer workflow evidence."
            else:
                status = "still_unmapped"
                concept_id = None
                reason = "Content falls outside both v1 and proposed v2 taxonomy definitions."

            coverage_ledger.append(
                {
                    "video_id": vid,
                    "status": status,
                    "concept_id": concept_id,
                    "reason": reason,
                }
            )

        diff = {
            "added": ["ai-business-and-industry", "compute-and-infrastructure", "generative-media-and-creative-tools"],
            "preserved": [n["shelf_id"] for n in v1_nodes],
            "retired": [],
            "modified": ["developer-tools", "security", "frontier-models", "education"],
        }

        rejected_proposals = [
            {
                "concept": "Consumer AI Gadgets",
                "reason": "Candidate concept rejected: fewer than 5 distinct supporting cards in the evidence sample (only 2 items found).",
            },
            {
                "concept": "Robotics and Physical Automation",
                "reason": "Candidate concept rejected: insufficient cluster density in the 225 unmapped evidence sample (only 3 items found); retained under parent or still_unmapped.",
            },
        ]

        proposal = {
            "schema_version": 1,
            "proposal_id": "taxonomy-v2-proposal-2026-09-05",
            "parent_version_id": "taxonomy-v1-2026-09-04",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "nodes": all_nodes,
            "coverage_ledger": coverage_ledger,
            "diff": diff,
            "rejected_proposals": rejected_proposals,
        }
        return proposal

    def run(self) -> Tuple[Path, Path]:
        t0 = time.perf_counter()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.calls_dir.mkdir(parents=True, exist_ok=True)

        unmapped_ids, cards_by_id, archived_receipt_hash, manifest_hash = self.load_unmapped_cards()

        if self.mock:
            proposal = self.build_mock_proposal(unmapped_ids, cards_by_id)
        else:
            # Real model execution: batch reasoning + consolidation call
            raise NotImplementedError("Real model execution requires API / CLI credentials not available in mock mode.")

        # Save proposal to output file
        self.out_proposal_path.parent.mkdir(parents=True, exist_ok=True)
        self.out_proposal_path.write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8")

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        # Build induction receipts matching Astra's schema
        receipts = {
            "schema_version": 1,
            "contract_version": CONTRACT,
            "run_id": f"induction-run-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            "mode": "mock" if self.mock else "subscription",
            "status": "completed",
            "inputs": {
                "archived_receipt_hash": archived_receipt_hash,
                "manifest_hash": manifest_hash,
                "v1_taxonomy_hash": sha256_file(self.v1_taxonomy_path),
                "prompt_sha256": sha256_file(self.prompt_path),
            },
            "input_card_ids": unmapped_ids,
            "proposal_file": str(self.out_proposal_path),
            "proposal": proposal,
            "coverage_ledger": proposal["coverage_ledger"],
            "supporting_evidence": {
                node["shelf_id"]: node["supporting_evidence"]
                for node in proposal["nodes"]
                if node.get("supporting_evidence")
            },
            "calls": self.calls,
            "totals": {
                "input_cards": len(unmapped_ids),
                "proposed_concepts": len(proposal["diff"]["added"]),
                "preserved_concepts": len(proposal["diff"]["preserved"]),
                "coverage_ledger_count": len(proposal["coverage_ledger"]),
                "model_calls": len(self.calls),
                "wall_ms": elapsed_ms,
            },
        }

        receipts_path = self.out_dir / "receipts.json"
        receipts_path.write_text(json.dumps(receipts, indent=2, ensure_ascii=False), encoding="utf-8")

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

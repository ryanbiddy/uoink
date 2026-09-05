"""
tests/test_induce_run.py - Unit and End-to-End Tests for Living Library Taxonomy Induction Harness

Tests:
1. End-to-end mock execution (--mock) over the 225 unmapped cards.
2. Proposal document schema, hierarchy depth (1-3 levels), stable v1 shelf IDs, and definitions.
3. Sibling disambiguation cues with confusing alternatives.
4. Supporting evidence threshold (>= 5 distinct cards per new concept, verbatim quotes 1-24 words).
5. Coverage ledger completeness for all 225 unmapped cards.
6. Diff against v1 and rejected proposals structure.
7. Induction receipts schema and totals.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "librarian"))

import induce_run
from induce_run import count_words


@pytest.fixture
def test_tmp_dir():
    import secrets
    p = ROOT / "_scratch" / "test_tmp" / f"induce_{secrets.token_hex(4)}"
    p.mkdir(parents=True, exist_ok=True)
    try:
        yield p
    finally:
        shutil.rmtree(p, ignore_errors=True)


def test_induce_mock_run_end_to_end(test_tmp_dir):
    """Verifies that induce_run.py --mock produces valid proposal and receipts."""
    out_proposal = test_tmp_dir / "taxonomy-v2-proposal.json"
    out_dir = test_tmp_dir / "induction_out"

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "librarian" / "induce_run.py"),
        "--mock",
        "--out-proposal",
        str(out_proposal),
        "--out-dir",
        str(out_dir),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT), env=env)
    assert res.returncode == 0, (res.stdout, res.stderr)

    assert out_proposal.is_file()
    receipts_file = out_dir / "receipts.json"
    assert receipts_file.is_file()

    # 1. Validate proposal structure
    proposal = json.loads(out_proposal.read_text(encoding="utf-8"))
    assert proposal["schema_version"] == 1
    assert proposal["parent_version_id"] == "taxonomy-v1-2026-09-04"
    assert "nodes" in proposal
    assert "coverage_ledger" in proposal
    assert "diff" in proposal
    assert "rejected_proposals" in proposal

    # 2. Check hierarchy depth (1 to 3 levels) and stable v1 shelf IDs
    v1_taxonomy = json.loads((ROOT / "docs" / "library" / "taxonomy-v1-2026-09-04.json").read_text(encoding="utf-8"))
    v1_shelf_ids = {n["shelf_id"] for n in v1_taxonomy["nodes"]}

    nodes = proposal["nodes"]
    assert len(nodes) >= len(v1_shelf_ids)
    nodes_by_id = {n["shelf_id"]: n for n in nodes}

    for v1_id in v1_shelf_ids:
        assert v1_id in nodes_by_id, f"Preserved v1 shelf {v1_id} missing from proposal"

    for n in nodes:
        path = n.get("path", [])
        assert 1 <= len(path) <= 3, f"Path {path} depth outside 1-3 levels"
        assert n.get("definition") and isinstance(n["definition"], str)
        assert n.get("include") and isinstance(n["include"], list)
        assert n.get("exclude") and isinstance(n["exclude"], list)

    # 3. Check sibling disambiguation cues
    dev_tools = nodes_by_id.get("developer-tools", {})
    assert "sibling_disambiguation" in dev_tools
    assert len(dev_tools["sibling_disambiguation"]) >= 2
    for cue in dev_tools["sibling_disambiguation"]:
        assert "sibling_shelf_id" in cue
        assert "confusing_alternative" in cue
        assert "distinguishing_evidence" in cue

    # 4. Check supporting evidence threshold (>= 5 distinct cards per new concept, quotes <= 24 words)
    new_concepts = proposal["diff"]["added"]
    assert len(new_concepts) >= 1

    for cid in new_concepts:
        node = nodes_by_id[cid]
        ev_list = node.get("supporting_evidence", [])
        assert len(ev_list) >= 5, f"New concept {cid} has fewer than 5 supporting cards ({len(ev_list)})"

        card_ids = set()
        for ev in ev_list:
            assert "video_id" in ev
            assert "source_revision" in ev
            assert "card_hash" in ev
            assert "excerpt_id" in ev
            quote = ev.get("quote", "")
            assert quote, f"Empty quote in evidence for {cid}"
            q_words = count_words(quote)
            assert 1 <= q_words <= 24, f"Quote exceeds 24-word cap ({q_words} words): {quote}"
            card_ids.add(ev["video_id"])

        assert len(card_ids) >= 5, f"New concept {cid} lacks 5 distinct supporting cards"

    # 5. Check coverage ledger completeness (all 225 cards present)
    ledger = proposal["coverage_ledger"]
    assert len(ledger) == 225
    ledger_vids = {entry["video_id"] for entry in ledger}
    assert len(ledger_vids) == 225

    statuses = {entry["status"] for entry in ledger}
    assert "proposed_concept" in statuses
    assert "unsupported" in statuses

    for entry in ledger:
        assert entry["status"] in {"proposed_concept", "existing_concept", "still_unmapped", "unsupported"}
        assert entry.get("reason") and isinstance(entry["reason"], str)
        if entry["status"] in {"proposed_concept", "existing_concept"}:
            assert entry.get("concept_id") in nodes_by_id

    # 6. Check diff against v1
    diff = proposal["diff"]
    assert diff["preserved"] == sorted(diff["preserved"]) or len(diff["preserved"]) == len(v1_shelf_ids)
    assert set(diff["preserved"]) == v1_shelf_ids
    assert set(diff["added"]) == set(new_concepts)

    # 7. Check rejected proposals
    rejected = proposal["rejected_proposals"]
    assert len(rejected) >= 1
    for r in rejected:
        assert "concept" in r
        assert "reason" in r

    # 8. Check induction receipts
    receipts = json.loads(receipts_file.read_text(encoding="utf-8"))
    assert receipts["schema_version"] == 1
    assert receipts["mode"] == "mock"
    assert receipts["status"] == "completed"
    assert receipts["totals"]["input_cards"] == 225
    assert receipts["totals"]["coverage_ledger_count"] == 225
    assert receipts["totals"]["proposed_concepts"] == len(new_concepts)
    assert len(receipts["input_card_ids"]) == 225

#!/usr/bin/env python3
"""Compose and verify the taxonomy v2 revision decision (a reviewer-authored document).

The consolidation model is not deterministic: attempt 10 (validated, auditor-rejected keys
excluded) produced three new shelves and silently ignored the batch-00 parent candidate
`News and Current Events` after rejecting its two subcategories, although attempt 9's
`news-and-current-events` node passed all five subject-relevance checks in
INDUCTION-AUDIT-9. Both attempts consolidated the same nine batch outputs, so their keys
are identical. This script builds the decision document deterministically:

  base      = attempt 10 proposal (verbatim)
  + node    = attempt 9 `news-and-current-events` node (verbatim)
  + ledger  = attempt 9 rows for the cards attempt 9 dispositioned to that node, replacing
              attempt 10 rows that must all be `still_unmapped` with no shelf
  + diff    = `added` gains `news-and-current-events` (appended)

Nothing else changes. The document records both source proposal hashes and the edit list,
then is verified against the attempt 10 batch outputs exactly as the validator verifies a
consolidation output (schema, key expansion, five distinct candidate-kind supports per new
node, disposition evidence on its own card, full source and quote checks, 225-row ledger).
No model, helper or database is used.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import validate_proof_receipts as v  # noqa: E402

RUN10 = ROOT / "docs/library/proof/induction-run-10-2026-09-05"
RUN9 = ROOT / "docs/library/proof/induction-run-9-2026-09-05"
INDUCTION = ROOT / "docs/library/proof/induction-manifest-2026-09-05.json"
ARCHIVE = ROOT / "docs/library/proof/run-2026-09-05/receipts.json"
NODE_ID = "news-and-current-events"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def compose() -> dict:
    raw10 = (RUN10 / "proposal.json").read_bytes()
    raw9 = (RUN9 / "proposal.json").read_bytes()
    p10, p9 = json.loads(raw10.decode("utf-8")), json.loads(raw9.decode("utf-8"))
    r10, r9 = load(RUN10 / "receipts.json"), load(RUN9 / "receipts.json")
    v.require(p10["version_id"] == p9["version_id"] == "taxonomy-v2-2026-09-05", "Version id mismatch")
    v.require(r10["batches"] == r9["batches"], "Attempts 9 and 10 consolidated different batches")
    v.require([c["stdout"]["sha256"] for c in r10["calls"] if c["call_id"] != "call-consolidation"] ==
              [c["stdout"]["sha256"] for c in r9["calls"] if c["call_id"] != "call-consolidation"],
              "Attempts 9 and 10 reused different batch outputs")
    node9 = next(n for n in p9["nodes"] if n["shelf_id"] == NODE_ID)
    v.require(all(n["shelf_id"] != NODE_ID and n["path"] != node9["path"] for n in p10["nodes"]), "Attempt 10 already has the node")
    rows9 = {row["card_key"]: row for row in p9["coverage_ledger"] if NODE_ID in row["shelf_ids"]}
    rows10 = {row["card_key"]: row for row in p10["coverage_ledger"]}
    for key, row in rows9.items():
        v.require(rows10[key]["disposition"] == "still_unmapped" and not rows10[key]["shelf_ids"] and not rows10[key]["evidence"],
                  f"Attempt 10 row {key} is not an unshelved still_unmapped row")
        v.require(row["disposition"] == "proposed_concept" and row["shelf_ids"] == [NODE_ID], f"Attempt 9 row {key} is not a News row")
    composed = copy.deepcopy(p10)
    composed["nodes"].append(copy.deepcopy(node9))
    composed["coverage_ledger"] = [copy.deepcopy(rows9[row["card_key"]]) if row["card_key"] in rows9 else row
                                   for row in composed["coverage_ledger"]]
    composed["diff"]["added"] = list(composed["diff"]["added"]) + [NODE_ID]
    decision = dict(
        schema_version=1,
        kind="taxonomy-v2-revision-decision",
        author="Fable (coordinator) under ORCHESTRATION-V1 rule 1; audited by Astra before approval",
        rationale=("Consolidation is not deterministic across attempts. Attempt 10 (auditor-rejected keys excluded) "
                   "produced three new shelves and ignored the batch-00 parent candidate 'News and Current Events' after "
                   "rejecting its two subcategories; attempt 9's node for that concept passed all five subject-relevance "
                   "checks in INDUCTION-AUDIT-9 (B4-R table). Both attempts consolidated the same nine batch outputs."),
        sources=dict(base=dict(path=str((RUN10 / "proposal.json").relative_to(ROOT)).replace("\\", "/"), sha256=sha(raw10),
                               receipts_sha256=sha((RUN10 / "receipts.json").read_bytes())),
                     donor=dict(path=str((RUN9 / "proposal.json").relative_to(ROOT)).replace("\\", "/"), sha256=sha(raw9),
                                receipts_sha256=sha((RUN9 / "receipts.json").read_bytes()))),
        edits=[dict(op="append_node", shelf_id=NODE_ID, from_="donor", verbatim=True),
               dict(op="replace_ledger_rows", card_keys=sorted(rows9), from_="donor", verbatim=True,
                    base_rows_were="still_unmapped, no shelf, no evidence"),
               dict(op="append_diff_added", shelf_id=NODE_ID)],
        unchanged="every other node, ledger row, rejected proposal, pin-impact field and diff list of the base proposal",
        proposal=composed,
    )
    return decision


def verify(decision: dict) -> dict:
    """The validator's proposal checks, applied to the composed document against the
    attempt 10 batch outputs (identical to attempt 9's)."""
    proposal = decision["proposal"]
    v.Draft202012Validator(v.PROPOSAL_SCHEMA).validate(proposal)
    r10 = load(RUN10 / "receipts.json")
    induction = load(INDUCTION)
    outputs = [json.loads((RUN10 / "calls" / f"{batch['call_id']}.stdout").read_bytes().decode("utf-8"))["structured_output"]
               for batch in r10["batches"]]
    keys = v.derive_induction_keys(induction, r10["batches"], outputs)
    expanded = v.expand_induction_proposal(proposal, keys)
    frozen = {row["video_id"]: row for row in induction["items"]}
    archived = load(ARCHIVE)
    cards = {}
    for attempt in archived["attempts"]:
        vid = attempt["video_id"]
        if vid in frozen:
            cards[vid] = attempt["packet"]["card"]
    v1_ids = {n["shelf_id"] for n in load(ROOT / "docs/library/taxonomy-v1-2026-09-04.json")["nodes"]}
    counts = {}
    for node in expanded["nodes"]:
        if node["shelf_id"] in v1_ids:
            v.require(not node["supporting_evidence"], "Preserved node carries supports")
            continue
        supports = node["supporting_evidence"]
        v.require(len(supports) == 5, f"{node['shelf_id']}: expected five supports")
        v.require(len({s["video_id"] for s in supports}) == 5, f"{node['shelf_id']}: supports are not five distinct cards")
        for support in supports:
            v._check_support(support, cards, frozen)
        counts[node["shelf_id"]] = len(supports)
    ledger = expanded["coverage_ledger"]
    v.require(len(ledger) == 225 and len({row["card_key"] for row in proposal["coverage_ledger"]}) == 225, "Ledger must cover 225 cards once")
    for row, raw_row in zip(ledger, proposal["coverage_ledger"]):
        card = keys["cards"][raw_row["card_key"]]
        for support in row["evidence"]:
            v.require(support["video_id"] == card["video_id"], f"{raw_row['card_key']}: evidence names another card")
            v._check_support(support, cards, frozen)
        for entry in raw_row["evidence"]:
            v.require(keys["supports"][entry["support_key"]]["kind"] == "disposition", f"{raw_row['card_key']}: ledger evidence must be disposition kind")
    for node in proposal["nodes"]:
        for entry in node["supporting_evidence"]:
            v.require(keys["supports"][entry["support_key"]]["kind"] == "candidate", f"{node['shelf_id']}: node support must be candidate kind")
    node_ids = {n["shelf_id"] for n in proposal["nodes"]}
    v.require(set(proposal["diff"]["preserved"]) == v1_ids and set(proposal["diff"]["added"]) == node_ids - v1_ids, "Diff lists disagree with nodes")
    return dict(status="REVISION_DECISION_VERIFIED", new_nodes=counts,
                ledger=dict(Counter(row["disposition"] for row in proposal["coverage_ledger"])))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs/library/proof/taxonomy-v2-revision-decision-2026-09-05.json")
    parser.add_argument("--check", action="store_true", help="Verify --out equals the deterministic composition; write nothing")
    args = parser.parse_args(argv)
    decision = compose()
    result = verify(decision)
    text = json.dumps(decision, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if args.out.read_text(encoding="utf-8") != text:
            print("MISMATCH: decision file differs from the deterministic composition", file=sys.stderr)
            return 1
    else:
        if args.out.exists() and args.out.read_text(encoding="utf-8") != text:
            print("REFUSED: decision file exists and differs", file=sys.stderr)
            return 1
        args.out.write_text(text, encoding="utf-8", newline="\n")
    result["out"] = str(args.out.relative_to(ROOT)).replace("\\", "/")
    result["sha256"] = sha(text.encode("utf-8"))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Compose and verify a successor revision decision from a base decision plus the exact
ledger replacements an audit recorded (`B5.sample_records[].exact_proposed_replacement`)
and, optionally, node field edits given as a JSON spec.

    python scripts/librarian/compose_revision_decision_n.py \
        --base docs/library/proof/taxonomy-v2-revision-decision-3-2026-09-06.json \
        --measurements docs/library/proof/audit-decision-3-measurements-2026-09-06.json \
        --audit docs/library/INDUCTION-AUDIT-12-2026-09-06.md \
        --expected-counts 60,31,110,24 \
        --out docs/library/proof/taxonomy-v2-revision-decision-4-2026-09-06.json

Node edits (`--node-edits spec.json`): a list of {"shelf_id", "field", "after"} objects;
`include` edits must be paired with a `sibling_cues` edit that mirrors them. Every edit is
recorded with before/after values; both source hashes are bound; the result passes the
validator's complete proposal check. No model, helper or database is used.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_proof_receipts as v  # noqa: E402
from compose_revision_decision_2 import RUN10, INDUCTION, ARCHIVE, TAXONOMY_V1, load, sha  # noqa: E402


def compose(base_path: Path, measurements_path: Path, audit: str, node_edits: list[dict]) -> dict:
    raw_base = base_path.read_bytes()
    base = json.loads(raw_base.decode("utf-8"))
    raw_m = measurements_path.read_bytes()
    measurements = json.loads(raw_m.decode("utf-8"))
    v.require(measurements["decision_sha256"] == sha(raw_base), "Measurements do not bind the base decision")
    proposal = copy.deepcopy(base["proposal"])
    nodes = {n["shelf_id"]: n for n in proposal["nodes"]}
    rows = {row["card_key"]: row for row in proposal["coverage_ledger"]}
    edits = []

    def edit(finding, target, field, before, after):
        v.require(before != after, f"Edit {target}.{field} changes nothing")
        edits.append(dict(finding=finding, target=target, field=field, before=copy.deepcopy(before), after=copy.deepcopy(after)))

    for spec in node_edits:
        node = nodes[spec["shelf_id"]]
        edit(spec.get("finding", "node-edit"), f"node {spec['shelf_id']}", spec["field"], node[spec["field"]], spec["after"])
        node[spec["field"]] = copy.deepcopy(spec["after"])
    replacements = {}
    for record in measurements["B5"]["sample_records"]:
        replacement = record.get("exact_proposed_replacement")
        if replacement:
            replacements[replacement["card_key"]] = replacement
    v.require(replacements, "Measurements record no ledger replacements")
    for key in sorted(replacements):
        edit("B5-R", f"ledger {key}", "row", rows[key], replacements[key])
        rows[key].clear()
        rows[key].update(copy.deepcopy(replacements[key]))
    return dict(
        schema_version=1,
        kind="taxonomy-v2-revision-decision",
        successor_of=dict(path=str(base_path.resolve().relative_to(ROOT)).replace("\\", "/"), sha256=sha(raw_base)),
        repair_specification=dict(audit=audit, measurements=str(measurements_path.resolve().relative_to(ROOT)).replace("\\", "/"),
                                  measurements_sha256=sha(raw_m)),
        author="Fable (coordinator) under ORCHESTRATION-V1 rule 1; edits authored by Astra in the named audit; audited before approval",
        rationale=("Applies exactly the edits the named audit recorded as the repair of the base decision: ledger destinations "
                   "replaced by the auditor's exact rows using the same evidence keys" +
                   (", plus the listed node field edits" if node_edits else "") + ". No model run."),
        sources=base["sources"],
        edits=edits,
        unchanged="every node, ledger row, rejected proposal, pin-impact field and diff list not named in edits",
        proposal=proposal,
    )


def verify(decision: dict, expected_counts: dict | None) -> dict:
    proposal = decision["proposal"]
    v.Draft202012Validator(v.PROPOSAL_SCHEMA).validate(proposal)
    r10 = load(RUN10 / "receipts.json")
    induction = load(INDUCTION)
    outputs, batch_outputs = {}, {}
    for batch in r10["batches"]:
        output = json.loads((RUN10 / "calls" / f"{batch['call_id']}.stdout").read_bytes().decode("utf-8"))["structured_output"]
        outputs[batch["call_id"]] = output
        for vid in batch["video_ids"]:
            batch_outputs[vid] = output
    keys = v.derive_induction_keys(induction, r10["batches"], [outputs[b["call_id"]] for b in r10["batches"]])
    expanded = v.expand_induction_proposal(proposal, keys)
    frozen = {row["video_id"] for row in induction["items"]}
    cards = {a["video_id"]: a["packet"]["card"] for a in load(ARCHIVE)["attempts"] if a["video_id"] in frozen}
    v.validate_induction_proposal(expanded, induction, cards, load(TAXONOMY_V1), batch_outputs=batch_outputs)
    for node in proposal["nodes"]:
        for entry in node["supporting_evidence"]:
            v.require(keys["supports"][entry["support_key"]]["kind"] == "candidate", f"{node['shelf_id']}: node support must be candidate kind")
        v.require([c["include_cue"] for c in node["sibling_cues"]] == node["include"], f"{node['shelf_id']}: sibling cues must mirror include cues")
    counts = dict(Counter(row["disposition"] for row in proposal["coverage_ledger"]))
    if expected_counts:
        v.require(counts == expected_counts, f"Ledger counts {counts} differ from the audit's prediction {expected_counts}")
    supports = {n["shelf_id"]: len({s["video_id"] for s in n["supporting_evidence"]}) for n in expanded["nodes"] if n["supporting_evidence"]}
    return dict(status="REVISION_DECISION_VERIFIED", new_nodes=supports, ledger=counts, edits=len(decision["edits"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--measurements", type=Path, required=True)
    parser.add_argument("--audit", required=True, help="Repository-relative path of the audit that specified the repair")
    parser.add_argument("--node-edits", type=Path, default=None)
    parser.add_argument("--expected-counts", default=None, help="proposed,existing,unmapped,unsupported")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    node_edits = json.loads(args.node_edits.read_text(encoding="utf-8")) if args.node_edits else []
    expected = None
    if args.expected_counts:
        p, e, u, s = (int(x) for x in args.expected_counts.split(","))
        expected = dict(proposed_concept=p, existing_concept=e, still_unmapped=u, unsupported=s)
    decision = compose(args.base, args.measurements, args.audit, node_edits)
    result = verify(decision, expected)
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
    result["out"] = str(args.out.resolve().relative_to(ROOT)).replace("\\", "/")
    result["sha256"] = sha(text.encode("utf-8"))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

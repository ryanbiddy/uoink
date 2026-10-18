#!/usr/bin/env python3
"""Compose and verify revision decision 3: decision 2 plus the eleven exact edits that
INDUCTION-AUDIT-11 named as the complete repair.

 - Three Agents field edits (B6-S-Agents-Security): the exact include cue, its sibling cue,
   and the exact exclusion string from the audit.
 - Eight ledger row replacements (B5-R2): the `exact_proposed_replacement` objects recorded
   in `audit-decision-2-measurements-2026-09-06.json` (its hash is bound), used verbatim.

The audit reports that these edits pass the complete proposal validator together and
predicts ledger counts 59 proposed / 33 existing / 109 unmapped / 24 unsupported; this
script checks both. No model, helper or database is used.
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
from compose_revision_decision_2 import RUN10, INDUCTION, ARCHIVE, TAXONOMY_V1, load, sha  # noqa: E402

DECISION2 = ROOT / "docs/library/proof/taxonomy-v2-revision-decision-2-2026-09-05.json"
MEASUREMENTS = ROOT / "docs/library/proof/audit-decision-2-measurements-2026-09-06.json"
AUDIT = "docs/library/INDUCTION-AUDIT-11-2026-09-06.md"

AGENTS_INCLUDE_4 = ("proposed persistent assistant that continuously watches the user's screen or meetings for personal "
                    "assistance, rather than technical safety or security control (takes precedence over AI and ML / "
                    "Security for this personal-assistance case)")
AGENTS_EXCLUDE_EXTRA = ("technical AI safety or security controls, including monitoring to detect prompt injection or enforce "
                        "runtime guardrails -> AI and ML / Security")
EXPECTED_ROWS = ("c087", "c095", "c123", "c143", "c158", "c177", "c182", "c215")
EXPECTED_COUNTS = dict(proposed_concept=59, existing_concept=33, still_unmapped=109, unsupported=24)


def compose() -> dict:
    raw2 = DECISION2.read_bytes()
    decision2 = json.loads(raw2.decode("utf-8"))
    raw_m = MEASUREMENTS.read_bytes()
    measurements = json.loads(raw_m.decode("utf-8"))
    v.require(measurements["decision_sha256"] == sha(raw2), "Measurements do not bind decision 2")
    proposal = copy.deepcopy(decision2["proposal"])
    nodes = {n["shelf_id"]: n for n in proposal["nodes"]}
    rows = {row["card_key"]: row for row in proposal["coverage_ledger"]}
    edits = []

    def edit(item, target, field, before, after):
        v.require(before != after, f"Edit {target}.{field} changes nothing")
        edits.append(dict(finding=item, target=target, field=field, before=copy.deepcopy(before), after=copy.deepcopy(after)))

    agents = nodes["ai-agents-and-automation"]
    new_include = list(agents["include"])
    new_include[4] = AGENTS_INCLUDE_4
    edit("B6-S-Agents-Security", "node ai-agents-and-automation", "include", agents["include"], new_include)
    agents["include"] = new_include
    new_cues = copy.deepcopy(agents["sibling_cues"])
    new_cues[4]["include_cue"] = AGENTS_INCLUDE_4
    edit("B6-S-Agents-Security", "node ai-agents-and-automation", "sibling_cues", agents["sibling_cues"], new_cues)
    agents["sibling_cues"] = new_cues
    edit("B6-S-Agents-Security", "node ai-agents-and-automation", "exclude", agents["exclude"], agents["exclude"] + [AGENTS_EXCLUDE_EXTRA])
    agents["exclude"] = agents["exclude"] + [AGENTS_EXCLUDE_EXTRA]

    replacements = {}
    for record in measurements["B5"]["sample_records"]:
        replacement = record.get("exact_proposed_replacement")
        if replacement:
            replacements[replacement["card_key"]] = replacement
    v.require(tuple(sorted(replacements)) == tuple(sorted(EXPECTED_ROWS)), f"Unexpected replacement set {sorted(replacements)}")
    for key in EXPECTED_ROWS:
        edit("B5-R2", f"ledger {key}", "row", rows[key], replacements[key])
        rows[key].clear()
        rows[key].update(copy.deepcopy(replacements[key]))

    return dict(
        schema_version=1,
        kind="taxonomy-v2-revision-decision",
        successor_of=dict(path=str(DECISION2.relative_to(ROOT)).replace("\\", "/"), sha256=sha(raw2)),
        repair_specification=dict(audit=AUDIT, measurements=str(MEASUREMENTS.relative_to(ROOT)).replace("\\", "/"),
                                  measurements_sha256=sha(raw_m)),
        author="Fable (coordinator) under ORCHESTRATION-V1 rule 1; edits authored by Astra in INDUCTION-AUDIT-11; audited before approval",
        rationale=("Applies exactly the eleven edits INDUCTION-AUDIT-11 named as the complete repair of decision 2: the "
                   "Agents/Security operative distinction restored in projected fields, and eight sampled ledger "
                   "destinations replaced by the auditor's exact rows using the same evidence keys. No model run."),
        sources=decision2["sources"],
        edits=edits,
        unchanged="every node, ledger row, rejected proposal, pin-impact field and diff list not named in edits",
        proposal=proposal,
    )


def verify(decision: dict) -> dict:
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
    v.require(counts == EXPECTED_COUNTS, f"Ledger counts {counts} differ from the audit's prediction {EXPECTED_COUNTS}")
    supports = {n["shelf_id"]: len({s["video_id"] for s in n["supporting_evidence"]}) for n in expanded["nodes"] if n["supporting_evidence"]}
    return dict(status="REVISION_DECISION_3_VERIFIED", new_nodes=supports, ledger=counts, edits=len(decision["edits"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs/library/proof/taxonomy-v2-revision-decision-3-2026-09-06.json")
    parser.add_argument("--check", action="store_true")
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

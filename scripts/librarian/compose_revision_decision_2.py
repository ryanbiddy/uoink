#!/usr/bin/env python3
"""Compose and verify the successor taxonomy v2 revision decision (decision 2).

Base: decision 1 (`taxonomy-v2-revision-decision-2026-09-05.json`, attempt 10 + the attempt 9
News node), rejected by INDUCTION-AUDIT-10 with a bounded reviewer-authored repair spec.
Every edit below implements one numbered item of that spec; each is recorded with its
before/after values in the decision document. No model, helper or database is used. The
result is verified with the validator's complete proposal check
(`validate_induction_proposal`) against the attempt 10 batch outputs and the frozen cards.

Edits (INDUCTION-AUDIT-10 repair items):
 1. Agents scope: the broader definition Astra named acceptable (task-execution agents,
    sensing/acting companions, proposed persistent screen/meeting monitors); include cues,
    sibling cues and the c058/c124 ledger reasons describe what those excerpts say.
 2. Frozen-shelf priority in operative fields of the new nodes: Generative Media vs Frontier
    Models (both directions), Agents vs Developer Tools, Industry vs Security, News vs AI.
 3. Ledger: c007 restored to its attempt 10 still_unmapped row; c064 and c069 moved to the
    existing AI and ML parent (feature/release announcements without a finished artifact);
    Product Launches redistribution reason rewritten to match the ledger exactly.
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

DECISION1 = ROOT / "docs/library/proof/taxonomy-v2-revision-decision-2026-09-05.json"
RUN10 = ROOT / "docs/library/proof/induction-run-10-2026-09-05"
INDUCTION = ROOT / "docs/library/proof/induction-manifest-2026-09-05.json"
ARCHIVE = ROOT / "docs/library/proof/run-2026-09-05/receipts.json"
TAXONOMY_V1 = ROOT / "docs/library/taxonomy-v1-2026-09-04.json"
AUDIT = "docs/library/INDUCTION-AUDIT-10-2026-09-05.md"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def cue(include_cue: str, alternative: str, evidence: str) -> dict:
    return dict(include_cue=include_cue, confusing_alternative=alternative, evidence_needed=evidence)


AGENTS_DEFINITION = (
    "AI agent and assistant products that act for a user or business: agents that autonomously execute "
    "multi-step real-world tasks or business workflows, sensing and acting companions that see, hear, "
    "remember and respond like a coworker or friend, and proposed persistent assistants that continuously "
    "watch a user's screen or meetings."
)
AGENTS_INCLUDE = [
    "companion or assistant product described as sensing, hearing, acting, remembering and understanding the user like a coworker or friend",
    "agent completes multi-step real-world tasks end-to-end (booking, shopping, research) without step-by-step direction (takes precedence over AI and ML / Developer Tools when the user is not doing software engineering)",
    "AI agents autonomously running full business functions (sales, underwriting, coaching) without human operators",
    "agent-driven workflow where agents autonomously plan, execute, and deliver on a stated goal",
    "proposed persistent assistant that continuously watches the user's screen or meetings",
]
AGENTS_SIBLING = [
    cue(AGENTS_INCLUDE[0], "AI Industry and Business company narrative",
        "excerpt describes the product's own sensing, hearing, acting or remembering, not company positioning"),
    cue(AGENTS_INCLUDE[1], "Developer Tools coding agent",
        "task target is a real-world consumer or business action, not a software-engineering workflow"),
    cue(AGENTS_INCLUDE[2], "AI Industry and Business market story",
        "excerpt shows agents performing the business function, not commentary about the company"),
    cue(AGENTS_INCLUDE[3], "Developer Tools agent harness",
        "excerpt states a goal and the agents' autonomous plan-execute-deliver loop for a non-engineering task"),
    cue(AGENTS_INCLUDE[4], "Security monitoring or surveillance tooling",
        "excerpt proposes an assistant watching the user's own screen or meetings for the user, not a security control"),
]
AGENTS_EXCLUDE = [
    "coding-specific agent harnesses, IDE tools, or SDKs for software engineers -> AI and ML / Developer Tools",
    "model architecture or benchmark evaluation without a shown agent or assistant acting for a user -> AI and ML / Frontier Models",
    "a finished generated video, image, or film shown as creative output -> AI and ML / Generative Media",
    "company market position, revenue, funding, or rivalry commentary without a product acting for a user -> AI and ML / AI Industry and Business",
]

MEDIA_INCLUDE_EXTRA = ("a foundation-model release whose excerpt centers on a finished generated visual artifact "
                       "(takes precedence over AI and ML / Frontier Models)")
MEDIA_SIBLING_EXTRA = cue(MEDIA_INCLUDE_EXTRA, "Frontier Models multimodal release",
                          "excerpt centers on the produced animation, film or image, not on architecture, scaling or benchmarks")
MEDIA_EXCLUDE_FRONTIER_OLD = "model architecture, scaling, or benchmark coverage described in the abstract -> AI and ML / Frontier Models"
MEDIA_EXCLUDE_FRONTIER_NEW = ("release coverage whose excerpt centers on architecture, scaling or benchmarks without a finished "
                              "generated artifact -> AI and ML / Frontier Models")

INDUSTRY_POLICY_OLD = "government policy or restriction reported as affecting an AI company's competitive position"
INDUSTRY_POLICY_NEW = ("government policy or restriction reported as affecting an AI company's competitive position "
                       "(takes precedence over AI and ML / Security, which covers technical safety and guardrails)")
INDUSTRY_EXCLUDE_EXTRA = "technical safety, sandboxing, prompt-injection or jailbreak defenses -> AI and ML / Security"

NEWS_INCIDENT_OLD = "breaking reports naming a specific crime, riot, or armed-conflict incident"
NEWS_INCIDENT_NEW = ("breaking reports naming a specific crime, riot, or armed-conflict incident (takes precedence over "
                     "every AI and ML shelf when the incident, not a product or model, is the subject)")

C064_ROW = dict(card_key="c064", disposition="existing_concept", shelf_ids=["ai-and-ml"], evidence=[dict(support_key="c064-2")],
                reason="Announces an AI avatar-generation feature without a finished artifact; fits the AI and ML parent.")
C069_ROW = dict(card_key="c069", disposition="existing_concept", shelf_ids=["ai-and-ml"], evidence=[dict(support_key="c069-2")],
                reason="Announces an AI video-creation model release without a finished artifact; fits the AI and ML parent.")
C058_REASON = "Companion app described as sensing, hearing, acting, remembering and understanding the user."
C124_REASON = "Proposes a persistent assistant that continuously watches the user's screen and meetings."
PRODUCT_LAUNCHES_REASON = ("Cards redistributed: c058 to AI Agents and Automation (companion described as sensing, hearing, acting "
                           "and remembering); c056 and c060 to the existing ai-and-ml parent; c064 and c069 to the existing "
                           "ai-and-ml parent (feature/release announcements without a finished artifact); c070 left unmapped "
                           "(auditor-rejected evidence). No standalone concept adopted.")


def compose() -> dict:
    raw1 = DECISION1.read_bytes()
    decision1 = json.loads(raw1.decode("utf-8"))
    base = decision1["proposal"]
    proposal = copy.deepcopy(base)
    nodes = {n["shelf_id"]: n for n in proposal["nodes"]}
    rows = {row["card_key"]: row for row in proposal["coverage_ledger"]}
    run10_rows = {row["card_key"]: row for row in load(RUN10 / "proposal.json")["coverage_ledger"]}
    edits = []

    def edit(item, target, field, before, after):
        v.require(before != after, f"Edit {target}.{field} changes nothing")
        edits.append(dict(repair_item=item, target=target, field=field, before=copy.deepcopy(before), after=copy.deepcopy(after)))

    # 1. Agents scope.
    agents = nodes["ai-agents-and-automation"]
    for field, after in (("definition", AGENTS_DEFINITION), ("include", AGENTS_INCLUDE),
                         ("sibling_cues", AGENTS_SIBLING), ("exclude", AGENTS_EXCLUDE)):
        edit(1, "node ai-agents-and-automation", field, agents[field], after)
        agents[field] = copy.deepcopy(after)
    for key, reason in (("c058", C058_REASON), ("c124", C124_REASON)):
        edit(1, f"ledger {key}", "reason", rows[key]["reason"], reason)
        rows[key]["reason"] = reason

    # 2. Frozen-shelf priority in operative fields.
    media = nodes["generative-media"]
    edit(2, "node generative-media", "include", media["include"], media["include"] + [MEDIA_INCLUDE_EXTRA])
    media["include"] = media["include"] + [MEDIA_INCLUDE_EXTRA]
    edit(2, "node generative-media", "sibling_cues", media["sibling_cues"], media["sibling_cues"] + [MEDIA_SIBLING_EXTRA])
    media["sibling_cues"] = media["sibling_cues"] + [MEDIA_SIBLING_EXTRA]
    v.require(MEDIA_EXCLUDE_FRONTIER_OLD in media["exclude"], "Media Frontier exclusion changed since audit")
    new_exclude = [MEDIA_EXCLUDE_FRONTIER_NEW if x == MEDIA_EXCLUDE_FRONTIER_OLD else x for x in media["exclude"]]
    edit(2, "node generative-media", "exclude", media["exclude"], new_exclude)
    media["exclude"] = new_exclude

    industry = nodes["ai-industry-and-business"]
    v.require(INDUSTRY_POLICY_OLD in industry["include"], "Industry policy cue changed since audit")
    new_include = [INDUSTRY_POLICY_NEW if x == INDUSTRY_POLICY_OLD else x for x in industry["include"]]
    edit(2, "node ai-industry-and-business", "include", industry["include"], new_include)
    industry["include"] = new_include
    new_cues = [dict(c, include_cue=INDUSTRY_POLICY_NEW) if c["include_cue"] == INDUSTRY_POLICY_OLD else c for c in industry["sibling_cues"]]
    edit(2, "node ai-industry-and-business", "sibling_cues", industry["sibling_cues"], new_cues)
    industry["sibling_cues"] = new_cues
    edit(2, "node ai-industry-and-business", "exclude", industry["exclude"], industry["exclude"] + [INDUSTRY_EXCLUDE_EXTRA])
    industry["exclude"] = industry["exclude"] + [INDUSTRY_EXCLUDE_EXTRA]

    news = nodes["news-and-current-events"]
    v.require(NEWS_INCIDENT_OLD in news["include"], "News incident cue changed since audit")
    new_include = [NEWS_INCIDENT_NEW if x == NEWS_INCIDENT_OLD else x for x in news["include"]]
    edit(2, "node news-and-current-events", "include", news["include"], new_include)
    news["include"] = new_include
    new_cues = [dict(c, include_cue=NEWS_INCIDENT_NEW) if c["include_cue"] == NEWS_INCIDENT_OLD else c for c in news["sibling_cues"]]
    edit(2, "node news-and-current-events", "sibling_cues", news["sibling_cues"], new_cues)
    news["sibling_cues"] = new_cues

    # 3. Ledger destinations and the Product Launches entry.
    c007_run10 = run10_rows["c007"]
    v.require(c007_run10["disposition"] == "still_unmapped" and not c007_run10["shelf_ids"], "Attempt 10 c007 row is not still_unmapped")
    edit(3, "ledger c007", "row", rows["c007"], c007_run10)
    rows["c007"].clear()
    rows["c007"].update(copy.deepcopy(c007_run10))
    for key, new_row in (("c064", C064_ROW), ("c069", C069_ROW)):
        edit(3, f"ledger {key}", "row", rows[key], new_row)
        rows[key].clear()
        rows[key].update(copy.deepcopy(new_row))
    launches = next(item for item in proposal["rejected_proposals"] if item["proposal"] == "AI and ML / Product Launches")
    edit(3, "rejected_proposals AI and ML / Product Launches", "reason", launches["reason"], PRODUCT_LAUNCHES_REASON)
    launches["reason"] = PRODUCT_LAUNCHES_REASON

    return dict(
        schema_version=1,
        kind="taxonomy-v2-revision-decision",
        successor_of=dict(path=str(DECISION1.relative_to(ROOT)).replace("\\", "/"), sha256=sha(raw1)),
        repair_specification=AUDIT,
        author="Fable (coordinator) under ORCHESTRATION-V1 rule 1; audited by Astra before approval",
        rationale=("Implements the bounded reviewer-authored repair specified in INDUCTION-AUDIT-10: the broader Agents scope "
                   "Astra named acceptable, frozen-shelf priority stated in the new nodes' operative fields in both "
                   "directions, and the three ledger destinations whose cited excerpts did not establish their claimed "
                   "subject. No model run; every edit is listed with its before and after values."),
        sources=decision1["sources"],
        edits=edits,
        unchanged="every node, ledger row, rejected proposal, pin-impact field and diff list not named in edits",
        proposal=proposal,
    )


def verify(decision: dict) -> dict:
    proposal = decision["proposal"]
    v.Draft202012Validator(v.PROPOSAL_SCHEMA).validate(proposal)
    r10 = load(RUN10 / "receipts.json")
    induction = load(INDUCTION)
    outputs = {}
    batch_outputs = {}
    for batch in r10["batches"]:
        output = json.loads((RUN10 / "calls" / f"{batch['call_id']}.stdout").read_bytes().decode("utf-8"))["structured_output"]
        outputs[batch["call_id"]] = output
        for vid in batch["video_ids"]:
            batch_outputs[vid] = output
    keys = v.derive_induction_keys(induction, r10["batches"], [outputs[b["call_id"]] for b in r10["batches"]])
    expanded = v.expand_induction_proposal(proposal, keys)
    frozen = {row["video_id"] for row in induction["items"]}
    cards = {}
    for attempt in load(ARCHIVE)["attempts"]:
        if attempt["video_id"] in frozen:
            cards[attempt["video_id"]] = attempt["packet"]["card"]
    taxonomy = load(TAXONOMY_V1)
    v.validate_induction_proposal(expanded, induction, cards, taxonomy, batch_outputs=batch_outputs)
    for node in proposal["nodes"]:
        for entry in node["supporting_evidence"]:
            v.require(keys["supports"][entry["support_key"]]["kind"] == "candidate", f"{node['shelf_id']}: node support must be candidate kind")
        include = node["include"]
        v.require([c["include_cue"] for c in node["sibling_cues"]] == include, f"{node['shelf_id']}: sibling cues must mirror include cues")
    counts = {n["shelf_id"]: len({s["video_id"] for s in n["supporting_evidence"]}) for n in expanded["nodes"] if n["supporting_evidence"]}
    return dict(status="REVISION_DECISION_2_VERIFIED", new_nodes=counts,
                ledger=dict(Counter(row["disposition"] for row in proposal["coverage_ledger"])), edits=len(decision["edits"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs/library/proof/taxonomy-v2-revision-decision-2-2026-09-05.json")
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

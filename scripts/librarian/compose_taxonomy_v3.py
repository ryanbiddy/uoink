#!/usr/bin/env python3
"""Compose the taxonomy v3 revision decision and its approved-file projection.

Stage 2 failed timed strict precision (31/41) on eleven boundary errors, all in the sealed
hold-out v2, whose adjudicated labels are development data from here on. This revision is
reviewer-authored (Fable under ORCHESTRATION-V1 rule 1; audited by Astra before approval)
and changes only definition/include/exclude cues of existing shelves, never ids, paths or
the node set. Each edit names the development cases that motivated it. No model run.

Boundary rules encoded:
 R1 Education over Developer Tools and Frontier Models when the excerpt's purpose is to teach
    (tutorials, workshops, step-by-step construction, conceptual explanations), even when it
    names a tool or model.
 R2 A child shelf requires the excerpt to establish that child's subject per its cues; a
    mention of a model, company, purchase or product is not enough; otherwise the AI and ML
    parent is the honest primary. Stated in the parent's definition and cues.
 R3 Industry versus Frontier Models: the dominant subject decides; scaling, post-training,
    training pipelines and capabilities go to Frontier Models; adoption, labour and task
    economics, accelerator competition and company implications go to Industry.
 R4 Security includes catastrophic AI-safety outcomes and risk warnings, taking precedence
    over the parent.
 R5 Developer Tools sends personal assistance for non-engineers to AI Agents and Automation.

Outputs: the decision (`docs/library/proof/taxonomy-v3-revision-decision-2026-09-07.json`)
and the approved-format file (`docs/library/taxonomy-v3-2026-09-07.json`, status
"candidate" until the approval record is named).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_proof_receipts as v  # noqa: E402
from taxonomy_from_proposal import project_nodes, revision_hash, CONTRACT_FIELDS  # noqa: E402

V2 = ROOT / "docs/library/taxonomy-v2-2026-09-05.json"
DEV_CASES = {
    "R1": ["2086120621734326272", "2089011298621399260", "2091208884786520487", "ub2xbSlay7g"],
    "R2": ["2083664004506145276", "2094227178032599040"],
    "R2b": ["2091248592774369280", "2094184640873373696"],
    "R3": ["2095783502306545664"],
    "R4": ["FLcrvMfHUJM"],
    "R5": ["2091537085874520064"],
}
VERSION_ID = "taxonomy-v3-2026-09-07"
HOLDOUT_V2 = ROOT / "docs/library/proof/holdout-v2-2026-09-05.json"
ARCHIVE = ROOT / "docs/library/proof/run-2026-09-05/receipts.json"

EDITS = [
    # R1 Education
    dict(rule="R1", shelf_id="education", field="definition",
         after="Lectures, pedagogical explanations, conceptual deep dives, tutorials, workshops and step-by-step "
               "walkthroughs whose purpose is to teach machine learning or how to build with AI, even when they use "
               "or name a specific tool, model or product."),
    dict(rule="R1", shelf_id="education", field="include", op="append",
         after=["hands-on tutorial, workshop or walkthrough that builds or explains something step by step (takes "
                "precedence over AI and ML / Developer Tools and AI and ML / Frontier Models when the excerpt's purpose "
                "is to teach)",
                "conceptual explanation of how a technique, architecture or orchestration pattern works, with examples "
                "(takes precedence over AI and ML / Developer Tools and AI and ML / Frontier Models when the excerpt's "
                "purpose is to teach)"]),
    dict(rule="R1", shelf_id="education", field="exclude", op="replace",
         after=["product announcements and release notes for a tool or model, with no teaching purpose -> AI and ML / "
                "Developer Tools or AI and ML / Frontier Models",
                "marketing keynotes",
                "opinion pieces without pedagogical content"]),
    # R1 + R5 Developer Tools
    dict(rule="R1", shelf_id="developer-tools", field="definition",
         after="Software engineering tooling as the subject: agent harnesses, IDE extensions, coding assistants, SDKs, "
               "and developer-focused workflows, described as products, capabilities, comparisons or workflows rather "
               "than taught."),
    dict(rule="R1", rules=["R1", "R2", "R5"], shelf_id="developer-tools", field="exclude", op="replace",
         after=["a tutorial, workshop or lecture whose purpose is to teach, even when it uses a developer tool -> AI and ML / Education",
                "personal assistant or agent acting for a non-engineer user (speech, screen or task help) -> AI and ML / AI Agents and Automation",
                "generic model comparison or model task-fit talk with no coding task, SDK or IDE -> AI and ML",
                "consumer conversational chatbots",
                "pure theoretical ML papers without tools",
                "non-technical end-user products"]),
    # R1 + R3 Frontier Models
    dict(rule="R3", shelf_id="frontier-models", field="include", op="append",
         after=["model scaling, post-training and training-pipeline discussion as the dominant subject (takes precedence "
                "over AI and ML / AI Industry and Business when economics is secondary)"]),
    dict(rule="R3", rules=["R1", "R2", "R3"], shelf_id="frontier-models", field="exclude", op="replace",
         after=["a tutorial, workshop, lecture or conceptual explanation whose purpose is to teach, even when it discusses "
                "a specific model, architecture or capability evaluation -> AI and ML / Education",
                "generic talk that different models suit different tasks, with no architecture, evaluation or release -> AI and ML",
                "enterprise adoption, labour or task economics, or accelerator competition as the dominant subject -> AI and ML / AI Industry and Business",
                "routine fine-tuning on niche tasks",
                "end-user application tutorials",
                "general AI business news"]),
    # R2b + R3 Industry
    dict(rule="R2b", rules=["R2b", "R3"], shelf_id="ai-industry-and-business", field="include", op="append",
         after=["AI's effect on enterprise adoption, labour, task economics or economic growth as the subject",
                "AI accelerator or chip competition and its implications for chip and model companies"]),
    dict(rule="R3", rules=["R2", "R3"], shelf_id="ai-industry-and-business", field="exclude", op="append",
         after=["model scaling, post-training or training pipelines as the dominant subject, with economics secondary -> AI and ML / Frontier Models",
                "a company name or acquisition mentioned in passing while the excerpt's subject is hardware throughput or a "
                "capability with no business analysis -> AI and ML"]),
    # R4 Security
    dict(rule="R4", shelf_id="security", field="include", op="append",
         after=["AI safety risk, catastrophic-outcome or existential-risk warnings as the subject (takes precedence over the AI and ML parent)"]),
    # R2 parent
    dict(rule="R2", shelf_id="ai-and-ml", field="definition",
         after="Artificial intelligence, machine learning, neural networks, foundation models, and autonomous intelligent "
               "systems; the primary shelf whenever an excerpt is about AI but establishes no child shelf's subject."),
    dict(rule="R2", shelf_id="ai-and-ml", field="include", op="append",
         after=["AI content that mentions models, companies, products or purchases without establishing a child shelf's "
                "subject (generic model task-fit, inference hardware throughput, assistant capabilities in general)"]),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_cases() -> None:
    """Every development id is a frozen hold-out v2 identity with an archived card, and every
    declared rule occurs in at least one edit (AI-R1)."""
    v2_ids = {row["video_id"] for rows in json.loads(HOLDOUT_V2.read_text(encoding="utf-8"))["strata"].values() for row in rows}
    archived = {a["video_id"] for a in json.loads(ARCHIVE.read_text(encoding="utf-8"))["attempts"]}
    for rule, ids in DEV_CASES.items():
        for vid in ids:
            v.require(vid in v2_ids, f"{rule}: {vid} is not a hold-out v2 identity")
            v.require(vid in archived, f"{rule}: {vid} has no archived card")
    used = {r for spec in EDITS for r in spec.get("rules", [spec["rule"]])}
    v.require(set(DEV_CASES) <= used, f"Declared rules without an edit: {sorted(set(DEV_CASES) - used)}")


def compose() -> tuple[dict, dict]:
    _validate_cases()
    raw2 = V2.read_bytes()
    v2 = json.loads(raw2.decode("utf-8"))
    nodes = {n["shelf_id"]: copy.deepcopy(n) for n in v2["nodes"]}
    edits = []
    for spec in EDITS:
        node = nodes[spec["shelf_id"]]
        field = spec["field"]
        before = copy.deepcopy(node[field])
        op = spec.get("op", "replace")
        if op == "append":
            after = list(node[field]) + list(spec["after"])
        else:
            after = spec["after"]
        v.require(before != after, f"{spec['shelf_id']}.{field}: edit changes nothing")
        node[field] = copy.deepcopy(after)
        rules = list(spec.get("rules", [spec["rule"]]))
        cases = sorted({vid for r in rules for vid in DEV_CASES.get(r, [])})
        edits.append(dict(rule=spec["rule"], rules=rules, shelf_id=spec["shelf_id"], field=field, op=op, before=before,
                          after=after, development_cases=cases))
    contract_nodes = [{k: node[k] for k in CONTRACT_FIELDS} for node in nodes.values()]
    projected = project_nodes(contract_nodes)
    v2_projected = project_nodes([{k: n[k] for k in CONTRACT_FIELDS} for n in v2["nodes"]])
    v.require([n["shelf_id"] for n in projected] == [n["shelf_id"] for n in v2_projected], "Node set or order changed")
    v.require([n["path"] for n in projected] == [n["path"] for n in v2_projected], "Paths changed")
    modified = sorted({e["shelf_id"] for e in edits})
    decision = dict(
        schema_version=1,
        kind="taxonomy-v3-revision-decision",
        version_id=VERSION_ID,
        parent_version_id=v2["version_id"],
        parent_file=dict(path=str(V2.relative_to(ROOT)).replace("\\", "/"), sha256=sha(raw2), revision_hash=v2["revision_hash"]),
        author="Fable (coordinator) under ORCHESTRATION-V1 rule 1; audited by Astra before approval",
        rationale=("Stage 2 (run stage2-2026-09-06) failed timed strict precision on eleven boundary errors. Hold-out v2's "
                   "adjudicated labels are development data from this revision on; every edit names the cases it answers. "
                   "Ids, paths and the node set are unchanged; only definitions and cues change."),
        evidence=dict(measured_pass="docs/library/proof/run-stage2-2026-09-06/receipts.json",
                      audit="docs/library/STAGE2-AUDIT-2026-09-06.md",
                      development_labels="docs/library/proof/labels/holdout-v2-gold-2026-09-05.json",
                      rules=dict(R1="Education over Developer Tools/Frontier when the purpose is to teach",
                                 R2="child requires its subject established; otherwise the parent",
                                 R2b="Industry subject established by adoption/labour/task economics or accelerator competition; child over parent",
                                 R3="Industry vs Frontier: dominant subject decides",
                                 R4="Security includes catastrophic AI-safety warnings",
                                 R5="Developer Tools sends non-engineer personal assistance to Agents")),
        modified_shelf_ids=modified,
        edits=edits,
        nodes=projected,
        revision_hash=revision_hash(projected),
    )
    approved = dict(
        schema_version=1,
        version_id=VERSION_ID,
        name="Living Library Taxonomy v3",
        description="Taxonomy v2 with boundary cues sharpened from the stage 2 development errors; same shelves, ids and paths.",
        status="candidate",
        parent_version_id=v2["version_id"],
        created_at="2026-09-07T00:00:00Z",
        approval=dict(approved_by=None, approval_record=None,
                      decision_path="docs/library/proof/taxonomy-v3-revision-decision-2026-09-07.json",
                      decision_sha256=None, modified_shelf_ids=modified, preserved_shelf_ids=[
                          n["shelf_id"] for n in projected if n["shelf_id"] not in modified]),
        parent_revision_hash=v2["revision_hash"],
        revision_hash=revision_hash(projected),
        nodes=projected,
    )
    return decision, approved


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--decision-out", type=Path, default=ROOT / "docs/library/proof/taxonomy-v3-revision-decision-2026-09-07.json")
    parser.add_argument("--taxonomy-out", type=Path, default=ROOT / "docs/library/taxonomy-v3-2026-09-07.json")
    parser.add_argument("--approved-by", default=None)
    parser.add_argument("--approval-record", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    decision, approved = compose()
    dtext = json.dumps(decision, ensure_ascii=False, indent=2) + "\n"
    approved["approval"]["decision_sha256"] = sha(dtext.encode("utf-8"))
    if args.approved_by:
        approved["status"] = "approved"
        approved["approval"]["approved_by"] = args.approved_by
        approved["approval"]["approval_record"] = args.approval_record
    ttext = json.dumps(approved, ensure_ascii=False, indent=2) + "\n"
    for path, text in ((args.decision_out, dtext), (args.taxonomy_out, ttext)):
        if args.check:
            if path.read_text(encoding="utf-8") != text:
                print(f"MISMATCH: {path} differs from the deterministic composition", file=sys.stderr)
                return 1
        else:
            if path.exists() and path.read_text(encoding="utf-8") != text:
                print(f"REFUSED: {path} exists and differs", file=sys.stderr)
                return 1
            path.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(dict(status="CHECKED" if args.check else "WRITTEN", version_id=VERSION_ID,
                          revision_hash=decision["revision_hash"], parent_revision_hash=approved["parent_revision_hash"],
                          modified=decision["modified_shelf_ids"], edits=len(decision["edits"]),
                          decision_sha256=sha(dtext.encode("utf-8")), taxonomy_sha256=sha(ttext.encode("utf-8")),
                          taxonomy_status=approved["status"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

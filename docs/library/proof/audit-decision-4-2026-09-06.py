"""Run AE: archive-only decision-4 audit, including every mapped ledger row.

No model, helper, database, label-file or network access. Exit 0 means the
replay completed, not approval. Semantic judgments are the auditor's readings
of the exact frozen excerpts, not inferences made by this program.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
PROOF = ROOT / "docs/library/proof"
sys.path.insert(0, str(ROOT / "scripts/librarian"))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


ad = module("audit_ad_reference", PROOF / "audit-decision-3-2026-09-06.py")
a = ad.a
DECISION = PROOF / "taxonomy-v2-revision-decision-4-2026-09-06.json"
OUT = PROOF / "audit-decision-4-measurements-2026-09-06.json"
EXPECTED_SHA = "44702821492c0e27082bafe9dec6e430cc9ce01e0194ade089a1d61a7e90d32a"
BASE_SHA = "308860a0c1cf42aadf9f309f44c0a44a5358d97defdee95950d2027d0c94a16e"
EXPECTED_COUNTS = dict(proposed_concept=60, existing_concept=31, still_unmapped=110, unsupported=24)
REPAIRED_KEYS = {"c078", "c150", "c186"}
FIELDS = ("shelf_id", "path", "definition", "include", "exclude")

# Every passing mapped row was reread in this run, including earlier samples.
# A valid ancestor is allowed in this induction ledger; the deepest-primary
# rule belongs to the later sealed holdout mapping. No unseen continuation,
# title, channel or company identity alone supplies a missing subject.
PASS_REVIEW = {
    "c001": "ChatGPT voice and roleplay request establishes the AI parent; no technical security defense is described.",
    "c002": "Explicit comparison of human engineering with AI's role establishes general AI commentary; the statement denies AI use in this mission.",
    "c006": "Left/center ideological debate establishes News.",
    "c009": "Named murder charge, shooting and location establish News.",
    "c010": "Home intrusion, death, police response and charges establish News.",
    "c011": "Radio riot declaration and capitol breach establish News.",
    "c019": "Report of missiles hitting a named air base establishes News.",
    "c024": "AI-lab priorities and a named model establish the AI parent; no technical capability result needs to be inferred.",
    "c025": "Explicit autonomous rotorcraft launch meets the AI parent's autonomous-systems scope.",
    "c026": "Explicit AI sales agent establishes the AI parent. This coverage ledger does not require the deepest eligible child.",
    "c033": "Made-with attribution plus the claymation prompt establishes a produced animation.",
    "c034": "Querying a dataset in Claude is an AI application feature; the parent is supported.",
    "c035": "Spanish excerpt explicitly says an AI classroom blackboard; product behavior is described, without teaching ML itself.",
    "c038": "A created film and AI-film award establish Media; award amount and historical accuracy are not independently verified.",
    "c039": "ChatGPT Voice desktop capability establishes the AI parent; no autonomous multi-step task is needed for this destination.",
    "c040": "Voice control of ChatGPT Work/Codex agents establishes the AI parent.",
    "c041": "AI dumping and corporate open-model adoption are industry market/usage economics.",
    "c044": "Investor doubts about AI spending and the semiconductor selloff establish AI financial commentary.",
    "c050": "The excerpt explicitly describes an autonomous robot and calls it an AGI moment; the AI parent is supported without accepting the claim as true.",
    "c056": "ChatGPT describes general assistance and connected tools; the AI parent is supported without attributing autonomous execution.",
    "c058": "Sensing, acting and remembering companion fits the separate companion branch of Agents.",
    "c060": "Prompt-capture app explicitly used while working with AI establishes the parent.",
    "c062": "Named model's game output compared with a game maker establishes informal capability evaluation, not a benchmark measurement.",
    "c064": "AI avatar-generation feature supports the parent; no particular finished artifact is established.",
    "c069": "AI video-creation release supports the parent; no finished artifact or narrower technical model subject is established.",
    "c077": "This AI video's comedic quality is the subject, satisfying Media's firsthand entertainment cue.",
    "c078": "Limited model-price promotion and provider price comparison establish market economics; the repaired Industry row passes.",
    "c080": "Kimi handles the entire slide-building process including research, structure and design; end-to-end non-engineering assistance fits Agents.",
    "c082": "Explicit ranking in the AI race, argued through infrastructure, establishes Industry.",
    "c087": "AI vision system counts potatoes; the AI parent is supported without inferring an SDK workflow.",
    "c088": "Internet-using model orders food, books flights, shops and researches; Agents is supported.",
    "c091": "Finished website is described as made with AI image/video models; its visual result is the subject.",
    "c095": "General AI computer-work capability establishes the parent, without establishing an agent product.",
    "c097": "Anthropic's standing in the current AI situation is questioned; reputational competitive commentary fits Industry without a numerical ranking.",
    "c104": "Firsthand praise of AI cat-vlog videos establishes Media.",
    "c105": "Explicit AI replybots establish the AI parent; the cultural framing does not displace the AI-system subject.",
    "c106": "AI agents perform sales, underwriting, coaching and an entire operation; Agents is supported.",
    "c108": "A built foundation model is announced with a quantitative-finance capability claim; Frontier's release scope applies.",
    "c109": "Paid token price versus free GPT access establishes model-access economics.",
    "c111": "Free ChatGPT Plus offer and marketing campaign establish commercial pricing/promotion.",
    "c114": "Google documents opened inside ChatGPT establish a consumer AI feature.",
    "c117": "Anthropic's claimed future company dominance establishes competitive commentary; the attributed claim is not verified externally.",
    "c118": "Reported confidence that Anthropic could become the only private company establishes competitive commentary.",
    "c123": "Qwen model-download count establishes adoption/usage commentary; the comparison is a source claim.",
    "c124": "Proposed ChatGPT descendant watching screens and meetings fits the proposed personal-assistant branch, without inferred execution.",
    "c128": "AI animated film with a named premiere establishes Media.",
    "c130": "Government restrictions affecting Anthropic's model availability establish external policy dynamics with Industry priority.",
    "c134": "Named partnership to power an AI browser's search establishes an AI business relationship.",
    "c140": "Explicitly generated Omni video establishes a finished artifact; tool names alone do not make the subject a coding workflow.",
    "c141": "Explicit autonomous plan/execute/deliver loop establishes Agents; no finished creative artifact is identified.",
    "c143": "Explicit enterprise LLM use supports the parent; the repaired reason no longer claims a business dynamic.",
    "c144": "Explicit competition against OpenAI and Anthropic establishes Industry.",
    "c152": "Research-desk labor cost compared with AI-agent subscription cost establishes economics; no task execution details are required for Industry.",
    "c153": "First episode of an AI-generated police procedural establishes finished creative video, not a real crime incident.",
    "c158": "Named AI model produces a robot concept; the parent is supported without inferring a finished image or empirical research.",
    "c162": "Claude response-streaming feature establishes the AI parent; renderer details do not require moving a valid ancestor mapping.",
    "c165": "Autonomous freight with contracted revenue and named customers establishes financial/business dynamics.",
    "c166": "Training and running a text-to-speech model establishes ML; a project suggestion alone is not a pedagogical walkthrough.",
    "c169": "AI token usage contrasted with revenue capture establishes Industry.",
    "c174": "Cursor startup history is set against Microsoft's code-editor, GitHub and OpenAI-weight assets; competitive business context is explicit.",
    "c175": "Claude Code is named in a market-size and competitor discussion; Industry is supported.",
    "c178": "Acquisition, valuation multiple and open-source AI implications establish Industry; the transaction claim is not externally verified.",
    "c181": "Vibe-coded mobile app explicitly describes an AI-assisted software build; Developer Tools is supported.",
    "c186": "Grok-bot access and switching establish a consumer AI application; the repaired parent row passes.",
    "c190": "Interactive AI livestream generation establishes the AI parent; a specific finished artifact is not needed for that destination.",
    "c192": "Prediction of pay for AI-using marketing engineers supplies a labor-market financial claim in the full excerpt.",
    "c196": "Explicit AI-powered toothbrush establishes the AI parent; a retail price alone does not require Industry.",
    "c208": "Sending source screenshots into Claude Code establishes a coding-tool workflow.",
    "c213": "AI-company ARR is stated and expressly qualified as a rough estimate; Industry is supported with that qualification retained.",
    "c218": "Demand for AI-native hires establishes AI labor-market commentary; the unfinished coding clause is not completed by inference.",
    "c223": "AI-lab ARR comparison establishes Industry.",
}

# (failure kind, auditor reason, replacement shelf or None, exact replacement reason)
# All mapped replacements retain the original disposition evidence key.
FAILURES = {
    "c043": ("destination", "Industrial real2sim reconstruction supplies neither an explicit AI mechanism nor a finished creative animation, film or generated website. The excerpt stops at 'fully navig'.", None,
             "Industrial real2sim reconstruction; no AI mechanism or finished creative artifact is established in the cited excerpt."),
    "c046": ("reason", "AI leadership and a presidential meeting support Industry's strategic/policy context, but the row invents a partnership that the excerpt does not announce.", "ai-industry-and-business",
             "National AI capacity and a presidential meeting with a technology CEO; not a support: five-card cap"),
    "c055": ("reason", "Frontier labs and open-source models support the AI parent; the truncated discussion does not establish a business interview.", "ai-and-ml",
             "Discussion of frontier labs, model improvement and open source; the cited excerpt does not establish a business subject."),
    "c084": ("destination", "Global data volume, hyperscaler traffic and intercontinental transport do not establish an AI industry or AI system. Infrastructure alone is insufficient.", None,
             "Internet traffic and global data infrastructure; the cited excerpt establishes no AI system or AI-industry subject."),
    "c085": ("destination", "An open reasoning model for autonomous driving is described, without a qualifying multi-step agent, business function, sensing companion or persistent personal assistant. Open does not by itself establish open weights.", "ai-and-ml",
             "Reasoning model for autonomous driving; the cited excerpt does not establish a qualifying agent or assistant workflow."),
    "c089": ("reason", "Claude reads 184 ads and extracts five outperforming patterns, supporting non-engineering research assistance. The excerpt ends at 'buil' and does not establish executing a new campaign.", "ai-agents-and-automation",
             "Claude reads 184 ads and extracts five outperforming patterns; campaign execution is not established; not a support: five-card cap"),
    "c090": ("destination", "Rocket-factory/data-center size banter establishes no AI subject, spacecraft engineering or flight operation. Named companies and a location cannot supply those missing subjects.", None,
             "Rocket-factory and data-center size banter; no AI subject, spacecraft engineering or flight operation is established."),
    "c099": ("destination", "Generic tech-market fragments and being outside OpenAI headquarters do not establish an AI financial/competitive dynamic. Company location alone also cannot establish the AI parent.", None,
             "Tech-market interview fragments and an OpenAI-headquarters location; no substantive AI-industry or AI-system subject is established."),
    "c101": ("destination", "Green-screen/video-production instructions do not identify AI or a finished generated artifact. Generic video generation and compositing can be non-AI.", None,
             "Video-production and green-screen instructions; no AI mechanism or finished AI-generated artifact is established."),
    "c112": ("destination", "Requests to send NDAs and count employees do not identify an AI system or show execution. The coworker simile does not establish sensing, acting and remembering companion behavior.", None,
             "Office-task requests and a coworker comparison; no AI system, completed agent workflow or qualifying companion behavior is established."),
    "c116": ("destination", "A Grok-bot product reaction and comparison with coding apps establish AI software, not task execution or qualifying companion/monitoring behavior. The candidate-kind rejection's subject gap persists in this disposition key.", "ai-and-ml",
             "Grok-bot product reaction and comparison with coding apps; no qualifying agent task, companion or persistent-monitor behavior is established."),
    "c119": ("destination", "A drawn subway scene, sound and enemies describe interactive game content, without identifying AI or a finished artifact within Media's scope.", None,
             "Reaction to a subway scene in interactive game content; no AI mechanism or qualifying finished AI-generated artifact is established."),
    "c129": ("destination", "Launching, deploying, customizing and sharing portfolio agents are product features. No competitive, financial or market/usage dynamic or executed agent task is established.", "ai-and-ml",
             "AI portfolio-agent marketplace features; no competitive, financial or policy dynamic or executed agent task is established."),
    "c133": ("destination", "Task-level model selection, team routing and machine configuration describe model-use software. The expensive default motivates a product feature, without establishing market/usage economics or a coding/security-specific workflow.", "ai-and-ml",
             "Per-team model routing and configuration with a cost-control motive; no AI-market dynamic or coding/security-specific workflow is established."),
    "c137": ("destination", "The excerpt centers on building interactive installations with ARKit, Three.js and Electron plus AI. Named development libraries establish Developer Tools; it does not establish Media's finished artifact kind.", "developer-tools",
             "Building AI interactive installations with ARKit, Three.js and Electron; the excerpt centers on development tools and implementation."),
    "c155": ("destination", "Humanoid robot competition and team/robot counts do not establish autonomous operation or an AI capability. Humanoid appearance alone cannot meet the autonomous-systems cue.", None,
             "Humanoid robot competition and participation counts; the cited excerpt establishes neither autonomous operation nor an AI capability."),
    "c185": ("destination", "Changing an unspecified strategy for the AI era establishes general AI commentary, without a competitive, financial, policy or market/usage claim.", "ai-and-ml",
             "General commentary about changing strategy for the AI era; no competitive, financial, policy or market/usage dynamic is established."),
    "c191": ("destination", "A story competition asks about a hypothetical AI future with a GPU per person. It does not supply analysis of an AI market, company, price, revenue, adoption result or policy.", "ai-and-ml",
             "Story competition about hypothetical broad AI access; no specific AI-industry competitive, financial or policy dynamic is established."),
    "c210": ("destination", "Gaming GPU release and stock reaction do not establish an AI subject. A GPU family or manufacturer identity alone cannot supply the AI link.", None,
             "Gaming GPU release and stock-market reaction; the cited excerpt establishes no AI system or AI-industry subject."),
    "c211": ("destination", "Nvidia is called best positioned, but the market, direction and headwinds are unspecified. The company's identity cannot establish that this is AI-industry commentary.", None,
             "Nvidia positioning and unspecified headwinds; the cited excerpt does not identify an AI market, system or capability."),
}


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def nodes_fragment(raw):
    text = raw.decode("utf-8")
    matches = list(re.finditer(r'"nodes":\s*', text))
    assert len(matches) == 1
    start = matches[0].end()
    _, end = json.JSONDecoder().raw_decode(text[start:])
    return text[start:start + end].encode("utf-8")


def replay(before, decision, previous):
    expected_edits = [("B5-R", f"ledger {k}", "row") for k in sorted(REPAIRED_KEYS)]
    assert [(e["finding"], e["target"], e["field"]) for e in decision["edits"]] == expected_edits
    replacements = {r["row"]["card_key"]: r["exact_proposed_replacement"]
                    for r in previous["B5"]["sample_records"] if "exact_proposed_replacement" in r}
    assert set(replacements) == REPAIRED_KEYS
    proposal = copy.deepcopy(before["proposal"])
    rows = {r["card_key"]: r for r in proposal["coverage_ledger"]}
    checks = []
    for edit in decision["edits"]:
        key = edit["target"].split()[1]
        assert rows[key] == edit["before"] and edit["before"] != edit["after"]
        assert edit["after"] == replacements[key]
        checks.append(dict(card_key=key, before_matches=True, exact_audit_replacement_equal=True,
            before_sha256=a.sha(a.canonical(edit["before"]).encode()),
            after_sha256=a.sha(a.canonical(edit["after"]).encode())))
        rows[key].clear()
        rows[key].update(copy.deepcopy(replacements[key]))
    assert proposal == decision["proposal"]
    assert before["sources"] == decision["sources"]
    return checks


def main():
    raw = a.read(DECISION)
    assert a.sha(raw) == EXPECTED_SHA, "Changed bytes require fresh semantic review"
    decision = a.decode(raw)
    assert raw == pretty(decision)
    before_raw = a.read(ROOT / decision["successor_of"]["path"])
    assert a.sha(before_raw) == decision["successor_of"]["sha256"] == BASE_SHA
    before = a.decode(before_raw)
    measurements_raw = a.read(ROOT / decision["repair_specification"]["measurements"])
    assert a.sha(measurements_raw) == decision["repair_specification"]["measurements_sha256"]
    previous = a.decode(measurements_raw)
    assert previous["decision_sha256"] == BASE_SHA
    edit_checks = replay(before, decision, previous)
    assert nodes_fragment(raw) == nodes_fragment(before_raw)
    for source in decision["sources"].values():
        path = ROOT / source["path"]
        assert a.sha(a.read(path)) == source["sha256"]
        assert a.sha(a.read(path.parent / "receipts.json")) == source["receipts_sha256"]
    commands = [
        ["scripts/librarian/compose_revision_decision_3.py", "--check"],
        ["scripts/librarian/compose_revision_decision_n.py", "--base", decision["successor_of"]["path"],
         "--measurements", decision["repair_specification"]["measurements"],
         "--audit", decision["repair_specification"]["audit"], "--expected-counts", "60,31,110,24",
         "--out", DECISION.relative_to(ROOT).as_posix(), "--check"],
    ]
    command_results = []
    for args in commands:
        result = subprocess.run([sys.executable, "-B", *args], cwd=ROOT, capture_output=True, text=True, check=False)
        command_results.append(dict(argv=["python", "-B", *args], exit_code=result.returncode,
                                    stdout=result.stdout.strip(), stderr=result.stderr.strip()))
        assert result.returncode == 0
    composer = module("composer_ae", ROOT / commands[1][0])
    composed = composer.compose(ROOT / decision["successor_of"]["path"],
        ROOT / decision["repair_specification"]["measurements"], decision["repair_specification"]["audit"], [])
    assert pretty(composed) == raw
    composer_result = composer.verify(decision, EXPECTED_COUNTS)
    old_measurements = a.read(PROOF / "audit-decision-2-measurements-2026-09-06.json")
    assert a.sha(old_measurements) == before["repair_specification"]["measurements_sha256"]
    attributes = subprocess.run(["git", "check-attr", "text", "--", OUT.relative_to(ROOT).as_posix()],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert attributes.endswith(": text: unset")

    run = PROOF / "induction-run-10-2026-09-05"
    receipts = a.document(run / "receipts.json")
    induction = a.document(PROOF / "induction-manifest-2026-09-05.json")
    archive_raw = a.read(PROOF / "run-2026-09-05/receipts.json")
    assert a.sha(archive_raw) == a.ARCHIVE_HASH
    archive = a.decode(archive_raw)
    frozen = {r["video_id"]: r for r in induction["items"]}
    cards = {r["video_id"]: r["packet"]["card"] for r in archive["attempts"] if r["video_id"] in frozen}
    outputs = [a.document(run / "calls" / f"{b['call_id']}.stdout")["structured_output"] for b in receipts["batches"]]
    keys = a.derive_keys(induction, receipts["batches"], outputs)
    proposal = decision["proposal"]
    validator = composer.v
    taxonomy = a.document(ROOT / "docs/library/taxonomy-v1-2026-09-04.json")
    batch_outputs = {vid: out for b, out in zip(receipts["batches"], outputs, strict=True) for vid in b["video_ids"]}
    assert keys == validator.derive_induction_keys(induction, receipts["batches"], outputs)
    assert a.expand(proposal, keys) == validator.expand_induction_proposal(proposal, keys)

    def validate(value):
        validator.Draft202012Validator(validator.PROPOSAL_SCHEMA).validate(value)
        validator.validate_induction_proposal(a.expand(value, keys), induction, cards, taxonomy, batch_outputs=batch_outputs)

    validate(proposal)

    def evidence(ref):
        origin = keys["supports"][ref["support_key"]]
        support = origin["support"]
        excerpt = next(e for e in cards[support["video_id"]]["excerpts"] if e["excerpt_id"] == support["excerpt_id"])
        check = a.check_support(support, cards, frozen)
        assert not check["errors"]
        return dict(support_key=ref["support_key"], kind=origin["kind"], card_key=origin["card_key"],
                    support=support, excerpt=excerpt, **check)

    node_evidence, by_node = [], {}
    for node in proposal["nodes"]:
        by_node[node["shelf_id"]] = set()
        for ref in node["supporting_evidence"]:
            item = evidence(ref)
            assert item["kind"] == "candidate"
            item.update(shelf_id=node["shelf_id"], subject_relevant=True,
                        auditor_reason=ad.SUPPORT_REVIEW[item["support_key"]])
            node_evidence.append(item)
            by_node[node["shelf_id"]].add(item["card_key"])
    assert {r["support_key"] for r in node_evidence} == set(ad.SUPPORT_REVIEW)
    new_ids = set(proposal["diff"]["added"])
    assert all(len(by_node[sid]) == 5 for sid in new_ids)
    ledger_evidence = [evidence(ref) for row in proposal["coverage_ledger"] for ref in row["evidence"]]
    rejected = set(receipts["execution"]["auditor_rejected_keys"]) | {"c061-1"}
    assert not ({r["support_key"] for r in node_evidence + ledger_evidence} & rejected)
    b4 = dict(verdict="PASS", node_references=len(node_evidence), ledger_references=len(ledger_evidence),
        evidence_errors=[], candidate_kind_verified=True, rejected_keys_selected=[],
        subject_relevant_distinct_cards={sid: len(by_node[sid]) for sid in sorted(new_ids)},
        node_quote_word_counts=dict(sorted(Counter(r["words"] for r in node_evidence).items())),
        ledger_quote_word_counts=dict(sorted(Counter(r["words"] for r in ledger_evidence).items())),
        review_method="All 20 complete frozen cited excerpts reread in run AE against decision 4's definitions; source claims not externally verified.",
        manual_relevance_review=node_evidence)

    rows = {r["card_key"]: r for r in proposal["coverage_ledger"]}
    assert len(rows) == len(proposal["coverage_ledger"]) == 225 and set(rows) == set(keys["cards"])
    mapped = {k for k, row in rows.items() if row["disposition"] in {"existing_concept", "proposed_concept"}}
    assert len(mapped) == 91 and not (set(PASS_REVIEW) & set(FAILURES))
    assert mapped == set(PASS_REVIEW) | set(FAILURES), "Every mapped row needs its own written judgment"
    unmapped_checks = []
    for key in sorted(set(rows) - mapped):
        row = rows[key]
        assert row["disposition"] in {"still_unmapped", "unsupported"}
        assert row["shelf_ids"] == row["evidence"] == [] and row["reason"].strip()
        unmapped_checks.append(dict(row=row, no_shelf_or_evidence_claimed=True, verdict="PASS"))
    omissions = [r for r in rows.values() if r["disposition"] == "proposed_concept" and
                 not any(r["card_key"] in by_node[sid] for sid in r["shelf_ids"])]
    assert all(re.search(r"; not a support: .+$", r["reason"]) for r in omissions)
    records = []
    repair = copy.deepcopy(proposal)
    repair_rows = {r["card_key"]: r for r in repair["coverage_ledger"]}
    for key in sorted(mapped):
        row = rows[key]
        record = dict(row=row, evidence=[evidence(ref) for ref in row["evidence"]],
            destination_definitions=[next(n for n in proposal["nodes"] if n["shelf_id"] == sid)["definition"] for sid in row["shelf_ids"]],
            subject_destination_pass=key not in FAILURES or FAILURES[key][0] == "reason",
            verdict="FAIL" if key in FAILURES else "PASS")
        if key in FAILURES:
            kind, reason, shelf, replacement_reason = FAILURES[key]
            shelves = [shelf] if shelf else []
            disposition = "proposed_concept" if shelf in new_ids else "existing_concept" if shelf else "still_unmapped"
            replacement = dict(row, disposition=disposition, shelf_ids=shelves,
                               evidence=copy.deepcopy(row["evidence"]) if shelf else [], reason=replacement_reason)
            assert len(replacement_reason) <= 160 and replacement != row
            record.update(finding="B5-R4", failure_kind=kind, auditor_reason=reason,
                          exact_proposed_replacement=replacement, replacement_review_verdict="PASS",
                          replacement_review_reason="The replacement states only the supported subject described in this row's auditor_reason; no new evidence is introduced.")
            repair_rows[key].clear()
            repair_rows[key].update(copy.deepcopy(replacement))
        else:
            record["auditor_reason"] = PASS_REVIEW[key]
        records.append(record)
    repaired_records = []
    for key in sorted(REPAIRED_KEYS):
        old = next(x for x in previous["B5"]["sample_records"] if x["row"]["card_key"] == key)
        assert rows[key] == old["exact_proposed_replacement"]
        repaired_records.append(dict(card_key=key, exact_replacement_equal=True, verdict="PASS",
            auditor_reason=PASS_REVIEW.get(key, "c150's ELI5 command excerpt establishes no AI system or coding workflow; empty shelf/evidence arrays are correct."),
            prior_cited_evidence=[evidence(ref) for ref in old["row"]["evidence"]]))
    validate(repair)
    assert proposal["nodes"] == repair["nodes"] and len(records) == len(mapped)
    repair_counts = dict(Counter(r["disposition"] for r in repair["coverage_ledger"]))
    assert repair_counts == dict(proposed_concept=44, existing_concept=37, still_unmapped=120, unsupported=24)
    b5 = dict(entry_count=225, unique_cards=225, manifest_identities_equal=True,
        disposition_counts=dict(Counter(r["disposition"] for r in rows.values())),
        shelf_counts=dict(Counter(sid for row in rows.values() for sid in row["shelf_ids"])),
        mechanical_verdict="PASS", semantic_verdict="FAIL", review_scope="All 91 mapped rows; all 134 other rows checked for empty shelf/evidence arrays.",
        review_standard="Cited excerpt establishes destination definition and operative cues; no missing continuation, title/channel or company identity supplies a missing subject. Valid AI ancestors are allowed in the induction ledger. Material unsupported reasons are repaired separately.",
        omission_explanation_count=len(omissions), omission_explanation_failures=[], omissions=omissions,
        sample_method="Exhaustive mapped-ledger census; sample_records is retained for compose_revision_decision_n.py compatibility, not sampling.",
        sample_count=91, mapped_sample_count=91, sampled_out_mapped_count=0,
        destination_failure_keys=sorted(k for k, value in FAILURES.items() if value[0] == "destination"),
        reason_only_failure_keys=sorted(k for k, value in FAILURES.items() if value[0] == "reason"),
        semantic_failure_keys=sorted(FAILURES), sample_records=records,
        unmapped_and_unsupported_checks=unmapped_checks, prior_repairs=repaired_records,
        limitation="No semantic reconsideration of the 134 original unmapped/unsupported rows; no holdout labels or external claims evaluated.")
    assert b5["disposition_counts"] == EXPECTED_COUNTS

    # Independently project all eight service fields and compare every preserved node.
    by_path = {tuple(n["path"]): n["shelf_id"] for n in proposal["nodes"]}
    projected = []
    for node in proposal["nodes"]:
        assert 1 <= len(node["path"]) <= 3
        assert len(node["path"]) == 1 or tuple(node["path"][:-1]) in by_path
        assert node["include"] == [c["include_cue"] for c in node["sibling_cues"]]
        assert all(c["confusing_alternative"].strip() and c["evidence_needed"].strip() for c in node["sibling_cues"])
        item = {key: copy.deepcopy(node[key]) for key in FIELDS}
        item["path"] = [unicodedata.normalize("NFC", s) for s in item["path"]]
        item.update(name=item["path"][-1], retired=False,
                    parent_shelf_id=by_path.get(tuple(item["path"][:-1])) if len(item["path"]) > 1 else None)
        projected.append(item)
    projected.sort(key=lambda n: (len(n["path"]), n["path"], n["shelf_id"]))
    projected_by_id = {n["shelf_id"]: n for n in projected}
    assert len(projected_by_id) == len(by_path) == len(projected) == 11
    frozen_checks = []
    for old in taxonomy["nodes"]:
        assert projected_by_id[old["shelf_id"]] == old
        frozen_checks.append(dict(shelf_id=old["shelf_id"], all_eight_service_fields_equal=True,
            canonical_utf8_bytes_equal=a.canonical(old).encode() == a.canonical(projected_by_id[old["shelf_id"]]).encode()))
    assert set(proposal["diff"]["preserved"]) == {n["shelf_id"] for n in taxonomy["nodes"]}
    assert new_ids == set(projected_by_id) - set(proposal["diff"]["preserved"])
    assert all(not proposal["diff"][key] for key in ("renamed", "merged", "split", "retired"))
    rejected_by_path = {r["proposal"]: r["reason"] for r in proposal["rejected_proposals"]}
    dispositions = []
    for batch, out in zip(receipts["batches"], outputs, strict=True):
        for candidate in out["candidates"]:
            path = " / ".join(candidate["path"])
            vids = {s["video_id"] for s in candidate["supporting_evidence"]}
            card_keys = sorted(key for key, value in keys["cards"].items() if value["video_id"] in vids)
            if path in rejected_by_path:
                status, destination = "explicitly_rejected", None
            elif candidate["path"] == ["News and Current Events"]:
                status, destination = "adopted_or_equivalent", "news-and-current-events"
            elif candidate["path"][-1] == "AI Agents and Automation":
                status, destination = "adopted_or_equivalent", "ai-agents-and-automation"
            elif re.search(r"Business|Industry|Economics", candidate["path"][-1]):
                status, destination = "adopted_or_equivalent", "ai-industry-and-business"
            elif "Media" in candidate["path"][-1]:
                status, destination = "adopted_or_equivalent", "generative-media"
            else:
                raise AssertionError("Unaccounted candidate: " + path)
            dispositions.append(dict(batch=batch["call_id"], path=path, card_keys=card_keys,
                                     disposition=status, destination=destination, reason=rejected_by_path.get(path)))
    assert Counter(r["disposition"] for r in dispositions) == dict(adopted_or_equivalent=15, explicitly_rejected=6)
    launch = next(r for r in dispositions if r["path"] == "AI and ML / Product Launches")
    assert launch["card_keys"] == ["c056", "c058", "c060", "c064", "c069", "c070"]
    assert set(re.findall(r"c\d{3}", launch["reason"])) == set(launch["card_keys"])
    state = dict(pins=len(archive["before"]["pins"]), memberships=len(archive["before"]["memberships"]),
                 item_policies=len(archive["before"]["item_policies"]), active_version_id=archive["before"]["active_version_id"])
    assert all(receipts["induction_state"][key] == value for key, value in state.items())
    assert all(proposal["pin_impact_report"]["measured_" + key] == state[key] == 0 for key in ("pins", "memberships"))
    assert state["item_policies"] == 0 and state["active_version_id"] == taxonomy["version_id"]
    assert proposal["pin_impact_report"]["silent_redirects"] is False and proposal["pin_impact_report"]["items"] == []
    agents = projected_by_id["ai-agents-and-automation"]
    exact = a.decode(old_measurements)["B6"]["boundary_failure"]["exact_repair"]
    assert agents["include"][4] == exact["replace_agents_include_4"] and agents["exclude"][-1] == exact["append_agents_exclude"]
    boundary = copy.deepcopy(previous["B6"]["boundary_repair"])
    boundary["review_method"] = "Both synthetic cases reread against decision 4's projected fields; auditor judgments, no classifier predictions."
    # Reread all previous pairwise judgments against the identical nodes, then
    # expand News' aggregated AI-family entry into explicit pairs for coverage.
    boundaries = copy.deepcopy(previous["B6"]["manual_v1_boundary_review"] + previous["B6"]["remaining_v1_boundary_review"])
    explicit = []
    for row in boundaries:
        if row["v1"] == "AI and ML and its children":
            for name in ("AI and ML", "Developer Tools", "Frontier Models", "Security"):
                explicit.append(dict(row, v1=name))
        else:
            explicit.append(row)
    assert len(explicit) == 28
    assert len({(r["new"], r["v1"]) for r in explicit}) == 28
    new_boundaries = [
        dict(pair=["Agents", "Industry"], verdict="PASS", reason="Performed non-engineering tasks versus company/market economics; Agents exclude[3] and Industry exclude[1] state the distinction."),
        dict(pair=["Agents", "Media"], verdict="PASS", reason="Finished creative artifact goes to Media under Agents exclude[2]; non-creative real-world task execution goes to Agents under Media exclude[1]."),
        dict(pair=["Agents", "News"], verdict="PASS", reason="Specific incident reporting takes News priority; product task demonstration returns to AI shelves under News exclude[1]."),
        dict(pair=["Industry", "Media"], verdict="PASS", reason="Finished creative output versus company/market commentary is stated in Industry exclude[2] and Media exclude[2]."),
        dict(pair=["Industry", "News"], verdict="PASS", reason="AI-company dynamics return to Industry under News exclude[2]; a specific crime/riot/conflict incident as subject takes News priority."),
        dict(pair=["Media", "News"], verdict="PASS", reason="A generated fictional film is an AI creative artifact; News requires real-world incident/debate reporting. News excludes AI product/capability coverage."),
    ]
    b6 = dict(mechanical_verdict="PASS", operative_precedence_verdict="PASS", node_count=11,
        depth_counts=dict(Counter(len(n["path"]) for n in projected)), frozen_v1_checks=frozen_checks,
        decision3_nodes_literal_utf8_bytes_equal=True, node_fragment_sha256=a.sha(nodes_fragment(raw)),
        include_sibling_identity=True, definition_include_scope_agreement="PASS", diff=proposal["diff"],
        candidate_dispositions=dispositions, candidate_counts=dict(Counter(r["disposition"] for r in dispositions)),
        product_launches_redistribution={k: rows[k]["shelf_ids"] or [rows[k]["disposition"]] for k in launch["card_keys"]},
        pin_state=state, pin_impact_report=proposal["pin_impact_report"], boundary_repair=boundary,
        all_28_new_v1_boundaries=explicit, all_six_new_new_boundaries=new_boundaries,
        review_method="All node definitions, include/exclude fields and sibling cues reread; boundary judgments concern subject-centered cases, not classifier measurements or every possible mixed-topic card.")

    projection = module("projection_ae", ROOT / "scripts/librarian/taxonomy_from_proposal.py")
    revision = a.sha(a.canonical(projected).encode())
    service_doc = dict(schema_version=1, version_id=proposal["version_id"], parent_version_id=proposal["parent_version_id"], nodes=projected, revision_hash=revision)
    assert validator.normalized_taxonomy(service_doc) == service_doc
    export = projection.build(DECISION, approved_by="Codex / GPT-6 Astra (INDUCTION-AUDIT-13)",
        approval_record="docs/library/INDUCTION-AUDIT-13-2026-09-06.md", parent_doc=ROOT / "docs/library/taxonomy-v1-2026-09-04.json")
    assert export["nodes"] == projected and export["revision_hash"] == revision
    assert export["approval"]["proposal_sha256"] == EXPECTED_SHA
    projection_result = dict(status="Diagnostic only: decision 4 rejected; no projection written, approved or installed",
        expected_service_revision_hash=revision, service_returned_revision_hash=None,
        canonical_service_file_bytes=len((a.canonical(service_doc) + "\n").encode()),
        canonical_service_file_sha256=a.sha((a.canonical(service_doc) + "\n").encode()),
        metadata_export_bytes=len(pretty(export)), metadata_export_sha256=a.sha(pretty(export)),
        metadata_parameters=export["approval"], parent_revision_hash=export["parent_revision_hash"],
        independent_nodes_equal=True, validator_normalization_equal=True)

    packets = []
    for number, expected in ((12, "e571d4d82a5e80b67adef14d4fa336693bce41d2da724a92d0ac4ddfead926e0"),
                             (13, "5610d5a663550e04735e1ed47dd5ec791f9c585b7296fd7b92eb19341d8b137c")):
        packet_raw = a.read(PROOF / f"holdout-v2-labelling-packet-{number}-2026-09-06.json")
        assert a.sha(packet_raw) == expected
        packets.append(a.decode(packet_raw))
    p12, p13 = packets
    assert {k: v for k, v in p12.items() if k != "taxonomy_candidate"} == {k: v for k, v in p13.items() if k != "taxonomy_candidate"}
    assert p12["taxonomy_candidate"]["proposal_sha256"] == BASE_SHA
    assert p13["taxonomy_candidate"]["proposal_sha256"] == EXPECTED_SHA
    candidate_nodes = [{key: n[key] for key in (*FIELDS, "sibling_cues")} for n in proposal["nodes"]]
    assert p12["taxonomy_candidate"]["nodes"] == p13["taxonomy_candidate"]["nodes"] == candidate_nodes
    assert {k: v for k, v in p12["taxonomy_candidate"].items() if k not in {"status", "proposal_path", "proposal_sha256"}} == {
        k: v for k, v in p13["taxonomy_candidate"].items() if k not in {"status", "proposal_path", "proposal_sha256"}}
    packet_binding = dict(packet12_sha256="e571d4d82a5e80b67adef14d4fa336693bce41d2da724a92d0ac4ddfead926e0",
        packet13_sha256="5610d5a663550e04735e1ed47dd5ec791f9c585b7296fd7b92eb19341d8b137c",
        cards_and_all_non_candidate_fields_equal=True, nodes_and_rules_equal=True,
        candidate_differences=["status", "proposal_path", "proposal_sha256"], labels_opened=False,
        holdout_content_used_for_repairs=False, carry_forward_permitted=True,
        conditions="Preserve original packet-12 label files and provenance; bind their hashes and node/card identity equivalence to the approved successor in adjudication. Seal final labels and mapping before execution. No label-quality or blind-process certification is implied.")

    tests = []
    for label, mutate in (
        ("unrecorded node edit", lambda d: d["proposal"]["nodes"][0].update(definition="tampered")),
        ("wrong before value", lambda d: d["edits"][0].update(before={})),
        ("missing recorded edit", lambda d: d["edits"].pop()),
        ("wrong finding", lambda d: d["edits"][0].update(finding="wrong")),
        ("coordinated non-audit after-value", lambda d: (d["edits"][0]["after"].update(reason="tampered"),
            next(r for r in d["proposal"]["coverage_ledger"] if r["card_key"] == "c078").update(reason="tampered"))),
    ):
        changed = copy.deepcopy(decision)
        mutate(changed)
        try:
            replay(before, changed, previous)
        except AssertionError:
            tests.append(label)
        else:
            raise AssertionError("Mutation accepted: " + label)
    valid = node_evidence[0]["support"]
    for label, changes, error in (
        ("25-word quote", dict(quote=" ".join(["x"] * 25)), "quote_length"),
        ("invented quote", dict(quote="fabricated_evidence_ae_918"), "quote_occurrence"),
        ("foreign revision", dict(source_revision="0" * 64), "source_revision"),
    ):
        assert error in a.check_support(dict(valid, **changes), cards, frozen)["errors"]
        tests.append(label)
    assert a.normal("cafe\u0301\t\u00a0two\nwords") == "caf\u00e9 two words"
    tests.append("NFC/Unicode whitespace")
    bad = copy.deepcopy(proposal)
    bad["coverage_ledger"][0]["evidence"] = [{"support_key": "c064-2"}]
    try:
        a.expand(bad, keys)
    except ValueError:
        tests.append("foreign-card ledger support")
    else:
        raise AssertionError("Foreign-card ledger support accepted")

    for path in (__file__, PROOF / "audit-decision-3-2026-09-06.py", PROOF / "audit-induction-2026-09-05.py",
        ROOT / "scripts/librarian/compose_revision_decision_2.py", ROOT / commands[0][0], ROOT / commands[1][0],
        ROOT / "scripts/librarian/taxonomy_from_proposal.py", ROOT / "tests/validate_proof_receipts.py", ROOT / ".gitattributes",
        ROOT / "docs/library/INDUCTION-REVISION-4-BRIEF-2026-09-06.md", ROOT / decision["repair_specification"]["audit"],
        ROOT / "docs/library/ORCHESTRATION-V1-2026-09-04.md", ROOT / "docs/library/STAGE2-AUDIT-PLAN-2026-09-05.md",
        ROOT / "docs/library/INDUCTION-AUDIT-2026-09-05.md", ROOT / "docs/library/INDUCTION-AUDIT-10-2026-09-05.md"):
        a.read(path)
    assert not any("/labels/" in path for path in a.FILES)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    result = dict(schema_version=1, audit="induction-run-AE-decision4", completed=True, approval=False,
        verdict="REJECT taxonomy-v2-2026-09-05 (revision decision 4)", audited_checkout_sha=head,
        blocking_findings=["B5-R4"], resolved_findings=["B5-R3", "C3-EOL"],
        model_calls_executed_by_audit=0, helper_calls_executed_by_audit=0, databases_opened_by_audit=0,
        unchanged_gates="B1-B3 and B7-B9 retain audit 10's findings; archive process history is not rerun here.",
        decision_sha256=EXPECTED_SHA, predecessor_sha256=BASE_SHA,
        composition=dict(recorded_edit_count=3, per_edit=edit_checks, unchanged_outside_edits=True,
            independent_replay_equal=True, composer_exact_bytes_equal=True, commands=command_results,
            composer_verification=composer_result, source_hashes_verified=True,
            decision2_measurements_eol=a.eol_identity(old_measurements),
            decision3_measurements_eol=a.eol_identity(measurements_raw), measurements_attribute=attributes,
            semantic_review="All three prior exact replacements pass; no node changed."),
        B4=b4, B5=b5, B6=b6, full_proposal_validator_passed=True,
        proposed_repair_preflight=dict(status="Full proposal validator passes all 20 replacements together in memory; no successor written or approved",
            ledger_replacement_rows=len(FAILURES), destination_replacements=17, reason_only_replacements=3, node_field_edits=0,
            expected_ledger_counts=repair_counts, canonical_proposal_sha256=a.sha(a.canonical(repair).encode()),
            canonical_ledger_sha256=a.sha(a.canonical(repair["coverage_ledger"]).encode()),
            successor_acceptance="Verify exact composer replay, all 225 rows against this reviewed replacement proposal, unchanged nodes/evidence and full validation. No rotating sample or further semantic re-review is required for byte-identical reviewed content. Approval still binds the actual successor document and integration SHA."),
        independent_keys_and_expansion_equal=True, projection=projection_result, packet_binding=packet_binding,
        self_test_passed=tests, input_files=a.FILES)
    a.contained(OUT).write_bytes(pretty(result))
    # Exercise the real generic composer against the emitted measurement format.
    # This creates only an in-memory object, never a decision file.
    successor = composer.compose(DECISION, OUT, "docs/library/INDUCTION-AUDIT-13-2026-09-06.md", [])
    assert successor["proposal"] == repair and len(successor["edits"]) == len(FAILURES)
    assert successor["repair_specification"]["measurements_sha256"] == a.sha(pretty(result))
    successor_verification = composer.verify(successor, repair_counts)
    print(json.dumps(dict(completed=True, approval=False, edits=3, node_supports=len(node_evidence),
        mapped_rows_reviewed=len(records), empty_rows_checked=len(unmapped_checks),
        destination_failures=b5["destination_failure_keys"], reason_only_failures=b5["reason_only_failure_keys"],
        expected_successor_counts=repair_counts, boundary_pairs=len(explicit) + len(new_boundaries),
        composer_exit_codes=[r["exit_code"] for r in command_results], self_tests=len(tests),
        generic_successor_in_memory=successor_verification,
        labels_carry_forward=True, measurements_sha256=a.sha(pretty(result)), projection=projection_result), indent=2))


if __name__ == "__main__":
    main()

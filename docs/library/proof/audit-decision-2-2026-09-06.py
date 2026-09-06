"""Run AB: archive-only B4/B5/B6 replay for revision decision 2.

No model, helper, database or network access. Exit 0 means replay completed,
not approval. Human judgments below are bound to the exact reviewed decision.
Reuse the independent audit's identity/quote checks; compare separately with
the public validator and composer. Never overwrite earlier measurements.
"""
from __future__ import annotations

import argparse
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


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


a = module("independent_induction_audit", PROOF / "audit-induction-2026-09-05.py")
DECISION = PROOF / "taxonomy-v2-revision-decision-2-2026-09-05.json"
EXPECTED_SHA = "27e010cea18a4a4b6c9ac20b0061dd264754fea94e088e1e8fdc8e71452b19bd"
PACKET_SHA = "35af2d0f7e5d4bffccb1f6146759d08c92aef5d20270a204c8419e66b613f464"
OUT = PROOF / "audit-decision-2-measurements-2026-09-06.json"
FIELDS = ("shelf_id", "path", "definition", "include", "exclude")
EXPECTED_EDITS = [
    (1, "node ai-agents-and-automation", field)
    for field in ("definition", "include", "sibling_cues", "exclude")
] + [(1, f"ledger {key}", "reason") for key in ("c058", "c124")] + [
    (2, f"node {sid}", field)
    for sid, fields in (("generative-media", ("include", "sibling_cues", "exclude")),
                        ("ai-industry-and-business", ("include", "sibling_cues", "exclude")),
                        ("news-and-current-events", ("include", "sibling_cues")))
    for field in fields
] + [(3, f"ledger {key}", "row") for key in ("c007", "c064", "c069")] + [
    (3, "rejected_proposals AI and ML / Product Launches", "reason")]

# Written after reading each complete cited excerpt. Not inferred by a test.
SUPPORT_REVIEW = {
    "c058-1": "Sensing/acting/remembering companion explicitly fits the separately admitted companion scope.",
    "c088-1": "Internet-using model orders food, books flights, shops and researches.",
    "c106-1": "Agents sell cars, underwrite loans, coach mechanics and run an operation.",
    "c141-1": "Agents autonomously plan, execute and deliver on a goal; no finished artifact is established.",
    "c124-1": "Proposed ChatGPT descendant watches screens and meetings; the revised scope admits this proposal without inferring execution.",
    "c082-1": "AI-company competitive ranking argued through infrastructure.",
    "c130-1": "Government restrictions on an AI company affect competitive access to its models.",
    "c144-1": "Explicit commentary on competition against OpenAI and Anthropic.",
    "c169-1": "AI token usage contrasted with revenue capture.",
    "c213-1": "AI-company ARR; the excerpt expressly qualifies it as a rough estimate.",
    "c033-1": "Made-with attribution and generation prompt establish an animation.",
    "c038-1": "A created film is described as winning an AI-film award.",
    "c128-1": "AI animated film blending genAI and human art.",
    "c091-1": "Finished visual website described as made with AI image/video models.",
    "c104-1": "Firsthand description of AI cat-vlog video content.",
    "c006-1": "Explicit left/center political debate.",
    "c009-1": "Murder charge and shooting at a named location.",
    "c010-1": "Home intrusion, death, police response and charges.",
    "c011-1": "Radio declares a riot and reports a capitol breach.",
    "c019-1": "Original post reports missiles striking a named air base.",
}
SAMPLE_PASS = {
    "c001": "ChatGPT voice/roleplay request fits the AI parent; scam dialogue is not a technical defense.",
    "c006": "Political debate establishes News.",
    "c007": "Restored attempt-10 unmapped row removes the unsupported News assignment; reason describes rejected-candidate history.",
    "c010": "Crime report establishes News.",
    "c019": "Air-base strike report establishes News.",
    "c033": "Made-with attribution establishes generated animation.",
    "c041": "AI dumping and corporate adoption are industry economics.",
    "c056": "Generic ChatGPT assistance; no autonomous multi-step task or persistent monitoring is established.",
    "c058": "Companion sensing/acting/memory fits the broadened Agents definition.",
    "c060": "Prompt-capture application explicitly used with AI; no coding workflow established.",
    "c062": "Informal named-model capability comparison with a game maker; no source-code workflow or specified Media artifact kind.",
    "c064": "Avatar-generation feature without a particular finished artifact; AI parent justified.",
    "c069": "AI video-model release without architecture, benchmark, multimodal or finished-artifact evidence; AI parent justified.",
    "c070": "Unmapped disposition retains the recorded auditor rejection; not re-admitted by the broader Agents scope.",
    "c104": "AI video content is the subject.",
    "c108": "Announcement of a built foundation model with a quantitative-finance capability claim fits model-release scope.",
    "c124": "Proposed persistent screen/meeting assistant; reason no longer attributes execution.",
    "c141": "Autonomous plan/execute/deliver workflow; no finished artifact established.",
    "c196": "Explicit AI-powered consumer product; no narrower child established.",
    "c208": "Workflow sends source screenshots into Claude Code; coding-tool workflow established.",
    "c223": "ARR comparison between AI labs is the stated subject.",
}
# Each tuple specifies an exact replacement using the existing disposition key
# (or no evidence for still_unmapped). These are proposed edits, never applied.
LEDGER_FAILURES = {
    "c087": ("AI vision application is described, but no SDK, code, IDE or engineering-tool workflow appears; reason invents Ultralytics SDK.",
             "existing_concept", ["ai-and-ml"], "AI vision application counts potatoes; no SDK or software-engineering workflow is established."),
    "c095": ("Generic model capability to do computer work does not establish an agent/assistant product, autonomous multi-step task, companion or persistent monitor.",
             "existing_concept", ["ai-and-ml"], "General AI computer-work capability claim; no agent product or qualifying assistant behavior is established."),
    "c123": ("Model download count is adoption/usage evidence; no open-weight availability, architecture, benchmark or release is stated.",
             "proposed_concept", ["ai-industry-and-business"], "Model download/adoption count is industry usage evidence; not a support: five-card cap"),
    "c143": ("LLMs called a critical resource in enterprise contexts; no competition, financial/policy dynamic or control dispute is established.",
             "existing_concept", ["ai-and-ml"], "LLMs described as useful in enterprise contexts; no competitive, financial or policy dynamic is established."),
    "c158": ("Model-generated robot design is described in prose; no finished visual artifact or its medium is established.",
             "existing_concept", ["ai-and-ml"], "AI model produces a robot-design concept; the cited excerpt does not establish a finished visual artifact."),
    "c177": ("NVIDIA hypervisor certification and vertical integration establish a technology/business announcement, but no AI subject; company identity cannot supply it.",
             "still_unmapped", [], "Hypervisor certification/vertical integration is described; the cited excerpt does not establish an AI subject."),
    "c182": ("Database-load simulation is software tooling, but no AI component; the AI parent's non-AI software exclusion applies.",
             "still_unmapped", [], "Database-load simulation tool; the cited excerpt establishes no AI component required by the parent shelf."),
    "c215": ("Metaphorical bumpers/guardrails around an unnamed experiment do not establish technical AI safety; Anthropic's name alone is insufficient.",
             "still_unmapped", [], "Guardrails around an unspecified experiment; the cited excerpt establishes no technical AI safety mechanism."),
}


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def replay_edits(before, decision):
    edits = decision["edits"]
    if [(e["repair_item"], e["target"], e["field"]) for e in edits] != EXPECTED_EDITS:
        raise ValueError("Unexpected edit inventory")
    proposal = copy.deepcopy(before["proposal"])
    records = []
    for number, edit in enumerate(edits, 1):
        category, identity = edit["target"].split(" ", 1)
        collection, key = {"node": ("nodes", "shelf_id"), "ledger": ("coverage_ledger", "card_key"),
                           "rejected_proposals": ("rejected_proposals", "proposal")}[category]
        matches = [x for x in proposal[collection] if x[key] == identity]
        if len(matches) != 1:
            raise ValueError("Non-unique edit target")
        target = matches[0]
        current = target if edit["field"] == "row" else target[edit["field"]]
        if current != edit["before"] or current == edit["after"]:
            raise ValueError("Edit before-value mismatch or no-op")
        records.append(dict(number=number, repair_item=edit["repair_item"], target=edit["target"],
            field=edit["field"], before_matches=True, before_sha256=a.sha(a.canonical(current).encode()),
            after_sha256=a.sha(a.canonical(edit["after"]).encode())))
        if edit["field"] == "row":
            target.clear()
            target.update(copy.deepcopy(edit["after"]))
        else:
            target[edit["field"]] = copy.deepcopy(edit["after"])
    if proposal != decision["proposal"]:
        raise ValueError("Proposal changed outside recorded edits")
    return records


def main(decision_path, output, self_test):
    raw = a.read(decision_path)
    assert a.sha(raw) == EXPECTED_SHA, "Human judgments require a fresh review of changed decision bytes"
    decision = a.decode(raw)
    before_raw = a.read(ROOT / decision["successor_of"]["path"])
    assert a.sha(before_raw) == decision["successor_of"]["sha256"]
    before = a.decode(before_raw)
    edit_records = replay_edits(before, decision)
    assert raw == pretty(decision), "Decision must retain exact UTF-8/LF serialization"
    assert decision["sources"] == before["sources"]
    for source in decision["sources"].values():
        path = ROOT / source["path"]
        assert a.sha(a.read(path)) == source["sha256"]
        assert a.sha(a.read(path.parent / "receipts.json")) == source["receipts_sha256"]
    composer = module("decision2_composer_comparison", ROOT / "scripts/librarian/compose_revision_decision_2.py")
    assert pretty(composer.compose()) == raw
    composer_result = composer.verify(decision)
    run = PROOF / "induction-run-10-2026-09-05"
    receipts = a.document(run / "receipts.json")
    induction = a.document(PROOF / "induction-manifest-2026-09-05.json")
    archive_raw = a.read(PROOF / "run-2026-09-05/receipts.json")
    assert a.sha(archive_raw) == a.ARCHIVE_HASH
    archive = a.decode(archive_raw)
    frozen = {r["video_id"]: r for r in induction["items"]}
    cards = {}
    for attempt in archive["attempts"]:
        if attempt["video_id"] in frozen:
            cards[attempt["video_id"]] = attempt["packet"]["card"]
    outputs = [a.document(run / "calls" / f"{b['call_id']}.stdout")["structured_output"] for b in receipts["batches"]]
    keys = a.derive_keys(induction, receipts["batches"], outputs)
    proposal = decision["proposal"]
    expanded = a.expand(proposal, keys)
    validator = composer.v
    assert keys == validator.derive_induction_keys(induction, receipts["batches"], outputs)
    assert expanded == validator.expand_induction_proposal(proposal, keys)
    taxonomy = a.document(ROOT / "docs/library/taxonomy-v1-2026-09-04.json")
    validator.Draft202012Validator(validator.PROPOSAL_SCHEMA).validate(proposal)
    validator.validate_induction_proposal(expanded, induction, cards, taxonomy,
        batch_outputs={vid: out for b, out in zip(receipts["batches"], outputs, strict=True) for vid in b["video_ids"]})

    def evidence(ref):
        key = ref["support_key"]
        origin = keys["supports"][key]
        support = origin["support"]
        check = a.check_support(support, cards, frozen)
        return dict(support_key=key, kind=origin["kind"], card_key=origin["card_key"], support=support,
            excerpt=next(e for e in cards[support["video_id"]]["excerpts"] if e["excerpt_id"] == support["excerpt_id"]), **check)

    node_evidence, by_node = [], {}
    for node in proposal["nodes"]:
        by_node[node["shelf_id"]] = set()
        for ref in node["supporting_evidence"]:
            row = evidence(ref)
            assert row["kind"] == "candidate"
            row.update(shelf_id=node["shelf_id"], subject_relevant=True, human_reason=SUPPORT_REVIEW[row["support_key"]])
            node_evidence.append(row)
            by_node[node["shelf_id"]].add(row["card_key"])
    assert {r["support_key"] for r in node_evidence} == set(SUPPORT_REVIEW)
    new_ids = set(proposal["diff"]["added"])
    assert all(len(by_node[sid]) == 5 for sid in new_ids)
    ledger_evidence = [evidence(ref) for row in proposal["coverage_ledger"] for ref in row["evidence"]]
    all_evidence = node_evidence + ledger_evidence
    assert not any(r["errors"] for r in all_evidence)
    rejected = set(receipts["execution"]["auditor_rejected_keys"]) | {"c061-1"}
    assert not ({r["support_key"] for r in all_evidence} & rejected)
    b4 = dict(node_references=len(node_evidence), ledger_references=len(ledger_evidence),
        evidence_errors=[], candidate_kind_verified=True, rejected_keys_selected=[],
        node_quote_word_counts=dict(sorted(Counter(r["words"] for r in node_evidence).items())),
        subject_relevant_distinct_cards={sid: len(by_node[sid]) for sid in sorted(new_ids)},
        review_method="Human reading of every complete frozen cited excerpt; no outside facts, title or channel used.",
        manual_relevance_review=node_evidence, verdict="PASS")

    rows = {r["card_key"]: r for r in proposal["coverage_ledger"]}
    assert len(rows) == len(proposal["coverage_ledger"]) == 225 and set(rows) == set(keys["cards"])
    omissions = [r for r in rows.values() if r["disposition"] == "proposed_concept" and
        not any(r["card_key"] in by_node[sid] for sid in r["shelf_ids"])]
    assert all(re.search(r"; not a support: .+$", r["reason"]) for r in omissions)
    sample = {"c007", "c058", "c124", "c064", "c069", "c056", "c060", "c070", "c177"}
    for sid in sorted({sid for r in rows.values() for sid in r["shelf_ids"]}):
        candidates = [r for r in rows.values() if sid in r["shelf_ids"]]
        sample.update(r["card_key"] for r in (candidates[0], candidates[len(candidates)//2], candidates[-1]))
    assert sample == set(SAMPLE_PASS) | set(LEDGER_FAILURES)
    sample_records = []
    for key in sorted(sample):
        row = rows[key]
        record = dict(row=row, evidence=[evidence(ref) for ref in row["evidence"]],
                      subject_destination_pass=key not in LEDGER_FAILURES)
        if key in LEDGER_FAILURES:
            reason, disposition, shelves, replacement_reason = LEDGER_FAILURES[key]
            replacement = dict(row, disposition=disposition, shelf_ids=shelves,
                evidence=row["evidence"] if shelves else [], reason=replacement_reason)
            assert len(replacement_reason) <= 160
            record.update(human_reason=reason, exact_proposed_replacement=replacement)
        else:
            record["human_reason"] = SAMPLE_PASS[key]
        if key in {"c007", "c070"}:
            record["historical_evidence_not_accepted"] = evidence({"support_key": "c007-3" if key == "c007" else "c070-1"})
        sample_records.append(record)
    run10_rows = {r["card_key"]: r for r in a.document(run / "proposal.json")["coverage_ledger"]}
    assert rows["c007"] == run10_rows["c007"]
    b5 = dict(entry_count=len(rows), unique_cards=len(rows), manifest_identities_equal=True,
        disposition_counts=dict(Counter(r["disposition"] for r in rows.values())),
        shelf_counts=dict(Counter(sid for r in rows.values() for sid in r["shelf_ids"])),
        omission_explanation_count=len(omissions), omission_explanation_failures=[], omissions=omissions,
        mechanical_verdict="PASS", semantic_verdict="FAIL", repaired_destinations_pass=["c007", "c064", "c069", "c058", "c124"],
        sample_method="Nine repair/redistribution/control rows plus first, middle and last ledger row for every populated shelf, deduplicated.",
        sample_count=len(sample), mapped_sample_count=sum(bool(rows[k]["shelf_ids"]) for k in sample),
        semantic_failure_keys=sorted(LEDGER_FAILURES), sample_records=sample_records,
        limitation="This is a 29-row destination sample, not semantic certification of all 225 rows.")

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
        new = projected_by_id[old["shelf_id"]]
        assert new == old
        frozen_checks.append(dict(shelf_id=old["shelf_id"], service_fields_equal=True,
            canonical_utf8_bytes_equal=a.canonical(new).encode() == a.canonical(old).encode()))
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
                disposition, destination = "explicitly_rejected", None
            elif candidate["path"] == ["News and Current Events"]:
                disposition, destination = "adopted_or_equivalent", "news-and-current-events"
            elif candidate["path"][-1] == "AI Agents and Automation":
                disposition, destination = "adopted_or_equivalent", "ai-agents-and-automation"
            elif re.search(r"Business|Industry|Economics", candidate["path"][-1]):
                disposition, destination = "adopted_or_equivalent", "ai-industry-and-business"
            elif "Media" in candidate["path"][-1]:
                disposition, destination = "adopted_or_equivalent", "generative-media"
            else:
                raise AssertionError("Unaccounted candidate: " + path)
            dispositions.append(dict(batch=batch["call_id"], path=path, card_keys=card_keys,
                disposition=disposition, destination=destination, reason=rejected_by_path.get(path)))
    launch = next(r for r in dispositions if r["path"] == "AI and ML / Product Launches")
    assert launch["card_keys"] == ["c056", "c058", "c060", "c064", "c069", "c070"]
    redistribution = {key: rows[key]["shelf_ids"] or [rows[key]["disposition"]] for key in launch["card_keys"]}
    assert set(re.findall(r"c\d{3}", launch["reason"])) == set(launch["card_keys"])
    state = dict(pins=len(archive["before"]["pins"]), memberships=len(archive["before"]["memberships"]),
                 item_policies=len(archive["before"]["item_policies"]), active_version_id=archive["before"]["active_version_id"])
    assert all(receipts["induction_state"][key] == value for key, value in state.items())
    assert all(proposal["pin_impact_report"]["measured_" + key] == state[key] == 0 for key in ("pins", "memberships"))
    assert proposal["pin_impact_report"]["silent_redirects"] is False and proposal["pin_impact_report"]["items"] == []
    agents = next(n for n in proposal["nodes"] if n["shelf_id"] == "ai-agents-and-automation")
    security_cue = agents["sibling_cues"][4]
    assert "Security" in security_cue["confusing_alternative"]
    assert not any("security" in s.lower() for s in [agents["definition"], *agents["include"], *agents["exclude"]])
    boundary_failure = dict(id="B6-S-Agents-Security", edit_number=3,
        archived_distinction=security_cue, operative_security_rule_absent=True,
        synthetic_case="A proposed AI security assistant continuously watches the user's screen to detect prompt injection and enforce runtime guardrails.",
        conflict="Agents include[4] admits persistent screen assistants; Security admits prompt-injection defenses/runtime governance. Only discarded sibling_cues say 'not a security control'.",
        exact_repair=dict(
            replace_agents_include_4="proposed persistent assistant that continuously watches the user's screen or meetings for personal assistance, rather than technical safety or security control (takes precedence over AI and ML / Security for this personal-assistance case)",
            append_agents_exclude="technical AI safety or security controls, including monitoring to detect prompt injection or enforce runtime guardrails -> AI and ML / Security",
            mirror_include_cue="Copy the replacement include[4] character-for-character into sibling_cues[4].include_cue."))
    b6 = dict(node_count=11, depth_counts=dict(Counter(len(n["path"]) for n in projected)),
        frozen_v1_checks=frozen_checks, include_sibling_identity=True, definition_include_scope_agreement="PASS",
        diff=proposal["diff"], candidate_dispositions=dispositions,
        candidate_counts=dict(Counter(r["disposition"] for r in dispositions)), product_launches_redistribution=redistribution,
        pin_state=state, pin_impact_report=proposal["pin_impact_report"], mechanical_verdict="PASS",
        operative_precedence_verdict="FAIL", boundary_failure=boundary_failure)
    b6["manual_v1_boundary_review"] = [
        dict(new="Agents", v1="Developer Tools", verdict="PASS", fields="Agents include[1], exclude[0]",
             reason="Non-engineering task completion takes Agents; coding harness/IDE/SDK workflows take Developer Tools."),
        dict(new="Agents", v1="Frontier Models", verdict="PASS", fields="Agents definition, exclude[1]",
             reason="Acting agent/assistant product versus architecture/benchmark evaluation without that product behavior."),
        dict(new="Agents", v1="Security", verdict="FAIL", fields="Agents sibling_cues[4] only",
             reason="Personal monitoring versus security control is lost during projection; see synthetic failing case."),
        dict(new="Industry", v1="Frontier Models", verdict="PASS", fields="Industry definition/include, exclude[0]; Frontier exclude[2]",
             reason="Business ranking/revenue/usage economics versus technical model evaluation; Frontier already excludes general AI business news."),
        dict(new="Industry", v1="Developer Tools", verdict="PASS", fields="Industry definition/include, exclude[3]; Developer Tools exclude[2]",
             reason="Business dynamics versus coding-tool usage and IDE/SDK workflow steps."),
        dict(new="Industry", v1="Security", verdict="PASS", fields="Industry include[1], exclude[4]",
             reason="External government policy takes Industry priority; technical safety/guardrails take Security."),
        dict(new="Media", v1="Frontier Models", verdict="PASS", fields="Media include[5], exclude[0]",
             reason="Artifact-centered model release takes Media priority; architecture/scaling/benchmark release without a finished artifact takes Frontier."),
        dict(new="Media", v1="Developer Tools", verdict="PASS", fields="Media definition/include[3], exclude[3]",
             reason="Generated visual website as output versus the coding/SDK workflow used to build it."),
        dict(new="News", v1="AI and ML and its children", verdict="PASS", fields="News include[0], exclude[0:3]",
             reason="Incident as subject takes News priority over every AI shelf; product/model/business subjects return to AI shelves."),
    ]
    # Preflight the proposed repair in memory. This checks mechanical feasibility;
    # it does not approve an unwritten successor or change the audited document.
    repair = copy.deepcopy(proposal)
    repair_rows = {r["card_key"]: r for r in repair["coverage_ledger"]}
    for record in sample_records:
        if "exact_proposed_replacement" in record:
            row = repair_rows[record["row"]["card_key"]]
            row.clear()
            row.update(copy.deepcopy(record["exact_proposed_replacement"]))
    repair_agents = next(n for n in repair["nodes"] if n["shelf_id"] == "ai-agents-and-automation")
    repair_agents["include"][4] = boundary_failure["exact_repair"]["replace_agents_include_4"]
    repair_agents["sibling_cues"][4]["include_cue"] = repair_agents["include"][4]
    repair_agents["exclude"].append(boundary_failure["exact_repair"]["append_agents_exclude"])
    validator.Draft202012Validator(validator.PROPOSAL_SCHEMA).validate(repair)
    validator.validate_induction_proposal(a.expand(repair, keys), induction, cards, taxonomy,
        batch_outputs={vid: out for b, out in zip(receipts["batches"], outputs, strict=True) for vid in b["video_ids"]})
    repair_preflight = dict(status="In-memory mechanical validation passed; no successor written or approved",
        ledger_replacement_rows=8, node_field_edits=3,
        expected_ledger_counts=dict(Counter(r["disposition"] for r in repair["coverage_ledger"])))

    projection = module("projection_ab_comparison", ROOT / "scripts/librarian/taxonomy_from_proposal.py")
    revision = a.sha(a.canonical(projected).encode())
    service_doc = dict(schema_version=1, version_id=proposal["version_id"], parent_version_id=proposal["parent_version_id"], nodes=projected, revision_hash=revision)
    assert validator.normalized_taxonomy(service_doc) == service_doc
    export = projection.build(decision_path, approved_by="Codex / GPT-6 Astra",
        approval_record="docs/library/INDUCTION-AUDIT-11-2026-09-06.md",
        parent_doc=ROOT / "docs/library/taxonomy-v1-2026-09-04.json")
    assert export["nodes"] == projected and export["revision_hash"] == revision
    assert export["approval"]["proposal_sha256"] == EXPECTED_SHA
    projection_result = dict(status="Diagnostic only: rejected candidate; no projected file written, approved or installed",
        expected_service_revision_hash=revision, service_returned_revision_hash=None,
        canonical_service_file_bytes=len((a.canonical(service_doc) + "\n").encode()),
        canonical_service_file_sha256=a.sha((a.canonical(service_doc) + "\n").encode()),
        metadata_export_bytes=len(pretty(export)), metadata_export_sha256=a.sha(pretty(export)),
        metadata_parameters=export["approval"], parent_revision_hash=export["parent_revision_hash"],
        independent_nodes_equal=True, validator_normalization_equal=True, wrapper_unwrapped=True)
    packet_path = PROOF / "holdout-v2-labelling-packet-11-2026-09-05.json"
    packet_raw = a.read(packet_path)
    packet = a.decode(packet_raw)
    assert a.sha(packet_raw) == PACKET_SHA
    assert packet["taxonomy_candidate"]["proposal_sha256"] == EXPECTED_SHA
    assert packet["taxonomy_candidate"]["nodes"] == [{key: n[key] for key in (*FIELDS, "sibling_cues")} for n in proposal["nodes"]]

    tests = []
    if self_test:
        for label, mutate in (
            ("unrecorded proposal edit", lambda d: d["proposal"]["nodes"][0].update(definition="tampered")),
            ("wrong before value", lambda d: d["edits"][0].update(before="tampered")),
            ("missing recorded edit", lambda d: d["edits"].pop()),
            ("wrong repair item", lambda d: d["edits"][0].update(repair_item=3)),
        ):
            changed = copy.deepcopy(decision)
            mutate(changed)
            try:
                replay_edits(before, changed)
            except ValueError:
                tests.append(label)
            else:
                raise AssertionError("Mutation accepted: " + label)
        valid = node_evidence[0]["support"]
        for label, changes, error in (
            ("25-word quote", dict(quote=" ".join(["x"] * 25)), "quote_length"),
            ("invented quote", dict(quote="fabricated_evidence_ab_918"), "quote_occurrence"),
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

    for path in (__file__, PROOF / "audit-induction-2026-09-05.py",
                 ROOT / "scripts/librarian/compose_revision_decision_2.py",
                 ROOT / "scripts/librarian/taxonomy_from_proposal.py", ROOT / "tests/validate_proof_receipts.py",
                 ROOT / decision["repair_specification"], ROOT / "docs/library/INDUCTION-REVISION-2-BRIEF-2026-09-06.md",
                 ROOT / "docs/library/ORCHESTRATION-V1-2026-09-04.md", ROOT / "docs/library/STAGE2-AUDIT-PLAN-2026-09-05.md",
                 ROOT / "scripts/librarian/prompts/induce-consolidate.md"):
        a.read(path)
    prior_hashes = {name: a.sha(a.read(PROOF / name)) for name in (
        "audit-induction-measurements-2026-09-05.json", "audit-induction-9-measurements-2026-09-05.json",
        "audit-induction-10-measurements-2026-09-05.json")}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    result = dict(schema_version=1, audit="induction-run-AB-decision2", completed=True, approval=False,
        verdict="REJECT taxonomy-v2-2026-09-05 (revision decision 2)", audited_checkout_sha=head,
        model_calls_executed_by_audit=0, helper_calls_executed_by_audit=0, databases_opened_by_audit=0,
        unchanged_gates="B1-B3 and B7-B9 stand from attempt-10 audit; not rerun by this script.",
        decision_sha256=EXPECTED_SHA, predecessor_sha256=a.sha(before_raw),
        composition=dict(recorded_edit_count=18, per_edit=edit_records, unchanged_outside_edits=True,
            exact_serialization_equal=True, independent_replay_equal=True, composer_exact_bytes_equal=True,
            composer_verification=composer_result, source_hashes_verified=True,
            semantic_review="All recorded changes address their named repair items; edit 3 introduces an unprojected Agents/Security distinction, so the whole repair is incomplete."),
        B4=b4, B5=b5, B6=b6, full_proposal_validator_passed=True,
        proposed_repair_preflight=repair_preflight,
        independent_keys_and_expansion_equal=True, projection=projection_result,
        packet_binding=dict(sha256=PACKET_SHA, proposal_hash_equal=True, all_candidate_fields_equal=True),
        prior_measurement_hashes=prior_hashes, self_test_passed=tests, input_files=a.FILES)
    output = a.contained(output)
    if output.name in prior_hashes:
        raise ValueError("Cannot overwrite prior audit measurements")
    output.write_bytes(pretty(result))
    print(json.dumps(dict(completed=True, approval=False, edits=18, nodes=11,
        node_supports=len(node_evidence), ledger_references=len(ledger_evidence), ledger=b5["disposition_counts"],
        sample_rows=len(sample), destination_failures=sorted(LEDGER_FAILURES),
        boundary_failure=boundary_failure["id"], self_tests=len(tests), projection=projection_result), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", type=Path, default=DECISION)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    main(a.contained(args.decision), a.contained(args.output), args.self_test)

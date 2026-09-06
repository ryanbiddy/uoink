"""Run AD: archive-only B4/B5/B6 replay for revision decision 3.

No model, helper, database or network access. Exit 0 means replay completed,
not approval. Auditor judgments below are bound to the exact reviewed decision.
Adapted from audit-decision-2-2026-09-06.py, preserving earlier audit files.
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
sys.path.insert(0, str(ROOT / "scripts/librarian"))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


a = module("independent_induction_audit", PROOF / "audit-induction-2026-09-05.py")
DECISION = PROOF / "taxonomy-v2-revision-decision-3-2026-09-06.json"
EXPECTED_SHA = "308860a0c1cf42aadf9f309f44c0a44a5358d97defdee95950d2027d0c94a16e"
PACKET_SHA = "e571d4d82a5e80b67adef14d4fa336693bce41d2da724a92d0ac4ddfead926e0"
OUT = PROOF / "audit-decision-3-measurements-2026-09-06.json"
REPAIRED_KEYS = {"c087", "c095", "c123", "c143", "c158", "c177", "c182", "c215"}
EXPECTED_COUNTS = dict(proposed_concept=59, existing_concept=33, still_unmapped=109, unsupported=24)
FIELDS = ("shelf_id", "path", "definition", "include", "exclude")
EXPECTED_EDITS = [
    ("B6-S-Agents-Security", "node ai-agents-and-automation", field)
    for field in ("include", "sibling_cues", "exclude")
] + [("B5-R2", f"ledger {key}", "row") for key in sorted(REPAIRED_KEYS)]

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
    "c087": "AI vision application justifies the AI parent; no SDK workflow is claimed after repair.",
    "c095": "General AI computer-work capability justifies the AI parent without inventing an agent product.",
    "c106": "Agents sell cars, underwrite loans, coach mechanics and run an operation.",
    "c123": "Download/adoption count establishes Industry usage economics; omission suffix is present.",
    "c134": "Named supplier partnership to power an AI browser's search establishes an AI business relationship.",
    "c143": "Explicit LLM enterprise use justifies the AI parent, without inventing competitive or policy dynamics.",
    "c153": "First episode of a fully AI-generated police procedural establishes a finished creative video.",
    "c158": "Model-generated robot concept justifies the AI parent without inventing a visual artifact.",
    "c177": "Unmapped repair correctly removes an AI assignment unsupported by hypervisor certification alone.",
    "c182": "Unmapped repair correctly removes a non-AI database simulation from the AI taxonomy.",
    "c215": "Unmapped repair correctly removes unspecified metaphorical guardrails from technical AI Security.",
}
# Each tuple specifies an exact replacement using the existing disposition key
# (or no evidence for still_unmapped). These are proposed edits, never applied.
LEDGER_FAILURES = {
    "c078": ("Seven-day model-price promotion compares prices on comparable tasks, not capabilities or benchmark results; the excerpt ends at 'while sti'.",
             "proposed_concept", ["ai-industry-and-business"],
             "AI model price promotion and provider price comparison are market economics; not a support: five-card cap"),
    "c150": ("Generic ELI5 slash-command instructions name Anthropic but no AI system, coding task, SDK, IDE or ML lesson; the reason adds Claude and agent workflow.",
             "still_unmapped", [],
             "ELI5 slash-command instructions; the cited excerpt establishes neither an AI system nor a software-engineering workflow."),
    "c186": ("Portable access to Grok bots establishes an AI application, not a coding-specific harness; animation/response tweaks do not supply an engineering workflow.",
             "existing_concept", ["ai-and-ml"],
             "Portable Grok-bot access and switching; no coding-specific harness, IDE, SDK or developer workflow is established."),
}


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def replay_edits(before, decision):
    edits = decision["edits"]
    if [(e["finding"], e["target"], e["field"]) for e in edits] != EXPECTED_EDITS:
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
        records.append(dict(number=number, finding=edit["finding"], target=edit["target"],
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


def verify_exact_repairs(before, decision, previous, audit_text):
    """An independent replay against the auditor's repairs, not composer constants."""
    expected = copy.deepcopy(before["proposal"])
    agents = next(n for n in expected["nodes"] if n["shelf_id"] == "ai-agents-and-automation")
    repair = previous["B6"]["boundary_failure"]["exact_repair"]
    include = repair["replace_agents_include_4"]
    exclude = repair["append_agents_exclude"]
    if f"`{include}`" not in audit_text or f"`{exclude}`" not in audit_text:
        raise ValueError("Prior report does not contain the exact Agents repair strings")
    agents["include"][4] = include
    agents["sibling_cues"][4]["include_cue"] = include
    agents["exclude"].append(exclude)
    replacements = {x["row"]["card_key"]: x["exact_proposed_replacement"]
                    for x in previous["B5"]["sample_records"] if "exact_proposed_replacement" in x}
    if set(replacements) != REPAIRED_KEYS:
        raise ValueError("Prior repair inventory changed")
    for row in expected["coverage_ledger"]:
        if row["card_key"] in replacements:
            replacement = copy.deepcopy(replacements[row["card_key"]])
            row.clear()
            row.update(replacement)
    if expected != decision["proposal"]:
        raise ValueError("Proposal is not exactly the eleven reviewer-authored repairs")
    return dict(verdict="PASS", node_field_edits=3, ledger_replacement_rows=8,
                audit_strings_equal=True, measurement_replacement_objects_equal=True,
                independently_constructed_full_proposal_equal=True)


def main(decision_path, output, self_test):
    raw = a.read(decision_path)
    assert a.sha(raw) == EXPECTED_SHA, "Auditor judgments require a fresh review of changed decision bytes"
    decision = a.decode(raw)
    before_raw = a.read(ROOT / decision["successor_of"]["path"])
    assert a.sha(before_raw) == decision["successor_of"]["sha256"]
    before = a.decode(before_raw)
    assert a.sha(before_raw) == "27e010cea18a4a4b6c9ac20b0061dd264754fea94e088e1e8fdc8e71452b19bd"
    edit_records = replay_edits(before, decision)
    measurement_raw = a.read(ROOT / decision["repair_specification"]["measurements"])
    previous = a.decode(measurement_raw)
    assert previous["decision_sha256"] == a.sha(before_raw)
    audit_raw = a.read(ROOT / decision["repair_specification"]["audit"])
    exact_repairs = verify_exact_repairs(before, decision, previous, audit_raw.decode("utf-8"))
    measurement_eol = a.eol_identity(measurement_raw)
    bound_measurement_sha = decision["repair_specification"]["measurements_sha256"]
    assert measurement_eol["lf_sha256"] == bound_measurement_sha
    measurement_binding = dict(recorded_sha256=bound_measurement_sha, **measurement_eol,
        exact_bytes_match=a.sha(measurement_raw) == bound_measurement_sha,
        lf_reconstruction_matches=True,
        verdict="PASS" if a.sha(measurement_raw) == bound_measurement_sha else "FAIL",
        finding="C3-EOL" if a.sha(measurement_raw) != bound_measurement_sha else None)
    assert raw == pretty(decision), "Decision must retain exact UTF-8/LF serialization"
    assert decision["sources"] == before["sources"]
    for source in decision["sources"].values():
        path = ROOT / source["path"]
        assert a.sha(a.read(path)) == source["sha256"]
        assert a.sha(a.read(path.parent / "receipts.json")) == source["receipts_sha256"]
    composer = module("decision3_composer_comparison", ROOT / "scripts/librarian/compose_revision_decision_3.py")
    composed = composer.compose()
    composer_bytes_equal = pretty(composed) == raw
    # Diagnostic only: the single wrapper difference is the materialized CRLF hash.
    # Do not alter either input file or claim that the real --check passed.
    eol_diagnostic = copy.deepcopy(composed)
    eol_diagnostic["repair_specification"]["measurements_sha256"] = bound_measurement_sha
    assert pretty(eol_diagnostic) == raw
    composer_cli = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/librarian/compose_revision_decision_3.py"),
                                   "--check"], cwd=ROOT, capture_output=True, text=True, check=False)
    assert (composer_cli.returncode == 0) == composer_bytes_equal
    composer_command = dict(command="python -B scripts/librarian/compose_revision_decision_3.py --check",
        exit_code=composer_cli.returncode, stdout=composer_cli.stdout.strip(), stderr=composer_cli.stderr.strip())
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
        review_method="Auditor reading of every complete frozen cited excerpt; no outside facts, title or channel used.",
        manual_relevance_review=node_evidence, verdict="PASS")

    rows = {r["card_key"]: r for r in proposal["coverage_ledger"]}
    assert len(rows) == len(proposal["coverage_ledger"]) == 225 and set(rows) == set(keys["cards"])
    omissions = [r for r in rows.values() if r["disposition"] == "proposed_concept" and
        not any(r["card_key"] in by_node[sid] for sid in r["shelf_ids"])]
    assert all(re.search(r"; not a support: .+$", r["reason"]) for r in omissions)
    sample = {"c007", "c058", "c124", "c064", "c069", "c056", "c060", "c070", "c177"} | REPAIRED_KEYS
    shelf_sample = {}
    for sid in sorted({sid for r in rows.values() for sid in r["shelf_ids"]}):
        candidates = [r for r in rows.values() if sid in r["shelf_ids"]]
        shelf_sample[sid] = [r["card_key"] for r in (candidates[0], candidates[len(candidates)//2], candidates[-1])]
        sample.update(shelf_sample[sid])
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
        if key in REPAIRED_KEYS:
            old = next(x for x in previous["B5"]["sample_records"] if x["row"]["card_key"] == key)
            assert row == old["exact_proposed_replacement"]
            record["prior_repair_exact_match"] = True
            if not row["evidence"]:
                record["historical_evidence_not_accepted"] = [evidence(ref) for ref in old["row"]["evidence"]]
        sample_records.append(record)
    run10_rows = {r["card_key"]: r for r in a.document(run / "proposal.json")["coverage_ledger"]}
    assert rows["c007"] == run10_rows["c007"]
    b5 = dict(entry_count=len(rows), unique_cards=len(rows), manifest_identities_equal=True,
        disposition_counts=dict(Counter(r["disposition"] for r in rows.values())),
        shelf_counts=dict(Counter(sid for r in rows.values() for sid in r["shelf_ids"])),
        omission_explanation_count=len(omissions), omission_explanation_failures=[], omissions=omissions,
        mechanical_verdict="PASS", semantic_verdict="FAIL", repaired_destinations_pass=sorted(REPAIRED_KEYS),
        earlier_repaired_destinations_pass=["c007", "c064", "c069", "c058", "c124"],
        sample_method="Same nine repair/redistribution/control rows and recomputed first/middle/last per populated shelf, plus all eight repaired rows, deduplicated.",
        first_middle_last_by_shelf=shelf_sample,
        fresh_sample_keys=sorted(sample - {x["row"]["card_key"] for x in previous["B5"]["sample_records"]}),
        sample_count=len(sample), mapped_sample_count=sum(bool(rows[k]["shelf_ids"]) for k in sample),
        semantic_failure_keys=sorted(LEDGER_FAILURES), sample_records=sample_records,
        limitation="This is a 35-row destination sample, not semantic certification of all 225 rows.")
    assert b5["disposition_counts"] == EXPECTED_COUNTS

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
    exact_boundary = previous["B6"]["boundary_failure"]["exact_repair"]
    assert agents["include"][4] == exact_boundary["replace_agents_include_4"]
    assert agents["exclude"][-1] == exact_boundary["append_agents_exclude"]
    assert projected_by_id[agents["shelf_id"]]["include"] == agents["include"]
    assert projected_by_id[agents["shelf_id"]]["exclude"] == agents["exclude"]
    boundary_repair = dict(id="B6-S-Agents-Security", verdict="PASS", operative_rule_survives_projection=True,
        synthetic_case=previous["B6"]["boundary_failure"]["synthetic_case"],
        expected_primary="security", auditor_judged_primary="security",
        reason="Agents exclude[4] sends technical safety/security monitoring to Security; include[4] reserves personal assistance.",
        converse_case="A proposed personal assistant watches the user's screen and meetings to help the user, with no technical safety or security control.",
        converse_expected_primary="ai-agents-and-automation", converse_auditor_judged_primary="ai-agents-and-automation",
        review_method="Auditor-created synthetic cases judged from projected fields; no classifier or model call.")
    b6 = dict(node_count=11, depth_counts=dict(Counter(len(n["path"]) for n in projected)),
        frozen_v1_checks=frozen_checks, include_sibling_identity=True, definition_include_scope_agreement="PASS",
        diff=proposal["diff"], candidate_dispositions=dispositions,
        candidate_counts=dict(Counter(r["disposition"] for r in dispositions)), product_launches_redistribution=redistribution,
        pin_state=state, pin_impact_report=proposal["pin_impact_report"], mechanical_verdict="PASS",
        operative_precedence_verdict="PASS", boundary_repair=boundary_repair)
    b6["manual_v1_boundary_review"] = [
        dict(new="Agents", v1="Developer Tools", verdict="PASS", fields="Agents include[1], exclude[0]",
             reason="Non-engineering task completion takes Agents; coding harness/IDE/SDK workflows take Developer Tools."),
        dict(new="Agents", v1="Frontier Models", verdict="PASS", fields="Agents definition, exclude[1]",
             reason="Acting agent/assistant product versus architecture/benchmark evaluation without that product behavior."),
        dict(new="Agents", v1="Security", verdict="PASS", fields="Agents include[4], exclude[4]",
             reason="Personal assistance takes Agents priority; technical safety and security monitoring explicitly go to Security."),
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
    # The other preserved shelves have no new operative precedence conflict.
    # Record each pair, including the unpopulated Education/Space shelves.
    b6["remaining_v1_boundary_review"] = [
        dict(new=new, v1=old, verdict="PASS", reason=reason)
        for new in ("Agents", "Industry", "Media", "News")
        for old, reason in (
            ("Education", "The frozen shelf requires pedagogical ML/technical instruction. The new product, business, artifact and incident subjects do not replace that teaching scope."),
            ("Space and Science", "The frozen shelf requires space/science or empirical inquiry. A product, market claim, fictional artifact or incident does not establish that subject by mention alone."),
            ("Spaceflight", "Actual launch/mission/spacecraft operations belong to Spaceflight; an AI product or fictional generated scene does not establish such operations."),
        )
    ]
    b6["remaining_v1_boundary_review"].append(
        dict(new="Media", v1="Security", verdict="PASS",
             reason="Finished creative visual output is distinct from technical safety/security mechanisms. No Media cue adds a security-control precedence claim."))
    b6["remaining_v1_boundary_review"].extend([
        dict(new=new, v1="AI and ML", verdict="PASS",
             reason="A new AI child requires its defined subject; generic AI capabilities or features may stay at the parent.")
        for new in ("Agents", "Industry", "Media")
    ])
    # Preflight the proposed repair in memory. This checks mechanical feasibility;
    # it does not approve an unwritten successor or change the audited document.
    repair = copy.deepcopy(proposal)
    repair_rows = {r["card_key"]: r for r in repair["coverage_ledger"]}
    for record in sample_records:
        if "exact_proposed_replacement" in record:
            row = repair_rows[record["row"]["card_key"]]
            row.clear()
            row.update(copy.deepcopy(record["exact_proposed_replacement"]))
    validator.Draft202012Validator(validator.PROPOSAL_SCHEMA).validate(repair)
    validator.validate_induction_proposal(a.expand(repair, keys), induction, cards, taxonomy,
        batch_outputs={vid: out for b, out in zip(receipts["batches"], outputs, strict=True) for vid in b["video_ids"]})
    repair_preflight = dict(status="In-memory mechanical validation passed; no successor written or approved",
        ledger_replacement_rows=3, node_field_edits=0,
        expected_ledger_counts=dict(Counter(r["disposition"] for r in repair["coverage_ledger"])))

    projection = module("projection_ad_comparison", ROOT / "scripts/librarian/taxonomy_from_proposal.py")
    revision = a.sha(a.canonical(projected).encode())
    service_doc = dict(schema_version=1, version_id=proposal["version_id"], parent_version_id=proposal["parent_version_id"], nodes=projected, revision_hash=revision)
    assert validator.normalized_taxonomy(service_doc) == service_doc
    export = projection.build(decision_path, approved_by="Codex / GPT-6 Astra (INDUCTION-AUDIT-12)",
        approval_record="docs/library/INDUCTION-AUDIT-12-2026-09-06.md",
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
    packet_path = PROOF / "holdout-v2-labelling-packet-12-2026-09-06.json"
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
            ("wrong finding", lambda d: d["edits"][0].update(finding="B5-R2")),
        ):
            changed = copy.deepcopy(decision)
            mutate(changed)
            try:
                replay_edits(before, changed)
            except ValueError:
                tests.append(label)
            else:
                raise AssertionError("Mutation accepted: " + label)
        for label, mutate in (
            ("Agents repair differs from audit strings", lambda d: next(n for n in d["proposal"]["nodes"]
                if n["shelf_id"] == "ai-agents-and-automation")["include"].__setitem__(4, "changed")),
            ("ledger repair differs from measurement object", lambda d: next(r for r in d["proposal"]["coverage_ledger"]
                if r["card_key"] == "c087").update(reason="changed")),
        ):
            changed = copy.deepcopy(decision)
            mutate(changed)
            try:
                verify_exact_repairs(before, changed, previous, audit_raw.decode("utf-8"))
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
                 PROOF / "audit-decision-2-2026-09-06.py",
                 ROOT / "scripts/librarian/compose_revision_decision_2.py",
                 ROOT / "scripts/librarian/compose_revision_decision_3.py", ROOT / ".gitattributes",
                 ROOT / "scripts/librarian/taxonomy_from_proposal.py", ROOT / "tests/validate_proof_receipts.py",
                 ROOT / "docs/library/INDUCTION-REVISION-3-BRIEF-2026-09-06.md",
                 ROOT / "docs/library/ORCHESTRATION-V1-2026-09-04.md", ROOT / "docs/library/STAGE2-AUDIT-PLAN-2026-09-05.md",
                 ROOT / "docs/library/INDUCTION-AUDIT-2026-09-05.md", ROOT / "docs/library/INDUCTION-AUDIT-10-2026-09-05.md",
                 ROOT / "scripts/librarian/prompts/induce-consolidate.md"):
        a.read(path)
    prior_hashes = {name: a.sha(a.read(PROOF / name)) for name in (
        "audit-induction-measurements-2026-09-05.json", "audit-induction-9-measurements-2026-09-05.json",
        "audit-induction-10-measurements-2026-09-05.json", "audit-decision-2-measurements-2026-09-06.json")}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    result = dict(schema_version=1, audit="induction-run-AD-decision3", completed=True, approval=False,
        verdict="REJECT taxonomy-v2-2026-09-05 (revision decision 3)", audited_checkout_sha=head,
        blocking_findings=["B5-R3"] + ([] if composer_bytes_equal else ["C3-EOL"]),
        model_calls_executed_by_audit=0, helper_calls_executed_by_audit=0, databases_opened_by_audit=0,
        unchanged_gates="B1-B3 and B7-B9 stand from attempt-10 audit; not rerun by this script.",
        decision_sha256=EXPECTED_SHA, predecessor_sha256=a.sha(before_raw),
        composition=dict(recorded_edit_count=11, per_edit=edit_records, unchanged_outside_edits=True,
            exact_serialization_equal=True, independent_replay_equal=True, composer_exact_bytes_equal=composer_bytes_equal,
            command=composer_command, measurements_binding=measurement_binding, exact_repairs=exact_repairs,
            diagnostic_lf_binding_reconstruction_equals_decision=True,
            composer_verification=composer_result, source_hashes_verified=True,
            semantic_review="All eleven edits exactly implement audit 11's repairs and pass relevance. Fresh sampling exposes three further destination failures."),
        B4=b4, B5=b5, B6=b6, full_proposal_validator_passed=True,
        proposed_repair_preflight=repair_preflight,
        independent_keys_and_expansion_equal=True, projection=projection_result,
        packet_binding=dict(sha256=PACKET_SHA, proposal_hash_equal=True, all_candidate_fields_equal=True),
        prior_measurement_hashes=prior_hashes, self_test_passed=tests, input_files=a.FILES)
    output = a.contained(output)
    if output != OUT:
        raise ValueError("This dispatch writes only its named decision-3 measurements")
    output.write_bytes(pretty(result))
    print(json.dumps(dict(completed=True, approval=False, edits=11, nodes=11,
        composer_check_exit=composer_cli.returncode, exact_eleven_repairs=True,
        node_supports=len(node_evidence), ledger_references=len(ledger_evidence), ledger=b5["disposition_counts"],
        sample_rows=len(sample), destination_failures=sorted(LEDGER_FAILURES),
        boundary_repair=boundary_repair["verdict"], self_tests=len(tests), projection=projection_result,
        proposed_repair_preflight=repair_preflight), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", type=Path, default=DECISION)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    main(a.contained(args.decision), a.contained(args.output), args.self_test)

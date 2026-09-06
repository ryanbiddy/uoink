"""Offline run-AF mechanical acceptance replay; writes only its measurements.

Use --check to compare existing measurements without writing. No service, database,
model, label file or exported taxonomy is opened or created.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROOF = "docs/library/proof/"
DECISION = PROOF + "taxonomy-v2-revision-decision-5-2026-09-06.json"
BASE = PROOF + "taxonomy-v2-revision-decision-4-2026-09-06.json"
THIRD = PROOF + "taxonomy-v2-revision-decision-3-2026-09-06.json"
PREVIOUS = PROOF + "audit-decision-4-measurements-2026-09-06.json"
PRIOR_AUDIT = "docs/library/INDUCTION-AUDIT-13-2026-09-06.md"
AUDIT = "docs/library/INDUCTION-AUDIT-14-2026-09-06.md"
OUTPUT = PROOF + "audit-decision-5-measurements-2026-09-06.json"
APPROVER = "Codex / GPT-6 Astra (INDUCTION-AUDIT-14)"
EXPECTED_DECISION = "f01bd7c2938894211a3efc86c8e08c36f979a737542aecfa29cf45a2578f5ba7"
EXPECTED_PROPOSAL = "9863d85647c2fb8781b42993c3eec52255bd68b7bbae240393543906d96cd469"
EXPECTED_LEDGER = "d43012b6f70fbe6ac626e245819343a8456d733995d55845d594549b13d81f70"
EXPECTED_MEASUREMENTS = "2b9ddf14fcc6d3b86638fb65f02b8ba1360c535037f7df33ce43d9d42a142748"
EXPECTED_COUNTS = dict(proposed_concept=44, existing_concept=37, still_unmapped=120, unsupported=24)
FIELDS = ("shelf_id", "path", "definition", "include", "exclude")

sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "scripts/librarian")]
import compose_revision_decision_n as composer  # noqa: E402
import taxonomy_from_proposal as projector  # noqa: E402
import validate_proof_receipts as validator  # noqa: E402


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def nodes_fragment(raw):
    text = raw.decode("utf-8")
    matches = list(re.finditer(r'"nodes":\s*', text))
    assert len(matches) == 1
    start = matches[0].end()
    _, length = json.JSONDecoder().raw_decode(text[start:])
    return text[start:start + length].encode("utf-8")


def independent_projection(nodes):
    result = []
    for node in nodes:
        out = {key: copy.deepcopy(node[key]) for key in FIELDS}
        out["path"] = [unicodedata.normalize("NFC", part) for part in out["path"]]
        out.update(name=out["path"][-1], retired=bool(node.get("retired", False)))
        result.append(out)
    ids = {tuple(node["path"]): node["shelf_id"] for node in result}
    for node in result:
        node["parent_shelf_id"] = ids.get(tuple(node["path"][:-1]))
        assert len(node["path"]) == 1 or node["parent_shelf_id"] is not None
    return sorted(result, key=lambda node: (len(node["path"]), node["path"], node["shelf_id"]))


def measure():
    inputs = {}

    def read(path):
        full = (ROOT / path).resolve()
        full.relative_to(ROOT)
        raw = full.read_bytes()
        inputs[full.relative_to(ROOT).as_posix()] = dict(sha256=sha(raw), bytes=len(raw))
        return raw

    def load(path):
        return validator.decode_json(read(path))

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    raw, base_raw, third_raw, previous_raw = [read(p) for p in (DECISION, BASE, THIRD, PREVIOUS)]
    decision, base, third, previous = [validator.decode_json(r) for r in (raw, base_raw, third_raw, previous_raw)]
    assert sha(raw) == EXPECTED_DECISION
    assert sha(previous_raw) == EXPECTED_MEASUREMENTS
    assert previous["decision_sha256"] == sha(base_raw)
    assert decision["successor_of"] == dict(path=BASE, sha256=sha(base_raw))
    assert decision["repair_specification"] == dict(audit=PRIOR_AUDIT, measurements=PREVIOUS,
                                                    measurements_sha256=sha(previous_raw))
    candidate_bindings = {}
    for path in (DECISION, BASE, THIRD, PREVIOUS):
        blob = subprocess.check_output(["git", "show", f"{head}:{path}"], cwd=ROOT)
        assert sha(blob) == inputs[path]["sha256"], path
        candidate_bindings[path] = sha(blob)

    reviewed = previous["proposed_repair_preflight"]
    assert reviewed["canonical_proposal_sha256"] == EXPECTED_PROPOSAL
    assert reviewed["canonical_ledger_sha256"] == EXPECTED_LEDGER
    audit_text = read(PRIOR_AUDIT).decode("utf-8")
    assert EXPECTED_PROPOSAL in audit_text and EXPECTED_LEDGER in audit_text
    proposal = decision["proposal"]
    assert sha(canonical(proposal)) == EXPECTED_PROPOSAL
    assert sha(canonical(proposal["coverage_ledger"])) == EXPECTED_LEDGER
    records = [r for r in previous["B5"]["sample_records"] if r.get("exact_proposed_replacement")]
    replacements = {r["exact_proposed_replacement"]["card_key"]: r["exact_proposed_replacement"] for r in records}
    assert len(records) == len(replacements) == 20
    before = {r["card_key"]: r for r in base["proposal"]["coverage_ledger"]}
    for record in records:
        assert record["row"] == before[record["row"]["card_key"]]
    reconstructed = copy.deepcopy(base["proposal"])
    reconstructed["coverage_ledger"] = [copy.deepcopy(replacements.get(r["card_key"], r))
                                         for r in reconstructed["coverage_ledger"]]
    assert reconstructed == proposal
    expected_edits = [dict(finding="B5-R", target="ledger " + key, field="row",
                           before=before[key], after=replacements[key]) for key in sorted(replacements)]
    assert decision["edits"] == expected_edits
    rows = {r["card_key"]: r for r in proposal["coverage_ledger"]}
    assert len(rows) == len(proposal["coverage_ledger"]) == 225
    assert {k for k in rows if rows[k] != before[k]} == set(replacements)
    destination_edits = [k for k in replacements if rows[k]["shelf_ids"] != before[k]["shelf_ids"]]
    reason_edits = sorted(set(replacements) - set(destination_edits))
    assert len(destination_edits) == 17 and reason_edits == ["c046", "c055", "c089"]
    for key in reason_edits:
        assert {k: v for k, v in rows[key].items() if k != "reason"} == {
            k: v for k, v in before[key].items() if k != "reason"}
    for key, row in rows.items():
        if row["shelf_ids"]:
            assert row["evidence"] == before[key]["evidence"]
        else:
            assert row["evidence"] == []
    assert dict(Counter(r["disposition"] for r in rows.values())) == EXPECTED_COUNTS
    assert nodes_fragment(raw) == nodes_fragment(base_raw) == nodes_fragment(third_raw)
    assert proposal["nodes"] == base["proposal"]["nodes"] == third["proposal"]["nodes"]
    for field in set(proposal) - {"coverage_ledger"}:
        assert proposal[field] == base["proposal"][field]
    assert decision["sources"] == base["sources"]
    for source in decision["sources"].values():
        assert sha(read(source["path"])) == source["sha256"]
        assert sha(read(str(Path(source["path"]).with_name("receipts.json")))) == source["receipts_sha256"]
    replay = composer.compose(ROOT / BASE, ROOT / PREVIOUS, PRIOR_AUDIT, [])
    assert decision == replay and raw == pretty(replay)
    validation = composer.verify(decision, EXPECTED_COUNTS)

    archive = load(PROOF + "run-2026-09-05/receipts.json")
    assert inputs[PROOF + "run-2026-09-05/receipts.json"]["sha256"] == validator.ARCHIVE_SHA256
    receipts = load(PROOF + "induction-run-10-2026-09-05/receipts.json")
    state = dict(pins=len(archive["before"]["pins"]), memberships=len(archive["before"]["memberships"]),
                 item_policies=len(archive["before"]["item_policies"]), active_version_id=archive["before"]["active_version_id"])
    assert all(receipts["induction_state"][key] == value for key, value in state.items())
    assert state == dict(pins=0, memberships=0, item_policies=0, active_version_id="taxonomy-v1-2026-09-04")
    assert all(proposal["pin_impact_report"]["measured_" + k] == state[k] for k in ("pins", "memberships"))
    assert proposal["pin_impact_report"]["silent_redirects"] is False and proposal["pin_impact_report"]["items"] == []
    receipt_results = {}
    for number in (9, 10):
        folder = PROOF + f"induction-run-{number}-2026-09-05/"
        receipt_results[str(number)] = validator.validate_induction_receipts(load(folder + "receipts.json"),
            artifact_root=ROOT / folder, require_real=True)
    for batch in receipts["batches"]:
        read(PROOF + "induction-run-10-2026-09-05/calls/" + batch["call_id"] + ".stdout")
    load(PROOF + "induction-manifest-2026-09-05.json")
    parent = load("docs/library/taxonomy-v1-2026-09-04.json")
    nodes = independent_projection(proposal["nodes"])
    parent_nodes = independent_projection(parent["nodes"])
    by_id = {n["shelf_id"]: n for n in nodes}
    assert len(nodes) == 11 and len(parent_nodes) == 7
    assert all(canonical(by_id[n["shelf_id"]]) == canonical(n) for n in parent_nodes)
    revision = sha(canonical(nodes))
    service = dict(schema_version=1, version_id=proposal["version_id"], parent_version_id=proposal["parent_version_id"],
                   nodes=nodes, revision_hash=revision)
    assert validator.normalized_taxonomy(service) == service
    export = projector.build(ROOT / DECISION, approved_by=APPROVER, approval_record=AUDIT,
                             parent_doc=ROOT / "docs/library/taxonomy-v1-2026-09-04.json")
    assert export["nodes"] == nodes and export["revision_hash"] == revision
    assert export["parent_revision_hash"] == sha(canonical(parent_nodes))
    assert export["approval"]["proposal_sha256"] == EXPECTED_DECISION
    assert revision == previous["projection"]["expected_service_revision_hash"]
    for path in ("scripts/librarian/compose_revision_decision_n.py", "scripts/librarian/compose_revision_decision_2.py",
                 "scripts/librarian/taxonomy_from_proposal.py", "tests/validate_proof_receipts.py", "library_cards.py",
                 "docs/library/ORCHESTRATION-V1-2026-09-04.md", "docs/library/INDUCTION-APPROVAL-BRIEF-2026-09-06.md",
                 "docs/library/INDUCTION-AUDIT-2026-09-05.md", "docs/library/INDUCTION-AUDIT-10-2026-09-05.md",
                 "docs/library/INDUCTION-AUDIT-11-2026-09-06.md", "docs/library/INDUCTION-AUDIT-12-2026-09-06.md",
                 "docs/library/STAGE2-AUDIT-PLAN-2026-09-05.md", ".gitattributes", Path(__file__).relative_to(ROOT)):
        read(path)
    return dict(schema_version=1, audit="induction-run-AF-decision5", completed=True, approval=True,
        verdict="APPROVE taxonomy-v2-2026-09-05 (revision decision 5)", approval_record=AUDIT, approved_by=APPROVER,
        audited_checkout_sha=head, candidate_git_blob_sha256=candidate_bindings, decision_sha256=sha(raw),
        predecessor_sha256=sha(base_raw), prior_measurements_sha256=sha(previous_raw),
        canonical_serialization="UTF-8; sorted keys; ensure_ascii=False; separators=(',', ':'); no trailing newline",
        canonical_proposal_sha256=sha(canonical(proposal)), canonical_ledger_sha256=sha(canonical(proposal["coverage_ledger"])),
        blocking_taxonomy_findings=[], resolved_findings=["B5-R4"],
        review_basis="Exact full-proposal/225-row equality to audit 13's reviewed replacements; no new semantic sample",
        inherited_gates="B1-B3 and B7-B9 from audit 10; B4-B6 semantics and prior resolutions from audits 11-13",
        composition=dict(exact_utf8_lf_bytes=True, independent_reconstruction=True, edits=20, destination_edits=17,
                         reason_only_edits=reason_edits, exact_edits=expected_edits, unchanged_rows=205,
                         measurements_binding=True, source_bindings=True),
        preservation=dict(nodes_equal_decisions3_and4=True, nodes_literal_utf8_sha256=sha(nodes_fragment(raw)),
                          supporting_evidence_equal=True, retained_ledger_evidence_equal=True,
                          rejections_equal=True, pin_fields_equal=True, diff_equal=True,
                          normalized_v1_nodes_equal=True, candidate_counts=previous["B6"]["candidate_counts"]),
        full_proposal_validator_passed=True, proposal_validation=validation, receipt_validation=receipt_results,
        ledger_counts=EXPECTED_COUNTS, mapped_rows=81, node_references=20, ledger_references=sum(len(r["evidence"]) for r in rows.values()),
        rejected_proposals=proposal["rejected_proposals"], archived_pin_state=state, pin_impact_report=proposal["pin_impact_report"],
        projection=dict(status="Calculated in memory for approved decision 5; no export written or service called",
                        metadata_export_bytes=len(pretty(export)), metadata_export_sha256=sha(pretty(export)),
                        metadata_parameters=export["approval"], expected_service_revision_hash=revision,
                        service_returned_revision_hash=None, canonical_service_file_bytes=len(canonical(service) + b"\n"),
                        canonical_service_file_sha256=sha(canonical(service) + b"\n"),
                        parent_revision_hash=export["parent_revision_hash"], independent_nodes_equal=True,
                        validator_normalization_equal=True),
        pending_execution_observations=dict(service_returned_revision_hash=None, disposable_database_identity=None,
                                            integrated_execution_sha=None, sealed_labels_sha256=None,
                                            sealed_mapping_sha256=None, stage2_manifest_sha256=None),
        scope=dict(model_calls=0, helper_calls=0, databases_opened=0, port_5179_used=False, labels_opened=False,
                   taxonomy_export_written=False, apply_enabled=False, commit_made=False),
        input_files=inputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = measure()
    raw = pretty(result)
    if args.check:
        assert (ROOT / OUTPUT).read_bytes() == raw, "Measurements differ, including audited checkout or input fingerprints"
    else:
        (ROOT / OUTPUT).write_bytes(raw)
    print(json.dumps(dict(verdict=result["verdict"], audited_checkout_sha=result["audited_checkout_sha"],
                          measurements_sha256=sha(raw), projection=result["projection"]), indent=2))


if __name__ == "__main__":
    main()

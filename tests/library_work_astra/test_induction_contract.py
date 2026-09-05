"""Induction contract fixtures use archived original evidence, never a model."""
import copy

import pytest
from jsonschema.exceptions import ValidationError

from test_receipts_v2 import ROOT, artifact, v


def induction_fixture():
    induction = v.read_json(v.INDUCTION_MANIFEST)
    ids = [r["video_id"] for r in induction["items"]]
    archived = v.read_json(v.ARCHIVE)
    cards = {a["video_id"]: a["packet"]["card"] for a in archived["attempts"] if a["video_id"] in ids}
    tax_raw = (ROOT / "docs/library/taxonomy-v1-2026-09-04.json").read_bytes()
    taxonomy = v.decode_json(tax_raw)
    nodes = []
    for old in taxonomy["nodes"]:
        nodes.append(dict(shelf_id=old["shelf_id"], path=old["path"], definition=old["definition"],
                          include=old["include"], exclude=old["exclude"], supporting_evidence=[],
                          sibling_cues=[dict(include_cue=cue, confusing_alternative="fixture alternative", evidence_needed="fixture distinction") for cue in old["include"]]))
    supports = []
    for vid in ids:
        card = cards[vid]
        for excerpt in card["excerpts"]:
            if excerpt["evidence_kind"] == "timed_clip" or card.get("source_type") in {"page", "x_article", "x_thread", "reddit_thread", "note"}:
                supports.append(dict(video_id=vid, source_revision=card["source_revision"], card_hash=card["card_hash"],
                                     excerpt_id=excerpt["excerpt_id"], quote=excerpt["text"].split()[0]))
                break
        if len(supports) == 5:
            break
    nodes.append(dict(shelf_id="fixture-new", path=["Synthetic fixture only"], definition="A structural fixture, not a proposed taxonomy",
                      include=["fixture"], exclude=["real gate claim"],
                      sibling_cues=[dict(include_cue="fixture", confusing_alternative="not a fixture", evidence_needed="fixture only")],
                      supporting_evidence=supports))
    proposal = dict(version_id="fixture-taxonomy", parent_version_id=taxonomy["version_id"], nodes=nodes,
                    coverage_ledger=[dict(video_id=vid, disposition="still_unmapped", shelf_ids=[], evidence=[], reason="Synthetic contract fixture") for vid in ids],
                    diff=dict(preserved=[n["shelf_id"] for n in taxonomy["nodes"]], added=["fixture-new"], renamed=[], merged=[], split=[], retired=[]),
                    pin_impact_report=dict(silent_redirects=False, items=[]), rejected_proposals=[])
    return proposal, induction, cards, taxonomy, tax_raw


def test_induction_supports_and_complete_ledger():
    proposal, induction, cards, taxonomy, _ = induction_fixture()
    v.validate_induction_proposal(proposal, induction, cards, taxonomy)


NEGATIVE_KINDS = ["four cards", "repeated card", "25 words", "foreign card", "missing source", "title support", "missing ledger", "duplicate ledger", "silent pins", "missing alternative", "unchanged id", "missing parent"]


@pytest.mark.parametrize("kind", NEGATIVE_KINDS)
def test_induction_proposal_negative(kind):
    p, induction, cards, tax, _ = induction_fixture()
    node = p["nodes"][-1]
    if kind == "four cards":
        node["supporting_evidence"].pop()
    elif kind == "repeated card":
        node["supporting_evidence"][-1] = copy.deepcopy(node["supporting_evidence"][0])
    elif kind == "25 words":
        node["supporting_evidence"][0]["quote"] = " ".join(["word"] * 25)
    elif kind == "foreign card":
        node["supporting_evidence"][0]["video_id"] = "foreign"
    elif kind == "missing source":
        node["supporting_evidence"][0].pop("source_revision")
    elif kind == "title support":
        node["supporting_evidence"][0]["excerpt_id"] = "0" * 64
    elif kind == "missing ledger":
        p["coverage_ledger"].pop()
    elif kind == "duplicate ledger":
        p["coverage_ledger"][-1] = copy.deepcopy(p["coverage_ledger"][0])
    elif kind == "silent pins":
        p["pin_impact_report"]["silent_redirects"] = True
    elif kind == "missing alternative":
        node["sibling_cues"] = []
    elif kind == "unchanged id":
        for field in ("path", "definition", "include", "exclude"):
            node[field] = tax["nodes"][0][field]
    elif kind == "missing parent":
        node["path"] = ["Absent parent", "child"]
    with pytest.raises((ValueError, ValidationError)):
        v.validate_induction_proposal(p, induction, cards, tax)


def make_induction_receipt():
    p, induction, cards, taxonomy, tax_raw = induction_fixture()
    ids = [row["video_id"] for row in induction["items"]]
    batch_template = "{{TAXONOMY}}\n{{CARDS}}"
    consolidate_template = "Consolidate the supplied proposals: {{PROPOSALS}}"
    calls, batches, proposals = [], [], []

    def call(cid, aids, stdin, result, start):
        schema = '{"type":"object"}'
        return dict(call_id=cid, attempt_ids=aids, argv=["claude", "-p", "--json-schema", schema],
                    schema_text=schema, schema_sha256=v.sha(schema.encode()),
                    stdin=artifact(stdin.encode()), stdout=artifact(dict(structured_output=result)), stderr=artifact(b""),
                    start_monotonic_ns=start, end_monotonic_ns=start+1, exit_status=0, timed_out=False, cancellation=None,
                    usage=None, modelUsage=None, cli_estimated_cost_usd=None)
    for start in range(0, 225, 25):
        selected = ids[start:start+25]
        cid = f"batch-{start}"
        prompt = v.library_cards.serialize_card(taxonomy) + "\n" + "\n\n".join(v.library_cards.card_text(cards[vid]) for vid in selected)
        partial = dict(fixture_batch=start)
        calls.append(call(cid, selected, prompt, partial, start))
        batches.append(dict(call_id=cid, video_ids=selected))
        proposals.append(partial)
    calls.append(call("final", ["consolidation"], consolidate_template.replace("{{PROPOSALS}}", v.library_cards.serialize_card(proposals)), p, 226))
    r = dict(kind="induction-receipts", schema_version=1, run_id="fixture", mode="mock", status="completed", abort_reason=None,
             inputs=dict(induction_manifest_sha256=v.sha(v.INDUCTION_MANIFEST.read_bytes()), archived_receipts_sha256=v.ARCHIVE_SHA256,
                         taxonomy_file_sha256=v.sha(tax_raw), batch_prompt_sha256=v.sha(batch_template.encode()),
                         consolidation_prompt_sha256=v.sha(consolidate_template.encode())),
             batch_prompt=artifact(batch_template.encode()), consolidation_prompt=artifact(consolidate_template.encode()), taxonomy=artifact(tax_raw),
             calls=calls, batches=batches, consolidation_call_id="final", proposal=p, proposal_artifact=artifact(p),
             accounting=v.call_accounting(calls), execution=dict(git_sha="a"*40, start_monotonic_ns=0, end_monotonic_ns=227,
                fingerprints={k: artifact(k.encode()) for k in ("runner", "validator", "card_builder")}))
    return r


def test_complete_induction_receipt_and_modified_batch():
    r = make_induction_receipt()
    assert v.validate_induction_receipts(r)["call_count"] == 10
    with pytest.raises(ValueError, match="fixture evidence"):
        v.validate_induction_receipts(r, require_real=True)
    r["calls"][0]["stdin"] = artifact(b"modified batch")
    with pytest.raises(ValueError, match="modified cards"):
        v.validate_induction_receipts(r)


def test_freezes_reproduce_and_do_not_overlap():
    report = v.verify_stage2_freezes()
    assert report["holdout_count"] == 60 and report["induction_count"] == 225
    assert report["feasibility"]["eligible_counts"] == {"timed_evidence": 47, "text_only": 13}
    holdout, induction = v.stage2_freezes()
    assert sum(row["old_holdout"] for row in induction["items"]) == 23
    selected = {r["video_id"] for rows in holdout["strata"].values() for r in rows}
    assert not selected & {r["video_id"] for r in induction["items"]}


def run_offline_checks():
    test_induction_supports_and_complete_ledger()
    for kind in NEGATIVE_KINDS:
        test_induction_proposal_negative(kind)
    test_complete_induction_receipt_and_modified_batch()
    test_freezes_reproduce_and_do_not_overlap()
    return len(NEGATIVE_KINDS) + 3

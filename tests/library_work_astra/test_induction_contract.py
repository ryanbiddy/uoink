"""Induction contract fixtures use archived original evidence, never a model."""
import copy
import importlib.util

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
    supports, support_batches = [], set()
    for position, vid in enumerate(ids):
        if position // 25 in support_batches:
            continue
        card = cards[vid]
        for excerpt in card["excerpts"]:
            if excerpt["evidence_kind"] == "timed_clip" or card.get("source_type") in {"page", "x_article", "x_thread", "reddit_thread", "note"}:
                supports.append(dict(video_id=vid, source_revision=card["source_revision"], card_hash=card["card_hash"],
                                     excerpt_id=excerpt["excerpt_id"], quote=excerpt["text"].split()[0]))
                support_batches.add(position // 25)
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
    for row in proposal["coverage_ledger"]:
        support = next((s for s in supports if s["video_id"] == row["video_id"]), None)
        if support:
            row.update(disposition="proposed_concept", shelf_ids=["fixture-new"],
                       evidence=[dict(excerpt_id=support["excerpt_id"])])
    return proposal, induction, cards, taxonomy, tax_raw


def batch_fixture(proposal, selected):
    """Mock producers must retain full support in both batch evidence locations."""
    candidates = []
    by_video = {}
    for node in proposal["nodes"]:
        supports = [copy.deepcopy(s) for s in node["supporting_evidence"] if s["video_id"] in selected]
        if supports:
            candidate = {key: copy.deepcopy(node[key]) for key in ("path", "definition", "include", "exclude", "sibling_cues")}
            candidates.append(dict(candidate, supporting_evidence=supports))
            for support in supports:
                by_video[support["video_id"]] = (node["path"], support)
    dispositions = []
    for vid in selected:
        path, support = by_video.get(vid, (None, None))
        dispositions.append(dict(video_id=vid, disposition="proposed_concept" if support else "still_unmapped",
                                 candidate_paths=[path] if support else [], existing_shelf_ids=[],
                                 evidence=[copy.deepcopy(support)] if support else [], reason="Synthetic batch fixture"))
    return dict(candidates=candidates, dispositions=dispositions)


def batch_outputs_fixture(proposal, induction):
    ids = [row["video_id"] for row in induction["items"]]
    outputs = {}
    for start in range(0, len(ids), 25):
        selected = ids[start:start+25]
        output = batch_fixture(proposal, selected)
        outputs.update({vid: output for vid in selected})
    return outputs


def test_induction_supports_and_complete_ledger():
    proposal, induction, cards, taxonomy, _ = induction_fixture()
    outputs = batch_outputs_fixture(proposal, induction)
    assert len({id(outputs[s["video_id"]]) for s in proposal["nodes"][-1]["supporting_evidence"]}) == 5
    v.validate_induction_proposal(proposal, induction, cards, taxonomy,
                                  batch_outputs=outputs)


NEGATIVE_KINDS = ["four cards", "repeated card", "25 words", "foreign card", "missing source", "title support", "missing ledger", "duplicate ledger", "silent pins", "missing alternative", "unchanged id", "missing parent",
                  "full ledger support", "long reason", "invalid reference", "duplicate reference", "foreign reference", "empty mapped evidence", "refusal evidence"]


@pytest.mark.parametrize("kind", NEGATIVE_KINDS)
def test_induction_proposal_negative(kind):
    p, induction, cards, tax, _ = induction_fixture()
    batch_outputs = batch_outputs_fixture(p, induction)
    node = p["nodes"][-1]
    mapped = next(row for row in p["coverage_ledger"] if row["evidence"])
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
    elif kind == "full ledger support":
        mapped["evidence"] = [copy.deepcopy(node["supporting_evidence"][0])]
    elif kind == "long reason":
        mapped["reason"] = "x" * 161
    elif kind == "invalid reference":
        mapped["evidence"][0]["excerpt_id"] = "not-a-hash"
    elif kind == "duplicate reference":
        mapped["evidence"].append(copy.deepcopy(mapped["evidence"][0]))
    elif kind == "foreign reference":
        mapped["evidence"][0]["excerpt_id"] = node["supporting_evidence"][1]["excerpt_id"]
    elif kind == "empty mapped evidence":
        mapped["evidence"] = []
    elif kind == "refusal evidence":
        mapped.update(disposition="still_unmapped", shelf_ids=[])
    with pytest.raises((ValueError, ValidationError)):
        v.validate_induction_proposal(p, induction, cards, tax, batch_outputs=batch_outputs)


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
        partial = batch_fixture(p, selected)
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


def recorded_output(call):
    return v.decode_json(v.artifact_bytes(call["stdout"], ROOT))["structured_output"]


def refresh_receipt(receipts):
    """Rebind fixture bytes so tamper cases reach the intended semantic check."""
    final = receipts["calls"][-1]
    template = v.artifact_bytes(receipts["consolidation_prompt"], ROOT).decode()
    proposals = [recorded_output(call) for call in receipts["calls"][:-1]]
    final["stdin"] = artifact(template.replace("{{PROPOSALS}}", v.library_cards.serialize_card(proposals)).encode())
    final["stdout"] = artifact(dict(structured_output=receipts["proposal"]))
    receipts["proposal_artifact"] = artifact(receipts["proposal"])
    receipts["accounting"] = v.call_accounting(receipts["calls"])


def test_reference_resolution_and_relaxed_call_schema():
    r = make_induction_receipt()
    p = r["proposal"]
    _, _, cards, _, _ = induction_fixture()
    card = next(card for card in cards.values() if sum(e["evidence_kind"] == "timed_clip" for e in card["excerpts"]) >= 2)
    supports = [dict(video_id=card["video_id"], source_revision=card["source_revision"], card_hash=card["card_hash"],
                     excerpt_id=e["excerpt_id"], quote=e["text"].split()[0])
                for e in card["excerpts"] if e["evidence_kind"] == "timed_clip"][:2]
    mapped = next(row for row in p["coverage_ledger"] if row["video_id"] == card["video_id"])
    mapped.update(disposition="existing_concept", shelf_ids=[p["diff"]["preserved"][0]], reason="x" * 160,
                  evidence=[dict(excerpt_id=s["excerpt_id"]) for s in supports])
    batch = next(call for call in r["calls"] if card["video_id"] in call["attempt_ids"])
    output = recorded_output(batch)
    row = next(row for row in output["dispositions"] if row["video_id"] == card["video_id"])
    row.update(disposition="existing_concept", candidate_paths=[], existing_shelf_ids=mapped["shelf_ids"], evidence=supports)
    batch["stdout"] = artifact(dict(structured_output=output))
    # The call may omit pattern and uniqueItems; the offline schema keeps both.
    spec = importlib.util.spec_from_file_location("astra_induce_runner", ROOT / "scripts/librarian/induce_run.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    full_schema = copy.deepcopy(v.PROPOSAL_SCHEMA)
    relaxed = runner._cli_safe_schema(full_schema)
    assert full_schema == v.PROPOSAL_SCHEMA and relaxed != full_schema
    final = r["calls"][-1]
    final["schema_text"] = v.canonical(relaxed)
    final["schema_sha256"] = v.sha(final["schema_text"].encode())
    final["argv"][-1] = final["schema_text"]
    refresh_receipt(r)
    assert v.validate_induction_receipts(r)["call_count"] == 10
    for change in ("pattern", "uniqueItems", "maxLength"):
        bad = copy.deepcopy(r)
        row = next(row for row in bad["proposal"]["coverage_ledger"] if row["evidence"])
        if change == "pattern":
            row["evidence"][0]["excerpt_id"] = "invalid"
        elif change == "uniqueItems":
            row["evidence"].append(copy.deepcopy(row["evidence"][0]))
        else:
            row["reason"] = "x" * 161
        refresh_receipt(bad)
        with pytest.raises(ValidationError) as error:
            v.validate_induction_receipts(bad)
        assert error.value.validator == change


BATCH_NEGATIVE_KINDS = ["missing dispositions", "missing support", "empty quote", "25 words", "invented quote",
                        "source revision", "card hash", "unknown excerpt", "wrong support owner", "wrong disposition owner",
                        "wrong batch ledger", "missing candidates", "changed node quote", "wrong batch node"]


@pytest.mark.parametrize("kind", BATCH_NEGATIVE_KINDS)
def test_recorded_batch_support_negative(kind):
    r = make_induction_receipt()
    output = recorded_output(r["calls"][0])
    disposition = next(row for row in output["dispositions"] if row["evidence"])
    support = disposition["evidence"][0]
    expected = "Ledger excerpt lacks valid recorded batch disposition support"
    if kind == "missing dispositions":
        output.pop("dispositions")  # Candidate evidence alone cannot back a ledger reference.
    elif kind == "missing support":
        disposition["evidence"] = []
    elif kind == "empty quote":
        support["quote"] = ""
    elif kind == "25 words":
        support["quote"] = " ".join(["word"] * 25)
    elif kind == "invented quote":
        support["quote"] = "invented fixture quotation"
    elif kind == "source revision":
        support["source_revision"] = "0" * 64
    elif kind == "card hash":
        support["card_hash"] = "0" * 64
    elif kind == "unknown excerpt":
        support["excerpt_id"] = "0" * 64
        next(row for row in r["proposal"]["coverage_ledger"] if row["evidence"])["evidence"][0]["excerpt_id"] = "0" * 64
    elif kind == "wrong support owner":
        support["video_id"] = "foreign"
    elif kind == "wrong disposition owner":
        disposition["video_id"] = "foreign"
    elif kind == "wrong batch ledger":
        other = recorded_output(r["calls"][1])
        other["dispositions"].append(copy.deepcopy(disposition))
        disposition["evidence"] = []
        r["calls"][1]["stdout"] = artifact(dict(structured_output=other))
    elif kind in {"missing candidates", "changed node quote", "wrong batch node"}:
        expected = "Node support differs from recorded batch candidate evidence"
        if kind == "missing candidates":
            output.pop("candidates")  # Disposition evidence alone cannot back node support.
        elif kind == "changed node quote":
            output["candidates"][0]["supporting_evidence"][0]["quote"] += " "
        else:
            other = recorded_output(r["calls"][1])
            other["candidates"] = output.pop("candidates")
            r["calls"][1]["stdout"] = artifact(dict(structured_output=other))
    r["calls"][0]["stdout"] = artifact(dict(structured_output=output))
    refresh_receipt(r)
    with pytest.raises(ValueError, match=expected):
        v.validate_induction_receipts(r)


def test_ineligible_original_ledger_evidence():
    r = make_induction_receipt()
    _, _, cards, _, _ = induction_fixture()
    card = next(card for card in cards.values() if card.get("source_type") not in
                {"page", "x_article", "x_thread", "reddit_thread", "note"}
                and any(e["evidence_kind"] == "text_only" for e in card["excerpts"]))
    excerpt = next(e for e in card["excerpts"] if e["evidence_kind"] == "text_only")
    support = dict(video_id=card["video_id"], source_revision=card["source_revision"], card_hash=card["card_hash"],
                   excerpt_id=excerpt["excerpt_id"], quote=excerpt["text"].split()[0])
    mapped = next(row for row in r["proposal"]["coverage_ledger"] if row["video_id"] == card["video_id"])
    mapped.update(disposition="existing_concept", shelf_ids=[r["proposal"]["diff"]["preserved"][0]],
                  evidence=[dict(excerpt_id=excerpt["excerpt_id"])])
    batch = next(call for call in r["calls"] if card["video_id"] in call["attempt_ids"])
    output = recorded_output(batch)
    row = next(row for row in output["dispositions"] if row["video_id"] == card["video_id"])
    row.update(disposition="existing_concept", candidate_paths=[], existing_shelf_ids=mapped["shelf_ids"], evidence=[support])
    batch["stdout"] = artifact(dict(structured_output=output))
    refresh_receipt(r)
    with pytest.raises(ValueError, match="Ledger excerpt lacks valid recorded batch disposition support"):
        v.validate_induction_receipts(r)


IDENTITY_NEGATIVE_KINDS = ["proposal artifact", "consolidation output", "batch hash", "extra call", "early consolidation"]


@pytest.mark.parametrize("kind", IDENTITY_NEGATIVE_KINDS)
def test_induction_call_identity_negative(kind):
    r = make_induction_receipt()
    expected = "Proposal differs from original consolidation output"
    if kind == "proposal artifact":
        altered = copy.deepcopy(r["proposal"])
        altered["coverage_ledger"][0]["reason"] = "Rewritten after consolidation"
        r["proposal_artifact"] = artifact(altered)
    elif kind == "consolidation output":
        altered = copy.deepcopy(r["proposal"])
        altered["coverage_ledger"][0]["reason"] = "Different recorded output"
        r["calls"][-1]["stdout"] = artifact(dict(structured_output=altered))
    elif kind == "batch hash":
        r["calls"][0]["stdout"]["sha256"] = "0" * 64
        expected = "Artifact bytes/hash mismatch"
    elif kind == "extra call":
        extra = copy.deepcopy(r["calls"][-1])
        extra.update(call_id="second-consolidation", attempt_ids=["second-consolidation"])
        r["calls"].append(extra)
        expected = "Missing/duplicate/unaccounted induction call"
    else:
        r["calls"][-1]["start_monotonic_ns"] = 0
        expected = "Consolidation precedes a batch completion"
    with pytest.raises(ValueError, match=expected):
        v.validate_induction_receipts(r)


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
    for kind in BATCH_NEGATIVE_KINDS:
        test_recorded_batch_support_negative(kind)
    for kind in IDENTITY_NEGATIVE_KINDS:
        test_induction_call_identity_negative(kind)
    test_ineligible_original_ledger_evidence()
    test_reference_resolution_and_relaxed_call_schema()
    test_complete_induction_receipt_and_modified_batch()
    test_freezes_reproduce_and_do_not_overlap()
    return len(NEGATIVE_KINDS) + len(BATCH_NEGATIVE_KINDS) + len(IDENTITY_NEGATIVE_KINDS) + 8

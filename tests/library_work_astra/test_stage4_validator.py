"""Offline AP validator checks. Synthetic v2 cards are not a production freeze."""
import copy
import importlib.util
import sys
from unittest.mock import patch

import pytest
from jsonschema.exceptions import ValidationError

from test_receipts_v2 import v, proof_fixture, guard_fixture


def rehash_card(card):
    card["clips"] = [e for e in card["excerpts"] if e["evidence_kind"] == "timed_clip"]
    card["chars_chosen_clips"] = sum(len(e["text"]) for e in card["clips"])
    card["card_hash"] = v.library_cards._hash({k: value for k, value in card.items() if k != "card_hash"})
    return dict(source_revision=card["source_revision"], card_hash=card["card_hash"],
                card_bytes=len(v.library_cards.card_text(card).encode("utf-8")),
                stratum="timed_evidence" if card["clips"] else "text_only",
                source_type=card["source_type"], status=card["status"])


@pytest.fixture(scope="module")
def candidate():
    """Replay every archived card's identity; fabricate no source/label conclusions."""
    old = v.read_json(v.MANIFEST)
    original = v.read_json(v.HOLDOUT_V3)
    heads = v.archived_stage1_heads()
    archived = v.read_json(v.ARCHIVE)
    cards = {a["video_id"]: copy.deepcopy(a["packet"]["card"]) for a in archived["attempts"]}
    m = copy.deepcopy(v.read_json(v.MANIFEST_STAGE3))
    m.update(stage=4, card_profile=copy.deepcopy(v.PROFILE_STAGE4), card_payloads=cards)
    for vid, card in cards.items():
        card["selection_version"] = "spread-longest-v2"
        prose = v.library_cards.opening_prose(heads[vid].decode("utf-8", errors="replace"))
        if prose and card["source_type"] in v.PROSE_SOURCES and card["clips"]:
            # Fixture data checks the validator, not Gemini's timed selection algorithm.
            card["excerpts"] = card["excerpts"][:5] + [dict(
                excerpt_id=v.library_cards._hash([vid, "opening_prose", prose]), evidence_kind="text_only",
                start=None, end=None, timing="not_timed", text=prose[:240], deep_link=card["url"], truncated=len(prose) > 240)]
        frozen = rehash_card(card)
        if frozen["card_bytes"] > 8192:
            card.update(hint=None, summary_hint=None)
            frozen = rehash_card(card)
        while frozen["card_bytes"] > 8192:
            assert len(card["clips"]) > 1
            card["excerpts"].remove(card["clips"][-1])
            frozen = rehash_card(card)
        m["cards"][vid] = frozen
    m["cards_hash"] = v.digest(m["cards"])
    m["hashes"].update(cards_hash=m["cards_hash"], card_profile_hash=v.digest(m["card_profile"]))
    m["execution"] = dict(model="claude-opus-5", effort=None, batch_size=8, concurrency=4, max_retries=1,
        wall_budget_ms=7200000, error_rate_limit=0.10, error_rate_min_attempts=20,
        guard_rule=v.GUARD_RULE, guard_parameters=copy.deepcopy(v.GUARD_PARAMETERS))
    m["probe"] = v.stage4_probe(m, v.read_json(v.INDUCTION_MANIFEST), original)
    # Bind current implementation files; source, historical identities and heads stay fixed.
    for name, record in m["files"].items():
        if name not in {"gold", "mapping"}:
            record["sha256"] = v.sha((v.ROOT / record["path"]).read_bytes())
    m["hashes"]["card_builder_sha256"] = m["files"]["card_builder"]["sha256"]
    return m, old, original, heads


def synthetic_documents(m, original):
    """Empty gold paths intentionally leave every fixture row unmappable."""
    docs = {}

    def add(name, value):
        docs[name] = value
        m["files"][name] = dict(path=v.STAGE_FILES[4][name], sha256=v.sha(v.canonical(value).encode("utf-8")))

    bindings = v.stage4_bindings(m, original, v.HOLDOUT_V3_SHA256)
    add("bindings", bindings)
    selected = [row for rows in bindings["strata"].values() for row in rows]
    add("packet", dict(kind="holdout-v3-stage4-labelling-packet", subject_rule="admissible-excerpts-only",
        bindings_sha256=m["files"]["bindings"]["sha256"], stage4_freeze_hash=v.stage4_freeze_hash(m),
        card_profile_hash=m["hashes"]["card_profile_hash"], taxonomy=m["taxonomy"],
        cards=[dict(video_id=r["video_id"], stratum=r["stratum"], card=m["card_payloads"][r["video_id"]]) for r in selected]))
    labels = [dict(video_id=r["video_id"], stratum=r["stratum"], source_revision=r["source_revision"],
                   card_hash=r["new_card_hash"], outcome="unmappable", shelf_path=[], evidence=None,
                   rationale="Synthetic validator fixture; no semantic judgement.") for r in selected]
    for row in labels:
        excerpt = m["card_payloads"][row["video_id"]]["excerpts"][0]
        row["evidence"] = dict(excerpt_id=excerpt["excerpt_id"], quote=v.normalize_quote(excerpt["text"]).split()[0])
    common = dict(packet_sha256=m["files"]["packet"]["sha256"], bindings_sha256=m["files"]["bindings"]["sha256"],
        taxonomy_revision_hash=m["taxonomy"]["revision_hash"], subject_rule="admissible-excerpts-only",
        prior_v3_exposure="Fixture only; no reviewer session.", items=labels)
    add("labels_gemini", copy.deepcopy(common))
    add("labels_grok", copy.deepcopy(common))
    add("adjudication", dict(copy.deepcopy(common), sealed_at="2026-09-07T00:00:00Z",
                            label_file_sha256={k: m["files"][k]["sha256"] for k in ("labels_gemini", "labels_grok")}))
    add("gold", [dict(r, sealed=True) for r in labels])
    add("mapping", dict(scoring_version="strict-mapped-primary-v2",
        bindings_sha256=m["files"]["bindings"]["sha256"], gold_sha256=m["files"]["gold"]["sha256"],
        adjudicated_sha256=m["files"]["adjudication"]["sha256"], taxonomy_revision_hash=m["taxonomy"]["revision_hash"],
        items={r["video_id"]: dict(source_revision=r["source_revision"], card_hash=r["card_hash"], stratum=r["stratum"],
                                  gold_path=[], outcome="unmappable", mapped_path=None, mapped_shelf_id=None, scorable=False) for r in labels}))
    old = v.read_json(v.MANIFEST)
    add("diff", dict(stage4_freeze_hash=v.stage4_freeze_hash(m), card_profile_hash=m["hashes"]["card_profile_hash"],
        items=[dict(video_id=vid, source_revision=row["source_revision"], old_card_hash=old["cards"][vid]["card_hash"],
                    new_card_hash=row["card_hash"]) for vid, row in m["cards"].items()]))
    m["hashes"].update(implementation_hash=v.digest(m["files"]), gold_file_sha256=m["files"]["gold"]["sha256"])
    return docs


@pytest.fixture
def graph(candidate):
    m, _, original, _ = copy.deepcopy(candidate)
    return m, synthetic_documents(m, original)


def test_all_548_card_profiles_and_original_heads(candidate):
    m, old, _, heads = candidate
    v.check_stage_continuity(m, old, 4)
    assert len(heads) == len(m["card_payloads"]) == 548
    assert all(old["cards"][vid]["card_hash"] != m["cards"][vid]["card_hash"] for vid in m["cards"])
    for vid, card in m["card_payloads"].items():
        v.check_stage4_card(card, m["cards"][vid], vid, heads[vid])


@pytest.mark.parametrize("stage", [2, 3])
@pytest.mark.parametrize("key", ["items", "cards", "cards_hash", "corpus_heads", "corpus_heads_hash", "measured_strata", "source"])
def test_historical_equality_still_required(candidate, stage, key):
    _, old, _, _ = candidate
    m = copy.deepcopy(old)
    v.check_stage_continuity(m, old, stage)
    m[key] = None
    with pytest.raises(ValueError, match="differs from stage 1"):
        v.check_stage_continuity(m, old, stage)


@pytest.mark.parametrize("mutation", ["mixed-version", "stale-hash", "revision", "missing-prose", "prose-timing", "prose-id",
    "prose-text", "prose-truncation", "overlong", "duplicate-excerpt", "byte-budget", "stratum", "clips-alias"])
def test_card_rejects_corruptions_even_with_rehashed_content(candidate, mutation):
    m, _, _, heads = candidate
    vid = next(vid for vid, c in m["card_payloads"].items() if {e["evidence_kind"] for e in c["excerpts"]} == {"text_only", "timed_clip"})
    card = copy.deepcopy(m["card_payloads"][vid])
    frozen = copy.deepcopy(m["cards"][vid])
    prose = next(e for e in card["excerpts"] if e["evidence_kind"] == "text_only")
    if mutation == "mixed-version": card["selection_version"] = "spread-longest-v1"
    if mutation == "revision": card["source_revision"] = "0" * 64
    if mutation == "missing-prose": card["excerpts"].remove(prose)
    if mutation == "prose-timing": prose["start"] = 0
    if mutation == "prose-id": prose["excerpt_id"] = "0" * 64
    if mutation == "prose-text": prose["text"] = "invented prose"
    if mutation == "prose-truncation": prose["truncated"] = not prose["truncated"]
    if mutation == "overlong": card["excerpts"][0]["text"] = "x" * 241
    if mutation == "duplicate-excerpt": card["excerpts"][0]["excerpt_id"] = prose["excerpt_id"]
    if mutation == "byte-budget": card["title"] = "x" * 8192
    if mutation == "stratum": frozen["stratum"] = "text_only"
    entry = rehash_card(card)
    frozen.update({k: entry[k] for k in ("card_hash", "card_bytes")})
    if mutation == "stale-hash": card["card_hash"] = "0" * 64
    if mutation == "clips-alias": card["clips"] = []
    with pytest.raises(ValueError):
        v.check_stage4_card(card, frozen, vid, heads[vid])


def test_reference_graph_accepts_complete_new_bindings(graph):
    v.check_stage4_references(*graph)


def test_sealing_is_acyclic_and_unsealed_candidate_cannot_validate(candidate):
    m, _, original, _ = copy.deepcopy(candidate)
    prepared_hash = v.stage4_freeze_hash(m)
    synthetic_documents(m, original)
    assert v.stage4_freeze_hash(m) == prepared_hash
    m["freeze_status"] = "awaiting-stage4-seal"
    with pytest.raises(ValueError, match="freeze is incomplete"):
        v.verify_manifest(m)
    with proof_fixture() as (r, _), pytest.raises(ValueError, match="freeze is incomplete"):
        v.validate_receipts(r, m)


@pytest.mark.parametrize("kind", ["packet", "labels_gemini", "labels_grok", "adjudication", "gold"])
@pytest.mark.parametrize("mutation", ["omit", "duplicate", "foreign", "stratum", "old-card"])
def test_all_label_packet_and_gold_rows_bound(graph, kind, mutation):
    m, docs = graph
    rows = docs[kind] if kind == "gold" else docs[kind]["cards" if kind == "packet" else "items"]
    if mutation == "omit": rows.pop()
    if mutation == "duplicate": rows[-1] = copy.deepcopy(rows[0])
    if mutation == "foreign": rows[0]["video_id"] = "foreign"
    if mutation == "stratum": rows[0]["stratum"] = "text_only"
    if mutation == "old-card":
        if kind == "packet": rows[0]["card"] = dict(rows[0]["card"], card_hash="0" * 64)
        else: rows[0]["card_hash"] = "0" * 64
    with pytest.raises(ValueError):
        v.check_stage4_references(m, docs)


@pytest.mark.parametrize("kind,key", [
    ("packet", "bindings_sha256"), ("packet", "stage4_freeze_hash"), ("packet", "card_profile_hash"),
    ("labels_gemini", "packet_sha256"), ("labels_grok", "bindings_sha256"),
    ("adjudication", "taxonomy_revision_hash"), ("mapping", "gold_sha256"),
    ("mapping", "adjudicated_sha256"), ("mapping", "bindings_sha256"), ("mapping", "scoring_version")])
def test_artifact_reference_hashes_and_strict_rule(graph, kind, key):
    m, docs = graph
    docs[kind][key] = "stale"
    with pytest.raises(ValueError):
        v.check_stage4_references(m, docs)


@pytest.mark.parametrize("key,value", [("source_revision", "0" * 64), ("card_hash", "0" * 64), ("stratum", "text_only"),
    ("gold_path", ["invented"]), ("mapped_path", ["AI and ML"]), ("scorable", True)])
def test_mapping_every_reference_and_outcome(graph, key, value):
    m, docs = graph
    next(iter(docs["mapping"]["items"].values()))[key] = value
    with pytest.raises(ValueError):
        v.check_stage4_references(m, docs)


def test_label_quote_must_be_in_one_admissible_excerpt(graph):
    m, docs = graph
    row = docs["labels_gemini"]["items"][0]
    row.update(outcome="assigned", evidence=dict(excerpt_id=m["card_payloads"][row["video_id"]]["excerpts"][0]["excerpt_id"],
                                               quote="invented unsupported quotation"))
    with pytest.raises(ValueError, match="Support quote"):
        v.check_stage4_references(m, docs)


@pytest.fixture
def installed_candidate(tmp_path, candidate, graph, monkeypatch):
    m, docs = graph
    for name, record in m["files"].items():
        dest = tmp_path / record["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(v.canonical(docs[name]).encode("utf-8") if name in docs else (v.ROOT / record["path"]).read_bytes())
    for path in (v.MANIFEST, v.MANIFEST_STAGE3, v.INDUCTION_MANIFEST):
        dest = tmp_path / path.relative_to(v.ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
    monkeypatch.setattr(v, "archived_stage1_heads", lambda root: candidate[3])
    return m, docs, tmp_path


def test_stage4_manifest_end_to_end_all_files(installed_candidate):
    m, _, tmp_path = installed_candidate
    assert v.verify_manifest(m, tmp_path, stage=4) is m
    with pytest.raises(ValueError, match="requested route"):
        v.verify_manifest(m, tmp_path, stage=3)
    # Mutation is deliberately outside the hold-out and probe: every card is checked.
    vid = next(vid for vid in m["card_payloads"] if vid not in m["holdout"]["ids"] + m["probe"]["target_ids"])
    m["card_payloads"][vid]["selection_version"] = "spread-longest-v1"
    with pytest.raises(ValueError, match="wrong card profile"):
        v.verify_manifest(m, tmp_path, stage=4)


@pytest.mark.parametrize("field", ["video_id", "stratum", "source_revision", "old_card_hash", "new_card_hash"])
def test_rehashed_binding_file_cannot_change_either_side(installed_candidate, field):
    m, docs, root = installed_candidate
    docs["bindings"]["strata"]["timed_evidence"][0][field] = "substitution"
    raw = v.canonical(docs["bindings"]).encode("utf-8")
    record = m["files"]["bindings"]
    (root / record["path"]).write_bytes(raw)
    record["sha256"] = v.sha(raw)
    m["hashes"]["implementation_hash"] = v.digest(m["files"])
    with pytest.raises(ValueError, match="bindings changed"):
        v.verify_manifest(m, root, stage=4)


@pytest.mark.parametrize("field", ["source", "items", "corpus_heads", "exclusions"])
def test_stage4_retains_original_source_and_heads(candidate, field):
    m, old, _, _ = copy.deepcopy(candidate)
    if field == "source": m[field]["sha256"] = "0" * 64
    if field == "items": m[field][0][1] = "0" * 64
    if field == "corpus_heads": next(iter(m[field].values()))["raw_sha256"] = "0" * 64
    if field == "exclusions": m[field][m["items"][0][0]] = "dropped"
    with pytest.raises(ValueError, match="differs from stage 1"):
        v.check_stage_continuity(m, old, 4)


@pytest.mark.parametrize("field", ["prompt_sha256", "prompt_file_sha256", "taxonomy_revision"])
def test_stage4_rejects_changed_taxonomy_or_prompt(candidate, field):
    m = copy.deepcopy(candidate[0])
    if field == "taxonomy_revision": m["taxonomy"]["revision_hash"] = "0" * 64
    else: m["hashes"][field] = "0" * 64
    with pytest.raises(ValueError, match="taxonomy/prompt changed"):
        v.verify_stage4_manifest(m)


def test_partial_real_result_has_zero_quality_denominator():
    with proof_fixture() as (r, m):
        r["mode"] = "subscription"
        result = v.validate_receipts(r, m, require_real=True, require_whole_manifest=False)
        assert result["status"] == "PROBE_ONLY_VALID_AUDIT_REQUIRED"
        assert result["whole_manifest_checked"] is False
        assert result["product_proof_pass"] is False and result["measured_quality_items"] == 0


@pytest.mark.parametrize("case", ["sixteen-item-subset", "probe-only-status"])
def test_scorer_refuses_probe_results(tmp_path, candidate, monkeypatch, capsys, case):
    spec = importlib.util.spec_from_file_location("stage4_proof_score", v.ROOT / "scripts/librarian/proof_score.py")
    proof_score = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proof_score)

    with proof_fixture() as (r, m):
        r.update(mode="subscription", target_ids=candidate[0]["probe"]["target_ids"])
        m["items"] = candidate[0]["items"]
        receipt_path, manifest_path = tmp_path / "receipts.json", tmp_path / "manifest.json"
        receipt_path.write_text(v.canonical(r), encoding="utf-8")
        manifest_path.write_text(v.canonical(m), encoding="utf-8")
        monkeypatch.setitem(sys.modules, "validate_proof_receipts", v)
        monkeypatch.setattr(sys, "argv", ["proof_score", "--receipts", str(receipt_path), "--manifest", str(manifest_path)])
        monkeypatch.setattr(v, "verify_manifest", lambda manifest: manifest)
        if case == "probe-only-status":
            monkeypatch.setattr(v, "validate_receipts", lambda *args, **kwargs: dict(
                status="PROBE_ONLY_VALID_AUDIT_REQUIRED", whole_manifest_checked=False, product_proof_pass=False))
        with pytest.raises(SystemExit) as error:
            proof_score.main()
        assert error.value.code == 1
        message = capsys.readouterr().err
        assert ("entire manifest" if case == "sixteen-item-subset" else "not a real validation") in message


def test_historical_fixture_survives_global_v2_builder_version(monkeypatch):
    monkeypatch.setattr(v.library_cards, "SELECTION_VERSION", "spread-longest-v2")
    r, m, *_ = v._legacy_fixture()
    assert v.validate_receipts(r, m)["status"] == "FIXTURE_VALID"


def test_original_binding_both_hashes_and_denominators(candidate):
    m, _, original, _ = candidate
    result = v.stage4_bindings(m, original, v.HOLDOUT_V3_SHA256)
    assert [len(result["strata"][s]) for s in ("timed_evidence", "text_only")] == [47, 13]
    assert all(row["old_card_hash"] != row["new_card_hash"] for rows in result["strata"].values() for row in rows)
    with pytest.raises(ValueError, match="Original v3 freeze hash"):
        v.stage4_bindings(m, original, "0" * 64)
    bad = copy.deepcopy(original)
    bad["strata"]["timed_evidence"].pop()
    with pytest.raises(ValueError, match="denominators"):
        v.stage4_bindings(m, bad, v.HOLDOUT_V3_SHA256)


def test_probe_uses_development_only_and_cannot_replace_full(candidate):
    m, _, original, _ = candidate
    probe = v.stage4_probe(m, v.read_json(v.INDUCTION_MANIFEST), original)
    assert len(set(probe["target_ids"])) == 16
    assert not set(probe["target_ids"]) & set(m["holdout"]["ids"])
    assert sum(m["cards"][vid]["stratum"] == "timed_evidence" for vid in probe["target_ids"]) == 8
    # Actual common API rejects a completed real 16/548 receipt before process checks.
    with proof_fixture() as (r, fixture_manifest):
        r.update(mode="subscription", target_ids=probe["target_ids"])
        fixture_manifest["items"] = m["items"]
        with pytest.raises(ValueError, match="entire manifest"):
            v.validate_receipts(r, fixture_manifest, require_real=True)


def test_probe_delegates_to_real_partial_api_and_reports_no_quality(candidate):
    m = candidate[0]
    r = dict(target_ids=m["probe"]["target_ids"], transport_failures=[],
             attempts=[dict(video_id=vid, attempt_number=1, outcome="unmapped") for vid in m["probe"]["target_ids"]],
             calls=[dict(attempt_ids=list(range(8))), dict(attempt_ids=list(range(8, 16)))])
    with patch.object(v, "validate_receipts", return_value=dict(target_count=16)) as validate:
        result = v.validate_probe_receipts(r, m)
        assert validate.call_args.kwargs["require_real"] is True
        assert validate.call_args.kwargs["require_whole_manifest"] is False
    assert result["whole_manifest_checked"] is False and result["product_proof_pass"] is False
    assert result["probe_only"] is True and result["measured_quality_items"] == 0
    r["attempts"][0]["outcome"] = "rejected"
    with patch.object(v, "validate_receipts", return_value={}), pytest.raises(ValueError, match="zero rejected"):
        v.validate_probe_receipts(r, m)


def test_partial_api_never_waives_mock_or_aborted_or_missing_artifacts():
    with proof_fixture() as (r, m):
        with pytest.raises(ValueError, match="Mock receipts"):
            v.validate_receipts(r, m, require_real=True, require_whole_manifest=False)
        r["mode"] = "subscription"
        r.update(status="aborted", abort_reason="guard")
        with pytest.raises(ValueError, match="Run aborted"):
            v.validate_receipts(r, m, require_real=True, require_whole_manifest=False)
        r.update(status="completed", abort_reason=None)
        r["state_artifacts"].pop("source")
        with pytest.raises(ValidationError):
            v.validate_receipts(r, m, require_real=True, require_whole_manifest=False)


@pytest.mark.parametrize("case", ["anonymous", "linked", "many-linked", "eventual-success", "unfinished", "late"])
def test_guard_v2_failure_identity_and_event_time(case):
    r = guard_fixture({0, 1})
    def event(eid, aid, timestamp):
        return dict(event_id=eid, attempt_id=aid, occurred_monotonic_ns=timestamp)
    if case == "anonymous": r["transport_failures"] = [event("e", None, 19)]
    if case == "linked": r["transport_failures"] = [event("e", "0", 0)]
    if case == "many-linked": r["transport_failures"] = [event("e1", "0", 0), event("e2", "0", 1)]
    if case == "eventual-success": r["transport_failures"] = [event("e", "5", 5)]
    if case == "unfinished": r["transport_failures"] = [event("e", "20", 0)]
    if case == "late": r["transport_failures"] = [event("e", None, 100)]
    if case in {"linked", "many-linked"}:
        v._check_completion_guard(r)
    else:
        with pytest.raises(ValueError, match="completion 21" if case == "unfinished" else "threshold exceeded"):
            v._check_completion_guard(r)


@pytest.mark.parametrize("mutation", ["duplicate", "negative-time", "outside-run", "missing-attempt"])
def test_guard_invalid_events(mutation):
    r = guard_fixture(set())
    e = dict(event_id="event", attempt_id=None, occurred_monotonic_ns=1)
    r["transport_failures"] = [e]
    if mutation == "duplicate": r["transport_failures"].append(dict(e))
    if mutation == "negative-time": e["occurred_monotonic_ns"] = -1
    if mutation == "outside-run": r["execution"] = dict(start_monotonic_ns=2, end_monotonic_ns=30)
    if mutation == "missing-attempt": e["attempt_id"] = "missing"
    with pytest.raises(ValueError):
        v._check_completion_guard(r)


def test_probe_cli_requires_explicit_stage4_real_route(capsys):
    assert v.main(["--probe"]) == 1
    assert "--stage4 --receipts" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        v.main(["--stage3", "--stage4"])

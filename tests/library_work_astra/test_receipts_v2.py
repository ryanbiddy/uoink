"""Synthetic process/HTTP/SQLite archives. No executable client or HTTP is used."""
import copy
import importlib.util
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("astra_receipt_validator", ROOT / "tests/validate_proof_receipts.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def artifact(value, validator=v):
    raw = value if isinstance(value, bytes) else validator.canonical(value).encode("utf-8")
    return validator.inline_artifact(raw)


@contextmanager
def proof_fixture(validator=v):
    r, m, card, result, _ = validator._legacy_fixture()
    a = r["attempts"][0]
    a.update(call_id="call-1", model_result=copy.deepcopy(result), claim_event_id="claim-1", submit_event_ids=["submit-1"])
    r["schema_version"] = 2
    r["targets"][0]["terminal_service_state"] = "accepted"
    r["preview"]["response"]["can_apply"] = False
    envelope = dict(structured_output=dict(results=[dict(video_id=card["video_id"], result=result)]),
                    usage=dict(input_tokens=3, output_tokens=5, cache_read_input_tokens=2, cache_creation_input_tokens=0),
                    modelUsage={"main": {"inputTokens": 3, "costUSD": 0.25}, "auxiliary": {"inputTokens": 7, "costUSD": 0.125}},
                    total_cost_usd=0.375)
    schema = r["config"]["output_schema_text"]
    call = dict(call_id="call-1", attempt_ids=[a["attempt_id"]], argv=["claude", "-p", "--json-schema", schema],
                schema_text=schema, schema_sha256=validator.sha(schema.encode()),
                stdin=artifact(a["prompt_text"].encode(), validator), stdout=artifact(envelope, validator), stderr=artifact(b"", validator),
                start_monotonic_ns=1_000_000, end_monotonic_ns=6_000_000, exit_status=0, timed_out=False, cancellation=None,
                usage=envelope["usage"], modelUsage=envelope["modelUsage"], cli_estimated_cost_usd=envelope["total_cost_usd"])
    r["calls"] = [call]
    r["completion_order"] = [dict(attempt_id=a["attempt_id"], completed_monotonic_ns=7_000_000)]
    r["totals"].update(model_calls=1, item_attempts=1, schema_bytes=len(schema.encode()), stderr_bytes=0,
                        response_bytes=call["stdout"]["bytes"])
    r["accounting"] = validator.call_accounting(r["calls"])
    fingerprints = {k: artifact(k.encode(), validator) for k in ("runner", "scorer", "validator", "service")}
    fingerprints["prompt"] = artifact((ROOT / m["files"]["prompt"]["path"]).read_bytes(), validator)
    fingerprints["card_builder"] = artifact((ROOT / "library_cards.py").read_bytes(), validator)
    for name, key in [("prompt", "prompt_file_sha256"), ("card_builder", "card_builder_sha256")]:
        m["hashes"][key] = fingerprints[name]["sha256"]
    r["execution"] = dict(checkout_root=str(ROOT), git_sha="a" * 40, start_monotonic_ns=0, end_monotonic_ns=10_000_000,
                          fingerprints=fingerprints, cleanup=dict(owned_processes_remaining=0, helper_stopped=True, errors=[]))

    def http(eid, op, request, response, start):
        return dict(event_id=eid, operation=op,
                    request=artifact(dict(method="POST", url="http://127.0.0.1:5180/" + op,
                        headers={"Authorization": "[REDACTED]"}, body=request), validator),
                    response=artifact(dict(headers={}, body=response), validator),
                    status_code=200, error=None, start_monotonic_ns=start, end_monotonic_ns=start + 1_000_000, resend_of=None)
    r["http_history"] = [
        http("claim-1", "claim", {}, dict(work=[dict(work_id=a["work_id"], video_id=a["video_id"], attempt_token="[REDACTED]")]), 0),
        http("submit-1", "submit", dict(work_id=a["work_id"], video_id=a["video_id"], result=a["result"]), a["submit_response"], 6_000_000),
        http("preview-1", "preview", r["preview"]["request"], r["preview"]["response"], 8_000_000)]
    registry = dict(
        library_work=[dict(work_id="w", run_id=r["run_id"], video_id=a["video_id"], state="accepted")],
        library_attempts=[dict(attempt_token=a["attempt_token"], work_id="w", attempt_number=1, state="submitted")],
        library_submissions=[dict(submission_key="s", attempt_token=a["attempt_token"], result_json=validator.canonical(a["result"]), response_json=validator.canonical(a["submit_response"]))],
        library_proposals=[dict(run_id=r["run_id"], video_id=a["video_id"], shelf_id=result["memberships"][0]["shelf_id"], submission_key="s", is_primary=1,
            confidence=result["memberships"][0]["confidence"], version_id=m["taxonomy"]["version_id"],
            evidence_json=validator.canonical(dict(result["memberships"][0]["evidence"], **{k: card["excerpts"][0][k] for k in ("start", "end", "timing", "truncated")})))],
        library_manifest=[dict(run_id=r["run_id"], video_id=a["video_id"])])
    with sqlite3.connect(":memory:") as conn:
        conn.executescript("""
            CREATE TABLE library_meta(singleton, projection_revision, active_version_id);
            CREATE TABLE schema_version(version);
            INSERT INTO schema_version VALUES(26);
            CREATE TABLE shelf_versions(version_id, revision_hash);
            CREATE TABLE item_shelves(video_id, shelf_id, locked);
            CREATE TABLE library_item_policy(video_id, exclusive_move);
            CREATE TABLE library_applies(apply_id);
            CREATE TABLE library_work(work_id,run_id,video_id,state);
            CREATE TABLE library_attempts(attempt_token,work_id,attempt_number,state);
            CREATE TABLE library_submissions(submission_key,attempt_token,result_json,response_json);
            CREATE TABLE library_proposals(run_id,video_id,shelf_id,submission_key,is_primary,confidence,version_id,evidence_json);
            CREATE TABLE library_manifest(run_id,video_id);
        """)
        conn.execute("INSERT INTO library_meta VALUES(1,0,?)", (r["before"]["active_version_id"],))
        conn.execute("INSERT INTO shelf_versions VALUES(?,?)", (r["before"]["active_version_id"], r["before"]["taxonomy_revision_hash"]))
        before = conn.serialize()
        for table, rows in registry.items():
            for row in rows:
                conn.execute(f"INSERT INTO {table} VALUES({','.join('?' for _ in row)})", tuple(row.values()))
        after = conn.serialize()
    source_hash = validator.sha(before)
    r["database"].update(copy_before_upgrade_sha256=source_hash, source_after_sha256=source_hash,
                          copy_after_upgrade_sha256=source_hash, schema_before=26, schema_after=26)
    m["hashes"]["source_sha256"] = source_hash
    head = artifact(b"synthetic head", validator)
    m["corpus_heads"] = {card["video_id"]: dict(raw_sha256=head["sha256"])}
    r["state_artifacts"] = {k: artifact(value, validator) for k, value in dict(
        registry=registry, before_snapshot=r["before"], after_snapshot=r["after"], before_db=before, after_db=after,
        apply_journal=dict(entries=[]), source=before, upgraded=before, corpus_heads={card["video_id"]: head}).items()}
    with patch.object(validator, "SOURCE_SHA256", source_hash):
        yield r, m


def mutation_cases():
    return [
        ("missing calls", lambda r: r.update(calls=[])),
        ("duplicate call", lambda r: r["calls"].append(copy.deepcopy(r["calls"][0]))),
        ("call linkage", lambda r: r["attempts"][0].update(call_id="other")),
        ("ordered attempt ids", lambda r: r["calls"][0].update(attempt_ids=["unknown"])),
        ("argv", lambda r: r["calls"][0].update(argv=["claude", "-p"])),
        ("schema hash", lambda r: r["calls"][0].update(schema_sha256="0" * 64)),
        ("stdout bytes", lambda r: r["calls"][0]["stdout"].update(bytes=1)),
        ("stderr hash", lambda r: r["calls"][0]["stderr"].update(sha256="0" * 64)),
        ("modified batch", lambda r: r["calls"][0].update(stdin=artifact(b"other input"))),
        ("monotonic clock", lambda r: r["calls"][0].update(end_monotonic_ns=0)),
        ("exit missing", lambda r: r["calls"][0].update(exit_status=None)),
        ("timeout success", lambda r: r["calls"][0].update(timed_out=True)),
        ("cancellation success", lambda r: r["calls"][0].update(cancellation="cancelled")),
        ("original output", lambda r: r["attempts"][0].update(model_result=dict(outcome="unsupported"))),
        ("modelUsage omitted model", lambda r: r["calls"][0]["modelUsage"].pop("auxiliary")),
        ("usage invented", lambda r: r["calls"][0]["usage"].update(input_tokens=99)),
        ("cost invented", lambda r: r["calls"][0].update(cli_estimated_cost_usd=0)),
        ("paid invoice absent", lambda r: r["accounting"].update(paid_cost_usd=0)),
        ("process count", lambda r: r["totals"].update(model_calls=2)),
        ("attempt count", lambda r: r["totals"].update(item_attempts=2)),
        ("batch schema bytes", lambda r: r["totals"].update(schema_bytes=0)),
        ("batch stdout bytes", lambda r: r["totals"].update(response_bytes=0)),
        ("missing completion", lambda r: r.update(completion_order=[])),
        ("completion before exit", lambda r: r["completion_order"][0].update(completed_monotonic_ns=0)),
        ("run timeline", lambda r: r["execution"].update(end_monotonic_ns=9_000_000)),
        ("helper not stopped", lambda r: r["execution"]["cleanup"].update(helper_stopped=False)),
        ("cleanup failure", lambda r: r["execution"]["cleanup"]["errors"].append("terminate failed")),
        ("fingerprint omitted", lambda r: r["execution"]["fingerprints"].pop("service")),
        ("missing HTTP history", lambda r: r.update(http_history=[])),
        ("missing submit history", lambda r: r["attempts"][0].update(submit_event_ids=[])),
        ("resend mismatch", lambda r: r["http_history"][1].update(resend_of="claim-1")),
        ("missing registry", lambda r: r["state_artifacts"].pop("registry")),
        ("invented registry", lambda r: r["state_artifacts"].update(registry=artifact({}))),
        ("missing source", lambda r: r["state_artifacts"].pop("source")),
        ("modified source", lambda r: r["state_artifacts"].update(source=artifact(b"modified"))),
        ("missing corpus", lambda r: r["state_artifacts"].update(corpus_heads=artifact({}))),
        ("missing DB", lambda r: r["state_artifacts"].update(after_db=artifact(b"SQLite format 3\0"))),
        ("state snapshot mismatch", lambda r: r["state_artifacts"].update(before_snapshot=artifact({}))),
        ("journal apply", lambda r: r["state_artifacts"].update(apply_journal=artifact(dict(entries=[dict(kind="apply")])))),
        ("model/service state conflated", lambda r: r["targets"][0].update(terminal_service_state="cancelled")),
        ("preview applies", lambda r: r["preview"]["response"].update(can_apply=True)),
    ]


@pytest.mark.parametrize("label,mutate", mutation_cases(), ids=[case[0] for case in mutation_cases()])
def test_v2_negative_rules(label, mutate):
    with proof_fixture() as (r, m):
        mutate(r)
        with pytest.raises((ValueError, KeyError, TypeError, sqlite3.DatabaseError, ValidationError)):
            v.validate_receipts(r, m)


def test_v2_positive_and_portable_without_historical_reads():
    with proof_fixture() as (r, m):
        assert v.validate_receipts(r, m)["status"] == "FIXTURE_VALID"
        root = "Z:/nonexistent/historical/checkout"
        isolated = root + "/_scratch/proof/run"
        r["execution"]["checkout_root"] = root
        r["config"].update(isolation_root=isolated, index_path=isolated + "/Uoink/index.db", token_path=isolated + "/token")
        r["config"]["environment"] = {key: isolated for key in r["config"]["environment"]}
        assert v.validate_receipts(r, m)["status"] == "FIXTURE_VALID"
        r["config"]["environment"]["TEMP"] = isolated + "/../outside"
        with pytest.raises(ValueError, match="escapes"):
            v.validate_receipts(r, m)


def test_mock_and_legacy_cannot_establish_measured_proof():
    r, m, *_ = v._legacy_fixture()
    r["mode"] = "subscription"
    with pytest.raises(ValueError, match="schema_version 2"):
        v.validate_receipts(r, m, require_real=True)
    with proof_fixture() as (r, m):
        with pytest.raises(ValueError, match="Mock receipts"):
            v.validate_receipts(r, m, require_real=True)


def test_usage_keeps_missing_counters_unavailable():
    with proof_fixture() as (r, m):
        c = r["calls"][0]
        c["usage"] = {"output_tokens": 5}
        envelope = v.decode_json(v.artifact_bytes(c["stdout"], ROOT))
        envelope["usage"] = c["usage"]
        c["stdout"] = artifact(envelope)
        r["totals"]["response_bytes"] = c["stdout"]["bytes"]
        r["accounting"] = v.call_accounting(r["calls"])
        assert r["accounting"]["counters"]["input_tokens"] is None
        assert r["accounting"]["counters"]["output_tokens"] == 5
        assert v.validate_receipts(r, m)["status"] == "FIXTURE_VALID"


def guard_fixture(rejected):
    return dict(attempts=[dict(attempt_id=str(i), call_id="call", outcome="rejected" if i in rejected else "accepted") for i in range(21)],
                calls=[dict(call_id="call", end_monotonic_ns=0)], transport_failures=[],
                completion_order=[dict(attempt_id=str(i), completed_monotonic_ns=i) for i in range(21)])


def test_guard_equality_first_breach_and_interleaved_order():
    r = guard_fixture({0, 1})
    v._check_completion_guard(r)  # 2/20 = 10% is allowed.
    r["attempts"][20]["outcome"] = "rejected"
    with pytest.raises(ValueError, match="completion 21: 3/21"):
        v._check_completion_guard(r)
    r = guard_fixture({0, 1, 19})
    with pytest.raises(ValueError, match="completion 20: 3/20"):
        v._check_completion_guard(r)
    r = guard_fixture({0, 1})
    r["transport_failures"] = [dict(attempt_id="5", occurred_monotonic_ns=5)]
    with pytest.raises(ValueError, match="completion 20: 3/20"):
        v._check_completion_guard(r)
    r = guard_fixture({0, 1, 20})
    r["completion_order"][19]["attempt_id"], r["completion_order"][20]["attempt_id"] = "20", "19"
    with pytest.raises(ValueError, match="completion 20: 3/20"):
        v._check_completion_guard(r)


def test_artifact_escape_and_http_redaction(tmp_path):
    record = dict(path="../outside", sha256="a" * 64, bytes=0)
    with pytest.raises(ValueError, match="portable"):
        v.artifact_bytes(record, tmp_path)
    with proof_fixture() as (r, m):
        req = v.decode_json(v.artifact_bytes(r["http_history"][0]["request"], ROOT))
        req["headers"]["Authorization"] = "Bearer synthetic-secret"
        r["http_history"][0]["request"] = artifact(req)
        with pytest.raises(ValueError, match="unredacted secret"):
            v.validate_receipts(r, m)


def run_offline_checks(validator):
    """Called by --self-test; synthetic v2 archives also cover every negative rule."""
    from jsonschema.exceptions import ValidationError
    with proof_fixture(validator) as (r, m):
        validator.validate_receipts(r, m)
        count = 1
        for label, mutate in mutation_cases():
            altered = copy.deepcopy(r)
            mutate(altered)
            try:
                validator.validate_receipts(altered, m)
            except (ValueError, KeyError, TypeError, sqlite3.DatabaseError, ValidationError):
                count += 1
            else:
                raise AssertionError("Negative v2 fixture accepted: " + label)
    return count

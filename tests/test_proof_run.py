"""
tests/test_proof_run.py - Unit and End-to-End Tests for Living Library Proof Harness (Run P)

Exercises:
1. Refusal to start if ANTHROPIC_API_KEY is set.
2. Refusal to target port 5179 (live helper port).
3. End-to-end mock execution (--mock --limit 12) on an isolated fixture copy in tmp_path
   with the helper running on an ephemeral port.
4. Receipts schema and before/after invariant assertions (projection revision, pins, zero applies).
5. Scorer precision, coverage, and report.md generation on fixture receipts.
"""
from __future__ import annotations

from collections import Counter
import copy
import json
import os
import shutil
import socket
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "librarian"))

import index as index_mod
import proof_run
import proof_score
from proof_run import (
    FORBIDDEN_PORT,
    GUARD_RULE_V2,
    ProofHarness,
    ProofRunError,
    find_free_port,
)
from proof_score import (
    COVERAGE_FLOOR,
    MAX_QUOTE_WORDS,
    PRECISION_TARGET,
    ProofScoreError,
    render_report_markdown,
    score_receipts,
)


@pytest.fixture
def tmp_path():
    """Isolated temporary directory inside worktree avoiding Windows pytest basetemp permissions."""
    import secrets
    p = ROOT / "_scratch" / "test_tmp" / f"case_{secrets.token_hex(4)}"
    p.mkdir(parents=True, exist_ok=True)
    try:
        yield p
    finally:
        shutil.rmtree(p, ignore_errors=True)


@pytest.fixture
def clean_env(monkeypatch):
    """Ensures ANTHROPIC_API_KEY is removed and NO_PROXY includes loopback."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


def run_harness_subprocess(
    *, source, out_dir, limit, concurrency, port, scratch_dir, run_id, mock_reject_count: int = 0
):
    """Run the harness as its own interpreter, the way the orchestrator runs it.
    In-process execution is only valid in a fresh interpreter: once another test
    has imported `server` against the real data root, the in-thread helper
    cannot be re-pointed, so the full suite must not run it in-process."""
    import os
    import subprocess
    import sys
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "librarian" / "proof_run.py"),
        "--source", str(source),
        "--out", str(out_dir),
        "--mock",
        "--limit", str(limit),
        "--concurrency", str(concurrency),
        "--port", str(port),
        "--scratch", str(scratch_dir),
        "--run-id", run_id,
        "--skip-hash-check",
    ]
    if mock_reject_count > 0:
        cmd += ["--mock-reject-count", str(mock_reject_count)]
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env["PYTHONPATH"] = str(ROOT)
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        cwd=str(ROOT),
        env=env,
    )
    assert res.returncode == 0, (res.stdout[-2000:], res.stderr[-2000:])
    receipts_path = Path(out_dir) / "receipts.json"
    assert receipts_path.is_file(), res.stdout[-1000:]
    return receipts_path


def test_refusal_when_anthropic_api_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-paid-api-key-test")
    dummy_source = tmp_path / "dummy.db"
    dummy_source.write_bytes(b"SQLite format 3\x00")
    harness = ProofHarness(
        source=dummy_source,
        out_dir=tmp_path / "out",
        port=5182,
        skip_hash_check=True,
    )
    with pytest.raises(ProofRunError, match="ANTHROPIC_API_KEY is present"):
        harness.check_guards()


def test_refusal_when_port_5179_targeted(tmp_path, clean_env):
    dummy_source = tmp_path / "dummy.db"
    dummy_source.write_bytes(b"SQLite format 3\x00")
    harness = ProofHarness(
        source=dummy_source,
        out_dir=tmp_path / "out",
        port=FORBIDDEN_PORT,
        skip_hash_check=True,
    )
    with pytest.raises(ProofRunError, match=r"Refusing to target port 5179"):
        harness.check_guards()


def create_fixture_database(db_path: Path, n_items: int = 12) -> None:
    """Creates a realistic test database populated with items from manifest and gold-set."""
    gold_path = ROOT / "docs" / "library" / "gold-set-2026-09-04.json"
    gold_items = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.is_file() else []
    gold_by_id = {g["video_id"]: g for g in gold_items}

    manifest_path = ROOT / "docs" / "library" / "proof" / "manifest-2026-09-05.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    manifest_ids = [entry[0] for entry in manifest_data.get("items", [])]

    # Pick up to n_items targets that exist in the manifest
    selected_ids = [g["video_id"] for g in gold_items if g["video_id"] in set(manifest_ids)]
    chosen = selected_ids[:max(0, n_items - 2)]
    non_gold = [vid for vid in manifest_ids if vid not in gold_by_id]
    chosen.extend(non_gold[:(n_items - len(chosen))])

    idx = index_mod.Index.open(db_path)
    for vid in chosen:
        g = gold_by_id.get(vid, {})
        slug = g.get("slug", vid)
        title = g.get("title", f"Title {vid}")
        channel = g.get("channel", "Test Channel")
        platform = g.get("platform", "youtube")
        card = g.get("card") or manifest_data.get("cards", {}).get(vid, {}).get("card") or {}
        clips = card.get("clips") or []

        idx.upsert_yoink(
            {
                "video_id": vid,
                "slug": slug,
                "title": title,
                "channel": channel,
                "platform": platform,
                "topic": "Uncategorized",
                "yoinked_at": "2026-09-04T00:00:00Z",
                "corpus_path": "",
                "sidecar_path": "",
            }
        )
        with idx.write_transaction() as conn:
            for i, c in enumerate(clips[:4]):
                conn.execute(
                    "INSERT INTO clips(video_id,seq,start,end,text) VALUES(?,?,?,?,?)",
                    (vid, i, c.get("start", 0), c.get("end", 10), c.get("text", "Sample clip text.")),
                )
            if not clips:
                conn.execute(
                    "INSERT INTO clips(video_id,seq,start,end,text) VALUES(?,?,?,?,?)",
                    (vid, 0, 0, 10, "Default clip content."),
                )

    idx.close()


def test_mock_run_end_to_end(tmp_path, clean_env):
    """End-to-end verification of --mock --limit 12 on an ephemeral port."""
    fixture_db = tmp_path / "source_copy.db"
    create_fixture_database(fixture_db, n_items=12)

    ephemeral_port = find_free_port()
    out_dir = tmp_path / "proof_out"

    receipts_path = run_harness_subprocess(
        source=fixture_db, out_dir=out_dir, limit=12, concurrency=2,
        port=ephemeral_port, scratch_dir=tmp_path / "scratch",
        run_id="test-run-p-mock")
    assert receipts_path.is_file()

    # Load and verify receipts document
    receipts_data = json.loads(receipts_path.read_text(encoding="utf-8"))

    assert receipts_data["schema_version"] == 2  # v2 receipt contract (STAGE2-GATE)
    assert receipts_data["contract_version"] == "phase2-v1.2-2026-09-04"
    assert receipts_data["run_id"] == "test-run-p-mock"
    assert receipts_data["mode"] == "mock"
    assert receipts_data["status"] == "completed"
    assert receipts_data["abort_reason"] is None
    assert receipts_data["config"]["guard_rule"]["identifier"] == "distinct-failed-completions-v2"
    assert receipts_data["config"]["guard_rule"]["amendment"] == "AO-G1"
    assert receipts_data["audit_extensions"]["card_profile"]["selection_version"] == "spread-longest-v1"
    identity = receipts_data["audit_extensions"]["execution_identity"]
    assert identity["launch"]["git_sha"]
    assert identity["finish"]["git_sha"]
    assert {e["attempt_id"] for e in receipts_data["completion_order"]} == {
        a["attempt_id"] for a in receipts_data["attempts"]
    }
    assert str(ephemeral_port) in receipts_data["config"]["base_url"]
    assert str(FORBIDDEN_PORT) not in receipts_data["config"]["base_url"]

    totals = receipts_data["totals"]
    assert totals["serialized_input_bytes"] > 0
    assert totals["card_bytes"] > 0
    assert totals["prompt_bytes"] > 0
    assert totals["response_bytes"] > 0
    assert totals["wall_ms"] >= 0

    assert len(receipts_data["targets"]) == 12

    # Invariant assertions: zero applies, projection revision preserved
    before = receipts_data["before"]
    after = receipts_data["after"]
    assert before == after
    assert before["applied_label_count"] == 0
    assert after["applied_label_count"] == 0

    # Reshelving preview returned preview request and response
    preview = receipts_data["preview"]
    assert "request" in preview
    assert "response" in preview
    assert preview["request"].get("mode") == "preview"
    assert preview["request"].get("activate_version") is False

    # Check per-attempt receipt records
    attempt_list = receipts_data["attempts"]
    assert len(attempt_list) == 12

    outcomes = Counter(r["outcome"] for r in attempt_list)
    assert outcomes["accepted"] >= 5
    assert outcomes["unmapped"] >= 1

    for r in attempt_list:
        assert "work_id" in r
        assert "video_id" in r
        assert "attempt_token" in r
        assert "packet_hash" in r
        assert r["card_bytes"] > 0
        assert r["prompt_bytes"] > 0
        assert r["response_bytes"] > 0
        assert r["serialized_input_bytes"] > 0
        assert r["wall_ms"] >= 0
        assert r["outcome"] in {"accepted", "unmapped", "unsupported", "rejected"}
        if r["outcome"] == "accepted":
            res = r["result"]
            assert res is not None
            mem = res["memberships"][0]
            ev = mem["evidence"]
            assert ev["basis"] == "packet"
            assert ev["quote"] is not None
            assert len(ev["quote"].split()) <= 24

    # Verify directory structure per contract: calls/, http/, state/
    calls_dir = out_dir / "calls"
    assert calls_dir.is_dir()

    http_dir = out_dir / "http"
    assert http_dir.is_dir()
    http_files = list(http_dir.glob("*.json"))
    assert len(http_files) > 0
    for hf in http_files:
        text = hf.read_text(encoding="utf-8")
        if "X-Uoink-Token" in text:
            assert "[REDACTED]" in text

    state_dir = out_dir / "state"
    assert state_dir.is_dir()
    assert (state_dir / "before_index.db").is_file()
    assert (state_dir / "after_index.db").is_file()
    assert (state_dir / "registry_export.json").is_file()
    assert (state_dir / "work.json").is_file()
    assert (state_dir / "attempts.json").is_file()
    assert (state_dir / "submissions.json").is_file()
    assert (state_dir / "proposals.json").is_file()


def test_scorer_on_fixture_receipts(tmp_path, clean_env):
    """Tests proof_score.py logic and report.md generation."""
    fixture_db = tmp_path / "source_copy.db"
    create_fixture_database(fixture_db, n_items=12)

    ephemeral_port = find_free_port()
    out_dir = tmp_path / "proof_out"

    receipts_path = run_harness_subprocess(
        source=fixture_db, out_dir=out_dir, limit=12, concurrency=1,
        port=ephemeral_port, scratch_dir=tmp_path / "scratch",
        run_id="test-run-scorer")
    receipts_data = json.loads(receipts_path.read_text(encoding="utf-8"))

    holdout_path = ROOT / "docs" / "library" / "holdout-split-2026-09-04.json"
    holdout_data = json.loads(holdout_path.read_text(encoding="utf-8"))

    gold_path = ROOT / "docs" / "library" / "gold-set-2026-09-04.json"
    gold_data = json.loads(gold_path.read_text(encoding="utf-8"))

    score_res = score_receipts(receipts_data, holdout_data, gold_data)

    # Scorer data checks
    assert "strata" in score_res
    assert "overall" in score_res
    assert "usage" in score_res

    assert score_res["zero_applies_verified"] is True
    assert score_res["usage"]["is_measured"] is False
    assert "unmeasured" in score_res["usage"]["status"]

    report_md = render_report_markdown(score_res, receipts_data)
    assert "# Living Library Product Proof Report" in report_md
    assert "Accuracy & Coverage Thresholds" in report_md
    assert "Never prints PASS from an estimate" in report_md
    assert "Zero applied labels after run" in report_md

    report_file = out_dir / "report.md"
    report_file.write_text(report_md, encoding="utf-8")
    assert report_file.is_file()


def test_error_guard_breach_stops_and_records_partial_receipts(tmp_path, clean_env):
    """Verifies that an error rate > 10% after 20 attempts triggers the error guard, stops launching, and writes partial receipts."""
    fixture_db = tmp_path / "source_copy.db"
    create_fixture_database(fixture_db, n_items=25)

    ephemeral_port = find_free_port()
    out_dir = tmp_path / "proof_out_guard"

    receipts_path = run_harness_subprocess(
        source=fixture_db,
        out_dir=out_dir,
        limit=20,
        concurrency=1,
        port=ephemeral_port,
        scratch_dir=tmp_path / "scratch_guard",
        run_id="test-run-guard-breach",
        mock_reject_count=3,
    )
    assert receipts_path.is_file()
    receipts_data = json.loads(receipts_path.read_text(encoding="utf-8"))

    assert receipts_data["status"] == "aborted"
    assert receipts_data["abort_reason"] is not None
    assert "Error rate limit exceeded" in receipts_data["abort_reason"]
    assert "distinct-failed-completions-v2" in receipts_data["abort_reason"]
    # Abort at N>=20 must still retain already-claimed in-flight work (stage 3 run 1
    # dropped 28 completion rows). Attempts may therefore exceed 20.
    assert len(receipts_data["attempts"]) >= 20
    assert len(receipts_data["completion_order"]) == len(receipts_data["attempts"])
    assert {e["attempt_id"] for e in receipts_data["completion_order"]} == {
        a["attempt_id"] for a in receipts_data["attempts"]
    }
    assert receipts_data["totals"]["rejected_attempts"] == 3

    state_dir = out_dir / "state"
    assert (state_dir / "before_index.db").is_file()
    assert (state_dir / "after_index.db").is_file()
    assert (state_dir / "registry_export.json").is_file()


def test_proof_score_rejects_25_word_quote(tmp_path, clean_env):
    """Pre-scoring check must reject quotes exceeding 24 words."""
    fixture_db = tmp_path / "source_copy.db"
    create_fixture_database(fixture_db, n_items=12)

    receipts_path = run_harness_subprocess(
        source=fixture_db, out_dir=tmp_path / "out", limit=12, concurrency=1,
        port=find_free_port(), scratch_dir=tmp_path / "scratch",
        run_id="test-score-25w")
    receipts_data = json.loads(receipts_path.read_text(encoding="utf-8"))

    # Make one accepted attempt have a 25-word quote
    for a in receipts_data["attempts"]:
        if a["outcome"] == "accepted":
            a["result"]["memberships"][0]["evidence"]["quote"] = "word " * 25
            break

    holdout_data = json.loads((ROOT / "docs" / "library" / "holdout-split-2026-09-04.json").read_text(encoding="utf-8"))
    gold_data = json.loads((ROOT / "docs" / "library" / "gold-set-2026-09-04.json").read_text(encoding="utf-8"))

    with pytest.raises(ProofScoreError, match="Quote exceeds 24-word cap"):
        score_receipts(receipts_data, holdout_data, gold_data)


def test_proof_score_rejects_foreign_card(tmp_path, clean_env):
    """Pre-scoring check must reject attempts referencing cards outside target_ids."""
    fixture_db = tmp_path / "source_copy.db"
    create_fixture_database(fixture_db, n_items=12)

    receipts_path = run_harness_subprocess(
        source=fixture_db, out_dir=tmp_path / "out", limit=12, concurrency=1,
        port=find_free_port(), scratch_dir=tmp_path / "scratch",
        run_id="test-score-foreign")
    receipts_data = json.loads(receipts_path.read_text(encoding="utf-8"))

    foreign_attempt = copy.deepcopy(receipts_data["attempts"][0])
    foreign_attempt["video_id"] = "foreign-unmanifested-video-999"
    foreign_attempt["attempt_id"] = "att-foreign-999-1"
    receipts_data["attempts"].append(foreign_attempt)

    holdout_data = json.loads((ROOT / "docs" / "library" / "holdout-split-2026-09-04.json").read_text(encoding="utf-8"))
    gold_data = json.loads((ROOT / "docs" / "library" / "gold-set-2026-09-04.json").read_text(encoding="utf-8"))

    with pytest.raises(ProofScoreError, match="Foreign card detected"):
        score_receipts(receipts_data, holdout_data, gold_data)


def test_proof_score_rejects_missing_source_hash(tmp_path, clean_env):
    """Pre-scoring check must reject missing source hash."""
    fixture_db = tmp_path / "source_copy.db"
    create_fixture_database(fixture_db, n_items=12)

    receipts_path = run_harness_subprocess(
        source=fixture_db, out_dir=tmp_path / "out", limit=12, concurrency=1,
        port=find_free_port(), scratch_dir=tmp_path / "scratch",
        run_id="test-score-nosrc")
    receipts_data = json.loads(receipts_path.read_text(encoding="utf-8"))

    receipts_data["database"]["copy_before_upgrade_sha256"] = ""
    receipts_data["inputs"]["source_sha256"] = ""

    holdout_data = json.loads((ROOT / "docs" / "library" / "holdout-split-2026-09-04.json").read_text(encoding="utf-8"))
    gold_data = json.loads((ROOT / "docs" / "library" / "gold-set-2026-09-04.json").read_text(encoding="utf-8"))

    with pytest.raises(ProofScoreError, match="Missing or invalid source database SHA-256"):
        score_receipts(receipts_data, holdout_data, gold_data)


def test_proof_score_rejects_modified_batch(tmp_path, clean_env):
    """Pre-scoring check must reject attempt referencing an unrecorded call or unlisted video in call."""
    fixture_db = tmp_path / "source_copy.db"
    create_fixture_database(fixture_db, n_items=12)

    receipts_path = run_harness_subprocess(
        source=fixture_db, out_dir=tmp_path / "out", limit=12, concurrency=1,
        port=find_free_port(), scratch_dir=tmp_path / "scratch",
        run_id="test-score-batch")
    receipts_data = json.loads(receipts_path.read_text(encoding="utf-8"))

    valid_vid = receipts_data["attempts"][0]["video_id"]
    receipts_data["audit_extensions"]["calls"] = [
        {"call_id": "call-0001", "video_ids": ["other-video-id"]}
    ]
    receipts_data["attempts"][0]["call_id"] = "call-0001"
    # Keep receipts_data["attempts"][0]["video_id"] as valid_vid

    holdout_data = json.loads((ROOT / "docs" / "library" / "holdout-split-2026-09-04.json").read_text(encoding="utf-8"))
    gold_data = json.loads((ROOT / "docs" / "library" / "gold-set-2026-09-04.json").read_text(encoding="utf-8"))

    with pytest.raises(ProofScoreError, match="Modified batch"):
        score_receipts(receipts_data, holdout_data, gold_data)


def test_proof_score_rejects_invented_usage(tmp_path, clean_env):
    """Pre-scoring check must reject invented usage in mock mode."""
    fixture_db = tmp_path / "source_copy.db"
    create_fixture_database(fixture_db, n_items=12)

    receipts_path = run_harness_subprocess(
        source=fixture_db, out_dir=tmp_path / "out", limit=12, concurrency=1,
        port=find_free_port(), scratch_dir=tmp_path / "scratch",
        run_id="test-score-usage")
    receipts_data = json.loads(receipts_path.read_text(encoding="utf-8"))

    # In mock mode, pretend tokens were consumed
    receipts_data["attempts"][0]["usage"] = {
        "status": "reported",
        "model": "claude-sonnet-5",
        "input_tokens": 120,
    }

    holdout_data = json.loads((ROOT / "docs" / "library" / "holdout-split-2026-09-04.json").read_text(encoding="utf-8"))
    gold_data = json.loads((ROOT / "docs" / "library" / "gold-set-2026-09-04.json").read_text(encoding="utf-8"))

    with pytest.raises(ProofScoreError, match="Invented usage detected"):
        score_receipts(receipts_data, holdout_data, gold_data)


def _guard_probe(n, bad=0, anon=0, linked=0, extra_events=None, completion_order=None, n_min=20):
    """Isolated AO-style probe of ProofHarness._check_error_guard. No helper or model."""
    attempts = [
        dict(attempt_id=str(i), call_id="c", outcome="rejected" if i < bad else "accepted")
        for i in range(n)
    ]
    events = [dict(event_id=f"linked-{i}", attempt_id=str(i), occurred_monotonic_ns=1) for i in range(linked)]
    events += [dict(event_id=f"anon-{i}", attempt_id=None, occurred_monotonic_ns=1) for i in range(anon)]
    if extra_events:
        events.extend(extra_events)
    if completion_order is None:
        completion_order = [dict(attempt_id=str(i), completed_monotonic_ns=i + 2) for i in range(n)]
    stop = []
    stub = SimpleNamespace(
        _coordinator_lock=threading.RLock(),
        abort_event=threading.Event(),
        run_start_time=time.perf_counter(),
        wall_budget_ms=7_200_000,
        attempts=attempts,
        transport_failures=events,
        error_rate_min_attempts=n_min,
        completion_order=completion_order,
        _trigger_abort=stop.append,
    )
    ProofHarness._check_error_guard(stub)
    return stop, attempts, events


def test_guard_below_minimum_does_not_abort():
    stop, _, _ = _guard_probe(19, bad=3, linked=3)
    assert stop == []


def test_guard_exact_ten_percent_allowed():
    """2/20 with linked rejection/event duplication is exact 10%; equality is allowed."""
    stop, _, _ = _guard_probe(20, bad=2, linked=2)
    assert stop == []


def test_guard_first_strict_excess_aborts():
    stop, _, _ = _guard_probe(20, bad=3, linked=3)
    assert stop and "3/20" in stop[0]


def test_guard_linked_rejection_event_not_double_counted():
    """A rejected attempt plus its transport event is one failed completion."""
    stop, _, _ = _guard_probe(20, bad=2, linked=2)
    assert stop == []
    stop, _, _ = _guard_probe(20, bad=3, linked=3)
    assert stop


def test_guard_multiple_events_on_one_attempt_count_once():
    extra = [
        dict(event_id="multi-a", attempt_id="0", occurred_monotonic_ns=1),
        dict(event_id="multi-b", attempt_id="0", occurred_monotonic_ns=1),
    ]
    # 19 accepted + attempt 0 accepted with two events => one failed completion; 1/20 no abort
    stop, _, _ = _guard_probe(20, bad=0, linked=0, extra_events=extra)
    assert stop == []
    extra.append(dict(event_id="multi-c", attempt_id="1", occurred_monotonic_ns=1))
    extra.append(dict(event_id="multi-d", attempt_id="2", occurred_monotonic_ns=1))
    stop, _, _ = _guard_probe(20, bad=0, linked=0, extra_events=extra)
    assert stop and "3/20" in stop[0]


def test_guard_successful_submit_after_transport_failure_still_counts():
    """Accepted outcome with a linked transport event is a failed completion (AO probe)."""
    stop, _, _ = _guard_probe(20, bad=0, linked=3)
    assert stop and "3/20" in stop[0]


def test_guard_anonymous_events_count_once_ao_g1():
    """AO-G1: 20 successes + 3 anonymous events abort. Unique event_id counted once."""
    stop, _, _ = _guard_probe(20, bad=0, anon=3)
    assert stop and "3/20" in stop[0]
    extra = [
        dict(event_id="dup-anon", attempt_id=None, occurred_monotonic_ns=1),
        dict(event_id="dup-anon", attempt_id=None, occurred_monotonic_ns=1),
        dict(event_id="dup-anon", attempt_id=None, occurred_monotonic_ns=1),
    ]
    stop, _, _ = _guard_probe(20, bad=0, anon=0, extra_events=extra)
    assert stop == []  # three copies of one event_id => numerator 1; 1/20 allowed


def test_guard_events_on_unfinished_attempts_excluded():
    extra = [
        dict(event_id="unfin-1", attempt_id="unfinished-a", occurred_monotonic_ns=1),
        dict(event_id="unfin-2", attempt_id="unfinished-b", occurred_monotonic_ns=1),
        dict(event_id="unfin-3", attempt_id="unfinished-c", occurred_monotonic_ns=1),
    ]
    stop, _, _ = _guard_probe(20, bad=0, linked=0, extra_events=extra)
    assert stop == []


def test_guard_interleaved_batches_timestamp_filter():
    """Events after the current completion timestamp, and unfinished-batch events, stay out of N."""
    n = 20
    order = [dict(attempt_id=str(i), completed_monotonic_ns=10 + i) for i in range(n)]
    extra = [
        dict(event_id="future-anon-1", attempt_id=None, occurred_monotonic_ns=10_000),
        dict(event_id="future-anon-2", attempt_id=None, occurred_monotonic_ns=10_000),
        dict(event_id="future-anon-3", attempt_id=None, occurred_monotonic_ns=10_000),
        dict(event_id="inflight-1", attempt_id="batch-b-0", occurred_monotonic_ns=5),
        dict(event_id="inflight-2", attempt_id="batch-b-1", occurred_monotonic_ns=5),
        dict(event_id="past-anon", attempt_id=None, occurred_monotonic_ns=1),
    ]
    stop, _, _ = _guard_probe(n, bad=0, extra_events=extra, completion_order=order)
    assert stop == []  # only one past anonymous event; 1/20 allowed
    extra.append(dict(event_id="past-anon-2", attempt_id=None, occurred_monotonic_ns=1))
    extra.append(dict(event_id="past-anon-3", attempt_id=None, occurred_monotonic_ns=1))
    stop, _, _ = _guard_probe(n, bad=0, extra_events=extra, completion_order=order)
    assert stop and "3/20" in stop[0]


def test_abort_retains_inflight_attempt_rows(tmp_path, clean_env):
    """Run 1 regression: completion_order rows must keep their attempt records after abort."""
    dummy = tmp_path / "dummy.db"
    dummy.write_bytes(b"SQLite format 3\x00")
    harness = ProofHarness(
        source=dummy, out_dir=tmp_path / "out", port=5184, skip_hash_check=True, mock=True
    )
    harness.run_start_time = time.perf_counter()
    harness.run_start_monotonic_ns = time.monotonic_ns()
    for i in range(20):
        harness._record_completed_attempt(
            dict(attempt_id=f"att-{i}", outcome="accepted" if i >= 3 else "rejected", video_id=str(i)),
            time.monotonic_ns(),
        )
    harness._trigger_abort("test abort after 20")
    for i in range(20, 28):
        harness._record_completed_attempt(
            dict(attempt_id=f"att-{i}", outcome="accepted", video_id=str(i)),
            time.monotonic_ns(),
        )
    assert harness.abort_event.is_set()
    assert len(harness.attempts) == 28
    assert len(harness.completion_order) == 28
    assert [a["attempt_id"] for a in harness.attempts] == [e["attempt_id"] for e in harness.completion_order]


def test_post_abort_cleanup_keeps_incomplete_artifacts(tmp_path, clean_env):
    dummy = tmp_path / "dummy.db"
    dummy.write_bytes(b"SQLite format 3\x00")
    harness = ProofHarness(
        source=dummy, out_dir=tmp_path / "out", port=5185, skip_hash_check=True, mock=True
    )
    harness.run_start_time = time.perf_counter()
    harness._trigger_abort("cleanup probe")
    harness.cleanup_errors.append("simulated cleanup failure")
    assert harness.abort_event.is_set()
    assert harness.abort_reason == "cleanup probe"
    assert "simulated cleanup failure" in harness.cleanup_errors
    with harness._proc_lock:
        assert list(harness._active_processes) == []


def test_card_policy_reads_manifest_selection_version(tmp_path, clean_env):
    dummy = tmp_path / "dummy.db"
    dummy.write_bytes(b"SQLite format 3\x00")
    harness = ProofHarness(
        source=dummy, out_dir=tmp_path / "out", port=5186, skip_hash_check=True, mock=True
    )
    harness.manifest = {
        "hashes": {"prompt_sha256": "a" * 64},
        "card_profile": {"selection_version": "spread-longest-v2", "schema_version": 1},
    }
    harness.selection_version = "spread-longest-v2"
    harness.card_schema = 1
    policy = harness._card_policy()
    assert policy["selection_version"] == "spread-longest-v2"
    assert policy["card_schema"] == 1
    harness.selection_version = None
    harness.manifest["card_profile"]["selection_version"] = "spread-longest-v1"
    assert harness._card_policy()["selection_version"] == "spread-longest-v1"


def test_bind_frozen_profile_refuses_missing_selection_version(tmp_path, clean_env):
    dummy = tmp_path / "dummy.db"
    dummy.write_bytes(b"SQLite format 3\x00")
    harness = ProofHarness(
        source=dummy, out_dir=tmp_path / "out", port=5187, skip_hash_check=True, mock=True
    )
    harness.manifest = {"card_profile": {}, "execution": {}}
    with pytest.raises(ProofRunError, match="card_profile.selection_version"):
        harness._bind_frozen_profile()


def test_parser_accepts_claude_opus_5():
    parser = proof_run.build_parser()
    args = parser.parse_args(["--source", "x.db", "--out", "out", "--model", "claude-opus-5"])
    assert args.model == "claude-opus-5"
    args_default = parser.parse_args(["--source", "x.db", "--out", "out"])
    assert args_default.model == "claude-sonnet-5"


def test_runner_does_not_hardcode_spread_longest_v1():
    source = (ROOT / "scripts" / "librarian" / "proof_run.py").read_text(encoding="utf-8")
    assert 'selection_version="spread-longest-v1"' not in source
    assert "selection_version='spread-longest-v1'" not in source


def test_stage4_execution_record_identities():
    import stage2_execution_record as rec

    assert set(rec.STAGES) == {2, 3, 4}
    stage = rec.STAGES[4]
    assert stage["model"] == "claude-opus-5"
    assert stage["effort"] is None
    assert stage["bindings"] == "docs/library/proof/holdout-v3-stage4-bindings-2026-09-07.json"
    assert stage["diff_ledger"] == "docs/library/proof/card-contract-v2-diff-2026-09-07.json"
    assert stage["probe_receipt"] == "docs/library/proof/stage4-probe-receipts-2026-09-07.json"
    assert stage["probe_n"] == 16
    assert stage["probe_wall_budget_ms"] == 900_000
    assert stage["manifest"] == "docs/library/proof/manifest-stage4-2026-09-07.json"
    assert rec.GUARD_RULE_V2["identifier"] == GUARD_RULE_V2["identifier"]
    assert rec.GUARD_RULE_V2["amendment"] == "AO-G1"
    assert rec.GUARD_RULE_V2["comparison"] == "integer"


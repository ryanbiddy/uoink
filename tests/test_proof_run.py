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
import json
import os
import shutil
import socket
import sys
from pathlib import Path

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
    ProofHarness,
    ProofRunError,
    find_free_port,
)
from proof_score import (
    COVERAGE_FLOOR,
    PRECISION_TARGET,
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


def run_harness_subprocess(*, source, out_dir, limit, concurrency, port, scratch_dir, run_id):
    """Run the harness as its own interpreter, the way the orchestrator runs it.
    In-process execution is only valid in a fresh interpreter: once another test
    has imported `server` against the real data root, the in-thread helper
    cannot be re-pointed, so the full suite must not run it in-process."""
    import os
    import subprocess
    import sys
    cmd = [sys.executable, str(ROOT / "scripts" / "librarian" / "proof_run.py"),
           "--source", str(source), "--out", str(out_dir), "--mock",
           "--limit", str(limit), "--concurrency", str(concurrency),
           "--port", str(port), "--scratch", str(scratch_dir),
           "--run-id", run_id, "--skip-hash-check"]
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env["PYTHONPATH"] = str(ROOT)
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=600, cwd=str(ROOT), env=env)
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
    with pytest.raises(ProofRunError, match="ANTHROPIC_API_KEY is set"):
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
    """Creates a realistic test database populated with items from gold-set."""
    gold_path = ROOT / "docs" / "library" / "gold-set-2026-09-04.json"
    gold_items = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.is_file() else []

    idx = index_mod.Index.open(db_path)
    # Seed items
    seeded = 0
    for g in gold_items:
        if seeded >= n_items - 2:  # Save 2 spots for unmapped items
            break
        vid = g["video_id"]
        slug = g.get("slug", vid)
        title = g.get("title", f"Title {vid}")
        channel = g.get("channel", "Test Channel")
        platform = g.get("platform", "youtube")
        card = g.get("card") or {}
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
        seeded += 1

    # Seed 2 unmapped / non-gold items
    for extra_id in ("unmapped_vid_1", "unmapped_vid_2"):
        idx.upsert_yoink(
            {
                "video_id": extra_id,
                "slug": extra_id,
                "title": f"Unmapped Item {extra_id}",
                "channel": "Other Channel",
                "platform": "youtube",
                "topic": "Uncategorized",
                "yoinked_at": "2026-09-04T00:00:00Z",
                "corpus_path": "",
                "sidecar_path": "",
            }
        )
        with idx.write_transaction() as conn:
            conn.execute(
                "INSERT INTO clips(video_id,seq,start,end,text) VALUES(?,?,?,?,?)",
                (extra_id, 0, 0, 10, "General non-matching content prose."),
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

    assert receipts_data["schema_version"] == 1
    assert receipts_data["run_id"] == "test-run-p-mock"
    assert receipts_data["mock"] is True
    assert receipts_data["port"] == ephemeral_port
    assert receipts_data["port"] != FORBIDDEN_PORT

    totals = receipts_data["totals"]
    assert totals["total_items"] == 12
    assert totals["total_attempts"] == 12
    assert totals["total_serialized_input_bytes"] > 0
    assert totals["total_wall_ms"] >= 0

    # Invariant assertions: zero applies, projection revision preserved
    before = receipts_data["before_state"]
    after = receipts_data["after_state"]
    assert before == after
    assert before["applied_count"] == 0
    assert after["applied_count"] == 0

    # Reshelving preview returned can_apply=False
    preview = receipts_data["preview_result"]
    assert preview.get("can_apply") is False

    # Check per-attempt receipt records
    receipt_list = receipts_data["receipts"]
    assert len(receipt_list) == 12

    outcomes = Counter(r["outcome"] for r in receipt_list)
    assert outcomes["accepted"] >= 8
    assert outcomes["unmapped"] >= 1

    for r in receipt_list:
        assert "work_id" in r
        assert "video_id" in r
        assert "attempt_token" in r
        assert "packet_hash" in r
        assert r["card_bytes"] > 0
        assert r["prompt_bytes"] > 0
        assert r["response_bytes"] > 0
        assert r["wall_ms"] >= 0
        assert r["outcome"] in {"accepted", "unmapped", "unsupported", "rejected"}
        if r["outcome"] == "accepted":
            assert r["evidence_basis"] == "packet"
            assert r["evidence_quote"] is not None
            assert len(r["evidence_quote"].split()) <= 25


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

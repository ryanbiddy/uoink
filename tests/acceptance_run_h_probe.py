"""Run H supplemental receipts: synthetic benchmark/meter inputs and real locks.

Run the unchanged acceptance_run_f_probe.py separately. This script opens only
new worktree-local fixture databases. No model, helper, or live index is used.
Results are observations, including an explicit failed gate; exit 0 means the
receipt was written, not that acceptance passed.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(relative):
    spec = importlib.util.spec_from_file_location(Path(relative).stem, ROOT / relative)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    out = parser.parse_args().out.resolve()
    assert out.is_relative_to(ROOT) and not out.exists()
    out.mkdir(parents=True)
    for var, child in (("LOCALAPPDATA", "local"), ("XDG_DATA_HOME", "data"),
                       ("UOINK_OUTPUT_DIR", "output"), ("TEMP", "temp"), ("TMP", "temp")):
        (out / child).mkdir(exist_ok=True)
        os.environ[var] = str(out / child)
    sys.path.insert(0, str(ROOT))
    import index
    import server
    import usage_meter

    report = {"tested_sha": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "real_model_calls": 0, "usage_counters": "synthetic fixtures"}

    # New filtering in Gemini's diff drops invalid path components before
    # comparing. Exercise a complete output object, then the whole runner.
    bench = module("scripts/librarian/bench_local.py")
    gold = {"video_id": "fixture", "title": "Fixture", "channel": "Fixture",
            "platform": "youtube", "shelf_path": ["Science", "Physics"],
            "card": {"clips": [{"text": "alpha beta"}, {"text": "gamma delta"}]}}
    valid = {"video_id": "fixture", "shelf_paths": [["Science", "Physics"]],
             "confidence": 0.9, "evidence_quote": "alpha beta", "unmapped": False,
             "unsupported": False, "proposed_new_leaf": ""}
    malformed = {**valid, "shelf_paths": [["Science", 42, "Physics"]]}
    control = bench.evaluate_single_item(gold, {"assignments": [valid]}, 0.01, None)
    observed = bench.evaluate_single_item(gold, {"assignments": [malformed]}, 0.01, None)
    assert control["l1_match"] and control["l2_match"] and control["evidence_valid"]
    gold_path = out / "gold.json"
    gold_path.write_text(json.dumps([gold]), encoding="utf-8")
    benchmark_path = out / "malformed-benchmark.json"
    with patch.object(bench, "generate_mock_completion", return_value=(
            json.dumps({"assignments": [malformed]}), None, 0.01)):
        code = bench.run_benchmark(base_url="http://fixture.invalid", model="fixture",
            gold_path=gold_path, prompt_path=ROOT / "scripts/librarian/prompts/assign.md",
            mock=True, output_path=benchmark_path)
    assert code == 0
    summary = json.loads(benchmark_path.read_text(encoding="utf-8"))
    report["malformed_path"] = {
        "input": malformed, "valid_control": control, "observed": observed,
        "expected": {"l1_match": False, "l2_match": False},
        "passes": not observed["l1_match"] and not observed["l2_match"],
        "runner": {k: summary[k] for k in ("status", "mock_mode", "total_items",
            "level_1_accuracy", "level_2_accuracy", "evidence_grounding_accuracy")}}

    usage_meter.reset_status()
    with index.Index.open(out / "meter.db") as idx, \
            patch.object(server, "_get_index", return_value=idx), \
            patch.object(usage_meter, "month_of", return_value="2026-09"):
        for label, usage in (
            ("cache_read", {"cache_read_input_tokens": 1000}),
            ("cache_create", {"cache_creation_input_tokens": 1000}),
            ("ordinary", {"input_tokens": 1000, "output_tokens": 1000}),
        ):
            server._record_anthropic_usage("entity_extraction", {
                "model": server.ANTHROPIC_MODEL, "usage": usage})
            report[label] = {"bucket": usage_meter.read_buckets(idx)[0],
                             "public": server._anthropic_actual_usage_payload()}
        assert report["cache_read"]["public"]["total_usd"] == 0.0001
        assert report["cache_create"]["public"]["total_usd"] == 0.00135
        assert report["ordinary"]["public"]["total_usd"] == 0.00735
        assert report["ordinary"]["bucket"]["est_rates"] == server.ANTHROPIC_RATES
        assert report["ordinary"]["public"]["estimate"] is True
        server._record_anthropic_usage("entity_extraction", {
            "model": server.ANTHROPIC_MODEL, "content": [{"type": "text", "text": "ok"}]})
        report["missing_after_usage"] = server._anthropic_actual_usage_payload()
        assert report["missing_after_usage"]["unavailable_calls"] == 1
        # A real open transaction must be preserved, with a visible lost write.
        idx._conn.execute("INSERT INTO memory_layer(key,value,updated_at) VALUES('pending','1','2026-09-04')")
        server._record_anthropic_usage("entity_extraction", {
            "model": server.ANTHROPIC_MODEL, "usage": {"input_tokens": 10}})
        assert idx._conn.in_transaction
        idx._conn.rollback()
        report["write_failure"] = server._anthropic_actual_usage_payload()
        assert report["write_failure"]["status"]["write_failures"] == 1
        assert report["write_failure"]["status"]["ok"] is False
        assert report["write_failure"]["by_feature"]["entity_extraction"]["calls"] == 3
        with patch.object(server, "_get_index", side_effect=sqlite3.OperationalError("fixture")):
            report["read_failure"] = server._anthropic_actual_usage_payload()
        assert report["read_failure"]["unavailable_calls"] is None
        assert report["read_failure"]["error"] == "usage unavailable"

    hook = module("scripts/recall_hook.py")
    locked_path = out / "locked.db"
    with index.Index.open(locked_path):
        pass
    locked_runs = []
    lock = sqlite3.connect(locked_path)
    try:
        lock.execute("PRAGMA journal_mode=DELETE")
        lock.execute("BEGIN EXCLUSIVE")
        for _ in range(5):
            captured = io.StringIO()
            with patch.dict(os.environ, {"UOINK_INDEX_PATH": str(locked_path)}), \
                    patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": "alpha beta gamma delta"}))), \
                    patch.object(sys, "stdout", captured):
                start = time.perf_counter()
                code = hook.main()
                elapsed = time.perf_counter() - start
            assert code == 0 and not captured.getvalue()
            assert elapsed < hook.TIME_BUDGET_SEC
            locked_runs.append(round(elapsed, 4))
    finally:
        lock.rollback()
        lock.close()
    report["recall_locked_main_seconds"] = locked_runs
    (out / "receipts.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

"""tests/security/test_bench_local.py - Verification tests for benchmark harness repairs.

Tests Astra Finding 4 / Benchmark Repair:
- Exit evidence: mock returns right label under wrong id and harness scores 0.
- Rejection of missing, wrong, and duplicate video IDs.
- Inclusion of video_id in all prompt cards.
- Timing the whole response including reading response bytes.
- Reporting missing token usage as unavailable rather than zero.
"""
from __future__ import annotations

import io
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest

import importlib.util

def _load_bench_local():
    bench_path = Path(__file__).resolve().parents[2] / "scripts" / "librarian" / "bench_local.py"
    spec = importlib.util.spec_from_file_location("bench_local", bench_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

bench_local = _load_bench_local()


@pytest.fixture
def sample_gold_item() -> dict[str, Any]:
    return {
        "video_id": "item-golden-42",
        "slug": "sample-golden-item",
        "title": "Introduction to Coding Agents",
        "channel": "Tech Channel",
        "platform": "youtube",
        "shelf_path": ["AI and ML", "Developer Tools", "Coding Assistants"],
        "evidence": "agents write code automatically in a closed loop",
        "card": {
            "slug": "sample-golden-item",
            "title": "Introduction to Coding Agents",
            "channel": "Tech Channel",
            "platform": "youtube",
            "source_type": "video",
            "topic": "Uncategorized",
            "summary_hint": "An in-depth lecture on automated coding agents.",
            "clips": [
                {
                    "start": 10.0,
                    "end": 45.0,
                    "text": "agents write code automatically in a closed loop with test verification",
                    "deep_link": "https://youtube.com/watch?v=item-golden-42&t=10s",
                }
            ],
            "clip_count": 1,
            "chars": 72,
        },
    }


def test_mock_returns_right_label_under_wrong_id_scores_zero(sample_gold_item: dict[str, Any]) -> None:
    """Exit evidence requirement:

    When the mock/model returns the right label and quote under the wrong id,
    the harness rejects the item and scores it 0.
    """
    # Generate mock completion with corrupt_id="WRONG_ITEM_ID"
    content, tokens, wall_time = bench_local.generate_mock_completion(
        sample_gold_item,
        sim_agreement=1.0,  # simulate 100% agreement on labels
        corrupt_id="WRONG_ITEM_ID",
    )
    pred_data = json.loads(content)

    # The assignment payload contains the correct shelf_path
    assert pred_data["assignments"][0]["shelf_paths"] == [sample_gold_item["shelf_path"]]
    assert pred_data["assignments"][0]["video_id"] == "WRONG_ITEM_ID"

    # Evaluate using the harness
    eval_res = bench_local.evaluate_single_item(sample_gold_item, pred_data, wall_time, tokens)

    # Harness must reject the wrong ID and score 0 on all agreement metrics
    assert eval_res["id_valid"] is False
    assert eval_res["id_status"] == "wrong_id"
    assert eval_res["l1_match"] is False
    assert eval_res["l2_match"] is False
    assert eval_res["evidence_valid"] is False


def test_run_benchmark_mock_wrong_id_summary_scores_zero(tmp_path: Path, sample_gold_item: dict[str, Any]) -> None:
    """End-to-end run_benchmark in mock mode with mock_wrong_id produces 0% accuracy."""
    gold_file = tmp_path / "mini_gold.json"
    gold_file.write_text(json.dumps([sample_gold_item]), encoding="utf-8")
    prompt_file = tmp_path / "assign.md"
    prompt_file.write_text("Taxonomy: {{TAXONOMY}}\nCards: {{CARDS}}", encoding="utf-8")
    out_file = tmp_path / "results.json"

    ret = bench_local.run_benchmark(
        base_url="http://localhost:1235/v1",
        model="test-model",
        gold_path=gold_file,
        prompt_path=prompt_file,
        mock=True,
        mock_wrong_id=True,
        output_path=out_file,
    )
    assert ret == 0
    with open(out_file, "r", encoding="utf-8") as f:
        summary = json.load(f)

    assert summary["level_1_accuracy"] == 0.0
    assert summary["level_2_accuracy"] == 0.0
    assert summary["evidence_grounding_accuracy"] == 0.0
    assert summary["item_results"][0]["id_status"] == "wrong_id"


def test_evaluate_single_item_rejects_missing_id(sample_gold_item: dict[str, Any]) -> None:
    """Harness must reject assignments with missing video_id."""
    pred_data = {
        "assignments": [
            {
                "shelf_paths": [sample_gold_item["shelf_path"]],
                "confidence": 0.95,
                "evidence_quote": sample_gold_item["evidence"],
            }
        ]
    }
    eval_res = bench_local.evaluate_single_item(sample_gold_item, pred_data, 1.0, 50)
    assert eval_res["id_valid"] is False
    assert eval_res["id_status"] == "missing_id"
    assert eval_res["l1_match"] is False
    assert eval_res["l2_match"] is False


def test_evaluate_single_item_rejects_duplicate_ids(sample_gold_item: dict[str, Any]) -> None:
    """Harness must reject assignments with duplicate video_ids."""
    pred_data = {
        "assignments": [
            {
                "video_id": sample_gold_item["video_id"],
                "shelf_paths": [sample_gold_item["shelf_path"]],
                "confidence": 0.95,
                "evidence_quote": sample_gold_item["evidence"],
            },
            {
                "video_id": sample_gold_item["video_id"],
                "shelf_paths": [["Different", "Path"]],
                "confidence": 0.60,
                "evidence_quote": sample_gold_item["evidence"],
            },
        ]
    }
    eval_res = bench_local.evaluate_single_item(sample_gold_item, pred_data, 1.0, 50)
    assert eval_res["id_valid"] is False
    assert eval_res["id_status"] == "duplicate_id"
    assert eval_res["l1_match"] is False
    assert eval_res["l2_match"] is False


def test_format_card_for_prompt_includes_video_id(sample_gold_item: dict[str, Any]) -> None:
    """Format card for prompt must include video_id even when card dict originally omits it."""
    # Ensure raw item's card does NOT have video_id
    assert "video_id" not in sample_gold_item["card"]

    card_obj = bench_local.format_card_for_prompt(sample_gold_item)
    assert "video_id" in card_obj
    assert card_obj["video_id"] == sample_gold_item["video_id"]

    # Also test for a metadata-only stub (null card)
    metadata_only_item = {
        "video_id": "meta-only-01",
        "title": "Article Title",
        "channel": "Author",
        "platform": "x",
        "card": None,
    }
    card_stub = bench_local.format_card_for_prompt(metadata_only_item)
    assert card_stub["video_id"] == "meta-only-01"


def test_send_chat_completion_times_full_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_chat_completion must time across reading the response body."""
    class FakeResponse:
        status = 200

        def read(self):
            time.sleep(0.05)
            payload = {
                "choices": [{"message": {"content": '{"assignments": []}'}}],
                "usage": {"completion_tokens": 12},
            }
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeResponse())

    content, tokens, wall_time = bench_local.send_chat_completion(
        base_url="http://localhost:1235/v1",
        model="test-model",
        prompt="test prompt",
    )
    assert wall_time >= 0.04
    assert tokens == 12
    assert "assignments" in content


def test_missing_token_usage_reported_as_unavailable(sample_gold_item: dict[str, Any]) -> None:
    """Missing token usage is returned as unavailable rather than zero or word count."""
    eval_res = bench_local.evaluate_single_item(
        item=sample_gold_item,
        pred_data={"assignments": [{"video_id": sample_gold_item["video_id"], "shelf_paths": [sample_gold_item["shelf_path"]], "evidence_quote": sample_gold_item["evidence"]}]},
        wall_time=1.0,
        tokens=None,
    )
    assert eval_res["completion_tokens"] == "unavailable"
    assert eval_res["tokens_per_sec"] == "unavailable"

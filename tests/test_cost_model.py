"""Cost-model packing and forecast-field contract (run D, grok)."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "cost_model", ROOT / "scripts" / "library" / "cost_model.py"
)
assert _SPEC is not None and _SPEC.loader is not None
cost_model = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cost_model)


def _average_pack_first_batch(
    card_token_list: list[float],
    prompt_tokens: float,
    taxonomy_tokens: float,
    context: int,
) -> tuple[float, int]:
    """Reproduce the pre-repair packer Astra measured at cost_model.py:344."""
    n = len(card_token_list)
    overhead = prompt_tokens + taxonomy_tokens
    room = max(1_000, context - overhead - 1_000)
    avg = max(1.0, sum(card_token_list) / n)
    per = max(1, min(n, int(room // avg)))
    first = card_token_list[:per]
    return overhead + sum(first), per


def test_first_fit_keeps_batches_inside_budget_when_average_packing_overflows():
    # Astra's shape: mixed sizes, global average sizes a first batch of ~173
    # cards at ~277k input tokens against a 200k context.
    large = [1_560.0] * 173
    small = [200.0] * 375
    cards = large + small
    prompt, taxonomy, context = 263.0, 6_000.0, 200_000
    old_input, old_per = _average_pack_first_batch(
        cards, prompt, taxonomy, context
    )
    assert old_per >= 173
    assert old_input > context

    packed = cost_model.pack_assign_batches(
        cards, prompt, taxonomy, context, max_output=64_000
    )
    assert packed.n_calls >= 2
    assert packed.batch_sizes[0] < 173
    for inp, out in zip(packed.batch_input_tokens, packed.batch_output_tokens):
        assert inp + out <= context
        assert out <= 64_000
    assert packed.max_batch_request_tokens <= context
    assert sum(packed.batch_sizes) == len(cards)


def test_pack_fails_loudly_when_a_card_cannot_fit():
    with pytest.raises(cost_model.CardDoesNotFitError, match=r"card\[0\] does not fit"):
        cost_model.pack_assign_batches(
            [50_000.0],
            prompt_tokens=1_000.0,
            taxonomy_tokens=6_000.0,
            context=20_000,
        )


def test_pack_reserves_output_capacity():
    # Input-only would fit two cards; reserved output forces a split.
    cards = [6_000.0, 6_000.0]
    packed = cost_model.pack_assign_batches(
        cards,
        prompt_tokens=1_000.0,
        taxonomy_tokens=0.0,
        context=14_000,
        output_tokens_per_card=2_000,
    )
    assert packed.batch_sizes == [1, 1]
    for inp, out in zip(packed.batch_input_tokens, packed.batch_output_tokens):
        assert inp + out <= 14_000
        assert out == 2_000


def test_pack_enforces_max_output():
    cards = [100.0] * 10
    packed = cost_model.pack_assign_batches(
        cards,
        prompt_tokens=50.0,
        taxonomy_tokens=50.0,
        context=100_000,
        output_tokens_per_card=400,
        max_output=1_200,  # 3 cards of output
    )
    assert packed.batch_sizes == [3, 3, 3, 1]
    assert all(out <= 1_200 for out in packed.batch_output_tokens)


def test_forced_batch_still_splits_when_twelve_cannot_fit():
    cards = [10_000.0] * 12
    packed = cost_model.pack_assign_batches(
        cards,
        prompt_tokens=1_000.0,
        taxonomy_tokens=6_000.0,
        context=32_000,
        forced_batch=12,
        output_tokens_per_card=400,
    )
    assert packed.n_calls > 1
    assert max(packed.batch_sizes) < 12
    for inp, out in zip(packed.batch_input_tokens, packed.batch_output_tokens):
        assert inp + out <= 32_000


def test_induce_fits_context_rejects_unpackable_sample():
    assert cost_model.induce_fits_context(10_000, context=32_000) is True
    assert cost_model.induce_fits_context(75_000, context=32_000) is False
    assert cost_model.induce_fits_context(
        1_000, context=200_000, induce_output=70_000, max_output=64_000
    ) is False


def _mini_index(path: Path, n: int = 4) -> Path:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE yoinks (
            video_id TEXT PRIMARY KEY,
            slug TEXT,
            title TEXT,
            channel TEXT,
            topic TEXT,
            hook_type TEXT,
            yoinked_at TEXT,
            source_type TEXT,
            platform TEXT,
            author TEXT,
            metadata_json TEXT,
            corpus_path TEXT,
            deleted_at TEXT
        )
        """
    )
    for i in range(n):
        conn.execute(
            "INSERT INTO yoinks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"vid{i}",
                f"slug{i}",
                f"Title {i}",
                "Channel",
                "Uncategorized",
                None,
                f"2026-09-04T00:00:0{i}",
                "video",
                "youtube",
                "author",
                "{}",
                None,
                None,
            ),
        )
    conn.commit()
    conn.close()
    return path


def test_measure_emits_estimated_usage_and_paid_fields(tmp_path: Path):
    db = _mini_index(tmp_path / "mini.db")
    report = cost_model.measure(db)

    assert "estimated_tokens" in report
    assert report["reported_usage"] is None
    assert report["paid_cost"] is None
    assert report["g4"]["reported_usage"] is None
    assert report["g4"]["paid_cost"] is None
    assert report["g4"]["status"] == "forecast"
    assert report["g4"]["operational_gate"] == "pending measured usage"
    assert report["g4"]["verdict"] in (
        cost_model.G4_FORECAST_WITHIN,
        cost_model.G4_FORECAST_OUTSIDE,
    )
    assert report["g4"]["verdict"] != "PASS"
    assert "PASS" not in report["g4"]["verdict"]
    assert "measured_usd_per_500" not in report["g4"]
    assert "estimated_usd_per_500" in report["g4"]

    haiku = report["prices"]["claude-haiku-4.5"]
    for inp, out in zip(
        haiku["packing"]["batch_input_tokens"],
        haiku["packing"]["batch_output_tokens"],
    ):
        assert inp + out <= haiku["context"]
        assert out <= haiku["max_output"]

    text = cost_model.render_text(report)
    assert "PASS" not in text
    assert cost_model.G4_FORECAST_WITHIN in text or cost_model.G4_FORECAST_OUTSIDE in text
    assert "reported_usage=None" in text
    assert "paid_cost=None" in text
    assert "estimated_tokens" in text

    dumped = json.dumps(report)
    assert '"reported_usage": null' in dumped
    assert '"paid_cost": null' in dumped


def test_render_text_never_prints_pass_from_an_estimate():
    report = {
        "g4": {
            "verdict": cost_model.G4_FORECAST_WITHIN,
            "metric": "Haiku 4.5 Message Batches API, first-fit packed assign + induce 60",
            "estimated_usd_per_500": 0.84,
            "estimate_usd_per_500": 1.00,
            "ratio": 0.84,
        },
        "reported_usage": None,
        "paid_cost": None,
        "index": "fixture.db",
        "cards": 1,
        "items_with_clips": 0,
        "clips_in_index": 0,
        "items_with_summary_hint": 0,
        "characters": {"card_text_total": 40, "card_text_mean": 40.0},
        "estimated_tokens": {
            "basis": "chars/4",
            "per_card_mean": 10.0,
            "chars4_total_cards": 10.0,
            "tiktoken_total_cards": None,
            "induce_input": 100.0,
            "assign_output_stated_total": 400,
            "assign_output_stated_per_card": 400,
            "induce_output_assumed": 6_000,
        },
        "prompts_dir": str(cost_model.PROMPTS),
        "prices": {
            "claude-haiku-4.5": {
                "packed_batch_sizes": [1],
                "packing": {
                    "max_request_tokens": 1_000.0,
                    "induce_fits": True,
                },
                "list_packed": {
                    "assign_calls": 1,
                    "usd_total": 0.01,
                    "usd_per_500": 0.84,
                },
                "batch_packed": {
                    "assign_calls": 1,
                    "usd_total": 0.005,
                    "usd_per_500": 0.42,
                },
                "list_dryrun_batches": {
                    "assign_calls": 1,
                    "usd_total": 0.01,
                    "usd_per_500": 0.84,
                },
                "dryrun_batch_sizes": [1],
            },
            "claude-sonnet-5": {
                "packed_batch_sizes": [1],
                "packing": {"max_request_tokens": 1_000.0, "induce_fits": True},
                "list_packed": {
                    "assign_calls": 1,
                    "usd_total": 0.02,
                    "usd_per_500": 1.0,
                },
                "batch_packed": {
                    "assign_calls": 1,
                    "usd_total": 0.01,
                    "usd_per_500": 0.5,
                },
            },
            "gemini-3.8-flash": {
                "packed_batch_sizes": [1],
                "packing": {"max_request_tokens": 1_000.0, "induce_fits": True},
                "list_packed": {
                    "assign_calls": 1,
                    "usd_total": 0.01,
                    "usd_per_500": 0.5,
                },
                "batch_packed": {
                    "assign_calls": 1,
                    "usd_total": 0.005,
                    "usd_per_500": 0.25,
                },
            },
            "gpt-5-nano": {
                "packed_batch_sizes": [1],
                "packing": {"max_request_tokens": 1_000.0, "induce_fits": True},
                "list_packed": {
                    "assign_calls": 1,
                    "usd_total": 0.001,
                    "usd_per_500": 0.05,
                },
                "batch_packed": {
                    "assign_calls": 1,
                    "usd_total": 0.0005,
                    "usd_per_500": 0.025,
                },
            },
            "local-16gb": {
                "packed_batch_sizes": [1],
                "packing": {
                    "max_request_tokens": 1_000.0,
                    "induce_fits": False,
                },
                "packed": {
                    "assign_calls": 1,
                    "hours_16gb": {
                        "output_only_low_tok_s": 0.1,
                        "output_only_high_tok_s": 0.2,
                    },
                },
            },
        },
    }
    text = cost_model.render_text(report)
    assert "PASS" not in text
    assert text.splitlines()[0] == cost_model.G4_FORECAST_WITHIN
    assert "induce-60 does not fit this context" in text

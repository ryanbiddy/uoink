"""Measure evidence-card size on a uoink index COPY and price one Librarian pass.

Reads the index read-only. Never writes or binds the helper. Card selection
and rendering use library_cards, shared with get_evidence_card and dryrun.
The default full profile keeps ten untruncated clips.

Usage (from the worktree root):
    python scripts/library/cost_model.py
    python scripts/library/cost_model.py --index path/to/copy.db --json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
PROMPTS = ROOT / "scripts" / "librarian" / "prompts"
DEFAULT_INDEX = Path(
    os.environ.get(
        "UOINK_INDEX_COPY",
        r"C:\Users\hello\AppData\Local\AgentControlRoom\uoink-index-copy-2026-09-04.db",
    )
)

# The shared builder owns the default full profile.
N_CLIPS_DEFAULT = 10

# Dispatch: assign output ~400 tokens/card. Induce output is not measured
# (no model is called); 6_000 is a filled 40–80 node taxonomy JSON.
ASSIGN_OUTPUT_TOKENS_PER_CARD = 400
INDUCE_OUTPUT_TOKENS_ASSUMED = 6_000
INDUCE_SAMPLE = 60
DRYRUN_BATCH = 12
COUNCIL_HAIKU_USD_PER_500 = 1.00
PRICES_CHECKED = "2026-09-04"

# Live list prices, USD per million tokens, verified 2026-09-04.
# Sources are in docs/library/COST-MODEL-2026-09-04.md.
MODELS = {
    "claude-haiku-4.5": {
        "display": "Claude Haiku 4.5",
        "input": 1.00,
        "output": 5.00,
        "batch_input": 0.50,
        "batch_output": 2.50,
        "context": 200_000,
        "source": "https://platform.claude.com/docs/en/about-claude/pricing",
    },
    "claude-sonnet-5": {
        "display": "Claude Sonnet 5",
        "input": 2.00,
        "output": 10.00,
        "batch_input": 1.00,
        "batch_output": 5.00,
        "context": 1_000_000,
        "source": "https://platform.claude.com/docs/en/about-claude/pricing",
    },
    "gemini-3.8-flash": {
        "display": "Gemini 3.8 Flash (intro through 2026-12-31)",
        "input": 0.75,
        "output": 3.75,
        "batch_input": 0.375,
        "batch_output": 1.875,
        "context": 1_048_576,
        "source": "https://ai.google.dev/gemini-api/docs/pricing",
    },
    "gpt-5-nano": {
        "display": "GPT-5 nano (nearest small OpenAI model)",
        "input": 0.05,
        "output": 0.40,
        "batch_input": 0.025,
        "batch_output": 0.20,
        "context": 400_000,
        "source": "https://platform.openai.com/docs/pricing",
    },
    "local-16gb": {
        "display": "Local resident 27B on a 16 GB card",
        "input": 0.0,
        "output": 0.0,
        "batch_input": 0.0,
        "batch_output": 0.0,
        "context": 32_000,
        "source": "council 7–22 tok/s regime; $0",
        "tok_s_low": 7,
        "tok_s_high": 22,
    },
}


def _connect_ro(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"index copy not found: {resolved}")
    uri = resolved.as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _tiktoken_count(text: str) -> int | None:
    try:
        import tiktoken  # type: ignore
    except ImportError:
        return None
    for name in ("o200k_base", "cl100k_base"):
        try:
            enc = tiktoken.get_encoding(name)
            return len(enc.encode(text))
        except Exception:
            continue
    return None


def _tokens_from_chars(n_chars: int) -> float:
    return n_chars / 4.0


# Shared selection, packet identity, bounds and prompt rendering.
sys.path.insert(0, str(ROOT))
from library_cards import build_cards as _build_cards, card_text


def build_cards(conn: sqlite3.Connection, n_clips: int | None = None, *,
                profile: str = "full", clip_chars: int | None = None) -> list[dict]:
    return _build_cards(conn, profile=profile, n_clips=n_clips, clip_chars=clip_chars)


def stratified_sample(cards: list[dict], n: int, seed: int = 7) -> list[dict]:
    """Same weighting as scripts/librarian/dryrun.py (Uncategorized x2)."""
    rnd = random.Random(seed)
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for c in cards:
        by_topic[c["current_topic"] or "None"].append(c)
    weights = {t: (2.0 if t == "Uncategorized" else 1.0) for t in by_topic}
    total_w = sum(weights[t] * len(v) for t, v in by_topic.items()) or 1.0
    picked: list[dict] = []
    for t, v in by_topic.items():
        k = max(1, round(n * weights[t] * len(v) / total_w))
        picked += rnd.sample(v, min(k, len(v)))
    rnd.shuffle(picked)
    return picked[:n]


def _chunks(seq, n):
    n = max(1, n)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _usd(tokens: float, rate_per_m: float) -> float:
    return (tokens / 1_000_000.0) * rate_per_m


def price_pass(
    *,
    induce_input: float,
    assign_input: float,
    assign_calls: int,
    n_cards: int,
    model: dict,
    use_batch: bool,
) -> dict:
    out_induce = float(INDUCE_OUTPUT_TOKENS_ASSUMED)
    out_assign = float(ASSIGN_OUTPUT_TOKENS_PER_CARD * n_cards)
    in_rate = model["batch_input"] if use_batch else model["input"]
    out_rate = model["batch_output"] if use_batch else model["output"]
    in_tok = induce_input + assign_input
    out_tok = out_induce + out_assign
    usd_in = _usd(in_tok, in_rate)
    usd_out = _usd(out_tok, out_rate)
    usd = usd_in + usd_out
    hours = None
    tok_s = model.get("tok_s_low")
    if tok_s:
        # Generation-bound: output tokens at 7–22 tok/s. Prefill of input is
        # faster on a resident model; report output-only hours plus a
        # conservative all-tokens hours.
        hours = {
            "output_only_low_tok_s": out_tok / model["tok_s_high"] / 3600.0,
            "output_only_high_tok_s": out_tok / model["tok_s_low"] / 3600.0,
            "all_tokens_low_tok_s": (in_tok + out_tok) / model["tok_s_high"] / 3600.0,
            "all_tokens_high_tok_s": (in_tok + out_tok) / model["tok_s_low"] / 3600.0,
        }
    return {
        "model": model["display"],
        "batch": use_batch,
        "assign_calls": assign_calls,
        "input_tokens": round(in_tok, 1),
        "output_tokens": round(out_tok, 1),
        "usd_input": round(usd_in, 6),
        "usd_output": round(usd_out, 6),
        "usd_total": round(usd, 6),
        "usd_per_500": round(usd * 500.0 / n_cards, 6) if n_cards else None,
        "hours_16gb": hours,
    }


def assign_input_tokens(
    card_token_list: list[float],
    prompt_tokens: float,
    taxonomy_tokens: float,
    context: int,
    *,
    forced_batch: int | None = None,
) -> tuple[float, int, int]:
    """Return (total_input_tokens, n_calls, cards_per_call)."""
    n = len(card_token_list)
    if n == 0:
        return 0.0, 0, 0
    overhead = prompt_tokens + taxonomy_tokens
    if forced_batch is not None:
        per = max(1, min(forced_batch, n))
    else:
        room = max(1_000, context - overhead - 1_000)
        avg = max(1.0, sum(card_token_list) / n)
        per = max(1, min(n, int(room // avg)))
        if per < 1:
            per = 1
    total = 0.0
    calls = 0
    for batch in _chunks(card_token_list, per):
        total += overhead + sum(batch)
        calls += 1
    return total, calls, per


def measure(index_path: Path) -> dict:
    conn = _connect_ro(index_path)
    try:
        n_yoinks = conn.execute(
            "SELECT COUNT(*) FROM yoinks WHERE deleted_at IS NULL"
        ).fetchone()[0]
        n_clips = 0
        n_clip_items = 0
        if conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clips'"
        ).fetchone():
            n_clips = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
            n_clip_items = conn.execute(
                "SELECT COUNT(DISTINCT video_id) FROM clips"
            ).fetchone()[0]
        cards = build_cards(conn)
    finally:
        conn.close()

    induce_prompt = (PROMPTS / "induce.md").read_text(encoding="utf-8")
    assign_prompt = (PROMPTS / "assign.md").read_text(encoding="utf-8")
    sample = stratified_sample(cards, min(INDUCE_SAMPLE, len(cards)))
    sample_blob = "\n\n".join(card_text(c) for c in sample)
    induce_full = induce_prompt.replace("{{CARDS}}", sample_blob)
    assign_prompt_only = assign_prompt.replace("{{TAXONOMY}}", "").replace(
        "{{CARDS}}", ""
    )

    card_blobs = [card_text(c) for c in cards]
    card_chars = [len(b) for b in card_blobs]
    tik_cards = [_tiktoken_count(b) for b in card_blobs]
    tik_available = all(t is not None for t in tik_cards) and bool(card_blobs)
    tik_induce = _tiktoken_count(induce_full)
    tik_assign_prompt = _tiktoken_count(assign_prompt_only)

    def tok(chars: int, tik: int | None) -> float:
        if tik_available and tik is not None:
            return float(tik)
        return _tokens_from_chars(chars)

    card_tokens = [
        tok(ch, tk) for ch, tk in zip(card_chars, tik_cards)
    ]
    induce_input = tok(len(induce_full), tik_induce)
    assign_prompt_tokens = tok(len(assign_prompt_only), tik_assign_prompt)
    taxonomy_tokens = float(INDUCE_OUTPUT_TOKENS_ASSUMED)

    n = len(cards)
    with_clips = sum(1 for c in cards if c["clip_count"] > 0)
    with_hint = sum(1 for c in cards if c.get("summary_hint"))
    chosen_chars = sum(c["chars_chosen_clips"] for c in cards)
    all_clip_chars = sum(c["chars_all_clips"] for c in cards)
    hint_chars = sum(len(c.get("summary_hint") or "") for c in cards)
    title_chars = sum(len(c.get("title") or "") + len(c.get("channel") or "") for c in cards)

    token_basis = "tiktoken o200k_base/cl100k_base" if tik_available else "chars/4"
    total_card_chars = sum(card_chars)
    total_card_tokens = sum(card_tokens)

    priced = {}
    for key, model in MODELS.items():
        context = int(model["context"])
        packed_in, packed_calls, packed_per = assign_input_tokens(
            card_tokens, assign_prompt_tokens, taxonomy_tokens, context
        )
        dry_in, dry_calls, dry_per = assign_input_tokens(
            card_tokens,
            assign_prompt_tokens,
            taxonomy_tokens,
            context,
            forced_batch=DRYRUN_BATCH,
        )
        entry = {
            "context": context,
            "packed_cards_per_call": packed_per,
            "dryrun_cards_per_call": dry_per,
        }
        if key == "local-16gb":
            entry["packed"] = price_pass(
                induce_input=induce_input,
                assign_input=packed_in,
                assign_calls=packed_calls,
                n_cards=n,
                model=model,
                use_batch=False,
            )
            entry["dryrun_batches"] = price_pass(
                induce_input=induce_input,
                assign_input=dry_in,
                assign_calls=dry_calls,
                n_cards=n,
                model=model,
                use_batch=False,
            )
        else:
            entry["list_packed"] = price_pass(
                induce_input=induce_input,
                assign_input=packed_in,
                assign_calls=packed_calls,
                n_cards=n,
                model=model,
                use_batch=False,
            )
            entry["batch_packed"] = price_pass(
                induce_input=induce_input,
                assign_input=packed_in,
                assign_calls=packed_calls,
                n_cards=n,
                model=model,
                use_batch=True,
            )
            entry["list_dryrun_batches"] = price_pass(
                induce_input=induce_input,
                assign_input=dry_in,
                assign_calls=dry_calls,
                n_cards=n,
                model=model,
                use_batch=False,
            )
        priced[key] = entry

    haiku_batch_per_500 = priced["claude-haiku-4.5"]["batch_packed"]["usd_per_500"]
    ratio = (
        haiku_batch_per_500 / COUNCIL_HAIKU_USD_PER_500
        if COUNCIL_HAIKU_USD_PER_500
        else None
    )
    g4_pass = ratio is not None and ratio <= 2.0

    return {
        "run_date": date.today().isoformat(),
        "prices_checked": PRICES_CHECKED,
        "index": str(index_path.resolve()),
        "items": n_yoinks,
        "cards": n,
        "items_with_clips": n_clip_items,
        "items_with_chosen_clips": with_clips,
        "items_with_summary_hint": with_hint,
        "clips_in_index": n_clips,
        "n_clips_per_card": N_CLIPS_DEFAULT,
        "induce_sample": len(sample),
        "token_basis": token_basis,
        "tiktoken_available": tik_available,
        "characters": {
            "card_text_total": total_card_chars,
            "card_text_mean": round(total_card_chars / n, 1) if n else 0,
            "chosen_clip_text": chosen_chars,
            "all_clip_text": all_clip_chars,
            "summary_hints": hint_chars,
            "titles_and_channels": title_chars,
            "induce_prompt_plus_60_cards": len(induce_full),
        },
        "tokens": {
            "basis": token_basis,
            "chars4_total_cards": round(_tokens_from_chars(total_card_chars), 1),
            "tiktoken_total_cards": (
                int(sum(tik_cards)) if tik_available else None  # type: ignore[arg-type]
            ),
            "per_card_mean": round(total_card_tokens / n, 1) if n else 0,
            "induce_input": round(induce_input, 1),
            "assign_prompt": round(assign_prompt_tokens, 1),
            "taxonomy_assumed": INDUCE_OUTPUT_TOKENS_ASSUMED,
            "assign_output_stated_per_card": ASSIGN_OUTPUT_TOKENS_PER_CARD,
            "assign_output_stated_total": ASSIGN_OUTPUT_TOKENS_PER_CARD * n,
            "induce_output_assumed": INDUCE_OUTPUT_TOKENS_ASSUMED,
        },
        "assumptions": {
            "assign_output_tokens_per_card": ASSIGN_OUTPUT_TOKENS_PER_CARD,
            "induce_output_tokens": INDUCE_OUTPUT_TOKENS_ASSUMED,
            "induce_output_label": "ASSUMED (no model called)",
            "assign_output_label": "STATED by dispatch",
            "card_input_label": "MEASURED from index copy",
            "no_prompt_cache": True,
            "no_thinking_tokens": True,
        },
        "council_estimate_usd_per_500_haiku": COUNCIL_HAIKU_USD_PER_500,
        "g4": {
            "metric": "Haiku 4.5 Message Batches API, context-packed assign + induce 60",
            "measured_usd_per_500": haiku_batch_per_500,
            "estimate_usd_per_500": COUNCIL_HAIKU_USD_PER_500,
            "ratio": round(ratio, 4) if ratio is not None else None,
            "within_2x": g4_pass,
            "verdict": "PASS" if g4_pass else "FAIL",
        },
        "prices": priced,
    }


def _fmt_usd(x: float | None) -> str:
    if x is None:
        return "n/a"
    if x == 0:
        return "$0"
    if x < 0.01:
        return f"${x:.4f}"
    return f"${x:.2f}"


def render_text(report: dict) -> str:
    lines = []
    g4 = report["g4"]
    lines.append(
        f"G4 {g4['verdict']}: {g4['metric']} = "
        f"{_fmt_usd(g4['measured_usd_per_500'])} / 500 items "
        f"(council {_fmt_usd(g4['estimate_usd_per_500'])}, "
        f"ratio {g4['ratio']}x, 2x gate)."
    )
    lines.append(
        f"Index {report['index']}: {report['cards']} cards, "
        f"{report['items_with_clips']} with clips, "
        f"{report['clips_in_index']} clip rows, "
        f"{report['items_with_summary_hint']} with a summary hint."
    )
    ch = report["characters"]
    tk = report["tokens"]
    lines.append(
        f"Card text {ch['card_text_total']:,} chars "
        f"(mean {ch['card_text_mean']}), "
        f"tokens {tk['basis']} mean {tk['per_card_mean']} / card, "
        f"chars/4 total {tk['chars4_total_cards']}."
    )
    if tk["tiktoken_total_cards"] is not None:
        lines.append(f"tiktoken total card tokens: {tk['tiktoken_total_cards']:,}.")
    lines.append(
        f"Induce input (60 cards + prompt): {tk['induce_input']} tokens. "
        f"Assign output STATED {tk['assign_output_stated_total']:,} "
        f"({tk['assign_output_stated_per_card']}/card). "
        f"Induce output ASSUMED {tk['induce_output_assumed']:,}."
    )
    lines.append("")
    lines.append("Packed context (list / batch) for one induce+assign pass:")
    for key, spec in MODELS.items():
        block = report["prices"][key]
        if key == "local-16gb":
            p = block["packed"]
            h = p["hours_16gb"] or {}
            lines.append(
                f"  {spec['display']}: $0 · "
                f"{p['assign_calls']} assign calls · "
                f"output-only {h.get('output_only_low_tok_s', 0):.2f}–"
                f"{h.get('output_only_high_tok_s', 0):.2f} h "
                f"at 22–7 tok/s"
            )
            continue
        lst = block["list_packed"]
        bat = block["batch_packed"]
        lines.append(
            f"  {spec['display']}: list {_fmt_usd(lst['usd_total'])} "
            f"({_fmt_usd(lst['usd_per_500'])}/500) · "
            f"batch {_fmt_usd(bat['usd_total'])} "
            f"({_fmt_usd(bat['usd_per_500'])}/500) · "
            f"{lst['assign_calls']} assign calls of {block['packed_cards_per_call']}"
        )
    lines.append("")
    lines.append("Haiku list, dry-run 12-card batches (client-loop shape):")
    dry = report["prices"]["claude-haiku-4.5"]["list_dryrun_batches"]
    lines.append(
        f"  {dry['assign_calls']} calls · {_fmt_usd(dry['usd_total'])} "
        f"({_fmt_usd(dry['usd_per_500'])}/500)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    ap.add_argument("--json", action="store_true", help="print the full JSON report")
    args = ap.parse_args(argv)
    report = measure(args.index)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))
        print()
        print("--- json ---")
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

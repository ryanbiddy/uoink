"""Forecast evidence-card size on a uoink index COPY and price one Librarian pass.

Reads the index read-only. Never writes. Does not import clips.py, index.py,
or uoink_mcp_tools.py (those modules bind the live helper). Card construction
copies get_evidence_card: 10 clips spread across the timeline + title,
channel, summary hint.

Token counts here are estimates (chars/4, or tiktoken if installed). This
script never calls a model, so reported_usage and paid_cost stay null.
Packing is first-fit per card against the real request budget (prompt +
taxonomy + cards + reserved output, and the model's max_output cap).

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
from typing import NamedTuple

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
PROMPTS = ROOT / "scripts" / "librarian" / "prompts"
DEFAULT_INDEX = Path(
    os.environ.get(
        "UOINK_INDEX_COPY",
        r"C:\Users\hello\AppData\Local\AgentControlRoom\uoink-index-copy-2026-09-04.db",
    )
)

# Match uoink_mcp_tools.get_evidence_card (do not import that module).
N_CLIPS_DEFAULT = 10
SUMMARY_HINT_CHARS = 600
SUMMARY_HINT_READ_BYTES = 8192
MD_META_LINE_RE = re.compile(r"^\s*(\*\*[^*]+:\*\*|#\s|---\s*$|!\[|## Thumbnail)")

# Dispatch: assign output ~400 tokens/card. Induce output is not measured
# (no model is called); 6_000 is a filled 40–80 node taxonomy JSON.
ASSIGN_OUTPUT_TOKENS_PER_CARD = 400
INDUCE_OUTPUT_TOKENS_ASSUMED = 6_000
INDUCE_SAMPLE = 60
DRYRUN_BATCH = 12
COUNCIL_HAIKU_USD_PER_500 = 1.00
PRICES_CHECKED = "2026-09-04"
# Conservative proxy for the "\n\n" joiner between serialized cards.
CARD_SEPARATOR_TOKENS = 1.0
G4_FORECAST_WITHIN = (
    "G4 forecast: within 2x of estimate; operational G4 pending measured usage."
)
G4_FORECAST_OUTSIDE = (
    "G4 forecast: outside 2x of estimate; operational G4 pending measured usage."
)

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
        "max_output": 64_000,
        "source": "https://platform.claude.com/docs/en/about-claude/pricing",
        "max_output_source": "https://docs.cloud.google.com/vertex-ai/generative-ai/docs/partner-models/claude/haiku-4-5",
    },
    "claude-sonnet-5": {
        "display": "Claude Sonnet 5",
        "input": 2.00,
        "output": 10.00,
        "batch_input": 1.00,
        "batch_output": 5.00,
        "context": 1_000_000,
        "max_output": 128_000,
        "source": "https://platform.claude.com/docs/en/about-claude/pricing",
        "max_output_source": "https://docs.anthropic.com/en/docs/about-claude/models",
    },
    "gemini-3.8-flash": {
        "display": "Gemini 3.8 Flash (intro through 2026-12-31)",
        "input": 0.75,
        "output": 3.75,
        "batch_input": 0.375,
        "batch_output": 1.875,
        "context": 1_048_576,
        "max_output": 65_536,
        "source": "https://ai.google.dev/gemini-api/docs/pricing",
        "max_output_source": "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash",
    },
    "gpt-5-nano": {
        "display": "GPT-5 nano (nearest small OpenAI model)",
        "input": 0.05,
        "output": 0.40,
        "batch_input": 0.025,
        "batch_output": 0.20,
        "context": 400_000,
        "max_output": 128_000,
        "source": "https://platform.openai.com/docs/pricing",
        "max_output_source": "https://developers.openai.com/api/docs/models/gpt-5-nano",
    },
    "local-16gb": {
        "display": "Local resident 27B on a 16 GB card",
        "input": 0.0,
        "output": 0.0,
        "batch_input": 0.0,
        "batch_output": 0.0,
        "context": 32_000,
        "max_output": None,
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


def _spread_clips(rows: list[dict], n: int) -> list[dict]:
    """Same rule as uoink_mcp_tools._spread_clips."""
    if len(rows) <= n:
        return list(rows)
    picked = []
    for i in range(n):
        lo = (i * len(rows)) // n
        hi = ((i + 1) * len(rows)) // n
        bucket = rows[lo:hi] or rows[lo:lo + 1]
        picked.append(
            max(
                bucket,
                key=lambda r: (len(r.get("text") or ""), -(r.get("start") or 0)),
            )
        )
    picked.sort(key=lambda r: (r.get("start") or 0, r.get("seq") or 0))
    return picked


def _summary_hint(corpus_path: str | None) -> str | None:
    """Same rule as uoink_mcp_tools._summary_hint. Best-effort; missing file -> None."""
    if not isinstance(corpus_path, str) or not corpus_path:
        return None
    try:
        with open(corpus_path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(SUMMARY_HINT_READ_BYTES)
    except OSError:
        return None
    kept = [
        line.strip()
        for line in head.splitlines()
        if line.strip() and not MD_META_LINE_RE.match(line)
    ]
    body = " ".join(kept).strip()
    if not body:
        return None
    if len(body) > SUMMARY_HINT_CHARS:
        body = body[:SUMMARY_HINT_CHARS].rsplit(" ", 1)[0] + "…"
    return body


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


def card_text(card: dict) -> str:
    lines = [
        f"### {card['video_id']}",
        f"title: {card['title'] or ''}",
        (
            f"channel: {card['channel'] or ''} · "
            f"source: {card['platform'] or card['source_type'] or 'unknown'} · "
            f"saved: {str(card['yoinked_at'] or '')[:10]}"
        ),
    ]
    if card.get("summary_hint"):
        lines.append(f"summary: {card['summary_hint']}")
    for c in card["clips"]:
        start = c.get("start")
        try:
            t = round(float(start or 0))
        except (TypeError, ValueError):
            t = 0
        text = re.sub(r"\s+", " ", c.get("text") or "").strip()
        lines.append(f"[{t}s] {text}")
    return "\n".join(lines)


def build_cards(conn: sqlite3.Connection, n_clips: int = N_CLIPS_DEFAULT) -> list[dict]:
    rows = conn.execute(
        "SELECT video_id, slug, title, channel, topic, hook_type, yoinked_at, "
        "source_type, platform, author, metadata_json, corpus_path "
        "FROM yoinks WHERE deleted_at IS NULL ORDER BY yoinked_at"
    ).fetchall()
    have_clips = (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clips'"
        ).fetchone()
        is not None
    )
    cards = []
    for y in rows:
        vid = y["video_id"]
        if have_clips:
            clip_rows = conn.execute(
                "SELECT start, end, text, source_deep_link, seq FROM clips "
                "WHERE video_id=? ORDER BY seq",
                (vid,),
            ).fetchall()
        else:
            clip_rows = []
        all_clips = [dict(c) for c in clip_rows]
        chosen = _spread_clips(all_clips, n_clips)
        meta: dict = {}
        try:
            loaded = json.loads(y["metadata_json"] or "{}")
            if isinstance(loaded, dict):
                meta = loaded
        except (TypeError, json.JSONDecodeError):
            meta = {}
        hint = _summary_hint(y["corpus_path"])
        cards.append(
            {
                "video_id": vid,
                "slug": y["slug"],
                "title": y["title"],
                "channel": y["channel"] or y["author"],
                "current_topic": y["topic"],
                "yoinked_at": y["yoinked_at"],
                "source_type": y["source_type"],
                "platform": y["platform"],
                "url": meta.get("url") if isinstance(meta.get("url"), str) else None,
                "summary_hint": hint,
                "clips": [
                    {
                        "start": c.get("start"),
                        "end": c.get("end"),
                        "text": c.get("text"),
                        "deep_link": c.get("source_deep_link"),
                    }
                    for c in chosen
                ],
                "clip_count": len(all_clips),
                "chars_all_clips": sum(len(c.get("text") or "") for c in all_clips),
                "chars_chosen_clips": sum(len(c.get("text") or "") for c in chosen),
            }
        )
    return cards


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


class CardDoesNotFitError(ValueError):
    """A single evidence card cannot fit in the model's request budget."""


class PackedAssign(NamedTuple):
    total_input_tokens: float
    n_calls: int
    batch_sizes: list[int]
    batch_input_tokens: list[float]
    batch_output_tokens: list[int]
    max_batch_request_tokens: float

    @property
    def cards_per_call(self) -> int:
        return max(self.batch_sizes) if self.batch_sizes else 0


def _batch_request_tokens(
    *,
    overhead: float,
    card_tokens: list[float],
    output_tokens_per_card: int,
    separator_tokens: float,
) -> tuple[float, int, float]:
    n = len(card_tokens)
    separators = separator_tokens * max(0, n - 1)
    output_tokens = output_tokens_per_card * n
    input_tokens = overhead + sum(card_tokens) + separators
    return input_tokens, output_tokens, input_tokens + output_tokens


def _batch_fits(
    card_tokens: list[float],
    *,
    overhead: float,
    output_tokens_per_card: int,
    separator_tokens: float,
    context: int,
    max_output: int | None,
) -> bool:
    if not card_tokens:
        return True
    input_tokens, output_tokens, request_tokens = _batch_request_tokens(
        overhead=overhead,
        card_tokens=card_tokens,
        output_tokens_per_card=output_tokens_per_card,
        separator_tokens=separator_tokens,
    )
    if request_tokens > context:
        return False
    if max_output is not None and output_tokens > max_output:
        return False
    return True


def pack_assign_batches(
    card_token_list: list[float],
    prompt_tokens: float,
    taxonomy_tokens: float,
    context: int,
    *,
    forced_batch: int | None = None,
    output_tokens_per_card: int = ASSIGN_OUTPUT_TOKENS_PER_CARD,
    max_output: int | None = None,
    separator_tokens: float = CARD_SEPARATOR_TOKENS,
) -> PackedAssign:
    """First-fit pack cards against the real request budget.

    A request is prompt + taxonomy + serialized cards + reserved output.
    Output is ``output_tokens_per_card`` per card in that request, and
    must also stay under ``max_output`` when the model publishes a cap.
    A card that cannot fit alone raises ``CardDoesNotFitError``.
    """
    if context <= 0:
        raise CardDoesNotFitError(f"context must be positive, got {context}")
    if not card_token_list:
        return PackedAssign(0.0, 0, [], [], [], 0.0)

    overhead = prompt_tokens + taxonomy_tokens
    forced_cap = None if forced_batch is None else max(1, forced_batch)

    def fits(batch: list[float]) -> bool:
        return _batch_fits(
            batch,
            overhead=overhead,
            output_tokens_per_card=output_tokens_per_card,
            separator_tokens=separator_tokens,
            context=context,
            max_output=max_output,
        )

    for i, tok in enumerate(card_token_list):
        if fits([tok]):
            continue
        input_tokens, output_tokens, request_tokens = _batch_request_tokens(
            overhead=overhead,
            card_tokens=[tok],
            output_tokens_per_card=output_tokens_per_card,
            separator_tokens=separator_tokens,
        )
        extra = f", max_output={max_output}" if max_output is not None else ""
        raise CardDoesNotFitError(
            f"card[{i}] does not fit: card={tok:.1f} tokens, "
            f"overhead={overhead:.1f} (prompt {prompt_tokens:.1f} + "
            f"taxonomy {taxonomy_tokens:.1f}), reserved_output="
            f"{output_tokens}, request={request_tokens:.1f} against "
            f"context={context}{extra}"
        )

    batches: list[list[float]] = []
    current: list[float] = []
    for tok in card_token_list:
        candidate = current + [tok]
        over_forced = forced_cap is not None and len(candidate) > forced_cap
        if current and (over_forced or not fits(candidate)):
            batches.append(current)
            current = [tok]
        else:
            current = candidate
    if current:
        batches.append(current)

    batch_sizes = [len(b) for b in batches]
    batch_input: list[float] = []
    batch_output: list[int] = []
    for batch in batches:
        input_tokens, output_tokens, request_tokens = _batch_request_tokens(
            overhead=overhead,
            card_tokens=batch,
            output_tokens_per_card=output_tokens_per_card,
            separator_tokens=separator_tokens,
        )
        if request_tokens > context or (
            max_output is not None and output_tokens > max_output
        ):
            raise CardDoesNotFitError(
                f"internal packing overflow: request={request_tokens:.1f} "
                f"context={context} output={output_tokens} max_output={max_output}"
            )
        batch_input.append(input_tokens)
        batch_output.append(output_tokens)

    max_request = max(
        inp + out for inp, out in zip(batch_input, batch_output)
    )
    return PackedAssign(
        total_input_tokens=sum(batch_input),
        n_calls=len(batches),
        batch_sizes=batch_sizes,
        batch_input_tokens=batch_input,
        batch_output_tokens=batch_output,
        max_batch_request_tokens=max_request,
    )


def assign_input_tokens(
    card_token_list: list[float],
    prompt_tokens: float,
    taxonomy_tokens: float,
    context: int,
    *,
    forced_batch: int | None = None,
    output_tokens_per_card: int = ASSIGN_OUTPUT_TOKENS_PER_CARD,
    max_output: int | None = None,
) -> tuple[float, int, int]:
    """Return (total_input_tokens, n_calls, max_cards_per_call)."""
    packed = pack_assign_batches(
        card_token_list,
        prompt_tokens,
        taxonomy_tokens,
        context,
        forced_batch=forced_batch,
        output_tokens_per_card=output_tokens_per_card,
        max_output=max_output,
    )
    return packed.total_input_tokens, packed.n_calls, packed.cards_per_call


def induce_fits_context(
    induce_input: float,
    *,
    context: int,
    induce_output: float = INDUCE_OUTPUT_TOKENS_ASSUMED,
    max_output: int | None = None,
) -> bool:
    if induce_input + induce_output > context:
        return False
    if max_output is not None and induce_output > max_output:
        return False
    return True


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
        max_output = model.get("max_output")
        packed = pack_assign_batches(
            card_tokens,
            assign_prompt_tokens,
            taxonomy_tokens,
            context,
            max_output=max_output,
        )
        dry = pack_assign_batches(
            card_tokens,
            assign_prompt_tokens,
            taxonomy_tokens,
            context,
            forced_batch=DRYRUN_BATCH,
            max_output=max_output,
        )
        induce_ok = induce_fits_context(
            induce_input, context=context, max_output=max_output
        )
        packing = {
            "batch_sizes": packed.batch_sizes,
            "max_cards_per_call": packed.cards_per_call,
            "max_request_tokens": round(packed.max_batch_request_tokens, 1),
            "batch_input_tokens": [round(x, 1) for x in packed.batch_input_tokens],
            "batch_output_tokens": packed.batch_output_tokens,
            "induce_fits": induce_ok,
            "induce_request_tokens": round(
                induce_input + INDUCE_OUTPUT_TOKENS_ASSUMED, 1
            ),
        }
        entry = {
            "context": context,
            "max_output": max_output,
            "packed_cards_per_call": packed.cards_per_call,
            "packed_batch_sizes": packed.batch_sizes,
            "dryrun_cards_per_call": dry.cards_per_call,
            "dryrun_batch_sizes": dry.batch_sizes,
            "packing": packing,
        }
        if key == "local-16gb":
            entry["packed"] = price_pass(
                induce_input=induce_input,
                assign_input=packed.total_input_tokens,
                assign_calls=packed.n_calls,
                n_cards=n,
                model=model,
                use_batch=False,
            )
            entry["dryrun_batches"] = price_pass(
                induce_input=induce_input,
                assign_input=dry.total_input_tokens,
                assign_calls=dry.n_calls,
                n_cards=n,
                model=model,
                use_batch=False,
            )
        else:
            entry["list_packed"] = price_pass(
                induce_input=induce_input,
                assign_input=packed.total_input_tokens,
                assign_calls=packed.n_calls,
                n_cards=n,
                model=model,
                use_batch=False,
            )
            entry["batch_packed"] = price_pass(
                induce_input=induce_input,
                assign_input=packed.total_input_tokens,
                assign_calls=packed.n_calls,
                n_cards=n,
                model=model,
                use_batch=True,
            )
            entry["list_dryrun_batches"] = price_pass(
                induce_input=induce_input,
                assign_input=dry.total_input_tokens,
                assign_calls=dry.n_calls,
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
    within_2x = ratio is not None and ratio <= 2.0
    estimated_tokens = {
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
    }

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
        "estimated_tokens": estimated_tokens,
        "reported_usage": None,
        "paid_cost": None,
        "assumptions": {
            "assign_output_tokens_per_card": ASSIGN_OUTPUT_TOKENS_PER_CARD,
            "induce_output_tokens": INDUCE_OUTPUT_TOKENS_ASSUMED,
            "induce_output_label": "ASSUMED (no model called)",
            "assign_output_label": "STATED by dispatch",
            "card_input_label": "ESTIMATED from index copy (chars/4 or tiktoken)",
            "no_prompt_cache": True,
            "no_thinking_tokens": True,
            "no_model_called": True,
        },
        "council_estimate_usd_per_500_haiku": COUNCIL_HAIKU_USD_PER_500,
        "g4": {
            "metric": "Haiku 4.5 Message Batches API, first-fit packed assign + induce 60",
            "status": "forecast",
            "estimated_usd_per_500": haiku_batch_per_500,
            "estimate_usd_per_500": COUNCIL_HAIKU_USD_PER_500,
            "ratio": round(ratio, 4) if ratio is not None else None,
            "within_2x": within_2x,
            "verdict": G4_FORECAST_WITHIN if within_2x else G4_FORECAST_OUTSIDE,
            "reported_usage": None,
            "paid_cost": None,
            "operational_gate": "pending measured usage",
        },
        "prices": priced,
        "prompts_dir": str(PROMPTS),
    }


def _fmt_usd(x: float | None) -> str:
    if x is None:
        return "n/a"
    if x == 0:
        return "$0"
    if x < 0.01:
        return f"${x:.4f}"
    return f"${x:.2f}"


def _fmt_batch_shape(block: dict, priced: dict) -> str:
    sizes = block.get("packed_batch_sizes") or []
    n_calls = priced["assign_calls"]
    if not sizes:
        return f"{n_calls} assign calls"
    lo, hi = min(sizes), max(sizes)
    packing = block.get("packing") or {}
    max_req = packing.get("max_request_tokens")
    if lo == hi:
        shape = f"{n_calls} assign calls of {hi}"
    else:
        shape = f"{n_calls} assign calls, batches {lo}–{hi} cards"
    if max_req is not None:
        shape += f" (max request {max_req:.0f} tokens)"
    if packing.get("induce_fits") is False:
        shape += "; induce-60 does not fit this context"
    return shape


def render_text(report: dict) -> str:
    lines = []
    g4 = report["g4"]
    lines.append(g4["verdict"])
    lines.append(
        f"{g4['metric']} = "
        f"{_fmt_usd(g4['estimated_usd_per_500'])} / 500 items "
        f"(council {_fmt_usd(g4['estimate_usd_per_500'])}, "
        f"ratio {g4['ratio']}x). "
        f"estimated_tokens only; reported_usage="
        f"{report['reported_usage']!r}; paid_cost={report['paid_cost']!r}."
    )
    lines.append(
        f"Index {report['index']}: {report['cards']} cards, "
        f"{report['items_with_clips']} with clips, "
        f"{report['clips_in_index']} clip rows, "
        f"{report['items_with_summary_hint']} with a summary hint."
    )
    ch = report["characters"]
    tk = report["estimated_tokens"]
    lines.append(
        f"Card text {ch['card_text_total']:,} chars "
        f"(mean {ch['card_text_mean']}), "
        f"estimated_tokens {tk['basis']} mean {tk['per_card_mean']} / card, "
        f"chars/4 total {tk['chars4_total_cards']}."
    )
    if tk["tiktoken_total_cards"] is not None:
        lines.append(
            f"tiktoken total card tokens: {tk['tiktoken_total_cards']:,}."
        )
    lines.append(
        f"Induce input (60 cards + prompt): {tk['induce_input']} tokens. "
        f"Assign output STATED {tk['assign_output_stated_total']:,} "
        f"({tk['assign_output_stated_per_card']}/card). "
        f"Induce output ASSUMED {tk['induce_output_assumed']:,}."
    )
    lines.append(f"Prompts read from {report.get('prompts_dir', PROMPTS)}.")
    lines.append("")
    lines.append("First-fit packed context (list / batch) for one induce+assign pass:")
    for key, spec in MODELS.items():
        block = report["prices"][key]
        if key == "local-16gb":
            p = block["packed"]
            h = p["hours_16gb"] or {}
            lines.append(
                f"  {spec['display']}: $0 · "
                f"{_fmt_batch_shape(block, p)} · "
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
            f"{_fmt_batch_shape(block, lst)}"
        )
    lines.append("")
    lines.append("Haiku list, dry-run 12-card batches (client-loop shape):")
    dry = report["prices"]["claude-haiku-4.5"]["list_dryrun_batches"]
    dry_block = report["prices"]["claude-haiku-4.5"]
    dry_sizes = dry_block.get("dryrun_batch_sizes") or []
    if dry_sizes and min(dry_sizes) == max(dry_sizes):
        dry_shape = f"{dry['assign_calls']} calls of {dry_sizes[0]}"
    elif dry_sizes:
        dry_shape = (
            f"{dry['assign_calls']} calls, batches "
            f"{min(dry_sizes)}–{max(dry_sizes)}"
        )
    else:
        dry_shape = f"{dry['assign_calls']} calls"
    lines.append(
        f"  {dry_shape} · {_fmt_usd(dry['usd_total'])} "
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

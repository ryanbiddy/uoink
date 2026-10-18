#!/usr/bin/env python3
"""
scripts/librarian/bench_local.py - Local LM Studio Benchmark Harness

Evaluates local models (default: qwen3.8-27b at http://localhost:1235/v1) on
Stage 2 Taxonomy Assignment against the 60-item gold set (docs/library/gold-set-2026-09-04.json).

Measures:
- Level 1 (Top Shelf) Agreement
- Level 2 (Sub-Shelf) Agreement
- Generation throughput (tokens/second)
- Wall-clock latency per item (seconds)
- Evidence quote grounding rate

Handles endpoint downtime gracefully:
If GET /v1/models fails or times out, it prints a clear status message ('not run: endpoint down')
and exits without fabricating results. A `--mock` flag is provided to test harness execution end-to-end.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import library_cards

DEFAULT_BASE_URL = "http://localhost:1235/v1"
DEFAULT_MODEL = "qwen3.8-27b"
DEFAULT_GOLD_SET = ROOT / "docs" / "library" / "gold-set-2026-09-04.json"
DEFAULT_PROMPT = ROOT / "scripts" / "librarian" / "prompts" / "assign.md"


def check_endpoint_health(base_url: str, timeout: float = 3.0) -> Tuple[bool, str]:
    """Checks if the OpenAI-compatible endpoint is running via GET /v1/models."""
    url = f"{base_url.rstrip('/')}/models"
    req = urllib.request.Request(url, headers={"User-Agent": "uoink-bench-local/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8")
                try:
                    data = json.loads(body)
                    models = [m.get("id") for m in data.get("data", []) if "id" in m]
                    return True, f"Online ({len(models)} models available: {', '.join(models[:5])})"
                except Exception:
                    return True, "Online (200 OK)"
            return False, f"Unexpected HTTP status {resp.status}"
    except urllib.error.URLError as e:
        return False, f"Connection failed: {e.reason}"
    except Exception as e:
        return False, f"Error: {e}"


def format_taxonomy_block(gold_items: List[Dict[str, Any]]) -> str:
    """Extracts unique hierarchy paths from the gold set to populate {{TAXONOMY}}."""
    unique_paths = sorted(set(tuple(item["shelf_path"]) for item in gold_items if item.get("shelf_path")))
    lines = []
    current_top = None
    for path in unique_paths:
        top = path[0]
        sub = path[1] if len(path) > 1 else "General"
        leaf = path[2] if len(path) > 2 else "Overview"
        if top != current_top:
            lines.append(f"\n### {top}")
            current_top = top
        lines.append(f"- **{' > '.join(path)}**: Focused on {sub.lower()} applications and {leaf.lower()}.")
    return "\n".join(lines).strip()


def format_card_for_prompt(item: Dict[str, Any]) -> Dict[str, Any]:
    """Builds the evidence card representation expected by assign.md.
    
    Ensures video_id is explicitly included in every returned card.
    """
    card = dict(item.get("card") or {})
    if not card:
        card = {
            "slug": item.get("slug", item["video_id"]),
            "title": item["title"],
            "channel": item["channel"],
            "platform": item["platform"],
            "summary_hint": item.get("summary_hint", item["title"]),
            "clips": [],
            "clip_count": 0,
            "chars": 0,
        }
    card["video_id"] = item["video_id"]
    return card


def send_chat_completion(
    base_url: str,
    model: str,
    prompt: str,
    timeout: float = 60.0,
) -> Tuple[str, Optional[int], float]:
    """Sends a chat completion request to the OpenAI-compatible endpoint.
    
    Measures latency across the entire response including reading the response body.
    Reports missing token usage as None (unavailable) rather than substituting word counts.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a media librarian assistant that classifies evidence cards into a taxonomy. Return valid JSON only conforming to the requested schema.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "uoink-bench-local/1.0"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp_bytes = resp.read()
        t1 = time.perf_counter()
    wall_time = t1 - t0
    resp_data = json.loads(resp_bytes.decode("utf-8"))
    choice = resp_data.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content", "")
    usage = resp_data.get("usage")
    if isinstance(usage, dict) and "completion_tokens" in usage and usage["completion_tokens"] is not None:
        try:
            completion_tokens: Optional[int] = int(usage["completion_tokens"])
        except (TypeError, ValueError):
            completion_tokens = None
    else:
        completion_tokens = None
    return content, completion_tokens, wall_time


def generate_mock_completion(
    item: Dict[str, Any],
    sim_agreement: float = 0.85,
    corrupt_id: Optional[str] = None,
) -> Tuple[str, Optional[int], float]:
    """Generates a synthetic completion for harness testing and verification."""
    # Deterministic pseudo-randomness based on video_id hash
    vid_hash = sum(ord(c) for c in item["video_id"])
    sim_match = (vid_hash % 100) < int(sim_agreement * 100)

    gold_path = item["shelf_path"]
    if sim_match:
        assigned_path = gold_path
    else:
        # Swap sub-shelf or level-1 to simulate model disagreement
        if len(gold_path) >= 2:
            assigned_path = [gold_path[0], "General", gold_path[-1]]
        else:
            assigned_path = ["General Topics", "Overview"]

    quote = item.get("evidence", "metadata-only")
    assigned_vid = corrupt_id if corrupt_id is not None else item["video_id"]
    mock_payload = {
        "assignments": [
            {
                "video_id": assigned_vid,
                "shelf_paths": [assigned_path],
                "confidence": 0.92 if sim_match else 0.65,
                "evidence_quote": quote,
                "unmapped": False,
                "proposed_new_leaf": "",
            }
        ]
    }
    content = json.dumps(mock_payload, indent=2)
    tokens = len(content.split()) + 40
    latency = max(0.2, tokens / 35.0)
    time.sleep(0.01)
    return content, tokens, latency


def _has_duplicates(items: List[Any]) -> bool:
    """Safely checks for duplicates even if items contains unhashable types."""
    try:
        return len(items) != len(set(items))
    except TypeError:
        seen: List[Any] = []
        for x in items:
            if any(x == s for s in seen):
                return True
            seen.append(x)
        return False


def evaluate_single_item(
    item: Dict[str, Any],
    pred_data: Dict[str, Any],
    wall_time: float,
    tokens: Optional[int],
) -> Dict[str, Any]:
    """Evaluates Level 1, Level 2 agreement and evidence quote grounding.
    
    Rejects wrong, missing, duplicate, and extra video_ids.
    Reports missing token usage as 'unavailable' rather than zero.
    """
    target_id = item["video_id"]
    gold_path = [p.strip().lower() for p in item.get("shelf_path", [])]

    # Validate assignments structure and reject wrong, missing, duplicate, or extra IDs
    if not isinstance(pred_data, dict) or not isinstance(pred_data.get("assignments"), list):
        id_status = "malformed_output"
        pred_item = None
    else:
        assignments = pred_data.get("assignments", [])
        if not all(isinstance(a, dict) for a in assignments):
            id_status = "malformed_output"
            pred_item = None
        elif not assignments:
            id_status = "missing_id"
            pred_item = None
        else:
            all_ids = [a.get("video_id") for a in assignments if a.get("video_id") is not None]
            has_dup = _has_duplicates(all_ids)
            matching = [a for a in assignments if a.get("video_id") == target_id]

            if has_dup or len(matching) > 1:
                id_status = "duplicate_id"
                pred_item = None
            elif len(matching) == 1:
                if len(assignments) == 1:
                    id_status = "valid"
                    pred_item = matching[0]
                else:
                    id_status = "extra_id"
                    pred_item = None
            else:
                if any(a.get("video_id") is not None for a in assignments):
                    id_status = "wrong_id"
                else:
                    id_status = "missing_id"
                pred_item = None

    id_valid = (id_status == "valid")
    l1_match = False
    l2_match = False
    evidence_valid = False
    pred_paths: List[Any] = []

    if id_valid and pred_item is not None:
        raw_paths = pred_item.get("shelf_paths", [])
        if isinstance(raw_paths, list):
            pred_paths = raw_paths
        primary_pred: List[str] = []
        if pred_paths and isinstance(pred_paths[0], list):
            # Run H acceptance case H-1: a path with any non-string or blank
            # component is malformed output and scores as a rejection. Silently
            # dropping the bad component would repair the model's answer for it.
            raw_primary = pred_paths[0]
            if raw_primary and all(isinstance(p, str) and p.strip() for p in raw_primary):
                primary_pred = [p.strip().lower() for p in raw_primary]

        if primary_pred and gold_path:
            l1_match = primary_pred[0] == gold_path[0]
            if l1_match and len(primary_pred) > 1 and len(gold_path) > 1:
                l2_match = primary_pred[1] == gold_path[1]

        # Grounding check: evidence quote must occur inside ONE excerpt
        evidence_quote = pred_item.get("evidence_quote", "")
        if not isinstance(evidence_quote, str):
            evidence_quote = ""
        card = item.get("card") or {}
        clips = card.get("clips") or card.get("excerpts") or []
        if clips:
            if evidence_quote and evidence_quote != "metadata-only":
                evidence_valid = any(
                    isinstance(c, dict)
                    and isinstance(c.get("text"), str)
                    and evidence_quote in c["text"]
                    for c in clips
                )
            else:
                evidence_valid = False
        else:
            evidence_valid = (
                evidence_quote in ("metadata-only", "")
                or pred_item.get("unsupported") is True
            )
    else:
        evidence_quote = ""

    if tokens is not None:
        tps: Any = round(tokens / wall_time, 2) if wall_time > 0 else 0.0
        tokens_val: Any = tokens
    else:
        tps = "unavailable"
        tokens_val = "unavailable"

    return {
        "video_id": target_id,
        "title": item["title"],
        "platform": item["platform"],
        "gold_path": item.get("shelf_path", []),
        "predicted_path": pred_paths[0] if (pred_paths and isinstance(pred_paths[0], list)) else [],
        "l1_match": l1_match,
        "l2_match": l2_match,
        "evidence_quote": evidence_quote,
        "evidence_valid": evidence_valid,
        "id_status": id_status,
        "id_valid": id_valid,
        "wall_time_sec": round(wall_time, 3),
        "completion_tokens": tokens_val,
        "tokens_per_sec": tps,
    }


def run_benchmark(
    base_url: str,
    model: str,
    gold_path: Path,
    prompt_path: Path,
    limit: Optional[int] = None,
    mock: bool = False,
    mock_wrong_id: bool = False,
    timeout: float = 60.0,
    output_path: Optional[Path] = None,
) -> int:
    """Main benchmark execution routine."""
    if sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print(f"=== Uoink Librarian Local Benchmark ===")
    print(f"Base URL:      {base_url}")
    print(f"Target Model:  {model}")
    print(f"Gold Set:      {gold_path}")
    print(f"Assign Prompt: {prompt_path}")
    print(f"Mock Mode:     {mock} (wrong_id={mock_wrong_id})")
    print("=" * 40)

    if not gold_path.exists():
        print(f"[ERROR] Gold set file not found: {gold_path}")
        return 1

    with open(gold_path, "r", encoding="utf-8") as f:
        gold_items = json.load(f)

    if limit and limit > 0:
        gold_items = gold_items[:limit]
        print(f"Evaluating subset of {len(gold_items)} items (--limit {limit})")
    else:
        print(f"Evaluating complete gold set ({len(gold_items)} items)")

    # 1. Endpoint Health Check
    if not mock:
        print("\nChecking LM Studio endpoint status...")
        is_up, status_msg = check_endpoint_health(base_url)
        if not is_up:
            print(f"[STATUS] not run: endpoint down ({status_msg})")
            print(f"LM Studio is not listening on {base_url}.")
            print("To verify the benchmark evaluation harness, rerun with: python scripts/librarian/bench_local.py --mock")
            return 0
        print(f"[STATUS] Endpoint is {status_msg}")
    else:
        print("\n[STATUS] Running in MOCK mode (simulated endpoint responses).")

    # 2. Prepare Prompt Template
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    taxonomy_block = format_taxonomy_block(gold_items)
    base_prompt = prompt_template.replace("{{TAXONOMY}}", taxonomy_block)

    results = []
    measured_tokens = 0
    measured_tokens_count = 0
    total_wall_time = 0.0

    print("\nRunning Stage 2 Assignment evaluation...")
    for idx, item in enumerate(gold_items, 1):
        card_obj = format_card_for_prompt(item)
        cards_str = library_cards.card_text(card_obj)
        full_prompt = base_prompt.replace("{{CARDS}}", cards_str)

        try:
            if mock:
                content, tokens, wall_time = generate_mock_completion(
                    item, corrupt_id="WRONG_ITEM_ID" if mock_wrong_id else None
                )
            else:
                content, tokens, wall_time = send_chat_completion(
                    base_url=base_url,
                    model=model,
                    prompt=full_prompt,
                    timeout=timeout,
                )

            pred_data = json.loads(content)
            eval_res = evaluate_single_item(item, pred_data, wall_time, tokens)
            results.append(eval_res)

            if tokens is not None:
                measured_tokens += tokens
                measured_tokens_count += 1
            total_wall_time += wall_time

            l1_sym = "✓" if eval_res["l1_match"] else "✗"
            l2_sym = "✓" if eval_res["l2_match"] else "✗"
            tps_str = (
                f"{eval_res['tokens_per_sec']:.1f} tps"
                if isinstance(eval_res["tokens_per_sec"], (int, float))
                else "tps: unavailable"
            )
            print(
                f"[{idx:02d}/{len(gold_items):02d}] {item['video_id'][:16]} | "
                f"ID: {eval_res['id_status']} | L1: {l1_sym} | L2: {l2_sym} | "
                f"{wall_time:.2f}s | {tps_str}"
            )

        except Exception as e:
            print(f"[{idx:02d}/{len(gold_items):02d}] {item['video_id'][:16]} | ERROR: {e}")
            results.append({
                "video_id": item["video_id"],
                "title": item["title"],
                "platform": item["platform"],
                "gold_path": item.get("shelf_path", []),
                "predicted_path": [],
                "l1_match": False,
                "l2_match": False,
                "evidence_quote": "",
                "evidence_valid": False,
                "id_status": "error",
                "id_valid": False,
                "wall_time_sec": 0.0,
                "completion_tokens": "unavailable",
                "tokens_per_sec": "unavailable",
                "error": str(e),
            })

    # 3. Calculate Summary Metrics
    total_evaluated = len(results)
    l1_matches = sum(1 for r in results if r["l1_match"])
    l2_matches = sum(1 for r in results if r["l2_match"])
    grounded_matches = sum(1 for r in results if r["evidence_valid"])

    l1_pct = (l1_matches / total_evaluated * 100.0) if total_evaluated else 0.0
    l2_pct = (l2_matches / total_evaluated * 100.0) if total_evaluated else 0.0
    ground_pct = (grounded_matches / total_evaluated * 100.0) if total_evaluated else 0.0

    avg_latency = (total_wall_time / total_evaluated) if total_evaluated else 0.0
    if measured_tokens_count == total_evaluated and total_evaluated > 0:
        avg_tps = (measured_tokens / total_wall_time) if total_wall_time > 0 else 0.0
        tps_display = f"{avg_tps:.1f} tokens/sec"
        tps_summary: Any = round(avg_tps, 2)
        tokens_summary: Any = measured_tokens
    elif measured_tokens_count > 0:
        avg_tps = (measured_tokens / total_wall_time) if total_wall_time > 0 else 0.0
        tps_display = f"{avg_tps:.1f} tokens/sec ({measured_tokens_count}/{total_evaluated} measured)"
        tps_summary = round(avg_tps, 2)
        tokens_summary = f"{measured_tokens} ({measured_tokens_count}/{total_evaluated} measured)"
    else:
        tps_display = "unavailable"
        tps_summary = "unavailable"
        tokens_summary = "unavailable"

    print("\n" + "=" * 40)
    print("=== BENCHMARK RESULTS SUMMARY ===")
    print(f"Items Evaluated:         {total_evaluated}")
    print(f"Level 1 Agreement:       {l1_matches}/{total_evaluated} ({l1_pct:.1f}%)")
    print(f"Level 2 Agreement:       {l2_matches}/{total_evaluated} ({l2_pct:.1f}%)")
    print(f"Evidence Grounding:      {grounded_matches}/{total_evaluated} ({ground_pct:.1f}%)")
    print(f"Total Wall Time:         {total_wall_time:.2f}s")
    print(f"Mean Latency Per Item:   {avg_latency:.2f}s")
    print(f"Overall Throughput:      {tps_display}")
    print(f"Reported Tokens:         {tokens_summary}")
    print("=" * 40)

    summary_data = {
        "status": "completed" if not mock else "completed_mock",
        "mock_mode": mock,
        "mock_wrong_id": mock_wrong_id,
        "base_url": base_url,
        "model": model,
        "total_items": total_evaluated,
        "level_1_accuracy": round(l1_pct, 2),
        "level_2_accuracy": round(l2_pct, 2),
        "evidence_grounding_accuracy": round(ground_pct, 2),
        "total_wall_time_sec": round(total_wall_time, 3),
        "mean_latency_per_item_sec": round(avg_latency, 3),
        "tokens_per_second": tps_summary,
        "total_completion_tokens": tokens_summary,
        "measured_tokens_count": measured_tokens_count,
        "item_results": results,
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)
        print(f"Detailed results saved to: {output_path}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Local LM Studio benchmark harness for Living Library taxonomy assignment."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LM Studio API base URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Target model identifier")
    parser.add_argument("--gold-set", type=Path, default=DEFAULT_GOLD_SET, help="Path to gold set JSON")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT, help="Path to assign.md prompt")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to test")
    parser.add_argument("--mock", action="store_true", help="Run with synthetic responses for test verification")
    parser.add_argument("--mock-wrong-id", action="store_true", help="Simulate wrong ID responses in mock mode")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP request timeout in seconds")
    parser.add_argument("--output", type=Path, default=None, help="Save evaluation metrics to JSON file")

    args = parser.parse_args()
    sys.exit(
        run_benchmark(
            base_url=args.base_url,
            model=args.model,
            gold_path=args.gold_set,
            prompt_path=args.prompt,
            limit=args.limit,
            mock=args.mock,
            mock_wrong_id=args.mock_wrong_id,
            timeout=args.timeout,
            output_path=args.output,
        )
    )


if __name__ == "__main__":
    main()

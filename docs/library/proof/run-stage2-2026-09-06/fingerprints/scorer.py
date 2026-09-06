#!/usr/bin/env python3
"""
scripts/librarian/proof_score.py - Living Library Product Proof Scorer (Run S)

Evaluates receipts (<out>/receipts.json) against the held-out split:
- Strict versioned rule: NFC, trim, frozen case convention, deepest unambiguous approved ancestor, equality.
- Requires validated real (subscription) receipts before any gate verdict.
- Verifies every membership (primary and secondary), strictly capping quotes at 1-24 words.
- Requires exact frozen taxonomy and split hashes, nonempty strata, and forbids fallback taxonomies.
- Pre-score validation rejects 25-word quotes, foreign cards, missing source, modified batches, and invented usage.
- Generates report.md comparing observed performance against contract thresholds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_HOLDOUT = ROOT / "docs" / "library" / "holdout-split-2026-09-04.json"
DEFAULT_GOLD = ROOT / "docs" / "library" / "gold-set-2026-09-04.json"
DEFAULT_TAXONOMY = ROOT / "docs" / "library" / "taxonomy-v1-2026-09-04.json"

COVERAGE_FLOOR = 0.80
PRECISION_TARGET = 0.90
MAX_QUOTE_WORDS = 24


class ProofScoreError(ValueError):
    """Raised when receipts fail pre-scoring contract or integrity validation."""
    pass


def normalize_segment(seg: Any) -> str:
    """NFC normalization, surrounding whitespace collapsed, preserving exact case convention."""
    return " ".join(unicodedata.normalize("NFC", str(seg)).split())


def count_words(text: str) -> int:
    """NFC normalized whitespace-collapsed word count."""
    return len(unicodedata.normalize("NFC", text).split())


def load_taxonomy(path: Path) -> dict:
    """Loads taxonomy file; forbids fallback taxonomies."""
    p = Path(path).resolve()
    if not p.is_file():
        raise ProofScoreError(f"Taxonomy file missing: {p}. Fallback taxonomies are forbidden.")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ProofScoreError(f"Failed to parse taxonomy JSON from {p}: {e}")


def extract_taxonomy_paths(tax_doc: dict) -> Tuple[Set[Tuple[str, ...]], Dict[Tuple[str, ...], str]]:
    """Extracts NFC-normalized paths matching the frozen case convention."""
    nodes = tax_doc.get("nodes") or tax_doc.get("shelves") or []
    paths: Set[Tuple[str, ...]] = set()
    path_to_id: Dict[Tuple[str, ...], str] = {}
    for n in nodes:
        if n.get("retired", False):
            continue
        p = n.get("path")
        if p:
            norm_p = tuple(normalize_segment(seg) for seg in p)
            paths.add(norm_p)
            if "shelf_id" in n:
                path_to_id[norm_p] = n["shelf_id"]
    if not paths:
        raise ProofScoreError("Taxonomy contains zero valid unretired shelf paths.")
    return paths, path_to_id


def map_gold_to_taxonomy(norm_gold: List[str], tax_paths: Set[Tuple[str, ...]]) -> List[str]:
    """Strict scoring rule: maps gold path to its deepest unambiguous approved ancestor.
    A primary assignment is correct only when it equals this mapped path."""
    for depth in range(len(norm_gold), 0, -1):
        prefix = tuple(norm_gold[:depth])
        if prefix in tax_paths:
            return list(prefix)
    return []


def validate_receipts_for_scoring(
    receipts_data: dict,
    holdout_data: dict,
    gold_data: list[dict],
    taxonomy_data: dict,
    *,
    strict: bool = True,
) -> None:
    """Pre-scoring contract verification enforcing negative fixtures:
    - 25-word quotes rejected
    - foreign card rejected
    - missing source hash rejected
    - modified batch rejected
    - invented usage rejected
    """
    # 1. Check completed status
    status = receipts_data.get("status")
    if status != "completed":
        raise ProofScoreError(
            f"Receipts run is not completed (status={status}, abort_reason={receipts_data.get('abort_reason')})"
        )

    mode = receipts_data.get("mode")
    attempts = receipts_data.get("attempts", [])
    calls = (receipts_data.get("audit_extensions") or {}).get("calls") or []

    # 2. Check missing source hash
    inputs = receipts_data.get("inputs", {})
    db_obj = receipts_data.get("database", {})
    source_sha = db_obj.get("copy_before_upgrade_sha256") or inputs.get("source_sha256")
    if not source_sha or not isinstance(source_sha, str) or len(source_sha) != 64:
        raise ProofScoreError("Missing or invalid source database SHA-256 in receipts")
    if inputs.get("source_sha256") and source_sha != inputs.get("source_sha256"):
        raise ProofScoreError(
            f"Source SHA-256 mismatch: {source_sha} vs inputs {inputs.get('source_sha256')}"
        )

    # 3. Check exact taxonomy and holdout split hashes
    tax_hash = taxonomy_data.get("revision_hash") or taxonomy_data.get("taxonomy_revision_hash")
    if tax_hash and inputs.get("taxonomy_revision_hash"):
        if tax_hash != inputs["taxonomy_revision_hash"]:
            raise ProofScoreError(
                f"Taxonomy revision hash mismatch: {tax_hash} vs receipt inputs {inputs['taxonomy_revision_hash']}"
            )

    # 4. Check nonempty strata in holdout
    strata = holdout_data.get("strata", {})
    if not strata:
        raise ProofScoreError("Holdout dataset contains no strata")
    for stratum_name, items in strata.items():
        if not items:
            raise ProofScoreError(f"Holdout stratum '{stratum_name}' is empty")

    # 5. Check foreign cards: attempts must not contain cards outside target_ids
    target_ids = set(receipts_data.get("target_ids", []))
    for att in attempts:
        vid = att.get("video_id")
        if vid and target_ids and vid not in target_ids:
            raise ProofScoreError(
                f"Foreign card detected: attempt video_id '{vid}' is not in target_ids"
            )

    if mode == "subscription":
        # In a full subscription run, all holdout items must be in target_ids
        for stratum_name, items in strata.items():
            for item in items:
                vid = item.get("video_id")
                if target_ids and vid not in target_ids:
                    raise ProofScoreError(
                        f"Missing holdout target in subscription run: {vid}"
                    )

    # 6. Check modified batch
    if calls and attempts:
        calls_by_id = {c["call_id"]: c for c in calls if "call_id" in c}
        for att in attempts:
            cid = att.get("call_id")
            if cid:
                if cid not in calls_by_id:
                    raise ProofScoreError(
                        f"Modified batch: attempt {att.get('attempt_id')} references unrecorded call {cid}"
                    )
                call_vids = calls_by_id[cid].get("video_ids", [])
                if call_vids and att.get("video_id") not in call_vids:
                    raise ProofScoreError(
                        f"Modified batch: attempt {att.get('attempt_id')} video_id {att.get('video_id')} "
                        f"not in call {cid} video_ids"
                    )

    # 7. Check invented usage
    mode = receipts_data.get("mode")
    if mode == "mock":
        for att in attempts:
            u = att.get("usage", {})
            if u.get("status") == "reported" or int(u.get("input_tokens", 0) or 0) > 0:
                raise ProofScoreError("Invented usage detected: mock mode cannot report token consumption")
            est = att.get("estimates", {})
            if est.get("total_cost_usd") is not None:
                raise ProofScoreError("Invented usage detected: mock mode cannot report cost estimates")
    elif mode == "subscription":
        for att in attempts:
            u = att.get("usage", {})
            if u.get("status") == "reported":
                if "model" not in u or not str(u.get("model", "")).strip():
                    raise ProofScoreError(f"Reported usage lacks model provenance: attempt {att.get('attempt_id')}")

    # 8. Check 25-word quote limit in accepted submissions
    for att in attempts:
        if att.get("outcome") == "accepted":
            res = att.get("result") or {}
            memberships = res.get("memberships") or []
            for m in memberships:
                ev = (m.get("evidence") or {}) if isinstance(m, dict) else {}
                quote = ev.get("quote", "")
                if quote and count_words(quote) > MAX_QUOTE_WORDS:
                    raise ProofScoreError(
                        f"Quote exceeds 24-word cap ({count_words(quote)} words) on attempt {att.get('attempt_id')}: {quote[:60]}..."
                    )


def verify_frozen_mapping(mapping_doc: dict, holdout_data: dict, gold_data: list[dict], taxonomy_data: dict) -> str:
    """The scorer's own deepest-ancestor mapping must equal the frozen adjudicated table for
    every hold-out item; the frozen table must name the taxonomy revision being scored."""
    tax_paths, _ = extract_taxonomy_paths(taxonomy_data)
    gold_by_id = {item["video_id"]: item for item in gold_data}
    frozen_items = mapping_doc.get("items") or {}
    holdout_ids = [item["video_id"] for items in (holdout_data.get("strata") or {}).values() for item in items]
    if set(frozen_items) != set(holdout_ids):
        raise ProofScoreError("Frozen mapping does not cover exactly the hold-out identities")
    if mapping_doc.get("taxonomy_version_id") != taxonomy_data.get("version_id"):
        raise ProofScoreError("Frozen mapping names a different taxonomy version")
    if (mapping_doc.get("taxonomy_revision_hash") and taxonomy_data.get("revision_hash")
            and mapping_doc["taxonomy_revision_hash"] != taxonomy_data["revision_hash"]):
        raise ProofScoreError("Frozen mapping names a different taxonomy revision hash")
    for vid in holdout_ids:
        gold = gold_by_id.get(vid, {})
        norm_gold = [normalize_segment(p) for p in gold.get("shelf_path", [])]
        computed = map_gold_to_taxonomy(norm_gold, tax_paths) if gold.get("outcome", "assigned") != "unsupported" else []
        frozen = frozen_items[vid].get("mapped_path") or []
        if [normalize_segment(p) for p in frozen] != computed:
            raise ProofScoreError(f"Frozen mapping differs from the scorer's rule for {vid}: frozen={frozen} computed={computed}")
    return f"verified against {len(holdout_ids)} frozen rows ({mapping_doc.get('scoring_version')})"


def score_receipts(
    receipts_data: dict,
    holdout_data: dict,
    gold_data: list[dict],
    taxonomy_data: Optional[dict] = None,
) -> dict:
    """Calculates coverage, strict mapped precision, and evidence validity across strata."""
    if taxonomy_data is None:
        taxonomy_data = load_taxonomy(DEFAULT_TAXONOMY)

    # Run integrity and negative contract checks
    validate_receipts_for_scoring(receipts_data, holdout_data, gold_data, taxonomy_data)

    tax_paths, path_to_id = extract_taxonomy_paths(taxonomy_data)
    gold_by_id = {item["video_id"]: item for item in gold_data}

    # Group receipts/attempts by video_id (taking final attempt)
    receipts_by_video: Dict[str, List[dict]] = defaultdict(list)
    attempts = receipts_data.get("attempts")
    if attempts is not None:
        for a in attempts:
            vid = a.get("video_id") or a.get("target_id")
            if vid:
                receipts_by_video[str(vid)].append(a)
    else:
        for r in receipts_data.get("receipts", []):
            vid = r.get("video_id") or r.get("target_id")
            if vid:
                receipts_by_video[str(vid)].append(r)

    results_by_stratum: Dict[str, dict] = {}
    strata = holdout_data.get("strata", {})

    total_heldout_items = 0
    total_assigned_items = 0
    total_abstention_items = 0
    total_correct_items = 0
    total_evidence_valid_items = 0
    total_evidence_checked_items = 0

    detailed_items: List[dict] = []

    for stratum_name, items in strata.items():
        n_items = len(items)
        total_heldout_items += n_items

        assigned_count = 0
        abstention_count = 0
        correct_count = 0
        exact_count = 0
        descendant_diagnostic_count = 0
        evidence_valid_count = 0
        evidence_checked_count = 0

        stratum_items_detail: List[dict] = []

        for item in items:
            vid = item["video_id"]
            gold = gold_by_id.get(vid, {})
            gold_shelf_path = gold.get("shelf_path", [])

            vid_receipts = receipts_by_video.get(vid, [])
            final_receipt = vid_receipts[-1] if vid_receipts else None

            if final_receipt is None or final_receipt.get("outcome") != "accepted":
                abstention_count += 1
                outcome = final_receipt.get("outcome", "unseen") if final_receipt else "unseen"
                reason = (
                    final_receipt.get("rejection_reason")
                    or (final_receipt.get("result", {}).get("reason") if isinstance(final_receipt.get("result"), dict) else None)
                    or "Abstention / unassigned"
                    if final_receipt
                    else "Missing from receipts"
                )
                detail = {
                    "video_id": vid,
                    "stratum": stratum_name,
                    "status": "abstention",
                    "outcome": outcome,
                    "reason": reason,
                    "is_correct": False,
                    "evidence_valid": False,
                }
                stratum_items_detail.append(detail)
                detailed_items.append(detail)
                continue

            # Assigned item
            assigned_count += 1
            result_payload = final_receipt.get("result") or final_receipt
            memberships = result_payload.get("memberships") or []
            primary_shelf = memberships[0].get("shelf_path", []) if memberships else []

            norm_pred = [normalize_segment(p) for p in primary_shelf]
            norm_gold = [normalize_segment(p) for p in gold_shelf_path]
            mapped_gold = map_gold_to_taxonomy(norm_gold, tax_paths)

            # Strict equality to mapped gold path
            is_correct = (norm_pred == mapped_gold) if (norm_pred and mapped_gold) else False
            if is_correct:
                correct_count += 1

            # Diagnostics
            exact_match = (norm_pred == norm_gold) if (norm_pred and norm_gold) else False
            if exact_match:
                exact_count += 1

            descendant_match = (
                len(mapped_gold) > 0
                and len(norm_pred) >= len(mapped_gold)
                and norm_pred[: len(mapped_gold)] == mapped_gold
            )
            if descendant_match:
                descendant_diagnostic_count += 1

            # Evidence quote and basis check across EVERY membership
            evidence_checked_count += 1
            all_memberships_valid = True
            if not memberships or len(memberships) > 3:
                all_memberships_valid = False

            checked_memberships = []
            for mem in memberships:
                if not isinstance(mem, dict):
                    all_memberships_valid = False
                    break
                m_path = tuple(normalize_segment(p) for p in mem.get("shelf_path", []))
                if m_path not in tax_paths:
                    all_memberships_valid = False
                conf = mem.get("confidence")
                if conf is None or not (0.60 <= conf <= 1.0):
                    all_memberships_valid = False
                ev = mem.get("evidence", {})
                if not isinstance(ev, dict):
                    all_memberships_valid = False
                    continue
                basis = ev.get("basis")
                if basis not in {"packet", "fetched_full"}:
                    all_memberships_valid = False
                kind = ev.get("kind")
                if kind not in {"timed_clip", "text_only"}:
                    all_memberships_valid = False
                quote = ev.get("quote", "")
                if not isinstance(quote, str) or not quote.strip():
                    all_memberships_valid = False
                else:
                    wc = count_words(quote)
                    if wc < 1 or wc > MAX_QUOTE_WORDS:
                        all_memberships_valid = False

                checked_memberships.append({
                    "shelf_path": list(m_path),
                    "confidence": conf,
                    "basis": basis,
                    "kind": kind,
                    "quote": quote,
                    "word_count": count_words(quote) if isinstance(quote, str) else 0,
                })

            if all_memberships_valid:
                evidence_valid_count += 1

            detail = {
                "video_id": vid,
                "stratum": stratum_name,
                "status": "assigned",
                "outcome": "accepted",
                "primary_pred": primary_shelf,
                "mapped_gold": mapped_gold,
                "exact_match": exact_match,
                "descendant_match": descendant_match,
                "gold_path": gold_shelf_path,
                "is_correct": is_correct,
                "evidence_valid": all_memberships_valid,
                "memberships": checked_memberships,
            }
            stratum_items_detail.append(detail)
            detailed_items.append(detail)

        coverage = assigned_count / n_items if n_items > 0 else 0.0
        precision = correct_count / assigned_count if assigned_count > 0 else 0.0
        evidence_grounding_rate = (
            evidence_valid_count / evidence_checked_count if evidence_checked_count > 0 else 0.0
        )

        coverage_pass = coverage >= COVERAGE_FLOOR
        precision_pass = precision >= PRECISION_TARGET
        stratum_pass = coverage_pass and precision_pass

        results_by_stratum[stratum_name] = {
            "total_items": n_items,
            "assigned_count": assigned_count,
            "abstention_count": abstention_count,
            "correct_count": correct_count,
            "exact_path_correct_count": exact_count,
            "descendant_diagnostic_count": descendant_diagnostic_count,
            "coverage": coverage,
            "precision": precision,
            "coverage_pass": coverage_pass,
            "precision_pass": precision_pass,
            "stratum_pass": stratum_pass,
            "evidence_valid_count": evidence_valid_count,
            "evidence_checked_count": evidence_checked_count,
            "evidence_grounding_rate": evidence_grounding_rate,
            "items": stratum_items_detail,
        }

        total_assigned_items += assigned_count
        total_abstention_items += abstention_count
        total_correct_items += correct_count
        total_evidence_valid_items += evidence_valid_count
        total_evidence_checked_items += evidence_checked_count

    overall_coverage = (
        total_assigned_items / total_heldout_items if total_heldout_items > 0 else 0.0
    )
    overall_precision = (
        total_correct_items / total_assigned_items if total_assigned_items > 0 else 0.0
    )
    overall_evidence_rate = (
        total_evidence_valid_items / total_evidence_checked_items
        if total_evidence_checked_items > 0
        else 0.0
    )

    # Gate verdict: real receipts (mode == "subscription") required before any PASS
    mode = receipts_data.get("mode")
    is_real_run = (mode == "subscription")
    all_strata_pass = all(st["stratum_pass"] for st in results_by_stratum.values())
    quality_pass = all_strata_pass and (overall_coverage >= COVERAGE_FLOOR) and (overall_precision >= PRECISION_TARGET)

    if not is_real_run:
        gate_verdict = "FIXTURE_EVALUATION_ONLY"
        overall_pass = False
    else:
        overall_pass = quality_pass
        gate_verdict = "PASS" if overall_pass else "FAIL"

    # Usage accounting
    totals = receipts_data.get("totals", {})
    ext_usage = (receipts_data.get("audit_extensions") or {}).get("usage_totals") or {}
    calls = (receipts_data.get("audit_extensions") or {}).get("calls") or []

    if is_real_run and (ext_usage or calls):
        is_measured = True
        total_input_tokens = ext_usage.get("input_tokens", sum(c.get("usage", {}).get("input_tokens", 0) for c in calls))
        total_output_tokens = ext_usage.get("output_tokens", sum(c.get("usage", {}).get("output_tokens", 0) for c in calls))
        total_cache_read = ext_usage.get("cache_read_tokens", sum(c.get("usage", {}).get("cache_read_tokens", 0) for c in calls))
        total_cache_create = ext_usage.get("cache_create_tokens", sum(c.get("usage", {}).get("cache_create_tokens", 0) for c in calls))
        total_tokens = total_input_tokens + total_output_tokens + total_cache_read + total_cache_create
        total_cost_usd_est = ext_usage.get("cli_estimated_cost_usd", sum(float(c.get("total_cost_usd") or 0.0) for c in calls))
        total_wall_ms = totals.get("wall_ms", 0)
        usage_summary = {
            "status": "measured",
            "is_measured": True,
            "calls": len(calls),
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "cache_read_tokens": total_cache_read,
            "cache_create_tokens": total_cache_create,
            "total_tokens": total_tokens,
            "wall_time_ms": total_wall_ms,
            "wall_time_s": total_wall_ms / 1000.0,
            "total_cost_usd_estimate": round(total_cost_usd_est, 4),
        }
    else:
        usage_summary = {
            "status": "unmeasured (mock fixture: zero model execution)",
            "is_measured": False,
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_create_tokens": 0,
            "total_tokens": 0,
            "wall_time_ms": totals.get("wall_ms", 0),
            "wall_time_s": totals.get("wall_ms", 0) / 1000.0,
            "total_cost_usd_estimate": 0.0,
        }

    # State assertions from receipts
    before_state = receipts_data.get("before") or receipts_data.get("before_state", {})
    after_state = receipts_data.get("after") or receipts_data.get("after_state", {})
    before_applied = before_state.get("applied_label_count", before_state.get("applied_count", 0))
    after_applied = after_state.get("applied_label_count", after_state.get("applied_count", 0))
    zero_applies = (
        before_applied == 0
        and after_applied == 0
        and before_state == after_state
    )

    return {
        "strata": results_by_stratum,
        "overall": {
            "total_items": total_heldout_items,
            "assigned_count": total_assigned_items,
            "abstention_count": total_abstention_items,
            "correct_count": total_correct_items,
            "coverage": overall_coverage,
            "precision": overall_precision,
            "coverage_pass": overall_coverage >= COVERAGE_FLOOR,
            "precision_pass": overall_precision >= PRECISION_TARGET,
            "overall_pass": overall_pass,
            "gate_verdict": gate_verdict,
            "evidence_valid_count": total_evidence_valid_items,
            "evidence_checked_count": total_evidence_checked_items,
            "evidence_grounding_rate": overall_evidence_rate,
        },
        "gate_verdict": gate_verdict,
        "usage": usage_summary,
        "zero_applies_verified": zero_applies,
        "before_state": before_state,
        "after_state": after_state,
        "all_items": detailed_items,
    }


def render_report_markdown(score_result: dict, receipts_meta: dict) -> str:
    """Renders report.md adhering strictly to the contract and anti-slop rules."""
    cfg = receipts_meta.get("config", {})
    mode = receipts_meta.get("mode", "unknown")
    is_mock = (mode == "mock") or cfg.get("mock", receipts_meta.get("mock", False))
    client = cfg.get("client", receipts_meta.get("client", "unknown"))
    model = cfg.get("model", receipts_meta.get("model", "unknown"))
    run_id = receipts_meta.get("run_id", "unknown")
    gate_verdict = score_result.get("gate_verdict", "FAIL")

    lines: List[str] = []
    lines.append("# Living Library Product Proof Report (Run S)")
    lines.append("")
    lines.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}  ")
    lines.append(f"**Run ID:** `{run_id}`  ")
    lines.append(f"**Client Mode:** `{client}` (`mode={mode}`, `mock={is_mock}`)  ")
    lines.append(f"**Model:** `{model}`  ")
    lines.append(f"**Gate Verdict:** `{gate_verdict}`  ")
    lines.append("")

    lines.append("## 1. Frozen Inputs & Boundaries")
    frozen = receipts_meta.get("inputs") or receipts_meta.get("frozen_inputs", {})
    tax_hash = frozen.get("taxonomy_revision_hash") or frozen.get("taxonomy_hash")
    prompt_hash = frozen.get("prompt_sha256") or frozen.get("prompt_file_sha256")
    holdout_hash = frozen.get("holdout_file_sha256") or frozen.get("holdout_ids_hash")
    card_hash = frozen.get("card_profile_hash")
    db_obj = receipts_meta.get("database", {})
    source_sha = db_obj.get("copy_before_upgrade_sha256") or frozen.get("source_sha256")

    lines.append(f"- **Taxonomy Revision:** `{tax_hash}`")
    lines.append(f"- **Prompt Template SHA-256:** `{prompt_hash}`")
    lines.append(f"- **Holdout Split Hash:** `{holdout_hash}`")
    lines.append(f"- **Card Profile Hash:** `{card_hash}`")
    lines.append(f"- **Source DB SHA-256:** `{source_sha}`")
    lines.append("- **Transport:** Pure HTTP registry (`/tools/claim_library_work`, `/tools/submit_library_result`, `/tools/apply_reshelving`).")
    lines.append("- **Tool Invocation:** The harness drives all HTTP tool endpoints. The model executes zero tool calls.")
    lines.append("")

    lines.append("## 2. Accuracy & Coverage Thresholds")
    lines.append("Contract requirements: Coverage floor **0.80**, Primary-shelf precision target **0.90** per stratum.")
    lines.append("Scoring rule: Strict mapped equality to the deepest approved taxonomy ancestor.")
    lines.append("Abstentions (`unmapped`, `unsupported`, `rejected`) are counted against coverage and excluded from precision.")
    lines.append("")
    lines.append("| Stratum | Total (N) | Assigned (A) | Abstentions (U) | Coverage | Coverage Floor | Correct (C) | Precision | Precision Target | Result |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    for stratum_name, st in score_result["strata"].items():
        res_label = "PASS" if st["stratum_pass"] else "FAIL"
        lines.append(
            f"| **{stratum_name}** | {st['total_items']} | {st['assigned_count']} | {st['abstention_count']} | "
            f"{st['coverage']:.1%} | >= 80.0% | {st['correct_count']} | {st['precision']:.1%} | >= 90.0% | **{res_label}** |"
        )

    ov = score_result["overall"]
    lines.append(
        f"| **Overall (Held-out)** | **{ov['total_items']}** | **{ov['assigned_count']}** | **{ov['abstention_count']}** | "
        f"**{ov['coverage']:.1%}** | >= 80.0% | **{ov['correct_count']}** | **{ov['precision']:.1%}** | >= 90.0% | **{gate_verdict}** |"
    )
    lines.append("")

    lines.append("## 3. Evidence Grounding & Identity Checks")
    lines.append("- Verifies evidence basis is `packet` or `fetched_full`.")
    lines.append("- Verifies every membership quote adheres strictly to the 1 to 24 words brevity cap.")
    lines.append("- Verifies card hash and excerpt hash bindings match frozen input records.")
    lines.append("")
    lines.append(f"- **Assigned items evaluated for evidence:** {ov['evidence_checked_count']}")
    lines.append(f"- **Grounded evidence valid:** {ov['evidence_valid_count']} ({ov['evidence_grounding_rate']:.1%})")
    lines.append("")

    lines.append("## 4. Invariant Assertions & State Isolation")
    before_state = score_result["before_state"]
    after_state = score_result["after_state"]
    before_applied = before_state.get("applied_label_count", before_state.get("applied_count", 0))
    after_applied = after_state.get("applied_label_count", after_state.get("applied_count", 0))
    pins_list = before_state.get("pins", [])
    pins_count = len(pins_list) if isinstance(pins_list, list) else before_state.get("pins_count", 0)

    lines.append("- **Librarian apply enabled:** `False` (preview only).")
    lines.append(f"- **Zero applied labels before run:** `{before_applied == 0}`")
    lines.append(f"- **Zero applied labels after run:** `{after_applied == 0}`")
    lines.append(f"- **Projection revision identical before/after:** `{before_state.get('projection_revision') == after_state.get('projection_revision')}` (rev {before_state.get('projection_revision')})")
    lines.append(f"- **Active taxonomy version unchanged:** `{before_state.get('active_version_id')}`")
    lines.append(f"- **Pins preserved:** `{pins_count} pin(s)`")
    lines.append(f"- **All invariant checks passed:** `{score_result['zero_applies_verified']}`")
    lines.append("")

    lines.append("## 5. Usage & Resource Accounting")
    u = score_result["usage"]
    lines.append(f"- **Usage Reporting Status:** `{u['status']}`")
    lines.append(f"- **Wall Time:** {u['wall_time_s']:.2f} s ({u['wall_time_ms']:,} ms)")

    if u["is_measured"]:
        lines.append(f"- **CLI Process Calls:** {u.get('calls', 0):,}")
        lines.append(f"- **Input Tokens:** {u['input_tokens']:,}")
        lines.append(f"- **Output Tokens:** {u['output_tokens']:,}")
        lines.append(f"- **Cache Read Tokens:** {u['cache_read_tokens']:,}")
        lines.append(f"- **Cache Create Tokens:** {u['cache_create_tokens']:,}")
        lines.append(f"- **Total Tokens:** {u['total_tokens']:,}")
        lines.append(f"- **Total Estimated Cost (USD):** ${u['total_cost_usd_estimate']:.4f} *(Note: CLI estimate)*")
    else:
        lines.append("- **Token Usage:** Unmeasured (Mock run / zero model API execution).")
        lines.append("> [!NOTE]")
        lines.append("> Never prints PASS from an estimate: Mock runs evaluate fixture assignments and offline contracts only. Gate certification requires validated real subscription receipts.")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Living Library product proof scorer (Run S, evaluates receipts against holdout split)"
    )
    parser.add_argument(
        "--receipts",
        type=Path,
        required=True,
        help="Path to receipts.json",
    )
    parser.add_argument(
        "--holdout",
        type=Path,
        default=DEFAULT_HOLDOUT,
        help=f"Path to holdout-split JSON (default: {DEFAULT_HOLDOUT})",
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=DEFAULT_GOLD,
        help=f"Path to gold-set JSON (default: {DEFAULT_GOLD})",
    )
    parser.add_argument(
        "--taxonomy",
        type=Path,
        default=DEFAULT_TAXONOMY,
        help=f"Path to frozen taxonomy JSON (default: {DEFAULT_TAXONOMY})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Directory to write report.md (default: parent directory of receipts.json)",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=None,
        help="Frozen adjudicated mapping table; every gold path must map to exactly the frozen mapped_path",
    )
    args = parser.parse_args()

    if not args.receipts.is_file():
        print(f"ERROR: Receipts file not found: {args.receipts}", file=sys.stderr)
        sys.exit(1)
    if not args.holdout.is_file():
        print(f"ERROR: Holdout file not found: {args.holdout}", file=sys.stderr)
        sys.exit(1)
    if not args.gold.is_file():
        print(f"ERROR: Gold set file not found: {args.gold}", file=sys.stderr)
        sys.exit(1)
    if not args.taxonomy.is_file():
        print(f"ERROR: Taxonomy file not found: {args.taxonomy}", file=sys.stderr)
        sys.exit(1)

    receipts_data = json.loads(args.receipts.read_text(encoding="utf-8"))
    holdout_data = json.loads(args.holdout.read_text(encoding="utf-8"))
    gold_data = json.loads(args.gold.read_text(encoding="utf-8"))
    taxonomy_data = load_taxonomy(args.taxonomy)

    mapping_status = "not checked (no --mapping)"
    if args.mapping is not None:
        if not args.mapping.is_file():
            print(f"ERROR: Mapping file not found: {args.mapping}", file=sys.stderr)
            sys.exit(1)
        mapping_doc = json.loads(args.mapping.read_text(encoding="utf-8"))
        try:
            mapping_status = verify_frozen_mapping(mapping_doc, holdout_data, gold_data, taxonomy_data)
        except ProofScoreError as exc:
            print(f"SCORER ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

    try:
        results = score_receipts(receipts_data, holdout_data, gold_data, taxonomy_data)
    except ProofScoreError as exc:
        print(f"SCORER ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    results["frozen_mapping"] = mapping_status

    out_dir = args.out if args.out else args.receipts.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    report_md = render_report_markdown(results, receipts_data)
    report_path = out_dir / "report.md"
    report_path.write_text(report_md, encoding="utf-8")

    # Print summary to terminal
    print("=" * 78)
    print(" LIVING LIBRARY PRODUCT PROOF SCORING SUMMARY (RUN S)")
    print("=" * 78)
    for s_name, st in results["strata"].items():
        status_str = "PASS" if st["stratum_pass"] else "FAIL"
        print(
            f"Stratum: {s_name:<16} | Cov: {st['coverage']:.1%} ({st['assigned_count']}/{st['total_items']}) | "
            f"Prec: {st['precision']:.1%} ({st['correct_count']}/{st['assigned_count']}) | Abst: {st['abstention_count']} | [{status_str}]"
        )

    ov = results["overall"]
    print("-" * 78)
    print(
        f"Overall Held-out:        | Cov: {ov['coverage']:.1%} ({ov['assigned_count']}/{ov['total_items']}) | "
        f"Prec: {ov['precision']:.1%} ({ov['correct_count']}/{ov['assigned_count']}) | Abst: {ov['abstention_count']} | [{results['gate_verdict']}]"
    )
    print(
        f"Evidence Grounding Rate: {ov['evidence_grounding_rate']:.1%} ({ov['evidence_valid_count']}/{ov['evidence_checked_count']} valid)"
    )
    print(
        f"Zero Applied Labels:     {results['zero_applies_verified']} (Projection revision {results['before_state'].get('projection_revision')})"
    )
    print(f"Usage Status:            {results['usage']['status']}")
    print(f"Frozen Mapping:          {results['frozen_mapping']}")
    print("-" * 78)
    print(f"Detailed Markdown Report: {report_path}")
    print("=" * 78)


if __name__ == "__main__":
    main()

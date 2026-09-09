"""Collector and operator checkpoints for the Phase 4 installed receipt.

Retrieves evidence, follows a citation, opens a brief, jumps to a chapter.
Absent screenshots and traffic stay unobserved — never synthesized or marked
passed. Original-route failures are recorded as product findings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from p4_common import (
    BLOCKED_X_LINK,
    IsolationError,
    OPTIONAL_PLAYER_JUMP,
    PROTECTED_SENTINEL_BYTES,
    add_common_args,
    bind_from_args,
    record_product_finding,
    save_json,
    sha_bytes,
    sha_file,
)
from p4_inspect_evidence import inspect
from p4_execute_checks import execute as execute_checks


UNOBSERVED = "unobserved"
PASSED = "passed"
FAILED = "failed"
BLOCKED = "blocked"
PENDING_REVIEW = "pending_review"


def screenshot_status(path) -> dict:
    if path is None:
        return {
            "status": UNOBSERVED,
            "reason": "no image supplied; not synthesized; not marked passed",
        }
    file = Path(path)
    if file.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        return {"status": UNOBSERVED, "reason": "expected a retained image file"}
    if not file.is_file():
        return {
            "status": UNOBSERVED,
            "path": str(file),
            "reason": "image file absent; not synthesized; not marked passed",
        }
    stat = file.stat()
    return {
        "status": PENDING_REVIEW,
        "path": str(file.resolve()),
        "sha256": sha_file(file),
        "bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "not_a_pass_by_itself": True,
        "reason": "bytes retained; Astra must inspect the actual image and matching observation",
    }


def visual_status(matches: bool, observation: dict, image: dict) -> str:
    if image["status"] == UNOBSERVED or not observation:
        return UNOBSERVED
    return PENDING_REVIEW if matches else FAILED


def _load_operator(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def operator_sequence(binding: dict) -> dict:
    """Argument arrays preserve spaces; a missing binding never becomes a command."""
    profile = Path(binding["isolated_profile"])
    kit = Path(__file__).resolve().parent
    manifest = binding.get("package_manifest") or {}
    values = {
        "--isolated-profile": str(profile),
        "--isolated-port": binding.get("isolated_port"),
        "--installed-app": binding.get("installed_app"),
        "--installed-interpreter": binding.get("installed_interpreter"),
        "--package-manifest": manifest.get("path"),
        "--receipt-root": binding.get("receipt_root"),
        "--runtime-mode": binding.get("runtime_mode"),
        "--package-path": (manifest.get("package_bytes") or {}).get("path"),
        "--source-bindings": (manifest.get("source_bindings_file") or {}).get("path"),
        "--forbid-checkout": binding.get("forbid_checkout"),
    }
    required = set(values) if binding.get("runtime_mode") == "installed" else set(values) - {
        "--package-path", "--source-bindings", "--forbid-checkout"}
    missing = sorted(key for key in required if values[key] is None)
    for name in ("p4_prepare_fixture.py", "p4_prepare_client.py", "p4_stdio_check.py",
                 "p4_collect_evidence.py", "p4_operator.py"):
        if not (kit / name).is_file():
            missing.append(name)
    for flag in ("--package-manifest", "--package-path", "--source-bindings", "--installed-interpreter"):
        if values[flag] and not Path(values[flag]).is_file():
            missing.append(flag + " file")
    app = Path(values["--installed-app"]) if values["--installed-app"] else None
    for name in ("uoink_mcp.py", "scripts/recall_hook.py"):
        if app is None or not (app / name).is_file():
            missing.append("installed " + name)
    common = [part for key, value in values.items() if value is not None for part in (key, str(value))]
    # p4_operator is run by the documented system Python with -I -S. It installs
    # and proves the target guard before a bundled tool or original entry starts.
    commands = [] if missing else [
        {"stage": stage, "args_after_system_python_I_S": [str(kit / "p4_operator.py"), stage, *common]}
        for stage in ("prepare", "check", "prepare-client", "collect")
    ]
    return {
        "commands": commands, "missing_inputs": missing,
        "refused_missing_inputs": bool(missing),
        "client_step": "Ryan authenticates the isolated subscription config, then uses p4_operator client with explicit client executable, prompt file and subscription/credits acknowledgements",
        "guard_lifecycle": "p4_operator owns the entire child job and restores exact bytes only after affirmative cleanup",
        "real_client_ui": "unobserved until Ryan supplies stream/screenshots and Astra reviews them",
        "x_link": "documented HTTP 403, no retry", "speaker_claim": False,
        "phase5_part_b": "deferred", "apply_enabled": False,
    }


def _cmp_text(expected: str | None, actual: str | None, *, field: str) -> dict:
    if actual is None:
        return {"field": field, "status": UNOBSERVED, "reason": "actual text absent"}
    if expected is None:
        return {"field": field, "status": FAILED, "reason": "expected text missing"}
    equal = actual == expected
    return {
        "field": field,
        "status": PASSED if equal else FAILED,
        "expected_sha256": sha_bytes(expected.encode()),
        "actual_sha256": sha_bytes(actual.encode()),
        "exact": equal,
    }


def collect(binding: dict, operator: dict) -> dict:
    profile = Path(binding["isolated_profile"])
    expected = json.loads((profile / "expected.json").read_text(encoding="utf-8"))
    preparation = json.loads((profile / "preparation.json").read_text(encoding="utf-8"))
    items = expected.get("items") or {}
    findings = list(preparation.get("product_findings") or [])
    checkpoints = []

    def add(name, status, **fields):
        checkpoints.append({"name": name, "status": status, **fields})

    records = sorted((profile / "records").glob("*/events.jsonl"))
    original_records = [
        path for path in records
        if "originalinstalled" in path.parent.name.replace("-", "").lower()
        or "original-installed" in str(path)
    ]
    inspection = None
    if original_records:
        inspection = inspect(expected, original_records, required_route="original-installed")
        add("protocol_packets", PASSED if inspection["packet_and_prompt_subset_complete"] else FAILED,
            packet_and_prompt_subset_complete=inspection["packet_and_prompt_subset_complete"],
            original_sessions=inspection.get("session_reports"), source="original-installed")
    elif records:
        inspection = inspect(expected, records)
        add("protocol_packets",
            PASSED if inspection["packet_and_prompt_subset_complete"] else FAILED,
            packet_and_prompt_subset_complete=inspection["packet_and_prompt_subset_complete"],
            frame_faults=len(inspection["frame_faults"]),
            missing_prompts=inspection["missing_required_native_prompts"],
            comparisons=inspection["exact_packet_comparisons"])
        labels = {session.get("route_label") for session in inspection["sessions"]}
        if "fixture-attached" in labels and "original-installed" not in labels:
            findings.append(record_product_finding(
                operation="route_label",
                input_value={"observed_labels": sorted(x for x in labels if x)},
                error="fixture-attached records present without original-installed; do not treat attached as original",
                route="fixture-attached",
            ))
    else:
        add("protocol_packets", UNOBSERVED, reason="no recorder events.jsonl")

    proto_by_item = {}
    if inspection:
        for row in inspection.get("exact_packet_comparisons") or []:
            proto_by_item.setdefault(row.get("item_id"), []).append(row)
    for item_id, kind in (
        ("p4fx-timed-01", "timed"),
        ("p4fx-text-01", "text_only"),
        ("p4fx-hostile-01", "hostile"),
    ):
        item = items.get(item_id) or {}
        actual = ((operator.get("packets") or {}).get(item_id) or {})
        checks = []
        proto = proto_by_item.get(item_id) or []
        if proto:
            for field, kind_name in (("card_text", "card"), ("excerpt_text", "excerpt"),
                                     ("corpus_text", "corpus")):
                rows = [c for c in proto if c.get("kind") == kind_name]
                if not rows:
                    checks.append({"field": field, "status": FAILED, "reason": "declared pair missing from protocol"})
                    continue
                equal = all(c.get("status") == "equal" for c in rows)
                checks.append({
                    "field": field,
                    "status": PASSED if equal else FAILED,
                    "source": "protocol_records",
                    "routes": [c.get("route") for c in rows],
                    "operator_boolean_used": False,
                })
        else:
            for field in ("card_text", "excerpt_text", "corpus_text"):
                checks.append(_cmp_text(item.get(field), actual.get(field), field=field))
        timing = item.get("timing")
        if kind == "text_only":
            checks.append({
                "field": "timing_null",
                "status": PASSED if timing in (None, "not_timed") else FAILED,
                "timing": timing,
            })
        status = FAILED if any(c["status"] == FAILED for c in checks) else (
            PASSED if checks and all(c["status"] == PASSED for c in checks) else UNOBSERVED)
        add(f"retrieve_{kind}", status, item_id=item_id, checks=checks,
            screenshot=screenshot_status((operator.get("screenshots") or {}).get(item_id)),
            operator_boolean_used=False)

    follow = operator.get("follow_citation") or {}
    if follow.get("url") == BLOCKED_X_LINK["url"]:
        if follow.get("fetched") is True:
            findings.append(record_product_finding(
                operation="follow_citation_x",
                input_value=follow,
                error="X fetch was attempted; prior HTTP 403 must remain blocked with no retry",
                route="operator",
            ))
            add("follow_citation", FAILED, blocked_link=BLOCKED_X_LINK, observation=follow)
        else:
            add("follow_citation", BLOCKED, blocked_link=BLOCKED_X_LINK,
                observation=follow, screenshot=screenshot_status(follow.get("screenshot")),
                no_retry=True, no_new_fetch=True)
    else:
        add("follow_citation", UNOBSERVED, blocked_link=BLOCKED_X_LINK,
            reason="operator did not record a citation follow; not marked passed")

    brief = expected.get("brief") or {}
    local = operator.get("follow_local_citation") or {}
    local_image = screenshot_status(local.get("screenshot"))
    citation = brief.get("citation_quote")
    local_matches = bool(citation) and local.get("citation_quote") == citation
    local_matches = local_matches and bool(brief.get("uri")) and local.get("brief_uri") == brief.get("uri")
    add("follow_local_citation", visual_status(local_matches, local, local_image),
        expected_brief_uri=brief.get("uri"), expected_citation_quote=citation,
        expected_source_items=items, actual=local, screenshot=local_image,
        new_fetch_authorized=False, reason="retain exact URI, quote/revision and source bytes for Astra review")
    actual_brief = operator.get("brief") or {}
    quote_check = _cmp_text(brief.get("text"), actual_brief.get("text"), field="brief_text")
    brief_image = screenshot_status(actual_brief.get("screenshot"))
    add("open_brief", visual_status(quote_check["status"] == PASSED, actual_brief, brief_image), expected_uri=brief.get("uri"),
        citation_quote=brief.get("citation_quote"), check=quote_check,
        client_authored=False, screenshot=brief_image)

    chapter = expected.get("chapter") or {}
    actual_chapter = operator.get("chapter") or {}
    chapter_ok = (
        actual_chapter.get("title") == chapter.get("title")
        and actual_chapter.get("start") == chapter.get("start")
    ) if actual_chapter else False
    chapter_image = screenshot_status(actual_chapter.get("screenshot"))
    add("jump_chapter_fixture",
        visual_status(chapter_ok, actual_chapter, chapter_image),
        expected=chapter, actual=actual_chapter,
        screenshot=chapter_image)

    jump = operator.get("optional_player_jump") or {}
    if jump.get("observed") is True:
        url_ok = jump.get("url") == OPTIONAL_PLAYER_JUMP["url"]
        jump_image = screenshot_status(jump.get("screenshot"))
        add("optional_player_jump", visual_status(url_ok, jump, jump_image),
            allowed=OPTIONAL_PLAYER_JUMP, actual=jump,
            screenshot=jump_image,
            speaker_accuracy_claim=False)
    else:
        add("optional_player_jump", UNOBSERVED, allowed=OPTIONAL_PLAYER_JUMP,
            reason="optional separately observed player jump was not recorded; not marked passed")

    sentinel_path = Path((expected.get("protected_sentinel") or {}).get("path") or
                         (profile / "client" / "protected-sentinel.bin"))
    if sentinel_path.is_file():
        current = sha_file(sentinel_path)
        unchanged = current == sha_bytes(PROTECTED_SENTINEL_BYTES)
        add("protected_bytes", PASSED if unchanged else FAILED,
            expected_sha256=sha_bytes(PROTECTED_SENTINEL_BYTES), actual_sha256=current)
    else:
        add("protected_bytes", FAILED, reason="protected sentinel missing")

    try:
        executed = execute_checks(binding)
    except Exception as exc:
        executed = {"checkpoints": [], "product_findings": [record_product_finding(
            operation="executable_checks", input_value={}, error=f"{type(exc).__name__}: {exc}",
            route="executable-check",
        )]}
    executed_by_name = {c["name"]: c for c in executed.get("checkpoints") or []}
    findings.extend(executed.get("product_findings") or [])

    hostile_exec = executed_by_name.get("hostile_actions")
    actions = operator.get("actions") or {}
    attempted = actions.get("hostile_attempts") or []
    executed_effects = actions.get("effects_executed") or []
    if hostile_exec:
        add("hostile_sentinel_instrument", hostile_exec["status"],
            **{k: v for k, v in hostile_exec.items() if k not in ("name", "status")}, client_run=False)
        add("hostile_actions", UNOBSERVED,
            reason="an explicit synthetic sentinel call does not establish actual client injection resistance")
    elif not attempted and not actions.get("observed"):
        add("hostile_actions", UNOBSERVED,
            reason="no action log or executable sentinel result; empty denial list is not a pass")
    else:
        add("hostile_actions", FAILED if executed_effects else UNOBSERVED,
            attempted=attempted, effects_executed=executed_effects,
            reason="operator list is not evidence; executable sentinel result required")

    original_check = profile / "stdio-check-original-installed.json"
    synth_check = profile / "stdio-check-synthetic-instrument.json"
    stdio = {}
    if original_check.is_file():
        stdio = json.loads(original_check.read_text(encoding="utf-8"))
        stdio["source"] = "original-installed"
    elif synth_check.is_file():
        stdio = json.loads(synth_check.read_text(encoding="utf-8"))
        stdio["source"] = "synthetic-instrument"
        stdio["not_installed_credit"] = True

    reconnect = (stdio.get("reconnect") or {})
    child_old = reconnect.get("first_child_pid") or reconnect.get("first_wrapper_pid")
    child_new = reconnect.get("second_child_pid") or reconnect.get("second_wrapper_pid")
    operator_reconnect = operator.get("reconnect") or {}
    if child_old and child_new:
        add("reconnect",
            PASSED if child_old != child_new else FAILED,
            old_child_pid=child_old, new_child_pid=child_new,
            source=stdio.get("source"), operator_boolean_used=False)
    elif operator_reconnect.get("old_child_pid") and operator_reconnect.get("new_child_pid"):
        add("reconnect", UNOBSERVED,
            reason="operator-supplied PIDs are not evidence without recorder child identities",
            operator=operator_reconnect)
    elif inspection and inspection.get("reconnect_identities"):
        pids = []
        for row in inspection["reconnect_identities"]:
            pids.extend(row.get("child_pids") or [])
        add("reconnect",
            PASSED if len(set(pids)) >= 2 else UNOBSERVED,
            child_pids=pids, source="recorder", operator_boolean_used=False)
    else:
        add("reconnect", UNOBSERVED, reason="no reconnect identities recorded")

    storage = stdio.get("unavailable_storage") or {}
    measured = storage.get("elapsed_ms")
    if measured is None:
        add("unavailable_storage", UNOBSERVED, bound_ms=2000,
            reason="no original-route or synthetic measured storage refusal")
    else:
        add("unavailable_storage",
            PASSED if measured <= 2000 and not storage.get("replacement_index_created") else FAILED,
            elapsed_ms=measured, bound_ms=2000,
            replacement_index_created=bool(storage.get("replacement_index_created")),
            source=stdio.get("source"), operator_boolean_used=False)

    transport = stdio.get("transport_failure") or {}
    if transport.get("elapsed_ms") is None:
        add("transport_failure", UNOBSERVED, bound_ms=15000)
    else:
        add("transport_failure",
            PASSED if transport["elapsed_ms"] <= 15000 else FAILED,
            elapsed_ms=transport["elapsed_ms"], bound_ms=15000,
            source=stdio.get("source"), operator_boolean_used=False)

    recall_exec = executed_by_name.get("recall_silent_unavailable")
    if recall_exec:
        add("recall_silent_unavailable", recall_exec["status"],
            **{k: v for k, v in recall_exec.items() if k not in ("name", "status")})
    else:
        add("recall_silent_unavailable", UNOBSERVED,
            reason="Recall silent missing-index outcome not executed")

    for name in ("mirror_disconnect_reconnect", "user_edit_preservation", "deletion_cleanup"):
        row = executed_by_name.get(name)
        if row:
            add(name, row["status"], **{k: v for k, v in row.items() if k not in ("name", "status")})
        else:
            add(name, UNOBSERVED, fixture_only=True,
                reason="executable mirror check did not run; operator booleans are not evidence")

    for name, key in (("native_consult_library", "consult-library"),
                      ("native_reshelve_review", "reshelve-review")):
        if inspection and inspection.get("packet_and_prompt_subset_complete") and original_records:
            add(name, PASSED)
        else:
            add(name, UNOBSERVED if not records else FAILED)

    for route in ("ordinary", "recall"):
        stream = profile / ("operator-client-" + route + ".stdout")
        if stream.is_file() and stream.stat().st_size:
            add("actual_client_" + route, PENDING_REVIEW, stream=str(stream),
                sha256=sha_file(stream), bytes=stream.stat().st_size,
                reason="review complete requests, decisions, source use and actual settings before acceptance")
        else:
            add("actual_client_" + route, UNOBSERVED, reason="no actual client stream retained")

    outcome = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "isolation": {
            "isolated_profile": binding["isolated_profile"],
            "isolated_port": binding["isolated_port"],
            "instrument_only": binding["instrument_only"],
            "installed_credit": binding["installed_credit"],
        },
        "apply_enabled": False,
        "checkpoints": checkpoints,
        "product_findings": findings,
        "counts": {
            "passed": sum(1 for c in checkpoints if c["status"] == PASSED),
            "failed": sum(1 for c in checkpoints if c["status"] == FAILED),
            "blocked": sum(1 for c in checkpoints if c["status"] == BLOCKED),
            "unobserved": sum(1 for c in checkpoints if c["status"] == UNOBSERVED),
            "pending_review": sum(1 for c in checkpoints if c["status"] == PENDING_REVIEW),
        },
        "operator_sequence": operator_sequence(binding),
        "operator_commands": [
            "Retrieve timed item card, excerpt and corpus via native resource and fallback tool",
            "Retrieve text-only item; timing fields must stay null",
            "Follow the local citation and retain URI, quote/revision, source bytes and screenshot; X HTTP 403 remains blocked without retry",
            "Open the prepared fixture brief and compare the full quote/revision",
            "Open the synthetic chapter list on p4fx-timed-01",
            "Retain the already completed BD-27 player observation; no new external fetch is required",
            "Record one explicit reconnect with old/new child PIDs and unchanged item bytes",
            "Observe live-child unavailable storage within 2s; no replacement empty index",
            "Observe broken transport within 15s and at most one explicit reconnect",
            "Hostile payloads: retain tool inputs, permission decisions, sentinel hashes",
            "Recall missing isolated index: silent exit 0, no replacement database",
            "Fixture-only mirror: disconnect/reconnect, preserve user edit, account deletion cleanup",
        ],
        "absent_images_never_passed": True,
        "no_synthesized_screenshots": True,
        "package_hash_status": preparation.get("package_manifest", {}).get("package_hash_status"),
    }
    return outcome


def main(argv=None):
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--operator-json", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        binding = bind_from_args(args)
    except IsolationError as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}), file=sys.stderr)
        return 2
    operator = _load_operator(args.operator_json)
    result = collect(binding, operator)
    output = args.output or (Path(binding["isolated_profile"]) / "collection.json")
    if output.exists():
        raise IsolationError("refusing to overwrite existing collection output")
    save_json(output, result)
    print(json.dumps({
        "status": "recorded",
        "output": str(output),
        "counts": result["counts"],
        "product_findings": len(result["product_findings"]),
        "installed_credit": result["isolation"]["installed_credit"],
    }))
    failed = result["counts"]["failed"]
    return 1 if failed or result["product_findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

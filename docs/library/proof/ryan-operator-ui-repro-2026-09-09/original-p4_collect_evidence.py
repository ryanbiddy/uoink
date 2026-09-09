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


def screenshot_status(path) -> dict:
    if path is None:
        return {
            "status": UNOBSERVED,
            "reason": "no image supplied; not synthesized; not marked passed",
        }
    file = Path(path)
    if not file.is_file():
        return {
            "status": UNOBSERVED,
            "path": str(file),
            "reason": "image file absent; not synthesized; not marked passed",
        }
    stat = file.stat()
    return {
        "status": "observed",
        "path": str(file.resolve()),
        "sha256": sha_file(file),
        "bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "not_a_pass_by_itself": True,
    }


def _load_operator(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def operator_sequence(binding: dict) -> dict:
    """Complete copy-paste commands. Missing inputs are refused, not hypothesized."""
    profile = Path(binding["isolated_profile"])
    app = Path(binding.get("installed_app") or "")
    interpreter = Path(binding.get("installed_interpreter") or "")
    kit = Path(__file__).resolve().parent
    root = Path(binding.get("receipt_root") or profile.parent)
    port = binding.get("isolated_port")
    manifest = binding.get("package_manifest") or {}
    manifest_path = manifest.get("path") or "<package-manifest.json>"
    missing = []
    for label, path in (
        ("installed-app/uoink_mcp.py", app / "uoink_mcp.py" if app else None),
        ("installed-interpreter", interpreter if interpreter else None),
        ("p4_prepare_fixture.py", kit / "p4_prepare_fixture.py"),
        ("p4_stdio_check.py", kit / "p4_stdio_check.py"),
        ("p4_collect_evidence.py", kit / "p4_collect_evidence.py"),
    ):
        if path is None or not Path(path).exists():
            missing.append(label)
    recall = app / "scripts" / "recall_hook.py" if app else None
    if recall is None or not recall.is_file():
        missing.append("installed scripts/recall_hook.py")
    commands = [
        f"{interpreter} -B {kit / 'p4_prepare_fixture.py'} "
        f"--isolated-profile {profile} --isolated-port {port} "
        f"--installed-app {app} --installed-interpreter {interpreter} "
        f"--package-manifest {manifest_path} --receipt-root {root} "
        f"--runtime-mode {binding.get('runtime_mode') or 'source-runtime'}",
        f"{interpreter} -B {kit / 'p4_stdio_check.py'} "
        f"--isolated-profile {profile} --isolated-port {port} "
        f"--installed-app {app} --installed-interpreter {interpreter} "
        f"--package-manifest {manifest_path} --receipt-root {root} "
        f"--route original-installed --runtime-mode {binding.get('runtime_mode') or 'source-runtime'}",
        "# Ryan only: capture the complete client stdout JSONL and stderr from "
        f"{profile / 'client' / 'launch-isolated.json'} stream_collection. "
        "Do not start a client from this worker. Do not set ANTHROPIC_API_KEY.",
        f"{interpreter} -B {kit / 'p4_collect_evidence.py'} "
        f"--isolated-profile {profile} --isolated-port {port} "
        f"--installed-app {app} --installed-interpreter {interpreter} "
        f"--package-manifest {manifest_path} --receipt-root {root} "
        f"--operator-json {profile / 'operator.json'} "
        f"--output {profile / 'collection.json'}",
        "# Restore receipt-owned python._pth / sitecustomize bytes after every "
        "child has exited. p4_stdio_check restores in an outer finally; do not "
        "leave a mutated bundled guard in place across kit runs.",
    ]
    return {
        "commands": commands,
        "missing_inputs": missing,
        "refused_missing_inputs": bool(missing),
        "real_client_ui": "unobserved until Ryan supplies stream/screenshots",
        "x_link": "documented HTTP 403, no retry",
        "speaker_claim": False,
        "phase5_part_b": "deferred",
        "apply_enabled": False,
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
    if follow.get("url") == BLOCKED_X_LINK["url"] or follow.get("attempted") is True:
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
    actual_brief = operator.get("brief") or {}
    quote_check = _cmp_text(brief.get("text"), actual_brief.get("text"), field="brief_text")
    add("open_brief", quote_check["status"], expected_uri=brief.get("uri"),
        citation_quote=brief.get("citation_quote"), check=quote_check,
        client_authored=False, screenshot=screenshot_status(actual_brief.get("screenshot")))

    chapter = expected.get("chapter") or {}
    actual_chapter = operator.get("chapter") or {}
    chapter_ok = (
        actual_chapter.get("title") == chapter.get("title")
        and actual_chapter.get("start") == chapter.get("start")
    ) if actual_chapter else False
    add("jump_chapter_fixture",
        PASSED if chapter_ok else (UNOBSERVED if not actual_chapter else FAILED),
        expected=chapter, actual=actual_chapter,
        screenshot=screenshot_status(actual_chapter.get("screenshot")))

    jump = operator.get("optional_player_jump") or {}
    if jump.get("observed") is True:
        url_ok = jump.get("url") == OPTIONAL_PLAYER_JUMP["url"]
        add("optional_player_jump", PASSED if url_ok else FAILED,
            allowed=OPTIONAL_PLAYER_JUMP, actual=jump,
            screenshot=screenshot_status(jump.get("screenshot")),
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
        add("hostile_actions", hostile_exec["status"], **{k: v for k, v in hostile_exec.items() if k != "name"})
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
            **{k: v for k, v in recall_exec.items() if k != "name"})
    else:
        add("recall_silent_unavailable", UNOBSERVED,
            reason="Recall silent missing-index outcome not executed")

    for name in ("mirror_disconnect_reconnect", "user_edit_preservation", "deletion_cleanup"):
        row = executed_by_name.get(name)
        if row:
            add(name, row["status"], **{k: v for k, v in row.items() if k != "name"})
        else:
            add(name, UNOBSERVED, fixture_only=True,
                reason="executable mirror check did not run; operator booleans are not evidence")

    for name, key in (("native_consult_library", "consult-library"),
                      ("native_reshelve_review", "reshelve-review")):
        if inspection and key not in inspection.get("missing_required_native_prompts", [key]):
            add(name, PASSED)
        else:
            add(name, UNOBSERVED if not records else FAILED)

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
        },
        "operator_sequence": operator_sequence(binding),
        "operator_commands": [
            "Retrieve timed item card, excerpt and corpus via native resource and fallback tool",
            "Retrieve text-only item; timing fields must stay null",
            "Follow the returned X citation; expect blocked HTTP 403; do not retry or fetch",
            "Open the prepared fixture brief and compare the full quote/revision",
            "Open the synthetic chapter list on p4fx-timed-01",
            "Optional: open https://www.youtube.com/watch?v=D_FCYsshMI4&t=34s and record player time + screenshot",
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

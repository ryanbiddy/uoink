"""Executable everyday/Recall/mirror checks. Operator booleans are not evidence.

Fixture-only: disconnect/reconnect, user-edit preservation, deletion cleanup,
Recall silent unavailable storage, hostile sentinel refusal. Missing images
stay unobserved. Apply stays false. No client or model is started.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import time

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from p4_common import (
    IsolationError,
    PROTECTED_SENTINEL_BYTES,
    isolated_index_path,
    prove_guard_canary,
    record_product_finding,
    sha_bytes,
    sha_file,
    save_json_exclusive,
    write_guard,
)

UNOBSERVED = "unobserved"
PASSED = "passed"
FAILED = "failed"


def deletion_evidence_ok(evidence: dict) -> bool:
    """Require concrete deletion bytes, owned-path absence and accounted residuals."""
    return bool(
        evidence.get("soft_delete_committed") is True
        and evidence.get("content_free_tombstone") is True
        and evidence.get("purge_committed") is True
        and evidence.get("owned_paths")
        and all(row.get("absent") is True for row in evidence["owned_paths"])
        and evidence.get("unaccounted_pending_keys") == []
        and evidence.get("remaining_temp_paths") == []
        and evidence.get("user_edit_preserved") is True
        and evidence.get("unmanaged_preserved") is True
    )


def _bind_before_import(profile: Path, app: Path, port: int) -> None:
    os.environ["P4_ISOLATED_PROFILE"] = str(profile)
    os.environ["P4_FIXTURE_ROOT"] = str(profile)
    os.environ["UOINK_ISOLATED_PROFILE"] = str(profile)
    os.environ["UOINK_ISOLATED_PORT"] = str(port)
    os.environ["UOINK_INDEX_PATH"] = str(isolated_index_path(profile))
    os.environ["UOINK_OUTPUT_DIR"] = str(profile / "output")
    if str(app) not in sys.path:
        sys.path.insert(0, str(app))
    iso = app / "uoink_install_isolation.py"
    if iso.is_file():
        import uoink_install_isolation as _iso
        _iso.apply_from_process(argv=[
            "--isolated-profile", str(profile), "--isolated-port", str(port),
        ])


def recall_silent_unavailable(profile: Path, app: Path, interpreter: Path) -> dict:
    """Missing isolated Recall index: silent stdout, exit 0, no replacement db.

    Requires the installed helper script at app/scripts/recall_hook.py. A
    staged copy is not a substitute.
    """
    script = app / "scripts" / "recall_hook.py"
    if not script.is_file():
        return {
            "name": "recall_silent_unavailable",
            "status": FAILED,
            "error": "installed scripts/recall_hook.py missing; refusing staged fallback",
            "script": str(script),
            "operator_boolean_used": False,
            "refused_missing_input": True,
        }
    missing = profile / "recall-missing" / "index.db"
    if missing.exists():
        missing.unlink()
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env["UOINK_INDEX_PATH"] = str(missing)
    env["P4_ISOLATED_PROFILE"] = str(profile)
    started = time.perf_counter_ns()
    import subprocess
    try:
        result = subprocess.run(
            [str(interpreter), "-B", "-s", "-P", str(script)],
            input=b'{"prompt":"Please find saved computer vision research examples"}',
            capture_output=True, cwd=str(profile), env=env, timeout=3,
        )
        timed_out = False
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        code, stdout, stderr = None, exc.stdout or b"", exc.stderr or b""
    elapsed = (time.perf_counter_ns() - started) / 1_000_000
    created = missing.exists()
    silent = (stdout or b"") == b"" and code == 0 and not timed_out
    status = PASSED if silent and elapsed <= 2000 and not created else FAILED
    return {
        "name": "recall_silent_unavailable",
        "status": status,
        "elapsed_ms": elapsed,
        "exit_code": code,
        "stdout": (stdout or b"").decode("utf-8", "replace"),
        "stderr_len": len(stderr or b""),
        "timed_out": timed_out,
        "replacement_index_created": created,
        "script": str(script),
        "index_path": str(missing),
        "operator_boolean_used": False,
    }


def hostile_sentinel(profile: Path, interpreter: Path) -> dict:
    sentinel = profile / "client" / "protected-sentinel.bin"
    before = sha_file(sentinel) if sentinel.is_file() else None
    observer = profile / "kit" / "p4_observe_actions.py"
    if not observer.is_file():
        observer = _HERE / "p4_observe_actions.py"
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.update(
        P4_FIXTURE_ROOT=str(profile),
        P4_ISOLATED_PROFILE=str(profile),
        P4_ISOLATED_PORT=os.environ.get("P4_ISOLATED_PORT") or "18081",
    )
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "record_action",
                    "arguments": {"action": "shell", "marker": "P4_BODY"}}},
    ]
    import subprocess
    sent = subprocess.run(
        [str(interpreter), "-B", str(observer), "sentinel",
         "--fixture-root", str(profile),
         "--isolated-profile", str(profile),
         "--isolated-port", env["P4_ISOLATED_PORT"]],
        input=("\n".join(json.dumps(m) for m in messages) + "\n").encode(),
        env=env, capture_output=True, timeout=8,
    )
    replies = []
    for line in sent.stdout.splitlines():
        try:
            replies.append(json.loads(line))
        except ValueError:
            continue
    refused = any((r.get("result") or {}).get("isError") for r in replies)
    after = sha_file(sentinel) if sentinel.is_file() else None
    unchanged = after == sha_bytes(PROTECTED_SENTINEL_BYTES) or after == before
    return {
        "name": "hostile_actions",
        "status": PASSED if sent.returncode == 0 and refused and unchanged else FAILED,
        "refused": refused,
        "protected_unchanged": unchanged,
        "effects_executed": [],
        "operator_boolean_used": False,
    }


def mirror_fixture_checks(profile: Path, app: Path, port: int) -> list:
    """Disconnect/reconnect, user-edit preservation, deletion accounting.

    Uses installed modules under the isolated profile. Not a client run.
    """
    checkpoints = []
    index_path = isolated_index_path(profile)
    vault = profile / "vault"
    unmanaged = vault / "unmanaged-user-file.txt"
    if not index_path.is_file():
        for name in ("mirror_disconnect_reconnect", "user_edit_preservation", "deletion_cleanup"):
            checkpoints.append({
                "name": name, "status": UNOBSERVED, "fixture_only": True,
                "reason": "isolated index missing; executable mirror checks not run",
                "operator_boolean_used": False,
            })
        return checkpoints
    try:
        _bind_before_import(profile, app, port)
        import index as index_mod
        import library_resources
        import library_briefs
        import library_work
        import library_mirror
        from library_mirror import Mirror, MirrorConsent, SCOPE_ALL
    except Exception as exc:
        for name in ("mirror_disconnect_reconnect", "user_edit_preservation", "deletion_cleanup"):
            checkpoints.append({
                "name": name, "status": FAILED, "fixture_only": True,
                "error": f"{type(exc).__name__}: {exc}",
                "operator_boolean_used": False,
            })
        return checkpoints
    idx = index_mod.Index.open(index_path)
    try:
        reader = library_resources.LibraryReader(idx, data_root=profile)
        service = library_work.LibraryWorkService(
            idx, profile / "prompt-store", librarian_apply_enabled=False)
        briefs = library_briefs.BriefStore(idx, service, data_root=profile)
        marker = "p4-synthetic-vault"
        (vault / "Uoink").mkdir(parents=True, exist_ok=True)
        (vault / ".uoink-volume-marker").write_text(marker + "\n", encoding="utf-8")
        (vault / "Uoink" / ".uoink-volume-marker").write_text(marker + "\n", encoding="utf-8")
        if not unmanaged.is_file():
            unmanaged.write_text("SYNTHETIC unmanaged vault file; must remain unchanged.\n", encoding="utf-8")
        unmanaged_before = unmanaged.read_bytes()
        consent = MirrorConsent(
            destination=str(vault),
            scope=SCOPE_ALL,
            allowlist=(),
            consented_at_ms=int(time.time() * 1000),
            marker=marker,
        )
        mirror = Mirror(idx, reader, briefs, data_root=profile, consent=consent, enabled=True)
        first = mirror.resync()
        user_file = vault / "Uoink" / "Library.md"
        # Independent user edit of an exported file if present; otherwise the unmanaged file.
        edit_target = user_file if user_file.is_file() else unmanaged
        original_edit = edit_target.read_bytes()
        edited = original_edit + b"\nSYNTHETIC USER EDIT - must remain unchanged.\n"
        edit_target.write_bytes(edited)
        hidden = profile / "vault-disconnected"
        if hidden.exists():
            shutil.rmtree(hidden)
        vault.rename(hidden)
        disconnected = Mirror(idx, reader, briefs, data_root=profile, consent=consent, enabled=True)
        down = disconnected.status()
        dest_unavailable = (
            down.get("destination_state") == "unavailable"
            or down.get("destination_available") is False
            or down.get("code") == "destination_unavailable"
            or down.get("ok") is False
        )
        hidden.rename(vault)
        reconnected = Mirror(idx, reader, briefs, data_root=profile, consent=consent, enabled=True)
        up = reconnected.resync()
        after_edit = edit_target.read_bytes()
        preserved = after_edit == edited
        unmanaged_after = unmanaged.read_bytes() if unmanaged.is_file() else b""
        item_id = "p4fx-timed-01"
        ledger_before = reconnected._load_ledger()
        before_item = idx.get_yoink(item_id)
        item_entry = ledger_before["entries"]["item:" + item_id]
        item_path = vault / "Uoink" / item_entry["relpath"]
        owned_paths = [row["relpath"] for row in ledger_before["entries"].values()
                       if row.get("identity") == item_id or item_id in row.get("dependencies", [])]
        deleted = idx.soft_delete_yoink(item_id)
        deletion = reconnected.tombstone(item_id)
        tombstone = item_path.read_bytes() if item_path.is_file() else b""
        content_free = b"deleted: true" in tombstone.lower()
        for text in (before_item.get("title"), before_item.get("url")):
            if text and text.encode("utf8") in tombstone:
                content_free = False
        idx.delete_yoink(item_id)
        purged = reconnected.purge(item_id)
        ledger_after = reconnected._load_ledger()
        intents_after = reconnected._load_intents()
        pending = [key for key, entry in ledger_after["entries"].items()
                   if entry.get("pending_action", "none") != "none"
                   and not (key == "index:Library.md" and entry.get("status") == "user_edit_conflict")]
        temp_paths = []
        for intent in intents_after.values():
            for temp in intent.get("pending_temps", []):
                candidate = vault / "Uoink" / temp["rel"]
                if candidate.is_file():temp_paths.append(str(candidate))
        evidence = {
            "generator_version": "p4-mirror-real-delete-v2",
            "soft_delete_committed": bool(deleted and deleted.get("deleted_at")),
            "content_free_tombstone": content_free,
            "tombstone_bytes": tombstone.decode("utf8", "replace"),
            "tombstone_sha256": sha_bytes(tombstone),
            "purge_committed": idx.get_yoink(item_id) is None and purged.get("ok") is True,
            "owned_paths": [{"relpath": rel, "absent": not (vault / "Uoink" / rel).exists()} for rel in owned_paths],
            "ledger_before": ledger_before, "ledger_after": ledger_after,
            "intents_after": intents_after,
            "unaccounted_pending_keys": pending,
            "remaining_temp_paths": temp_paths,
            "user_edit_preserved": edit_target.read_bytes() == edited,
            "unmanaged_preserved": unmanaged.read_bytes() == unmanaged_before,
        }
        save_json_exclusive(profile / "mirror-execution-v2.json", evidence)
        status_after = reconnected.status()
        accounted = {
            "owned": status_after.get("synced"),
            "temp": status_after.get("pending"),
            "pending": status_after.get("pending"),
            "conflict": (status_after.get("conflicts") or {}).get("user_edit"),
            "deletion_pending": status_after.get("deletion_pending"),
        }
        checkpoints.append({
            "name": "mirror_disconnect_reconnect",
            "status": PASSED if dest_unavailable and up.get("ok") is True and first.get("ok") is True else FAILED,
            "disconnected": dest_unavailable,
            "reconnected": up.get("ok") is not False,
            "pending_after_disconnect": down.get("pending"),
            "pending_after_reconnect": up.get("pending") if isinstance(up, dict) else None,
            "first_resync": {k: first.get(k) for k in ("ok", "code", "synced") if isinstance(first, dict)},
            "fixture_only": True,
            "operator_boolean_used": False,
        })
        checkpoints.append({
            "name": "user_edit_preservation",
            "status": PASSED if preserved and unmanaged_after == unmanaged_before else FAILED,
            "bytes_unchanged": preserved,
            "unmanaged_unchanged": unmanaged_after == unmanaged_before,
            "path": str(edit_target),
            "fixture_only": True,
            "operator_boolean_used": False,
        })
        checkpoints.append({
            "name": "deletion_cleanup",
            "status": PASSED if deletion_evidence_ok(evidence) else FAILED,
            "accounted": accounted,
            "exact_evidence": evidence,
            "tombstone": {k: deletion.get(k) for k in ("ok", "code") if isinstance(deletion, dict)},
            "fixture_only": True,
            "operator_boolean_used": False,
        })
    except Exception as exc:
        for name in ("mirror_disconnect_reconnect", "user_edit_preservation", "deletion_cleanup"):
            checkpoints.append({
                "name": name, "status": FAILED, "fixture_only": True,
                "error": f"{type(exc).__name__}: {exc}",
                "operator_boolean_used": False,
            })
    finally:
        idx.close()
    return checkpoints


def execute(binding: dict) -> dict:
    profile = Path(binding["isolated_profile"])
    app_value = binding.get("installed_app")
    interpreter_value = binding.get("installed_interpreter")
    if not app_value or not interpreter_value:
        return {
            "checkpoints": [],
            "product_findings": [],
            "skipped": "installed_app/interpreter not in binding; executable checks not run",
            "operator_booleans_are_not_evidence": True,
            "apply_enabled": False,
        }
    app = Path(app_value)
    interpreter = Path(interpreter_value)
    port = int(binding["isolated_port"])
    findings = []
    checkpoints = []
    write_guard(profile, binding)
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env["P4_ISOLATED_PROFILE"] = str(profile)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(profile / "guard")] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    canary = prove_guard_canary(
        interpreter=interpreter, env=env, profile=profile, cwd=profile,
    )
    if not canary.get("refused"):
        findings.append(record_product_finding(
            operation="guard_canary",
            input_value={"canary": canary},
            error="owned canary was not refused; refusing product import in executable checks",
            route="executable-check",
        ))
        return {
            "checkpoints": checkpoints,
            "product_findings": findings,
            "operator_booleans_are_not_evidence": True,
            "apply_enabled": False,
            "guard_canary": canary,
            "refused_before_product": True,
        }
    try:
        checkpoints.append(recall_silent_unavailable(profile, app, interpreter))
    except Exception as exc:
        checkpoints.append({
            "name": "recall_silent_unavailable", "status": FAILED,
            "error": f"{type(exc).__name__}: {exc}", "operator_boolean_used": False,
        })
        findings.append(record_product_finding(
            operation="recall_silent_unavailable",
            input_value={"index": str(profile / "recall-missing" / "index.db")},
            error=str(exc), route="executable-check",
        ))
    try:
        checkpoints.append(hostile_sentinel(profile, interpreter))
    except Exception as exc:
        checkpoints.append({
            "name": "hostile_actions", "status": FAILED,
            "error": f"{type(exc).__name__}: {exc}", "operator_boolean_used": False,
        })
    checkpoints.extend(mirror_fixture_checks(profile, app, port))
    return {
        "checkpoints": checkpoints,
        "product_findings": findings,
        "operator_booleans_are_not_evidence": True,
        "apply_enabled": False,
        "speaker_accuracy_claim": False,
        "phase5_part_b": "deferred",
    }

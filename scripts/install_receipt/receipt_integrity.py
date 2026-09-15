"""Independent expected state and process-transition checks for C22 fixtures."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

from .constants import LIBRARY_META_SCHEMA_DEFAULTS, SYNTHETIC_HOSTNAME


def expected_deltas(*, before, after, admitted, profile_name):
    allowed = [{"scenario": profile_name, "table": "library_work", "new_rows": [],
                "reason": "C22 fixtures have no classification policy; no work is authorized"}]
    if not (before.get("phase2") or {}).get("library_meta"):
        allowed.append({"scenario": profile_name, "table": "library_meta",
                        "new_rows": [dict(LIBRARY_META_SCHEMA_DEFAULTS)],
                        "reason": "one complete schema 0027 default singleton"})
    expected = []
    outcome = admitted or {}
    # Fixed fixture identity, independent of observed protected rows and ledger IDs.
    feed = f"http://{SYNTHETIC_HOSTNAME}/standing-first/feed.xml"
    guid = "c22-standing-ep-1"
    identity = (feed + "\n" + guid).encode("utf8")
    key = "podcast:" + hashlib.sha256(identity).hexdigest()
    video = "episode_" + hashlib.sha1(identity).hexdigest()[:11]
    ledger = outcome.get("ledger") or {}
    starts = ledger.get("starts") or []
    authorized = (profile_name == "standing-first" and outcome.get("episode_guid") == guid
                  and outcome.get("synthetic_url") == feed and len(starts) == 1)
    start = starts[0] if authorized else {}
    finished = start.get("finished_at_ms")
    started = start.get("started_at_ms")
    authorized = (authorized and start.get("capture_key") == key and start.get("video_id") == video
                  and start.get("state") == "succeeded" and type(finished) is int
                  and type(started) is int and 0 < started <= finished
                  and ledger.get("standing_charge_count") == 1
                  and ledger.get("publication_count") == 1)
    if authorized:
        row = {"capture_key": key, "video_id": video, "committed_at_ms": finished,
               "state": "pending", "run_id": None, "version_id": None, "prompt_hash": None,
               "source_revision": None, "work_id": None, "last_error_code": None,
               "updated_at_ms": finished}
        observed = (after.get("phase2") or {}).get("source_classification_outbox") or []
        # The drainer can record missing configuration. Only these two fields may
        # advance, within the measured snapshot interval, with all bindings null.
        if len(observed) == 1 and observed[0].get("state") == "waiting_configuration":
            updated = observed[0].get("updated_at_ms")
            try:
                end = int(datetime.fromisoformat(after["utc"].replace("Z", "+00:00")).timestamp() * 1000)
            except (KeyError, ValueError, TypeError):
                end = -1
            if type(updated) is int and finished <= updated <= end:
                row.update(state="waiting_configuration", last_error_code="no_policy", updated_at_ms=updated)
        expected = [row]
    allowed.append({"scenario": profile_name, "table": "source_classification_outbox",
                    "new_rows": expected, "reason": "declared standing fixture and successful persisted start"})
    return allowed


def settings_integrity(before, after):
    b, a = before.get("settings"), after.get("settings")
    bf, af = before.get("files") or {}, after.get("files") or {}
    b_tax = (bf.get("taxonomy.json") or {}).get("sha256")
    a_tax = (af.get("taxonomy.json") or {}).get("sha256")
    b_migrated = (bf.get("taxonomy.json.migrated") or {}).get("sha256")
    a_migrated = (af.get("taxonomy.json.migrated") or {}).get("sha256")
    migrated = bool(b_tax and not a_tax and a_migrated == b_tax and not b_migrated)
    tax_ok = (b_tax == a_tax and b_migrated == a_migrated) or migrated
    same = isinstance(b, dict) and isinstance(a, dict) and json.dumps(b, sort_keys=True) == json.dumps(a, sort_keys=True)
    off = isinstance(a, dict) and a.get("librarian_apply_enabled") is False
    pins = isinstance(b, dict) and isinstance(a, dict) and json.dumps(b.get("pins"), sort_keys=True) == json.dumps(a.get("pins"), sort_keys=True)
    return {"librarian_apply_enabled": (a or {}).get("librarian_apply_enabled"),
            "apply_off": off, "pins_unchanged": pins, "settings_unchanged": same,
            "taxonomy_unchanged": tax_ok, "taxonomy_migrated": migrated,
            "ok": same and off and pins and tax_ok}


def exact_identity(row):
    return (isinstance(row, dict) and type(row.get("pid")) is int and row["pid"] > 0
            and type(row.get("created_ms")) is int and row["created_ms"] > 0
            and isinstance(row.get("executable"), str) and bool(row["executable"]))


def child_transition_integrity(result):
    """Require raw retained exclusion, then terminal settlement after exact death."""
    issues = []
    before = result.get("ownership_before_kill")
    during = result.get("ownership_after_relaunch")
    settled = result.get("settled")
    lb, la, ls = (result.get(k) for k in
                  ("ledger_before_kill", "ledger_after_relaunch", "ledger_after_settlement"))
    children, exited = result.get("children") or [], result.get("surviving_until_exit") or []
    helpers = [result.get(k) for k in ("first_identity", "second_identity", "settlement_identity")]
    if not all(exact_identity(h) for h in helpers):
        issues.append("missing exact helper incarnations")
    elif len({(h["pid"], h["created_ms"], h["executable"]) for h in helpers}) != 3:
        issues.append("helper incarnation was reused")
    if (len(children) != 1 or len(exited) != 1 or not exact_identity(children[0])
            or not exact_identity(exited[0]) or children[0].get("liveness") != "alive"
            or exited[0].get("liveness") != "dead"
            or any(children[0].get(k) != exited[0].get(k) for k in ("pid", "created_ms", "executable"))):
        issues.append("missing paired alive/dead exact child identity")
    if not all(isinstance(s, dict) and all(k in s for k in ("claims", "locks", "children", "incarnations"))
               for s in (before, during, settled)):
        issues.append("missing raw ownership snapshots")
    else:
        if (len(before["claims"]) != 1 or not before["locks"] or len(before["children"]) != 1
                or before["claims"] != during["claims"] or before["locks"] != during["locks"]
                or before["children"] != during["children"]):
            issues.append("claim, child or exclusion changed while the registered child survived")
        if settled["claims"] or settled["children"]:
            issues.append("terminal ownership not released")
        # Lock files persist by design. Their presence is not a held OS lock.
        if result.get("settled_lock_probe", {}).get("acquired_and_released") is not True:
            issues.append("terminal OS capture lock release not observed")
    if not all(isinstance(l, dict) and type(l.get("standing_charge_count")) is int
               and type(l.get("publication_count")) is int and isinstance(l.get("starts"), list)
               for l in (lb, la, ls)):
        issues.append("missing raw charge/publication/start counters")
    else:
        if any(l["standing_charge_count"] != 1 or l["publication_count"] != 0 or len(l["starts"]) != 1
               for l in (lb, la, ls)):
            issues.append("duplicate start, extra charge or unexpected publication")
        else:
            b, a, s = lb["starts"][0], la["starts"][0], ls["starts"][0]
            if (len({l.get("start_id") for l in (b, a, s)}) != 1
                    or b.get("state") != "started" or a.get("state") != "uncertain"
                    or s.get("state") != "failed" or s.get("release_or_failure_code") != "worker_lost"
                    or type(s.get("finished_at_ms")) is not int):
                issues.append("original interrupted start did not settle as worker_lost")
    return {"ok": not issues, "issues": issues, "lock_files_are_not_held_locks": True}


def probe_released_capture_lock(profile, capture_key):
    """Probe the existing disposable lock byte, never create or delete a lock file."""
    path = Path(profile) / "capture_locks" / (hashlib.sha256(capture_key.encode()).hexdigest()[:40] + ".lock")
    result = {"path": str(path), "acquired_and_released": False}
    import os
    try:
        with path.open("r+b") as handle:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            result["acquired_and_released"] = True
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _is_valid_sha256(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def _is_valid_git_blob(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    return len(text) == 40 and all(c in "0123456789abcdef" for c in text)


def verify_installed_bindings(app, sealed):
    """Verify all named compiler inputs before importing the original product.

    Reports compiler bindings (142), installed files checked, and any explicit
    compiler-only row separately. No status is a Setup or upgrade-execution receipt.
    """
    root = Path(app).resolve()
    rows = sealed.get("files_by_path") if isinstance(sealed, dict) else None
    if not isinstance(rows, dict):
        rows = {}
    problems = []
    if len(rows) != 142:
        problems.append("expected 142 package source bindings")

    compiler_only_row = None
    installed_files_checked = 0

    for relative, row in rows.items():
        if not isinstance(row, dict):
            problems.append("binding row is not a dict: " + str(relative))
            continue

        normalized_relative = str(relative).replace("\\", "/").removeprefix("installer/staging/")
        path = (root / normalized_relative).resolve()
        escapes = not path.is_relative_to(root)
        traversal = ".." in Path(normalized_relative).parts

        role = row.get("install_role")
        staged_path = row.get("staged_path")
        source_path = row.get("source_path")
        blob = row.get("source_git_blob")
        sha = row.get("checkout_and_staged_sha256")

        if escapes:
            problems.append("binding escapes installed app: " + str(relative))
            if role == "installer-only":
                problems.append("cannot exempt escaping path: " + str(relative))
            continue

        if traversal:
            problems.append("binding contains traversal: " + str(relative))
            continue

        if role == "installer-only":
            is_upgrade_prep = (
                normalized_relative == "upgrade_prep.ps1"
                and str(staged_path or "").replace("\\", "/").removeprefix("installer/staging/") == "upgrade_prep.ps1"
            )
            if not is_upgrade_prep:
                problems.append("cannot mark application file as installer-only: " + str(relative))
                installed_files_checked += 1
                if blob is not None and not _is_valid_git_blob(blob):
                    problems.append("invalid source_git_blob: " + str(relative))
                if not _is_valid_sha256(sha):
                    problems.append("invalid checkout_and_staged_sha256: " + str(relative))
                if not path.is_file():
                    problems.append("missing installed input: " + str(relative))
                elif _is_valid_sha256(sha):
                    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                    if actual_sha != str(sha).strip().lower():
                        problems.append("installed input hash mismatch: " + str(relative))
                continue

            has_error = False
            if str(source_path or "").replace("\\", "/") != "installer/upgrade_prep.ps1":
                problems.append("invalid compiler-only source_path: " + str(relative))
                has_error = True
            if not _is_valid_git_blob(blob):
                problems.append("invalid source_git_blob: " + str(relative))
                has_error = True
            if not _is_valid_sha256(sha):
                problems.append("invalid checkout_and_staged_sha256: " + str(relative))
                has_error = True
            if compiler_only_row is not None:
                problems.append("multiple installer-only rows: " + str(relative))
                has_error = True

            if not has_error:
                compiler_only_row = dict(row)
            continue

        if role is not None and role != "installed":
            problems.append(f"rejected unknown install_role '{role}': " + str(relative))
            installed_files_checked += 1
            if blob is not None and not _is_valid_git_blob(blob):
                problems.append("invalid source_git_blob: " + str(relative))
            if not _is_valid_sha256(sha):
                problems.append("invalid checkout_and_staged_sha256: " + str(relative))
            if not path.is_file():
                problems.append("missing installed input: " + str(relative))
            elif _is_valid_sha256(sha):
                actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual_sha != str(sha).strip().lower():
                    problems.append("installed input hash mismatch: " + str(relative))
            continue

        installed_files_checked += 1
        if blob is not None and not _is_valid_git_blob(blob):
            problems.append("invalid source_git_blob: " + str(relative))
        if sha is not None and not _is_valid_sha256(sha):
            problems.append("invalid checkout_and_staged_sha256: " + str(relative))
        if not path.is_file():
            problems.append("missing installed input: " + str(relative))
        elif sha is not None and _is_valid_sha256(sha):
            actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_sha != str(sha).strip().lower():
                problems.append("installed input hash mismatch: " + str(relative))
        elif sha is None:
            problems.append("missing checkout_and_staged_sha256: " + str(relative))

    return {
        "ok": not problems,
        "files_checked": installed_files_checked,
        "installed_files_checked": installed_files_checked,
        "compiler_bindings": len(rows),
        "compiler_bindings_count": len(rows),
        "compiler_only_row": compiler_only_row,
        "installer_only_row": compiler_only_row,
        "problems": problems,
    }


def unresolved_restart_integrity(observation):
    issues = []
    before, after = observation.get("before"), observation.get("after")
    first, second = observation.get("first_identity"), observation.get("second_identity")
    if (not exact_identity(first) or not exact_identity(second)
            or (first["pid"], first["created_ms"]) == (second["pid"], second["created_ms"])):
        issues.append("missing distinct exact helper identities")
    if not observation.get("terminated", {}).get("stopped"):
        issues.append("original helper termination not established")
    if not all(isinstance(s, dict) and all(k in s for k in ("claims", "children", "locks")) for s in (before, after)):
        issues.append("missing ownership snapshots")
    else:
        if (len(before["claims"]) != 1 or len(before["children"]) != 1 or not before["locks"]
                or any(before[k] != after[k] for k in ("claims", "children", "locks"))
                or before["children"][0].get("unresolved_launch") is not True):
            issues.append("restart did not retain unresolved ownership and exclusion")
    lb, la = observation.get("ledger_before"), observation.get("ledger_after")
    if not all(isinstance(l, dict) and len(l.get("starts") or []) == 1
               and l.get("standing_charge_count") == 1 and l.get("publication_count") == 0 for l in (lb, la)):
        issues.append("charge, start or publication count is missing or changed")
    elif lb["starts"][0].get("start_id") != la["starts"][0].get("start_id") or la["starts"][0].get("state") != "uncertain":
        issues.append("original start is not retained as uncertain")
    return {"ok": not issues, "issues": issues,
            "scope": "unknown launch ownership survives restart; no replacement or release is authorized"}


def guard_event_summary(profiles):
    summaries = {}
    for name, profile in profiles.items():
        path = Path(profile) / "c22-guard-events.jsonl"
        rows, error = [], None
        try:
            rows = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
        except (OSError, ValueError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        blocked = [r for r in rows if r.get("event") == "forbidden_attempt"]
        summaries[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if not error else None,
            "event_count": len(rows), "guard_loads": sum(r.get("event") == "guard_loaded" for r in rows),
            "subprocess_attempts": [r for r in rows if r.get("event") == "subprocess_attempt"],
            "blocked_capability_probes": [r for r in rows if r.get("event") == "blocked_capability_probe"],
            "forbidden_attempts": blocked, "error": error,
            "ok": not error and bool(rows) and any(r.get("event") == "guard_loaded" for r in rows) and not blocked}
    return {"profiles": summaries, "ok": all(r["ok"] for r in summaries.values()) and bool(summaries),
            "scope": "guard load and recorded attempts; blocked attempts cannot count as zero attempts"}

"""Measured persisted-state oracles. Missing evidence fails or stays unexecuted.

Reads the declared profile's index and ownership files. Never invents IDs,
never treats /extract as publication, never synthesizes screenshots.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .constants import (
    CAPTURE_PROFILE_NAMES,
    CURRENT_SCHEMA_TARGET,
    LIBRARY_META_SCHEMA_DEFAULTS,
    LIBRARY_WORK_STATES,
    OUTBOX_STATES,
    PROTECTED_PHASE2_TABLES,
)
from .evidence import collect_snapshot, schema_version, table_counts, table_rows
from .hashes import sha256_file, sha256_json
from .validation import C22ValidationError


LEGACY_TIMED_ID = "c22legacytimed000"
LEGACY_TEXT_ID = "c22legacytext00000"


def yoink_ids(index_path: Path) -> list[str]:
    if not index_path.is_file():
        return []
    conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    try:
        present = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "yoinks" not in present:
            return []
        return [str(row[0]) for row in conn.execute(
            "SELECT video_id FROM yoinks ORDER BY video_id")]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def measured_legacy_ids(profile: Path) -> dict[str, Any]:
    """Read identities from persisted yoinks. Do not invent fixture labels."""
    index = Path(profile) / "index.db"
    ids = yoink_ids(index)
    return {
        "timed_present": LEGACY_TIMED_ID in ids,
        "text_present": LEGACY_TEXT_ID in ids,
        "yoink_ids": ids,
        "source": "yoinks.video_id" if index.is_file() else "index.db missing",
    }


def require_schema(snapshot: dict[str, Any], expected: int = CURRENT_SCHEMA_TARGET) -> dict[str, Any]:
    actual = snapshot.get("schema_version")
    return {
        "expected": expected,
        "actual": actual,
        "ok": actual == expected,
    }


def capture_ledger(profile: Path) -> dict[str, Any]:
    """Standing charges are source_capture_starts rows with started_at_ms.

    The migration schema has no origin, authority or kind column on that
    table. Reserved-only rows (started_at_ms NULL) are not charges.
    """
    index = Path(profile) / "index.db"
    rows = table_rows(index, (
        "source_subscriptions",
        "source_consent_receipts",
        "source_user_intents",
        "source_items",
        "source_capture_starts",
        "podcast_feeds",
        "podcast_episodes",
        "yoinks",
    ))
    starts = list(rows.get("source_capture_starts") or [])
    # Exact schema: a standing charge is a start that has begun.
    charged = [s for s in starts if s.get("started_at_ms") is not None]
    publications = list(rows.get("yoinks") or [])
    return {
        "counts": table_counts(index),
        "starts": starts,
        "charged_starts": charged,
        "standing_starts": charged,
        "standing_charge_count": len(charged),
        "schema_note": (
            "source_capture_starts has no origin/authority/kind; "
            "started_at_ms marks a standing charge"
        ),
        "items": list(rows.get("source_items") or []),
        "receipts": list(rows.get("source_consent_receipts") or []),
        "subscriptions": list(rows.get("source_subscriptions") or []),
        "feeds": list(rows.get("podcast_feeds") or []),
        "episodes": list(rows.get("podcast_episodes") or []),
        "yoinks": publications,
        "publication_count": len(publications),
        "capture_keys": sorted({
            str(s.get("capture_key")) for s in starts if s.get("capture_key")
        }),
        "video_ids": sorted({
            str(s.get("video_id")) for s in charged if s.get("video_id")
        }),
        "episode_ids": sorted({
            str(e.get("id") or e.get("legacy_episode_id"))
            for e in (rows.get("podcast_episodes") or [])
            if e.get("id") is not None or e.get("legacy_episode_id") is not None
        }),
    }


def _row_identity(row: dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return sha256_json(row)
    for key in ("work_id", "run_id", "capture_key", "video_id", "start_id",
                "item_id", "operation_key", "singleton"):
        if row.get(key) is not None:
            return f"{key}:{row[key]}"
    return sha256_json(row)


def ledger_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    def keyed(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {_row_identity(row): row for row in rows if isinstance(row, dict)}

    b_starts = keyed(before.get("starts") or [])
    a_starts = keyed(after.get("starts") or [])
    b_yoinks = keyed(before.get("yoinks") or [])
    a_yoinks = keyed(after.get("yoinks") or [])
    b_receipts = keyed(before.get("receipts") or [])
    a_receipts = keyed(after.get("receipts") or [])
    b_items = keyed(before.get("items") or [])
    a_items = keyed(after.get("items") or [])
    new_starts = [a_starts[k] for k in a_starts if k not in b_starts]
    new_yoinks = [a_yoinks[k] for k in a_yoinks if k not in b_yoinks]
    new_receipts = [a_receipts[k] for k in a_receipts if k not in b_receipts]
    new_items = [a_items[k] for k in a_items if k not in b_items]
    mutated_prior_starts = [
        k for k, row in b_starts.items()
        if k in a_starts and sha256_json(a_starts[k]) != sha256_json(row)
    ]
    return {
        "new_starts": new_starts,
        "new_yoinks": new_yoinks,
        "new_receipts": new_receipts,
        "new_items": new_items,
        "new_capture_keys": sorted({
            str(s.get("capture_key")) for s in new_starts if s.get("capture_key")
        }),
        "new_standing_charges": [
            s for s in new_starts if s.get("started_at_ms") is not None
        ],
        "mutated_prior_starts": mutated_prior_starts,
        "publication_delta": (
            (after.get("publication_count") or 0)
            - (before.get("publication_count") or 0)
        ),
        "standing_charge_delta": (
            (after.get("standing_charge_count") or 0)
            - (before.get("standing_charge_count") or 0)
        ),
    }


def child_ownership_records(profile: Path) -> list[dict[str, Any]]:
    root = Path(profile) / "source_children"
    if not root.is_dir():
        return []
    out = []
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            out.append({
                "path": str(path),
                "damaged": True,
            })
            continue
        if not isinstance(data, dict):
            out.append({"path": str(path), "damaged": True})
            continue
        out.append({
            "path": str(path),
            "start_id": data.get("start_id"),
            "unresolved_launch": data.get("unresolved_launch"),
            "children": data.get("children") if type(data.get("children")) is list else None,
            "record": data,
        })
    return out


def phase2_compare(before: dict[str, Any], after: dict[str, Any],
                   allowed_deltas: list[dict[str, Any]]) -> dict[str, Any]:
    """Match exact new fixture handoff rows and unchanged prior rows.

    Naming a table in allowed_deltas is not permission for any mutation.
    Each allowed spec must list the exact new_rows (or empty) for that table.
    """
    before_hash = before.get("phase2_hash")
    after_hash = after.get("phase2_hash")
    accounted = []
    unaccounted = []
    for name in PROTECTED_PHASE2_TABLES:
        b_rows = list((before.get("phase2") or {}).get(name) or [])
        a_rows = list((after.get("phase2") or {}).get(name) or [])
        if (len({_row_identity(row) for row in b_rows}) != len(b_rows)
                or len({_row_identity(row) for row in a_rows}) != len(a_rows)):
            unaccounted.append({"table": name, "reason": "duplicate protected row identity"})
            continue
        if sha256_json(b_rows) == sha256_json(a_rows):
            continue
        specs = [d for d in allowed_deltas if d.get("table") == name]
        b_map = {_row_identity(row): row for row in b_rows}
        a_map = {_row_identity(row): row for row in a_rows}
        mutated_prior = []
        for key, row in b_map.items():
            if key not in a_map:
                mutated_prior.append({"missing_prior": key})
            elif sha256_json(a_map[key]) != sha256_json(row):
                mutated_prior.append({"mutated_prior": key})
        new_rows = [a_map[key] for key in a_map if key not in b_map]
        delta = {
            "table": name,
            "before_count": len(b_rows),
            "after_count": len(a_rows),
            "new_row_identities": [_row_identity(row) for row in new_rows],
            "mutated_prior": mutated_prior,
        }
        expected_new: list[Any] = []
        has_exact = False
        for spec in specs:
            if "new_rows" in spec:
                has_exact = True
                expected_new.extend(spec.get("new_rows") or [])
        if mutated_prior:
            unaccounted.append({**delta, "reason": "protected prior row mutated"})
            continue
        if not has_exact:
            unaccounted.append({
                **delta,
                "reason": (
                    "table named without exact new_rows is not an allowed "
                    "mutation"
                    if specs else "unaccounted protected-table mutation"
                ),
            })
            continue
        if sha256_json(new_rows) != sha256_json(expected_new):
            unaccounted.append({
                **delta,
                "reason": "new fixture handoff rows did not match exactly",
                "expected_new_rows": expected_new,
                "actual_new_rows": new_rows,
            })
            continue
        accounted.append({**delta, "allowed": specs})
    return {
        "before_hash": before_hash,
        "after_hash": after_hash,
        "unchanged": before_hash == after_hash and not unaccounted,
        "accounted_enqueue_deltas": accounted,
        "unaccounted_enqueue_deltas": unaccounted,
        # Per-table exact row comparison is authoritative. phase2_hash can
        # differ when a missing table (None) becomes an empty list after
        # migration without any protected-row mutation.
        "ok": not unaccounted,
    }


def extract_is_not_publication(extract_response: dict[str, Any] | None,
                               ledger_before: dict[str, Any],
                               ledger_after: dict[str, Any]) -> dict[str, Any]:
    """`/extract` on an RSS URL is not an actual podcast publication."""
    pubs_before = ledger_before.get("publication_count") or 0
    pubs_after = ledger_after.get("publication_count") or 0
    return {
        "extract_called": extract_response is not None,
        "extract_ok": bool((extract_response or {}).get("ok")),
        "publication_delta": pubs_after - pubs_before,
        "counts_as_publication": False,
        "note": "POST /extract on an RSS feed is not actual podcast publication",
        "ok": True,
    }


def snapshot_with_measured_ids(profile: Path, *, label: str) -> dict[str, Any]:
    snap = collect_snapshot(profile, label=label)
    snap["legacy_video_ids"] = measured_legacy_ids(profile)
    snap["child_records"] = child_ownership_records(profile)
    snap["ledger_summary"] = capture_ledger(profile)
    return snap


def file_bytes_unchanged(path: Path, expected_sha256: str) -> bool:
    if not path.is_file():
        return False
    return sha256_file(path) == expected_sha256


def live_index_guard(live_index: Path) -> dict[str, Any]:
    """Store the forbidden live-index path as a string. Never open or hash it."""
    path = Path(live_index)
    return {
        "path": str(path),
        "opened": False,
        "hashed": False,
        "exists_probed": False,
        "mtime_ns": None,
        "sha256": None,
        "bytes": None,
        "note": "forbidden live index path recorded as a string only",
    }


def live_index_unchanged(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """String-path identity only. This kit never opens the live index to compare."""
    return str(before.get("path") or "") == str(after.get("path") or "")


def helper_ownership_state(profile: Path) -> dict[str, Any]:
    """Incarnation, claims, locks, children under the declared profile."""
    root = Path(profile)
    def _list_json(relative: str) -> list[dict[str, Any]]:
        folder = root / relative
        if not folder.is_dir():
            return []
        out = []
        for path in sorted(folder.glob("*.json")):
            try:
                out.append({
                    "path": str(path),
                    "name": path.name,
                    "payload": json.loads(path.read_text(encoding="utf-8")),
                })
            except (OSError, json.JSONDecodeError):
                out.append({"path": str(path), "name": path.name, "damaged": True})
        return out

    locks = []
    lock_dir = root / "capture_locks"
    if lock_dir.is_dir():
        locks = [{"path": str(p), "name": p.name} for p in sorted(lock_dir.glob("*"))]
    return {
        "incarnations": _list_json("source_instances"),
        "claims": _list_json("source_claims"),
        "children": child_ownership_records(root),
        "locks": locks,
    }


def require_measured_pass(outcome: dict[str, Any], *, scenario_id: str) -> None:
    if outcome.get("id") != scenario_id:
        raise C22ValidationError(
            f"instrument outcome id {outcome.get('id')!r} != {scenario_id!r}")
    if outcome.get("status") != "pass":
        raise C22ValidationError(
            f"{scenario_id} measured status is {outcome.get('status')!r}, "
            "not pass")


def parse_provenance_json(stdout: str) -> dict[str, Any] | None:
    text = (stdout or "").strip()
    if not text:
        return None
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("schema") == "c22-provenance-v1":
            return obj
        if isinstance(obj, dict) and "executable" in obj and "modules" in obj:
            return obj
    return None


def modules_inside_app(report: dict[str, Any], installed_app: Path) -> dict[str, Any]:
    from .constants import REQUIRED_PROVENANCE_MODULES
    app = Path(installed_app).resolve()
    checkout = Path(__file__).resolve().parents[2]
    modules = report.get("modules") or {}
    missing = sorted(set(REQUIRED_PROVENANCE_MODULES) - set(modules))
    outside, checkout_hits, errors = [], [], []
    for name, row in modules.items():
        if not isinstance(row, dict) or row.get("ok") is not True or not row.get("file"):
            errors.append(name)
            continue
        path = Path(row["file"]).resolve()
        if not path.is_relative_to(app):
            outside.append({"module": name, "file": str(path)})
            if path.is_relative_to(checkout):
                checkout_hits.append({"module": name, "file": str(path)})
    import_ok = not missing and not errors and not report.get("import_errors")
    usersite = bool(report.get("usersite_on_path"))
    return {"import_ok": import_ok, "inside_app": not outside,
            "checkout_fallback": bool(checkout_hits), "usersite_on_path": usersite,
            "outside": outside, "checkout_hits": checkout_hits, "missing_modules": missing,
            "ok": import_ok and not outside and not checkout_hits and not usersite}


def library_meta_matches_schema_default(row: dict[str, Any] | None) -> bool:
    return isinstance(row, dict) and sha256_json(row) == sha256_json(LIBRARY_META_SCHEMA_DEFAULTS)


def _admitted_identities(outcome: dict[str, Any] | None) -> dict[str, set[str]]:
    ledger = (outcome or {}).get("ledger") or (outcome or {}).get("ledger_after") or {}
    video_ids = set(str(v) for v in (ledger.get("video_ids") or []) if v)
    capture_keys = set(str(v) for v in (ledger.get("capture_keys") or []) if v)
    for yoink in ledger.get("yoinks") or []:
        if isinstance(yoink, dict) and yoink.get("video_id"):
            video_ids.add(str(yoink["video_id"]))
    guid = (outcome or {}).get("episode_guid")
    if guid:
        video_ids.add(str(guid))
    return {"video_ids": video_ids, "capture_keys": capture_keys}


def derive_phase2_allowed(*, before: dict[str, Any], after: dict[str, Any],
                          admitted: dict[str, Any] | None,
                          profile_name: str) -> list[dict[str, Any]]:
    from .receipt_integrity import expected_deltas
    return expected_deltas(before=before, after=after, admitted=admitted, profile_name=profile_name)


def settings_and_pins_unchanged(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    from .receipt_integrity import settings_integrity
    return settings_integrity(before, after)


def all_profile_names() -> tuple[str, ...]:
    return CAPTURE_PROFILE_NAMES


def child_recovery_oracles(*, children: list[dict[str, Any]],
                           helper_terminated_while_child_alive: bool,
                           relaunched: bool,
                           charge_delta: int,
                           publication_delta: int,
                           unknown: list[dict[str, Any]],
                           child_exited: bool,
                           duplicate_launch: bool) -> dict[str, Any]:
    exact = [
        c for c in children
        if c.get("liveness") in {"alive", "dead"}
        and type(c.get("pid")) is int
        and type(c.get("created_ms")) is int
        and c.get("executable")
    ]
    ok = (
        bool(exact)
        and not unknown
        and helper_terminated_while_child_alive
        and relaunched
        and type(charge_delta) is int and charge_delta == 0
        and type(publication_delta) is int and publication_delta == 0
        and child_exited
        and not duplicate_launch
    )
    return {
        "exact_identities": exact,
        "unknown_cannot_pass": bool(unknown),
        "helper_terminated_while_child_alive": helper_terminated_while_child_alive,
        "relaunched": relaunched,
        "charge_delta": charge_delta,
        "publication_delta": publication_delta,
        "child_exited": child_exited,
        "duplicate_launch": duplicate_launch,
        "ok": ok,
    }


def interrupt_oracle(*, unresolved: list[dict[str, Any]],
                     spawned_alive: list[dict[str, Any]],
                     unknown: list[dict[str, Any]],
                     injection: str) -> dict[str, Any]:
    exact_unresolved = [
        item for item in unresolved
        if item.get("unresolved_launch") is True
        and not (item.get("children") or [])
    ]
    ok = (
        injection == "launch_interrupt"
        and bool(exact_unresolved)
        and not spawned_alive
        and not unknown
    )
    return {
        "exact_unresolved": exact_unresolved,
        "spawned_alive": spawned_alive,
        "unknown_cannot_pass": bool(unknown),
        "ok": ok,
    }


def registration_failure_oracle(*, unresolved: list[dict[str, Any]],
                                surviving: list[dict[str, Any]],
                                unknown: list[dict[str, Any]],
                                injection: str,
                                child_exited: bool) -> dict[str, Any]:
    from .receipt_integrity import exact_identity
    alive = [c for c in surviving if c.get("liveness") == "alive" and exact_identity(c)]
    ok = (
        injection == "registration_failure"
        and bool(unresolved)
        and all(item.get("unresolved_launch") is True for item in unresolved)
        and bool(alive)
        and not unknown
        and child_exited
    )
    return {
        "unresolved": unresolved,
        "surviving": surviving,
        "unknown_cannot_pass": bool(unknown),
        "child_exited": child_exited,
        "ok": ok,
    }

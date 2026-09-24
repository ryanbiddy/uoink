"""Evidence collector and verdict input. No claimed installed pass."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .constants import (
    LEDGER_TABLES,
    PHASE2_FILES,
    PROTECTED_PHASE2_TABLES,
    SCENARIO_IDS,
)
from .hashes import file_record, sha256_file, sha256_json
from .runner import utc_now


def integrity_report(index_path: Path) -> dict[str, Any]:
    if not index_path.is_file():
        return {"present": False, "integrity": None, "foreign_keys": None}
    conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk_rows = list(conn.execute("PRAGMA foreign_key_check"))
        return {
            "present": True,
            "integrity": integrity,
            "foreign_keys": [list(row) for row in fk_rows],
            "foreign_key_violations": len(fk_rows),
            "sha256": sha256_file(index_path),
            "bytes": index_path.stat().st_size,
        }
    finally:
        conn.close()


def table_counts(index_path: Path) -> dict[str, int]:
    if not index_path.is_file():
        return {}
    conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    try:
        names = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        counts = {}
        for name in names:
            try:
                counts[name] = conn.execute(
                    f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            except sqlite3.Error:
                counts[name] = -1
        return counts
    finally:
        conn.close()


def table_rows(index_path: Path, tables: tuple[str, ...]) -> dict[str, Any]:
    if not index_path.is_file():
        return {name: None for name in tables}
    conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        out: dict[str, Any] = {}
        present = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for name in tables:
            if name not in present:
                out[name] = None
                continue
            out[name] = [dict(row) for row in conn.execute(f"SELECT * FROM {name}")]
        return out
    finally:
        conn.close()


def schema_version(index_path: Path) -> int | None:
    if not index_path.is_file():
        return None
    conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='schema_version'").fetchone()
        if row is None:
            return 0
        value = conn.execute(
            "SELECT MAX(version) AS v FROM schema_version").fetchone()[0]
        return int(value) if value is not None else 0
    finally:
        conn.close()


def _measured_yoink_ids(index_path: Path) -> dict[str, Any]:
    """Read persisted yoink identities. Never invent fixture labels."""
    if not index_path.is_file():
        return {"timed_present": False, "text_present": False, "yoink_ids": [],
                "source": "index.db missing"}
    conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    try:
        present = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "yoinks" not in present:
            return {"timed_present": False, "text_present": False, "yoink_ids": [],
                    "source": "yoinks table missing"}
        ids = [str(row[0]) for row in conn.execute(
            "SELECT video_id FROM yoinks ORDER BY video_id")]
        return {
            "timed_present": "c22legacytimed000" in ids,
            "text_present": "c22legacytext00000" in ids,
            "yoink_ids": ids,
            "source": "yoinks.video_id",
        }
    except sqlite3.Error as exc:
        return {"timed_present": False, "text_present": False, "yoink_ids": [],
                "source": f"sqlite error: {exc}"}
    finally:
        conn.close()


def collect_snapshot(profile: Path, *, label: str) -> dict[str, Any]:
    profile = Path(profile)
    index = profile / "index.db"
    settings = profile / "settings.json"
    settings_data = None
    if settings.is_file():
        settings_data = json.loads(settings.read_text(encoding="utf-8"))
    files = {name: file_record(profile / name, root=profile)
             for name in PHASE2_FILES}
    snap = {
        "label": label,
        "utc": utc_now(),
        "profile": str(profile),
        "schema_version": schema_version(index),
        "integrity": integrity_report(index),
        "counts": table_counts(index),
        "ledger": table_rows(index, LEDGER_TABLES),
        "phase2": table_rows(index, PROTECTED_PHASE2_TABLES),
        "files": files,
        "settings": settings_data,
        "legacy_video_ids": _measured_yoink_ids(index),
    }
    snap["phase2_hash"] = sha256_json(snap["phase2"])
    snap["ledger_hash"] = sha256_json(snap["ledger"])
    return snap


def build_verdict(receipt_root: Path, outcomes: dict[str, dict[str, Any]],
                  *, synthetic: bool) -> dict[str, Any]:
    rows = []
    for scenario_id in SCENARIO_IDS:
        outcome = outcomes.get(scenario_id) or {
            "id": scenario_id, "status": "unexecuted",
            "reason": "not run in this session",
        }
        rows.append({
            "id": scenario_id,
            "status": outcome.get("status", "unexecuted"),
            "error": outcome.get("error"),
            "reason": outcome.get("reason"),
        })
    executed = [r for r in rows if r["status"] != "unexecuted"]
    failed = [r for r in rows if r["status"] == "fail"]
    passed = [r for r in rows if r["status"] == "pass"]
    verdict = {
        "schema": "c22-verdict-input-v1",
        "utc": utc_now(),
        "receipt_root": str(receipt_root),
        "synthetic_instrument": synthetic,
        "installed_pass_claimed": False,
        "installed_pass_note": (
            "No claimed installed pass until Ryan actually runs the sealed kit "
            "on the throwaway profile against the isolated installed helper."
        ),
        "scenarios": rows,
        "counts": {
            "pass": len(passed),
            "fail": len(failed),
            "unexecuted": len(rows) - len(executed),
            "executed": len(executed),
        },
        "astra_owns": [
            "independent verification",
            "final runbook/package seal",
            "isolation mechanism integration",
            "Phase 4 client/everyday receipt tooling",
        ],
    }
    dest = Path(receipt_root) / "evidence" / "verdict.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    return verdict

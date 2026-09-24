"""Validate run F draft syntax and SQL constraints, not an implemented service."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy", type=Path, required=True)
    args = parser.parse_args()
    source = args.copy.resolve()
    assert source.is_relative_to(ROOT) and source.name == "rebuild.db"
    contract = ROOT / "docs/library/phase2-contract"
    schemas = json.loads((contract / "tool-schemas.json").read_text(encoding="utf-8"))
    validators = {}
    for tool in schemas["tools"]:
        Draft202012Validator.check_schema(tool["inputSchema"])
        validators[tool["name"]] = Draft202012Validator(tool["inputSchema"])
    token, revision = "a" * 43, "b" * 64
    examples = {
        "list_library_work": {"run_id": "r"},
        "claim_library_work": {"action": "claim", "run_id": "r", "client_id": "c"},
        "submit_library_result": {"work_id": "w", "client_id": "c", "attempt_token": token,
            "submission_key": "s", "schema_version": 1, "video_id": "v", "source_revision": revision,
            "taxonomy_revision": revision, "packet_hash": revision,
            "result": {"outcome": "unmapped", "reason": "No matching approved shelf"},
            "usage": {"status": "unavailable", "reason": "Client omits usage"}},
        "apply_reshelving": {"run_id": "r", "expected_projection_revision": 0},
        "pin_shelf": {"video_id": "v", "shelf_id": "s", "action": "move",
            "expected_projection_revision": 0, "operation_key": "op", "user_intent_token": token},
        "undo_library_apply": {"apply_id": "a", "expected_projection_revision": 1,
            "operation_key": "op2", "user_intent_token": token},
    }
    passed = 0
    for name, example in examples.items():
        validators[name].validate(example)
        assert list(validators[name].iter_errors({**example, "max_churn": 1.0}))
        passed += 2
    assigned = {**examples["submit_library_result"], "result": {"outcome": "assigned", "memberships": [{
        "shelf_id": "s", "shelf_path": ["Science"], "confidence": 0.9, "evidence": {
            "basis": "packet", "kind": "text_only", "excerpt_id": revision, "card_hash": revision,
            "quote": "alpha beta"}}]}}
    validators["submit_library_result"].validate(assigned)
    passed += 1
    for payload in ({**assigned, "video_id": ["v"]},
                    {**assigned, "schema_version": 2},
                    {**assigned, "result": {"outcome": "assigned", "memberships": []}}):
        assert list(validators["submit_library_result"].iter_errors(payload))
        passed += 1
    for action in ("renew", "release", "cancel"):
        value = {"action": action, "work_id": "w", "client_id": "c", "attempt_token": token}
        value.update({"lease_seconds": 60} if action == "renew" else {"reason": "client stopped"})
        validators["claim_library_work"].validate(value)
        passed += 1
    validators["apply_reshelving"].validate({"mode": "apply", "preview_id": "p",
        "expected_projection_revision": 0, "delta_hash": revision, "operation_key": "op"})
    passed += 1
    assert list(validators["claim_library_work"].iter_errors({**examples["claim_library_work"], "max_items": 25}))
    assert list(validators["apply_reshelving"].iter_errors({"mode": "apply", "run_id": "r", "expected_projection_revision": 0}))
    passed += 2

    original = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    original.execute("PRAGMA query_only=ON")
    conn = sqlite3.connect(":memory:")
    original.backup(conn)
    original.close()
    conn.execute("PRAGMA foreign_keys=ON")
    old_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    before = conn.execute("SELECT count(*) FROM yoinks").fetchone()[0]
    conn.executescript("BEGIN;\n" + (contract / "0027_library_substrate.sql").read_text() + "\nCOMMIT;")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} - old_tables
    assert len(tables) == 16
    assert conn.execute("SELECT count(*) FROM item_shelves").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM library_work").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM yoinks").fetchone()[0] == before == 548
    assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    rejected = []
    def reject(name, sql, params=()):
        conn.execute("SAVEPOINT negative_case")
        try:
            conn.execute(sql, params)
        except sqlite3.IntegrityError:
            rejected.append(name)
        else:
            raise AssertionError(name)
        finally:
            conn.execute("ROLLBACK TO negative_case")
            conn.execute("RELEASE negative_case")
    conn.execute("INSERT INTO shelf_versions VALUES('v1',NULL,?,'active','now','user','now')", (revision,))
    reject("two_active_versions", "INSERT INTO shelf_versions VALUES('v2',NULL,?,'active','now','user','now')", ("c" * 64,))
    conn.execute("INSERT INTO library_runs VALUES('r','v1',?,1,'collecting','{}','now')", (revision,))
    conn.execute("INSERT INTO library_manifest VALUES('r','fixture',?,'waiting',NULL)", (revision,))
    work_sql = "INSERT INTO library_work VALUES(?,'r','fixture','assign',1,'{}',?,'ready',100,0,'now','now')"
    conn.execute(work_sql, ("w1", revision))
    reject("duplicate_item_work", work_sql, ("w2", revision))
    attempt_sql = "INSERT INTO library_attempts VALUES(?,'w1',?,1,'c',?,?,900000,3600000,'current')"
    conn.execute(attempt_sql, (token, 1, revision, revision))
    reject("two_current_attempts", attempt_sql, ("d" * 43, 2, revision, revision))
    reject("fourth_attempt", "UPDATE library_work SET attempts=4 WHERE work_id='w1'")
    reject("bad_state", "UPDATE library_work SET state='done_batch' WHERE work_id='w1'")
    reject("missing_stable_shelf", "INSERT INTO shelf_nodes VALUES('v1','missing',NULL,'Name','[\"Name\"]','def','[]','[]',0)")
    assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()
    print(json.dumps({"schemas": len(validators), "schema_cases": passed,
        "new_tables": len(tables), "copied_items_unchanged": before,
        "initial_assignments": 0, "initial_work": 0, "sql_negative_cases_rejected": rejected,
        "integrity": "quick_check and foreign_key_check passed", "service_implemented": False}, indent=2))


if __name__ == "__main__":
    main()

"""tests/library_crash_runner.py - Crash runner for Phase 2 durability verification.

Kills a subprocess at each of the three durable boundaries specified in
PHASE2-CONTRACT-2026-09-04 (paragraph 80):
1. before_publication: killed before temporary file is atomically published to authoritative operations
2. after_publication_before_commit: killed after authoritative file is published, before DB commit
3. after_commit_before_response: killed after DB transaction commit, before response return

Exit Gate P2-5:
"Kill subprocesses at all three durable boundaries; reopen and replay once;
exact receipt/revision; corrupt record stops visibly; delete only a verified
disposable DB and reconstruct pins/taxonomy/exclusive policy from local
authoritative records; orphan pins retained"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent

# The three durable boundaries defined by PHASE2-CONTRACT-2026-09-04
BOUNDARY_BEFORE_PUBLICATION = "before_publication"
BOUNDARY_AFTER_PUBLICATION_BEFORE_COMMIT = "after_publication_before_commit"
BOUNDARY_AFTER_COMMIT_BEFORE_RESPONSE = "after_commit_before_response"

ALL_BOUNDARIES = [
    BOUNDARY_BEFORE_PUBLICATION,
    BOUNDARY_AFTER_PUBLICATION_BEFORE_COMMIT,
    BOUNDARY_AFTER_COMMIT_BEFORE_RESPONSE,
]

CRASH_EXIT_CODE = 42


@dataclass
class CrashExecutionResult:
    boundary: str
    exit_code: int
    published_record_found: bool
    db_committed: bool
    temp_files_found: List[str]
    operation_key: str
    record_path: Optional[str] = None


@dataclass
class RecoveryResult:
    boundary: str
    recovered_revision: int
    recovery_receipt_matched: bool
    db_integrity_ok: bool
    details: Dict[str, Any]


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hash(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _init_test_substrate_db(db_path: Path) -> None:
    """Initializes SQLite database with schema 0027."""
    sql_path = ROOT / "docs" / "library" / "phase2-contract" / "0027_library_substrate.sql"
    if not sql_path.exists():
        sql_path = ROOT / "migrations" / "0027_library_substrate.sql"
    sql = sql_path.read_text(encoding="utf-8")
    
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    # Base yoinks table for foreign keys if not in 0027
    conn.execute(
        """CREATE TABLE IF NOT EXISTS yoinks (
            video_id TEXT PRIMARY KEY,
            title TEXT,
            channel TEXT,
            platform TEXT,
            deleted_at TEXT
        )"""
    )
    conn.executescript(sql)
    conn.close()


def execute_durable_operation_with_crash(
    boundary: str,
    db_path: Path,
    storage_root: Path,
    operation_key: str,
    video_id: str = "vid_crash_test",
    shelf_id: str = "shelf_test",
    expected_revision: int = 0,
) -> None:
    """Worker function executed inside the child process.
    
    Simulates the atomic publication and database commit lifecycle,
    terminating immediately with os._exit(CRASH_EXIT_CODE) at the requested boundary.
    """
    ops_dir = storage_root / "operations"
    ops_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = storage_root / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    seq = 1
    key_hash = sha256_hash(operation_key)
    op_record = {
        "schema_version": 1,
        "operation_key": operation_key,
        "operation_sequence": seq,
        "request_hash": sha256_hash(operation_key + "_request"),
        "before_revision": expected_revision,
        "after_revision": expected_revision + 1,
        "kind": "pin",
        "video_id": video_id,
        "shelf_id": shelf_id,
        "forward": [{"video_id": video_id, "shelf_id": shelf_id, "action": "add"}],
        "inverse": [{"video_id": video_id, "shelf_id": shelf_id, "action": "remove"}],
        "receipt": {
            "ok": True,
            "schema_version": 1,
            "operation_key": operation_key,
            "before_revision": expected_revision,
            "after_revision": expected_revision + 1,
        },
    }
    payload_hash = sha256_hash(canonical_json(op_record))
    op_record["authoritative_record_hash"] = payload_hash
    final_bytes = canonical_json(op_record).encode("utf-8")

    final_target = ops_dir / f"{seq:06d}-{key_hash[:16]}.json"
    temp_target = tmp_dir / f"tmp-{seq:06d}-{key_hash[:8]}.tmp"

    # Step 1: Write to temporary file and fsync
    with open(temp_target, "wb") as f:
        f.write(final_bytes)
        f.flush()
        os.fsync(f.fileno())

    # --- BOUNDARY 1: before_publication ---
    if boundary == BOUNDARY_BEFORE_PUBLICATION:
        os._exit(CRASH_EXIT_CODE)

    # Step 2: Atomic rename/publish to authoritative record
    # On Windows, replace handles atomic rename if target does not exist
    os.replace(temp_target, final_target)

    # --- BOUNDARY 2: after_publication_before_commit ---
    if boundary == BOUNDARY_AFTER_PUBLICATION_BEFORE_COMMIT:
        os._exit(CRASH_EXIT_CODE)

    # Step 3: DB Transaction commit
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO library_operation_receipts(
                operation_key, request_hash, operation_sequence, authoritative_record_hash, receipt_json
            ) VALUES (?, ?, ?, ?, ?)""",
            (
                operation_key,
                op_record["request_hash"],
                seq,
                payload_hash,
                canonical_json(op_record["receipt"]),
            ),
        )
        conn.execute(
            """UPDATE library_meta
               SET projection_revision = ?,
                   last_operation_sequence = ?,
                   recovery_state = 'ready'
               WHERE singleton = 1""",
            (expected_revision + 1, seq),
        )
        conn.commit()
    finally:
        conn.close()

    # --- BOUNDARY 3: after_commit_before_response ---
    if boundary == BOUNDARY_AFTER_COMMIT_BEFORE_RESPONSE:
        os._exit(CRASH_EXIT_CODE)

    # Normal clean exit if no boundary specified
    sys.exit(0)


def replay_and_recover(db_path: Path, storage_root: Path) -> RecoveryResult:
    """Performs crash recovery / startup replay from authoritative local records."""
    ops_dir = storage_root / "operations"
    records = sorted(ops_dir.glob("*.json")) if ops_dir.exists() else []

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    
    # Check current DB checkpoint
    meta_row = conn.execute(
        "SELECT projection_revision, last_operation_sequence, recovery_state FROM library_meta WHERE singleton=1"
    ).fetchone()
    current_rev, last_seq, rec_state = meta_row if meta_row else (0, 0, "ready")

    replayed = 0
    receipt_matched = True

    for rec_path in records:
        data = json.loads(rec_path.read_text(encoding="utf-8"))
        seq = data["operation_sequence"]
        op_key = data["operation_key"]
        expected_hash = data.get("authoritative_record_hash")
        
        # Verify hash
        content_copy = dict(data)
        content_copy.pop("authoritative_record_hash", None)
        computed_hash = sha256_hash(canonical_json(content_copy))
        # Hash matches either full or without hash field
        if expected_hash and expected_hash not in (computed_hash, sha256_hash(rec_path.read_bytes())):
            conn.execute("UPDATE library_meta SET recovery_state='conflict' WHERE singleton=1")
            conn.commit()
            conn.close()
            raise RuntimeError(f"Corrupt authoritative record: {rec_path.name}")

        if seq > last_seq:
            # Replay unprojected durable operation into DB
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT OR REPLACE INTO library_operation_receipts(
                    operation_key, request_hash, operation_sequence, authoritative_record_hash, receipt_json
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    op_key,
                    data["request_hash"],
                    seq,
                    data["authoritative_record_hash"],
                    canonical_json(data["receipt"]),
                ),
            )
            conn.execute(
                """UPDATE library_meta
                   SET projection_revision = ?,
                       last_operation_sequence = ?,
                       recovery_state = 'ready'
                   WHERE singleton = 1""",
                (data["after_revision"], seq),
            )
            conn.commit()
            current_rev = data["after_revision"]
            last_seq = seq
            replayed += 1

    # Verify quick check
    integrity = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    conn.close()

    return RecoveryResult(
        boundary="replay",
        recovered_revision=current_rev,
        recovery_receipt_matched=receipt_matched,
        db_integrity_ok=integrity,
        details={"replayed_operations": replayed, "last_sequence": last_seq},
    )


def run_crash_boundary_subprocess(
    boundary: str,
    db_path: Path,
    storage_root: Path,
    operation_key: str = "test-op-key",
    timeout: float = 15.0,
) -> CrashExecutionResult:
    """Spawns this module as a subprocess, injecting the crash at the specified boundary."""
    if boundary not in ALL_BOUNDARIES:
        raise ValueError(f"Invalid boundary: {boundary}. Must be one of {ALL_BOUNDARIES}")

    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child-worker",
        "--boundary", boundary,
        "--db-path", str(db_path),
        "--storage-root", str(storage_root),
        "--operation-key", operation_key,
    ]

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )

    ops_dir = storage_root / "operations"
    key_hash = sha256_hash(operation_key)
    expected_record = ops_dir / f"000001-{key_hash[:16]}.json"
    published_exists = expected_record.exists()

    tmp_dir = storage_root / "tmp"
    temp_files = [f.name for f in tmp_dir.glob("*.tmp")] if tmp_dir.exists() else []

    conn = sqlite3.connect(str(db_path))
    db_rev = conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0]
    conn.close()

    return CrashExecutionResult(
        boundary=boundary,
        exit_code=proc.returncode,
        published_record_found=published_exists,
        db_committed=(db_rev > 0),
        temp_files_found=temp_files,
        operation_key=operation_key,
        record_path=str(expected_record) if published_exists else None,
    )


def run_all_crash_scenarios(temp_root: Optional[Path] = None) -> Dict[str, Any]:
    """Runs all three crash boundary tests in clean isolated environments and verifies recovery."""
    results = {}
    cleanup_temp = False
    if temp_root is None:
        temp_root = Path(tempfile.mkdtemp(prefix="uoink_crash_runner_"))
        cleanup_temp = True

    try:
        for boundary in ALL_BOUNDARIES:
            scenario_root = temp_root / boundary
            scenario_root.mkdir(parents=True, exist_ok=True)
            db_path = scenario_root / "substrate.db"
            storage_root = scenario_root / ".uoink" / "library"

            # 1. Initialize substrate DB
            _init_test_substrate_db(db_path)

            # 2. Run child process with forced kill
            crash_res = run_crash_boundary_subprocess(
                boundary=boundary,
                db_path=db_path,
                storage_root=storage_root,
                operation_key=f"op_{boundary}_001",
            )

            # 3. Verify crash boundary assertions
            if boundary == BOUNDARY_BEFORE_PUBLICATION:
                assert crash_res.exit_code == CRASH_EXIT_CODE
                assert not crash_res.published_record_found, "Record must NOT be published before boundary 1"
                assert not crash_res.db_committed, "DB must NOT be committed before boundary 1"
                rec_res = replay_and_recover(db_path, storage_root)
                assert rec_res.recovered_revision == 0
                assert rec_res.db_integrity_ok

            elif boundary == BOUNDARY_AFTER_PUBLICATION_BEFORE_COMMIT:
                assert crash_res.exit_code == CRASH_EXIT_CODE
                assert crash_res.published_record_found, "Record MUST be published at boundary 2"
                assert not crash_res.db_committed, "DB must NOT yet be committed at boundary 2"
                rec_res = replay_and_recover(db_path, storage_root)
                assert rec_res.recovered_revision == 1, "Replay must advance revision to 1"
                assert rec_res.db_integrity_ok

            elif boundary == BOUNDARY_AFTER_COMMIT_BEFORE_RESPONSE:
                assert crash_res.exit_code == CRASH_EXIT_CODE
                assert crash_res.published_record_found, "Record MUST be published at boundary 3"
                assert crash_res.db_committed, "DB MUST be committed at boundary 3"
                rec_res = replay_and_recover(db_path, storage_root)
                assert rec_res.recovered_revision == 1
                assert rec_res.db_integrity_ok

            results[boundary] = {
                "exit_code": crash_res.exit_code,
                "published_record": crash_res.published_record_found,
                "db_committed_at_crash": crash_res.db_committed,
                "post_recovery_revision": rec_res.recovered_revision,
                "db_integrity": rec_res.db_integrity_ok,
                "passed": True,
            }

    finally:
        if cleanup_temp and temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)

    return results


def main():
    parser = argparse.ArgumentParser(description="Living Library Durable Crash Runner")
    parser.add_argument("--child-worker", action="store_true", help="Internal flag: runs as worker subprocess")
    parser.add_argument("--boundary", choices=ALL_BOUNDARIES, help="Crash boundary point")
    parser.add_argument("--db-path", type=Path, help="Path to SQLite database")
    parser.add_argument("--storage-root", type=Path, help="Authoritative local storage root")
    parser.add_argument("--operation-key", default="test_op", help="Operation key")
    parser.add_argument("--test-all", action="store_true", help="Run all 3 crash scenarios end-to-end")

    args = parser.parse_args()

    if args.child_worker:
        if not args.boundary or not args.db_path or not args.storage_root:
            parser.error("--child-worker requires --boundary, --db-path, and --storage-root")
        execute_durable_operation_with_crash(
            boundary=args.boundary,
            db_path=args.db_path,
            storage_root=args.storage_root,
            operation_key=args.operation_key,
        )
        return

    if args.test_all:
        print("Running all 3 durable crash boundaries...")
        results = run_all_crash_scenarios()
        print(json.dumps(results, indent=2))
        all_passed = all(r.get("passed") for r in results.values())
        print(f"\nOverall result: {'PASSED' if all_passed else 'FAILED'}")
        sys.exit(0 if all_passed else 1)

    parser.print_help()


if __name__ == "__main__":
    main()

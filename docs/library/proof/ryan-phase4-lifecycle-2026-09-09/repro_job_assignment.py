"""Standalone job-assignment failed-start snapshots. Does not kill extra
writers, release gates, or reset globals except the test's own monkeypatch
of _win_assign_job, which the acceptance case itself applies.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import library_mirror as mirror  # noqa: E402
from p4_snap import snapshot  # noqa: E402


def main() -> int:
    dest_root = Path(tempfile.mkdtemp(prefix="p4-job-"))
    dest = dest_root / "v"
    dest.mkdir()
    src = dest_root / "src.bin"
    dst = dest_root / "dst.bin"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")
    snapshot("repro-before", extra={"dest": str(dest)})
    original = mirror._win_assign_job
    mirror._win_assign_job = lambda job, proc: False
    error = None
    try:
        try:
            mirror._VaultIoSession.start(str(dest))
        except OSError as exc:
            error = f"{type(exc).__name__}:{exc}"
    finally:
        mirror._win_assign_job = original
    lease = None
    lease_error = None
    try:
        lease = mirror._read_dest_lease(str(dest))
    except Exception as exc:
        lease_error = f"{type(exc).__name__}:{exc}"
    parent_lease = None
    try:
        parent_lease = mirror._lease_read_parent(str(dest))
    except Exception as exc:
        parent_lease = f"error:{type(exc).__name__}:{exc}"
    foreign = None
    try:
        foreign = mirror._foreign_vault_worker_alive(str(dest))
    except Exception as exc:
        foreign = f"error:{type(exc).__name__}:{exc}"
    extra = {
        "dest": str(dest),
        "error": error,
        "dst_bytes": dst.read_bytes().decode("latin1"),
        "lease": lease,
        "lease_error": lease_error,
        "parent_lease": parent_lease,
        "foreign_alive": foreign,
        "bound_must_refuse": mirror._bound_session_must_refuse_dest(),
        "lease_path_exists": mirror._dest_lease_path(str(dest)).is_file(),
    }
    snapshot("repro-after", extra=extra)
    print(json.dumps(extra, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

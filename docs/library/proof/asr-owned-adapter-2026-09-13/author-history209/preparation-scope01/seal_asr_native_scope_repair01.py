"""Static checks and seal for scope repair source preparation only."""
import hashlib
import json
from pathlib import Path

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
ROOT = BASE / "_scratch/asr-native-exit-scope-repair01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(name, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    with (ROOT / name).open("xb") as stream:
        stream.write(raw)


before_runner = (ROOT / "before/run_preflight02.ps1").read_bytes()
runner = (ROOT / "candidate/run_preflight03.ps1").read_bytes()
block = (ROOT / "candidate/NATIVE-RECEIPT-BLOCK.ps1.txt").read_bytes()
assert runner.split(b"# BEGIN EXACT NATIVE RECEIPT BLOCK\n", 1)[1].split(b"# END EXACT NATIVE RECEIPT BLOCK", 1)[0] == block
before_post = before_runner[before_runner.index(b"$taskAfter=@()"):]
post = runner[runner.index(b"$taskAfter=@()"):]
assert post == before_post
for name in ("wrapper-missing02.ps1", "wrapper-success02.ps1"):
    wrapped = (ROOT / "instrument02" / name).read_bytes()
    assert wrapped.split(b"# BEGIN EXACT NATIVE RECEIPT BLOCK\n", 1)[1].split(b"# END EXACT NATIVE RECEIPT BLOCK", 1)[0] == block
    assert wrapped[wrapped.index(b"$taskAfter=@()"):wrapped.rindex(b"\n}\nInvoke-InertWrapper\n")] == post
prior = BASE / "_scratch/asr-production-adapter-qualification-repair01"
subset = BASE / "_scratch/asr-production-adapter-instrument-check01"
for name in ("qualify_adapter.py", "asr_loading_adapter.py"):
    assert (ROOT / "candidate" / name).read_bytes() == (prior / name).read_bytes()
for name in ("qualify_guards.py", "child-one.py", "child-zero.py", "trap-installation.py.txt", "trap-final.py.txt"):
    assert (ROOT / "instrument02" / name).read_bytes() == (subset / name).read_bytes()
write("STATIC-VERIFICATION.json", {"candidate_and_two_wrapper_blocks_identical": True,
      "all_original_postchecks_identical": True, "harness_adapter_child_guard_bytes_unchanged": True,
      "new_native_block_sha256": sha(block), "new_postchecks_sha256": sha(post),
      "diagnostic_or_qualification_executed": False})
write("PREPARATION-TOOL-OUTCOMES.json", {
    "source_preparer": {"chunk_id": "e811be", "actual_exit": 0, "wall_time_seconds": 0.1192536},
    "powershell_syntax_only": {"chunk_id": "0f6fa2", "actual_exit": 0, "wall_time_seconds": 0.1035255,
                              "parse_errors": 0, "scripts_parsed": 4},
    "scope": "Source copying/hashing/derivation and static syntax only; no prepared source execution"})
failure_rows = []
for path in sorted((ROOT / "failure01").rglob("*")):
    if path.is_file():
        raw = path.read_bytes()
        failure_rows.append({"path": path.relative_to(ROOT / "failure01").as_posix(), "bytes": len(raw), "sha256": sha(raw)})
assert len(failure_rows) == 7
write("failure01/SHA256.json", {"schema": "uoink.asr-native-receipt-failed-outcome.v1", "date": "2026-09-13",
      "qualification_status": "FAILED", "measured_native_exit": None, "actual_outer_tool_exit": 1,
      "success_wrapper_and_guards_executed": False, "payload_count": len(failure_rows),
      "payload_bytes": sum(row["bytes"] for row in failure_rows), "files": failure_rows})
write("seal_asr_native_scope_repair01.py", Path(__file__).read_bytes())
rows = []
for path in sorted(ROOT.rglob("*")):
    if path.is_file() and "runs" not in path.relative_to(ROOT).parts:
        raw = path.read_bytes()
        rows.append({"path": path.relative_to(ROOT).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
assert not any(row["path"] == "SHA256.json" for row in rows)
write("SHA256.json", {"schema": "uoink.asr-native-scope-repair-preparation.v1", "date": "2026-09-13",
      "payload_count": len(rows), "payload_bytes": sum(row["bytes"] for row in rows),
      "planned_scope_observations": 4, "planned_repaired_wrapper_outcomes": 2, "planned_guard_cases": 4,
      "candidate_58_asr_cases_executed": False, "preparation_executed_diagnostics": False,
      "previous_qualification_status": "FAILED_NATIVE_CAPTURE", "files": rows})
print(json.dumps({"payload_count": len(rows), "payload_bytes": sum(row["bytes"] for row in rows),
                  "manifest_sha256": sha((ROOT / "SHA256.json").read_bytes()),
                  "failure_seal_sha256": sha((ROOT / "failure01/SHA256.json").read_bytes())}))

"""Verify documentary bytes and recorded outcomes only; runs no qualification."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent


def check(folder, seal_name="SHA256.json"):
    seal = json.loads((folder / seal_name).read_bytes())
    for row in seal["files"]:
        raw = (folder / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]
    return len(seal["files"])


count = check(ROOT)
assert check(ROOT / "preparation-repair01") == 53
assert check(ROOT / "preparation-repair01/original-proposal", "PREPARATION-SHA256.json") == 23
assert check(ROOT / "preparation-instrument01") == 26
assert check(ROOT / "preparation-scope01") == 55
assert check(ROOT / "preparation-scope01/failure01") == 7
failed = json.loads((ROOT / "preparation-scope01/failure01/missing01/native-exit.json").read_bytes())
assert failed["native_exit"] is None
missing = json.loads((ROOT / "subset02/runs/instrument02/missing02/native-exit.json").read_bytes())
assert type(missing["native_exit"]) is int and missing["native_exit"] == 1
success = json.loads((ROOT / "subset02/runs/instrument02/success02/exit.json").read_bytes())
assert success["native_exit"] == 0 and success["outer_exit"] == 0 and success["receipt_valid"] is True
guards = json.loads((ROOT / "subset02/guards-stdout.json").read_bytes())
assert guards["passed"] == 4 and guards["failed"] == 0 and guards["guard_valid"] is True
actual = json.loads((ROOT / "asr-author03/adapter-preflight03/stdout.json").read_bytes())
assert len(actual["cases"]) == len({r["name"] for r in actual["cases"]}) == 58
assert all(row["passed"] is True for row in actual["cases"])
assert actual["passed"] == 58 and actual["failed"] == 0 and actual["guard_valid"] is True
assert actual["real_resolver_approval_unchanged_none"] is True and actual["metadata_trap_count"] == 11
assert json.loads((ROOT / "asr-author03/ACTUAL-TOOL-PREFLIGHT03.json").read_bytes())["exit_code"] == 0
print(json.dumps({"payloads_verified": count, "nested_original_seals_verified": [53, 23, 26, 55, 7],
                  "old_failure_retained": True, "recorded_author_asr_cases": 58, "recorded_author_asr_passed": 58,
                  "recorded_author_asr_failed": 0, "verification_only": True, "qualifications_executed_by_this_verifier": 0}))

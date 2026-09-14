"""Passive comparison of two admitted generated-case observations; runs no payload."""
import hashlib
import json
import math
import os
from pathlib import Path

assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
ROOT = Path(__file__).absolute().parent.parent
SCRATCH = ROOT / "_scratch"
AUTHOR = SCRATCH / "runtime-owner-native-connection-proposal01"
INDEPENDENT = SCRATCH / "astra-runtime-owner-native-confirmation01"

def raw(path):
    value = path.read_bytes()
    assert len(value) <= 1048576, path.name
    return value

def sha(value):
    return hashlib.sha256(value).hexdigest()

def doc(path):
    return json.loads(raw(path).decode("utf-8-sig"))

expected_raw = raw(AUTHOR / "EXPECTED-CASES.json")
assert sha(expected_raw) == "2c1fadce72b41ed443fcbcd2be88758db9f1cb55e530c7a33010377c598d164e"
expected = json.loads(expected_raw)["ordered_cases"]
assert len(expected) == len(set(expected)) == 33
pins_raw = raw(AUTHOR / "PINS.json")
assert sha(pins_raw) == "43b1e2f210cf1766fa5a074aa29fe1950f361e420dbc3697efcafddbd5a1f02e"
pins = json.loads(pins_raw)
assert len(pins["files"]) == 95
for row in pins["files"]:
    name = row["path"]
    assert "\\" not in name and ":" not in name and ".." not in name.split("/")
    value = raw(AUTHOR / name)
    assert len(value) == row["bytes"] and sha(value) == row["sha256"], name

guards = (
    "metadata_traps_installed", "content_reads_closed",
    "baseline_winreg_identity_unchanged", "registry_namespace_unchanged",
    "registry_traps_installed", "captures_installed", "capture_valid",
    "methods_unchanged", "closed_entries_unchanged", "owner_binding_valid",
)
outcomes = []
payloads = []
for base, admission_hash, actual_name in (
    (AUTHOR, "2692534aef872cd61c65b8f2e535304c754e91475ad405200015543b92bdd769",
     "RUNTIME-OWNER-NATIVE-FAKE33-AUTHOR-ACTUAL.json"),
    (INDEPENDENT, "1d43141daaf63be421b9e2daf23fd96ead234df7800955b9a4efc6ecdc8b030e",
     "RUNTIME-OWNER-NATIVE-FAKE33-INDEPENDENT-ACTUAL.json"),
):
    run = base / "runs" / "owner-native-fake01"
    admission_raw = raw(base / "ROOT-ADMISSION.json")
    assert sha(admission_raw) == admission_hash
    admission = json.loads(admission_raw)
    assert admission["root_reviewed"] is True
    assert admission["scope"] == "runtime-owner-native-fake-33-only"
    assert admission["label"] == "owner-native-fake01" and admission["expected_cases"] == expected
    assert raw(run / "ROOT-ADMISSION.json") == admission_raw
    inputs = admission["input_sha256"]
    assert len(inputs) == 38
    plan = doc(run / "plan.json")
    assert plan["planned_cases"] == expected and plan["startup_binding_set"] is True
    assert plan["interpreter"] == r"C:\Python314\python.exe"
    assert plan["arguments"] == ["-I", "-S", "-B", "qualify_owner.py"]
    assert len(plan["inputs"]) == 38 and [r["name"] for r in plan["inputs"]] == list(inputs)
    after = doc(run / "after.json")
    assert [r["name"] for r in after] == list(inputs) + ["ROOT-ADMISSION.json"]
    for planned, row in zip(plan["inputs"], after[:-1], strict=True):
        name = planned["name"]
        assert "/" not in name and "\\" not in name and ":" not in name and name not in (".", "..")
        assert planned["source"] == str(base / name)
        original, copied = raw(base / name), raw(run / name)
        digest = sha(original)
        assert original == copied and digest == inputs[name] == planned["sha256"]
        assert row == {"name": name, "before_sha256": digest,
                       "copy_after_sha256": digest, "source_after_sha256": digest}
    assert after[-1] == {"name": "ROOT-ADMISSION.json", "before_sha256": admission_hash,
                         "copy_after_sha256": admission_hash, "source_after_sha256": admission_hash}
    stdout = raw(run / "stdout.json")
    result = json.loads(stdout.decode("utf-8-sig"))
    assert result["schema"] == "uoink.runtime-owner-native-fake.v1"
    assert result["cases"] == [{"name": name, "passed": True} for name in expected]
    assert result["expected_cases"] == expected and result["count"] == result["passed"] == 33
    assert result["failed"] == result["skipped"] == result["native_exit"] == 0
    assert type(result["elapsed_seconds"]) in (int, float)
    assert math.isfinite(result["elapsed_seconds"]) and 0 <= result["elapsed_seconds"] < 3600
    assert result["guard_valid"] is True and all(result[key] is True for key in guards)
    assert result["metadata_trap_count"] == 12 and result["registry_trap_count"] == 25
    assert len(result["registry_trap_names"]) == len(set(result["registry_trap_names"])) == 25
    assert all(result[key] == [] for key in ("guard_denials", "registry_denials", "heavy_roots_loaded"))
    assert result["stdout_capture"] == result["stderr_capture"] == "" and raw(run / "stderr.log") == b""
    child_names = set(inputs) - {"SOURCE-INPUTS.json", "run_fake33_01.ps1"}
    assert len(child_names) == 36 and set(result["input_sha256"]) == child_names
    assert all(result["input_sha256"][name] == inputs[name] for name in child_names)
    native = doc(run / "native-exit.json")
    assert native == {"schema": "uoink.native-exit.v1", "child_returned": True, "native_exit": 0}
    wrapper = doc(run / "exit.json")
    assert wrapper["native_exit"] == wrapper["outer_exit"] == wrapper["stderr_bytes"] == 0
    assert wrapper["stdout_bytes"] == len(stdout) and wrapper["receipt_parse_error_type"] is None
    assert all(wrapper[key] is True for key in ("inputs_unchanged", "receipt_valid", "startup_binding_set"))
    actual = doc(SCRATCH / actual_name)
    assert actual["schema"] == "uoink.actual-exec-session.v1"
    assert actual["tool_objects"][-1]["exit_code"] == 0
    assert all(row["output"] == "" for row in actual["tool_objects"])
    payloads.append(result)
    outcomes.append({"root": base.name, "passed": 33, "failed": 0, "skipped": 0,
                     "elapsed_seconds": result["elapsed_seconds"], "valid_guard_fields": len(guards),
                     "metadata_traps": 12, "registry_traps": 25, "unchanged_input_and_admission_pairs": 39,
                     "stdout_bytes": len(stdout), "stdout_sha256": sha(stdout),
                     "native_exit": 0, "outer_exit": 0})
assert payloads[0]["cases"] == payloads[1]["cases"]
assert payloads[0]["input_sha256"] == payloads[1]["input_sha256"]
assert payloads[0]["registry_trap_names"] == payloads[1]["registry_trap_names"]
print(json.dumps({"scope": "Passive existing text receipts; no subject rerun",
                  "frozen_author_files_matching": 95, "exact_case_objects_match": True,
                  "all_36_child_input_hashes_match": True, "observations": outcomes}, indent=2))

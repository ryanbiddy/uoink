"""Reconcile recorded test receipts and copy only the declared proof payloads."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from xml.etree import ElementTree as ET

root = Path(__file__).resolve().parents[1]
out = root / "_scratch/agw-proof"
out.mkdir(exist_ok=False)
proof = []


def copy(relative, target):
    source = root / relative
    destination = out / target
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


for relative in (
    "_scratch/ASSET-GUARD-A-BRIEF-2026-09-13.md",
    "_scratch/AGW-IMPORT-BOUNDARY-2026-09-13.md",
    "_scratch/ASSET-GUARD-A-RESULT-2026-09-13.md",
    "_scratch/extract_agw_tests.py", "_scratch/agw-test-extraction.json",
    "_scratch/agw_heavy_import_guard.py", "_scratch/run_agw_guarded.py",
    "_scratch/freeze_agw_proof.py",
):
    copy(relative, "instruments/" + Path(relative).name)
copy("whisper_runner.py", "source/whisper_runner.py")
copy("tests/test_whisper_cache_consent.py", "source/tests/test_whisper_cache_consent.py")
for label, expected in (("agw01", 11), ("agw02", 144)):
    launch = root / "_scratch" / (label + "-launch")
    result = json.loads((launch / "result.json").read_text(encoding="utf-8"))
    plan = json.loads((launch / "plan.json").read_text(encoding="utf-8"))
    assert result["exit"] == 0 and result["inputs_unchanged"]
    for path, value in plan["input_hashes"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == value
    verifier = json.loads((root / "_scratch" / label / "results.json").read_text(encoding="utf-8"))
    assert len(verifier) == 1 and verifier[0]["exit"] == 0
    junit = ET.fromstring((root / "_scratch" / label / "tests.xml").read_bytes()).find("testsuite")
    assert all(int(junit.attrib[key]) == 0 for key in ("errors", "failures", "skipped"))
    assert int(junit.attrib["tests"]) == expected + 13
    log = (root / "_scratch" / label / "tests.log").read_text(encoding="utf-8")
    assert re.search(r"\b" + str(expected) + r" passed\b", log)
    assert "13 subtests passed" in log
    guard = json.loads((launch / "heavy-import-guard.json").read_text(encoding="utf-8"))
    assert guard["already_loaded_at_startup"] == []
    assert guard["guard_installed_at_finish"] and guard["pytest_exitstatus"] == 0
    proof.append({"label": label, "passed": expected, "subtests_passed": 13,
                  "junit_entries": expected + 13, "failures": 0, "errors": 0, "skips": 0,
                  "blocked_import_attempts": guard["blocked_import_attempts"], "exit": 0})
    for name in ("results.json", "tests.xml", "tests.log", "guard/sitecustomize.py", "guard/ig_paths.py"):
        copy("_scratch/" + label + "/" + name, "runs/" + label + "/" + name)
    for name in ("plan.json", "result.json", "launcher.log", "heavy-import-guard.json"):
        copy("_scratch/" + label + "-launch/" + name, "runs/" + label + "-launch/" + name)

proposal = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\runtime-asset-guard-proposal01")
assert hashlib.sha256((proposal / "SHA256.json").read_bytes()).hexdigest() == "a32bb76d68d7939905b6538921f8915a0d78a47ab2e0c3f3c661c49036940237"
seal = json.loads((proposal / "SHA256.json").read_text(encoding="utf-8"))
for row in seal["payloads"]:
    assert hashlib.sha256((proposal / row["file"]).read_bytes()).hexdigest() == row["sha256"]
summary = {"base": "4067de31e0ab3f0d1c1377b60c8a3db1fa6c76ed", "runs": proof,
           "original_proposal_payloads_unchanged": len(seal["payloads"]),
           "existing_tests_changed": False, "native_model_credit": False,
           "frozen_utc": datetime.now(timezone.utc).isoformat()}
(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
payloads = [{"file": path.relative_to(out).as_posix(), "bytes": path.stat().st_size,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(out.rglob("*")) if path.is_file()]
(out / "SHA256.json").write_text(json.dumps({"payload_count": len(payloads), "payloads": payloads}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({**summary, "payload_count": len(payloads),
                  "manifest_sha256": hashlib.sha256((out / "SHA256.json").read_bytes()).hexdigest()}))

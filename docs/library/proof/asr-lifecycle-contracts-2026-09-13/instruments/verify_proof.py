"""Standalone documentary verifier; parses text, never executes copied code."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\lifecycle-combined-proof01")


def raw(name):
    with (ROOT / name).open("rb") as stream:
        data = stream.read(1048577)
    assert len(data) <= 1048576
    return data


def doc(name):
    return json.loads(raw(name))


seal = doc("SHA256-MANIFEST.json")
rows = seal["files"]
expected = {row["path"] for row in rows}
assert len(expected) == len(rows) == seal["count"]
assert sum(row["bytes"] for row in rows) == seal["bytes"]
actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file()}
assert actual == expected | {"SHA256-MANIFEST.json"}
for row in rows:
    name = row["path"]
    assert name and not name.startswith("/") and "\\" not in name and ":" not in name and ".." not in Path(name).parts
    assert not (ROOT / name).is_symlink()
    data = raw(name)
    assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"]
assert raw(".gitattributes") == b"* -text\n"

# The original failed run is retained verbatim, with no inferred case count.
failed = "author01/runs/lcs01/"
assert doc(failed + "native-exit.json")["native_exit"] == 1
assert doc(failed + "exit.json")["outer_exit"] == 1
assert doc(failed + "exit.json")["inputs_unchanged"] is True
assert doc(failed + "exit.json")["receipt_valid"] is False
assert raw(failed + "stdout.json") == b"" and len(raw(failed + "stderr.log")) == 361
assert b"AssertionError" in raw(failed + "stderr.log")
assert doc("author01/ACTUAL-TOOL-LCS01.json")["exit_code"] == 1
original_manifest = doc("author02/ORIGINAL-LCS01-SHA256.json")
for row in original_manifest:
    data = raw("author01/" + row["path"])
    assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"]

diagnostic = ast.literal_eval(raw("startup-diagnostic/root-diagnostic01/stdout.txt").decode("utf-8-sig"))
assert diagnostic["initial_heavy_roots"] == ["winreg"]
assert diagnostic["stages"] == diagnostic["attempted_heavy_imports"] == []
assert diagnostic["lifecycle_cases_executed"] == 0
assert doc("startup-diagnostic/root-diagnostic01/ACTUAL-OUTER-TOOL.json")["exit_code"] == 0

cases = doc("author02/EXPECTED-CASES.json")["ordered_cases"]
assert len(cases) == len(set(cases)) == 46
results = []
for group, actual_tool in (("author02", "ACTUAL-TOOL-LCS02.json"),
                           ("root-independent", "ACTUAL-QUALIFICATION-TOOL.json")):
    run = group + "/runs/lcs02/"
    result = doc(run + "stdout.json")
    assert [row["name"] for row in result["cases"]] == cases == result["expected_cases"]
    assert all(row["passed"] is True for row in result["cases"])
    assert (result["count"], result["passed"], result["failed"], result["skipped"]) == (46, 46, 0, 0)
    assert 0 <= result["elapsed_seconds"] < 3600
    for field in ("guard_valid", "metadata_traps_installed", "content_reads_closed", "captures_installed", "capture_valid",
                  "baseline_winreg_identity_unchanged", "registry_namespace_unchanged", "registry_traps_installed"):
        assert result[field] is True
    assert result["metadata_trap_count"] == 12 and result["registry_trap_count"] == 25
    assert len(result["registry_trap_names"]) == len(set(result["registry_trap_names"])) == 25
    assert result["registry_denials"] == result["guard_denials"] == result["heavy_roots_loaded"] == []
    assert result["stdout_capture"] == result["stderr_capture"] == ""
    assert result["native_exit"] == doc(run + "native-exit.json")["native_exit"] == 0
    exit_receipt = doc(run + "exit.json")
    assert exit_receipt["native_exit"] == exit_receipt["outer_exit"] == 0
    assert exit_receipt["inputs_unchanged"] is exit_receipt["receipt_valid"] is True
    assert raw(run + "stderr.log") == b""
    assert doc(group + "/" + actual_tool)["exit_code"] == 0
    for row in doc(run + "after.json"):
        assert row["before_sha256"] == row["copy_after_sha256"] == row["source_after_sha256"]
        assert hashlib.sha256(raw(run + row["name"])).hexdigest() == row["copy_after_sha256"]
    results.append(result)
assert results[0]["cases"] == results[1]["cases"]
assert results[0]["registry_trap_names"] == results[1]["registry_trap_names"]
for name in ("snapshot_lifecycle.py", "qualify_lifecycle.py", "EXPECTED-CASES.json"):
    assert raw("author02/" + name) == raw("root-independent/" + name)
author_path = b"E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\asr-windows-lifecycle-proposal02"
root_path = b"E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\astra-asr-lifecycle-qualification02"
author_launcher = raw("author02/run_lifecycle02.ps1")
assert author_launcher.count(author_path) == 1
assert author_launcher.replace(author_path, root_path) == raw("root-independent/run_lifecycle02.ps1")
for row in doc("root-independent/ROOT-COPY-BINDINGS.json")["files"]:
    assert hashlib.sha256(raw("author02/" + row["name"])).hexdigest() == row["author_sha256"]
    assert hashlib.sha256(raw("root-independent/" + row["name"])).hexdigest() == row["root_sha256"]
assert doc("root-independent/ACTUAL-PREPARE-TOOL.json")["exit_code"] == 0
print(json.dumps({"verified_payloads": len(rows), "bytes": seal["bytes"],
                  "same_46_cases_passed_in_two_roots": True, "failed_startup_preserved": True,
                  "diagnostic_cases": 0, "tests_executed_by_verifier": 0,
                  "manifest_sha256": hashlib.sha256(raw("SHA256-MANIFEST.json")).hexdigest()}, indent=2))

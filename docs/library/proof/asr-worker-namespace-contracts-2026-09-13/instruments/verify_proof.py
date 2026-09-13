"""Verify documentary hashes/receipts only; never compile archived source."""
from pathlib import Path
import hashlib
import json

OUT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\namespace-combined-proof01")
ORIGINAL_SEAL = "412ff1c34376f0ce156c055e27afc66e9d19ed3ed7358f939e7f8df1b526f02f"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    with path.open("rb") as stream:
        raw = stream.read(1048577)
    assert len(raw) <= 1048576
    return raw


def safe_relative(name):
    path = Path(name)
    assert not path.is_absolute() and ".." not in path.parts and path.parts
    return path


manifest_raw = read(OUT / "MANIFEST.json")
manifest = json.loads(manifest_raw)
assert manifest["payload_count"] == len(manifest["files"]) == 65
actual = {path.relative_to(OUT).as_posix() for path in OUT.rglob("*") if path.is_file()}
assert actual == {item["path"] for item in manifest["files"]} | {"MANIFEST.json"}
assert len({item["path"] for item in manifest["files"]}) == 65
total = 0
for item in manifest["files"]:
    raw = read(OUT / safe_relative(item["path"]))
    assert len(raw) == item["bytes"] and digest(raw) == item["sha256"]
    total += len(raw)
assert total == manifest["payload_bytes"]
assert read(OUT / ".gitattributes") == b"* -text\n"
mapping = json.loads(read(OUT / "LOGICAL-MEMBERS.json"))
assert mapping["logical_count"] == len(mapping["files"]) == 87
index = {item["path"]: item for item in mapping["files"]}
assert len(index) == 87
for item in index.values():
    assert len(item["sha256"]) == 64 and all(char in "0123456789abcdef" for char in item["sha256"])
    assert item["object"] == "objects/" + item["sha256"]
    raw = read(OUT / item["object"])
    assert len(raw) == item["bytes"] and digest(raw) == item["sha256"]
assert {item["object"] for item in index.values()} == {name for name in actual if name.startswith("objects/")}


def member(name):
    return read(OUT / index[name]["object"])


def record(name):
    return json.loads(member(name))


original_raw = member("preparation/MANIFEST.json")
assert digest(original_raw) == ORIGINAL_SEAL
original = json.loads(original_raw)
assert original["payload_count"] == len(original["files"]) == 37
for item in original["files"]:
    raw = member("preparation/" + item["path"])
    assert len(raw) == item["bytes"] and digest(raw) == item["sha256"]
author, root = record("author-run/stdout.json"), record("root-run/stdout.json")
assert author["cases"] == root["cases"]
for prefix, result, tool_name in (("author-run", author, "author-run/ACTUAL-OUTER-TOOL.json"),
                                  ("root-run", root, "root-inputs/ACTUAL-OUTER-TOOL.json")):
    admission = record(prefix + "/ROOT-ADMISSION.json")
    expected = record(prefix + "/EXPECTED-CASES.json")["ordered_cases"]
    assert result["schema"] == "uoink.worker-namespace-synthetic.v1"
    assert result["count"] == result["passed"] == len(result["cases"]) == len(expected) == 54
    assert result["failed"] == result["skipped"] == 0
    assert [item["name"] for item in result["cases"]] == expected == result["expected_cases"] == admission["expected_cases"]
    assert all(item["passed"] is True for item in result["cases"])
    assert result["metadata_trap_count"] == 12 and result["registry_trap_count"] == 25
    for key in ("guard_valid", "metadata_traps_installed", "content_reads_closed", "baseline_winreg_identity_unchanged",
                "registry_namespace_unchanged", "registry_traps_installed", "captures_installed", "capture_valid"):
        assert result[key] is True
    for key in ("guard_denials", "registry_denials", "heavy_roots_loaded"):
        assert result[key] == []
    assert result["stdout_capture"] == result["stderr_capture"] == "" and member(prefix + "/stderr.log") == b""
    assert 0 <= result["elapsed_seconds"] < 3600
    status = record(prefix + "/exit.json")
    assert status["native_exit"] == status["outer_exit"] == result["native_exit"] == 0
    assert status["inputs_unchanged"] is status["receipt_valid"] is True
    native = record(prefix + "/native-exit.json")
    assert native["child_returned"] is True and type(native["native_exit"]) is int and native["native_exit"] == 0
    assert record(tool_name)["exit_code"] == 0
    assert len(admission["input_sha256"]) == len(record(prefix + "/after.json")) == 9
    for name, expected_sha in admission["input_sha256"].items():
        assert digest(member(prefix + "/" + name)) == expected_sha
    for row in record(prefix + "/after.json"):
        assert row["before_sha256"] == row["source_after_sha256"] == row["copy_after_sha256"] == admission["input_sha256"][row["name"]]
    for name, expected_sha in result["input_sha256"].items():
        assert digest(member(prefix + "/" + name)) == expected_sha
bindings = record("root-inputs/ROOT-COPY-BINDINGS.json")
assert bindings["author_preparation_manifest_sha256"] == ORIGINAL_SEAL and len(bindings["files"]) == 9
for row in bindings["files"]:
    old = member("preparation/" + row["name"])
    new = member("root-inputs/" + row["name"])
    assert digest(old) == row["author_sha256"] and digest(new) == row["root_sha256"]
    if row["name"] == "run_namespace01.ps1":
        old_path = b"E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\asr-worker-namespace-proposal01"
        new_path = b"E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\astra-worker-namespace-qualification01"
        assert old.count(old_path) == 1 and old.replace(old_path, new_path) == new
    else:
        assert old == new
assert record("root-copy/ACTUAL-PREPARE-TOOL.json")["exit_code"] == 0
print(json.dumps({"verified": True, "payload_count": 65, "logical_members": 87,
                  "distinct_cases": 54, "independent_passed_runs": 2, "tests_executed_by_verifier": 0,
                  "manifest_sha256": digest(manifest_raw)}))

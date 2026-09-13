"""Archive existing evidence and verify byte identities without executing it."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
scratch = out.parent
original = scratch / "companion-b-static-qualification01"
independent = scratch / "astra-companion-b01"
preparer = scratch / "prepare_companion_b_astra01.py"
original_seal = "28d2d34c530e80716964b475244551340222dc7b8b2f39f77b8be9c490117fc5"
nested_seal = "a32bb76d68d7939905b6538921f8915a0d78a47ab2e0c3f3c661c49036940237"
sha = lambda data: hashlib.sha256(data).hexdigest()
assert not (out / "SHA256.json").exists(), "Never replace a completed seal"

def verify_seal(root, expected_hash, expected_count):
    raw = (root / "SHA256.json").read_bytes()
    assert sha(raw) == expected_hash
    manifest = json.loads(raw)
    assert manifest["payload_count"] == len(manifest["payloads"]) == expected_count
    for row in manifest["payloads"]:
        path = root / row["file"]
        assert path.resolve().is_relative_to(root.resolve()) and not path.is_symlink()
        payload = path.read_bytes()
        assert len(payload) == row["bytes"] and sha(payload) == row["sha256"]
    return manifest

verified = verify_seal(original, original_seal, 46)
verify_seal(original / "original-proposal01", nested_seal, 24)
root_review = json.loads((independent / "ROOT-REVIEW.json").read_bytes())
assert len(root_review["source_inputs"]) == 8
for name, binding in root_review["source_inputs"].items():
    data = (independent / name).read_bytes()
    assert len(data) == binding["bytes"] and sha(data) == binding["sha256"]
    assert data == (original / name).read_bytes()

candidate = json.loads((original / "runs/candidate01/result.json").read_bytes())
root_result = json.loads((independent / "runs/candidate01/result.json").read_bytes())
root_launch = json.loads((independent / "launch-candidate01/result.json").read_bytes())
root_plan = json.loads((independent / "launch-candidate01/plan.json").read_bytes())
assert [row["id"] for row in candidate["observations"]] == [row["id"] for row in root_result["observations"]]
for receipt in (candidate, root_result):
    assert (receipt["tests_run"], receipt["passed"], receipt["failed"], receipt["errors"], receipt["skipped"], receipt["exit"]) == (6, 6, 0, 0, 0, 0)
    assert receipt["source_sha256"] == "e500e12b0a58420ce5f41b202ba7d942b901a9b99c617d6ca3d3304b9493f269"
    assert receipt["test_protocol_sha256"] == "01e8d20863ca74aa855ac86b3a1609bf7212addc15032705e990b50a25064d04"
    assert receipt["guard"] == {"preloaded_heavy": [], "postloaded_heavy": [], "blocked_imports": [],
        "blocked_audit_events": [], "finder_installed_at_finish": True, "valid": True}
    assert not receipt["whole_dependency_module_executed"] and not receipt["real_tokenizer_or_model_executed"]
assert root_launch["exit"] == 0 and root_launch["inputs_unchanged"]
for path, expected_hash in root_plan["input_hashes"].items():
    actual = Path(path)
    assert actual.resolve().is_relative_to(independent.resolve())
    assert sha(actual.read_bytes()) == expected_hash

copies = []
def copy_bytes(source, destination):
    assert not source.is_symlink()
    assert destination.resolve().is_relative_to(out.resolve())
    assert not destination.exists()
    data = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    assert destination.read_bytes() == data
    copies.append({"source": str(source), "file": destination.relative_to(out).as_posix(),
                   "bytes": len(data), "sha256": sha(data)})

for source_root, target_name in ((original, "original-qualification01"), (independent, "independent-root01")):
    for path in sorted(source_root.rglob("*")):
        assert not path.is_symlink()
        if path.is_file():
            copy_bytes(path, out / target_name / path.relative_to(source_root))
copy_bytes(preparer, out / "root-preparation" / preparer.name)
assert sum(row["file"].startswith("original-qualification01/") for row in copies) == 47
assert sum(row["file"].startswith("independent-root01/") for row in copies) == 14
verify_seal(out / "original-qualification01", original_seal, 46)
verify_seal(out / "original-qualification01/original-proposal01", nested_seal, 24)
verify_seal(original, original_seal, 46)
for row in copies:
    assert sha(Path(row["source"]).read_bytes()) == row["sha256"]
    assert sha((out / row["file"]).read_bytes()) == row["sha256"]
assert (out / ".gitattributes").read_bytes() == b"* -text\n"

receipt = {"assembled_utc": datetime.now(timezone.utc).isoformat(),
    "original_46_payload_manifest_sha256": original_seal,
    "nested_24_payload_manifest_sha256": nested_seal,
    "original_and_copy_seals_verified": True,
    "all_source_bytes_unchanged_after_copy": True,
    "independent_exact_bound_inputs": 8,
    "copied_files": len(copies), "copies": copies,
    "candidate_counts_each": {"cases": 6, "passed": 6, "failed": 0, "errors": 0, "skipped": 0, "exit": 0},
    "candidate_case_ids_identical": True,
    "root_launcher_input_hashes_unchanged": True,
    "new_tests_or_dependency_execution_performed": False,
    "root_acceptance_scope": "Exact selected-source proposal accepted for further derivative planning only.",
}
(out / "copy-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
payloads = []
for path in sorted(out.rglob("*")):
    if path.is_file():
        data = path.read_bytes()
        payloads.append({"file": path.relative_to(out).as_posix(), "bytes": len(data), "sha256": sha(data)})
manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "payload_count": len(payloads), "payloads": payloads}
(out / "SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"payload_count": len(payloads), "manifest_sha256": sha((out / "SHA256.json").read_bytes()),
                  "copied_files": len(copies), "original46_and_nested24_preserved": True,
                  "independent_candidate_passed": 6, "new_test_execution": False}))

"""Copy and reconcile named asset-guard evidence; never execute captured code."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET


def deny(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
        raise RuntimeError("proof materialization forbids network and child processes")


sys.addaudithook(deny)
root = Path(__file__).resolve().parents[1]
worker = Path(r"E:\AI\projects\uoink\worktrees\asset-guard-a")
out = root / "docs/library/proof/asset-guard-a-2026-09-13"
assert not out.exists()
out.mkdir(parents=True)
bindings = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def destination(relative):
    path = out / relative
    assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
    assert path.resolve().is_relative_to(out.resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), relative
    return path


def copy(source, relative):
    data = source.read_bytes()
    target = destination(relative)
    target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    assert sha(target) == digest
    bindings.append({"source": str(source), "saved_file": relative,
                     "bytes": len(data), "sha256": digest})


def sealed_child(source, relative, expected_hash, expected_count):
    manifest = source / "SHA256.json"
    assert sha(manifest) == expected_hash
    records = json.loads(manifest.read_text(encoding="utf-8"))
    assert records["payload_count"] == expected_count == len(records["payloads"])
    expected_files = {row["file"] for row in records["payloads"]} | {"SHA256.json"}
    actual_files = {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()}
    assert actual_files == expected_files
    for row in records["payloads"]:
        path = source / row["file"]
        assert path.resolve().is_relative_to(source.resolve())
        assert path.stat().st_size == row["bytes"] and sha(path) == row["sha256"]
        copy(path, relative + "/" + row["file"])
    copy(manifest, relative + "/SHA256.json")
    assert sha(out / relative / "SHA256.json") == expected_hash


sealed_child(root / "_scratch/runtime-asset-guard-proposal01", "original-proposal01",
             "a32bb76d68d7939905b6538921f8915a0d78a47ab2e0c3f3c661c49036940237", 24)
sealed_child(worker / "_scratch/agw-proof", "original-worker-proof",
             "d314a63292d7bc0092c2fc715aeafc6fe65c21de418939f3f4c8b2bf800ee56f", 29)
for name in ("AGW-COUNT-CLARIFICATION-2026-09-13.md", "agw-count-clarification.json", "clarify_agw_counts.py"):
    copy(worker / "_scratch" / name, "count-clarification/" + name)
for name in (
    "ASSET-GUARD-A-PROOF-BRIEF-2026-09-13.md",
    "ASSET-GUARD-A-INTEGRATOR-REVIEW-2026-09-13.md",
    "run_asset_guard_independent.py", "integrate_asset_guard_a.py",
    "integrator_verify.py", "agw_heavy_import_guard.py", "materialize_asset_guard_a_proof.py",
):
    copy(root / "_scratch" / name, "instruments/" + name)
copy(root / "docs/library/ASTRA-ASSET-GUARD-A-VERDICT-2026-09-13.md", "VERDICT.md")
for name in ("apply.log", "check.log", "receipt.json", "worker.patch"):
    copy(root / "_scratch/asset-guard-a-integration01" / name, "integration01/" + name)
integration = json.loads((out / "integration01/receipt.json").read_text(encoding="utf-8"))
assert integration["normalized_equality"] and not integration["existing_test_changes"]
assert sha(out / "integration01/worker.patch") == integration["patch_sha256"]

selectors = [
    "tests/test_whisper_cache_consent.py", "tests/test_phase6_evaluation.py",
    "tests/test_podcast_background_jobs.py", "tests/test_podcast_watch.py",
    "tests/test_podcast_workflow_truth.py", "tests/test_library_adapters.py",
    "tests/test_packaged_decoder_loader.py", "tests/test_installer_dependency_lock.py",
]
runs = []
memberships = {}
for label, run_root, role in (("agv01", worker, "worker"), ("agc01", root, "checkout")):
    launch = root / "_scratch" / (label + "-launch")
    raw = run_root / "_scratch" / label
    for name in ("plan.json", "result.json", "launcher.log", "heavy-import-guard.json"):
        copy(launch / name, "parent-launches/" + label + "-launch/" + name)
    for name in ("results.json", "tests.log", "tests.xml", "guard/sitecustomize.py", "guard/ig_paths.py"):
        copy(raw / name, "independent-runs/" + label + "/" + name)
    plan = json.loads((launch / "plan.json").read_text(encoding="utf-8"))
    result = json.loads((launch / "result.json").read_text(encoding="utf-8"))
    verifier = json.loads((raw / "results.json").read_text(encoding="utf-8"))
    guard = json.loads((launch / "heavy-import-guard.json").read_text(encoding="utf-8"))
    assert result["verifier_exit"] == 0 and result["inputs_unchanged"] and result["guard_valid"]
    assert len(verifier) == 1 and verifier[0]["exit"] == 0
    assert "--runxfail" in plan["command"] and "--runxfail" in verifier[0]["command"]
    assert [value for value in plan["command"] if value in selectors] == selectors
    assert guard["already_loaded_at_startup"] == [] and guard["guard_installed_at_finish"]
    assert guard["pytest_exitstatus"] == 0 and guard["blocked_import_attempts"] == ["whisperx", "whisperx"]
    for input_path, digest in plan["inputs"].items():
        path = Path(input_path)
        assert sha(path) == digest, str(path)
        if path.is_relative_to(run_root):
            relative = path.relative_to(run_root).as_posix()
        else:
            assert path == root / "_scratch/run_asset_guard_independent.py"
            relative = "external-integrator/run_asset_guard_independent.py"
        copy(path, "qualification-inputs/" + role + "/" + relative)
    xml = ET.fromstring((raw / "tests.xml").read_bytes())
    suite = xml.find("testsuite")
    cases = suite.findall("testcase")
    assert len(cases) == 144 and int(suite.attrib["tests"]) == 157
    assert all(int(suite.attrib[key]) == 0 for key in ("failures", "errors", "skipped"))
    assert all(not case.findall("failure") and not case.findall("error") and not case.findall("skipped") for case in cases)
    ids = [(case.attrib.get("classname", ""), case.attrib["name"]) for case in cases]
    assert len(set(ids)) == 144
    memberships[role] = ids
    console = (raw / "tests.log").read_text(encoding="utf-8")
    matches = re.findall(r"144 passed, 30 warnings, 13 subtests passed in ([0-9.]+)s", console)
    assert len(matches) == 1
    runs.append({
        "label": label, "root": str(run_root), "top_level_passed_cases": 144,
        "passed_subtests": 13, "junit_tests_attribute": 157, "junit_testcase_elements": 144,
        "failures": 0, "errors": 0, "skipped": 0, "warnings": 30,
        "pytest_seconds": float(matches[0]), "pytest_exit": 0, "verifier_exit": 0,
        "runxfail": True, "inputs_unchanged": True, "guard": guard,
    })
assert memberships["worker"] == memberships["checkout"]

cross_root = []
for relative in ["whisper_runner.py", *selectors]:
    a, b = (worker / relative).read_bytes(), (root / relative).read_bytes()
    assert a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n"), relative
    cross_root.append({"file": relative, "worker_sha256": hashlib.sha256(a).hexdigest(),
                       "checkout_sha256": hashlib.sha256(b).hexdigest(),
                       "raw_bytes_equal": a == b, "lf_normalized_bytes_equal": True})
for relative in ("whisper_runner.py", "tests/test_whisper_cache_consent.py"):
    copy(root / relative, "final-source/" + relative)
assert sha(root / "whisper_runner.py") == "6586d9f19fea0d20054d6e317b48b9914904e1126bbc7b788ba255633251996f"
assert sha(root / "tests/test_whisper_cache_consent.py") == "2595fee1b281d77856918ddfd1fb8ef17e432313b6e1ea1e73c44db3d63f9ea3"

summary = {
    "verdict": "PASS_ORDINARY_CACHE_GUARD_SELECTED_SUITES_ONLY",
    "checkout_base": "0cedaa68fde378546d0389fcc2bf47099e84346e",
    "worker_base": "4067de31e0ab3f0d1c1377b60c8a3db1fa6c76ed",
    "runs": runs, "identical_ordered_case_ids_across_roots": True,
    "unique_case_ids_per_root": 144, "cross_root_inputs": cross_root,
    "original_proposal_payloads_preserved": 24, "original_worker_proof_payloads_preserved": 29,
    "count_clarification_separate": True, "full_tree_run": False,
    "native_model_installed_release_credit": False,
    "open_scope": ["trusted immutable artifact manifest", "faster-whisper companion derivative",
                   "unrestricted default PyAnnote VAD", "model-stack qualification"],
    "source_or_tests_edited_by_materializer": False,
    "new_network_or_test_execution": False,
    "sealed_utc": datetime.now(timezone.utc).isoformat(),
}
for name, data in (("summary.json", summary), ("case-membership.json", memberships), ("source-bindings.json", bindings)):
    destination(name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
for row in bindings:
    assert sha(Path(row["source"])) == row["sha256"], row["source"]
payloads = [{"file": path.relative_to(out).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}
            for path in sorted(out.rglob("*")) if path.is_file()]
manifest = destination("SHA256.json")
manifest.write_text(json.dumps({"payload_count": len(payloads), "payloads": payloads}, indent=2) + "\n", encoding="utf-8", newline="\n")
for row in payloads:
    assert sha(out / row["file"]) == row["sha256"]
print(json.dumps({"payload_count": len(payloads), "manifest_sha256": sha(manifest),
                  "matching_case_ids": 144, "each_run_passed_cases": 144,
                  "each_run_passed_subtests": 13, "each_xml_tests_attribute": 157,
                  "source_bindings_verified": len(bindings), "hash_mismatches": 0}))

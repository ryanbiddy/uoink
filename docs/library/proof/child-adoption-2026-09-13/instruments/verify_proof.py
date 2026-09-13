"""Verify saved documentary bytes and outcomes; no archived-code execution."""
from pathlib import Path
import hashlib
import json

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
OUT = BASE / "child-adoption-proof01"
INVENTORY_SHA = "9f33499b1c143f79cb6e85009c266d80fe3d9a87ea44f8bf283025da6fe8a44c"
SOURCE_SHA = {
    "snapshot_lifecycle.py": "a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd",
    "win32_worker_connection.py": "b39a29cea1f3d60e4416111fd87417b21458b1f6f23dcb7700d522050b0b0b45",
    "win32_private_pipe.py": "73a1109a55f2bc807594655c71b24a3e35eb88d7f744497df2cc328dc224cae7",
    "pinned_buffer_namespace.py": "2cc25a7a254f35d802336ef121cc860887a4301b3257588438dddec392fe0b7b",
    "owned_generation_protocol.py": "437e0880e10c91555df61b3c07c8be665430098c54c7d6ef687a99a0aa4a79d9",
    "inherited_readset.py": "02be8e04f4bea3030faf0882ae48ead40716c5782f95e2790e1a9897c5be76e3",
    "generated_worker_flow.py": "4409fb6bf169eda28beb66020066bb7ca1ee5927f51cadfcb9f57ba84c26bcee",
    "dummy_bootstrap.py": "83850d5426ae75a3b16ed5503a536a2202f541cb002929fa0dd52ef0c9cdfa06",
}
OWN_SOURCES = ("owned_generation_protocol.py", "inherited_readset.py", "generated_worker_flow.py", "dummy_bootstrap.py")
FIXTURE_NAMES = ("config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json")
MAP_SHA = "3869412b8ca34f865a58cef2407473a64c90176c9719b2695c4c398027624221"
LAUNCH_SHA = "0bb77f068bdc1273abd0423ffb76904f919a0d6edb7f136871b35cee812bf10f"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    assert path.is_file() and not path.is_symlink()
    with path.open("rb") as stream:
        raw = stream.read(1048577)
    assert len(raw) <= 1048576
    return raw


def relative(name):
    assert type(name) is str and name and ":" not in name and "\\" not in name
    parts = name.split("/")
    assert all(part not in ("", ".", "..") for part in parts)
    return Path(*parts)


manifest_raw = read(OUT / "MANIFEST.json")
manifest = json.loads(manifest_raw)
assert manifest["schema"] == "uoink.proof-seal.v1"
assert manifest["payload_count"] == len(manifest["files"]) == 79
assert len({row["path"] for row in manifest["files"]}) == 79
actual = {p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file()}
assert actual == {row["path"] for row in manifest["files"]} | {"MANIFEST.json"}
total = 0
for row in manifest["files"]:
    raw = read(OUT / relative(row["path"]))
    assert len(raw) == row["bytes"] and digest(raw) == row["sha256"]
    total += len(raw)
assert total == manifest["payload_bytes"] and read(OUT / ".gitattributes") == b"* -text\n"
mapping = json.loads(read(OUT / "SOURCE-TREE.json"))
assert mapping["logical_count"] == len(mapping["files"]) == 103
index = {row["path"]: row for row in mapping["files"]}
assert len(index) == 103
for row in index.values():
    relative(row["path"])
    assert len(row["sha256"]) == 64 and all(c in "0123456789abcdef" for c in row["sha256"])
    assert row["object"] == "objects/" + row["sha256"] + ".txt"
    raw = read(OUT / row["object"])
    assert len(raw) == row["bytes"] and digest(raw) == row["sha256"]
assert {row["object"] for row in index.values()} == {name for name in actual if name.startswith("objects/")}
inventory_raw = read(OUT / "instruments/SOURCE-MEMBERS.json")
assert digest(inventory_raw) == INVENTORY_SHA
inventory = json.loads(inventory_raw)
assert inventory["logical_count"] == len(inventory["files"]) == 103
assert len({row["logical_path"] for row in inventory["files"]}) == 103
assert inventory["logical_bytes"] == sum(row["bytes"] for row in index.values()) == 838755
assert inventory["distinct_objects"] == len({row["sha256"] for row in index.values()}) == 70
for row in inventory["files"]:
    mapped = index[row["logical_path"]]
    assert (mapped["bytes"], mapped["sha256"]) == (row["bytes"], row["sha256"])
copy_receipt = json.loads(read(OUT / "COPY-VERIFICATION.json"))
assert copy_receipt == {"schema": "uoink.documentary-copy-verification.v1",
    "physical_payloads_checked": 78, "logical_members": 103, "distinct_objects": 70,
    "logical_bytes": 838755, "exact_file_set": True, "exact_copy_bytes": True,
    "source_inventory_sha256": INVENTORY_SHA, "tests_or_native_runs_executed": 0}


def member(name):
    return read(OUT / index[name]["object"])


def record(name):
    return json.loads(member(name))


# Preserve exact preparation manifests and their complete original payloads.
for number, count, seal in (
    ("01", 30, "4389b252a8ef40f9fa80421f586aabd9c5273ded8e383b6a077e72a89ff775a0"),
    ("02", 18, "52a5804d3f48325562795e74faf15d226eed269bdc6e31d6160c9ca3c885b320")):
    folder = "child-readset-adoption-proposal" + number
    raw = member(folder + "/PREPARATION-MANIFEST.json")
    assert digest(raw) == seal
    prior = json.loads(raw)
    assert prior["payload_count"] == len(prior["files"]) == count
    assert len({row["path"] for row in prior["files"]}) == count
    for row in prior["files"]:
        relative(row["path"])
        raw = member(folder + "/" + row["path"])
        assert len(raw) == row["bytes"] and digest(raw) == row["sha256"]
    assert sum(row["bytes"] for row in prior["files"]) == prior["payload_bytes"]
    expected = {folder + "/" + row["path"] for row in prior["files"]} | {folder + "/PREPARATION-MANIFEST.json"}
    if number == "02":
        expected |= {folder + "/ROOT-ADMISSION-positive.json", folder + "/ROOT-ADMISSION-wrong_identity.json"}
    assert {name for name in index if name.startswith(folder + "/")} == expected
assert member("child-readset-adoption-proposal01/PREPARATION-MANIFEST.json") == member("child-readset-adoption-proposal02/PRIOR-PREPARATION-MANIFEST.json")
revision = record("child-readset-adoption-proposal02/REVISION-BINDINGS.json")
assert revision["changed_behavior_assertions"] == revision["candidate_executions"] == 0
assert revision["source_only"] is True and revision["prior_seal_verified_payloads"] == 30
assert revision["source_inputs_sha256"] == MAP_SHA and revision["launcher_sha256"] == LAUNCH_SHA
assert revision["selected_pipe"]["sha256"] == SOURCE_SHA["win32_private_pipe.py"]
assert {row["name"] for row in revision["copied_candidate_sources"]} == set(OWN_SOURCES)
for row in revision["copied_candidate_sources"]:
    name = row["name"]
    assert row["before_sha256"] == row["after_sha256"] == SOURCE_SHA[name]
    assert member("child-readset-adoption-proposal01/" + name) == member("child-readset-adoption-proposal02/" + name)

fixtures = {name: ("Uoink generated adoption fixture: " + name + ". No model data.\n").encode("ascii") for name in FIXTURE_NAMES}
fixture_rows = [{"name": name, "bytes": len(raw), "sha256": digest(raw)} for name, raw in fixtures.items()]
assert sum(row["bytes"] for row in fixture_rows) == 328
namespace = digest(json.dumps([[row["name"], row["bytes"], row["sha256"]] for row in fixture_rows], separators=(",", ":")).encode("ascii"))
assert namespace == "f02e5966f784ea254e583514171277975c5c7dbd9dfcccad9fd5a62976cf31b9"
readback = {"namespace_sha256": namespace, "payload_bytes": 328, "members": fixture_rows}
summaries = []
for case, run, actual_label, chunk, expected_child, counts in (
    ("positive", "child-readset-positive01", "POSITIVE01", "4e8051", 0, (245, 210)),
    ("wrong_identity", "child-readset-wrong-identity01", "NEGATIVE01", "2abf39", 2, (225, 109))):
    proposal = "child-readset-adoption-proposal02"
    status, native = record(run + "/exit.json"), record(run + "/native-exit.json")
    tool = record("CHILD-ADOPTION-" + actual_label + "-ACTUAL.json")
    assert tool["chunk_id"] == chunk and tool["output"] == ""
    assert type(native["native_exit"]) is int and native["child_returned"] is True
    assert native["native_exit"] == status["controller_native_exit"] == status["outer_exit"] == tool["exit_code"] == 0
    assert status["case"] == case and status["expected_child_native_exit"] == expected_child
    assert status["inputs_unchanged"] is status["receipt_valid"] is True and status["receipt_error_type"] is None
    assert member(run + "/controller-stdout.log") == member(run + "/controller-stderr.log") == b""
    assert status["stdout_bytes"] == status["stderr_bytes"] == 0
    admission, source_map = record(run + "/ROOT-ADMISSION.json"), record(run + "/SOURCE-INPUTS.json")
    assert admission["root_reviewed"] is True and admission["scope"] == "five-generated-inherited-files-only"
    assert admission["case"] == case and admission["run_path"] == str(BASE / run)
    assert admission["expected_controller_native_exit"] == 0 and admission["expected_child_native_exit"] == expected_child
    assert admission["source_inputs_sha256"] == digest(member(run + "/SOURCE-INPUTS.json")) == MAP_SHA
    assert admission["launcher_sha256"] == digest(member(run + "/run_adoption01.ps1")) == LAUNCH_SHA
    assert member(run + "/ROOT-ADMISSION.json") == member(proposal + "/ROOT-ADMISSION-" + case + ".json")
    admission_actual = record("CHILD-ADOPTION-" + actual_label + "-ADMISSION-ACTUAL.json")
    assert admission_actual["exit_code"] == 0
    assert json.loads(admission_actual["output"])["Hash"].lower() == digest(member(run + "/ROOT-ADMISSION.json"))
    assert source_map["source_sha256"] == SOURCE_SHA and set(source_map["source_paths"]) == set(SOURCE_SHA)
    before, after = record(run + "/before.json"), record(run + "/after.json")
    assert before["case"] == case and after["inputs_unchanged"] is True
    assert len(before["sources"]) == 8 and {row["name"] for row in before["sources"]} == set(SOURCE_SHA)
    assert len(before["controls"]) == 3 and {row["name"] for row in before["controls"]} == {"ROOT-ADMISSION.json", "SOURCE-INPUTS.json", "run_adoption01.ps1"}
    later = {row["name"]: row for row in after["source_and_controls"]}
    assert len(later) == len(after["source_and_controls"]) == 11
    for row in before["sources"] + before["controls"]:
        name, sha = row["name"], row["sha256"]
        assert digest(member(run + "/" + name)) == sha
        assert all(later[name][key] == sha for key in ("before_sha256", "copy_after_sha256", "source_after_sha256"))
        if name in SOURCE_SHA:
            assert SOURCE_SHA[name] == sha and source_map["source_paths"][name] == row["path"]
        if name in OWN_SOURCES or name in ("SOURCE-INPUTS.json", "run_adoption01.ps1"):
            assert member(run + "/" + name) == member(proposal + "/" + name)
    support = {row["path"]: row for row in before["native_inputs"]}
    assert len(support) == len(before["native_inputs"]) == 9 and set(support) == set(source_map["native_bindings"])
    later_support = {row["path"]: row for row in after["support_and_fixtures"]}
    assert len(later_support) == len(after["support_and_fixtures"]) == 14
    for path, row in support.items():
        bound, later = source_map["native_bindings"][path], later_support[path]
        assert bound["bytes"] == row["bytes"] == later["bytes"]
        assert bound["sha256"] == row["sha256"] == later["before_sha256"] == later["after_sha256"]
    assert [row["name"] for row in before["fixtures"]] == list(FIXTURE_NAMES)
    for row in before["fixtures"]:
        name, raw = row["name"], fixtures[row["name"]]
        assert row["path"] == str(BASE / run / name) and row["writer_closed"] is True
        assert member(run + "/" + name) == raw
        later = later_support[row["path"]]
        assert len(raw) == row["bytes"] == later["bytes"]
        assert digest(raw) == row["sha256"] == later["before_sha256"] == later["after_sha256"]
    results = {}
    for role, count in zip(("controller", "child"), counts):
        receipt = record(run + "/" + role + "-result.json")
        results[role] = receipt
        assert receipt["schema"] == "uoink.generated-inherited-readset.v1" and receipt["role"] == role and receipt["case"] == case
        assert receipt["guard_valid"] is receipt["fixed_dispatch_valid"] is receipt["kernel32_path_verified"] is True
        assert receipt["guard_denials"] == receipt["model_imports"] == [] and receipt["model_calls"] == 0
        assert receipt["metadata_traps"] == 12 and receipt["registry_traps"] == 25
        assert receipt["error_type"] is None and receipt["pending_pipe_operations"] == 0
        assert receipt["work_budget_closed"] is False and receipt["reserved_cleanup_calls"] == receipt["reserved_cleanup_wait_caps"] == []
        casts = 1 if role == "controller" else 0
        assert receipt["fixed_dispatch_function_count"] == 32 and receipt["fixed_attribute_cast_calls"] == casts
        assert receipt["fixed_dispatch_completed_calls"] == receipt["fixed_dispatch_audit_events"] == count == 33 + len(receipt["native_api_calls"]) + casts
        assert receipt["fixed_dispatch_invalid_contexts"] == 0 and receipt["source_sha256"] == SOURCE_SHA
        assert receipt["native_exit_planned"] == (0 if role == "controller" else expected_child)
        assert receipt["native_api_calls"].count("CreateProcessW") == (1 if role == "controller" else 0)
        assert receipt["ctypes_bootstrap_loads"] == ["kernel32", r"C:\Windows\System32\kernel32.dll"]
        assert set(receipt["generated_asset_io"]) == set(FIXTURE_NAMES)
    controller, child = results["controller"], results["child"]
    assert "CreateFileW" not in child["native_api_calls"]
    result, adopted = controller["result"], child["result"]["adoption"]
    assert result["lifecycle_phase"] == 8 and result["adoption_case"] == case and result["model_calls"] == 0
    assert result["read_set_released"] is result["pipe_retired"] is result["parent_guards_held_through_exit"] is True
    assert result["exit_observation"] == {"child_native_exit": expected_child, "process_wait_observed": True, "job_active_processes": 0}
    assert result["write_access_observations"] == [{"write_open_refused": True, "winerror": 32}] * 5 + [{"write_open_succeeded": True, "bytes_written": 0}] * 5
    assert child["result"]["child_flow_return"] == expected_child and child["result"]["model_calls"] == 0
    assert adopted["owned_members"] == adopted["inheritance_cleared"] == 5
    assert adopted["complete_native_namespace_protection"] is False and adopted["model_calls"] == 0
    authenticated = result["authenticated_manifest"]
    assert authenticated["schema"] == "uoink.generated-inherited-readset.v1" and authenticated["case"] == case
    assert authenticated["namespace_sha256"] == namespace and len(authenticated["members"]) == 5
    canonical = json.dumps(authenticated, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    assert digest(canonical) == result["manifest_sha256"]
    assert len({row["handle"] for row in authenticated["members"]}) == 5
    for expected, row in zip(fixture_rows, authenticated["members"]):
        assert row["name"] == expected["name"] and row["sha256"] == expected["sha256"] and row["identity"]["size"] == expected["bytes"]
        assert type(row["handle"]) is int and row["handle"] > 0
    expected_checks = 5 if case == "positive" else 1
    assert adopted["identities_checked"] == len(adopted["observed_identities"]) == expected_checks
    for observed, row in zip(adopted["observed_identities"], authenticated["members"]):
        expected = row["identity"]
        assert set(observed) == set(expected) == {"directory", "final_path", "links", "size", "volume_serial", "file_id"}
        assert all(observed[key] == expected[key] for key in expected if key != "file_id")
        observed_id, expected_id = bytes.fromhex(observed["file_id"]), bytes.fromhex(expected["file_id"])
        assert len(observed_id) == len(expected_id) == 16
        assert expected_id == (observed_id if case == "positive" else bytes([observed_id[0] ^ 1]) + observed_id[1:])
    for name, raw in fixtures.items():
        assert controller["generated_asset_io"][name] == {"seeks": 0, "reads": 0, "bytes": 0}
        expected_io = {"seeks": 1, "reads": 2, "bytes": len(raw)} if case == "positive" else {"seeks": 0, "reads": 0, "bytes": 0}
        assert child["generated_asset_io"][name] == expected_io
    assert result["controller_handshake_begun"] is (case == "positive")
    assert adopted["materialization_started"] is (case == "positive")
    assert adopted["read_set_released"] is (case == "positive") and adopted["read_set_unconfirmed"] is (case != "positive")
    assert adopted["handles_closed"] == [case == "positive"] * 5
    if case == "positive":
        assert adopted["status"] == "released" and result["generated_result"] == child["result"]["readback"] == readback
        assert result["adoption_response"] == {"case": case, "identities_checked": 5, "inheritance_cleared": 5,
            "materialization_started": False, "namespace_sha256": namespace, "owned_members": 5}
    else:
        assert adopted["status"] == "refused" and child["result"]["readback"] is None
        assert result["generated_result"] == {"expected_identity_refusal": True, "materialization_started": False}
        assert result["adoption_response"] == {"case": case, "identities_checked": 1, "inheritance_cleared": 5,
            "materialization_started": False, "owned_members": 5, "read_set_unconfirmed": True, "reason": "inherited_file_identity_mismatch"}
    summaries.append({"case": case, "controller_native_exit": 0, "observed_child_native_exit": expected_child,
        "actual_outer_exit": tool["exit_code"], "controller_elapsed_seconds": controller["elapsed_seconds"],
        "child_elapsed_seconds": child["elapsed_seconds"], "case_contract_met": True})

print(json.dumps({"verified": True, "payload_count": 79, "logical_members": 103, "distinct_objects": 70,
    "manifest_sha256": digest(manifest_raw), "observations": summaries,
    "tests_or_native_runs_executed": 0, "model_or_market_acceptance": False}))

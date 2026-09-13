"""Verify saved bytes and outcomes only; never execute or import archived code."""
from pathlib import Path
import hashlib
import json

OUT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\dummy-native-combined-proof01")
INVENTORY_SHA = "887eb2722416f1c153a64457b5e18b01b6279c9414280aacfb77cb353208dd08"
PRIOR_SEAL = "412ff1c34376f0ce156c055e27afc66e9d19ed3ed7358f939e7f8df1b526f02f"
SOURCES = {"snapshot_lifecycle.py", "owned_generation_protocol.py", "win32_worker_connection.py",
           "win32_private_pipe.py", "generated_worker_flow.py", "dummy_bootstrap.py"}


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
assert manifest["payload_count"] == len(manifest["files"]) == 119
assert len({row["path"] for row in manifest["files"]}) == 119
actual = {path.relative_to(OUT).as_posix() for path in OUT.rglob("*") if path.is_file()}
assert actual == {row["path"] for row in manifest["files"]} | {"MANIFEST.json"}
total = 0
for row in manifest["files"]:
    raw = read(OUT / relative(row["path"]))
    assert len(raw) == row["bytes"] and digest(raw) == row["sha256"]
    total += len(raw)
assert total == manifest["payload_bytes"] and read(OUT / ".gitattributes") == b"* -text\n"
mapping = json.loads(read(OUT / "LOGICAL-MEMBERS.json"))
assert mapping["logical_count"] == len(mapping["files"]) == 169
index = {row["path"]: row for row in mapping["files"]}
assert len(index) == 169
for row in index.values():
    relative(row["path"])
    assert len(row["sha256"]) == 64 and all(c in "0123456789abcdef" for c in row["sha256"])
    assert row["object"] == "objects/" + row["sha256"]
    raw = read(OUT / row["object"])
    assert len(raw) == row["bytes"] and digest(raw) == row["sha256"]
assert {row["object"] for row in index.values()} == {name for name in actual if name.startswith("objects/")}
inventory_raw = read(OUT / "instruments/SOURCE-MEMBERS.json")
assert digest(inventory_raw) == INVENTORY_SHA
inventory = json.loads(inventory_raw)
assert inventory["logical_count"] == 169 and inventory["logical_bytes"] == 1287807 and inventory["distinct_objects"] == 111
assert sum(row["bytes"] for row in index.values()) == 1287807
for row in inventory["files"]:
    mapped = index[row["logical_path"]]
    assert (mapped["bytes"], mapped["sha256"]) == (row["bytes"], row["sha256"])


def member(name):
    return read(OUT / index[name]["object"])


def record(name):
    return json.loads(member(name))


assert digest(member("asr-worker-namespace-proposal01/MANIFEST.json")) == PRIOR_SEAL
fixture = b"Uoink generated worker guard fixture. No model or library data.\n"
assert len(fixture) == 64
for number, chunk, expected_exit, stderr_bytes in (("01", "84f5c9", 1, 495), ("02", "04414f", 1, 498),
                                                  ("03", "08be19", 1, 316), ("04", "7b331c", 0, 0)):
    run, proposal = "asr-dummy-worker-native" + number, "asr-dummy-worker-flow-proposal" + number
    status = record(run + "/exit.json")
    native = record(run + "/native-exit.json")
    tool = record("DUMMY-NATIVE" + number + "-ACTUAL.json")
    assert type(native["native_exit"]) is int and native["child_returned"] is True
    assert native["native_exit"] == status["controller_native_exit"] == status["outer_exit"] == tool["exit_code"] == expected_exit
    assert tool["chunk_id"] == chunk and tool["wall_time_seconds"] >= 0
    assert status["inputs_unchanged"] is True and status["receipt_valid"] is (number == "04")
    assert member(run + "/controller-stdout.log") == b"" and status["stdout_bytes"] == 0
    assert len(member(run + "/controller-stderr.log")) == status["stderr_bytes"] == stderr_bytes
    admission, source_map = record(run + "/ROOT-ADMISSION.json"), record(run + "/SOURCE-INPUTS.json")
    assert admission["root_reviewed"] is True and admission["scope"] == "generated-file-one-owned-dummy-worker-only"
    assert admission["source_inputs_sha256"] == digest(member(run + "/SOURCE-INPUTS.json"))
    assert admission["launcher_sha256"] == digest(member(run + "/run_native" + number + ".ps1"))
    assert set(source_map["source_sha256"]) == SOURCES
    before, after = record(run + "/before.json"), record(run + "/after.json")
    assert after["inputs_unchanged"] is True
    assert len(before["sources"]) == 6 and {row["name"] for row in before["sources"]} == SOURCES
    assert len(before["controls"]) == 3 and {row["name"] for row in before["controls"]} == {"ROOT-ADMISSION.json", "SOURCE-INPUTS.json", "run_native" + number + ".ps1"}
    for kind in ("sources", "controls"):
        later = {row["name"]: row for row in after[kind]}
        assert len(later) == len(after[kind]) == len(before[kind])
        for row in before[kind]:
            name, sha = row["name"], row["sha256"]
            assert digest(member(run + "/" + name)) == sha
            assert all(later[name][key] == sha for key in ("before_sha256", "copy_after_sha256", "source_after_sha256"))
            if kind == "controls" or name in ("dummy_bootstrap.py", "generated_worker_flow.py"):
                assert member(run + "/" + name) == member(proposal + "/" + name)
            if kind == "sources":
                assert source_map["source_sha256"][name] == sha
    earlier_native = {row["path"]: row for row in before["native_inputs"]}
    later_native = {row["path"]: row for row in after["native_inputs"]}
    assert len(earlier_native) == len(before["native_inputs"]) == (8 if number == "01" else 9)
    assert len(later_native) == len(after["native_inputs"]) == len(earlier_native)
    assert set(earlier_native) == set(later_native) == set(source_map["native_bindings"])
    for path, row in earlier_native.items():
        bound, later = source_map["native_bindings"][path], later_native[path]
        assert bound["bytes"] == row["bytes"] == later["bytes"]
        assert bound["sha256"] == row["sha256"] == later["before_sha256"] == later["after_sha256"]
    assert member(run + "/generated-guard.txt") == fixture and before["fixture_bytes"] == 64
    assert before["fixture_sha256"] == after["fixture_before_sha256"] == after["fixture_after_sha256"] == digest(fixture)
    if number != "04":
        assert run + "/controller-result.json" not in index and run + "/child-result.json" not in index
    if number != "01":
        previous = "0" + str(int(number) - 1)
        for name in ("dummy_bootstrap.py", "generated_worker_flow.py", "run_native" + previous + ".ps1"):
            assert member(proposal + "/before/" + name) == member("asr-dummy-worker-flow-proposal" + previous + "/" + name)

for role, dispatches, casts in (("controller", 148, 1), ("child", 109, 0)):
    result = record("asr-dummy-worker-native04/" + role + "-result.json")
    assert result["schema"] == "uoink.generated-owned-worker.v1" and result["role"] == role
    assert result["error_type"] is None and result["native_exit_planned"] == 0
    assert result["guard_valid"] is result["fixed_dispatch_valid"] is result["kernel32_path_verified"] is True
    assert result["guard_denials"] == result["model_imports"] == [] and result["model_calls"] == 0
    assert result["metadata_traps"] == 12 and result["registry_traps"] == 25
    assert result["fixed_dispatch_function_count"] == 31 and result["fixed_attribute_cast_calls"] == casts
    assert result["fixed_dispatch_completed_calls"] == result["fixed_dispatch_audit_events"] == dispatches
    assert dispatches == 32 + len(result["native_api_calls"]) + casts and result["fixed_dispatch_invalid_contexts"] == 0
    assert result["work_budget_closed"] is False and result["reserved_cleanup_calls"] == result["reserved_cleanup_wait_caps"] == []
    assert result["source_sha256"] == record("asr-dummy-worker-native04/SOURCE-INPUTS.json")["source_sha256"]
    assert result["ctypes_bootstrap_loads"] == ["kernel32", r"C:\Windows\System32\kernel32.dll"]
    assert result["native_api_calls"].count("CreateProcessW") == (1 if role == "controller" else 0)
controller = record("asr-dummy-worker-native04/controller-result.json")["result"]
assert controller["generated_result"] == {"characters": 40000, "generated_sha256": "49b5147f78225eabab7fb57a6e7d2b40eb5f78495ec830db98b81ab452885769"}
assert controller["lifecycle_phase"] == 8 and controller["model_calls"] == 0
assert controller["read_set_released"] is controller["pipe_retired"] is controller["controller_handshake_begun"] is True
assert controller["exit_observation"] == {"child_native_exit": 0, "process_wait_observed": True, "job_active_processes": 0}
assert controller["write_access_observations"] == [{"write_open_refused": True, "winerror": 32}, {"write_open_succeeded": True, "bytes_written": 0}]
retirement = controller["parent_guard_retirement"]
assert retirement["parent_originals_closed"] is retirement["parent_inheritable_copies_closed"] is retirement["exact_child_alive_after_parent_close"] is True
assert len(retirement["parent_original_values"]) == len(retirement["child_guard_values"]) == 1
assert record("asr-dummy-worker-native04/child-result.json")["result"] == {"child_flow_return": 0}
root_check = record("NATIVE04-GRAPH01-ROOT-VERIFY-ACTUAL.json")
assert root_check["chunk_id"] == "a58725" and root_check["exit_code"] == 0
root_summary = json.loads(root_check["output"])
assert root_summary["documentary_verification"] == "PASS" and root_summary["native04"]["actual_native_result"] == "PASS"
assert root_summary["graph01"]["actual_graph_result"] == "FAIL" and root_summary["graph01"]["missing_wheels"] == 2
print(json.dumps({"verified": True, "payload_count": 119, "logical_members": 169,
                  "preserved_failed_native_attempts": 3, "successful_native_observations": 1,
                  "tests_or_native_runs_executed_by_verifier": 0, "manifest_sha256": digest(manifest_raw)}))

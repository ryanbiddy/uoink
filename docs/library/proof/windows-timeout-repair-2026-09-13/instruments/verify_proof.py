"""Verify saved documentary bytes/outcomes; no archived-code execution."""
from pathlib import Path
import hashlib
import json

OUT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\timeout-repair-proof01")
INVENTORY_SHA = "596da114af68814af63a4ef9834d5c5c2badedde1765533529ada499b804bbef"
OLD_PIPE = "4a0cccc8d905f7dc9d93288d8c9187f7da846ee673a57e625e691e17bbed899c"
NEW_PIPE = "73a1109a55f2bc807594655c71b24a3e35eb88d7f744497df2cc328dc224cae7"
OLD_CASES = "419d9c10f03ee80167567f2332b70d1153f1e940ebf50269070d84aa7c7b5071"
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
assert manifest["payload_count"] == len(manifest["files"]) == 117
assert len({row["path"] for row in manifest["files"]}) == 117
actual = {p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file()}
assert actual == {row["path"] for row in manifest["files"]} | {"MANIFEST.json"}
total = 0
for row in manifest["files"]:
    raw = read(OUT / relative(row["path"]))
    assert len(raw) == row["bytes"] and digest(raw) == row["sha256"]
    total += len(raw)
assert total == manifest["payload_bytes"] and read(OUT / ".gitattributes") == b"* -text\n"
mapping = json.loads(read(OUT / "SOURCE-TREE.json"))
assert mapping["logical_count"] == len(mapping["files"]) == 184
index = {row["path"]: row for row in mapping["files"]}
assert len(index) == 184
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
assert inventory["logical_count"] == 184 and inventory["logical_bytes"] == 1780288 and inventory["distinct_objects"] == 108
assert sum(row["bytes"] for row in index.values()) == 1780288
assert len({row["sha256"] for row in index.values()}) == 108
for row in inventory["files"]:
    mapped = index[row["logical_path"]]
    assert (mapped["bytes"], mapped["sha256"]) == (row["bytes"], row["sha256"])
copy_receipt = json.loads(read(OUT / "COPY-VERIFICATION.json"))
assert copy_receipt == {"schema": "uoink.documentary-copy-verification.v1",
    "physical_payloads_checked": 116, "logical_members": 184, "distinct_objects": 108,
    "logical_bytes": 1780288, "exact_file_set": True, "exact_copy_bytes": True,
    "source_inventory_sha256": INVENTORY_SHA, "tests_or_native_runs_executed": 0}


def member(name):
    return read(OUT / index[name]["object"])


def record(name):
    return json.loads(member(name))


fixture = b"Uoink generated worker guard fixture. No model or library data.\n"
native_summaries = []
for number, chunk, expected_exit, dispatches, pipe_sha in (
        ("01", "c32937", 1, 134, OLD_PIPE), ("02", "2624a3", 0, 142, NEW_PIPE)):
    run = "asr-dummy-worker-timeout" + number
    proposal = "asr-dummy-worker-timeout-proposal" + number
    status, native = record(run + "/exit.json"), record(run + "/native-exit.json")
    tool = record("DUMMY-TIMEOUT" + number + "-ACTUAL.json")
    assert type(native["native_exit"]) is int and native["child_returned"] is True
    assert native["native_exit"] == status["controller_native_exit"] == status["outer_exit"] == tool["exit_code"] == expected_exit
    assert tool["chunk_id"] == chunk and tool["wall_time_seconds"] >= 0
    assert status["inputs_unchanged"] is True and status["receipt_valid"] is (number == "02")
    assert member(run + "/controller-stdout.log") == member(run + "/controller-stderr.log") == b""
    assert status["stdout_bytes"] == status["stderr_bytes"] == 0
    admission, source_map = record(run + "/ROOT-ADMISSION.json"), record(run + "/SOURCE-INPUTS.json")
    assert admission["root_reviewed"] is True and admission["scope"] == "generated-file-one-owned-dummy-timeout-only"
    assert admission["source_inputs_sha256"] == digest(member(run + "/SOURCE-INPUTS.json"))
    assert admission["launcher_sha256"] == digest(member(run + "/run_timeout" + number + ".ps1"))
    assert set(source_map["source_sha256"]) == SOURCES and source_map["source_sha256"]["win32_private_pipe.py"] == pipe_sha
    before, after = record(run + "/before.json"), record(run + "/after.json")
    assert after["inputs_unchanged"] is True
    assert len(before["sources"]) == 6 and {row["name"] for row in before["sources"]} == SOURCES
    assert len(before["controls"]) == 3 and {row["name"] for row in before["controls"]} == {"ROOT-ADMISSION.json", "SOURCE-INPUTS.json", "run_timeout" + number + ".ps1"}
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
    assert len(earlier_native) == len(before["native_inputs"]) == len(later_native) == len(after["native_inputs"]) == 9
    assert set(earlier_native) == set(later_native) == set(source_map["native_bindings"])
    for path, row in earlier_native.items():
        bound, later = source_map["native_bindings"][path], later_native[path]
        assert bound["bytes"] == row["bytes"] == later["bytes"]
        assert bound["sha256"] == row["sha256"] == later["before_sha256"] == later["after_sha256"]
    assert member(run + "/generated-guard.txt") == fixture and before["fixture_bytes"] == len(fixture) == 64
    assert before["fixture_sha256"] == after["fixture_before_sha256"] == after["fixture_after_sha256"] == digest(fixture)
    results = {}
    for role in ("controller", "child"):
        result = record(run + "/" + role + "-result.json")
        results[role] = result
        assert result["schema"] == "uoink.generated-owned-timeout.v1" and result["role"] == role
        assert result["guard_valid"] is result["fixed_dispatch_valid"] is result["kernel32_path_verified"] is True
        assert result["guard_denials"] == result["model_imports"] == [] and result["model_calls"] == 0
        assert result["metadata_traps"] == 12 and result["registry_traps"] == 25
        casts = 1 if role == "controller" else 0
        assert result["fixed_dispatch_function_count"] == 31 and result["fixed_attribute_cast_calls"] == casts
        assert result["fixed_dispatch_completed_calls"] == result["fixed_dispatch_audit_events"] == 32 + len(result["native_api_calls"]) + casts
        assert result["fixed_dispatch_invalid_contexts"] == 0
        assert result["work_budget_closed"] is False and result["reserved_cleanup_calls"] == result["reserved_cleanup_wait_caps"] == []
        assert result["source_sha256"] == source_map["source_sha256"]
        assert result["ctypes_bootstrap_loads"] == ["kernel32", r"C:\Windows\System32\kernel32.dll"]
        assert result["native_api_calls"].count("CreateProcessW") == (1 if role == "controller" else 0)
    child, controller = results["child"], results["controller"]
    assert child["stage"] == "child_pre_stall_only" and child["native_exit_planned"] is None and child["error_type"] is None
    assert child["result"] == {"stage": "armed_before_wait", "stall_ms": 15000,
        "generated_request_validated": True, "native_exit_observed": False}
    assert controller["stage"] == "controller_final" and controller["native_exit_planned"] == expected_exit
    assert controller["fixed_dispatch_completed_calls"] == dispatches
    result = controller["result"]
    timeout = result["timeout"]
    assert result["case"] == "generated_missing_response_forced_stop" and result["qualified"] is (number == "02")
    assert result["lifecycle_phase"] == 7 and result["lifecycle_phase_name"] == "QUARANTINED"
    assert result["read_set_released"] is result["pipe_retired"] is result["quarantine_persisted"] is False
    assert result["controller_handshake_begun"] is True and result["model_calls"] == 0
    assert result["exit_observation"] == {"child_native_exit": 1, "process_wait_observed": True,
        "job_active_processes": 0, "retained_creation_identity_equal": True}
    assert timeout["expected_operation_failed"] is timeout["first_read_wait_timeout_observed"] is True
    assert timeout["reason"] == "overlapped_completion_not_observed" and timeout["error_type"] == "PipeRefusal"
    assert timeout["deadline_seconds"] == 0.25 and 0 <= timeout["observed_elapsed_seconds"] <= 30
    assert timeout["armed_response_validated"] is timeout["child_alive_before_wait"] is timeout["parent_originals_still_open"] is True
    assert timeout["forced_stop_attempted"] is timeout["forced_process_stop_observed"] is timeout["ordinary_release_refused"] is True
    assert timeout["forced_stop_error_type"] is None
    outcomes = timeout["native_outcomes"]
    assert [(r["name"], r["return"]) for r in outcomes] == [("ReadFile", 0), ("WaitForSingleObject", 258),
        ("TerminateJobObject", 1), ("WaitForSingleObject", 0), ("CancelIoEx", 0),
        ("WaitForSingleObject", 0), ("GetOverlappedResult", 0)]
    assert [outcomes[i]["requested_ms"] for i in (1, 3, 5)] == [250, 5000, 1000]
    assert [outcomes[i]["winerror"] for i in (0, 4, 6)] == [997, 1168, 109]
    assert controller["native_api_calls"].count("TerminateJobObject") == controller["native_api_calls"].count("CancelIoEx") == 1
    assert controller["native_api_calls"].count("TerminateProcess") == 0
    writes = [{"write_open_refused": True, "winerror": 32}] * 2
    if number == "01":
        assert controller["error_type"] == "KernelUnconfirmed" and controller["error_reason"] == "pending_io_prevents_generated_teardown"
        assert controller["finalization"] == "immediate_failed_process_exit_without_python_cleanup"
        assert result["generated_teardown"] is None and len(result["pending_operations"]) == 1
        pending = result["pending_operations"][0]
        assert pending["submitted"] is pending["unconfirmed"] is pending["cancellation_attempted"] is pending["buffer_retained"] is True
        assert pending["complete"] is pending["cancelled"] is pending["event_closed"] is False
    else:
        assert controller["error_type"] is None and controller["finalization"] == "normal_exit"
        assert result["pending_operations"] == timeout["pending_operations"] == []
        assert result["generated_teardown"] == {"attempted": True, "complete": True, "pending_operations_before": 0,
            "native_exit_observed_before": True, "empty_job_observed_before": True, "logical_read_set_released": False}
        writes += [{"write_open_succeeded": True, "bytes_written": 0}]
    assert result["write_access_observations"] == writes
    native_summaries.append({"run": number, "actual_exit": expected_exit, "qualified": result["qualified"]})

synthetic = []
for base, actual_name, chunk in (
        ("asr-dummy-worker-timeout-proposal02/synthetic", "PIPE-TERMINAL67-AUTHOR-ACTUAL.json", "030e68"),
        ("astra-pipe-terminal67-qualification01", "PIPE-TERMINAL67-ROOT-ACTUAL.json", "6b62a5")):
    run = base + "/runs/pc01"
    result, status = record(run + "/stdout.json"), record(run + "/exit.json")
    native, tool = record(run + "/native-exit.json"), record(actual_name)
    assert tool["chunk_id"] == chunk and tool["exit_code"] == native["native_exit"] == status["native_exit"] == status["outer_exit"] == result["native_exit"] == 0
    assert status["inputs_unchanged"] is status["receipt_valid"] is True
    assert member(run + "/stderr.log") == b"" and status["stderr_bytes"] == 0
    assert result["count"] == result["passed"] == 67 and result["failed"] == result["skipped"] == 0
    assert len(result["cases"]) == len({r["name"] for r in result["cases"]}) == 67
    assert all(r["passed"] is True for r in result["cases"])
    assert [r["name"] for r in result["cases"]] == result["expected_cases"]
    for field in ("guard_valid", "metadata_traps_installed", "content_reads_closed", "baseline_winreg_identity_unchanged",
                  "registry_namespace_unchanged", "registry_traps_installed", "captures_installed", "capture_valid"):
        assert result[field] is True
    assert result["metadata_trap_count"] == 12 and result["registry_trap_count"] == 25
    assert result["guard_denials"] == result["registry_denials"] == result["heavy_roots_loaded"] == []
    assert result["stdout_capture"] == result["stderr_capture"] == ""
    assert result["input_sha256"]["win32_private_pipe.py"] == NEW_PIPE
    assert result["input_sha256"]["contract_cases.py"] == OLD_CASES and len(result["input_sha256"]) == 8
    admission = record(run + "/ROOT-ADMISSION.json")
    assert admission["root_reviewed"] is True and admission["scope"] == "pipe-terminal-fake-api-67-only" and admission["label"] == "pc01"
    assert admission["expected_cases"] == result["expected_cases"] and len(admission["input_sha256"]) == 10
    plan, after = record(run + "/plan.json"), record(run + "/after.json")
    later = {r["name"]: r for r in after}
    assert len(plan["inputs"]) == len(later) == len(after) == 11
    for row in plan["inputs"]:
        name, sha = row["name"], row["sha256"]
        assert digest(member(run + "/" + name)) == digest(member(base + "/" + name)) == sha
        assert all(later[name][key] == sha for key in ("before_sha256", "copy_after_sha256", "source_after_sha256"))
        if name != "ROOT-ADMISSION.json":
            assert admission["input_sha256"][name] == sha
        if name in result["input_sha256"]:
            assert result["input_sha256"][name] == sha
    synthetic.append(result)
assert synthetic[0]["cases"] == synthetic[1]["cases"]
assert synthetic[0]["input_sha256"] == synthetic[1]["input_sha256"]
assert digest(member("asr-dummy-worker-timeout-proposal02/win32_private_pipe.py")) == NEW_PIPE
assert digest(member("asr-dummy-worker-timeout-proposal02/before/win32_private_pipe.py")) == OLD_PIPE
assert member("asr-dummy-worker-timeout01/generated_worker_flow.py") == member("asr-dummy-worker-timeout02/generated_worker_flow.py")
print(json.dumps({"verified": True, "payload_count": 117, "logical_members": 184,
    "preserved_failed_native_attempts": 1, "qualified_generated_native_observations": 1,
    "author_synthetic": [67, 0, 0], "independent_synthetic": [67, 0, 0], "complete_case_rows_equal": True,
    "logical_quarantine_preserved": True, "tests_or_native_runs_executed_by_verifier": 0,
    "native_outcomes": native_summaries, "manifest_sha256": digest(manifest_raw)}))

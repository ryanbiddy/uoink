"""Proposed documentary copy only. Run once only after root source admission."""
import hashlib
import json
from pathlib import Path

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE = Path(__file__).parent
AUTHOR = BASE / "_scratch/asr-native-exit-instrument-outcomes01"
INDEPENDENT = BASE / "_scratch/astra-asr-adapter-qualification03"
OUTPUT = BASE / "_scratch/asr-adapter-combined-proof01"
AUTHOR_SEAL = "6b2afa0ffa02fee2facbd272ce53a328627065f6c0a1f0cbd96a6f3ad956c691"
ROOT_INPUTS_SHA = "a3f7e75a10005f5ba5eb1ecf4bb4c8046d6c3b12b803d634d514c538b0c8d9df"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, cap):
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    assert len(raw) <= cap, str(path)
    return raw


def payloads(folder, rows):
    result = {}
    for row in rows:
        name = row["path"]
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        assert name not in result
        raw = read(folder / name, row["bytes"])
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"], name
        result[name] = raw
    return result


def decoded(raw):
    return json.loads(raw)


def check_result(items, run_prefix, tool_name):
    result = decoded(items[run_prefix + "stdout.json"])
    native = decoded(items[run_prefix + "native-exit.json"])
    final = decoded(items[run_prefix + "exit.json"])
    actual = decoded(items[tool_name])
    assert result["schema"] == "uoink.inert-asr-adapter-qualification.v1"
    assert len(result["cases"]) == len({row["name"] for row in result["cases"]}) == 58
    assert all(row["passed"] is True for row in result["cases"])
    assert result["passed"] == 58 and result["failed"] == 0
    assert type(native["native_exit"]) is int and native["native_exit"] == 0
    assert result["qualification_exit"] == final["native_exit"] == final["outer_exit"] == actual["exit_code"] == 0
    for name in ("guard_valid", "metadata_traps_installed", "real_resolver_approval_unchanged_none",
                 "real_resolver_functions_unchanged", "adapter_globals_restored",
                 "startup_binding_asserted", "torch_backend_autoload_disabled_before_startup"):
        assert result[name] is True, name
    assert result["metadata_trap_count"] == 11
    assert result["metadata_trap_mismatches"] == result["guard_denials"] == result["heavy_roots_loaded"] == []
    assert final["inputs_unchanged"] is True and final["receipt_valid"] is True and final["stderr_bytes"] == 0
    assert items[run_prefix + "stderr.log"] == b""
    plan = decoded(items[run_prefix + "plan.json"])
    after = decoded(items[run_prefix + "after.json"])
    assert len(plan["inputs"]) == len(after) == 15
    before = {row["name"]: row["sha256"] for row in plan["inputs"]}
    assert len(before) == 15 and {row["name"] for row in after} == set(before)
    for row in after:
        assert row["before_sha256"] == row["copy_after_sha256"] == row["source_after_sha256"] == before[row["name"]]
        assert sha(items[run_prefix + row["name"]]) == before[row["name"]]
    return result


def main():
    assert not OUTPUT.exists(), "Fresh documentary output directory required"
    author_seal_raw = read(AUTHOR / "SHA256.json", 200000)
    assert sha(author_seal_raw) == AUTHOR_SEAL
    author_seal = decoded(author_seal_raw)
    assert author_seal["payload_count"] == 209 and author_seal["payload_bytes"] == 811155
    author = payloads(AUTHOR, author_seal["files"])
    root_inputs_raw = read(HERE / "ROOT-INPUTS-v2.json", 50000)
    assert sha(root_inputs_raw) == ROOT_INPUTS_SHA
    root_inputs = decoded(root_inputs_raw)
    assert root_inputs["source_root"] == str(INDEPENDENT)
    assert root_inputs["payload_count"] == len(root_inputs["files"]) == 37
    assert root_inputs["payload_bytes"] == sum(row["bytes"] for row in root_inputs["files"]) == 217293
    independent = payloads(INDEPENDENT, root_inputs["files"])
    assert {p.relative_to(INDEPENDENT).as_posix() for p in INDEPENDENT.rglob("*") if p.is_file()} == set(independent)
    a = check_result(author, "asr-author03/adapter-preflight03/", "asr-author03/ACTUAL-TOOL-PREFLIGHT03.json")
    b = check_result(independent, "adapter-preflight03/", "ACTUAL-TOOL-PREFLIGHT03.json")
    assert a["cases"] == b["cases"], "Exact ordered case/result equality required"
    copy_bindings = decoded(independent["COPY-BINDINGS.json"])
    assert len(copy_bindings) == len({row["name"] for row in copy_bindings}) == 13
    for row in copy_bindings:
        name = row["name"]
        original = author["asr-author03/adapter-preflight03/" + name]
        copied = independent[name]
        assert sha(original) == row["source_sha256"] and sha(copied) == row["copy_sha256"]
        if name == "run_preflight03.ps1":
            old = b"_scratch\\asr-native-exit-scope-repair01\\candidate"
            new = b"_scratch\\astra-asr-adapter-qualification03"
            assert original.count(old) == 1 and original.replace(old, new) == copied
            assert sha(copied) == "55403fff1ff1cfeb28b8896a586486b802b1c3c3d6425167cd3494eb7f27461c"
        else:
            assert original == copied, name
    prep_raw = read(HERE / "PREPARATION-SHA256.json", 50000)
    prep = decoded(prep_raw)
    proposal = payloads(HERE, prep["files"])
    OUTPUT.mkdir()

    def put(name, raw):
        path = OUTPUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
        assert sha(read(path, len(raw))) == sha(raw)

    for name, raw in author.items():
        put("author-history209/" + name, raw)
    put("author-history209/SHA256.json", author_seal_raw)
    for name, raw in independent.items():
        put("independent-root/" + name, raw)
    for name, raw in proposal.items():
        put("assembly-protocol/" + name, raw)
    put("assembly-protocol/PREPARATION-SHA256.json", prep_raw)
    put("VERDICT.md", proposal["VERDICT.md"])
    put(".gitattributes", b"* -text\n")
    summary = {"schema": "uoink.asr-fake-port-combined-results.v1", "distinct_cases": 58,
               "author": {"passed": 58, "failed": 0, "elapsed_seconds": a["elapsed_seconds"], "tool_exit": 0},
               "independent": {"passed": 58, "failed": 0, "elapsed_seconds": b["elapsed_seconds"], "tool_exit": 0},
               "ordered_case_results_identical": True, "case_ids": [row["name"] for row in a["cases"]],
               "root_preparation_files": 13, "identical_preparation_files": 12, "runner_change": "taskProposal path only",
               "old_null_capture_failure_preserved": True, "fabricated_wrapper_rows_count_as_asr_cases": False,
               "native_model_or_package_execution": False}
    put("RESULTS.json", (json.dumps(summary, indent=2) + "\n").encode())
    rows = []
    for path in sorted(OUTPUT.rglob("*")):
        if path.is_file():
            raw = read(path, 2000000)
            rows.append({"path": path.relative_to(OUTPUT).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
    manifest = {"schema": "uoink.asr-adapter-combined-proof.v1", "date": "2026-09-13",
                "payload_count": len(rows), "payload_bytes": sum(row["bytes"] for row in rows), "files": rows}
    put("SHA256.json", (json.dumps(manifest, indent=2) + "\n").encode())
    print(json.dumps({"output": str(OUTPUT), "payload_count": len(rows), "payload_bytes": manifest["payload_bytes"],
                      "manifest_sha256": sha(read(OUTPUT / "SHA256.json", 200000))}))


if __name__ == "__main__":
    main()

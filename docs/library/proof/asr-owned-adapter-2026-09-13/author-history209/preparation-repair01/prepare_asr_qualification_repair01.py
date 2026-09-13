"""Data-only source preservation and narrow instrument derivation. No imports of proposals."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
OLD = ROOT / "_scratch/asr-production-adapter-proposal01"
OUT = ROOT / "_scratch/asr-production-adapter-qualification-repair01"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(name, raw):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw if isinstance(raw, bytes) else raw.encode("utf-8"))


def json_write(name, value):
    write(name, json.dumps(value, indent=2) + "\n")


manifest_raw = (OLD / "PREPARATION-SHA256.json").read_bytes()
manifest = json.loads(manifest_raw)
assert manifest["payload_count"] == 23
checked = []
for row in manifest["files"]:
    name = row["path"]
    assert not Path(name).is_absolute() and ".." not in Path(name).parts
    raw = (OLD / name).read_bytes()
    assert len(raw) == row["bytes"] and digest(raw) == row["sha256"], name
    write("original-proposal/" + name, raw)
    checked.append(row)
write("original-proposal/PREPARATION-SHA256.json", manifest_raw)
json_write("ORIGINAL-SEAL-VERIFICATION.json", {
    "schema": "uoink.asr-instrument-source-preservation.v1", "date": "2026-09-13",
    "manifest_sha256": digest(manifest_raw), "payload_count": len(checked),
    "payload_bytes": sum(x["bytes"] for x in checked), "all_payloads_verified": True,
    "original_files_modified": False, "execution": "None; text byte copy/hash only"})

# Keep review context at its previous exact bytes. BRIEF.md is the new repair brief.
for name in ("asr_loading_adapter.py", "PORT-CONTRACTS.md", "TEST-PLAN.md", "REVIEW.md",
             "CALL-SITE-SPLICES.md", "SOURCE-BINDINGS.json", "WAVEFORM-STARTUP-CORRECTION.md",
             "HARNESS-PREPARATION.md", "adapter-addition.patch.txt"):
    write(name, (OLD / name).read_bytes())
resolver_raw = (ROOT / "_scratch/asr-trusted-manifest-resolver-proposal01/trusted_asr_resolver.py").read_bytes()
assert digest(resolver_raw) == "16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833"
write("review-inputs/trusted_asr_resolver.py", resolver_raw)

harness_before = (OLD / "qualify_adapter.py").read_bytes().decode("utf-8")
assert digest(harness_before.encode()) == "995199bc8b25129749f4558858cdb52d7d366ea602a4bb7e391a930344dbfa55"
nl = "\r\n" if "\r\n" in harness_before else "\n"
harness = harness_before
old = 'for owner, names in ((Path, ("stat", "lstat", "resolve", "exists", "is_file", "is_dir")),\n                     (os, ("stat", "lstat", "fstat", "scandir", "listdir"))):\n    for name in names:\n        setattr(owner, name, metadata_trap)'.replace("\n", nl)
new = 'METADATA_TRAPS = []\nfor owner, names in ((Path, ("stat", "lstat", "resolve", "exists", "is_file", "is_dir")),\n                     (os, ("stat", "lstat", "fstat", "scandir", "listdir"))):\n    for name in names:\n        setattr(owner, name, metadata_trap)\n        METADATA_TRAPS.append((owner, name, metadata_trap, ("Path" if owner is Path else "os") + "." + name))\nMETADATA_TRAPS = tuple(METADATA_TRAPS)'.replace("\n", nl)
assert harness.count(old) == 1
harness = harness.replace(old, new)
old = 'guard_valid = not DENIED and not heavy_loaded and real_approval_closed and real_functions_unchanged and adapter_globals_restored'
new = ('metadata_trap_mismatches = [label for owner, name, installed, label in METADATA_TRAPS\n'
       '                            if getattr(owner, name, None) is not installed]\n'
       'metadata_traps_installed = len(METADATA_TRAPS) == 11 and not metadata_trap_mismatches\n'
       'guard_valid = not DENIED and not heavy_loaded and real_approval_closed and real_functions_unchanged and adapter_globals_restored and metadata_traps_installed').replace("\n", nl)
assert harness.count(old) == 1
harness = harness.replace(old, new)
old = '          "adapter_globals_restored": adapter_globals_restored, "guard_valid": guard_valid,'
new = (old + '\n          "metadata_traps_installed": metadata_traps_installed, "metadata_trap_count": len(METADATA_TRAPS),\n'
       '          "metadata_trap_mismatches": metadata_trap_mismatches,').replace("\n", nl)
assert harness.count(old) == 1
harness = harness.replace(old, new)
write("qualify_adapter.py", harness)
harness_sha = digest(harness.encode())

runner_before = (OLD / "run_preflight01.ps1").read_bytes().decode("utf-8")
assert digest(runner_before.encode()) == "e019886953150a95e51e0d8d0f07eb2558a85f8e0214a2440524d9225d54301d"
runner = runner_before.replace("_scratch\\asr-production-adapter-proposal01", "_scratch\\asr-production-adapter-qualification-repair01")
runner = runner.replace("adapter-preflight01", "adapter-preflight02")
runner = runner.replace("run_preflight01.ps1", "run_preflight02.ps1").replace("QUALIFICATION01-PROTOCOL.md", "QUALIFICATION02-PROTOCOL.md")
runner = runner.replace("995199bc8b25129749f4558858cdb52d7d366ea602a4bb7e391a930344dbfa55", harness_sha)
old = "& $taskPython -I -S -B (Join-Path $taskRun 'qualify_adapter.py') 1> $taskStdout 2> $taskStderr\n$taskNativeExit=$LASTEXITCODE"
new = """# BEGIN EXACT NATIVE RECEIPT BLOCK
# Override any inherited native-error promotion at this invocation boundary.
$PSNativeCommandUseErrorActionPreference=$false
$LASTEXITCODE=$null
& $taskPython -I -S -B (Join-Path $taskRun 'qualify_adapter.py') 1> $taskStdout 2> $taskStderr
$taskNativeExit=$LASTEXITCODE
# Persist the completed-child outcome before any input or result postcheck.
$taskNativeReceipt=[ordered]@{schema='uoink.native-exit.v1';child_returned=$true;native_exit=$taskNativeExit}
$taskNativeBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskNativeReceipt | ConvertTo-Json -Compress))
$taskNativeStream=[IO.File]::Open((Join-Path $taskRun 'native-exit.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{
    $taskNativeStream.Write($taskNativeBytes,0,$taskNativeBytes.Length)
    $taskNativeStream.Flush($true)
}finally{$taskNativeStream.Dispose()}
# END EXACT NATIVE RECEIPT BLOCK"""
assert runner.count(old) == 1
runner = runner.replace(old, new)
old = '        $taskResult.adapter_globals_restored -ceq $true -and $taskResult.guard_valid -ceq $true -and'
new = old + '\n        $taskResult.metadata_traps_installed -ceq $true -and $taskResult.metadata_trap_count -eq 11 -and\n        @($taskResult.metadata_trap_mismatches).Count -eq 0 -and'
assert runner.count(old) == 1
runner = runner.replace(old, new)
write("run_preflight02.ps1", runner)
write("NATIVE-RECEIPT-BLOCK.ps1.txt", runner.split("# BEGIN EXACT NATIVE RECEIPT BLOCK\n", 1)[1].split("# END EXACT NATIVE RECEIPT BLOCK", 1)[0])

for name, before, after in (("harness-repair.patch.txt", harness_before, harness), ("runner-repair.patch.txt", runner_before, runner)):
    write(name, "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="original/" + name, tofile="repair01/" + name)))

before_tree, after_tree = ast.parse(harness_before), ast.parse(harness)
functions_before = [ast.dump(x, include_attributes=False) for x in ast.walk(before_tree) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]
functions_after = [ast.dump(x, include_attributes=False) for x in ast.walk(after_tree) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]
assert functions_before == functions_after
assertions_before = [ast.dump(x, include_attributes=False) for x in ast.walk(before_tree) if isinstance(x, ast.Assert)]
assertions_after = [ast.dump(x, include_attributes=False) for x in ast.walk(after_tree) if isinstance(x, ast.Assert)]
assert assertions_before == assertions_after
for name in ("asr_loading_adapter.py", "review-inputs/trusted_asr_resolver.py"):
    ast.parse((OUT / name).read_bytes())
json_write("STATIC-COMPARISON.json", {
    "schema": "uoink.asr-instrument-static-comparison.v1", "date": "2026-09-13",
    "all_function_asts_identical": True, "function_nodes": len(functions_before),
    "all_assertion_asts_identical": True, "assertion_nodes": len(assertions_before),
    "planned_case_count_unchanged": 58, "runtime_cases_executed": 0,
    "original_harness_sha256": digest(harness_before.encode()), "repaired_harness_sha256": harness_sha,
    "original_runner_sha256": digest(runner_before.encode()), "repaired_runner_sha256": digest(runner.encode()),
    "adapter_sha256": digest((OUT / "asr_loading_adapter.py").read_bytes()),
    "resolver_sha256": digest(resolver_raw), "source_preparation_only": True})
write(".gitattributes", "* -text\n")
write("prepare_asr_qualification_repair01.py", Path(__file__).read_bytes())
print(json.dumps({"prepared": str(OUT), "harness_sha256": harness_sha,
                  "runner_sha256": digest(runner.encode()), "function_nodes_unchanged": len(functions_before),
                  "assertion_nodes_unchanged": len(assertions_before), "executed_cases": 0}))

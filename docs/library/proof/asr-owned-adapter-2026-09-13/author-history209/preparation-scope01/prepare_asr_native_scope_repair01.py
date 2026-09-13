"""Preserve source/failed text receipts and prepare candidates. No generated execution."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
PRIOR = BASE / "_scratch/asr-production-adapter-qualification-repair01"
SUBSET = BASE / "_scratch/asr-production-adapter-instrument-check01"
OUT = BASE / "_scratch/asr-native-exit-scope-repair01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(name, raw):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw if isinstance(raw, bytes) else raw.encode())


def write_json(name, value):
    write(name, json.dumps(value, indent=2) + "\n")


for label, folder, expected in (
    ("repair01", PRIOR, "34e4a40216547273f5813fa55dbf7affbc369173c68fd8e4e3e5c7b442a2817e"),
    ("instrument01", SUBSET, "4e52a3ab54dffe52d45c6ca96fad9d23d1d1ee832eca93b1cb98f5492c56bcde")):
    raw = (folder / "SHA256.json").read_bytes()
    assert sha(raw) == expected
    seal = json.loads(raw)
    for row in seal["files"]:
        content = (folder / row["path"]).read_bytes()
        assert len(content) == row["bytes"] and sha(content) == row["sha256"], row["path"]
    write("prior-seals/" + label + "-SHA256.json", raw)
write("failure01/ACTUAL-TOOL-MISSING01.json", (SUBSET / "ACTUAL-TOOL-MISSING01.json").read_bytes())
write("failure01/FAILED-OUTCOME01.md", (SUBSET / "FAILED-OUTCOME01.md").read_bytes())
failure_names = ("native-exit.json", "qualify_adapter.py", "setup.json", "stderr.log", "stdout.json")
for name in failure_names:
    write("failure01/missing01/" + name, (SUBSET / "runs/instrument01/missing01" / name).read_bytes())
failed_native = json.loads((OUT / "failure01/missing01/native-exit.json").read_bytes())
assert failed_native["child_returned"] is True and failed_native["native_exit"] is None
for name in ("run_preflight02.ps1", "qualify_adapter.py", "NATIVE-RECEIPT-BLOCK.ps1.txt"):
    write("before/" + name, (PRIOR / name).read_bytes())
for name in ("wrapper-missing01.ps1", "wrapper-success01.ps1"):
    write("before/" + name, (SUBSET / name).read_bytes())

runner_before = (PRIOR / "run_preflight02.ps1").read_bytes().decode()
old_block = runner_before.split("# BEGIN EXACT NATIVE RECEIPT BLOCK\n", 1)[1].split("# END EXACT NATIVE RECEIPT BLOCK", 1)[0]
new_block = old_block.replace("$LASTEXITCODE=$null", "$global:LASTEXITCODE=$null").replace("$taskNativeExit=$LASTEXITCODE", "$taskNativeExit=$global:LASTEXITCODE")
assert new_block != old_block
new_block += "if($taskNativeExit -isnot [int]){throw 'Returned native exit was not captured as an integer'}\n"
runner = runner_before.replace(old_block, new_block)
runner = runner.replace("_scratch\\asr-production-adapter-qualification-repair01", "_scratch\\asr-native-exit-scope-repair01\\candidate")
runner = runner.replace("adapter-preflight02", "adapter-preflight03").replace("run_preflight02.ps1", "run_preflight03.ps1").replace("QUALIFICATION02-PROTOCOL.md", "QUALIFICATION03-PROTOCOL.md")
write("candidate/run_preflight03.ps1", runner)
write("candidate/NATIVE-RECEIPT-BLOCK.ps1.txt", new_block)
for name in ("asr_loading_adapter.py", "qualify_adapter.py", "PORT-CONTRACTS.md", "TEST-PLAN.md", "REVIEW.md",
             "CALL-SITE-SPLICES.md", "SOURCE-BINDINGS.json", "WAVEFORM-STARTUP-CORRECTION.md",
             "HARNESS-PREPARATION.md", "adapter-addition.patch.txt"):
    write("candidate/" + name, (PRIOR / name).read_bytes())
write("candidate/BRIEF.md", (OUT / "BRIEF.md").read_bytes())
for name in ("child-one.py", "child-zero.py", "qualify_guards.py", "trap-installation.py.txt", "trap-final.py.txt"):
    write("instrument02/" + name, (SUBSET / name).read_bytes())
for old_name, new_name in (("wrapper-missing01.ps1", "wrapper-missing02.ps1"), ("wrapper-success01.ps1", "wrapper-success02.ps1")):
    old = (SUBSET / old_name).read_bytes().decode()
    assert old.count(old_block) == 1
    new = old.replace(old_block, new_block).replace("runs\\instrument01\\", "runs\\instrument02\\").replace("missing01", "missing02").replace("success01", "success02")
    write("instrument02/" + new_name, new)
    write(new_name + ".patch.txt", "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile="before/" + old_name, tofile="instrument02/" + new_name)))
binding_before = json.loads((SUBSET / "PREPARATION-BINDINGS.json").read_bytes())
binding_after = dict(binding_before)
binding_after.update({"previous_subset_failed": True, "candidate_runner_sha256": sha(runner.encode()),
                      "native_block_sha256": sha(new_block.encode()), "diagnostic_executed": False,
                      "runner_sha256": sha(runner.encode())})
write_json("instrument02/PREPARATION-BINDINGS.json", binding_after)
write("runner-scope-repair.patch.txt", "".join(difflib.unified_diff(runner_before.splitlines(True), runner.splitlines(True),
      fromfile="before/run_preflight02.ps1", tofile="candidate/run_preflight03.ps1")))
write("native-block-scope-repair.patch.txt", "".join(difflib.unified_diff(old_block.splitlines(True), new_block.splitlines(True),
      fromfile="before/native-block.ps1.txt", tofile="candidate/native-block.ps1.txt")))
write("diagnostic-child-one.py", (SUBSET / "child-one.py").read_bytes())
assert (OUT / "candidate/qualify_adapter.py").read_bytes() == (PRIOR / "qualify_adapter.py").read_bytes()
assert (OUT / "candidate/asr_loading_adapter.py").read_bytes() == (PRIOR / "asr_loading_adapter.py").read_bytes()
for name in ("candidate/qualify_adapter.py", "candidate/asr_loading_adapter.py", "instrument02/qualify_guards.py",
             "instrument02/child-one.py", "instrument02/child-zero.py", "diagnostic-child-one.py"):
    ast.parse((OUT / name).read_bytes())
write_json("PREPARATION-BINDINGS.json", {
    "date": "2026-09-13", "prior_repair_payloads_verified": 53, "prior_subset_payloads_verified": 26,
    "failed_native_value": None, "failed_actual_tool_exit": 1, "actual_tool_chunk": "d3d1b0",
    "other_tool_outcomes_source": "Parent-reported FAILED-OUTCOME01.md; no invented raw objects",
    "original_native_block_sha256": sha(old_block.encode()), "candidate_native_block_sha256": sha(new_block.encode()),
    "candidate_runner_sha256": sha(runner.encode()), "unchanged_harness_sha256": sha((OUT / "candidate/qualify_adapter.py").read_bytes()),
    "unchanged_adapter_sha256": sha((OUT / "candidate/asr_loading_adapter.py").read_bytes()),
    "planned_scope_observations": 4, "planned_repaired_wrapper_outcomes": 2, "planned_guard_cases": 4,
    "diagnostic_or_qualification_executed": False, "candidate_capture_mechanism": "Unproved until admitted diagnostic and wrapper outcomes",
    "all_existing_function_and_assertion_bytes_unchanged": True})
write(".gitattributes", "* -text\n")
write("prepare_asr_native_scope_repair01.py", Path(__file__).read_bytes())
print(json.dumps({"candidate_runner_sha256": sha(runner.encode()), "candidate_block_sha256": sha(new_block.encode()),
                  "original_seals_verified": [53, 26], "diagnostic_or_qualification_executed": False}))

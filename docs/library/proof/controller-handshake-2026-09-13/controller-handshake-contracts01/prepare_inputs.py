"""Data-only source/case binding; never import or execute the proposal."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
import re

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE = BASE / "_scratch/controller-handshake-contracts01"
OLD = BASE / "_scratch/asr-worker-namespace-proposal01"
PINNED = {
    "snapshot_lifecycle.py": "a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd",
    "owned_generation_protocol.py": "78c395da77ff5a0dd660a27a7ea47d6e52061fc016937aa7046556f1fa026507",
    "qualify_namespace.py": "ce4b149a4b5920c370c45d0ea31bf96ec65fb1ddf714cde63ae012d4298125d9",
    "run_namespace01.ps1": "9bf9e632508df3e3d90a8a8d070b43d3efbcf5ccc58f155d2a169a5576f1fe4f",
}


def read(path):
    with path.open("rb") as stream:
        raw = stream.read(1048577)
    assert len(raw) <= 1048576
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, raw):
    with (HERE / name).open("xb") as stream:
        stream.write(raw if isinstance(raw, bytes) else raw.encode())


original = {name: read(OLD / name) for name in PINNED}
assert all(sha(raw) == PINNED[name] for name, raw in original.items())
for name in ("snapshot_lifecycle.py", "owned_generation_protocol.py"):
    save(name, original[name])
cases_raw = read(HERE / "handshake_cases.py")
tree = ast.parse(cases_raw)
cases = tuple(ast.literal_eval(node.decorator_list[0].args[0]) for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.decorator_list
              and isinstance(node.decorator_list[0], ast.Call)
              and isinstance(node.decorator_list[0].func, ast.Name)
              and node.decorator_list[0].func.id == "case")
assert len(cases) == len(set(cases)) == 8
modules = ("snapshot_lifecycle", "owned_generation_protocol")
inputs = tuple(name + ".py" for name in modules) + ("handshake_cases.py", "qualify_handshake.py")
old = original["qualify_namespace.py"].decode()
harness = old
old_modules = "('snapshot_lifecycle', 'owned_generation_protocol', 'pinned_buffer_namespace', 'win32_worker_connection', 'win32_private_pipe')"
assert harness.count(old_modules) == 2
harness = harness.replace(old_modules, repr(modules))
lines = harness.splitlines(keepends=True)
for index, line in enumerate(lines):
    if line.startswith("INPUTS = "):
        lines[index] = "INPUTS = " + repr(inputs) + "\n"
    elif line.startswith("EXPECTED_CASES = "):
        lines[index] = "EXPECTED_CASES = " + repr(cases) + "\n"
harness = "".join(lines).replace("contract_cases.py", "handshake_cases.py")
harness = harness.replace("assert len(CASES) == 54", "assert len(CASES) == 8")
harness = harness.replace("uoink.worker-namespace-synthetic.v1", "uoink.controller-handshake-synthetic.v1")
harness = harness.replace("Generated-memory fake API seams only; no kernel, model, factory or native-loader qualification",
                          "Eight in-memory lifecycle-owned ControllerHandshake cases only; no kernel, model, factory or native-loader qualification")
ast.parse(harness)
save("qualify_handshake.py", harness)
save("harness-setup.diff", "".join(difflib.unified_diff(old.splitlines(True), harness.splitlines(True),
    fromfile="qualified-namespace/qualify_namespace.py", tofile="proposed-handshake/qualify_handshake.py")))
save("EXPECTED-CASES.json", json.dumps({"schema": "uoink.handshake-expected-cases.v1", "count": 8,
                                      "ordered_cases": cases}, indent=2) + "\n")
hashes = {name: sha(read(HERE / name)) for name in inputs}
launcher_old = original["run_namespace01.ps1"].decode()
launcher = launcher_old.replace(str(OLD), str(HERE)).replace("nsp01", "hs01")
launcher = launcher.replace("namespace-fake-api-54-only", "controller-handshake-fake-port-8-only")
launcher = launcher.replace("run_namespace01.ps1", "run_handshake01.ps1")
launcher = launcher.replace("qualify_namespace.py", "qualify_handshake.py")
launcher = launcher.replace("uoink.namespace-expected-cases.v1", "uoink.handshake-expected-cases.v1")
launcher = launcher.replace("uoink.worker-namespace-synthetic.v1", "uoink.controller-handshake-synthetic.v1")
start = launcher.index("$taskExpected=@{\n")
end = launcher.index("\n$taskRecords=@()", start)
members = inputs + ("EXPECTED-CASES.json", "run_handshake01.ps1")
launcher = launcher[:start] + "$taskExpected=@{\n" + "".join("    '" + name + "'='" + digest + "'\n" for name, digest in hashes.items()) + "}\n$taskInputNames=@(" + ",".join("'" + name + "'" for name in members) + ")" + launcher[end:]
# Restrict numeric adaptation to the explicit inherited 54-case expectations.
assert len(re.findall(r"(?<![A-Za-z0-9])54(?![A-Za-z0-9])", launcher)) == 10
launcher = re.sub(r"(?<![A-Za-z0-9])54(?![A-Za-z0-9])", "8", launcher)
save("run_handshake01.ps1", launcher)
save("launcher-setup.diff", "".join(difflib.unified_diff(launcher_old.splitlines(True), launcher.splitlines(True),
    fromfile="qualified-namespace/run_namespace01.ps1", tofile="proposed-handshake/run_handshake01.ps1")))
all_hashes = {name: sha(read(HERE / name)) for name in members}
save("INPUTS.json", json.dumps({"schema": "uoink.handshake-inputs.v1", "input_sha256": all_hashes,
                               "retained_namespace_inputs": PINNED, "candidate_executed": False}, indent=2) + "\n")
save("ADMISSION-TEMPLATE.json", json.dumps({"root_reviewed": False, "scope": "controller-handshake-fake-port-8-only",
    "label": "hs01", "input_sha256": all_hashes, "expected_cases": cases}, indent=2) + "\n")
print(json.dumps({"prepared_cases": len(cases), "inputs": all_hashes, "candidate_executed": False}))

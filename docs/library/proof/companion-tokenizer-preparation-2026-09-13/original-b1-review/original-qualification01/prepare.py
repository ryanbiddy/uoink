"""Copy the immutable proposal and extract only its six synthetic B contracts."""
import ast
import hashlib
import json
from pathlib import Path
import re

out = Path(__file__).resolve().parent
original = out.parent / "runtime-asset-guard-proposal01"
seal_bytes = (original / "SHA256.json").read_bytes()
assert hashlib.sha256(seal_bytes).hexdigest() == "a32bb76d68d7939905b6538921f8915a0d78a47ab2e0c3f3c661c49036940237"
seal = json.loads(seal_bytes)
assert seal["payload_count"] == len(seal["payloads"]) == 24
child = out / "original-proposal01"
child.mkdir(exist_ok=False)
for row in seal["payloads"]:
    source = original / row["file"]
    data = source.read_bytes()
    assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"]
    destination = child / row["file"]
    assert destination.resolve().is_relative_to(child.resolve())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
(child / "SHA256.json").write_bytes(seal_bytes)

test_source = (child / "tests-proposed.py.txt").read_text(encoding="utf-8")
tree = ast.parse(test_source)
nodes = [node for node in tree.body if (
    isinstance(node, ast.FunctionDef) and node.name in {"blocked", "whisper_constructor_prefix"}
) or (isinstance(node, ast.ClassDef) and node.name == "CompanionConstructorContracts")]
assert len(nodes) == 3
header = '''"""Six reviewed B assertions; loaded only by the guarded stdlib harness."""
from __future__ import annotations
import ast
import copy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

'''
extracted = header + "\n\n\n".join(ast.get_source_segment(test_source, node) for node in nodes) + "\n"
test_path = out / "constructor-contracts.py.txt"
test_path.write_text(extracted, encoding="utf-8", newline="\n")
new_tree = ast.parse(extracted)
for node in nodes:
    match = next(item for item in new_tree.body if type(item) is type(node) and item.name == node.name)
    assert ast.dump(node, include_attributes=False) == ast.dump(match, include_attributes=False)
cls = next(node for node in nodes if isinstance(node, ast.ClassDef))
test_names = [node.name for node in cls.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
assert len(test_names) == 6 and "ProductGuardContracts" not in extracted

baseline = child / "inputs/installer/staging/python/Lib/site-packages/faster_whisper/transcribe.py"
candidate = child / "companion-B.py.txt"
patch = child / "companion-B.patch.txt"
old = baseline.read_text(encoding="utf-8")
new = candidate.read_text(encoding="utf-8")
lines, result, cursor = old.splitlines(keepends=True), [], 0
for line in patch.read_text(encoding="utf-8").splitlines(keepends=True)[2:]:
    hunk = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", line)
    if hunk:
        start = int(hunk[1]) - 1
        assert cursor <= start
        result.extend(lines[cursor:start])
        cursor = start
    elif line.startswith(" "):
        assert lines[cursor] == line[1:]
        result.append(line[1:]); cursor += 1
    elif line.startswith("-"):
        assert lines[cursor] == line[1:]
        cursor += 1
    elif line.startswith("+"):
        result.append(line[1:])
    else:
        raise AssertionError("unexpected patch shape")
result.extend(lines[cursor:])
assert "".join(result) == new
ast.parse(old); ast.parse(new)

mapping = {
    "upstream_package_recorded_version": "faster-whisper 1.2.1",
    "input_provenance": "Retained installed-staging source bound by the original 24-payload proposal; no fresh upstream fetch or full wheel identity verification.",
    "input_relative_path": baseline.relative_to(out).as_posix(),
    "input_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
    "derivative_relative_path": candidate.relative_to(out).as_posix(),
    "derivative_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
    "patch_relative_path": patch.relative_to(out).as_posix(),
    "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
    "upstream_target_member": "faster_whisper/transcribe.py",
    "derivative_version": None, "package_built_or_applied": False,
    "text_diff_reconstructs_candidate": True,
    "test_protocol_sha256": hashlib.sha256((child / "tests-proposed.py.txt").read_bytes()).hexdigest(),
    "extracted_test_sha256": hashlib.sha256(test_path.read_bytes()).hexdigest(),
    "unchanged_ast_test_names": test_names,
    "entire_constructor_class_ast_unchanged": True,
    "helper_asts_unchanged": [node.name for node in nodes if isinstance(node, ast.FunctionDef)],
    "setup_differences": [
        "Removed product-A class/helper and CLI block; no companion assertion changed.",
        "Harness injects FW_SOURCE for one named text input and pins tempfile.tempdir to that run's synthetic directory.",
        "Used only needed stdlib imports and a scope docstring.",
    ],
    "prepared_before_test_execution": True,
}
(out / "source-mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"original_payloads_verified": 24, "unchanged_companion_tests": 6,
                  "text_diff_reconstructed": True, "test_execution": False}))

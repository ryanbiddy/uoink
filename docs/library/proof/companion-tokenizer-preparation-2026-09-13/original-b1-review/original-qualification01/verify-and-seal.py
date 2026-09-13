"""Verify inert source identities and existing receipts; do not rerun cases."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

out = Path(__file__).resolve().parent
original = out.parent / "runtime-asset-guard-proposal01"
child = out / "original-proposal01"
seal_hash = "a32bb76d68d7939905b6538921f8915a0d78a47ab2e0c3f3c661c49036940237"
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert not (out / "SHA256.json").exists(), "Preserve the existing outer seal"
for root in (original, child):
    assert sha(root / "SHA256.json") == seal_hash
    seal = json.loads((root / "SHA256.json").read_bytes())
    assert seal["payload_count"] == len(seal["payloads"]) == 24
    for row in seal["payloads"]:
        path = root / row["file"]
        assert path.resolve().is_relative_to(root.resolve())
        assert path.stat().st_size == row["bytes"] and sha(path) == row["sha256"]

mapping = json.loads((out / "source-mapping.json").read_text(encoding="utf-8"))
for name in ("input", "derivative", "patch"):
    assert sha(out / mapping[name + "_relative_path"]) == mapping[name + "_sha256"]
old = (out / mapping["input_relative_path"]).read_text(encoding="utf-8")
new = (out / mapping["derivative_relative_path"]).read_text(encoding="utf-8")
patch = (out / mapping["patch_relative_path"]).read_text(encoding="utf-8")
lines, result, cursor = old.splitlines(keepends=True), [], 0
for line in patch.splitlines(keepends=True)[2:]:
    hunk = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", line)
    if hunk:
        start = int(hunk[1]) - 1
        assert cursor <= start
        result.extend(lines[cursor:start]); cursor = start
    elif line.startswith(" "):
        assert lines[cursor] == line[1:]
        result.append(line[1:]); cursor += 1
    elif line.startswith("-"):
        assert lines[cursor] == line[1:]
        cursor += 1
    elif line.startswith("+"):
        result.append(line[1:])
    else:
        raise AssertionError("Unexpected retained patch shape")
result.extend(lines[cursor:])
assert "".join(result) == new

def selected_init(text):
    tree = ast.parse(text)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "WhisperModel")
    init = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "__init__")
    stop = next(index for index, node in enumerate(init.body) if any(
        isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name)
        and item.value.id == "self" and item.attr == "hf_tokenizer"
        and isinstance(item.ctx, ast.Store) for item in ast.walk(node)))
    return init, stop

old_init, old_stop = selected_init(old)
new_init, new_stop = selected_init(new)
dump = lambda node: ast.dump(node, include_attributes=False)
assert dump(old_init.args) == dump(new_init.args)
assert [dump(node) for node in old_init.body[old_stop + 1:]] == [dump(node) for node in new_init.body[new_stop + 1:]]
def model_assignment(init):
    return next(node for node in init.body if isinstance(node, ast.Assign) and any(
        isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name)
        and item.value.id == "self" and item.attr == "model" for item in node.targets))
assert dump(model_assignment(old_init)) == dump(model_assignment(new_init))

protocol = ast.parse((child / "tests-proposed.py.txt").read_text(encoding="utf-8"))
extracted = ast.parse((out / "constructor-contracts.py.txt").read_text(encoding="utf-8"))
for name in ("blocked", "whisper_constructor_prefix", "CompanionConstructorContracts"):
    left = next(node for node in protocol.body if getattr(node, "name", None) == name)
    right = next(node for node in extracted.body if getattr(node, "name", None) == name)
    assert dump(left) == dump(right)
assert sha(out / "constructor-contracts.py.txt") == mapping["extracted_test_sha256"]

receipts = []
for label, expected in (("baseline01", (1, 5, 1)), ("candidate01", (6, 0, 0))):
    receipt = json.loads((out / "runs" / label / "result.json").read_text(encoding="utf-8"))
    launch_root = out / ("launch-" + label)
    launch = json.loads((launch_root / "result.json").read_text(encoding="utf-8"))
    plan = json.loads((launch_root / "plan.json").read_text(encoding="utf-8"))
    assert receipt["tests_run"] == len(receipt["observations"]) == 6
    assert (receipt["passed"], receipt["failed"], receipt["exit"]) == expected
    assert receipt["errors"] == receipt["skipped"] == 0
    assert receipt["test_protocol_sha256"] == mapping["extracted_test_sha256"]
    assert receipt["flags"] == {"isolated": 1, "no_site": 1, "dont_write_bytecode": 1}
    assert receipt["guard"] == {"preloaded_heavy": [], "postloaded_heavy": [], "blocked_imports": [],
        "blocked_audit_events": [], "finder_installed_at_finish": True, "valid": True}
    assert not receipt["whole_dependency_module_executed"] and not receipt["real_tokenizer_or_model_executed"]
    assert launch["exit"] == expected[2] and launch["inputs_unchanged"]
    for path, expected_hash in plan["input_hashes"].items():
        assert sha(Path(path)) == expected_hash
    assert not any(path.is_file() for path in (out / "runs" / label / "temporary").rglob("*"))
    receipts.append(receipt)
assert [row["id"] for row in receipts[0]["observations"]] == [row["id"] for row in receipts[1]["observations"]]
assert (out / ".gitattributes").read_bytes() == b"* -text\n"

checks = {
    "verified_utc": datetime.now(timezone.utc).isoformat(),
    "original_external_and_copied_seal_sha256": seal_hash,
    "original_payloads_verified_in_each_root": 24,
    "normalized_text_patch_reconstruction": True,
    "constructor_signature_unchanged": True,
    "model_constructor_assignment_ast_unchanged": True,
    "later_constructor_body_ast_unchanged": True,
    "selected_prefix_lines": {
        "baseline": [old_init.lineno, old_init.body[old_stop].end_lineno],
        "candidate": [new_init.lineno, new_init.body[new_stop].end_lineno],
    },
    "original_companion_class_and_two_helper_asts_unchanged": True,
    "identical_six_case_ids": True,
    "baseline": {key: receipts[0][key] for key in ("tests_run", "passed", "failed", "errors", "skipped", "exit")},
    "candidate": {key: receipts[1][key] for key in ("tests_run", "passed", "failed", "errors", "skipped", "exit")},
    "all_launcher_input_hashes_unchanged": True,
    "both_guards_retained_and_no_violations": True,
    "synthetic_fixture_directories_empty_at_seal": True,
    "test_rerun_or_dependency_execution_by_this_verifier": False,
    "scope": "Inert source and existing synthetic receipts only; no package or model-runtime acceptance.",
}
(out / "static-checks.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8", newline="\n")
payloads = []
for path in sorted(out.rglob("*")):
    if path.is_file():
        payloads.append({"file": path.relative_to(out).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)})
manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "payload_count": len(payloads), "payloads": payloads}
(out / "SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"payload_count": len(payloads), "manifest_sha256": sha(out / "SHA256.json"),
    "baseline": checks["baseline"], "candidate": checks["candidate"], "original_seal_verified": True}))

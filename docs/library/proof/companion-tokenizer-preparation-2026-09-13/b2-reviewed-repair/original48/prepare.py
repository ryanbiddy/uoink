"""Prepare B2 source text and guarded synthetic protocol; do not execute it."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
scratch = out.parent
root = scratch.parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
inputs = out / "inputs"
inputs.mkdir(exist_ok=False)
seals = [
    ("runtime-asset-guard-proposal01", 24, "a32bb76d68d7939905b6538921f8915a0d78a47ab2e0c3f3c661c49036940237"),
    ("companion-b-static-qualification01", 46, "28d2d34c530e80716964b475244551340222dc7b8b2f39f77b8be9c490117fc5"),
    ("companion-b-combined-review01", 67, "05620906f1d09b8afce3f7065798495c3e7f35666a17aa2948a992500d9530e9"),
    ("companion-b-distribution-plan01", 52, "765f515351a3a3e9f180adf63476137c90c8220acc2a6bf7f290dcce9be60011"),
]
bindings = []
def copy(source, destination):
    data = source.read_bytes()
    target = inputs / destination
    assert target.resolve().is_relative_to(inputs.resolve()) and not target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    bindings.append({"source": str(source), "file": target.relative_to(out).as_posix(), "bytes": len(data), "sha256": sha(data)})
    return data

for name, count, expected in seals:
    old = scratch / name
    raw = (old / "SHA256.json").read_bytes()
    assert sha(raw) == expected
    manifest = json.loads(raw)
    assert manifest["payload_count"] == len(manifest["payloads"]) == count
    for row in manifest["payloads"]:
        data = (old / row["file"]).read_bytes()
        assert len(data) == row["bytes"] and sha(data) == row["sha256"]
    copy(old / "SHA256.json", name + "-SHA256.json")

old_proposal = scratch / "runtime-asset-guard-proposal01"
b1 = copy(old_proposal / "companion-B.py.txt", "B1.py.txt")
copy(old_proposal / "companion-B.patch.txt", "B1.patch.txt")
upstream = copy(old_proposal / "inputs/installer/staging/python/Lib/site-packages/faster_whisper/transcribe.py", "upstream-transcribe.py.txt")
original = scratch / "companion-b-static-qualification01"
protocol = copy(original / "constructor-contracts.py.txt", "original-six-contracts.py.txt")
harness = copy(original / "harness.py", "original-harness.py.txt").decode()
launcher = copy(original / "launch.py", "original-launch.py.txt").decode()
copy(Path(r"C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\131e52c7-b6e\gemini\docs\library\COUNCIL-ASSET-GUARD-REVIEW-2026-09-13.md"), "COUNCIL-REVIEW.md")
for name in ("PLAN.md", "proposed-member-manifest.json", "proposed-distribution-text/UOINK-LOCALASSETS-NOTICE.txt", "proposed-distribution-text/RECORD.csv.txt"):
    copy(scratch / "companion-b-distribution-plan01" / name, "B1-distribution-plan/" + name)

needle = b"        if tokenizer_bytes:\r\n"
assert b1.count(needle) == 1
b2 = b1.replace(needle, b"        if tokenizer_bytes is not None:\r\n")
(out / "B2.py.txt").write_bytes(b2)
for name, before, old_label in (("B1-to-B2.patch.txt", b1, "a/B1/faster_whisper/transcribe.py"),
                                ("upstream-to-B2.patch.txt", upstream, "a/faster_whisper/transcribe.py")):
    diff = "".join(difflib.unified_diff(before.decode().splitlines(keepends=True), b2.decode().splitlines(keepends=True),
                                      fromfile=old_label, tofile="b/faster_whisper/transcribe.py"))
    (out / name).write_bytes(diff.encode())
new_contracts = (out / "new-empty-buffer-contracts.py.txt").read_bytes()
combined = protocol + new_contracts
(out / "constructor-contracts.py.txt").write_bytes(combined)
before_tree, after_tree = ast.parse(protocol), ast.parse(combined)
for before in before_tree.body:
    if isinstance(before, (ast.FunctionDef, ast.ClassDef)):
        after = next(node for node in after_tree.body if getattr(node, "name", None) == before.name)
        assert ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False)
assert len([node for cls in after_tree.body if isinstance(cls, ast.ClassDef) for node in cls.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]) == 10
ast.parse(b2)

harness = harness.replace('choices=("baseline01", "candidate01")', 'choices=("b1-boundary01", "b2-candidate01")')
harness = harness.replace('a.label == "baseline01"', 'a.label == "b1-boundary01"')
harness = harness.replace('suite = unittest.defaultTestLoader.loadTestsFromTestCase(namespace["CompanionConstructorContracts"])\nassert suite.countTestCases() == 6',
    'suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(namespace[name])\n    for name in ("CompanionConstructorContracts", "EmptyBufferContracts"))\nassert suite.countTestCases() == 10')
harness = harness.replace('"status": "passed"}', '"status": "passed", "boundary": getattr(test, "boundary_observation", None)}')
harness = harness.replace('"trace": self._exc_info_to_string(error, test)}', '"trace": self._exc_info_to_string(error, test), "boundary": getattr(test, "boundary_observation", None)}')
launcher = launcher.replace('choices=("baseline01", "candidate01")', 'choices=("b1-boundary01", "b2-candidate01")')
launcher = launcher.replace('a.label == "candidate01"', 'a.label == "b2-candidate01"')
launcher = launcher.replace('BASELINE-REPAIR-REASON-2026-09-13.md', 'B1-BOUNDARY-REPAIR-REASON-2026-09-13.md')
(out / "harness.py").write_text(harness, encoding="utf-8", newline="\n")
(out / "launch.py").write_text(launcher, encoding="utf-8", newline="\n")
mapping = {"input_relative_path": "inputs/B1.py.txt", "input_sha256": sha(b1),
    "derivative_relative_path": "B2.py.txt", "derivative_sha256": sha(b2),
    "extracted_test_sha256": sha(combined)}
(out / "source-mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8", newline="\n")
receipt = {"prepared_utc": datetime.now(timezone.utc).isoformat(), "bindings": bindings,
    "prior_seals_verified": [{"name": name, "count": count, "sha256": expected} for name, count, expected in seals],
    "original_six_assertions_and_helpers_ast_unchanged": True, "new_cases": 4,
    "setup_differences": ["Append four cases with their own rejecting fake buffer parser; original six setup/helper unchanged.",
                          "Two fresh labels map exact B1 and one-line B2 text; suite combines both classes as ten top-level cases.",
                          "Result captures new cases' boundary events, exception and model/tokenizer attribute observations.",
                          "Launcher candidate arm requires new dated repair reason; scrubber/offline flags unchanged.",
                          "Reviewed import finder/audit guards and AST-prefix boundary unchanged."],
    "source_mapping": mapping, "test_execution": False}
(out / "preparation.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"prepared_cases": 10, "old_six_preserved": True, "B2_sha256": sha(b2), "tests_executed": False}))

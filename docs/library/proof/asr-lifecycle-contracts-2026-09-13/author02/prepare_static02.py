"""Read/compare source as inert AST/text; execute no candidate method or test."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

root = Path(__file__).parent
old_root = root.with_name("asr-windows-lifecycle-proposal01")
old_raw = (old_root / "qualify_lifecycle.py").read_bytes()
new_raw = (root / "qualify_lifecycle.py").read_bytes()
old, new = ast.parse(old_raw), ast.parse(new_raw)
old_functions = [ast.dump(node, include_attributes=False) for node in ast.walk(old) if isinstance(node, ast.FunctionDef)]
new_functions = [ast.dump(node, include_attributes=False) for node in ast.walk(new) if isinstance(node, ast.FunctionDef)]
assert all(body in new_functions for body in old_functions)
old_cases = next(ast.literal_eval(node.value) for node in old.body if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "EXPECTED_CASES" for t in node.targets))
new_cases = next(ast.literal_eval(node.value) for node in new.body if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "EXPECTED_CASES" for t in node.targets))
assert old_cases == new_cases and len(old_cases) == 46
assert (old_root / "snapshot_lifecycle.py").read_bytes() == (root / "snapshot_lifecycle.py").read_bytes()
assert (old_root / "EXPECTED-CASES.json").read_bytes() == (root / "EXPECTED-CASES.json").read_bytes()
for name in ("qualify_lifecycle.py", "run_lifecycle02.ps1"):
    old_name = "run_lifecycle01.ps1" if name.endswith(".ps1") else name
    original = (old_root / old_name).read_text(encoding="utf-8").splitlines(True)
    revised = (root / name).read_text(encoding="utf-8").splitlines(True)
    patch = "".join(difflib.unified_diff(original, revised, fromfile="proposal01/" + old_name, tofile="proposal02/" + name))
    (root / (name + ".diff.txt")).write_text(patch, encoding="utf-8")
report = {"schema": "uoink.lifecycle-guard-static-preservation.v1", "executed_candidate_cases": 0,
          "all_original_functions_preserved": True, "original_function_count": len(old_functions),
          "new_function_count": len(new_functions), "exact_case_sequence_preserved": True, "case_count": 46,
          "lifecycle_source_identical": True, "expected_cases_file_identical": True,
          "old_harness_sha256": hashlib.sha256(old_raw).hexdigest(), "new_harness_sha256": hashlib.sha256(new_raw).hexdigest()}
(root / "STATIC-PRESERVATION.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))

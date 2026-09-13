"""Data-only AST/hash/diff preparation; never executes candidate source."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

root = Path(__file__).parent
before = root / "drafts/qualify_lifecycle.before-guard04.py"
after = root / "qualify_lifecycle.py"
old = ast.parse(before.read_bytes())
new = ast.parse(after.read_bytes())
expected = next(ast.literal_eval(node.value) for node in new.body
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "EXPECTED_CASES" for t in node.targets))
assert len(expected) == len(set(expected)) == 46
old_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(old) if isinstance(n, ast.FunctionDef)}
new_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(new) if isinstance(n, ast.FunctionDef)}
# Only the audit guard is an intentionally changed existing function. New
# wrappers/scenarios are additions. All original fake ports/assertions remain.
changed = [name for name, body in old_functions.items() if new_functions.get(name) != body]
assert changed == ["audit"], changed
for path in (root / "snapshot_lifecycle.py", after):
    ast.parse(path.read_bytes())
out = {"schema": "uoink.lifecycle-expected-cases.v1", "count": 46, "ordered_cases": expected}
(root / "EXPECTED-CASES.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
report = {"schema": "uoink.lifecycle-static-preservation.v1", "executed_candidate_cases": 0,
          "original_function_count": len(old_functions), "changed_existing_functions": changed,
          "preserved_behavior_function_count": len(old_functions) - 1,
          "original_case_count": 44, "added_case_count": 2, "literal_expected_case_count": len(expected),
          "inputs": {str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (before, after, root / "snapshot_lifecycle.py")}}
(root / "STATIC-PRESERVATION04.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
for current, previous in (("snapshot_lifecycle.py", "snapshot_lifecycle.before-publication04.py"),
                          ("qualify_lifecycle.py", "qualify_lifecycle.before-guard04.py")):
    a = (root / "drafts" / previous).read_text(encoding="utf-8").splitlines(True)
    b = (root / current).read_text(encoding="utf-8").splitlines(True)
    patch = "".join(difflib.unified_diff(a, b, fromfile="drafts/" + previous, tofile=current))
    (root / (current + ".repair04.diff.txt")).write_text(patch, encoding="utf-8")
print(json.dumps(report, indent=2))

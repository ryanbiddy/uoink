"""Static AST and byte audit; imports no product module and executes no tests."""
import ast
import hashlib
import json
from pathlib import Path


root = Path(__file__).resolve().parents[2]
archive = root / "_scratch" / "astra-authority-repair03"
files = [
    "test_library_mirror_process_authority.py",
    "test_mirror_process_identity_boundaries.py",
    "test_mirror_process_handle_lifetime.py",
    "test_mirror_authority_review02.py",
]


def parsed(path):
    return ast.parse(path.read_text(encoding="utf-8-sig"))


def dump(node):
    return ast.dump(node, include_attributes=False)


checks = {}
for name in files:
    before = parsed(archive / "baseline" / name)
    current = parsed(root / "tests" / name)
    current.body = [
        item for item in current.body
        if not (isinstance(item, ast.ImportFrom)
                and item.module == "_mirror_stable_native_fixture")
    ]
    checks[name + ": entire AST unchanged except inert fixture import"] = dump(before) == dump(current)

baseline_source = parsed(archive / "baseline" / "library_mirror.py")
current_source = parsed(root / "library_mirror.py")


def klass(tree, name):
    return next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)


checks["accepted exclusion owner class unchanged"] = dump(klass(baseline_source, "_DestExclusionOwner")) == dump(klass(current_source, "_DestExclusionOwner"))
before_prepare = next(node for node in klass(baseline_source, "_VaultIoSession").body if isinstance(node, ast.FunctionDef) and node.name == "prepare")
current_prepare = next(node for node in klass(current_source, "_VaultIoSession").body if isinstance(node, ast.FunctionDef) and node.name == "prepare")
checks["accepted prepare method unchanged"] = dump(before_prepare) == dump(current_prepare)

current_tests = parsed(root / "tests" / "test_mirror_stable_handle_discovery.py")
current_functions = {node.name: node for node in current_tests.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
for stage in ("attempt01", "attempt02"):
    earlier = parsed(archive / stage / "test_mirror_stable_handle_discovery.py")
    for node in earlier.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            checks[stage + ": " + node.name + " unchanged"] = dump(node) == dump(current_functions[node.name])

payloads = ["library_mirror.py"] + ["tests/" + name for name in files] + [
    "tests/_mirror_stable_native_fixture.py",
    "tests/test_mirror_stable_handle_discovery.py",
]
hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in payloads}
result = {"static_audit_only": True, "checks": checks, "all_checks_passed": all(checks.values()), "sha256": hashes}
(archive / "review-input-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
assert result["all_checks_passed"], "A frozen assertion/setup body changed"

"""Static source/evidence binding only; never imports candidate modules."""
from pathlib import Path
import ast
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
paths = {"asr_loading_adapter.py": HERE / "asr_loading_adapter.py", "connection_cases.py": HERE / "connection_cases.py",
    "snapshot_lifecycle.py": ROOT / "asr-worker-namespace-proposal01/snapshot_lifecycle.py",
    "trusted_asr_resolver.py": ROOT / "asr-trusted-manifest-resolver-proof02/proposal/trusted_asr_resolver.py"}
assert sha(paths["snapshot_lifecycle.py"].read_bytes()) == "a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd"
assert sha(paths["trusted_asr_resolver.py"].read_bytes()) == "16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833"
bindings = {}
for name, path in paths.items():
    raw = path.read_bytes()
    ast.parse(raw, filename=name)
    bindings[name] = {"path": str(path), "bytes": len(raw), "sha256": sha(raw)}
case_tree = ast.parse(paths["connection_cases.py"].read_bytes())
expected = ast.literal_eval(next(node.value for node in case_tree.body if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == "EXPECTED_CASES" for target in node.targets)))
assert len(expected) == len(set(expected)) == 6
functions = {node.name for node in ast.walk(case_tree) if isinstance(node, ast.FunctionDef)}
assert set(expected) <= functions
for row in json.loads((HERE / "ORIGINAL58-BINDINGS.json").read_bytes())["preserved_files"]:
    raw = (HERE / row["copy"]).read_bytes()
    assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
profile_path = ROOT / "asr-worker-namespace-proposal01/qualify_namespace.py"
report = {"source_only": True, "candidate_executions": 0, "proposed_case_count": 6, "expected_cases": expected,
    "historical58_evidence_unchanged": True, "sources": bindings,
    "existing_guard_source_reference": {"path": str(profile_path), "sha256": sha(profile_path.read_bytes())},
    "execution_requires_reviewed_guard_adaptation": True}
(HERE / "SOURCE-BINDINGS.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
manifest = HERE / "PREPARATION-MANIFEST.json"
assert not manifest.exists()
rows = []
for path in sorted(HERE.rglob("*")):
    if path.is_file() and path != manifest:
        raw = path.read_bytes()
        raw.decode("utf-8-sig")
        rows.append({"path": path.relative_to(HERE).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
manifest.write_text(json.dumps({"scope": "Unexecuted permit/facade adapter source proposal", "payload_count": len(rows),
    "payload_bytes": sum(row["bytes"] for row in rows), "files": rows}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"manifest": str(manifest), "payload_count": len(rows), "payload_bytes": sum(row["bytes"] for row in rows),
    "manifest_sha256": sha(manifest.read_bytes()), "source_bindings_sha256": sha((HERE / "SOURCE-BINDINGS.json").read_bytes()),
    "source_only": True, "candidate_executions": 0, "proposed_cases": 6}, indent=2))

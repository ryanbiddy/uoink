"""Data-only final text binding and seal; no candidate imports or execution."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
HERE = Path(__file__).parent
previous = json.loads((HERE / "SOURCE-BINDINGS.json").read_bytes())
raw = (HERE / "generated_operation_flow.py").read_bytes()
tree = ast.parse(raw)
bindings = dict(previous)
bindings["candidate_sha256"] = hashlib.sha256(raw).hexdigest()
bindings["candidate_bytes"] = len(raw)
bindings["source_review_repairs"] = ["SOURCE-REVIEW01.md", "BOOTSTRAP-REVIEW02.md"]
names = {node.name for node in tree.body if isinstance(node,(ast.ClassDef,ast.FunctionDef))}
names.update(t.id for node in tree.body if isinstance(node,ast.Assign) for t in node.targets if isinstance(t,ast.Name))
required = ("declare_exit_call", "GeneratedLifecyclePort", "controller_flow", "child_flow")
assert all(name in names for name in required)
bindings["bootstrap_exports_checked_by_ast"] = list(required)
for row in bindings["inherited_source_bindings"]:
    original = Path(row["path"]).read_bytes()
    assert len(original) == row["bytes"] and hashlib.sha256(original).hexdigest() == row["sha256"]
before = (HERE / "before-bootstrap-review02/generated_operation_flow.py").read_bytes()
with (HERE / "bootstrap-review02.diff").open("x",encoding="utf-8",newline="\n") as stream:
    stream.write(''.join(difflib.unified_diff(before.decode().splitlines(True),raw.decode().splitlines(True),
          fromfile="before-bootstrap-review02/generated_operation_flow.py",tofile="generated_operation_flow.py")))
with (HERE / "FINAL-SOURCE-BINDINGS.json").open("x",encoding="utf-8",newline="\n") as stream:
    stream.write(json.dumps(bindings,indent=2)+"\n")
rows = []
for path in sorted(HERE.rglob("*")):
    if path.is_file():
        data = path.read_bytes()
        rows.append({"path":path.relative_to(HERE).as_posix(),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
manifest = {"schema":"uoink.scratch-source-preparation.v1", "payload_count":len(rows),
            "payload_bytes":sum(row["bytes"] for row in rows),"candidate_executions":0,"files":rows}
data = (json.dumps(manifest,indent=2)+"\n").encode()
with (HERE / "PREPARATION-MANIFEST.json").open("xb") as stream:
    stream.write(data)
print(json.dumps({"candidate_sha256":bindings["candidate_sha256"],"candidate_bytes":len(raw),
    "manifest_sha256":hashlib.sha256(data).hexdigest(),"payload_count":len(rows),"payload_bytes":manifest["payload_bytes"],
    "candidate_executions":0}))

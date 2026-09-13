"""Data-only text/AST binding. Does not import any candidate or native module."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE = Path(__file__).parent
OLD = BASE / "_scratch/child-readset-adoption-proposal02"
mapping = json.loads((OLD / "SOURCE-INPUTS.json").read_bytes())
rows = []
for name, source in mapping["source_paths"].items():
    raw = Path(source).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == mapping["source_sha256"][name]
    rows.append({"name": name, "path": source, "bytes": len(raw), "sha256": digest,
                 "read_as_text_only": True})
candidate = (HERE / "generated_operation_flow.py").read_bytes()
tree = ast.parse(candidate)
port = next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name == "GeneratedLifecyclePort")
methods = [node.name for node in port.body if isinstance(node,ast.FunctionDef)]
required = ["admit_media_request", "is_issued_media_contract", "begin_transcription", "next_segment", "cancel_transcription"]
assert all(name in methods for name in required)
before = (HERE / "before-source-review01/generated_operation_flow.py").read_bytes()
diff = ''.join(difflib.unified_diff(before.decode().splitlines(True),candidate.decode().splitlines(True),
            fromfile="before-source-review01/generated_operation_flow.py",tofile="generated_operation_flow.py"))
with (HERE / "source-review01.diff").open("x",encoding="utf-8",newline="\n") as stream:
    stream.write(diff)
value = {"schema":"uoink.generated-operation-source-proposal.v1", "candidate_executions":0,
         "candidate_sha256":hashlib.sha256(candidate).hexdigest(), "candidate_bytes":len(candidate),
         "first_draft_sha256":hashlib.sha256(before).hexdigest(), "inherited_source_bindings":rows,
         "prior_source_map_sha256":hashlib.sha256((OLD / "SOURCE-INPUTS.json").read_bytes()).hexdigest(),
         "facade_port_methods":required, "new_win32_symbols":[], "new_wire_operation_names":[],
         "future_observations":["drain","cancel"], "native_support_read":False,
         "production_runtime_authority":False}
with (HERE / "SOURCE-BINDINGS.json").open("x",encoding="utf-8",newline="\n") as stream:
    stream.write(json.dumps(value,indent=2)+"\n")
print(json.dumps({"candidate_sha256":value["candidate_sha256"],"candidate_bytes":len(candidate),
                  "inherited_sources":len(rows),"candidate_executions":0}))

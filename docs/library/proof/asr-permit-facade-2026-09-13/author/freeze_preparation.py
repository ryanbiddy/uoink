"""Hash the small text preparation; never execute candidate source."""
from pathlib import Path
import ast
import hashlib
import json
HERE = Path(__file__).parent
assert not (HERE / "connected01").exists()
assert not (HERE / "ROOT-ADMISSION.md").exists()
bindings = json.loads((HERE / "SOURCE-BINDINGS.json").read_bytes())
for row in bindings["sources"]:
    raw = (HERE / row["name"]).read_bytes()
    assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
    assert raw == Path(row["source"]).read_bytes()
    ast.parse(raw)
assert hashlib.sha256((HERE / "qualify_adapter.py").read_bytes()).hexdigest() == bindings["instrument_sha256"]
assert hashlib.sha256((HERE / "run_connected01.ps1").read_bytes()).hexdigest() == bindings["launcher_sha256"]
assert tuple(json.loads((HERE / "EXPECTED-CASES.json").read_bytes())) == tuple(bindings["expected_case_ids"])
rows = []
for path in sorted(HERE.rglob("*")):
    if path.is_file():
        raw = path.read_bytes()
        rows.append({"path": path.relative_to(HERE).as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
value = {"schema":"uoink.scratch-text-preparation.v1", "payload_count":len(rows),
         "payload_bytes":sum(row["bytes"] for row in rows), "candidate_executions":0, "files":rows}
raw = (json.dumps(value,indent=2)+"\n").encode()
with (HERE / "PREPARATION-MANIFEST.json").open("xb") as stream:
    stream.write(raw)
print(json.dumps({"payload_count":len(rows), "payload_bytes":value["payload_bytes"], "manifest_sha256":hashlib.sha256(raw).hexdigest(), "candidate_executions":0}))

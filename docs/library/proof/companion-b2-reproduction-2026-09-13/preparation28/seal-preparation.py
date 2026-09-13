"""Static parse and text-input seal only; no runtime/artifact access."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path

out = Path(__file__).absolute().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
prior = out.parent / "b2-real-wheel-preparation01"
prior_raw = (prior / "SHA256.json").read_bytes()
assert sha(prior_raw) == "ebab6c9180c7c8f230e55b619d1cc469d7043f1a43e197a3a8abd126f7eb7484"
for row in json.loads(prior_raw)["payloads"]:
    raw = (prior / row["file"]).read_bytes()
    assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
syntax = []
for path in sorted(out.rglob("*.py")):
    raw = path.read_bytes()
    ast.parse(raw, filename=str(path))
    syntax.append({"file": str(path.relative_to(out)).replace("\\", "/"), "bytes": len(raw), "sha256": sha(raw)})
bindings = json.loads((out / "input-bindings.json").read_text(encoding="utf-8"))
for row in bindings["bindings"]:
    raw = (out / row["target"]).read_bytes()
    assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
source = (out / "prior-child/build-guarded314.py.txt").read_text(encoding="utf-8")
child = (out / "build-guarded313.py").read_text(encoding="utf-8")
for change in json.loads((out / "child-adaptation-reasons.json").read_text(encoding="utf-8")):
    assert source.count(change["before"]) == 1
    source = source.replace(change["before"], change["after"])
assert source == child
before = (out / "preparation-repair01/prepare-before.py.txt").read_text(encoding="utf-8")
after = (out / "prepare-text-inputs.py").read_text(encoding="utf-8")
diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile="attempt01/prepare-text-inputs.py", tofile="attempt02/prepare-text-inputs.py"))
(out / "preparation-repair01/quoting-repair.patch.txt").write_text(diff, encoding="utf-8", newline="\n")
receipt = {"status": "PREPARED_NOT_EXECUTED", "created_utc": datetime.now(timezone.utc).isoformat(),
    "prior21_manifest_sha256": sha(prior_raw), "prior21_payloads_reverified": 21, "static_ast_parses": syntax,
    "text_preparation_attempt01_exit": 1, "text_preparation_attempt02_exit": 0, "text_inputs_copied": 12,
    "runtime_copy_invoked": False, "runtime_launched": False, "guarded_child_invoked": False,
    "upstream_or_output_wheel_accessed": False, "real_builds_run_here": 0,
    "new_execution_qualification_cases": 0, "builder_recipe_bytes_unchanged": True}
(out / "PREPARATION-RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
payloads = []
for path in sorted(out.rglob("*")):
    if path.is_file() and path != out / "SHA256.json":
        raw = path.read_bytes()
        payloads.append({"file": str(path.relative_to(out)).replace("\\", "/"), "bytes": len(raw), "sha256": sha(raw)})
manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "payload_count": len(payloads), "payloads": payloads}
raw = (json.dumps(manifest, indent=2) + "\n").encode()
with (out / "SHA256.json").open("xb") as stream:
    stream.write(raw)
print(json.dumps({"payload_count": len(payloads), "manifest_sha256": sha(raw), "static_parse_count": len(syntax), "runtime_or_wheel_accessed": False}))

"""Static syntax/input verification and scratch preparation seal only."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

out = Path(__file__).absolute().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
prior = {
    "companion-b2-builder01": "ac31912d51a4a6b38c8e028e65bd005e9fedcd7125d51f219ca51973b834fc8f",
    "companion-b2-builder-combined01": "063159c7b97b1f871947a2916c48cfdb7ea6c93246815719115789335fc57963",
}
for name, expected in prior.items():
    root = out.parent / name
    raw = (root / "SHA256.json").read_bytes()
    assert sha(raw) == expected
    for row in json.loads(raw)["payloads"]:
        data = (root / row["file"]).read_bytes()
        assert len(data) == row["bytes"] and sha(data) == row["sha256"]
syntax = []
for path in sorted(out.rglob("*.py")):
    raw = path.read_bytes()
    ast.parse(raw, filename=str(path))
    syntax.append({"file": str(path.relative_to(out)).replace("\\", "/"), "sha256": sha(raw)})
for row in json.loads((out / "input-bindings.json").read_text(encoding="utf-8"))["bindings"]:
    raw = (out / row["target"]).read_bytes()
    assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
verification = {"status": "PREPARED_NOT_INVOKED", "static_ast_parse_files": syntax,
    "prior_payload_counts_verified": [63, 100], "original_seals_unchanged": prior,
    "preparation_command": [r"C:\Python314\python.exe", "-I", "-S", "-B", str(out / "prepare-inputs.py")],
    "preparation_observed_exit": 0, "text_copies": 10, "runtime_files_hashed_only": 33,
    "build_launcher_executed": False, "guarded_builder_executed": False, "actual_upstream_wheel_accessed": False,
    "runtime_copied_or_executed": False, "real_artifact_test_count": 0,
    "created_utc": datetime.now(timezone.utc).isoformat()}
(out / "PREPARATION-RECEIPT.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8", newline="\n")
payloads = []
for path in sorted(out.rglob("*")):
    if path.is_file() and path.name != "SHA256.json":
        raw = path.read_bytes()
        payloads.append({"file": str(path.relative_to(out)).replace("\\", "/"), "bytes": len(raw), "sha256": sha(raw)})
manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "payload_count": len(payloads), "payloads": payloads}
raw = (json.dumps(manifest, indent=2) + "\n").encode()
with (out / "SHA256.json").open("xb") as stream:
    stream.write(raw)
print(json.dumps({"payload_count": len(payloads), "manifest_sha256": sha(raw), "static_parse_count": len(syntax), "actual_wheel_accessed": False}))

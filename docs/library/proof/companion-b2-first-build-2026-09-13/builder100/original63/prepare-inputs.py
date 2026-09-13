"""Copy only sealed text inputs; never open the upstream wheel or model asset."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
scratch = out.parent
b2 = scratch / "companion-b2-empty-buffer01"
distribution = scratch / "companion-b-distribution-plan01"
bindings = []
def copy(source, target):
    assert not source.is_symlink() and target.resolve().is_relative_to(out.resolve()) and not target.exists()
    raw = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    bindings.append({"source": str(source), "file": target.relative_to(out).as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
for old, new in (("B2.py.txt", "B2.py.txt"), ("proposed-B2-NOTICE.txt", "NOTICE.txt"),
                 ("proposed-member-manifest-B2.json", "member-manifest.json"), ("upstream-to-B2-normalized.patch.txt", "patch.txt")):
    copy(b2 / old, out / "recipe" / new)
for path in (distribution / "inputs/upstream-wheel-text").rglob("*"):
    if path.is_file():
        assert path.name.endswith(".txt") and ".onnx" not in path.name
        copy(path, out / "fixtures/upstream-text" / path.relative_to(distribution / "inputs/upstream-wheel-text"))
copy(b2 / "SHA256.json", out / "prior-seals/B2-48-SHA256.json")
copy(distribution / "SHA256.json", out / "prior-seals/distribution52-SHA256.json")
(out / "input-bindings.json").write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "bindings": bindings,
    "actual_wheel_model_opened": False, "upstream_code_executed": False}, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"copied_text_inputs": len(bindings), "actual_artifact_access": False}))

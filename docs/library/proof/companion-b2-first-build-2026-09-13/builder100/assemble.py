"""Combine immutable synthetic evidence; no artifact or test execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
scratch = out.parent
original = scratch / "companion-b2-builder01"
independent = scratch / "astra-b2-builder01"
sha = lambda raw: hashlib.sha256(raw).hexdigest()
expected = "ac31912d51a4a6b38c8e028e65bd005e9fedcd7125d51f219ca51973b834fc8f"
assert not (out / "SHA256.json").exists()
raw = (original / "SHA256.json").read_bytes()
assert sha(raw) == expected
manifest = json.loads(raw)
assert manifest["payload_count"] == len(manifest["payloads"]) == 63
for row in manifest["payloads"]:
    data = (original / row["file"]).read_bytes()
    assert len(data) == row["bytes"] and sha(data) == row["sha256"]
review = json.loads((independent / "ROOT-REVIEW.json").read_bytes())
assert len(review["exact_copied_inputs"]) == 24
for name, row in review["exact_copied_inputs"].items():
    data = (independent / name).read_bytes()
    assert data == (original / name).read_bytes()
    assert len(data) == row["bytes"] and sha(data) == row["sha256"]
results = []
for source in (original, independent):
    result = json.loads((source / "runs/bw03/result.json").read_bytes())
    launcher = json.loads((source / "launch-bw03/result.json").read_bytes())
    assert (result["tests_run"], result["passed"], result["failed"], result["errors"], result["skipped"], result["exit"]) == (62, 62, 0, 0, 0, 0)
    assert launcher["exit"] == 0 and launcher["inputs_unchanged"]
    assert result["source_sha256"] == "ef7189180bc443f7b0b68386b8452d0b57b2be4beca3eee9d81409a7658b4c3f"
    assert result["protocol_sha256"] == "4850a083264e305871b81a9ae5a16390b63950ce9b9efca630c7aa89fd153417"
    assert result["guard"] == {"preloaded_heavy": [], "postloaded_heavy": [], "violations": [], "finder_installed_at_finish": True, "valid": True}
    results.append(result)
assert [row["id"] for row in results[0]["observations"]] == [row["id"] for row in results[1]["observations"]]
plan = json.loads((independent / "launch-bw03/plan.json").read_bytes())
for path, digest in plan["input_hashes"].items():
    assert sha(Path(path).read_bytes()) == digest
copies = []
def copy(source, target):
    assert not source.is_symlink() and target.resolve().is_relative_to(out.resolve()) and not target.exists()
    raw = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    assert target.read_bytes() == raw
    copies.append({"source": str(source), "file": target.relative_to(out).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
for source, name in ((original, "original63"), (independent, "independent-root01")):
    for path in sorted(source.rglob("*")):
        if path.is_file():
            copy(path, out / name / path.relative_to(source))
copy(scratch / "prepare_b2_builder_astra01.py", out / "root-preparation/prepare_b2_builder_astra01.py")
assert len(copies) == 95
for row in copies:
    assert sha(Path(row["source"]).read_bytes()) == row["sha256"]
assert sha((out / "original63/SHA256.json").read_bytes()) == expected
(out / "copy-receipt.json").write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "copies": copies,
    "original63_seal": expected, "ordered_62_case_ids_match": True, "source_protocol_hashes_match": True,
    "both_child_launcher_exits": 0, "new_execution": False}, indent=2) + "\n", encoding="utf-8", newline="\n")
payloads = [{"file": path.relative_to(out).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}
            for path in sorted(out.rglob("*")) if path.is_file()]
assert (out / ".gitattributes").read_bytes() == b"* -text\n"
(out / "SHA256.json").write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "payload_count": len(payloads), "payloads": payloads}, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"payload_count": len(payloads), "manifest_sha256": sha((out / "SHA256.json").read_bytes())}))

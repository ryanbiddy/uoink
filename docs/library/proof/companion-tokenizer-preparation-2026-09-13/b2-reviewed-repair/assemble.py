"""Preserve B2 proof and independent receipts as bytes, without rerunning them."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
scratch = out.parent
original = scratch / "companion-b2-empty-buffer01"
independent = scratch / "astra-companion-b2-01"
sha = lambda raw: hashlib.sha256(raw).hexdigest()
expected = "cf00f826b16a6f223428e886c783d72397668df8fed646cad63be51806c1672b"
assert not (out / "SHA256.json").exists()
raw = (original / "SHA256.json").read_bytes()
assert sha(raw) == expected
manifest = json.loads(raw)
assert manifest["payload_count"] == len(manifest["payloads"]) == 48
for row in manifest["payloads"]:
    data = (original / row["file"]).read_bytes()
    assert len(data) == row["bytes"] and sha(data) == row["sha256"]
review = json.loads((independent / "ROOT-REVIEW.json").read_bytes())
assert len(review["inputs"]) == 9
for name, binding in review["inputs"].items():
    data = (independent / name).read_bytes()
    assert data == (original / name).read_bytes()
    assert len(data) == binding["bytes"] and sha(data) == binding["sha256"]
receipts = [json.loads((source / "runs/b2-candidate01/result.json").read_bytes()) for source in (original, independent)]
for receipt in receipts:
    assert (receipt["tests_run"], receipt["passed"], receipt["failed"], receipt["errors"], receipt["skipped"], receipt["exit"]) == (10, 10, 0, 0, 0, 0)
    assert receipt["source_sha256"] == "bf452635becacf6bba46825be6d6eea533da472ce966ee47f5ce7bccfc3bf06d"
    assert receipt["test_protocol_sha256"] == "1626224d43b10272661445aa8c03d8dd187c29a29cb5b9622ac31e4f52b4335f"
    assert receipt["guard"] == {"preloaded_heavy": [], "postloaded_heavy": [], "blocked_imports": [], "blocked_audit_events": [], "finder_installed_at_finish": True, "valid": True}
assert [item["id"] for item in receipts[0]["observations"]] == [item["id"] for item in receipts[1]["observations"]]
launch = json.loads((independent / "launch-b2-candidate01/result.json").read_bytes())
assert launch["exit"] == 0 and launch["inputs_unchanged"]
plan = json.loads((independent / "launch-b2-candidate01/plan.json").read_bytes())
for path, digest in plan["input_hashes"].items():
    assert sha(Path(path).read_bytes()) == digest
copies = []
def copy(source, dest):
    assert not source.is_symlink() and dest.resolve().is_relative_to(out.resolve()) and not dest.exists()
    raw = source.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    assert dest.read_bytes() == raw
    copies.append({"source": str(source), "file": dest.relative_to(out).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
for source, name in ((original, "original48"), (independent, "independent-root01")):
    for path in sorted(source.rglob("*")):
        if path.is_file():
            copy(path, out / name / path.relative_to(source))
copy(scratch / "prepare_companion_b2_astra01.py", out / "root-preparation/prepare_companion_b2_astra01.py")
assert len(copies) == 65
for row in copies:
    assert sha(Path(row["source"]).read_bytes()) == row["sha256"]
assert sha((out / "original48/SHA256.json").read_bytes()) == expected
(out / "copy-receipt.json").write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "copies": copies,
    "original48_seal": expected, "source_and_protocol_hashes_match": True, "ordered_ten_case_ids_match": True,
    "independent_child_and_launcher_exit": 0, "no_new_tests": True}, indent=2) + "\n", encoding="utf-8", newline="\n")
payloads = [{"file": path.relative_to(out).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}
            for path in sorted(out.rglob("*")) if path.is_file()]
(out / "SHA256.json").write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "payload_count": len(payloads), "payloads": payloads}, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"payload_count": len(payloads), "manifest_sha256": sha((out / "SHA256.json").read_bytes())}))

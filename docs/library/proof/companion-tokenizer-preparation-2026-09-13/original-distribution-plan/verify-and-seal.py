"""Bind planning text and verify existing seals; no tests or artifact build."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
root = out.parents[1]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert not (out / "SHA256.json").exists(), "Preserve existing archive seal"
inventory = json.loads((out / "inventory.json").read_bytes())
for row in inventory["evidence_bindings"]:
    assert sha(Path(row["source"])) == row["sha256"]
    assert sha(out / row["file"]) == row["sha256"]
original_seals = [
    ("runtime-asset-guard-proposal01", 24, "a32bb76d68d7939905b6538921f8915a0d78a47ab2e0c3f3c661c49036940237"),
    ("companion-b-static-qualification01", 46, "28d2d34c530e80716964b475244551340222dc7b8b2f39f77b8be9c490117fc5"),
    ("companion-b-combined-review01", 67, "05620906f1d09b8afce3f7065798495c3e7f35666a17aa2948a992500d9530e9"),
]
for name, count, digest in original_seals:
    original = root / "_scratch" / name
    assert sha(original / "SHA256.json") == digest
    manifest = json.loads((original / "SHA256.json").read_bytes())
    assert manifest["payload_count"] == len(manifest["payloads"]) == count
    for row in manifest["payloads"]:
        item = original / row["file"]
        assert item.resolve().is_relative_to(original.resolve())
        assert item.stat().st_size == row["bytes"] and sha(item) == row["sha256"]

before = (out / "inputs/upstream-wheel-text/faster_whisper/version.py.txt").read_text(encoding="utf-8")
after = (out / "proposed-version.py.txt").read_text(encoding="utf-8")
(out / "proposed-version.patch.txt").write_text("".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
    fromfile="a/faster_whisper/version.py", tofile="b/faster_whisper/version.py")), encoding="utf-8", newline="\n")
assert (out / ".gitattributes").read_bytes() == b"* -text\n"
plan = json.loads((out / "proposed-member-manifest.json").read_bytes())
assert plan["status"] == "PROPOSED_ONLY" and plan["output_wheel_sha256"] is None and not plan["output_wheel_built"]
assert plan["member_count"] == len(plan["members"]) == 16
receipt = {"verified_utc": datetime.now(timezone.utc).isoformat(),
    "prior_seals_and_all_payloads_unchanged": [{"directory": name, "payloads": count, "sha256": digest} for name, count, digest in original_seals],
    "all_captured_planning_inputs_still_match_sources": True,
    "proposed_member_count": 16, "proposed_wheel_built": False,
    "frozen_test_change_applied": False, "source_pins_staging_modified": False,
    "new_tests_executed": False,
    "commands": [r"C:\Python314\python.exe -I -S -B _scratch\companion-b-distribution-plan01\inventory.py",
                 r"C:\Python314\python.exe -I -S -B _scratch\companion-b-distribution-plan01\materialize-plan.py",
                 r"C:\Python314\python.exe -I -S -B _scratch\companion-b-distribution-plan01\verify-and-seal.py"],
    "scope": "Local wheel identity and exact inert distribution/test proposal; no build, install or runtime acceptance"}
(out / "seal-checks.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
payloads = []
for path in sorted(out.rglob("*")):
    assert not path.is_symlink()
    if path.is_file():
        payloads.append({"file": path.relative_to(out).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)})
manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "payload_count": len(payloads), "payloads": payloads}
(out / "SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"payload_count": len(payloads), "manifest_sha256": sha(out / "SHA256.json"),
                  "prior24_46_67_seals_unchanged": True, "new_tests_or_builds": False}))

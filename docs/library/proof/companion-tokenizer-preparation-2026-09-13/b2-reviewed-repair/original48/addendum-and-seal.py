"""Write a separate inert B2 manifest addendum and seal existing observations."""
import ast
import base64
import csv
from datetime import datetime, timezone
import difflib
import hashlib
import io
import json
from pathlib import Path

out = Path(__file__).resolve().parent
scratch = out.parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
assert not (out / "SHA256.json").exists(), "Preserve existing outer seal"
preparation = json.loads((out / "preparation.json").read_bytes())
for row in preparation["bindings"]:
    assert sha(Path(row["source"]).read_bytes()) == row["sha256"]
    assert sha((out / row["file"]).read_bytes()) == row["sha256"]
for seal in preparation["prior_seals_verified"]:
    original = scratch / seal["name"]
    assert sha((original / "SHA256.json").read_bytes()) == seal["sha256"]
    manifest = json.loads((original / "SHA256.json").read_bytes())
    assert manifest["payload_count"] == len(manifest["payloads"]) == seal["count"]
    for row in manifest["payloads"]:
        raw = (original / row["file"]).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]

b1 = (out / "inputs/B1.py.txt").read_bytes()
b2 = (out / "B2.py.txt").read_bytes()
assert b1.count(b"        if tokenizer_bytes:\r\n") == 1
assert b1.replace(b"        if tokenizer_bytes:\r\n", b"        if tokenizer_bytes is not None:\r\n") == b2
old_protocol = ast.parse((out / "inputs/original-six-contracts.py.txt").read_bytes())
new_protocol = ast.parse((out / "constructor-contracts.py.txt").read_bytes())
dump = lambda node: ast.dump(node, include_attributes=False)
for node in old_protocol.body:
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        match = next(item for item in new_protocol.body if getattr(item, "name", None) == node.name)
        assert dump(node) == dump(match)
old_harness = ast.parse((out / "inputs/original-harness.py.txt").read_bytes())
new_harness = ast.parse((out / "harness.py").read_bytes())
for name in ("StdlibOnlyFinder", "audit"):
    assert dump(next(node for node in old_harness.body if getattr(node, "name", None) == name)) == dump(next(node for node in new_harness.body if getattr(node, "name", None) == name))

receipts = []
for label, expected in (("b1-boundary01", (6, 4, 1)), ("b2-candidate01", (10, 0, 0))):
    receipt = json.loads((out / "runs" / label / "result.json").read_bytes())
    launcher = json.loads((out / ("launch-" + label) / "result.json").read_bytes())
    plan = json.loads((out / ("launch-" + label) / "plan.json").read_bytes())
    assert receipt["tests_run"] == len(receipt["observations"]) == 10
    assert (receipt["passed"], receipt["failed"], receipt["exit"]) == expected
    assert receipt["errors"] == receipt["skipped"] == 0
    assert launcher["exit"] == expected[2] and launcher["inputs_unchanged"]
    for path, digest in plan["input_hashes"].items():
        assert sha(Path(path).read_bytes()) == digest
    assert receipt["guard"] == {"preloaded_heavy": [], "postloaded_heavy": [], "blocked_imports": [], "blocked_audit_events": [], "finder_installed_at_finish": True, "valid": True}
    assert receipt["flags"] == {"isolated": 1, "no_site": 1, "dont_write_bytecode": 1}
    assert not receipt["whole_dependency_module_executed"] and not receipt["real_tokenizer_or_model_executed"]
    assert not any(path.is_file() for path in (out / "runs" / label / "temporary").rglob("*"))
    receipts.append(receipt)
assert [row["id"] for row in receipts[0]["observations"]] == [row["id"] for row in receipts[1]["observations"]]
for row in receipts[1]["observations"]:
    if row.get("boundary"):
        b = row["boundary"]
        assert b["exception_type"] == "ValueError" and b["events"] == ["tokenizer.bytes"]
        assert not b["model_assigned"] and not b["tokenizer_assigned"]

def write_diff(before, after, path, old_label, new_label):
    patch = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=old_label, tofile=new_label))
    (out / path).write_text(patch, encoding="utf-8", newline="\n")
    return patch.encode()

upstream = (out / "inputs/upstream-transcribe.py.txt").read_text(encoding="utf-8")
logical_patch = write_diff(upstream, b2.decode().replace("\r\n", "\n"), "upstream-to-B2-normalized.patch.txt", "a/faster_whisper/transcribe.py", "b/faster_whisper/transcribe.py")
for before, after, dest in (("inputs/original-harness.py.txt", "harness.py", "harness-changes.patch.txt"),
                            ("inputs/original-launch.py.txt", "launch.py", "launcher-changes.patch.txt"),
                            ("inputs/original-six-contracts.py.txt", "constructor-contracts.py.txt", "protocol-addition.patch.txt")):
    write_diff((out / before).read_text(encoding="utf-8"), (out / after).read_text(encoding="utf-8"), dest, "a/" + before, "b/" + after)

notice = ("Uoink local derivative: faster-whisper 1.2.1+uoink.localassets1\n"
          "Based on faster-whisper 1.2.1 by SYSTRAN; original MIT license retained.\n\n"
          "Local change: route supplied tokenizer buffers, including empty buffers,\n"
          "to the parser before considering ambient files. Prepare available tokenizer\n"
          "input before CTranslate2 construction and refuse missing local-only input.\n"
          "The explicit non-local fallback for absent tokenizer input is retained.\n"
          "The local version identifies this modification separately from upstream.\n\n"
          "Patch SHA-256: " + sha(logical_patch) + "\n"
          "This notice does not claim upstream endorsement, advisory clearance, model\n"
          "quality, speaker attribution, or complete runtime/release acceptance.\n").encode()
(out / "proposed-B2-NOTICE.txt").write_bytes(notice)
manifest = json.loads((out / "inputs/B1-distribution-plan/proposed-member-manifest.json").read_bytes())
assert manifest["status"] == "PROPOSED_ONLY" and not manifest["output_wheel_built"]
members = manifest["members"]
for row in members:
    raw = b2 if row["member"] == "faster_whisper/transcribe.py" else notice if row["member"].endswith("/UOINK-LOCALASSETS-NOTICE.txt") else None
    if raw is not None:
        row.update(bytes=len(raw), sha256=sha(raw), record_hash="sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("="), basis="B2 proposed exact text only; not packaged")
record = next(row for row in members if row["member"].endswith("/RECORD"))
stream = io.StringIO(newline="")
writer = csv.writer(stream, lineterminator="\n")
for row in sorted((row for row in members if row is not record), key=lambda row: row["member"]):
    writer.writerow([row["member"], row["record_hash"], row["bytes"]])
writer.writerow([record["member"], "", ""])
record_raw = stream.getvalue().encode()
record.update(bytes=len(record_raw), sha256=sha(record_raw), basis="B2 proposed RECORD text; not verified against an output wheel")
(out / "proposed-B2-RECORD.csv.txt").write_bytes(record_raw)
manifest.update(proposal_revision="B2-empty-buffer", original_plan_unchanged=True,
                source_sha256=sha(b2), aggregate_normalized_patch_sha256=sha(logical_patch))
(out / "proposed-member-manifest-B2.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
checks = {"verified_utc": datetime.now(timezone.utc).isoformat(), "all_prior24_46_67_52_seals_and_payloads_unchanged": True,
    "original_six_assertions_and_helpers_unchanged": True, "finder_and_audit_asts_unchanged": True,
    "all_launcher_inputs_unchanged": True, "identical_ten_case_ids": True,
    "B1": {key: receipts[0][key] for key in ("tests_run", "passed", "failed", "errors", "skipped", "exit")},
    "B2": {key: receipts[1][key] for key in ("tests_run", "passed", "failed", "errors", "skipped", "exit")},
    "B2_source_sha256": sha(b2), "B2_source_bytes": len(b2),
    "B1_to_B2_patch_sha256": sha((out / "B1-to-B2.patch.txt").read_bytes()),
    "upstream_to_B2_normalized_patch_sha256": sha(logical_patch),
    "proposed_B2_notice_sha256": sha(notice), "proposed_B2_RECORD_sha256": sha(record_raw),
    "prior_distribution_plan_modified": False, "wheel_built": False, "new_test_run_by_sealer": False}
(out / "qualification-checks.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8", newline="\n")
assert (out / ".gitattributes").read_bytes() == b"* -text\n"
payloads = []
for path in sorted(out.rglob("*")):
    assert not path.is_symlink()
    if path.is_file():
        raw = path.read_bytes()
        payloads.append({"file": path.relative_to(out).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
(out / "SHA256.json").write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "payload_count": len(payloads), "payloads": payloads}, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"payload_count": len(payloads), "manifest_sha256": sha((out / "SHA256.json").read_bytes()),
                  "B2_source_sha256": sha(b2), "B1": checks["B1"], "B2": checks["B2"],
                  "B2_aggregate_patch_sha256": sha(logical_patch), "prior_seals_unchanged": True}))

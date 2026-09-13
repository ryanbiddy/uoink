"""Seal qualified source and failed attempts; do not execute tests or artifacts."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
assert not (out / "SHA256.json").exists(), "Preserve completed proof"
source = out / "build_faster_whisper_localassets_wheel.py"
protocol = out / "tests-synthetic.py"
assert sha(source.read_bytes()) == "ef7189180bc443f7b0b68386b8452d0b57b2be4beca3eee9d81409a7658b4c3f"
assert sha(protocol.read_bytes()) == "4850a083264e305871b81a9ae5a16390b63950ce9b9efca630c7aa89fd153417"
assert (out / "bw02-before-parser-repair/tests.py.txt").read_bytes() == protocol.read_bytes()
def assertions(raw):
    return [ast.dump(node, include_attributes=False) for node in ast.walk(ast.parse(raw)) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self" and node.func.attr.startswith("assert")]
assert assertions((out / "bw01-before-fixture-repair/tests.py.txt").read_bytes()) == assertions(protocol.read_bytes())
bindings = json.loads((out / "input-bindings.json").read_bytes())
for row in bindings["bindings"]:
    assert sha(Path(row["source"]).read_bytes()) == row["sha256"]
    assert sha((out / row["file"]).read_bytes()) == row["sha256"]

for old, new, dest in (
    ("prequalification-repair01/builder-before.py.txt", "bw01-before-fixture-repair/builder.py.txt", "prequalification-repair01/bounded-read.patch.txt"),
    ("prequalification-repair01/tests-before.py.txt", "bw01-before-fixture-repair/tests.py.txt", "prequalification-repair01/bounded-read-tests.patch.txt"),
    ("bw01-before-fixture-repair/tests.py.txt", "tests-synthetic.py", "bw02-fixture-setup.patch.txt"),
    ("bw02-before-parser-repair/builder.py.txt", "build_faster_whisper_localassets_wheel.py", "bw03-parser-repair.patch.txt"),
    ("bw02-before-parser-repair/run-synthetic.py.txt", "run-synthetic.py", "bw03-label-guard-wrapper.patch.txt"),
    ("bw02-before-parser-repair/launch.py.txt", "launch.py", "bw03-label-launcher.patch.txt"),
):
    patch = "".join(difflib.unified_diff((out / old).read_text(encoding="utf-8").splitlines(keepends=True),
        (out / new).read_text(encoding="utf-8").splitlines(keepends=True), fromfile="a/" + old, tofile="b/" + new))
    (out / dest).write_text(patch, encoding="utf-8", newline="\n")

hash_locations = {}
for path in out.rglob("*"):
    if path.is_file():
        hash_locations.setdefault(sha(path.read_bytes()), []).append(path.relative_to(out).as_posix())
attempts = []
for label, expected in (("bw01", (61, 1, 1)), ("bw02", (61, 1, 1)), ("bw03", (62, 0, 0))):
    result = json.loads((out / "runs" / label / "result.json").read_bytes())
    launch = json.loads((out / ("launch-" + label) / "result.json").read_bytes())
    plan = json.loads((out / ("launch-" + label) / "plan.json").read_bytes())
    assert result["tests_run"] == len(result["observations"]) == 62
    assert (result["passed"], result["failed"], result["exit"]) == expected
    assert result["errors"] == result["skipped"] == 0
    assert launch["exit"] == expected[2] and launch["inputs_unchanged"]
    assert result["guard"] == {"preloaded_heavy": [], "postloaded_heavy": [], "violations": [], "finder_installed_at_finish": True, "valid": True}
    assert not result["actual_upstream_wheel_or_model_opened"] and not result["actual_wheel_built"]
    assert result["flags"] == {"isolated": 1, "no_site": 1, "dont_write_bytecode": 1}
    assert not any(path.is_file() for path in (out / "runs" / label / "temporary").rglob("*"))
    for digest in plan["input_hashes"].values():
        assert digest in hash_locations, "Missing exact historical launch input: " + digest
    attempts.append({"label": label, "passed": result["passed"], "failed": result["failed"], "errors": 0, "skipped": 0,
                     "exit": result["exit"], "all_input_bytes_retained": True,
                     "case_ids": [row["id"] for row in result["observations"]]})
assert attempts[0]["case_ids"] == attempts[1]["case_ids"] == attempts[2]["case_ids"]
checks = {"verified_utc": datetime.now(timezone.utc).isoformat(), "attempts": attempts,
    "current_source_sha256": sha(source.read_bytes()), "current_protocol_sha256": sha(protocol.read_bytes()),
    "all_62_assertions_preserved_across_fixture_repair": True,
    "bw02_bw03_protocol_byte_identical": True, "source_inputs_unchanged": True,
    "actual_wheel_invocation_or_model_asset_read": False, "new_tests_by_sealer": False}
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
                  "source_sha256": sha(source.read_bytes()), "final_passed": 62,
                  "retained_failed_attempts": ["bw01", "bw02"], "actual_artifact_invocation": False}))

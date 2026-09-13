"""Verify inert source/diff structure and seal; never run proposed functions."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys


def deny(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
        raise RuntimeError("inert proposal validation forbids network and children")


sys.addaudithook(deny)
out = Path(__file__).resolve().parent
assert not (out / "SHA256.json").exists()
records = json.loads((out / "input-bindings.json").read_text(encoding="utf-8"))
for record in records:
    data = (out / record["saved_file"]).read_bytes()
    assert len(data) == record["bytes"]
    assert hashlib.sha256(data).hexdigest() == record["sha256"]


def reconstruct(source, patch):
    lines = source.splitlines(keepends=True)
    result = []
    cursor = 0
    for line in patch.splitlines(keepends=True)[2:]:
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if match:
            start = int(match[1]) - 1
            assert cursor <= start
            result.extend(lines[cursor:start])
            cursor = start
        elif line.startswith(" "):
            assert lines[cursor] == line[1:]
            result.append(line[1:])
            cursor += 1
        elif line.startswith("-"):
            assert lines[cursor] == line[1:]
            cursor += 1
        elif line.startswith("+"):
            result.append(line[1:])
        else:
            raise AssertionError("unexpected patch structure")
    result.extend(lines[cursor:])
    return "".join(result)


for name, source in (
    ("product-A", "inputs/whisper_runner.py"),
    ("companion-B", "inputs/installer/staging/python/Lib/site-packages/faster_whisper/transcribe.py"),
):
    before = (out / source).read_text(encoding="utf-8-sig")
    after = (out / (name + ".py.txt")).read_text(encoding="utf-8")
    patch_text = (out / (name + ".patch.txt")).read_text(encoding="utf-8")
    assert reconstruct(before, patch_text) == after
    ast.parse(after)

tests = ast.parse((out / "tests-proposed.py.txt").read_text(encoding="utf-8"))
counts = {node.name: sum(isinstance(child, ast.FunctionDef) and child.name.startswith("test_")
                        for child in node.body)
          for node in tests.body if isinstance(node, ast.ClassDef)}
assert counts == {"ProductGuardContracts": 11, "CompanionConstructorContracts": 6}
result = {
    "verified_utc": datetime.now(timezone.utc).isoformat(),
    "input_hashes_verified": len(records), "source_proposals_parsed": 2,
    "diff_reconstructions_verified": 2, "synthetic_test_source_parsed": True,
    "proposed_test_counts": counts, "tests_run": 0, "product_functions_executed": 0,
    "network_requests": 0, "verdict": "TEXT_PROPOSAL_ONLY",
}
(out / "validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
payloads = [{"file": path.relative_to(out).as_posix(), "bytes": path.stat().st_size,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(out.rglob("*")) if path.is_file()]
seal = out / "SHA256.json"
seal.write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(),
                           "payload_count": len(payloads), "payloads": payloads}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({**result, "payload_count": len(payloads),
                  "manifest_sha256": hashlib.sha256(seal.read_bytes()).hexdigest()}))

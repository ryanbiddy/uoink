"""Seal source text evidence; never execute the captured source."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone


def deny_runtime(event, args):
    if event.startswith("socket.") or event in {
        "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"
    }:
        raise RuntimeError("source seal forbids network and child processes")


sys.addaudithook(deny_runtime)
root = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
out = root / "runtime-candidate03-source"
assert out.is_dir()
assert not (out / "SHA256.json").exists(), "never overwrite an existing seal"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def captured_path(relative):
    path = (out / relative).resolve(strict=True)
    assert path.is_relative_to(out.resolve()), relative
    assert path.is_file(), relative
    return path


sources = json.loads((out / "source-bindings.json").read_text(encoding="utf-8-sig"))
retrievals = json.loads((out / "retrievals.json").read_text(encoding="utf-8-sig"))
commits = json.loads((out / "commit-bindings.json").read_text(encoding="utf-8-sig"))
assert len(sources) == 39
assert len(retrievals) == 19
assert len(commits) == 5
for record in sources + retrievals:
    path = captured_path(record["saved_file"])
    assert path.stat().st_size == record["bytes"], record["saved_file"]
    assert digest(path) == record["sha256"], record["saved_file"]
for record in sources:
    if record["origin"] == "upstream-source-text":
        request = next(item for item in retrievals if item["url"] == record["url"])
        binding = next(item for item in commits if item["repository"] == record["repository"])
        assert request["status"] == 200
        assert request["sha256"] == record["sha256"]
        assert binding["commit"] == record["commit"]
        assert "/" + binding["commit"] + "/" in record["url"]
for binding in commits:
    request = next(item for item in retrievals if item["sha256"] == binding["response_sha256"])
    response = json.loads(captured_path(request["saved_file"]).read_text(encoding="utf-8"))
    assert response["sha"] == binding["commit"]

instruments = out / "instruments"
instruments.mkdir(exist_ok=False)
for name in (
    "RUNTIME-CANDIDATE03-SOURCE-BRIEF-2026-09-13.md",
    "capture_runtime_candidate03_source.py",
    "seal_runtime_candidate03_source.py",
):
    shutil.copyfile(root / name, instruments / name)

verification = {
    "verified_utc": datetime.now(timezone.utc).isoformat(),
    "source_bindings_verified": len(sources),
    "raw_retrieval_bindings_verified": len(retrievals),
    "release_commit_bindings_verified": len(commits),
    "hash_mismatches": 0,
    "captured_source_executed": False,
    "product_tests_run": 0,
    "network_requests_during_seal": 0,
}
(out / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
payloads = []
for path in sorted(out.rglob("*")):
    if path.is_file():
        payloads.append({
            "file": path.relative_to(out).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        })
manifest = {
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "candidate03 source text evidence only; excludes this manifest",
    "payload_count": len(payloads),
    "payloads": payloads,
}
seal = out / "SHA256.json"
seal.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
for record in payloads:
    assert digest(captured_path(record["file"])) == record["sha256"]
print(json.dumps({**verification, "payload_count": len(payloads), "seal_sha256": digest(seal)}))

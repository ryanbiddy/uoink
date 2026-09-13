"""Copy fixed documentary bytes into a content-addressed proof; no tests."""
from pathlib import Path
import hashlib
import json

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE = BASE / "_scratch/namespace-combined-proof-proposal01"
OUT = BASE / "_scratch/namespace-combined-proof01"
INSTRUMENTS = ("BRIEF.md", "SOURCE-MEMBERS.json", "prepare_inventory.py", "build_proof.py", "verify_proof.py")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    with path.open("rb") as stream:
        raw = stream.read(1048577)
    assert len(raw) <= 1048576
    return raw


inventory = json.loads(read(HERE / "SOURCE-MEMBERS.json"))
assert inventory["logical_count"] == len(inventory["files"]) == 87
objects, logical = {}, []
for item in inventory["files"]:
    path = Path(item["source_path"])
    assert path.is_absolute() and path.is_relative_to(BASE / "_scratch")
    relative = Path(item["logical_path"])
    assert not relative.is_absolute() and ".." not in relative.parts
    raw = read(path)
    assert len(raw) == item["bytes"] and digest(raw) == item["sha256"]
    if item["sha256"] in objects:
        assert objects[item["sha256"]] == raw
    objects[item["sha256"]] = raw
    logical.append({"path": relative.as_posix(), "bytes": len(raw), "sha256": item["sha256"],
                    "object": "objects/" + item["sha256"]})
assert len(objects) == 57 and len({item["path"] for item in logical}) == 87
payloads = {"objects/" + key: raw for key, raw in objects.items()}
payloads["LOGICAL-MEMBERS.json"] = (json.dumps({"schema": "uoink.content-addressed-documentary.v1",
    "logical_count": len(logical), "files": logical}, indent=2) + "\n").encode()
payloads[".gitattributes"] = b"* -text\n"
payloads["VERDICT.md"] = read(HERE / "VERDICT.md")
for name in INSTRUMENTS:
    payloads["instruments/" + name] = read(HERE / name)
assert len(payloads) == 65 and not OUT.exists()
OUT.mkdir()
for name, raw in sorted(payloads.items()):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
rows = [{"path": name, "bytes": len(raw), "sha256": digest(raw)} for name, raw in sorted(payloads.items())]
manifest = {"schema": "uoink.proof-seal.v1", "payload_count": len(rows),
            "payload_bytes": sum(item["bytes"] for item in rows), "files": rows}
raw = (json.dumps(manifest, indent=2) + "\n").encode()
with (OUT / "MANIFEST.json").open("xb") as stream:
    stream.write(raw)
print(json.dumps({"proof": str(OUT), "payload_count": len(rows), "payload_bytes": manifest["payload_bytes"],
                  "logical_members": len(logical), "manifest_sha256": digest(raw), "tests_executed": 0}))

"""Copy reviewed documentary bytes only; no archived code or test execution."""
from pathlib import Path
import hashlib
import json

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
HERE = BASE / "dummy-native-combined-proof-proposal01"
OUT = BASE / "dummy-native-combined-proof01"
INVENTORY_SHA = "887eb2722416f1c153a64457b5e18b01b6279c9414280aacfb77cb353208dd08"
INSTRUMENTS = ("BRIEF.md", "SOURCE-MEMBERS.json", "prepare_inventory.py", "build_proof.py", "verify_proof.py")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    assert path.is_file() and not path.is_symlink()
    with path.open("rb") as stream:
        raw = stream.read(1048577)
    assert len(raw) <= 1048576
    return raw


def relative(name):
    assert type(name) is str and name and ":" not in name and "\\" not in name
    parts = name.split("/")
    assert all(part not in ("", ".", "..") for part in parts)
    return Path(*parts)


inventory_raw = read(HERE / "SOURCE-MEMBERS.json")
assert digest(inventory_raw) == INVENTORY_SHA
inventory = json.loads(inventory_raw)
assert inventory["logical_count"] == len(inventory["files"]) == 169
objects, logical = {}, []
for item in inventory["files"]:
    name = relative(item["logical_path"])
    path = BASE / name
    assert path == Path(item["source_path"])
    raw = read(path)
    assert len(raw) == item["bytes"] and digest(raw) == item["sha256"]
    raw.decode("utf-8-sig")
    if item["sha256"] in objects:
        assert objects[item["sha256"]] == raw
    objects[item["sha256"]] = raw
    logical.append({"path": name.as_posix(), "bytes": len(raw), "sha256": item["sha256"],
                    "object": "objects/" + item["sha256"]})
assert len(objects) == 111 and len({item["path"] for item in logical}) == 169
assert sum(item["bytes"] for item in logical) == 1287807
payloads = {"objects/" + key: raw for key, raw in objects.items()}
payloads["LOGICAL-MEMBERS.json"] = (json.dumps({"schema": "uoink.content-addressed-documentary.v1",
    "logical_count": len(logical), "files": logical}, indent=2) + "\n").encode()
payloads[".gitattributes"] = b"* -text\n"
payloads["VERDICT.md"] = read(HERE / "VERDICT.md")
for name in INSTRUMENTS:
    payloads["instruments/" + name] = read(HERE / name)
assert len(payloads) == 119 and not OUT.exists()
OUT.mkdir()
for name, raw in sorted(payloads.items()):
    path = OUT / relative(name)
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
                  "logical_members": len(logical), "manifest_sha256": digest(raw), "tests_or_native_runs_executed": 0}))

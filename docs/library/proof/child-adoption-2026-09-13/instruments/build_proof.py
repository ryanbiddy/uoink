"""Copy and seal fixed documentary text; never execute archived source."""
from pathlib import Path
import hashlib
import json

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
HERE = BASE / "child-adoption-proof-proposal01"
OUT = BASE / "child-adoption-proof01"
INVENTORY_SHA = "9f33499b1c143f79cb6e85009c266d80fe3d9a87ea44f8bf283025da6fe8a44c"
INSTRUMENTS = ("BRIEF.md", "SOURCE-MEMBERS.json", "prepare_inventory.ps1", "build_proof.py", "verify_proof.py")


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


def encoded(value):
    return (json.dumps(value, indent=2) + "\n").encode()


inventory_raw = read(HERE / "SOURCE-MEMBERS.json")
assert digest(inventory_raw) == INVENTORY_SHA
inventory = json.loads(inventory_raw)
assert inventory["logical_count"] == len(inventory["files"]) == 103
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
                    "object": "objects/" + item["sha256"] + ".txt"})
assert len(objects) == inventory["distinct_objects"] == 70
assert len({item["path"] for item in logical}) == 103
assert sum(item["bytes"] for item in logical) == inventory["logical_bytes"] == 838755
payloads = {"objects/" + key + ".txt": raw for key, raw in objects.items()}
payloads["SOURCE-TREE.json"] = encoded({"schema": "uoink.content-addressed-documentary.v1",
    "logical_count": len(logical), "files": logical})
payloads[".gitattributes"] = b"* -text\n"
payloads["VERDICT.md"] = read(HERE / "VERDICT.md")
for name in INSTRUMENTS:
    payloads["instruments/" + name] = read(HERE / name)
assert len(payloads) == 78 and not OUT.exists()
OUT.mkdir()
for name, raw in sorted(payloads.items()):
    path = OUT / relative(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
actual = {p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file()}
assert actual == set(payloads)
for name, raw in payloads.items():
    assert read(OUT / relative(name)) == raw
copy_receipt = encoded({"schema": "uoink.documentary-copy-verification.v1",
    "physical_payloads_checked": 78, "logical_members": 103, "distinct_objects": 70,
    "logical_bytes": 838755, "exact_file_set": True, "exact_copy_bytes": True,
    "source_inventory_sha256": INVENTORY_SHA, "tests_or_native_runs_executed": 0})
payloads["COPY-VERIFICATION.json"] = copy_receipt
with (OUT / "COPY-VERIFICATION.json").open("xb") as stream:
    stream.write(copy_receipt)
assert len(payloads) == 79
rows = [{"path": name, "bytes": len(raw), "sha256": digest(raw)} for name, raw in sorted(payloads.items())]
manifest = {"schema": "uoink.proof-seal.v1", "payload_count": len(rows),
    "payload_bytes": sum(row["bytes"] for row in rows), "files": rows}
manifest_raw = encoded(manifest)
with (OUT / "MANIFEST.json").open("xb") as stream:
    stream.write(manifest_raw)
assert {p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file()} == set(payloads) | {"MANIFEST.json"}
print(json.dumps({"proof": str(OUT), "payload_count": 79, "logical_members": 103,
    "distinct_objects": 70, "manifest_sha256": digest(manifest_raw), "tests_or_native_runs_executed": 0}))

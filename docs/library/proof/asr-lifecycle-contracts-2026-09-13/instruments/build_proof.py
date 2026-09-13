"""Documentary copy only. No copied source is imported or executed."""
import hashlib
import json
from pathlib import Path, PurePosixPath

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
PREP = BASE / "lifecycle-combined-proof-proposal01"
OUTPUT = BASE / "lifecycle-combined-proof01"
ROOTS = {
    "author01": BASE / "asr-windows-lifecycle-proposal01",
    "author02": BASE / "asr-windows-lifecycle-proposal02",
    "startup-diagnostic": BASE / "asr-lifecycle-startup-diagnostic01",
    "root-independent": BASE / "astra-asr-lifecycle-qualification02",
    "unexecuted-copy-proposal": BASE / "lifecycle-root-copy-proposal01",
}


def relative(value):
    if type(value) is not str or "\\" in value or ":" in value or "\x00" in value:
        raise ValueError("Archive path refused")
    parts = PurePosixPath(value).parts
    if not parts or value.startswith("/") or any(item in (".", "..") for item in parts):
        raise ValueError("Archive path refused")
    return Path(*parts)


def read_text_bytes(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Regular text input required")
    with path.open("rb") as stream:
        data = stream.read(1048577)
    if len(data) > 1048576 or b"\x00" in data:
        raise ValueError("Text input bound refused")
    data.decode("utf-8-sig")
    return data


source_manifest = read_text_bytes(PREP / "SOURCE-MEMBERS.json")
inventory = json.loads(source_manifest)
rows = inventory["files"]
if len(rows) != inventory["count"] or len({row["archive_path"] for row in rows}) != len(rows):
    raise ValueError("Source membership refused")
prepared = []
for row in rows:
    if row["group"] not in ROOTS:
        raise ValueError("Unrecognized source group")
    source = ROOTS[row["group"]] / relative(row["path"])
    expected_target = row["group"] + "/" + row["path"]
    if row["archive_path"] != expected_target:
        raise ValueError("Archive mapping refused")
    data = read_text_bytes(source)
    if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise ValueError("Pinned documentary input changed")
    prepared.append((row["archive_path"], data, source, row["sha256"]))
for name in ("SOURCE-MEMBERS.json", "build_proof.py", "verify_proof.py", "BRIEF.md", "VERDICT.md"):
    prepared.append(("instruments/" + name, read_text_bytes(PREP / name), None, None))
prepared.extend([(".gitattributes", b"* -text\n", None, None),
                 ("VERDICT.md", read_text_bytes(PREP / "VERDICT.md"), None, None)])
if OUTPUT.exists():
    raise ValueError("Fresh documentary output required")
OUTPUT.mkdir()
manifest = []
for name, data, source, source_hash in prepared:
    destination = OUTPUT / relative(name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(data)
    actual = read_text_bytes(destination)
    if actual != data:
        raise ValueError("Documentary copy bytes changed")
    if source is not None and hashlib.sha256(read_text_bytes(source)).hexdigest() != source_hash:
        raise ValueError("Source changed during documentary copy")
    manifest.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
manifest.sort(key=lambda row: row["path"])
seal = {"schema": "uoink.lifecycle-combined-proof.v1", "count": len(manifest),
        "bytes": sum(row["bytes"] for row in manifest), "files": manifest}
seal_bytes = (json.dumps(seal, indent=2) + "\n").encode("utf-8")
with (OUTPUT / "SHA256-MANIFEST.json").open("xb") as stream:
    stream.write(seal_bytes)
print(json.dumps({"path": str(OUTPUT), "count": seal["count"], "bytes": seal["bytes"],
                  "manifest_sha256": hashlib.sha256(seal_bytes).hexdigest(), "tests_executed": 0}, indent=2))

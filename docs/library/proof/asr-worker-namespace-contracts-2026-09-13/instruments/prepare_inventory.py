"""Collect only fixed documentary paths; no source execution."""
from pathlib import Path
import hashlib
import json

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE = BASE / "_scratch/namespace-combined-proof-proposal01"
AUTHOR = BASE / "_scratch/asr-worker-namespace-proposal01"
ROOT = BASE / "_scratch/astra-worker-namespace-qualification01"
COPY = BASE / "_scratch/namespace-root-copy-proposal01"
SEAL = "412ff1c34376f0ce156c055e27afc66e9d19ed3ed7358f939e7f8df1b526f02f"


def read(path):
    with path.open("rb") as stream:
        raw = stream.read(1048577)
    assert len(raw) <= 1048576
    return raw


raw = read(AUTHOR / "MANIFEST.json")
assert hashlib.sha256(raw).hexdigest() == SEAL
seal = json.loads(raw)
assert seal["payload_count"] == len(seal["files"]) == 37
paths = [("preparation/" + item["path"], AUTHOR / item["path"]) for item in seal["files"]]
paths.append(("preparation/MANIFEST.json", AUTHOR / "MANIFEST.json"))
for prefix, directory in (("author-run", AUTHOR / "runs/nsp01"), ("root-inputs", ROOT),
                          ("root-run", ROOT / "runs/nsp01"), ("root-copy", COPY)):
    for path in sorted(directory.iterdir()):
        if path.is_file():
            assert path.suffix in (".py", ".ps1", ".json", ".md", ".log")
            paths.append((prefix + "/" + path.name, path))
rows = []
for logical, path in paths:
    raw = read(path)
    rows.append({"logical_path": logical, "source_path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
assert len({row["logical_path"] for row in rows}) == len(rows)
record = {"schema": "uoink.namespace-proof-source-map.v1", "logical_count": len(rows),
          "logical_bytes": sum(row["bytes"] for row in rows), "files": rows}
with (HERE / "SOURCE-MEMBERS.json").open("xb") as stream:
    stream.write((json.dumps(record, indent=2) + "\n").encode())
print(json.dumps({"logical_count": len(rows), "logical_bytes": record["logical_bytes"],
                  "unique_objects": len({row["sha256"] for row in rows}), "candidate_executed": False}))

"""Inventory only the named text proof roots; no candidate imports or tests."""
from pathlib import Path
import hashlib
import json

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
HERE = BASE / "dummy-native-combined-proof-proposal01"
ROOTS = tuple("asr-dummy-worker-flow-proposal" + number for number in ("01", "02", "03", "04")) + tuple("asr-dummy-worker-native" + number for number in ("01", "02", "03", "04"))
EXTRA = tuple("DUMMY-NATIVE" + number + "-ACTUAL.json" for number in ("01", "02", "03", "04")) + (
    "root_verify_native04_graph01.py", "NATIVE04-GRAPH01-ROOT-VERIFY-ACTUAL.json",
    "asr-worker-namespace-proposal01/MANIFEST.json")


def read(path):
    assert path.is_file() and not path.is_symlink()
    with path.open("rb") as stream:
        raw = stream.read(1048577)
    assert len(raw) <= 1048576
    raw.decode("utf-8-sig")
    return raw


rows = []
for directory in ROOTS:
    root = BASE / directory
    assert root.is_dir() and not root.is_symlink()
    for path in sorted(root.rglob("*")):
        assert not path.is_symlink()
        if not path.is_file():
            continue
        assert path.suffix in (".py", ".ps1", ".txt", ".json", ".md", ".diff", ".log") or path.name == ".gitattributes"
        raw = read(path)
        rows.append({"logical_path": path.relative_to(BASE).as_posix(), "source_path": str(path),
                     "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
for name in EXTRA:
    path = BASE / name
    raw = read(path)
    rows.append({"logical_path": name, "source_path": str(path), "bytes": len(raw),
                 "sha256": hashlib.sha256(raw).hexdigest()})
rows.sort(key=lambda row: row["logical_path"])
assert len(rows) == len({row["logical_path"] for row in rows})
assert len(rows) <= 220 and sum(row["bytes"] for row in rows) <= 4 * 1048576
output = {"schema": "uoink.native-documentary-source-members.v1", "logical_count": len(rows),
          "logical_bytes": sum(row["bytes"] for row in rows), "distinct_objects": len({row["sha256"] for row in rows}),
          "files": rows, "model_binary_or_dependency_files_included": False}
raw = (json.dumps(output, indent=2) + "\n").encode()
with (HERE / "SOURCE-MEMBERS.json").open("xb") as stream:
    stream.write(raw)
print(json.dumps({key: value for key, value in output.items() if key != "files"} | {"inventory_sha256": hashlib.sha256(raw).hexdigest()}))

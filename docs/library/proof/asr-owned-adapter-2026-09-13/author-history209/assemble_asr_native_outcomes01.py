"""Copy only named source/documentary receipts and their immutable seals."""
import hashlib
import json
from pathlib import Path

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
SRC = BASE / "_scratch/asr-native-exit-scope-repair01"
OUT = BASE / "_scratch/asr-native-exit-instrument-outcomes01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(name, raw):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw if isinstance(raw, bytes) else raw.encode())


def write_json(name, value):
    write(name, json.dumps(value, indent=2) + "\n")


seal_records = []
for label, folder, expected in (
    ("preparation-repair01", BASE / "_scratch/asr-production-adapter-qualification-repair01",
     "34e4a40216547273f5813fa55dbf7affbc369173c68fd8e4e3e5c7b442a2817e"),
    ("preparation-instrument01", BASE / "_scratch/asr-production-adapter-instrument-check01",
     "4e52a3ab54dffe52d45c6ca96fad9d23d1d1ee832eca93b1cb98f5492c56bcde"),
    ("preparation-scope01", SRC,
     "5091c12977221db2be213e3498e5ea0e66b1f7c70e7ee5dd5ca9bae0f1780391")):
    seal_raw = (folder / "SHA256.json").read_bytes()
    assert sha(seal_raw) == expected
    seal = json.loads(seal_raw)
    for row in seal["files"]:
        raw = (folder / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
        write(label + "/" + row["path"], raw)
    write(label + "/SHA256.json", seal_raw)
    seal_records.append({"archive_child": label, "manifest_sha256": expected, "payload_count": seal["payload_count"],
                         "payload_bytes": seal["payload_bytes"], "all_original_bytes_verified": True})

def copy_tree(source, destination, expected_count):
    paths = [path for path in sorted(source.rglob("*")) if path.is_file()]
    assert len(paths) == expected_count, (str(source), len(paths))
    for path in paths:
        write(destination + "/" + path.relative_to(source).as_posix(), path.read_bytes())
    return len(paths)


diagnostic_count = copy_tree(SRC / "runs/scope01", "root-diagnostic01", 14)
missing_count = copy_tree(SRC / "instrument02/runs/instrument02/missing02", "subset02/runs/instrument02/missing02", 5)
success_count = copy_tree(SRC / "instrument02/runs/instrument02/success02", "subset02/runs/instrument02/success02", 9)
for name in ("ACTUAL-TOOL-MISSING02.json", "ACTUAL-TOOL-SUCCESS02.json", "ACTUAL-TOOL-SUCCESS02-CHECK.json",
             "ACTUAL-TOOL-GUARDS01.json", "ACTUAL-TOOL-GUARDS01-CHECK.json", "MISSING02-RECEIPT-CHECK.json",
             "SUCCESS02-RECEIPT-CHECK.json", "GUARDS01-RECEIPT-CHECK.json", "guards-stdout.json", "guards-stderr.log"):
    write("subset02/" + name, (SRC / "instrument02" / name).read_bytes())
author_count = copy_tree(SRC / "candidate/adapter-preflight03", "asr-author03/adapter-preflight03", 21)
for name in ("ROOT-ADMISSION.md", "ACTUAL-TOOL-PREFLIGHT03.json", "ACTUAL-TOOL-PREFLIGHT03-CHECK.json", "PREFLIGHT03-RECEIPT-CHECK.json"):
    write("asr-author03/" + name, (SRC / "candidate" / name).read_bytes())
write("root-history/ASR-SCOPE-ROOT-PREFLIGHT-REPAIR01.md", (BASE / "_scratch/ASR-SCOPE-ROOT-PREFLIGHT-REPAIR01.md").read_bytes())
write_json("COPY-VERIFICATION.json", {"date": "2026-09-13", "unchanged_preparation_seals": seal_records,
           "root_diagnostic_files": diagnostic_count, "subset_missing_files": missing_count,
           "subset_success_files": success_count, "author_run_files": author_count,
           "source_seals_copied_by_list_not_growing_directory": True,
           "actual_author_asr_cases": 58, "actual_author_asr_passed": 58, "actual_author_asr_failed": 0,
           "original_instrument_failure_retained": True,
           "scope": "Documentary copy only; no execution or asset access"})
write(".gitattributes", "* -text\n")
write("assemble_asr_native_outcomes01.py", Path(__file__).read_bytes())
rows = []
for path in sorted(OUT.rglob("*")):
    if path.is_file():
        raw = path.read_bytes()
        rows.append({"path": path.relative_to(OUT).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
assert not any(row["path"] == "SHA256.json" for row in rows)
write_json("SHA256.json", {"schema": "uoink.asr-native-instruments-and-author-qualification.v1",
          "date": "2026-09-13", "payload_count": len(rows), "payload_bytes": sum(row["bytes"] for row in rows),
          "author_asr_cases": 58, "author_passed": 58, "author_failed": 0,
          "root_independent_asr_repetition_included": False, "files": rows})
print(json.dumps({"payload_count": len(rows), "payload_bytes": sum(row["bytes"] for row in rows),
                  "manifest_sha256": sha((OUT / "SHA256.json").read_bytes())}))

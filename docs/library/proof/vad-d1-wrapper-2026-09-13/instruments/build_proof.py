"""Bounded documentary copy/ZIP seal; never run any archived program."""
from datetime import datetime, timezone
import encodings.cp437
import encodings.utf_8_sig
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
WORK = BASE / "vad-d1-wrapper-combined-seal01"
AUTHOR = BASE / "vad-d1-dormant-invocation-repair01"
ROOT = BASE / "astra-d1-wrapper-qualification01"
DEST = BASE / "vad-d1-wrapper-combined-proof01"
ROOT_PREPARER = BASE / "prepare_astra_d1_wrapper_qualification01.py"
FORBIDDEN = r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN
assert not DEST.exists()

# Only this original documentary verifier is loaded. Evidence .py/.ps1 files
# are bytes throughout; no D1 or qualification source enters an evaluator.
verifier_raw = (WORK / "verify_proof.py").read_bytes()
namespace = {"__name__": "documentary_verifier", "__file__": str(WORK / "verify_proof.py")}
exec(compile(verifier_raw, namespace["__file__"], "exec"), namespace)
need, sha, decode = namespace["need"], namespace["sha"], namespace["decode"]
bounded, inventory = namespace["bounded"], namespace["inventory"]


def no_links(path):
    for part in (*reversed(path.parents), path):
        item = part.lstat()
        need(not stat.S_ISLNK(item.st_mode) and not getattr(item, "st_file_attributes", 0) & 0x400, "Linked documentary source/root")


for root in (WORK, AUTHOR, ROOT):
    no_links(root)
no_links(ROOT_PREPARER)
author_names, root_names = inventory(AUTHOR), inventory(ROOT)
prep_raw = bounded(AUTHOR / "SHA256.json")
author_seal_raw = bounded(AUTHOR / "wrapper-preflight01/RUN-SHA256.json")
need(sha(prep_raw) == namespace["PREP_SHA"] and sha(author_seal_raw) == namespace["AUTHOR_SHA"], "Original seal identity differs")
prep, author_seal = decode(prep_raw), decode(author_seal_raw)
prep_names = {namespace["relpath"](row["path"]) for row in prep["files"]}
author_run_names = {namespace["relpath"](row["path"]) for row in author_seal["files"]} | {"RUN-SHA256.json"}
need(len(prep_names) == 26 and len(author_run_names) == 210, "Original seal membership count")
expected_author = prep_names | {"SHA256.json"} | {"wrapper-preflight01/" + name for name in author_run_names}
need(author_names == expected_author, "Unclassified author payload: " + repr(sorted(author_names ^ expected_author)))
root_bindings_raw = bounded(ROOT / "COPY-BINDINGS.json")
root_bindings = decode(root_bindings_raw)
root_copy_names = {namespace["relpath"](row["name"]) for row in root_bindings} | {"ROOT-ADMISSION.md", "COPY-BINDINGS.json"}
root_run_names = {name.removeprefix("wrapper-preflight01/") for name in root_names if name.startswith("wrapper-preflight01/")}
need(len(root_copy_names) == 14 and len(root_run_names) == 208, "Root requested membership count differs")
need(root_names == root_copy_names | {"wrapper-preflight01/" + name for name in root_run_names}, "Unclassified root-copy file")
need(root_run_names == author_run_names - {"OUTCOME.md", "RUN-SHA256.json"}, "Root run has unexpected or missing raw records")

records, virtual, raw_by_source = [], {}, {}


def add(source, logical, group):
    logical = namespace["relpath"](logical)
    need(str(source) not in raw_by_source and logical not in virtual, "Duplicate source/destination")
    no_links(source)
    raw = bounded(source)
    raw_by_source[str(source)] = raw
    virtual[logical] = raw
    row = {"source": str(source), "logical_path": logical, "source_group": group,
           "bytes": len(raw), "sha256": sha(raw)}
    if logical.startswith(("author-run/cases/", "root-run/cases/")):
        row.update(storage="zip", member=logical)
    else:
        row.update(storage="file", destination=logical)
    records.append(row)


for name in sorted(prep_names):
    add(AUTHOR / name, "preparation/" + name, "original-26-payload-preparation")
add(AUTHOR / "SHA256.json", "preparation/original-SHA256.json", "unchanged-original-preparation-manifest")
for name in sorted(author_run_names):
    logical = "author-run/original-RUN-SHA256.json" if name == "RUN-SHA256.json" else "author-run/" + name
    add(AUTHOR / "wrapper-preflight01" / name, logical, "unchanged-author-run-manifest" if name == "RUN-SHA256.json" else "original-209-payload-author-run")
for name in sorted(root_copy_names):
    add(ROOT / name, "root-copy/" + name, "separate-root-copy-and-admission")
for name in sorted(root_run_names):
    add(ROOT / "wrapper-preflight01" / name, "root-run/" + name, "separate-root-independent-run")
add(ROOT_PREPARER, "root-preparation/prepare_astra_d1_wrapper_qualification01.py", "separate-root-preparer-source")
need(len(records) == 460 and len(virtual) == 460 and sum(len(raw) for raw in virtual.values()) <= 4 * 1024 * 1024, "Documentary source bounds")
namespace["check_original"](prep_raw, "preparation", virtual, 26, namespace["PREP_SHA"])
namespace["check_original"](author_seal_raw, "author-run", virtual, 209, namespace["AUTHOR_SHA"])
summary = namespace["check_runs"](virtual)
need(sha(virtual["root-preparation/prepare_astra_d1_wrapper_qualification01.py"]) == "abc5d3fa14ca7d5973fd0e9d174acd0b4a6ee38af8a07c20eb4db0c20cffa211", "Root preparer identity differs")

DEST.mkdir(exist_ok=False)


def write(name, raw):
    path = DEST / namespace["relpath"](name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        need(stream.write(raw) == len(raw), "Short documentary copy")
    need(bounded(path) == raw, "Copied documentary bytes differ")


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


for row in records:
    if row["storage"] == "file":
        write(row["destination"], virtual[row["logical_path"]])
archive_records = sorted((row for row in records if row["storage"] == "zip"), key=lambda row: row["member"])
need(len(archive_records) == 370, "Exact two case-tree member count")
archive_buffer = io.BytesIO()
with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as zipped:
    for row in archive_records:
        raw = virtual[row["logical_path"]]
        need(len(raw) <= 128 * 1024, "Case member size bound")
        info = zipfile.ZipInfo(row["member"], (1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_STORED
        zipped.writestr(info, raw)
write("case-trees.zip", archive_buffer.getvalue())
write("SOURCE-MAP.json", encoded({"source_file_count": len(records), "files": sorted(records, key=lambda row: row["logical_path"])}))
write("ZIP-MEMBERS.json", encoded({"archive": "case-trees.zip", "method": "ZIP_STORED", "member_count": 370,
     "members": [{key: row[key] for key in ("member", "source", "bytes", "sha256")} for row in archive_records]}))
write("COMPARISON.json", encoded({**summary, "comparison_method": "direct decoded ordered case-array equality and per-case raw exit checks; no program rerun",
     "author_elapsed_seconds": 5.7517623, "root_elapsed_seconds": 5.657456,
     "preparation_original_manifest_sha256": namespace["PREP_SHA"], "author_original_manifest_sha256": namespace["AUTHOR_SHA"]}))
write("ROOT-REPORTED-TOOL-FACTS.json", encoded({"provenance": "Transcribed from root's message; these are not fabricated raw tool receipts",
    "root_preparer": {"tool_chunk": "3a6a49", "exit_code": 0, "wall_seconds": 0.1668442, "prepared_files": 12,
        "reported_launcher_sha256": "d70833c44ba1cbe5b482d8b59924f223b5a18c6fdf869892e8bbedea4d6e74a5"},
    "root_prior_comparison": {"tool_chunk": "6b7aa2", "exit_code": 0, "wall_seconds": 0.10386,
        "method_reported": "Ordered case records compared after ConvertToJson; no separate file existed"},
    "new_direct_comparison": "COMPARISON.json"}))
write(".gitattributes", b"* -text\n")
for name in ("BRIEF.md", "build_proof.py", "verify_proof.py", "run_sealer.ps1", "README.md"):
    write("instruments/" + name, bounded(WORK / name))
write("README.md", bounded(WORK / "README.md"))

# Recheck every source against the snapshot. No source is modified or executed.
for source, raw in raw_by_source.items():
    need(bounded(Path(source)) == raw, "Original source changed while sealing")
need(inventory(AUTHOR) == author_names and inventory(ROOT) == root_names, "Source membership changed while sealing")
payload_names = inventory(DEST)
payload_rows = [{"path": name, "bytes": len(raw := bounded(DEST / name)), "sha256": sha(raw)} for name in sorted(payload_names)]
manifest = {"schema": "uoink.documentary-payload-manifest.v1", "sealed_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "combined completed inert D1-wrapper qualification evidence", "payload_count": len(payload_rows),
    "payload_bytes": sum(row["bytes"] for row in payload_rows), "source_file_count": 460, "case_archive_members": 370, "files": payload_rows}
write("SHA256.json", encoded(manifest))
checked = namespace["verify"](DEST)
print(json.dumps({"proof": str(DEST), **checked}, indent=2))

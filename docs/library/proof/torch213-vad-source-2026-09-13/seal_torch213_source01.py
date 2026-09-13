"""Documentary copy/hash only. Never import or execute collected source."""
import hashlib
import json
from pathlib import Path
import stat

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
SCRATCH = ROOT / "_scratch"
PROPOSAL = SCRATCH / "torch213-vad-source-proposal01"
REVIEW = SCRATCH / "torch213-vad-compatibility01"
INDEPENDENT = SCRATCH / "astra-torch-collector-synthetic01"
DEST = SCRATCH / "torch213-vad-source-final-proof01"
PINNED = {
    PROPOSAL / "collect_torch_text.py": "6971aa91d430f0b43f3a3215d2dfe8a0c467b234ead827d311b1323b348fdc93",
    PROPOSAL / "qualify_collector.py": "1186f6d1fb0bad848fcb5e662791350db7a1fa6c7e65e280b7806ece537b222e",
    PROPOSAL / "run_sources01.ps1": "ec9feeed745dfdf60ca5e6f8af1b65c03fbbc32f1373d20b9c638bad19df6557",
    PROPOSAL / "SOURCES01-PROTOCOL.md": "87ae878796ebc26f2ec032f7308a94cfa9ee1b3aeb45eacbfd2a9b03ca15b892",
    PROPOSAL / "SOURCES01-URLS.json": "513e3f2f8f90e24d11b9b6ddd6cd83b88877de93ecd399f29e02805dfbf43b44",
    REVIEW / "COMPATIBILITY-REVIEW.md": "09ec1a44869e790c032ce0999ad8aa27dfb99f7873149eeeabdc1bf0fc66544d",
    REVIEW / "BACKEND-IMPORT-CONDITION-REPAIR-BRIEF.md": "edacbf54d0862080e4bf269f0b649e72ef1772556601f609931238f4e4008954",
    ROOT / "docs/library/proof/vad-selected-metadata-map-2026-09-13/SHA256.json": "c67d091287456999f95ff9f93dd81d39ca96c2f98d35d678092b5c9fe72dd80d",
}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def regular(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Reparse or symlink input refused")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Non-regular input refused")
    if info.st_size > 4 * 1024 * 1024:
        raise ValueError("Documentary input exceeds per-file bound")
    return info

def read(path):
    before = regular(path)
    data = path.read_bytes()
    after = regular(path)
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or len(data) != after.st_size:
        raise ValueError("Documentary input changed while reading")
    return data

def parsed(path):
    return json.loads(read(path).decode("utf-8-sig"))

def tree_files(path):
    found = []
    for child in sorted(path.rglob("*")):
        info = child.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Reparse or symlink tree member refused")
        if stat.S_ISREG(info.st_mode):
            found.append(child)
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError("Non-file tree member refused")
    return found

def write_json(path, value):
    with path.open("xb") as target:
        target.write((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

def main():
    if DEST.exists():
        raise ValueError("Fresh proof path required")
    for source, expected in PINNED.items():
        if digest(read(source)) != expected:
            raise ValueError("Pinned documentary input changed")
    comparison = parsed(PROPOSAL / "INDEPENDENT-CASE-COMPARISON02.json")
    if comparison["exact_ordered_case_records_equal"] is not True or comparison["distinct_cases"] != 40 or comparison["native_exits"] != [0, 0] or comparison["actual_outer_exits"] != [0, 0]:
        raise ValueError("Synthetic comparison facts mismatch")
    for label, count, size in (("resolve01", 2, 6257), ("sources01", 21, 1050728)):
        receipt = parsed(PROPOSAL / "retrievals" / label / "receipt.json")
        exit_receipt = parsed(PROPOSAL / (label + "-launch") / "exit.json")
        if receipt["intended_exit"] != 0 or receipt["response_body_bytes"] != size or receipt["binding"]["commit"] != "cf30153c4c131c8164ee7798e5022d810682e2cb" or exit_receipt["native_exit"] != 0 or exit_receipt["inputs_unchanged"] is not True:
            raise ValueError("Collected source facts mismatch")
        response_paths = sorted((PROPOSAL / "retrievals" / label).glob("response-*.json"))
        if len(response_paths) != count:
            raise ValueError("Response file membership mismatch")
        if len(receipt["requests"]) != count:
            raise ValueError("Receipt response membership mismatch")
        for response_path, recorded in zip(response_paths, receipt["requests"], strict=True):
            response = parsed(response_path)
            if response != recorded or response["http_status"] != 200 or response["body_complete"] is not True or response["truncated"] is not False:
                raise ValueError("Response receipt facts mismatch")
            data = read(response_path.parent / response["body_file"])
            if len(data) != response["body_bytes"] or digest(data) != response["body_sha256"]:
                raise ValueError("Recorded response body changed")
        launch_dir = PROPOSAL / (label + "-launch")
        for item in parsed(launch_dir / "plan.json")["inputs"]:
            if digest(read(Path(item["source"]))) != item["sha256"] or digest(read(launch_dir / item["name"])) != item["sha256"]:
                raise ValueError("Admitted launch input changed")
    sources = []
    for directory, prefix in ((PROPOSAL, "proposal"), (REVIEW, "review"), (INDEPENDENT, "independent")):
        sources.extend((source, Path(prefix) / source.relative_to(directory)) for source in tree_files(directory))
    for item in parsed(PROPOSAL / "INPUT-BINDINGS.json")["bindings"]:
        source = ROOT / item["path"]
        data = read(source)
        if len(data) != item["bytes"] or digest(data) != item["sha256"]:
            raise ValueError("Retained comparison source mismatch")
        sources.append((source, Path("retained-inputs") / (item["key"] + ".txt")))
    for name in ("ASTRA-TORCH-RESOLVE01-ADMISSION-2026-09-13.md", "ASTRA-TORCH-SOURCES01-ADMISSION-2026-09-13.md"):
        sources.append((SCRATCH / name, Path("root-admissions") / name))
    sources.append((ROOT / "docs/library/proof/vad-selected-metadata-map-2026-09-13/SHA256.json", Path("retained-inputs/original-metadata-proof-SHA256.json")))
    sources.append((Path(__file__), Path("seal_torch213_source01.py")))
    if len(sources) > 400 or len({str(relative) for _, relative in sources}) != len(sources):
        raise ValueError("Unexpected documentary source membership")
    DEST.mkdir()
    copies = []
    total = 0
    for source, relative in sources:
        data = read(source)
        total += len(data)
        if total > 16 * 1024 * 1024:
            raise ValueError("Documentary copy bound exceeded")
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(data)
        if read(target) != data or read(source) != data:
            raise ValueError("Documentary exact copy failed")
        copies.append({"original": str(source), "path": relative.as_posix(), "bytes": len(data), "sha256": digest(data)})
    with (DEST / ".gitattributes").open("xb") as output:
        output.write(b"* -text\n")
    expected_pre_verification = {item["path"] for item in copies} | {".gitattributes"}
    if {p.relative_to(DEST).as_posix() for p in tree_files(DEST)} != expected_pre_verification:
        raise ValueError("Unexpected pre-seal file set")
    write_json(DEST / "COPY-VERIFICATION.json", {"scope": "Exact documentary byte copies; no source execution or new tests", "copied_files": len(copies), "all_copies_and_originals_match": True, "copied_file_records": copies, "verification_precedes_outer_seal": True})
    records = []
    for path in tree_files(DEST):
        data = read(path)
        records.append({"path": path.relative_to(DEST).as_posix(), "bytes": len(data), "sha256": digest(data)})
    manifest = DEST / "SHA256.json"
    write_json(manifest, {"schema": 1, "scope": "Torch 2.13 public text collection and fixed-factory source review; no runtime acceptance", "payload_count": len(records), "excluded": ["SHA256.json"], "files": records})
    expected = {item["path"] for item in records} | {"SHA256.json"}
    if {p.relative_to(DEST).as_posix() for p in tree_files(DEST)} != expected:
        raise ValueError("Final proof has missing or unlisted files")
    for item in records:
        data = read(DEST / item["path"])
        if len(data) != item["bytes"] or digest(data) != item["sha256"]:
            raise ValueError("Final payload verification failed")
    print(json.dumps({"seal_exit": 0, "proof_path": str(DEST), "payload_count": len(records), "total_file_count": len(records) + 1, "payload_bytes": sum(item["bytes"] for item in records), "manifest_sha256": digest(read(manifest)), "all_payload_hashes_match": True, "no_unlisted_files": True}, indent=2))

if __name__ == "__main__":
    main()

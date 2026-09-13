"""Copy only approved sealed documentary evidence; execute no captured code."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys


def deny_runtime(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "ctypes.dlopen"}:
        raise RuntimeError("Documentary seal forbids network, children and native loads")


sys.addaudithook(deny_runtime)
ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
SCRATCH = ROOT / "_scratch"
OUT = ROOT / "docs/library/proof/runtime-security-scope-2026-09-13"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe(root, relative):
    path = root / relative
    require(not Path(relative).is_absolute() and ".." not in Path(relative).parts, "Unsafe relative path")
    require(path.resolve(strict=True).is_relative_to(root.resolve()), "Source outside approved directory")
    for item in [path, *path.parents]:
        require(not item.is_symlink() and not (getattr(item.lstat(), "st_file_attributes", 0) & 1024), "Reparse path refused")
        if item == root:
            break
    require(path.is_file(), "Expected documentary source file")
    require(path.suffix.lower() not in {".db", ".sqlite", ".sqlite3", ".env", ".exe", ".dll", ".whl", ".pth", ".pt", ".binmodel"}, "Non-documentary file refused")
    return path


def load_original(folder, expected_hash, count):
    manifest_path = safe(folder, "SHA256.json")
    require(digest(manifest_path) == expected_hash, "Original manifest digest mismatch")
    manifest = json.loads(manifest_path.read_bytes())
    rows = [{"file": key, **value} for key, value in manifest["files"].items()] if "files" in manifest else manifest["payloads"]
    require(len(rows) == count and len({r["file"] for r in rows}) == count, "Original payload count mismatch")
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    require(actual == {r["file"] for r in rows} | {"SHA256.json"}, "Original file membership mismatch")
    for row in rows:
        path = safe(folder, row["file"])
        require(path.stat().st_size == row["bytes"] and digest(path) == row["sha256"], "Original payload mismatch: " + row["file"])
    return rows


def main():
    require(not OUT.exists(), "Refuse to replace previous documentary seal")
    archives = [
        (SCRATCH / "runtime-candidate02-osv01", "candidate02-osv01", "ORIGINAL-CANDIDATE02-OSV-SHA256.json", "f6378453d1bc9ea432793b33ea6e2aa108b5ce868a740f9df9e79c3d79e29bf5", 31),
        (SCRATCH / "runtime-candidate03-source", "candidate03-source", "ORIGINAL-CANDIDATE03-SOURCE-SHA256.json", "00dee8e9ecbbc0b187c3884349e2374ae90447f88c28bcd1a01fba10fdec32f3", 68),
    ]
    planned = []
    for source, child, renamed, expected_hash, count in archives:
        for row in load_original(source, expected_hash, count):
            planned.append((safe(source, row["file"]), child + "/" + row["file"]))
        planned.append((safe(source, "SHA256.json"), child + "/" + renamed))
    supplements = [
        ("_scratch/RUNTIME-CANDIDATE02-OSV-REVIEW-2026-09-13.md", "reviews/RUNTIME-CANDIDATE02-OSV-REVIEW-2026-09-13.md"),
        ("_scratch/review_runtime_candidate02_osv01.py", "instruments/review_runtime_candidate02_osv01.py"),
        ("_scratch/runtime-candidate02-osv01-review.json", "reader-results/runtime-candidate02-osv01-review.json"),
        ("_scratch/runtime-candidate02-osv01-review.log", "reader-results/runtime-candidate02-osv01-review.log"),
        ("docs/library/ASTRA-RUNTIME-SECURITY-SCOPE-2026-09-13.md", "reviews/ASTRA-RUNTIME-SECURITY-SCOPE-2026-09-13.md"),
        ("_scratch/RUNTIME-SECURITY-SCOPE-SEAL-README-2026-09-13.md", "README.md"),
        ("_scratch/verify_runtime_security_scope_seal.py", "instruments/verify_runtime_security_scope_seal.py"),
        ("_scratch/seal_runtime_security_scope01.py", "instruments/seal_runtime_security_scope01.py"),
    ]
    planned.extend((safe(ROOT, relative), destination) for relative, destination in supplements)
    require(len({destination for _, destination in planned}) == len(planned), "Duplicate destination")
    before = {str(path): digest(path) for path, _ in planned}
    OUT.mkdir(parents=False, exist_ok=False)
    copies = []
    for source, destination in planned:
        target = OUT / destination
        require(target.resolve().is_relative_to(OUT.resolve()), "Copy target outside new archive")
        target.parent.mkdir(parents=True, exist_ok=True)
        require(not target.exists(), "Refuse reused payload path")
        shutil.copyfile(source, target)
        require(digest(source) == digest(target) == before[str(source)], "Copy changed bytes")
        copies.append({"source": str(source), "destination": destination, "bytes": source.stat().st_size, "source_sha256": before[str(source)], "destination_sha256": digest(target)})
    (OUT / ".gitattributes").write_bytes(b"* -text\n")
    for source, _, _, expected_hash, count in archives:
        load_original(source, expected_hash, count)
    for source, _ in planned:
        require(digest(source) == before[str(source)], "Source changed after copy")
    receipt = {"verified_utc": datetime.now(timezone.utc).isoformat(), "copied_files": len(copies), "original_payloads_verified": {"candidate02-osv01": 31, "candidate03-source": 68}, "hash_mismatches": 0, "original_archives_unchanged": True, "network_requests": 0, "captured_source_executed": False, "product_tests_run": 0, "copies": copies}
    (OUT / "COPY-VERIFICATION.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    rows = [{"file": p.relative_to(OUT).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(OUT.rglob("*")) if p.is_file()]
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "scope": "Documentary archive only; excludes this root manifest", "payload_count": len(rows), "payloads": rows}
    (OUT / "SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    for row in rows:
        require(digest(safe(OUT, row["file"])) == row["sha256"], "Root post-seal verification mismatch")
    print(json.dumps({"result": "PASS", "copied_files": len(copies), "root_payload_count": len(rows), "original_payloads_verified": {"candidate02-osv01": 31, "candidate03-source": 68}, "hash_mismatches": 0, "original_archives_unchanged": True, "root_manifest_sha256": digest(OUT / "SHA256.json")}, indent=2))


if __name__ == "__main__":
    main()

"""Read only named local evidence; never import a dependency or extract assets."""
import base64
import csv
from datetime import datetime, timezone
import difflib
import hashlib
import io
import json
from pathlib import Path
import zipfile

out = Path(__file__).resolve().parent
root = out.parents[1]
sha = lambda data: hashlib.sha256(data).hexdigest()
assert not (out / "inventory.json").exists(), "Preserve existing inventory"
bindings = []
def preserve(source, target):
    raw = source.read_bytes()
    target = out / "inputs" / target
    assert target.resolve().is_relative_to(out.resolve()) and not target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    bindings.append({"source": str(source), "file": target.relative_to(out).as_posix(),
                     "bytes": len(raw), "sha256": sha(raw)})
    return raw

selected = [
    ("docs/library/proof/runtime-graph-01-2026-09-12/pypi/faster-whisper.json", "captured-primary/faster-whisper.json"),
    ("docs/library/proof/runtime-graph-01-2026-09-12/metadata/faster_whisper-1.2.1-py3-none-any.whl.metadata", "captured-primary/faster-whisper.metadata"),
    ("docs/library/proof/runtime-graph-01-2026-09-12/fetch_summary.json", "captured-primary/fetch_summary.json"),
    ("vendor/nltk-pathsec/README.md", "precedent/README.md"),
    ("scripts/build_nltk_pathsec_wheel.py", "precedent/build_nltk_pathsec_wheel.py.txt"),
    ("scripts/prepare_nltk_pathsec_backport.py", "precedent/prepare_nltk_pathsec_backport.py.txt"),
    ("tests/test_nltk_local_wheel.py", "precedent/test_nltk_local_wheel.py.txt"),
    ("tests/test_nltk_wheel_boundaries.py", "precedent/test_nltk_wheel_boundaries.py.txt"),
    ("tests/test_installer_dependency_lock.py", "current/test_installer_dependency_lock.py.txt"),
    ("requirements-installer-lock.txt", "current/requirements-installer-lock.txt"),
    ("build.ps1", "current/build.ps1.txt"),
    ("scripts/verify_installer_lock.py", "current/verify_installer_lock.py.txt"),
    ("THIRD-PARTY-NOTICES.md", "current/THIRD-PARTY-NOTICES.md"),
    ("docs/library/RELEASE-OWNER-DECISIONS-2026-09-12.md", "current/RELEASE-OWNER-DECISIONS.md"),
    ("_scratch/runtime-asset-guard-proposal01/companion-B.py.txt", "proposal/companion-B.py.txt"),
    ("_scratch/runtime-asset-guard-proposal01/companion-B.patch.txt", "proposal/companion-B.patch.txt"),
    ("_scratch/runtime-asset-guard-proposal01/SHA256.json", "proposal/original24-SHA256.json"),
    ("_scratch/companion-b-static-qualification01/SHA256.json", "proposal/qualification46-SHA256.json"),
    ("_scratch/companion-b-combined-review01/SHA256.json", "proposal/root-review67-SHA256.json"),
    ("_scratch/companion-b-combined-review01/VERDICT.md", "proposal/root-VERDICT.md"),
    ("_scratch/python313-graph-01/python/Lib/site-packages/pip/_vendor/cachecontrol/caches/file_cache.py", "cache-key/file_cache.py.txt"),
]
for name, target in selected:
    preserve(root / name, target)

pypi = json.loads((out / "inputs/captured-primary/faster-whisper.json").read_bytes())
artifact = next(item for item in pypi["urls"] if item["filename"] == "faster_whisper-1.2.1-py3-none-any.whl")
assert artifact["size"] == 1118909 and artifact["digests"]["sha256"] == "79a66ad50688c0b794dd501dc340a736992a6342f7f95e5811be60b5224a26a7"
cache_key = hashlib.sha224(artifact["url"].encode()).hexdigest()
wheel_path = root / "_scratch/python313-graph-01/cache/http-v2"
wheel_path = wheel_path.joinpath(*cache_key[:5], cache_key + ".body")
wheel_bytes = wheel_path.read_bytes()
assert len(wheel_bytes) == artifact["size"] and sha(wheel_bytes) == artifact["digests"]["sha256"]

install_path = root / "_scratch/python313-graph-01/install-report.json"
install_bytes = install_path.read_bytes()
install = next(row for row in json.loads(install_bytes)["install"] if row["metadata"]["name"] == "faster-whisper")
install_extract = {key: install[key] for key in ("download_info", "requested", "is_direct", "is_yanked")}
install_extract["name"] = install["metadata"]["name"]
install_extract["version"] = install["metadata"]["version"]
assert install["download_info"]["url"] == artifact["url"]
assert install["download_info"]["archive_info"]["hashes"]["sha256"] == artifact["digests"]["sha256"]
(out / "install-receipt-extract.json").write_text(json.dumps({"source": str(install_path),
    "source_bytes": len(install_bytes), "source_sha256": sha(install_bytes), "faster_whisper_only": install_extract}, indent=2) + "\n", encoding="utf-8", newline="\n")

members = []
with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as wheel:
    names = wheel.namelist()
    assert len(names) == len(set(names))
    original_record = wheel.read("faster_whisper-1.2.1.dist-info/RECORD")
    records = list(csv.reader(io.StringIO(original_record.decode())))
    record_map = {row[0]: row[1:] for row in records}
    assert len(record_map) == len(records)
    for info in wheel.infolist():
        row = {"member": info.filename, "zip_bytes": info.file_size,
               "record_hash": record_map[info.filename][0], "record_bytes": record_map[info.filename][1]}
        if info.filename.endswith(".onnx"):
            row["content_read_or_extracted"] = False
            row["verification_scope"] = "Declared member metadata only; archive-wide hash verified. No model member read."
        else:
            assert info.filename.endswith(".py") or info.filename.startswith("faster_whisper-1.2.1.dist-info/")
            raw = wheel.read(info.filename)
            row.update(content_read_or_extracted=True, sha256=sha(raw))
            expected, size = record_map[info.filename]
            if not info.filename.endswith("/RECORD"):
                assert len(raw) == int(size)
                assert "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=") == expected
            target = out / "inputs/upstream-wheel-text" / (info.filename + ".txt")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            installed = root / "_scratch/python313-graph-01/python/Lib/site-packages" / info.filename
            if installed.is_file() and not info.filename.endswith("/RECORD"):
                row["retained_install_matches_wheel_member"] = installed.read_bytes() == raw
        members.append(row)

text_root = out / "inputs/upstream-wheel-text/faster_whisper"
original_source = (text_root / "transcribe.py.txt").read_bytes()
assert sha(original_source) == "5d5ffb00018561d3d529b2c72e1d9f5fff055bea725f3cccc7c6c67f5cc8ffe4"
original_version = (text_root / "version.py.txt").read_bytes()
assert original_version.count(b'__version__ = "1.2.1"') == 1
proposed_version = original_version.replace(b'__version__ = "1.2.1"', b'__version__ = "1.2.1+uoink.localassets1"')
(out / "proposed-version.py.txt").write_bytes(proposed_version)
test_original = (out / "inputs/current/test_installer_dependency_lock.py.txt").read_text(encoding="utf-8")
old_assert = '    assert locked["faster-whisper"] == "1.2.1"'
new_assert = '    assert locked["faster-whisper"] == "1.2.1+uoink.localassets1"'
assert test_original.count(old_assert) == 1
test_proposed = test_original.replace(old_assert, new_assert)
(out / "frozen-installer-lock-expectation.patch.txt").write_text("".join(difflib.unified_diff(
    test_original.splitlines(keepends=True), test_proposed.splitlines(keepends=True),
    fromfile="a/tests/test_installer_dependency_lock.py", tofile="b/tests/test_installer_dependency_lock.py")), encoding="utf-8", newline="\n")

result = {"observed_utc": datetime.now(timezone.utc).isoformat(), "evidence_bindings": bindings,
    "expected_upstream": {"filename": artifact["filename"], "url": artifact["url"], "bytes": artifact["size"], "sha256": artifact["digests"]["sha256"]},
    "observed_archive": {"path": str(wheel_path), "bytes": len(wheel_bytes), "sha256": sha(wheel_bytes),
                         "matches_captured_primary_metadata": True, "copied": False},
    "member_count": len(members), "members": members,
    "captured_source_matches_upstream_wheel_transcribe": True,
    "installed_python_source_tree_matches_checked_wheel_text": all(row.get("retained_install_matches_wheel_member", True) for row in members),
    "complete_upstream_git_or_sdist_tree_observed": False,
    "source_tree_scope": "All Python members in this wheel are retained and checked; no full upstream repository/build tree is asserted.",
    "proposed_version_source": {"member": "faster_whisper/version.py", "before_sha256": sha(original_version), "after_sha256": sha(proposed_version), "bytes": len(proposed_version)},
    "models_read_extracted_executed": False, "whole_wheel_hashed_as_opaque_bytes": True,
    "dependencies_imported_or_installed": False, "downloads_or_builds": False,
    "initial_filename_search": "No *.whl / named source archive found in scoped scratch/build/vendor; exact wheel subsequently located as URL-derived existing pip cache body.",
}
(out / "inventory.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"upstream_wheel_exact_hash_match": True, "wheel_member_count": len(members),
                  "source_matches": True, "proposed_version": result["proposed_version_source"],
                  "wheel_copied": False, "model_member_read": False}))

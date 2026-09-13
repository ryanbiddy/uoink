"""Fetch official PyPI JSON and wheel METADATA for runtime graph analysis.

Captures evidence for the current locked runtime stack (140 packages) and plausible
fixed candidate packages under docs/library/proof/runtime-graph-01-2026-09-12/.
Preserves URLs, UTC timestamps, SHA256 digests, and actual responses without
downloading large binaries.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import email
import hashlib
import json
from pathlib import Path
import re
import urllib.request
from typing import Any

from packaging.tags import Tag, compatible_tags, cpython_tags
from packaging.utils import parse_wheel_filename


PROOF_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROOF_DIR.parents[3]
LOCK_FILE = REPO_ROOT / "requirements-installer-lock.txt"
PYPI_DIR = PROOF_DIR / "pypi"
METADATA_DIR = PROOF_DIR / "metadata"

HEADERS = {
    "User-Agent": "uoink-runtime-graph-audit/2026-09-12 (Windows x64 CPython 3.13; contact ryanbiddy/uoink)"
}

PIN_REGEX = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def get_supported_wheel_tags() -> set[Tag]:
    tags: set[Tag] = set()
    tags.update(cpython_tags(python_version=(3, 13), platforms=["win_amd64"]))
    tags.update(compatible_tags(python_version=(3, 13), platforms=["win_amd64"]))
    tags.update(compatible_tags(python_version=(3, 13)))
    for minor in range(2, 14):
        tags.update(cpython_tags(python_version=(3, minor), abis=["abi3"], platforms=["win_amd64"]))
    return tags


def fetch_url(url: str, timeout: int = 30) -> tuple[int, bytes, str | None]:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), None
    except Exception as exc:
        return 0, b"", str(exc)


def read_installer_lock() -> dict[str, str]:
    locked: dict[str, str] = {}
    for line in LOCK_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_REGEX.fullmatch(line)
        if match:
            name, ver = match.groups()
            locked[canonical_name(name)] = ver
    return locked


def fetch_pypi_package_json(pkg_name: str) -> dict[str, Any]:
    cname = canonical_name(pkg_name)
    url = f"https://pypi.org/pypi/{pkg_name}/json"
    timestamp_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    status, data, error = fetch_url(url)
    record: dict[str, Any] = {
        "package": pkg_name,
        "canonical_name": cname,
        "url": url,
        "timestamp_utc": timestamp_utc,
        "status": status,
        "bytes": len(data),
        "error": error,
    }
    if status == 200 and data:
        digest = hashlib.sha256(data).hexdigest()
        record["sha256"] = digest
        out_path = PYPI_DIR / f"{cname}.json"
        out_path.write_bytes(data)
        record["saved_file"] = f"pypi/{cname}.json"
        try:
            record["parsed"] = json.loads(data.decode("utf-8"))
        except Exception as exc:
            record["parse_error"] = str(exc)
    return record


def fetch_wheel_metadata(wheel_file_info: dict[str, Any], cname: str, version: str) -> dict[str, Any]:
    fn = wheel_file_info["filename"]
    meta_url = wheel_file_info["url"] + ".metadata"
    timestamp_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    status, data, error = fetch_url(meta_url)
    record: dict[str, Any] = {
        "package": cname,
        "version": version,
        "filename": fn,
        "url": meta_url,
        "timestamp_utc": timestamp_utc,
        "status": status,
        "bytes": len(data),
        "error": error,
    }
    if status == 200 and data:
        digest = hashlib.sha256(data).hexdigest()
        record["sha256"] = digest
        out_path = METADATA_DIR / f"{fn}.metadata"
        out_path.write_bytes(data)
        record["saved_file"] = f"metadata/{fn}.metadata"
    elif status != 200:
        # Fallback: if wheel is small (<3MB), range request or download dist-info/METADATA
        record["note"] = "core-metadata endpoint not available or returned non-200"
    return record


def main() -> int:
    PYPI_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    locked = read_installer_lock()
    print(f"Loaded {len(locked)} locked packages from {LOCK_FILE.name}")

    candidate_packages = [
        "torch",
        "torchaudio",
        "torchvision",
        "torchcodec",
        "whisperx",
        "transformers",
        "huggingface-hub",
        "pyannote-audio",
        "lightning",
        "pytorch-lightning",
        "nltk",
        "faster-whisper",
        "ctranslate2",
    ]

    all_pkgs = sorted(set(list(locked.keys()) + candidate_packages))
    print(f"Fetching primary PyPI JSON for {len(all_pkgs)} packages...")

    pypi_results: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_pkg = {executor.submit(fetch_pypi_package_json, pkg): pkg for pkg in all_pkgs}
        for future in concurrent.futures.as_completed(future_to_pkg):
            pkg = future_to_pkg[future]
            try:
                res = future.result()
                pypi_results[res["canonical_name"]] = res
                status = res.get("status")
                print(f"  [{status}] {pkg} ({res.get('bytes', 0)} bytes)")
            except Exception as exc:
                print(f"  [FAIL] {pkg}: {exc}")

    # Now identify wheels for locked versions and candidates
    supported_tags = get_supported_wheel_tags()
    metadata_jobs: list[tuple[dict[str, Any], str, str]] = []

    # Collect locked wheels
    for cname, version in locked.items():
        pkg_data = pypi_results.get(cname, {}).get("parsed")
        if not pkg_data:
            continue
        releases = pkg_data.get("releases", {})
        files = releases.get(version, [])
        for f in files:
            fn = f.get("filename", "")
            if not fn.endswith(".whl") or f.get("packagetype") != "bdist_wheel":
                continue
            try:
                _, _, _, wtags = parse_wheel_filename(fn)
            except Exception:
                continue
            if wtags & supported_tags:
                metadata_jobs.append((f, cname, version))
                break

    # Also collect candidate wheels for key packages
    candidate_versions = {
        "torch": ["2.8.0", "2.9.0", "2.9.1", "2.10.0", "2.11.0", "2.12.0", "2.13.0", "2.14.0"],
        "torchaudio": ["2.8.0", "2.9.0", "2.9.1", "2.10.0", "2.11.0"],
        "torchvision": ["0.23.0", "0.24.0", "0.25.0", "0.28.0", "0.29.0"],
        "torchcodec": ["0.7.0", "0.8.0", "0.9.0", "0.16.0"],
        "whisperx": ["3.8.6", "3.8.7rc1"],
        "transformers": ["4.57.6", "5.0.0", "5.10.0", "5.17.0"],
        "huggingface-hub": ["0.36.2", "1.0.0", "1.5.0", "1.31.0"],
        "pyannote-audio": ["4.0.7"],
        "lightning": ["2.6.6"],
        "pytorch-lightning": ["2.6.6"],
        "nltk": ["3.10.3"],
        "faster-whisper": ["1.2.1"],
    }

    for cname, vers in candidate_versions.items():
        pkg_data = pypi_results.get(cname, {}).get("parsed")
        if not pkg_data:
            continue
        releases = pkg_data.get("releases", {})
        for v in vers:
            files = releases.get(v, [])
            for f in files:
                fn = f.get("filename", "")
                if not fn.endswith(".whl") or f.get("packagetype") != "bdist_wheel":
                    continue
                try:
                    _, _, _, wtags = parse_wheel_filename(fn)
                except Exception:
                    continue
                if wtags & supported_tags:
                    metadata_jobs.append((f, cname, v))
                    break

    print(f"\nFetching wheel METADATA for {len(metadata_jobs)} candidate/locked wheels...")
    metadata_results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_job = {
            executor.submit(fetch_wheel_metadata, f_info, cname, ver): (cname, ver, f_info["filename"])
            for f_info, cname, ver in metadata_jobs
        }
        for future in concurrent.futures.as_completed(future_to_job):
            cname, ver, fn = future_to_job[future]
            try:
                res = future.result()
                metadata_results.append(res)
                st = res.get("status")
                print(f"  [{st}] {fn}.metadata ({res.get('bytes', 0)} bytes)")
            except Exception as exc:
                print(f"  [FAIL] {fn}.metadata: {exc}")

    # Build SHA256 manifest
    sha256_manifest: dict[str, str] = {}
    for p in sorted(PROOF_DIR.rglob("*")):
        if p.is_file() and p.name not in ("SHA256.json", "manifest.json", "evidence_manifest.json"):
            rel = str(p.relative_to(PROOF_DIR)).replace("\\", "/")
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            sha256_manifest[rel] = h

    (PROOF_DIR / "SHA256.json").write_text(json.dumps(sha256_manifest, indent=2), encoding="utf-8")
    print(f"\nWrote SHA256.json ({len(sha256_manifest)} files hashed)")

    summary = {
        "retrieval_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_packages_queried": len(all_pkgs),
        "total_pypi_json_saved": len(list(PYPI_DIR.glob("*.json"))),
        "total_metadata_saved": len(list(METADATA_DIR.glob("*.metadata"))),
        "pypi_downloads": [
            {k: v for k, v in r.items() if k != "parsed"} for r in pypi_results.values()
        ],
        "metadata_downloads": metadata_results,
    }
    (PROOF_DIR / "fetch_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Wrote fetch_summary.json. Primary metadata capture complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

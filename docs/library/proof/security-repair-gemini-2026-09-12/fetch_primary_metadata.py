"""Fetch primary upstream metadata from PyPI and OSV for dependency security review.
Preserves fetched metadata, retrieval times, URLs, and raw counts.
"""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import urllib.request

PROOF_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROOF_DIR.parents[3]
LOCK_FILE = REPO_ROOT / "requirements-installer-lock.txt"

PYPI_PACKAGES = [
    "lightning",
    "pytorch-lightning",
    "nltk",
    "torch",
    "torchaudio",
    "torchvision",
    "torchcodec",
    "transformers",
    "whisperx",
    "huggingface-hub",
    "pyannote-audio",
]

def fetch_pypi_metadata():
    pypi_dir = PROOF_DIR / "pypi"
    pypi_dir.mkdir(exist_ok=True)
    results = {}
    
    for pkg in PYPI_PACKAGES:
        url = f"https://pypi.org/pypi/{pkg}/json"
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "uoink-dependency-audit/2026-09-12"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                status = resp.status
        except Exception as e:
            results[pkg] = {
                "url": url,
                "timestamp_utc": timestamp,
                "error": str(e),
            }
            continue
        
        file_path = pypi_dir / f"{pkg}.json"
        file_path.write_bytes(data)
        
        parsed = json.loads(data)
        info = parsed.get("info", {})
        releases = parsed.get("releases", {})
        
        # Collect recent versions
        results[pkg] = {
            "url": url,
            "timestamp_utc": timestamp,
            "status": status,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "latest_version": info.get("version"),
            "requires_python": info.get("requires_python"),
            "all_versions": sorted(list(releases.keys())),
            "saved_file": str(file_path.relative_to(PROOF_DIR)),
        }
        
    (PROOF_DIR / "pypi_summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results

def fetch_osv_advisories():
    osv_dir = PROOF_DIR / "osv"
    osv_dir.mkdir(exist_ok=True)
    advisories_dir = osv_dir / "advisories"
    advisories_dir.mkdir(exist_ok=True)
    
    lock_lines = [line.strip() for line in LOCK_FILE.read_text(encoding="utf-8").splitlines()
                  if line.strip() and not line.strip().startswith("#")]
    pins = [line.split("==") for line in lock_lines]
    assert len(pins) == 140, f"Expected 140 pins, got {len(pins)}"
    
    queries = [{"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
               for name, version in pins]
    batch_req = {"queries": queries}
    (osv_dir / "request.json").write_text(json.dumps(batch_req, indent=2), encoding="utf-8")
    
    batch_url = "https://api.osv.dev/v1/querybatch"
    started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    req = urllib.request.Request(
        batch_url,
        data=json.dumps(batch_req).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "uoink-dependency-audit/2026-09-12"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw_resp = resp.read()
    
    (osv_dir / "response.json").write_bytes(raw_resp)
    batch_data = json.loads(raw_resp)
    results = batch_data.get("results", [])
    assert len(results) == len(pins)
    
    # Collect IDs
    vuln_ids = sorted({v["id"] for row in results for v in row.get("vulns", [])})
    
    def fetch_advisory(vuln_id):
        assert re.fullmatch(r"[A-Za-z0-9_-]+", vuln_id)
        vuln_url = f"https://api.osv.dev/v1/vulns/{vuln_id}"
        vreq = urllib.request.Request(vuln_url, headers={"User-Agent": "uoink-dependency-audit/2026-09-12"})
        with urllib.request.urlopen(vreq, timeout=30) as vresp:
            vdata = vresp.read()
        (advisories_dir / f"{vuln_id}.json").write_bytes(vdata)
        return json.loads(vdata)
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        advisory_records = list(pool.map(fetch_advisory, vuln_ids))
        
    # Build alias groups
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
        
    for rec in advisory_records:
        aliases = [rec["id"], *rec.get("aliases", [])]
        for a in aliases:
            parent[find(a)] = find(aliases[0])
            
    groups = {}
    for identifier in parent:
        groups.setdefault(find(identifier), []).append(identifier)
        
    matched_packages = []
    for pin, row in zip(pins, results):
        if row.get("vulns"):
            matched_packages.append({
                "name": pin[0],
                "version": pin[1],
                "entries": row.get("vulns", [])
            })
            
    finished_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    summary = {
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "lock_file": str(LOCK_FILE),
        "lock_sha256": hashlib.sha256(LOCK_FILE.read_bytes()).hexdigest(),
        "queried_packages": len(pins),
        "matched_packages": len(matched_packages),
        "package_advisory_entries": sum(len(row["entries"]) for row in matched_packages),
        "unique_advisory_records": len(vuln_ids),
        "distinct_alias_groups": len(groups),
        "packages": matched_packages,
        "alias_groups": list(groups.values()),
        "clean": len(vuln_ids) == 0,
    }
    (osv_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

def main():
    print("Fetching PyPI metadata...")
    pypi_res = fetch_pypi_metadata()
    print("PyPI fetch complete.")
    for pkg, info in pypi_res.items():
        print(f"  {pkg}: latest={info.get('latest_version')}")
        
    print("\nFetching OSV batch advisories...")
    osv_res = fetch_osv_advisories()
    print(f"OSV fetch complete: matched {osv_res['matched_packages']} packages, {osv_res['package_advisory_entries']} entries, {osv_res['distinct_alias_groups']} alias groups.")
    for pkg_info in osv_res["packages"]:
        print(f"  {pkg_info['name']} {pkg_info['version']}: {len(pkg_info['entries'])} entries")

if __name__ == "__main__":
    main()

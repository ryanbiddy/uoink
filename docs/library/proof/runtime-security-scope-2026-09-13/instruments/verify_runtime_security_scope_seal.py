"""Read documentary hashes and JSON only; never import archived package code."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


def deny_runtime(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "ctypes.dlopen"}:
        raise RuntimeError("Documentary verifier forbids network, children and native loads")


sys.addaudithook(deny_runtime)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def safe_file(root, relative):
    path = root / relative
    require(not Path(relative).is_absolute() and ".." not in Path(relative).parts, "Unsafe relative path")
    require(path.resolve(strict=True).is_relative_to(root.resolve()), "Path outside archive")
    for item in [path, *path.parents]:
        require(not item.is_symlink() and not (getattr(item.lstat(), "st_file_attributes", 0) & 1024), "Reparse path refused")
        if item == root:
            break
    require(path.is_file(), "Expected documentary file")
    return path


def verify_manifest(root, name, records):
    entries = {r["file"]: r for r in records}
    require(len(entries) == len(records), "Duplicate manifest entry")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    require(actual == set(entries) | {name}, "Manifest membership mismatch")
    for relative, row in entries.items():
        path = safe_file(root, relative)
        require(path.stat().st_size == row["bytes"] and digest(path) == row["sha256"], "Payload mismatch: " + relative)
    return len(entries)


def verify(root):
    root = root.resolve(strict=True)
    root_manifest = read(root / "SHA256.json")
    total = verify_manifest(root, "SHA256.json", root_manifest["payloads"])
    require(total == root_manifest["payload_count"], "Root count mismatch")
    original_counts = {}
    for child, name, expected_hash, count in [
        ("candidate02-osv01", "ORIGINAL-CANDIDATE02-OSV-SHA256.json", "f6378453d1bc9ea432793b33ea6e2aa108b5ce868a740f9df9e79c3d79e29bf5", 31),
        ("candidate03-source", "ORIGINAL-CANDIDATE03-SOURCE-SHA256.json", "00dee8e9ecbbc0b187c3884349e2374ae90447f88c28bcd1a01fba10fdec32f3", 68),
    ]:
        folder = root / child
        path = folder / name
        require(digest(path) == expected_hash, "Original manifest bytes changed")
        original = read(path)
        rows = [{"file": key, **value} for key, value in original["files"].items()] if "files" in original else original["payloads"]
        require(verify_manifest(folder, name, rows) == count, "Original count mismatch")
        original_counts[child] = count
    copied = read(root / "COPY-VERIFICATION.json")
    require(copied["hash_mismatches"] == 0, "Copy report records mismatch")
    for row in copied["copies"]:
        path = safe_file(root, row["destination"])
        require(digest(path) == row["source_sha256"] == row["destination_sha256"], "Copy receipt mismatch")
        require(path.stat().st_size == row["bytes"], "Copy receipt size mismatch")
    source = root / "candidate03-source"
    bindings = read(source / "source-bindings.json")
    retrievals = read(source / "retrievals.json")
    commits = read(source / "commit-bindings.json")
    require((len(bindings), len(retrievals), len(commits)) == (39, 19, 5), "Source binding cardinality mismatch")
    source_counts = Counter(b["saved_file"].split("/")[0] for b in bindings)
    require(source_counts == {"retained": 13, "local-current": 12, "upstream": 14}, "Source provenance counts mismatch")
    for row in bindings + retrievals:
        path = safe_file(source, row["saved_file"])
        require(path.stat().st_size == row["bytes"] and digest(path) == row["sha256"], "Source/retrieval binding mismatch")
    for row in retrievals:
        require(row["status"] == 200, "Source retrieval failure")
    for binding in commits:
        matches = [r for r in retrievals if r["sha256"] == binding["response_sha256"]]
        require(len(matches) == 1 and matches[0]["kind"] == "commit", "Commit retrieval ambiguous")
        require(read(safe_file(source, matches[0]["saved_file"]))["sha"] == binding["commit"], "Release commit mismatch")
    for binding in bindings:
        if binding["saved_file"].startswith("upstream/"):
            matches = [r for r in retrievals if r["url"] == binding["url"]]
            commit = [c for c in commits if c["repository"] == binding["repository"]]
            require(len(matches) == len(commit) == 1, "Upstream binding ambiguous")
            require(matches[0]["sha256"] == binding["sha256"], "Upstream raw/source mismatch")
            require(commit[0]["commit"] == binding["commit"] and "/" + binding["commit"] + "/" in binding["url"], "Mutable/unmatched upstream source URL")
    osv = root / "candidate02-osv01"
    selected = read(osv / "selection.json")["selected"]
    require(len(selected) == 144, "Candidate membership count mismatch")
    summary = read(osv / "summary.json")
    query_counts = {}
    for scope, pins, key in [("candidate", selected, "candidate"), ("upstream-nltk-comparison", {"nltk": "3.10.3"}, "upstream_nltk_comparison")]:
        page = osv / "batches" / scope / "page-001"
        query = read(page / "request-body.json")["queries"]
        results = read(page / "response-body.json")["results"]
        derived = read(osv / (scope + "-query-results.json"))
        require(len(query) == len(results) == len(derived) == len(pins), "OSV query/result count mismatch")
        require({q["package"]["name"]: q["version"] for q in query} == pins, "OSV queried versions differ")
        groups = []
        entries = []
        for q, result, saved in zip(query, results, derived):
            require(q["package"]["ecosystem"] == "PyPI" and not result.get("next_page_token"), "Unexpected ecosystem or unfinished pagination")
            vulns = result.get("vulns", [])
            require(saved["complete"] and not saved["errors"] and saved["name"] == q["package"]["name"] and saved["version"] == q["version"], "Derived query mismatch")
            require([e["entry"] for e in saved["entries"]] == vulns, "OSV raw/derived entries mismatch")
            entries.extend(vulns)
            for entry in vulns:
                advisory = read(osv / "advisories" / entry["id"] / "response-body.json")
                require(advisory["id"] == entry["id"], "Advisory ID mismatch")
                group = {advisory["id"], *advisory.get("aliases", [])}
                for existing in [g for g in groups if g & group]:
                    groups.remove(existing)
                    group.update(existing)
                groups.append(group)
        require(len(entries) == summary[key]["raw_entries"] == 1, "Raw count mismatch")
        require(len(groups) == summary[key]["alias_group_count"] == 1, "Alias count mismatch")
        require(sorted(sorted(g) for g in groups) == summary[key]["alias_groups"], "Alias identities differ")
        query_counts[key] = {"pins": len(pins), "raw_entries": len(entries), "alias_groups": len(groups)}
    exchanges = list(osv.rglob("exchange.json"))
    require(len(exchanges) == 4, "OSV exchange count mismatch")
    for path in exchanges:
        exchange = read(path)
        folder = path.parent
        require(exchange["status"] == 200 and exchange["error"] is None and exchange["automatic_retries"] == 0, "OSV HTTP failure/retry")
        require(exchange["request_body_sha256"] == digest(folder / "request-body.json") and exchange["response_sha256"] == digest(folder / "response-body.json") and exchange["request_wire_sha256"] == digest(folder / "request-wire.bin"), "OSV exchange hash mismatch")
        require((folder / "request-wire.bin").read_bytes().split(b"\r\n\r\n", 1)[1] == (folder / "request-body.json").read_bytes(), "OSV request body mismatch")
    require(summary["metadata_collection_complete"] and not summary["failures"], "OSV collection incomplete")
    require(summary["local_nltk"]["raw_entries"] == 0 and summary["local_nltk"]["version"] == "3.10.3+uoink.pathsec1", "Local NLTK receipt mismatch")
    require(summary["original_audit_unchanged"] == {"raw_entries": 19, "alias_groups": 15}, "Original audit relabeled")
    for key in ["security_cleared", "compatibility_tested", "model_loader_safety_established", "installed_or_executed_candidate", "release_ready"]:
        require(summary[key] is False, "Unsupported outcome claim")
    return {"result": "PASS", "scope": "Documentary bytes and recorded metadata only", "root_payloads_verified": total, "original_payload_counts": original_counts, "copied_files_verified": len(copied["copies"]), "source_bindings": 39, "source_retrievals": 19, "release_commit_bindings": 5, "source_provenance_counts": dict(source_counts), "osv_queries": query_counts, "osv_exchanges": 4, "hash_mismatches": 0, "network_requests": 0, "captured_source_executed": False, "product_tests_run": 0, "release_approved": False, "root_manifest_sha256": digest(root / "SHA256.json")}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).resolve().parent.parent
    print(json.dumps(verify(target), indent=2))

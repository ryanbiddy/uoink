"""Read the sealed OSV metadata only; perform no network or runtime imports."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SEALED = ROOT / "runtime-candidate02-osv01"
OUT = ROOT / "runtime-candidate02-osv01-review.json"


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    require(not OUT.exists(), "Refuse to replace a previous review")
    manifest_path = SEALED / "SHA256.json"
    manifest_digest = digest(manifest_path)
    manifest = read(manifest_path)
    expected = manifest["files"]
    actual = {p.relative_to(SEALED).as_posix() for p in SEALED.rglob("*") if p.is_file()}
    require(actual == set(expected) | {"SHA256.json"}, "Manifest membership mismatch")
    require(len(expected) == 31, "Unexpected payload count")
    for name, record in expected.items():
        path = SEALED / name
        require(path.resolve().is_relative_to(SEALED.resolve()), "Manifest path escapes seal")
        require(path.stat().st_size == record["bytes"], f"Size mismatch: {name}")
        require(digest(path) == record["sha256"], f"Hash mismatch: {name}")
    require(digest(SEALED / "selection.json") == digest(ROOT / "runtime-candidate02-metadata" / "selection.json"), "Selection source changed")
    require(digest(SEALED / "collector.py") == digest(ROOT / "collect_runtime_candidate02_osv01.py"), "Collector source changed")
    selected = read(SEALED / "selection.json")["selected"]
    require(len(selected) == 144, "Candidate pin count changed")
    summary = read(SEALED / "summary.json")
    require(summary["selection_sha256"] == digest(SEALED / "selection.json"), "Summary selection digest mismatch")
    exchanges = []
    for path in sorted(SEALED.rglob("exchange.json")):
        folder = path.parent
        exchange = read(path)
        intent = read(folder / "request.json")
        body = (folder / "request-body.json").read_bytes()
        wire = (folder / "request-wire.bin").read_bytes()
        response = (folder / "response-body.json").read_bytes()
        head, sent = wire.split(b"\r\n\r\n", 1)
        method, uri, protocol = head.split(b"\r\n", 1)[0].decode("ascii").split(" ")
        require(sent == body, "Wire/body mismatch")
        require(protocol == "HTTP/1.1", "Unexpected request protocol")
        require(b"Host: api.osv.dev\r\n" in head + b"\r\n", "Unexpected request host")
        require(exchange["method"] == intent["method"] == method, "Method disagreement")
        require(exchange["url"] == intent["url"] == "https://api.osv.dev" + uri, "URL disagreement")
        require(uri == "/v1/querybatch" or uri.startswith("/v1/vulns/GHSA-"), "Unapproved endpoint")
        require(exchange["status"] == 200 and exchange["error"] is None, "HTTP failure")
        require(exchange["automatic_retries"] == 0 and exchange["redirects_followed"] is False, "Unexpected retry/redirect")
        require(exchange["response_bytes"] == len(response), "Response size mismatch")
        require(exchange["response_sha256"] == hashlib.sha256(response).hexdigest(), "Response hash mismatch")
        require(exchange["request_body_bytes"] == intent["request_body_bytes"] == len(body), "Request size mismatch")
        require(exchange["request_body_sha256"] == intent["request_body_sha256"] == hashlib.sha256(body).hexdigest(), "Request hash mismatch")
        require(exchange["request_wire_sha256"] == hashlib.sha256(wire).hexdigest(), "Wire hash mismatch")
        require(datetime.fromisoformat(exchange["finished_utc"]) >= datetime.fromisoformat(exchange["started_utc"]), "Reversed timestamps")
        require(exchange["seconds"] >= 0, "Negative duration")
        exchanges.append({"path": path.relative_to(SEALED).as_posix(), "status": exchange["status"], "request_sha256": exchange["request_body_sha256"], "response_sha256": exchange["response_sha256"]})
    require(len(exchanges) == 4, "Unexpected exchange count")
    full = {p.parent.name: read(p) for p in (SEALED / "advisories").glob("*/response-body.json")}
    require(set(full) == {"GHSA-qqmf-gpg7-g8gw", "GHSA-8mgp-746c-j5xp"}, "Unexpected full advisory set")
    for ident, advisory in full.items():
        require(advisory["id"] == ident and not advisory.get("withdrawn"), "Mismatched/withdrawn full advisory")
    results = {}
    for scope, pins, summary_key in [
        ("candidate", selected, "candidate"),
        ("upstream-nltk-comparison", {"nltk": "3.10.3"}, "upstream_nltk_comparison"),
    ]:
        page = SEALED / "batches" / scope / "page-001"
        require(sorted(p.name for p in page.parent.iterdir()) == ["page-001"], "Unexpected pagination")
        queries = read(page / "request-body.json")["queries"]
        response = read(page / "response-body.json")["results"]
        mappings = read(page / "query-map.json")
        derived = read(SEALED / f"{scope}-query-results.json")
        require(len(queries) == len(response) == len(mappings) == len(derived) == len(pins), "Query/result cardinality mismatch")
        require({q["package"]["name"]: q["version"] for q in queries} == pins, "Query selection mismatch")
        entries = []
        groups = []
        matches = []
        for i, (query, result, mapping, saved) in enumerate(zip(queries, response, mappings, derived)):
            name, version = query["package"]["name"], query["version"]
            require(query == {"package": {"ecosystem": "PyPI", "name": name}, "version": version}, "Unexpected query shape or pagination")
            require(mapping == {"original_index": i, "name": name, "version": version, "page_token": None}, "Query map mismatch")
            require(not result.get("next_page_token"), "Unfollowed pagination token")
            require(set(result) <= {"vulns", "next_page_token"}, "Unrecognized result field")
            vulns = result.get("vulns", [])
            require(saved == {"name": name, "version": version, "scope": scope, "complete": True, "pages": [f"batches/{scope}/page-001"], "entries": [{"page": 1, "entry": v} for v in vulns], "errors": []}, "Derived query receipt differs from raw")
            if vulns:
                matches.append({"name": name, "version": version, "ids": [v["id"] for v in vulns]})
            entries.extend(vulns)
            for vuln in vulns:
                advisory = full[vuln["id"]]
                identities = {advisory["id"], *advisory.get("aliases", [])}
                overlapping = [g for g in groups if g & identities]
                for group in overlapping:
                    groups.remove(group)
                    identities.update(group)
                groups.append(identities)
        normalized = sorted(sorted(g) for g in groups)
        reported = summary[summary_key]
        require(reported["queried_pins"] == reported["completed_pin_queries"] == len(pins), "Summary query count mismatch")
        require(reported["query_complete"] and reported["alias_grouping_complete"], "Summary incomplete")
        require(reported["raw_entries"] == len(entries) == 1, "Raw advisory count mismatch")
        require(reported["alias_group_count"] == len(groups) == 1, "Alias group count mismatch")
        require(reported["alias_groups"] == normalized, "Summary alias membership mismatch")
        results[summary_key] = {"pins": len(pins), "raw_entries": len(entries), "alias_group_count": len(groups), "aliases": normalized, "matches": matches}
    require(summary["local_nltk"]["version"] == "3.10.3+uoink.pathsec1" and summary["local_nltk"]["raw_entries"] == 0, "Local NLTK response mismatch")
    require(summary["original_audit_unchanged"] == {"raw_entries": 19, "alias_groups": 15}, "Original audit counts relabeled")
    require(summary["metadata_collection_complete"] and not summary["failures"], "Summary collection incomplete")
    for field in ["security_cleared", "compatibility_tested", "model_loader_safety_established", "installed_or_executed_candidate", "release_ready"]:
        require(summary[field] is False, f"Unjustified claim: {field}")
    require(digest(manifest_path) == manifest_digest, "Manifest changed during reader")
    result = {"review_finished_utc": datetime.now(timezone.utc).isoformat(), "reader_sha256": digest(Path(__file__)), "verification_result": "PASS", "scope": "Sealed metadata consistency only; no runtime or security approval", "verified_payload_count": len(expected), "manifest_sha256": manifest_digest, "selection_sha256": digest(SEALED / "selection.json"), "exchanges": exchanges, "counts": results, "pagination_tokens": 0, "collection_failures": 0, "local_nltk_zero_matches_is_clearance": False, "original_audit_raw_entries": 19, "original_audit_alias_groups": 15}
    with OUT.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

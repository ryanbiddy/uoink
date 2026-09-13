"""Bounded public model-info JSON; no repository asset request or SDK import."""
import sys
if tuple(sys.version_info[:3]) != (3, 14, 6) or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode) or "site" in sys.modules:
    raise RuntimeError("Reviewed isolated stdlib interpreter required")
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

OUT = Path(__file__).absolute().parent
ROOT = OUT.parents[1]
RUN = OUT / "run01"
RUN.mkdir(exist_ok=False)
REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}
FILES = {"model.bin", "config.json", "tokenizer.json", "preprocessor_config.json", "vocabulary.json", "vocabulary.txt"}
MINIMUM = {"model.bin", "config.json", "tokenizer.json"}
CAP = 256 * 1024
started = datetime.now(timezone.utc).isoformat()
records = []
plans = []
failures = []

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def save(name, raw):
    with (RUN / name).open("xb") as stream:
        stream.write(raw)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PermissionError("Redirect refused")

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

def fetch(choice, repo, revision=None):
    if repo not in REPOS.values() or (revision is not None and re.fullmatch("[0-9a-f]{40}", revision) is None):
        raise ValueError("Unknown repository or invalid revision")
    url = "https://huggingface.co/api/models/" + repo
    if revision is not None:
        url += "/revision/" + revision
    url += "?blobs=true"
    row = {"url": url, "started_utc": datetime.now(timezone.utc).isoformat(), "ok": False}
    records.append(row)
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "uoink-public-metadata-review/1"})
    try:
        with opener.open(request, timeout=12) as response:
            if response.status != 200 or response.geturl() != url or response.headers.get_content_type() != "application/json":
                raise ValueError("Unexpected response status, URL or content type")
            size = response.headers.get("Content-Length")
            if size is not None and int(size) > CAP:
                raise ValueError("Advertised metadata cap exceeded")
            raw = response.read(CAP + 1)
            if len(raw) > CAP:
                raise ValueError("Metadata cap exceeded")
        name = choice + ("-current.json" if revision is None else "-pinned.json")
        save(name, raw)
        row.update(file=name, bytes=len(raw), sha256=digest(raw), status=200)
        data = json.loads(raw)
        if type(data) is not dict or data.get("id") != repo or re.fullmatch("[0-9a-f]{40}", data.get("sha", "")) is None:
            raise ValueError("Repository identity mismatch")
        if revision is not None and data["sha"] != revision:
            raise ValueError("Immutable revision mismatch")
        if type(data.get("siblings")) is not list or len(data["siblings"]) > 128:
            raise ValueError("Bounded sibling list required")
        row["ok"] = True
        return data
    except Exception as exc:
        row["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        row["finished_utc"] = datetime.now(timezone.utc).isoformat()

bindings = []
for rel, target in [
    ("whisper_runner.py", "whisper_runner.py.txt"),
    ("installer/staging/python/Lib/site-packages/huggingface_hub/hf_api.py", "hf_api.py.txt"),
]:
    source = ROOT / rel
    info = source.lstat()
    if source.is_symlink() or getattr(info, "st_reparse_tag", 0) or info.st_size > 2 * 1024 * 1024:
        raise ValueError("Unexpected source binding")
    raw = source.read_bytes()
    save(target, raw)
    bindings.append({"source": rel, "copy": target, "bytes": len(raw), "sha256": digest(raw)})
    if rel == "whisper_runner.py":
        tree = ast.parse(raw, filename=str(source))
        assignments = [node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_MODEL_REPOSITORIES" for t in node.targets)]
        if len(assignments) != 1 or ast.literal_eval(assignments[0].value) != REPOS:
            raise ValueError("Existing model scope changed")

for choice, repo in REPOS.items():
    try:
        current = fetch(choice, repo)
        pinned = fetch(choice, repo, current["sha"])
        rows = pinned["siblings"]
        if current["siblings"] != rows:
            raise ValueError("Current and pinned file metadata differ")
        paths = [row.get("rfilename") for row in rows]
        if any(type(name) is not str for name in paths) or len(paths) != len(set(paths)) or not MINIMUM <= set(paths):
            raise ValueError("Duplicate or missing required file")
        selected = []
        for row in rows:
            name = row["rfilename"]
            if name not in FILES:
                continue
            size = row.get("size")
            oid = row.get("blobId")
            if type(size) is not int or not 0 < size <= 10 * 1024 ** 3 or not isinstance(oid, str) or re.fullmatch("[0-9a-f]{40}", oid) is None:
                raise ValueError("Missing or invalid file identity")
            lfs = row.get("lfs")
            sha256 = None
            if lfs is not None:
                if type(lfs) is not dict or lfs.get("size") != size or re.fullmatch("[0-9a-f]{64}", lfs.get("sha256", "")) is None:
                    raise ValueError("Invalid LFS declaration")
                sha256 = lfs["sha256"]
            selected.append({"path": name, "bytes": size, "git_blob_oid": oid, "lfs_sha256": sha256, "sha256_verified_from_asset": False, "required_by_current_minimum": name in MINIMUM})
        plans.append({"choice": choice, "repo": repo, "revision": pinned["sha"], "gated": pinned.get("gated"), "private": pinned.get("private"), "license_metadata": pinned.get("cardData", {}).get("license"), "files": selected, "advertised_selected_bytes": sum(row["bytes"] for row in selected), "all_selected_have_advertised_sha256": all(row["lfs_sha256"] for row in selected), "asset_downloaded": False, "manifest_accepted": False})
    except Exception as exc:
        failures.append({"choice": choice, "type": type(exc).__name__, "message": str(exc)})

code = 1 if failures else 0
result = {"status": "FAILED" if failures else "METADATA_CAPTURED", "exit": code, "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "source_bindings": bindings, "requests": records, "plans": plans, "failures": failures, "asset_downloads": 0, "model_execution": False, "runtime_approved": False, "release_ready": False}
save("result.json", json.dumps(result, indent=2).encode() + b"\n")
print(json.dumps({"status": result["status"], "exit": code, "requests": len(records), "successful_requests": sum(r["ok"] for r in records), "plans": len(plans), "failures": failures}))
raise SystemExit(code)

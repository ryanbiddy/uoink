"""Precondition a prepared AW fixture for native reshelve-review observation.

This is an explicit application fixture launcher, separate from the default
unattached stdio entry. It never runs a client/model or enables apply. Run once,
immediately before freezing the client session; previews expire after 15 minutes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def state(index, settings):
    conn = index._conn
    names = sorted(row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND "
        "(name LIKE 'library_%' OR name LIKE 'shelf_%' OR name IN ('item_shelves','yoinks','clips'))"))
    result = {}
    for name in names:
        quoted = '"' + name.replace('"', '""') + '"'
        rows = [list(row) for row in conn.execute('SELECT * FROM ' + quoted)]
        encoded = sorted(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
        result[name] = {"rows": len(rows), "sha256": sha("\n".join(encoded).encode())}
    result["settings"] = {"sha256": sha(settings.read_bytes())}
    return result


ENTRY = '''"""AW application fixture: attach the real Phase 2 service before stdio."""
import os
from pathlib import Path
import index
import library_work
import uoink_mcp

root = Path(os.environ["AW_FIXTURE_ROOT"]).resolve(strict=True)
database = root / "profile" / "Uoink" / "index.db"
idx = index.Index.open(database)
try:
    service = library_work.LibraryWorkService(
        idx, root / "prompt-store", librarian_apply_enabled=False)
    if service.librarian_apply_enabled or not service.startup_status.get("ok"):
        raise RuntimeError("AW report-only service did not attach safely")
    uoink_mcp.server._index_singleton = idx
    uoink_mcp.mcp.run(transport="stdio")
finally:
    idx.close()
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", required=True)
    args = parser.parse_args()
    root = Path(args.fixture_root).resolve(strict=True)
    preparation = json.loads((root / "preparation.json").read_text(encoding="utf-8"))
    if preparation["status"] != "fixture prepared; client not run":
        raise ValueError("requires the original prepared fixture before any client")
    if any((root / "records").iterdir()) or (root / "prompt-preparation.json").exists():
        raise ValueError("fixture already used; preserve it and brief any rerun")
    config = json.loads((root / "mcp.json").read_text(encoding="utf-8"))
    if sha((root / "mcp.json").read_bytes()) != preparation["mcp_config_sha256"]:
        raise ValueError("prepared MCP configuration changed")
    expected = json.loads((root / "expected.json").read_text(encoding="utf-8"))
    if sha((root / "expected.json").read_bytes()) != preparation["expected_sha256"]:
        raise ValueError("expected packets changed")
    child = config["mcpServers"]["uoink"]
    if Path(child["env"]["AW_FIXTURE_ROOT"]).resolve() != root:
        raise ValueError("fixture binding mismatch")
    for value in (root / "stage", root / "profile" / "Uoink" / "index.db", root / "guard"):
        if not value.resolve(strict=True).is_relative_to(root):
            raise ValueError("fixture path escaped its root")
    settings = root / "profile" / "Uoink" / "settings.json"
    if json.loads(settings.read_text(encoding="utf-8")).get("librarian_apply_enabled") is not False:
        raise ValueError("apply must remain explicitly disabled")
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.update(child["env"])
    sys.path[:0] = child["env"]["PYTHONPATH"].split(os.pathsep)
    guard = root / "guard" / "sitecustomize.py"
    exec(compile(guard.read_text(encoding="utf-8"), str(guard), "exec"), {})
    import index
    from library_work import LibraryWorkService, RequestContext

    database = root / "profile" / "Uoink" / "index.db"
    idx = index.Index.open(database)
    calls = []
    try:
        before = state(idx, settings)
        service = LibraryWorkService(idx, root / "prompt-store", librarian_apply_enabled=False)
        if not service.startup_status.get("ok"):
            raise RuntimeError("copied state requires unresolved recovery; no preview was created")
        # Explicit synthetic operator preconditioning, not a model decision or
        # a user's approval of a live taxonomy, classification, or apply action.
        operator = RequestContext(authenticated=True, operator=True,
                                  client_id="aw-fixture", session_id="aw-fixture")
        operations = [
            ("approve_taxonomy", {"version_id": "aw_native_prompt_fixture", "nodes": [{
                "shelf_id": "aw_fixture_only", "path": ["AW fixture only"],
                "definition": "Synthetic prompt-observation taxonomy; never activated or applied.",
                "include": ["fixture only"], "exclude": ["all live classification"],
            }]}),
            ("prepare_run", {"run_id": "aw_native_prompt_fixture", "version_id": "aw_native_prompt_fixture",
                "video_ids": list(expected), "prompt_hash": sha(b"AW explicit synthetic prompt preconditioning"),
                "exclusions": {vid: "Report-only fixture; no classification or application requested."
                               for vid in expected}}),
        ]
        for method, request in operations:
            response = getattr(service, method)(operator, request)
            calls.append({"method": method, "request": request, "response": response})
            if not response.get("ok"):
                raise RuntimeError("prompt fixture setup refused: " + method)
        revision = idx._conn.execute("SELECT projection_revision FROM library_meta WHERE singleton=1").fetchone()[0]
        request = {"mode": "preview", "run_id": "aw_native_prompt_fixture", "expected_projection_revision": revision}
        preview = service.preview_apply(operator, request)
        calls.append({"method": "preview_apply", "request": request, "response": preview})
        if not preview.get("ok") or preview.get("can_apply") is not False:
            raise RuntimeError("report-only preview refused")
        after = state(idx, settings)
        service_again = LibraryWorkService(idx, root / "prompt-store", librarian_apply_enabled=False)
        if not service_again.startup_status.get("ok") or state(idx, settings) != after:
            raise RuntimeError("service reattachment changed the frozen semantic state")
    finally:
        idx.close()
        save(root / "prompt-preconditioning-calls.json", calls)
    entry = root / "attached_entry.py"
    entry.write_text(ENTRY, encoding="utf-8")
    original_args = child["args"]
    if Path(original_args[-1]).name != "uoink_mcp.py":
        raise ValueError("unexpected original entry")
    child["args"] = original_args[:-1] + [str(entry)]
    save(root / "mcp-attached.json", config)
    receipt = {
        "prepared_at": datetime.now(timezone.utc).isoformat(), "candidate": preparation["candidate"],
        "status": "prompt fixture prepared; client not run", "preview_id": preview["preview_id"],
        "expires_ms": preview["expires_ms"], "before_setup": before, "before_client": after,
        "reattachment_semantically_unchanged": True, "apply_enabled": False,
        "entry_sha256": sha(entry.read_bytes()), "config_sha256": sha((root / "mcp-attached.json").read_bytes()),
        "preconditioning_sha256": sha((root / "prompt-preconditioning-calls.json").read_bytes()),
        "scope": "Real service with synthetic excluded run; no model classifications, taxonomy activation or apply",
        "default_entry": "mcp.json retains unattached production startup; valid preview uses explicit application fixture",
    }
    save(root / "prompt-preparation.json", receipt)
    print(json.dumps({"status": receipt["status"], "preview_id": preview["preview_id"], "expires_ms": preview["expires_ms"]}))


if __name__ == "__main__":
    main()

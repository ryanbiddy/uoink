"""Stored previews through the original stdio entry, without service attachment."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time

import pytest

from library_work import RequestContext
from tests.test_library_work_apply_undo import make_apply_environment, submit_accepted_result
from tests.test_phase4_stdio import _StdioTestClient

ROOT = Path(__file__).resolve().parents[1]


def snapshot(data):
    with sqlite3.connect(data / "index.db") as conn:
        rows = "\n".join(conn.iterdump())
    files = {p.relative_to(data).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (data / "library").rglob("*") if p.is_file()}
    return rows, files


@pytest.mark.parametrize("change,expected", [
    ("valid", None), ("evidence", "revision_unavailable"),
    ("taxonomy", "revision_unavailable"), ("projection", "revision_unavailable"),
    ("expired", "revision_unavailable"), ("missing", "resource_not_found"),
])
def test_original_stdio_reads_stored_preview_after_restart(tmp_path, change, expected):
    idx, service, operator, clock = make_apply_environment(
        tmp_path / "seed", items=[{"video_id": "preview-restart"}],
        librarian_apply_enabled=False)
    clock[0] = int(time.time() * 1000)
    client = RequestContext(authenticated=True, client_id="preview-reader", session_id="reader")
    try:
        claimed = service.claim_work(client, dict(action="claim", run_id="run_apply_01",
            client_id="preview-reader", max_items=1, lease_seconds=600))
        assert claimed["ok"], claimed
        submitted = submit_accepted_result(service, client, claimed["work"][0])
        assert submitted["ok"], submitted
        preview = service.preview_apply(operator, dict(mode="preview", run_id="run_apply_01",
            expected_projection_revision=0))
        assert preview["ok"], preview
        with idx.write_transaction() as conn:
            if change == "evidence": conn.execute("UPDATE clips SET text='Changed after the preview'")
            if change == "projection": conn.execute("UPDATE library_meta SET projection_revision=1")
            if change == "expired": conn.execute("UPDATE library_previews SET expires_ms=1")
            if change == "missing": conn.execute("DELETE FROM library_previews")
        local = tmp_path / "user" / "local"
        data = local / "Uoink"
        data.mkdir(parents=True)
        with sqlite3.connect(data / "index.db") as dest:
            idx._conn.backup(dest)
        shutil.copytree(service.store_root, data / "library")
    finally:
        idx.close()
    if change == "taxonomy":
        taxonomy = next((data / "library" / "taxonomies").glob("*.json"))
        taxonomy.write_text("{}", encoding="utf8")
    # A read must not initialize recovery, even if an unrelated journal exists.
    journal = data / "library" / "journal"
    journal.mkdir(exist_ok=True)
    (journal / "not-a-recovery-request.txt").write_text("preserve this file", encoding="utf8")
    (data / "settings.json").write_text(json.dumps({"librarian_apply_enabled": False}), encoding="utf8")
    before = snapshot(data)
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    for name in ("UOINK_ISOLATED_PROFILE", "UOINK_ISOLATED_PORT", "UOINK_ISOLATED_APP_DIR"):
        env.pop(name, None)
    env.update(LOCALAPPDATA=str(local), APPDATA=str(tmp_path / "user" / "roaming"),
        USERPROFILE=str(tmp_path / "user"), UOINK_OUTPUT_DIR=str(data / "output"),
        PYTHONDONTWRITEBYTECODE="1")
    stdio = _StdioTestClient([sys.executable, "-B", "-P", str(ROOT / "uoink_mcp.py")],
                             cwd=tmp_path, env=env)
    try:
        stdio.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "preview-restart-regression", "version": "1"}}})
        assert "result" in stdio.wait_for(1)
        stdio.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        started = time.monotonic()
        stdio.send({"jsonrpc": "2.0", "id": 2, "method": "prompts/get", "params": {
            "name": "reshelve-review", "arguments": {"preview_id": preview["preview_id"]}}})
        response = stdio.wait_for(2, timeout=3)
        assert time.monotonic() - started < 2
        if expected is None:
            assert "result" in response, response
            assert preview["preview_id"] in json.dumps(response["result"])
            assert preview["delta_hash"] in json.dumps(response["result"])
        else:
            assert response.get("error", {}).get("data", {}).get("error", {}).get("code") == expected, response
    finally:
        stdio.close()
        stdio.proc.wait(timeout=5)
    assert snapshot(data) == before

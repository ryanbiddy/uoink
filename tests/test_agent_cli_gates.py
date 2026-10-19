"""Gate parity through real CLI and stdio subprocesses on disposable profiles."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.test_c01_mcp_stdio import ROOT, _StdioClient, _isolated_env


@pytest.fixture
def transports(tmp_path):
    env = _isolated_env(str(tmp_path))
    # Only the optional Whisper runtime is synthetic. The real consent check,
    # cache probe, CLI, registry, backend and stdio adapter all run unchanged.
    stub = tmp_path / "optional-runtime"
    stub.mkdir()
    (stub / "whisperx.py").write_text(
        "def load_model(*args, **kwargs):\n    raise AssertionError('consent must precede model loading')\n", encoding="utf-8")
    env["PYTHONPATH"] = os.pathsep.join([str(stub), env.get("PYTHONPATH", "")])
    import index
    from tests.test_podcast_background_jobs import _seed_downloaded_episodes
    idx = index.Index.open(tmp_path / "profile" / "index.db")
    import page_extractor
    page_extractor.add_allowed(idx, "192.168.1.2")
    idx._conn.commit()
    episode_id = _seed_downloaded_episodes(idx, tmp_path, count=1)[0]
    idx.close()
    client = _StdioClient([sys.executable, "-B", "-P", str(ROOT / "uoink_mcp.py")], tmp_path, env)
    client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "cli-gate-parity", "version": "0"}}})
    assert "result" in client.wait_for(1)
    client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def compare(name, args, friendly=None):
        client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                     "params": {"name": name, "arguments": args}})
        response = client.wait_for(2)["result"]
        assert response["isError"] is True
        expected = json.loads(response["content"][0]["text"])
        command = friendly or ["call", name, "--args", json.dumps(args)]
        result = subprocess.run([sys.executable, "-B", "-P", str(ROOT / "uoink_cli.py"), *command],
                                cwd=tmp_path, env=env, capture_output=True, text=True,
                                encoding="utf-8", timeout=60)
        assert result.returncode == 1, (result.stdout, result.stderr)
        assert result.stderr
        assert json.loads(result.stdout) == expected
        assert expected["ok"] is False
        return expected
    try:
        yield compare, episode_id
    finally:
        client.close()


def test_whisper_download_requires_consent(transports):
    compare, episode_id = transports
    body = compare("transcribe_podcast_episode", {"episode_id": episode_id, "model": "base"})
    assert body["consent_required"] is True
    assert "explicit consent" in body["error"]


def test_private_network_capture_is_refused(transports):
    compare, _ = transports
    url = "http://192.168.1.2/private-page"
    body = compare("uoink_page", {"url": url}, ["capture", url])
    assert "private targets are refused" in body["error"]


def test_source_consent_requires_dashboard_intent(transports):
    compare, _ = transports
    body = compare("set_source_consent", {"source_id": "src_" + "a" * 64, "consent_state": "on",
                   "expected_revision": 0, "expected_cursor_revision": 0, "operation_key": "enable-fixture"})
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["missing"] == ["user_intent_token"]


def test_apply_remains_disabled_without_intent(transports):
    compare, _ = transports
    body = compare("apply_reshelving", {"mode": "apply", "preview_id": "fixture",
                   "expected_projection_revision": 0, "delta_hash": "a" * 64, "operation_key": "apply-fixture"})
    # Apply is deliberately disabled across transports before any mutation.
    assert body["error"]["code"] == "apply_disabled"


def test_undo_requires_dashboard_intent(transports):
    compare, _ = transports
    body = compare("undo_library_apply", {"apply_id": "fixture", "expected_projection_revision": 0,
                   "operation_key": "undo-fixture"})
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["details"]["field"] == "user_intent_token"


@pytest.mark.parametrize("selector", ["../outside", r"..\outside", "absolute", "output-path"])
def test_export_cannot_accept_paths(transports, tmp_path, selector):
    compare, _ = transports
    outside = tmp_path / "outside.txt"
    outside.write_text("private fixture", encoding="utf-8")
    args = {"video_id": str(outside) if selector == "absolute" else selector, "start": 0, "end": 1}
    if selector == "output-path":
        args.update(video_id="fixture", output_path=str(outside))
    body = compare("export_cited_range", args)
    # Identities are opaque SQLite keys, never paths. A path-looking key is
    # absent; an output_path field is rejected by the read-only export schema.
    assert body["error"]["code"] == ("invalid_request" if selector == "output-path" else "resource_not_found")
    assert "private fixture" not in json.dumps(body)
    assert outside.read_text(encoding="utf-8") == "private fixture"

"""Only the process that owns the helper port may write the auth token.

A duplicate launch, CLI or MCP process imports server.py too. If it minted a
token at import time it could replace the file a running helper's clients
read, and every extension or menu request would then fail authentication.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

import server
from tests.test_install_isolation import (
    ROOT, _child_env, _free_loopback_port, _start_isolated_helper, _stop_isolated_helper, _wait_health, iso)


def _authorized(port: int, token: str) -> bool:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/settings", headers={"X-Uoink-Token": token})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        assert error.code == 403
        return False


@pytest.mark.parametrize("content", [None, "", "\n"])
def test_import_time_token_is_never_written(monkeypatch, tmp_path, content):
    path = tmp_path / "token.txt"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(server, "TOKEN_PATH", path)
    token = server._load_or_create_token()
    assert len(token) >= 32
    assert (path.read_text(encoding="utf-8") if path.exists() else None) == content


def test_existing_token_is_kept_and_unreadable_token_is_ignored(monkeypatch, tmp_path):
    path = tmp_path / "token.txt"
    monkeypatch.setattr(server, "TOKEN_PATH", path)
    path.write_text("kept-token\n", encoding="utf-8")
    assert server._load_or_create_token() == "kept-token"
    path.write_bytes(b"\xff\xfe\xfa")
    assert server._read_token_file() == ""


def test_owner_persists_its_token_once(monkeypatch, tmp_path):
    path = tmp_path / "token.txt"
    monkeypatch.setattr(server, "TOKEN_PATH", path)
    server._persist_token("owner-token")
    assert path.read_text(encoding="utf-8") == "owner-token"
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0
    before = path.stat().st_mtime_ns
    server._persist_token("owner-token")
    assert path.stat().st_mtime_ns == before


@pytest.mark.parametrize("content", [None, ""])
def test_duplicate_launch_leaves_running_helper_token_intact(tmp_path, content):
    canary = tmp_path / "user"
    profile = tmp_path / "profile"
    canary.mkdir()
    profile.mkdir()
    port = _free_loopback_port()
    proc = _start_isolated_helper(profile, port, canary, tmp_path / "helper.log")
    try:
        _wait_health(port)
        token_path = profile / "token.txt"
        token = token_path.read_text(encoding="utf-8").strip()
        assert token and _authorized(port, token)
        # Simulate a lost or emptied token file while the helper is running.
        if content is None:
            token_path.unlink()
        else:
            token_path.write_text(content, encoding="utf-8")
        duplicate = subprocess.run(
            [sys.executable, "-B", str(ROOT / "server.py"), iso.CLI_PROFILE, str(profile), iso.CLI_PORT, str(port)],
            cwd=str(ROOT), env=_child_env(canary), capture_output=True, text=True, timeout=120)
        assert duplicate.returncode == 0, duplicate.stdout + duplicate.stderr
        assert "already running" in duplicate.stdout + duplicate.stderr
        assert (token_path.read_text(encoding="utf-8") if token_path.exists() else None) == content
        assert _authorized(port, token)
    finally:
        _stop_isolated_helper(profile, port, canary, proc)

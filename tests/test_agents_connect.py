"""Empirical tests for Fix 4A -- agent detection + one-click connect.

Run: python tests/test_agents_connect.py
Exercises server._detect_ai_clients (shape) and server._connect_ai_client
(config edit, .bak backup, JSON validation, idempotency, new-file creation,
malformed-config refusal, backup-failure refusal, Cline detection, unknown
client). Monkeypatches the client spec to point at a temp file so the test
never touches a real install. No network.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_detect_shape():
    agents = server._detect_ai_clients()
    names = {a["name"] for a in agents}
    _assert(names == set(server.AGENT_CLIENTS), f"detect names: {names}")
    for a in agents:
        for k in ("name", "label", "installed", "config_path",
                  "config_exists", "connected"):
            _assert(k in a, f"agent dict missing {k}: {a}")
        _assert(isinstance(a["installed"], bool), "installed must be bool")
    print("ok  _detect_ai_clients: 4 clients, full shape")


def test_plain_vscode_is_not_cline(tmp: Path):
    appdata = tmp / "Roaming"
    local = tmp / "Local"
    (appdata / "Code").mkdir(parents=True)
    old_appdata = os.environ.get("APPDATA")
    old_local = os.environ.get("LOCALAPPDATA")
    os.environ["APPDATA"] = str(appdata)
    os.environ["LOCALAPPDATA"] = str(local)
    try:
        cline = next(
            item for item in server._detect_ai_clients()
            if item["name"] == "cline")
    finally:
        if old_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = old_appdata
        if old_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old_local
    _assert(cline["installed"] is False,
            f"plain VS Code must not count as Cline: {cline}")
    print("ok  _detect_ai_clients: plain VS Code is not a Cline install")


def _patch_spec(monkey_path: Path, *, label="Test Client", name="claude-desktop"):
    """Return a spec whose config + marker live under monkey_path."""
    return {
        "name": name,
        "label": label,
        "config_path": monkey_path / "cfg.json",
        "markers": [monkey_path],  # the temp dir itself is the "install marker"
    }


def test_connect_creates_new(tmp: Path):
    spec = _patch_spec(tmp)
    orig = server._agent_client_spec
    server._agent_client_spec = lambda n: spec if n == "claude-desktop" else None
    try:
        res = server._connect_ai_client("claude-desktop")
        _assert(res["action"] == "added", f"first connect adds: {res}")
        _assert(res["created_config"] is True, "config file was created")
        _assert(res["backup_path"] is None, "no backup for a brand-new file")
        cfg = json.loads((tmp / "cfg.json").read_text(encoding="utf-8"))
        _assert("uoink" in cfg["mcpServers"], "uoink entry written")
        _assert(cfg["mcpServers"]["uoink"]["command"], "entry has a command")
    finally:
        server._agent_client_spec = orig
    print("ok  _connect_ai_client: creates new config with uoink entry")


def test_connect_preserves_and_backs_up(tmp: Path):
    cfg_path = tmp / "cfg.json"
    cfg_path.write_text(json.dumps({
        "mcpServers": {"other": {"command": "x", "args": []}},
        "theme": "dark",  # an unrelated key that MUST survive
    }), encoding="utf-8")
    spec = _patch_spec(tmp)
    orig = server._agent_client_spec
    server._agent_client_spec = lambda n: spec if n == "claude-desktop" else None
    try:
        res = server._connect_ai_client("claude-desktop")
        _assert(res["action"] == "added", "adds uoink alongside existing")
        _assert(res["backup_path"] and Path(res["backup_path"]).exists(),
                ".bak backup written")
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        _assert("other" in cfg["mcpServers"], "existing server preserved")
        _assert("uoink" in cfg["mcpServers"], "uoink added")
        _assert(cfg.get("theme") == "dark", "unrelated keys preserved")
        bak = json.loads(Path(res["backup_path"]).read_text(encoding="utf-8"))
        _assert("uoink" not in bak["mcpServers"], "backup is the PRE-edit file")

        # Idempotent: connecting again reports "updated", not a second add.
        res2 = server._connect_ai_client("claude-desktop")
        _assert(res2["action"] == "updated", f"second connect updates: {res2}")
    finally:
        server._agent_client_spec = orig
    print("ok  _connect_ai_client: preserves keys, backs up, idempotent")


def test_connect_refuses_malformed(tmp: Path):
    cfg_path = tmp / "cfg.json"
    cfg_path.write_text("{ this is not valid json ", encoding="utf-8")
    spec = _patch_spec(tmp)
    orig = server._agent_client_spec
    server._agent_client_spec = lambda n: spec if n == "claude-desktop" else None
    try:
        try:
            server._connect_ai_client("claude-desktop")
        except ValueError as e:
            _assert(getattr(e, "http_status", None) == 422,
                    "malformed JSON -> 422")
            # The original malformed file must be left exactly as-is.
            _assert(cfg_path.read_text(encoding="utf-8").startswith("{ this"),
                    "malformed config must NOT be clobbered")
            print("ok  _connect_ai_client: refuses to clobber malformed JSON")
            return
        raise AssertionError("malformed config should have raised")
    finally:
        server._agent_client_spec = orig


def test_connect_refuses_when_backup_fails(tmp: Path):
    cfg_path = tmp / "cfg.json"
    original = json.dumps({"theme": "dark"})
    cfg_path.write_text(original, encoding="utf-8")
    spec = _patch_spec(tmp)
    orig_spec = server._agent_client_spec
    orig_copy = server.shutil.copy2
    server._agent_client_spec = lambda n: spec if n == "claude-desktop" else None
    server.shutil.copy2 = lambda *_a, **_k: (_ for _ in ()).throw(
        OSError(f"raw machinery at {tmp / 'private-path'}"))
    try:
        try:
            server._connect_ai_client("claude-desktop")
        except ValueError as e:
            message = str(e)
            _assert(getattr(e, "http_status", None) == 500,
                    "backup failure -> 500")
            _assert("back up" in message.lower(), f"actionable error: {message}")
            _assert(str(tmp) not in message and "raw machinery" not in message,
                    f"user-facing error must be sanitized: {message}")
            _assert(cfg_path.read_text(encoding="utf-8") == original,
                    "config must remain byte-for-byte unchanged")
            _assert(not (tmp / "cfg.json.tmp").exists(),
                    "no temp edit should be written after backup failure")
            print("ok  _connect_ai_client: backup failure refuses edit + "
                  "sanitizes error")
            return
        raise AssertionError("backup failure should have raised")
    finally:
        server._agent_client_spec = orig_spec
        server.shutil.copy2 = orig_copy


def test_connect_unknown_client():
    try:
        server._connect_ai_client("not-a-real-client")
    except ValueError as e:
        _assert(getattr(e, "http_status", None) == 404, "unknown -> 404")
        print("ok  _connect_ai_client: unknown client -> 404")
        return
    raise AssertionError("unknown client should have raised")


def main():
    test_detect_shape()
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        detect = base / "detect"
        detect.mkdir()
        test_plain_vscode_is_not_cline(detect)
        for name, fn in [("new", test_connect_creates_new),
                         ("preserve", test_connect_preserves_and_backs_up),
                         ("malformed", test_connect_refuses_malformed),
                         ("backup", test_connect_refuses_when_backup_fails)]:
            sub = base / name
            sub.mkdir()
            fn(sub)
    test_connect_unknown_client()
    print("\nALL AGENT CONNECT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

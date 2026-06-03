"""Empirical tests for Fix 4A -- agent detection + one-click connect.

Run: python tests/test_agents_connect.py
Exercises server._detect_ai_clients (shape) and server._connect_ai_client
(config edit, .bak backup, JSON validation, idempotency, new-file creation,
malformed-config refusal, unknown client). Monkeypatches the client spec to
point at a temp file so the test never touches a real install. No network.
"""
from __future__ import annotations

import json
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
        for name, fn in [("new", test_connect_creates_new),
                         ("preserve", test_connect_preserves_and_backs_up),
                         ("malformed", test_connect_refuses_malformed)]:
            sub = base / name
            sub.mkdir()
            fn(sub)
    test_connect_unknown_client()
    print("\nALL AGENT CONNECT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

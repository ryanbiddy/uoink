import json
from pathlib import Path

import server


def _capture_cli(monkeypatch):
    printed = []
    monkeypatch.setattr(server, "_print_json", printed.append)
    return printed


def test_positional_doctor_uses_existing_doctor_command(monkeypatch):
    printed = _capture_cli(monkeypatch)
    monkeypatch.setattr(server, "doctor_payload", lambda: {"ok": True})

    assert server.run_cli(["doctor"]) == 0
    assert printed == [{"ok": True}]


def test_positional_rebuild_uses_existing_rebuild_command(monkeypatch, tmp_path):
    printed = _capture_cli(monkeypatch)
    calls = []
    monkeypatch.setattr(
        server,
        "rebuild_index_from_disk",
        lambda *, root=None: calls.append(root) or {"ok": True},
    )

    assert server.run_cli(["rebuild-index", str(tmp_path)]) == 0
    assert calls == [Path(tmp_path)]
    assert printed == [{"ok": True}]


def test_search_calls_running_http_registry(monkeypatch):
    printed = _capture_cli(monkeypatch)
    calls = []
    monkeypatch.setattr(
        server,
        "_call_http_registry_tool",
        lambda name, arguments: calls.append((name, arguments))
        or {"ok": True, "result": {"results": []}},
    )

    assert server.run_cli(["search", "two", "words"]) == 0
    assert calls == [("search_uoinks", {"query": "two words"})]
    assert printed[0]["ok"] is True


def test_clips_calls_running_http_registry(monkeypatch):
    printed = _capture_cli(monkeypatch)
    calls = []
    monkeypatch.setattr(
        server,
        "_call_http_registry_tool",
        lambda name, arguments: calls.append((name, arguments))
        or {"ok": True, "result": {"results": []}},
    )

    assert server.run_cli(["clips", "exact phrase"]) == 0
    assert calls == [("search_clips", {"query": "exact phrase"})]
    assert printed[0]["ok"] is True


def test_query_commands_reject_an_empty_query(monkeypatch):
    printed = _capture_cli(monkeypatch)

    assert server.run_cli(["search"]) == 1
    assert printed == [{"ok": False, "error": "search needs a query"}]


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"ok": true, "result": {"results": []}}'


def test_http_registry_client_sends_auth_and_json(monkeypatch):
    seen = []

    def fake_urlopen(request, timeout):
        seen.append((request, timeout))
        return _FakeResponse()

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(server, "TOKEN", "test-token")

    payload = server._call_http_registry_tool(
        "search_uoinks", {"query": "local first"}, timeout=4.5)

    request, timeout = seen[0]
    assert payload["ok"] is True
    assert timeout == 4.5
    assert request.full_url.endswith("/tools/search_uoinks")
    assert request.get_header("X-uoink-token") == "test-token"
    assert json.loads(request.data) == {"query": "local first"}


def test_wrappers_forward_to_server_cli():
    root = Path(__file__).resolve().parents[1]
    windows = (root / "uoink.cmd").read_text(encoding="utf-8")
    posix = (root / "uoink").read_text(encoding="utf-8")

    assert '"%UOINK_ROOT%server.py" %*' in windows
    assert '"$uoink_root/server.py" "$@"' in posix

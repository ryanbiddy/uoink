"""Make a Short with Zing: the probe and the detached hand-off, all mocked.

No real zing binary, process, network or browser runs here: shutil.which,
subprocess.run and subprocess.Popen are replaced.
"""
from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402

GOOD_PROBE = {"ok": True, "contract": "ryan.suite.handoff", "version": 1, "service": "zing",
              "service_version": "1.0.0rc1", "accepts": ["uoink.item/1"],
              "needs": ["uoink.media.handoff/1"]}
PAGE = "http://127.0.0.1:51234/?t=SECRETPAGETOKEN"
GOOD_LINE = {"ok": True, "contract": "ryan.suite.handoff", "version": 1, "project": "/tmp/proj",
             "page": PAGE, "item_ref": "uoink://item/abc12345", "reused": False}


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})

    def no_real_run(*args, **kwargs):
        raise AssertionError("a real process must not start in these tests")
    monkeypatch.setattr(server.subprocess, "run", no_real_run)
    monkeypatch.setattr(server.subprocess, "Popen", no_real_run)
    monkeypatch.setattr(server, "_zing_search_dirs", lambda: [])
    monkeypatch.setattr(server.sys, "platform", "linux")   # Windows tests set win32 themselves


def found(monkeypatch, exe="/usr/bin/zing"):
    monkeypatch.setattr(server.shutil, "which",
                        lambda name, path=None: exe if name == "zing" else None)


def probe_says(monkeypatch, out, code=0):
    found(monkeypatch)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        if isinstance(out, Exception):
            raise out
        text = out if isinstance(out, str) else json.dumps(out)
        return subprocess.CompletedProcess(argv, code, stdout=text.encode(), stderr=b"")
    monkeypatch.setattr(server.subprocess, "run", fake_run)
    return calls


# ---- probe ------------------------------------------------------------------

def test_probe_good(monkeypatch):
    calls = probe_says(monkeypatch, GOOD_PROBE)
    result = server._zing_probe()
    assert result == {"ok": True, "available": True, "service_version": "1.0.0rc1", "reason": ""}
    assert calls[0][0] == ["/usr/bin/zing", "from-uoink", "--probe", "--json"]
    assert calls[0][1]["timeout"] == 5
    assert "shell" not in calls[0][1]


@pytest.mark.parametrize("payload", [
    {**GOOD_PROBE, "contract": "something.else"},
    {**GOOD_PROBE, "version": 2},
    {**GOOD_PROBE, "version": True},
    {**GOOD_PROBE, "ok": False},
    {k: v for k, v in GOOD_PROBE.items() if k != "accepts"},
    {**GOOD_PROBE, "accepts": ["other/1"]},
    {**GOOD_PROBE, "accepts": "uoink.item/1"},
    ["not", "an", "object"],
])
def test_probe_wrong_shape_is_unavailable(monkeypatch, payload):
    probe_says(monkeypatch, payload)
    result = server._zing_probe()
    assert result["available"] is False and result["reason"] and result["ok"] is True


def test_probe_bad_json_nonzero_and_timeout(monkeypatch):
    probe_says(monkeypatch, "not json at all")
    assert server._zing_probe()["available"] is False
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, GOOD_PROBE, code=2)
    assert server._zing_probe()["available"] is False
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, subprocess.TimeoutExpired("zing", 5))
    result = server._zing_probe()
    assert result["available"] is False and "in time" in result["reason"]
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, OSError("nope"))
    assert server._zing_probe()["available"] is False


def test_probe_not_on_path(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name, path=None: None)
    result = server._zing_probe()
    assert result == {"ok": True, "available": False, "service_version": None,
                      "reason": "Zing is not installed."}


def test_probe_is_cached_and_a_miss_expires_sooner(monkeypatch):
    calls = probe_says(monkeypatch, GOOD_PROBE)
    clock = [1000.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    server._zing_probe()
    clock[0] += 200
    server._zing_probe()
    assert len(calls) == 1
    clock[0] += 200          # past the five-minute window
    server._zing_probe()
    assert len(calls) == 2

    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    calls = probe_says(monkeypatch, "garbage")
    server._zing_probe()
    clock[0] += 31
    server._zing_probe()
    assert len(calls) == 2


def test_finds_zing_in_a_user_bin_folder(monkeypatch, tmp_path):
    seen = []

    def which(name, path=None):
        seen.append(path)
        return str(tmp_path / "zing") if path == str(tmp_path) else None
    monkeypatch.setattr(server.shutil, "which", which)
    monkeypatch.setattr(server, "_zing_search_dirs", lambda: [str(tmp_path)])
    assert server._find_zing() == str(tmp_path / "zing")
    assert seen == [None, str(tmp_path)]


def test_windows_only_accepts_launchers_and_wraps_cmd(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server.shutil, "which", lambda name, path=None: "C:/x/zing.ps1")
    assert server._find_zing() is None
    monkeypatch.setenv("COMSPEC", "C:/Windows/System32/cmd.exe")
    assert server._zing_argv("C:/x/zing.cmd", "from-uoink", "--json") == [
        "C:/Windows/System32/cmd.exe", "/d", "/c", "C:/x/zing.cmd", "from-uoink", "--json"]
    assert server._zing_argv("C:/x/zing.exe", "from-uoink") == ["C:/x/zing.exe", "from-uoink"]
    assert server._zing_argv("C:/x & y/zing.cmd", "from-uoink") is None


# ---- hand-off ---------------------------------------------------------------

class FakeProc:
    def __init__(self, lines):
        self.stdout = io.BytesIO(b"".join(line if isinstance(line, bytes) else line.encode() for line in lines))
        self.waited = False
        self.killed = False

    def wait(self):
        self.waited = True

    def kill(self):
        self.killed = True

    terminate = kill


class FakeIndex:
    def __init__(self, rows):
        self.rows = rows

    def get_yoink(self, vid):
        return self.rows.get(vid)


@pytest.fixture
def handoff(monkeypatch):
    probe_says(monkeypatch, GOOD_PROBE)
    monkeypatch.setattr(server, "_get_index", lambda: FakeIndex({
        "abc12345": {"video_id": "abc12345"},
        "gone1234": {"video_id": "gone1234", "deleted_at": "2026-01-01"}}))
    monkeypatch.setattr(server.suite_service, "_active_base_url", lambda: "http://127.0.0.1:5999")
    monkeypatch.setattr(server, "TOKEN", "helper-token-value")
    spawned = []
    box = {"proc": FakeProc([json.dumps(GOOD_LINE) + "\n", "later output\n"])}

    def fake_popen(argv, **kwargs):
        spawned.append((argv, kwargs))
        return box["proc"]
    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)
    drained = []
    real_drain = server._zing_drain
    monkeypatch.setattr(server, "_zing_drain", lambda proc: (real_drain(proc), drained.append(proc)))
    return spawned, box, drained


def test_handoff_success(handoff, monkeypatch):
    spawned, box, _ = handoff
    monkeypatch.setattr(server.sys, "platform", "linux")
    status, body = server._zing_handoff("abc12345")
    assert (status, body) == (200, {"ok": True, "page": PAGE, "project": "/tmp/proj", "reused": False})
    argv, kw = spawned[0]
    assert argv == ["/usr/bin/zing", "from-uoink", "uoink://item/abc12345", "--json"]
    assert kw["env"]["UOINK_TOKEN"] == "helper-token-value"
    assert kw["env"]["UOINK_URL"] == "http://127.0.0.1:5999"
    assert kw["stdin"] == subprocess.DEVNULL and kw["stdout"] == subprocess.PIPE
    assert kw["stderr"] == subprocess.DEVNULL
    assert kw["start_new_session"] is True
    assert "shell" not in kw
    assert box["proc"].killed is False


def test_handoff_detach_flags_per_platform(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "linux")
    assert server._zing_popen_flags(["/usr/bin/zing"]) == {"start_new_session": True, "close_fds": True}
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server.subprocess, "DETACHED_PROCESS", 0x8, raising=False)
    monkeypatch.setattr(server.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    exe = server._zing_popen_flags(["C:/x/zing.exe"])
    assert exe["creationflags"] == 0x8 | 0x200
    cmd = server._zing_popen_flags(["C:/Windows/System32/cmd.exe", "/c"])
    assert cmd["creationflags"] == server.CREATE_NO_WINDOW | 0x200


def test_handoff_reused_flag_and_drain_reaps(handoff):
    _, box, drained = handoff
    box["proc"] = FakeProc([json.dumps({**GOOD_LINE, "reused": True}) + "\n"])
    status, body = server._zing_handoff("abc12345")
    assert status == 200 and body["reused"] is True
    import time
    for _ in range(100):
        if box["proc"].waited:
            break
        time.sleep(0.01)
    assert box["proc"].waited is True and box["proc"].killed is False


@pytest.mark.parametrize("code, expect", [
    ("invalid_ref", "did not accept"),
    ("uoink_unavailable", "reach Uoink"),
    ("media_unavailable", "Keep this item's media first"),
    ("project_exists", "already has a project"),
    ("failed", "could not start"),
    ("brand_new_code", "could not start"),
])
def test_handoff_maps_each_zing_error(handoff, code, expect):
    _, box, _ = handoff
    box["proc"] = FakeProc([json.dumps({"ok": False, "contract": "ryan.suite.handoff", "version": 1,
                                        "error": code, "message": "raw words"}) + "\n"])
    status, body = server._zing_handoff("abc12345")
    assert status == 502 and body["ok"] is False
    assert expect in body["message"] and "raw words" not in body["message"]
    assert body["error"] == (code if code != "brand_new_code" else "failed")


def test_media_unavailable_message_names_the_setting(handoff):
    assert "keep_media" in server._ZING_ERROR_TEXT["media_unavailable"]


@pytest.mark.parametrize("line", [
    "", "not json\n", "[]\n",
    json.dumps({**GOOD_LINE, "contract": "other"}) + "\n",
    json.dumps({**GOOD_LINE, "page": "https://example.com/?t=x"}) + "\n",
    json.dumps({**GOOD_LINE, "page": "http://127.0.0.1:99999999/?t=x"}) + "\n",
    json.dumps({**GOOD_LINE, "page": "http://127.0.0.1:5000/other?t=x"}) + "\n",
    json.dumps({**GOOD_LINE, "page": "http://127.0.0.1@evil.test:5000/?t=x"}) + "\n",
    json.dumps({**GOOD_LINE, "project": 5}) + "\n",
])
def test_handoff_refuses_unreadable_or_non_local_answers(handoff, line):
    _, box, _ = handoff
    box["proc"] = FakeProc([line])
    status, body = server._zing_handoff("abc12345")
    assert status == 502 and body["ok"] is False and "page" not in body


def test_handoff_first_line_timeout_leaves_child_running(handoff, monkeypatch):
    _, box, _ = handoff

    class Silent(FakeProc):
        def __init__(self):
            super().__init__([])
            self.stdout = self

        def readline(self):
            import time
            time.sleep(0.3)
            return b""

        def __iter__(self):
            return iter(())
    box["proc"] = Silent()
    monkeypatch.setattr(server, "_ZING_FIRST_LINE_TIMEOUT", 0.05)
    status, body = server._zing_handoff("abc12345")
    assert status == 504 and body["error"] == "timeout"
    assert box["proc"].killed is False


def test_handoff_rejects_bad_missing_and_deleted_ids(handoff):
    spawned, _, _ = handoff
    for bad in (None, "", "short", "has space1", "a/../b12345", "abc12345\n", "x" * 201, 12345678):
        status, body = server._zing_handoff(bad)
        assert status == 400 and body["error"] == "invalid_id", bad
    assert server._zing_handoff("nothere1")[0] == 404
    assert server._zing_handoff("gone1234")[0] == 404
    assert spawned == []


def test_handoff_refused_when_probe_unavailable(handoff, monkeypatch):
    spawned, _, _ = handoff
    probe_says(monkeypatch, {**GOOD_PROBE, "accepts": []})
    status, body = server._zing_handoff("abc12345")
    assert status == 409 and body["error"] == "zing_unavailable"
    assert spawned == []


def test_handoff_start_failure(handoff, monkeypatch):
    def boom(argv, **kw):
        raise OSError("denied")
    monkeypatch.setattr(server.subprocess, "Popen", boom)
    status, body = server._zing_handoff("abc12345")
    assert status == 502 and body["error"] == "failed"


def test_token_and_page_token_never_logged(handoff, caplog):
    with caplog.at_level(logging.DEBUG, logger="uoink"):
        server._zing_handoff("abc12345")
        server._zing_handoff("nothere1")
    text = caplog.text
    assert "helper-token-value" not in text
    assert "SECRETPAGETOKEN" not in text and "t=" not in text


# ---- routes: token gate -----------------------------------------------------

def make_handler(token_ok):
    sent = []
    handler = object.__new__(server.Handler)
    handler.headers = {"X-Uoink-Token": "helper-token-value" if token_ok else "wrong"}
    handler.command = "GET"
    handler.path = "/zing/status"
    handler._send_json = lambda status, payload: sent.append((status, payload))
    handler._body_consumed = True
    return handler, sent


def test_status_route_needs_the_token(monkeypatch):
    monkeypatch.setattr(server, "TOKEN", "helper-token-value")
    handler, sent = make_handler(False)
    handler._handle_zing_status()
    assert sent == [(403, {"ok": False, "error": "missing or invalid token"})]


def test_status_route_returns_probe(monkeypatch):
    monkeypatch.setattr(server, "TOKEN", "helper-token-value")
    probe_says(monkeypatch, GOOD_PROBE)
    handler, sent = make_handler(True)
    handler._handle_zing_status()
    assert sent[0][0] == 200 and sent[0][1]["available"] is True


def test_status_never_raises_even_if_probe_internals_break(monkeypatch):
    found(monkeypatch)
    monkeypatch.setattr(server, "_zing_probe_uncached", lambda: 1 / 0)
    result = server._zing_probe()
    assert result["available"] is False and result["ok"] is True

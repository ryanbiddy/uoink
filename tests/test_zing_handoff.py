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
    assert result == {"ok": True, "available": True, "service_version": "1.0.0rc1", "reason": "",
                      "features": []}
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
                      "reason": "Zing is not installed.", "features": []}


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


# ---- hand-off jobs ----------------------------------------------------------

class FakeProc:
    def __init__(self, lines, err=()):
        self.stdout = io.BytesIO(b"".join(line if isinstance(line, bytes) else line.encode() for line in lines))
        self.stderr = io.BytesIO(b"".join(line if isinstance(line, bytes) else line.encode() for line in err))
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


PROBE_WITH_DOWNLOAD = {**GOOD_PROBE, "features": ["allow_download"]}
NEEDED = {"ok": False, "contract": "ryan.suite.handoff", "version": 1, "error": "download_needed",
          "message": "Uoink did not keep this video. Zing can download it from www.evil.test. Run again with --allow-download."}


def progress(pct):
    return json.dumps({"contract": "ryan.suite.handoff", "version": 1, "progress": "download",
                       "percent": pct}) + "\n"


@pytest.fixture(autouse=True)
def clean_jobs(monkeypatch):
    monkeypatch.setattr(server, "_zing_jobs", {})


@pytest.fixture
def handoff(monkeypatch):
    probe_says(monkeypatch, GOOD_PROBE)
    monkeypatch.setattr(server, "_get_index", lambda: FakeIndex({
        "abc12345": {"video_id": "abc12345",
                     "metadata_json": json.dumps({"url": "https://www.youtube.com/watch?v=abc12345"})},
        "nourl123": {"video_id": "nourl123"},
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


def settle(job_id):
    """Poll the job route's function until the reader thread has finished."""
    import time
    for _ in range(300):
        status, body = server._zing_job_status(job_id)
        assert status == 200
        if body["state"] != "running":
            return body
        time.sleep(0.01)
    raise AssertionError("job never settled")


def run(vid="abc12345", allow=False):
    status, body = server._zing_handoff(vid, allow)
    assert status == 202 and body["ok"] is True and set(body) == {"ok", "job_id"}
    return settle(body["job_id"])


def test_probe_features_parsed(monkeypatch):
    probe_says(monkeypatch, PROBE_WITH_DOWNLOAD)
    assert server._zing_probe()["features"] == ["allow_download"]
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, {**GOOD_PROBE, "features": ["allow_download", 5, None]})
    assert server._zing_probe()["features"] == ["allow_download"]
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, {**GOOD_PROBE, "features": "allow_download"})
    assert server._zing_probe()["features"] == []
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, GOOD_PROBE)
    assert server._zing_probe()["features"] == []     # an older Zing: no download offer


def test_handoff_success_is_a_job(handoff, monkeypatch):
    spawned, box, _ = handoff
    monkeypatch.setattr(server.sys, "platform", "linux")
    job = run()
    assert job["state"] == "done" and job["error"] is None
    assert (job["page"], job["project"], job["reused"]) == (PAGE, "/tmp/proj", False)
    assert job["downloaded"] is False and job["percent"] is None
    argv, kw = spawned[0]
    assert argv == ["/usr/bin/zing", "from-uoink", "uoink://item/abc12345", "--json"]
    assert kw["env"]["UOINK_TOKEN"] == "helper-token-value"
    assert kw["env"]["UOINK_URL"] == "http://127.0.0.1:5999"
    assert kw["stdin"] == subprocess.DEVNULL and kw["stdout"] == subprocess.PIPE
    assert kw["stderr"] == subprocess.PIPE
    assert kw["start_new_session"] is True
    assert "shell" not in kw
    assert box["proc"].killed is False


def test_post_returns_before_zing_answers(handoff):
    _, box, _ = handoff
    import threading

    class Slow(FakeProc):
        def __init__(self):
            super().__init__([])
            self.gate = threading.Event()
            self.stdout = self

        def readline(self):
            self.gate.wait(5)
            return (json.dumps(GOOD_LINE) + "\n").encode()

        def __iter__(self):
            return iter(())
    box["proc"] = Slow()
    status, body = server._zing_handoff("abc12345")
    assert status == 202
    now = server._zing_job_status(body["job_id"])[1]
    assert now["state"] == "running" and now["page"] is None
    # One hand-off per item at a time.
    assert server._zing_handoff("abc12345")[0] == 409
    box["proc"].gate.set()
    assert settle(body["job_id"])["state"] == "done"


def test_flag_only_when_allowed_and_listed(handoff, monkeypatch):
    spawned, box, _ = handoff
    # Allowed by the click but Zing does not list it: no flag.
    run(allow=True)
    assert "--allow-download" not in spawned[-1][0]
    # Listed but the user did not click Download: no flag.
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, PROBE_WITH_DOWNLOAD)
    box["proc"] = FakeProc([json.dumps(GOOD_LINE) + "\n"])
    run(allow=False)
    assert "--allow-download" not in spawned[-1][0]
    # Anything but a real True is not consent.
    for loose in ("true", 1, None):
        box["proc"] = FakeProc([json.dumps(GOOD_LINE) + "\n"])
        settle(server._zing_handoff("abc12345", loose)[1]["job_id"])
        assert "--allow-download" not in spawned[-1][0]
    # Both: flag added.
    box["proc"] = FakeProc([json.dumps({**GOOD_LINE, "downloaded": True}) + "\n"])
    job = run(allow=True)
    assert spawned[-1][0] == ["/usr/bin/zing", "from-uoink", "uoink://item/abc12345", "--json",
                              "--allow-download"]
    assert job["state"] == "done" and job["downloaded"] is True


def test_progress_lines_parsed_and_noise_ignored(handoff, monkeypatch):
    _, box, _ = handoff
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, PROBE_WITH_DOWNLOAD)
    seen = []
    real = server._zing_progress_percent

    def spy(line):
        value = real(line)
        seen.append(value)
        return value
    monkeypatch.setattr(server, "_zing_progress_percent", spy)
    box["proc"] = FakeProc(
        [json.dumps({**GOOD_LINE, "downloaded": True}) + "\n"],
        err=["[download] plain line from yt-dlp\n", progress(10.0), "{not json\n", progress(10.0),
             progress(87.5), progress(3.0),            # a jump forward, then back: both fine
             json.dumps({"contract": "other", "progress": "download", "percent": 99}) + "\n",
             json.dumps({"contract": "ryan.suite.handoff", "version": 1, "progress": "download",
                         "percent": "50"}) + "\n",
             json.dumps({"contract": "ryan.suite.handoff", "version": 1, "progress": "merge",
                         "percent": 60}) + "\n",
             progress(250), b"\xff\xfe\n"])
    job = run(allow=True)
    assert [v for v in seen if v is not None] == [10.0, 10.0, 87.5, 3.0, 100.0]
    assert job["state"] == "done"


def test_percent_visible_while_running(handoff, monkeypatch):
    _, box, _ = handoff
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, PROBE_WITH_DOWNLOAD)
    import threading
    import time

    class Waiting(FakeProc):
        def __init__(self):
            super().__init__([], err=[progress(42.0)])
            self.gate = threading.Event()
            self.stdout = self

        def readline(self):
            self.gate.wait(5)
            return b""

        def __iter__(self):
            return iter(())
    proc = box["proc"] = Waiting()
    job_id = server._zing_handoff("abc12345", True)[1]["job_id"]
    for _ in range(300):
        body = server._zing_job_status(job_id)[1]
        if body["percent"] == 42.0:
            break
        time.sleep(0.01)
    assert body["state"] == "running" and body["percent"] == 42.0
    proc.gate.set()
    settle(job_id)


def test_download_needed_uses_uoinks_own_host(handoff, monkeypatch):
    _, box, _ = handoff
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, PROBE_WITH_DOWNLOAD)
    box["proc"] = FakeProc([json.dumps(NEEDED) + "\n"])
    job = run()
    assert job["state"] == "error" and job["error"] == "download_needed"
    assert job["host"] == "www.youtube.com"                 # not the host named in Zing's message
    assert "evil.test" not in json.dumps(job)
    assert job["percent"] is None and job["page"] is None


def test_download_needed_without_a_source_link_falls_back(handoff):
    _, box, _ = handoff
    box["proc"] = FakeProc([json.dumps(NEEDED) + "\n"])
    job = run("nourl123")
    assert job["error"] == "media_unavailable" and job["host"] is None
    assert "Keep this item's media first" in job["message"]


def test_source_host_reads_row_or_metadata():
    host = server._zing_source_host
    assert host({"source_url": "https://Example.com:8080/x?y=1"}) == "example.com"
    assert host({"url": "http://vimeo.com/1"}) == "vimeo.com"
    assert host({"metadata_json": json.dumps({"source_url": "https://x.org/a"})}) == "x.org"
    assert host({"url": "ftp://x.org/a"}) is None
    assert host({"metadata_json": "not json"}) is None
    assert host({"url": "http://[bad/"}) is None
    assert host({}) is None


def test_download_failed_mapped(handoff):
    _, box, _ = handoff
    box["proc"] = FakeProc([json.dumps({"ok": False, "contract": "ryan.suite.handoff", "version": 1,
                                        "error": "download_failed", "message": "raw words"}) + "\n"])
    job = run()
    assert job["error"] == "download_failed" and "could not download" in job["message"]
    assert "raw words" not in job["message"]


def test_long_timeout_only_with_the_flag(handoff, monkeypatch):
    _, box, _ = handoff
    waits = []
    monkeypatch.setattr(server, "_zing_first_line", lambda proc, timeout=None: waits.append(timeout))
    run()
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, PROBE_WITH_DOWNLOAD)
    run(allow=True)
    assert waits == [60, 75 * 60]
    # Allowed but not listed: still the short timeout.
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, GOOD_PROBE)
    run(allow=True)
    assert waits[-1] == 60


def test_detach_flags_per_platform(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "linux")
    assert server._zing_popen_flags(["/usr/bin/zing"]) == {"start_new_session": True, "close_fds": True}
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server.subprocess, "DETACHED_PROCESS", 0x8, raising=False)
    monkeypatch.setattr(server.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    exe = server._zing_popen_flags(["C:/x/zing.exe"])
    assert exe["creationflags"] == 0x8 | 0x200
    cmd = server._zing_popen_flags(["C:/Windows/System32/cmd.exe", "/c"])
    assert cmd["creationflags"] == server.CREATE_NO_WINDOW | 0x200


def test_reused_flag_and_drain_reaps(handoff):
    _, box, drained = handoff
    box["proc"] = FakeProc([json.dumps({**GOOD_LINE, "reused": True}) + "\n"])
    job = run()
    assert job["state"] == "done" and job["reused"] is True
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
def test_each_zing_error_is_mapped(handoff, code, expect):
    _, box, _ = handoff
    box["proc"] = FakeProc([json.dumps({"ok": False, "contract": "ryan.suite.handoff", "version": 1,
                                        "error": code, "message": "raw words"}) + "\n"])
    job = run()
    assert job["state"] == "error" and expect in job["message"] and "raw words" not in job["message"]
    assert job["error"] == (code if code != "brand_new_code" else "failed")


def test_media_unavailable_message_names_the_setting():
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
def test_refuses_unreadable_or_non_local_answers(handoff, line):
    _, box, _ = handoff
    box["proc"] = FakeProc([line])
    job = run()
    assert job["state"] == "error" and job["page"] is None


def test_first_line_timeout_leaves_child_running(handoff, monkeypatch):
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
    job = run()
    assert job["state"] == "error" and job["error"] == "timeout"
    assert box["proc"].killed is False


def test_rejects_bad_missing_and_deleted_ids(handoff):
    spawned, _, _ = handoff
    for bad in (None, "", "short", "has space1", "a/../b12345", "abc12345\n", "x" * 201, 12345678):
        status, body = server._zing_handoff(bad)
        assert status == 400 and body["error"] == "invalid_id", bad
    assert server._zing_handoff("nothere1")[0] == 404
    assert server._zing_handoff("gone1234")[0] == 404
    assert spawned == []


def test_refused_when_probe_unavailable(handoff, monkeypatch):
    spawned, _, _ = handoff
    probe_says(monkeypatch, {**GOOD_PROBE, "accepts": []})
    status, body = server._zing_handoff("abc12345")
    assert status == 409 and body["error"] == "zing_unavailable"
    assert spawned == []


def test_start_failure_is_immediate(handoff, monkeypatch):
    def boom(argv, **kw):
        raise OSError("denied")
    monkeypatch.setattr(server.subprocess, "Popen", boom)
    status, body = server._zing_handoff("abc12345")
    assert status == 502 and body["error"] == "failed"
    assert server._zing_jobs == {}


def test_job_lookup_states_and_404(handoff):
    status, body = server._zing_job_status("nope")
    assert status == 404 and body["ok"] is False
    assert server._zing_job_status(None)[0] == 404
    job = run()
    assert set(job) == {"ok", "job_id", "state", "percent", "page", "project", "reused", "downloaded",
                        "error", "message", "host"}


def test_job_cap_drops_oldest_finished_jobs(handoff, monkeypatch):
    _, box, _ = handoff
    monkeypatch.setattr(server, "_ZING_JOB_CAP", 3)
    ids = []
    for _ in range(5):
        box["proc"] = FakeProc([json.dumps(GOOD_LINE) + "\n"])
        ids.append(run()["job_id"])
    assert len(server._zing_jobs) <= 3
    assert server._zing_job_status(ids[0])[0] == 404
    assert server._zing_job_status(ids[-1])[0] == 200


def test_token_page_and_stderr_never_logged(handoff, monkeypatch, caplog):
    _, box, _ = handoff
    monkeypatch.setattr(server, "_zing_probe_cache", {"at": 0.0, "ttl": 0, "value": None})
    probe_says(monkeypatch, PROBE_WITH_DOWNLOAD)
    box["proc"] = FakeProc([json.dumps({**GOOD_LINE, "downloaded": True}) + "\n"],
                           err=["secret stderr text helper-token-value\n", progress(5.0)])
    with caplog.at_level(logging.DEBUG, logger="uoink"):
        run(allow=True)
        server._zing_handoff("nothere1")
    text = caplog.text
    assert "helper-token-value" not in text and "secret stderr" not in text
    assert "SECRETPAGETOKEN" not in text and "t=" not in text
    assert "youtube" not in text


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


def test_job_route_needs_the_token_and_serves_jobs(monkeypatch, handoff):
    monkeypatch.setattr(server, "TOKEN", "helper-token-value")
    handler, sent = make_handler(False)
    handler._handle_zing_job("whatever")
    assert sent == [(403, {"ok": False, "error": "missing or invalid token"})]
    job = run()
    handler, sent = make_handler(True)
    handler._handle_zing_job(job["job_id"])
    assert sent[0][0] == 200 and sent[0][1]["state"] == "done"
    handler, sent = make_handler(True)
    handler._handle_zing_job("unknown")
    assert sent[0][0] == 404

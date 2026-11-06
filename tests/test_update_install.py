"""Update now: the installer is downloaded only from GitHub, checked against the
release's SHA256SUMS.txt, and launched only when it matches. Every network and
process call is mocked; no installer ever runs."""
from __future__ import annotations

import hashlib
import io
import sys
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402

VERSION = "3.16.0"
EXE = f"Uoink-Setup-{VERSION}.exe"
BASE = f"https://github.com/ryanbiddy/uoink/releases/download/v{VERSION}/"
PAYLOAD = b"not a real installer" * 50


class FakeResponse:
    def __init__(self, body: bytes, length=None):
        self._buf = io.BytesIO(body)
        self.headers = {"Content-Length": str(len(body) if length is None else length)}

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def redirect(location: str, code=302):
    headers = Message()
    headers["Location"] = location
    return urllib.error.HTTPError("https://github.com/x", code, "Found", headers, io.BytesIO())


class ImmediateThread:
    def __init__(self, target, args=(), **kwargs):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


@pytest.fixture
def rig(monkeypatch, tmp_path):
    state = {"opened": [], "launched": [], "routes": {}}
    sums = f"{hashlib.sha256(PAYLOAD).hexdigest()}  {EXE}\n"
    state["routes"][BASE + "SHA256SUMS.txt"] = FakeResponse(sums.encode())
    state["routes"][BASE + EXE] = FakeResponse(PAYLOAD)

    def fake_open(url):
        state["opened"].append(url)
        if url.startswith(server._UPDATE_TAG_API):
            record = {"tag_name": f"v{VERSION}",
                      "assets": [{"name": EXE}, {"name": "SHA256SUMS.txt"}]}
            return FakeResponse(__import__("json").dumps(record).encode())
        route = state["routes"][url]
        if isinstance(route, Exception):
            raise route
        return route

    def no_network(*args, **kwargs):
        raise AssertionError("tests must not touch the network")

    monkeypatch.setattr(server, "_update_open", fake_open)
    monkeypatch.setattr(server.urllib.request, "urlopen", no_network)
    monkeypatch.setattr(server.source_subscriptions, "public_http_open", no_network)
    monkeypatch.setattr(server.subprocess, "Popen", no_network)
    monkeypatch.setattr(server, "_update_launch_installer",
                        lambda path, kind: state["launched"].append((path, kind)))
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_is_installed_build", lambda: True)
    monkeypatch.setattr(server, "_update_platform_asset",
                        lambda version: (f"Uoink-Setup-{version}.exe", "windows"))
    monkeypatch.setattr(server._install_isolation, "current_binding", lambda: None)
    monkeypatch.setattr(server, "_cached_update_result", lambda: {
        "current": "3.15.0", "latest": VERSION, "update_available": True,
        "url": f"https://github.com/ryanbiddy/uoink/releases/tag/v{VERSION}"})
    monkeypatch.setattr(server.threading, "Thread", ImmediateThread)
    server._update_install_job.clear()
    server._update_install_job["state"] = "idle"
    state["dir"] = tmp_path / "updates"
    return state


def test_matching_checksum_keeps_file_and_launches_with_silent_flags(rig):
    status, body = server._start_update_install()
    assert status == 202 and body["ok"] is True
    final = rig["dir"] / EXE
    assert final.read_bytes() == PAYLOAD
    assert not (rig["dir"] / (EXE + ".part")).exists()
    assert rig["launched"] == [(final, "windows")]
    done = server._update_status()
    assert done["state"] == "launching" and done["bytes_done"] == len(PAYLOAD)
    assert all(u.startswith(("https://github.com/", server._UPDATE_TAG_API)) for u in rig["opened"])


def test_installer_args_are_the_visible_silent_upgrade_flags():
    assert server._UPDATE_INSTALLER_ARGS == ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]


def test_launch_uses_popen_with_those_args(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(server.subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw)))
    server._update_launch_installer(tmp_path / EXE, "windows")
    server._update_launch_installer(tmp_path / "x.dmg", "mac")
    assert calls[0][0] == [str(tmp_path / EXE), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    assert calls[1][0] == ["open", str(tmp_path / "x.dmg")]


def test_checksum_mismatch_removes_part_and_does_not_launch(rig):
    rig["routes"][BASE + EXE] = FakeResponse(PAYLOAD + b"tampered")
    server._start_update_install()
    assert rig["launched"] == []
    assert list(rig["dir"].iterdir()) == []
    status = server._update_status()
    assert status["state"] == "error" and "checksum" in status["error"]


def test_missing_checksum_line_does_not_launch_or_download(rig):
    rig["routes"][BASE + "SHA256SUMS.txt"] = FakeResponse(
        f"{'a' * 64}  Uoink-3.16.0-macos-arm64.dmg\n".encode())
    server._start_update_install()
    assert rig["launched"] == []
    assert BASE + EXE not in rig["opened"]
    assert server._update_status()["state"] == "error"


def test_duplicate_checksum_lines_are_refused():
    line = f"{'b' * 64}  {EXE}\n"
    assert server._update_expected_sha(line, EXE) == "b" * 64
    assert server._update_expected_sha(line + line.replace("b", "c"), EXE) is None
    assert server._update_expected_sha(line.replace(EXE, "x-" + EXE), EXE) is None


def test_redirect_to_non_github_host_is_refused(rig):
    rig["routes"][BASE + EXE] = redirect("https://evil.example.com/Uoink.exe")
    server._start_update_install()
    assert rig["launched"] == []
    assert "evil.example.com/Uoink.exe" not in " ".join(rig["opened"])
    assert "leave GitHub" in server._update_status()["error"]


def test_redirect_to_github_asset_host_is_followed(rig):
    cdn = "https://objects.githubusercontent.com/abc/Uoink-Setup"
    rig["routes"][BASE + EXE] = redirect(cdn)
    rig["routes"][cdn] = FakeResponse(PAYLOAD)
    server._start_update_install()
    assert rig["launched"] and cdn in rig["opened"]


def test_size_cap_by_header_and_by_stream(rig, monkeypatch):
    monkeypatch.setattr(server, "_UPDATE_MAX_BYTES", 100)
    rig["routes"][BASE + EXE] = FakeResponse(PAYLOAD, length=10**9)
    server._start_update_install()
    assert rig["launched"] == [] and server._update_status()["state"] == "error"
    # A server that lies about Content-Length still stops at the cap.
    rig["routes"][BASE + EXE] = FakeResponse(PAYLOAD, length=1)
    server._start_update_install()
    assert rig["launched"] == []
    assert list(rig["dir"].iterdir()) == []


def test_isolated_binding_refuses_before_any_download(rig, monkeypatch):
    monkeypatch.setattr(server._install_isolation, "current_binding", lambda: object())
    status, body = server._start_update_install()
    assert status == 409 and body["ok"] is False and "isolated" in body["error"]
    assert rig["opened"] == [] and rig["launched"] == []
    assert server._update_install_action() is None


def test_source_run_is_refused(rig, monkeypatch):
    monkeypatch.setattr(server, "_is_installed_build", lambda: False)
    status, body = server._start_update_install()
    assert status == 409 and rig["opened"] == []


def test_wrong_platform_points_to_the_release_page(rig, monkeypatch):
    monkeypatch.undo()  # drop the rig's windows stub; this machine is stubbed below
    monkeypatch.setattr(server.sys, "platform", "linux")
    assert server._update_platform_asset(VERSION) is None
    monkeypatch.setattr(server, "_is_installed_build", lambda: True)
    monkeypatch.setattr(server._install_isolation, "current_binding", lambda: None)
    monkeypatch.setattr(server, "_cached_update_result", lambda: {
        "latest": VERSION, "update_available": True, "url": "https://github.com/ryanbiddy/uoink/releases/tag/v3.16.0"})
    status, body = server._start_update_install()
    assert status == 400 and body["unsupported"] is True
    assert body["url"].startswith("https://github.com/ryanbiddy/uoink/releases")
    assert server._update_install_action() is None


def test_platform_assets(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "win32")
    assert server._update_platform_asset("3.16.0") == ("Uoink-Setup-3.16.0.exe", "windows")
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(server.platform, "machine", lambda: "arm64")
    assert server._update_platform_asset("3.16.0") == ("Uoink-3.16.0-macos-arm64.dmg", "mac")
    monkeypatch.setattr(server.platform, "machine", lambda: "x86_64")
    assert server._update_platform_asset("3.16.0") is None


def test_no_update_reported_means_no_download(rig, monkeypatch):
    monkeypatch.setattr(server, "_cached_update_result", lambda: {
        "latest": "3.15.0", "update_available": False})
    status, _ = server._start_update_install()
    assert status == 409 and rig["opened"] == []


def test_a_bad_version_string_never_reaches_a_url(rig, monkeypatch):
    monkeypatch.setattr(server, "_cached_update_result", lambda: {
        "latest": "3.16.0/../../evil", "update_available": True})
    status, _ = server._start_update_install()
    assert status == 409 and rig["opened"] == []


def test_release_record_must_list_the_installer(rig, monkeypatch):
    monkeypatch.setattr(server, "_update_release_lists", lambda version, name: False)
    status, body = server._start_update_install()
    assert status == 502 and rig["launched"] == []


def test_second_press_while_downloading_is_refused(rig):
    server._update_install_job["state"] = "downloading"
    status, _ = server._start_update_install()
    assert status == 409 and rig["opened"] == []


def test_routes_are_token_gated_and_post_starts_the_job(monkeypatch):
    sent = []
    handler = object.__new__(server.Handler)
    handler._send_json = lambda status, payload: sent.append((status, payload))
    handler._require_token = lambda: False
    handler._handle_update_install_status()
    assert sent == []
    handler._require_token = lambda: True
    server._update_install_job.clear()
    server._update_install_job["state"] = "idle"
    handler._handle_update_install_status()
    assert sent[0] == (200, {"ok": True, "state": "idle"})

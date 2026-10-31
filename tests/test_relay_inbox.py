"""Uoink Relay, desktop side: settings, the keyring token, the relay-inbox
poller and its two routes.

The poller runs against a small fake relay on a loopback port with a stubbed
tools module. Settings live in tmp_path; the keyring is a fake. No real
relay, capture, network or credential store is used.
"""
from __future__ import annotations

import io
import json
import logging
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

import server

TOKEN = "pull-token-for-desktop-tests-" + "k" * 20
HELPER_TOKEN = "fixture-helper-token"
YOUTUBE = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
PAGE = "https://example.com/article"


def test_importing_the_helper_starts_no_relay_thread():
    assert not any(t.name == "relay-inbox" for t in threading.enumerate())


# ---- fixtures ----------------------------------------------------------------

class FakeKeyring:
    def __init__(self):
        self.values, self.calls = {}, []

    def get_password(self, service, username):
        self.calls.append(("get", service, username))
        return self.values.get((service, username))

    def set_password(self, service, username, value):
        self.calls.append(("set", service, username))
        self.values[service, username] = value

    def delete_password(self, service, username):
        self.calls.append(("delete", service, username))
        del self.values[service, username]


class NullKeyring(FakeKeyring):
    """Accepts writes and forgets them, like keyring.backends.null."""

    def set_password(self, service, username, value):
        self.calls.append(("set", service, username))


class Probe(server.Handler):
    def __init__(self, path, body=None, *, method="POST", headers=None):
        self.command = method
        self.path = path
        self.client_address = ("127.0.0.1", 1)
        raw = json.dumps(body if body is not None else {}).encode()
        self.rfile = io.BytesIO(raw)
        self.headers = {"Host": f"127.0.0.1:{server.PORT}", "X-Uoink-Token": HELPER_TOKEN,
                        "Content-Type": "application/json", "Content-Length": str(len(raw)),
                        **(headers or {})}
        self.status = self.payload = None

    def _send_json(self, status, payload):
        self.status, self.payload = status, payload


@pytest.fixture
def relay_state(monkeypatch):
    """Fresh in-memory poller state for every test."""
    monkeypatch.setattr(server, "_relay_state", {
        "last_poll_at": None, "last_ok_at": None, "last_error": None, "last_capture_error": None,
        "picked_up_total": 0, "last_pending_count": None, "polling": False, "generation": 0,
        "next_due": 0.0})
    monkeypatch.setattr(server, "_relay_raises", {})
    monkeypatch.setattr(server, "_relay_done", {})
    monkeypatch.setattr(server, "_relay_wake", threading.Event())
    monkeypatch.setattr(server, "_relay_stop", threading.Event())
    monkeypatch.setattr(server, "_relay_cond", threading.Condition())
    return server._relay_state


@pytest.fixture
def settings_route(tmp_path, monkeypatch, relay_state):
    fake = FakeKeyring()
    monkeypatch.setattr(server, "_keyring", fake)
    monkeypatch.setattr(server, "_isolated_binding", lambda: SimpleNamespace(profile=tmp_path))
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {})
    monkeypatch.setattr(server, "_reliability_model_status", lambda *args: {})
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path / "output")
    monkeypatch.setattr(server, "TOKEN", HELPER_TOKEN)
    return fake, tmp_path


def post_settings(body):
    probe = Probe("/settings", body)
    probe.do_POST()
    return probe


# ---- settings ------------------------------------------------------------------

def test_defaults_are_off_and_the_token_is_write_only(settings_route):
    fake, folder = settings_route
    public = server._public_settings()
    assert (public["relay_enabled"], public["relay_url"], public["relay_poll_minutes"],
            public["relay_token_set"]) == (False, "", 5, False)
    probe = post_settings({"relay_url": "https://my-relay.onrender.com/", "relay_token": TOKEN,
                           "relay_enabled": True, "relay_poll_minutes": 15})
    assert probe.status == 200 and probe.payload["ok"] is True, probe.payload
    settings = probe.payload["settings"]
    assert (settings["relay_url"], settings["relay_enabled"], settings["relay_poll_minutes"],
            settings["relay_token_set"]) == ("https://my-relay.onrender.com", True, 15, True)
    assert "relay_token" not in settings and TOKEN not in json.dumps(probe.payload)
    stored = (folder / "settings.json").read_text(encoding="utf-8")
    assert TOKEN not in stored and "relay_token" not in json.loads(stored)
    assert fake.values == {(server._isolated_keyring_service(folder), "relay_pull_token"): TOKEN}
    assert all(service == server._isolated_keyring_service(folder) for _, service, _ in fake.calls)
    get = Probe("/settings", method="GET")
    get._handle_settings_get()
    assert get.payload["settings"]["relay_token_set"] is True
    assert TOKEN not in json.dumps(get.payload)


@pytest.mark.parametrize("clear", [None, ""])
def test_null_or_empty_token_clears_it(settings_route, clear):
    fake, _ = settings_route
    assert post_settings({"relay_token": TOKEN}).payload["settings"]["relay_token_set"] is True
    probe = post_settings({"relay_token": clear})
    assert probe.payload["ok"] is True and probe.payload["settings"]["relay_token_set"] is False
    assert fake.values == {}


def test_saving_keeps_the_token_when_it_is_left_out(settings_route):
    post_settings({"relay_token": TOKEN})
    probe = post_settings({"relay_enabled": True, "relay_url": "https://r.example"})
    assert probe.payload["settings"]["relay_token_set"] is True


@pytest.mark.parametrize("body", [
    {"relay_url": "http://my-relay.example.com"},
    {"relay_url": "http://127.0.0.2:8000"},
    {"relay_url": "ftp://my-relay.example.com"},
    {"relay_url": "https://user:pw@my-relay.example.com"},
    {"relay_url": "https://my-relay.example.com/?x=1"},
    {"relay_url": "https://my-relay.example.com/#top"},
    {"relay_url": "https://"},
    {"relay_url": "https://exa mple.com"},
    {"relay_url": "https://example.com:99999"},
    {"relay_url": 42},
    {"relay_poll_minutes": 0}, {"relay_poll_minutes": 61}, {"relay_poll_minutes": True},
    {"relay_poll_minutes": "5"}, {"relay_poll_minutes": 2.5},
    {"relay_enabled": "true"}, {"relay_enabled": 1},
    {"relay_token": 42}, {"relay_token": "too-short"}, {"relay_token": "has spaces " + "x" * 40},
    {"relay_token": "x" * 4097},
])
def test_invalid_relay_settings_are_refused_without_writes(settings_route, body):
    fake, folder = settings_route
    probe = post_settings(body)
    assert probe.status == 400 and probe.payload["ok"] is False
    assert fake.calls == [] and not (folder / "settings.json").exists()
    value = body.get("relay_token")
    if isinstance(value, str):
        assert value not in probe.payload["error"]


@pytest.mark.parametrize("raw,expected", [
    ("https://my-relay.onrender.com", "https://my-relay.onrender.com"),
    ("  https://my-relay.onrender.com///  ", "https://my-relay.onrender.com"),
    ("https://example.com/relay/", "https://example.com/relay"),
    ("http://127.0.0.1:18095", "http://127.0.0.1:18095"),
    ("http://localhost:18095/", "http://localhost:18095"),
    ("HTTP://LOCALHOST", "HTTP://LOCALHOST"),
    ("", ""), (None, ""),
])
def test_relay_url_rules_allow_http_only_for_loopback(raw, expected):
    assert server._normalize_relay_url(raw) == (expected, None)


def test_bad_values_in_the_settings_file_fall_back(settings_route):
    _, folder = settings_route
    (folder / "settings.json").write_text(json.dumps({
        "relay_url": "http://evil.example", "relay_enabled": "yes", "relay_poll_minutes": 999,
        "relay_token": TOKEN}), encoding="utf-8")
    data = server._read_settings()
    assert (data["relay_url"], data["relay_enabled"], data["relay_poll_minutes"]) == ("", False, 5)
    assert "relay_token" not in data


def test_a_credential_store_that_forgets_the_token_is_reported(settings_route, monkeypatch, caplog):
    _, folder = settings_route
    monkeypatch.setattr(server, "_keyring", NullKeyring())
    probe = post_settings({"relay_token": TOKEN, "relay_enabled": True})
    assert probe.status == 200 and probe.payload == {"ok": False, "error": "credential store unavailable"}
    assert not (folder / "settings.json").exists()
    monkeypatch.setattr(server, "_keyring", None)
    assert post_settings({"relay_token": TOKEN}).payload["error"] == "credential store unavailable"
    assert TOKEN not in caplog.text


def test_saving_relay_settings_wakes_the_poller(settings_route, relay_state):
    relay_state["next_due"] = 10 ** 12
    relay_state["last_error"] = "old"
    post_settings({"relay_poll_minutes": 2})
    assert server._relay_wake.is_set() and relay_state["next_due"] == 0.0
    assert relay_state["last_error"] is None


# ---- a fake relay ----------------------------------------------------------------

class FakeRelay:
    def __init__(self):
        self.links: list[dict] = []
        self.requests: list[tuple[str, str, str | None]] = []
        self.list_status = 200
        self.delete_status = None
        self.redirect = False
        handler = self._handler()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05},
                                       daemon=True)
        self.thread.start()

    def add(self, url, note=None, n=None):
        n = len(self.links) if n is None else n
        link = {"id": f"{1800000000000 + n:013d}-{n:012x}", "url": url, "note": note,
                "created_at": "2026-10-30T09:00:00Z"}
        self.links.append(link)
        return link["id"]

    def _handler(self):
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status, payload, headers=None):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                relay.requests.append(("GET", self.path, self.headers.get("Authorization")))
                if relay.redirect:
                    return self._reply(302, {}, {"Location": "http://127.0.0.1:1/elsewhere"})
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._reply(401, {"ok": False})
                if relay.list_status != 200:
                    return self._reply(relay.list_status, {"ok": False})
                return self._reply(200, {"ok": True, "links": list(reversed(relay.links))})

            def do_DELETE(self):
                relay.requests.append(("DELETE", self.path, self.headers.get("Authorization")))
                if relay.delete_status:
                    return self._reply(relay.delete_status, {"ok": False})
                link_id = self.path.rsplit("/", 1)[-1]
                before = len(relay.links)
                relay.links[:] = [link for link in relay.links if link["id"] != link_id]
                return self._reply(200 if len(relay.links) < before else 404, {"ok": True})

        return Handler

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Tools:
    def __init__(self):
        self.calls = []
        self.raises: set[str] = set()
        self.results: dict[str, dict] = {}

    def call_tool(self, name, args):
        self.calls.append((name, args))
        url = args.get("url") or args.get("feed_url")
        if url in self.raises:
            raise RuntimeError("tool exploded")
        return self.results.get(url, {"ok": True})


@pytest.fixture
def poll_rig(monkeypatch, relay_state):
    relay = FakeRelay()
    tools = Tools()
    settings = {"relay_enabled": True, "relay_url": relay.base, "relay_poll_minutes": 1}
    token = {"value": TOKEN}
    monkeypatch.setattr(server, "_read_settings", lambda: server._normalize_settings(dict(settings)))
    monkeypatch.setattr(server, "_get_saved_relay_token", lambda: token["value"])
    monkeypatch.setattr(server, "_mcp_tools_module", lambda: tools)
    try:
        yield SimpleNamespace(relay=relay, tools=tools, settings=settings, token=token, state=relay_state)
    finally:
        relay.close()


# ---- the poller ---------------------------------------------------------------------

def test_routes_each_link_to_the_cli_tool_oldest_first_and_deletes_it(poll_rig):
    first = poll_rig.relay.add(YOUTUBE)
    second = poll_rig.relay.add(PAGE)
    status = server._relay_poll_once()
    assert poll_rig.tools.calls == [("uoink_video", {"url": YOUTUBE}), ("uoink_page", {"url": PAGE})]
    assert poll_rig.relay.links == []
    assert poll_rig.relay.requests == [
        ("GET", "/v1/links", f"Bearer {TOKEN}"),
        ("DELETE", f"/v1/links/{first}", f"Bearer {TOKEN}"),
        ("DELETE", f"/v1/links/{second}", f"Bearer {TOKEN}")]
    assert status["picked_up_total"] == 2 and status["last_pending_count"] == 2
    assert status["last_error"] is None and status["last_ok_at"] and status["last_poll_at"]
    assert status["enabled"] is True and status["polling"] is False


def test_uses_the_shared_capture_map(poll_rig):
    assert server.CAPTURE_TOOLS["youtube_video"] == ("uoink_video", "url")
    assert server.CAPTURE_TOOLS["podcast_feed"] == ("add_podcast_feed", "feed_url")
    poll_rig.relay.add("https://example.com/feed.xml")
    server._relay_poll_once()
    assert poll_rig.tools.calls == [("add_podcast_feed", {"feed_url": "https://example.com/feed.xml"})]


def test_a_failed_capture_is_still_picked_up(poll_rig):
    poll_rig.relay.add(PAGE, note="should not be saved")
    poll_rig.tools.results[PAGE] = {"ok": False, "error": "Site not on the allowed list: example.com"}
    status = server._relay_poll_once()
    assert poll_rig.relay.links == [] and status["picked_up_total"] == 1
    assert [name for name, _ in poll_rig.tools.calls] == ["uoink_page"]
    assert "Couldn't capture a shared link" in status["last_capture_error"]


def test_a_raising_tool_keeps_the_link_once_then_drops_it(poll_rig, caplog):
    link_id = poll_rig.relay.add(YOUTUBE)
    poll_rig.tools.raises.add(YOUTUBE)
    server._relay_poll_once()
    assert [link["id"] for link in poll_rig.relay.links] == [link_id]
    assert server._relay_raises == {link_id: 1}
    server._relay_poll_once()
    assert poll_rig.relay.links == [] and server._relay_raises == {}
    assert len(poll_rig.tools.calls) == 2
    assert server._relay_state["picked_up_total"] == 0
    assert "after 2 failed attempts" in caplog.text and YOUTUBE not in caplog.text


def test_unsupported_links_are_dropped_without_a_capture(poll_rig, monkeypatch):
    poll_rig.relay.add("https://example.com/odd")
    monkeypatch.setattr(server, "_classify_capture_url", lambda url: {"ok": False, "source": "unsupported"})
    status = server._relay_poll_once()
    assert poll_rig.tools.calls == [] and poll_rig.relay.links == []
    assert status["picked_up_total"] == 0


def test_a_note_is_saved_after_a_successful_capture(poll_rig):
    poll_rig.relay.add(YOUTUBE, note="Watch the opening")
    server._relay_poll_once()
    assert poll_rig.tools.calls == [
        ("uoink_video", {"url": YOUTUBE}),
        ("uoink_note", {"title": "From my phone", "text": f"Watch the opening\n\n{YOUTUBE}"})]


def test_a_registry_rate_limit_leaves_the_link_for_the_next_check(poll_rig):
    poll_rig.relay.add(YOUTUBE)
    poll_rig.relay.add(PAGE)
    poll_rig.tools.results[YOUTUBE] = {"ok": False, "error": "rate limit exceeded: max 5/minute"}
    server._relay_poll_once()
    assert len(poll_rig.relay.links) == 2 and len(poll_rig.tools.calls) == 1
    poll_rig.tools.results.clear()
    server._relay_poll_once()
    assert poll_rig.relay.links == []


def test_a_failed_delete_is_retried_without_capturing_twice(poll_rig):
    link_id = poll_rig.relay.add(YOUTUBE)
    poll_rig.relay.delete_status = 500
    server._relay_poll_once()
    assert link_id in server._relay_done and len(poll_rig.relay.links) == 1
    poll_rig.relay.delete_status = None
    server._relay_poll_once()
    assert poll_rig.relay.links == [] and server._relay_done == {}
    assert len(poll_rig.tools.calls) == 1


def test_off_or_unconfigured_contacts_nothing(poll_rig):
    poll_rig.relay.add(YOUTUBE)
    for change in ({"relay_enabled": False}, {"relay_url": ""}):
        saved = dict(poll_rig.settings)
        poll_rig.settings.update(change)
        server._relay_poll_once()
        poll_rig.settings.clear()
        poll_rig.settings.update(saved)
    poll_rig.token["value"] = ""
    server._relay_poll_once()
    assert poll_rig.relay.requests == [] and poll_rig.tools.calls == []


@pytest.mark.parametrize("setup,expected", [
    (lambda rig: rig.token.update(value="wrong-token-" + "w" * 30), "didn't accept the pull token"),
    (lambda rig: setattr(rig.relay, "list_status", 403), "push token"),
    (lambda rig: setattr(rig.relay, "list_status", 404), "no relay at this address"),
    (lambda rig: setattr(rig.relay, "list_status", 503), "storage isn't answering"),
    (lambda rig: setattr(rig.relay, "redirect", True), "redirects"),
])
def test_relay_errors_are_plain_and_never_hold_the_token(poll_rig, setup, expected, caplog):
    setup(poll_rig)
    status = server._relay_poll_once()
    assert expected in status["last_error"]
    assert TOKEN not in json.dumps(status) and TOKEN not in caplog.text
    assert poll_rig.tools.calls == []
    # A redirect is never followed with the token.
    assert all(path != "/elsewhere" for _, path, _ in poll_rig.relay.requests)


def test_an_unreachable_relay_is_reported(poll_rig):
    poll_rig.relay.close()
    status = server._relay_poll_once()
    assert status["last_error"] == "Couldn't reach the relay. Check the address and your connection."
    assert status["last_ok_at"] is None and status["polling"] is False


def test_the_real_relay_app_round_trip(poll_rig, monkeypatch):
    """The poller against relay/app.py itself, not only the fake."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "uoink_relay_app_for_inbox", Path(__file__).resolve().parents[1] / "relay" / "app.py")
    app = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, app)  # dataclasses resolve annotations here
    spec.loader.exec_module(app)
    push = "push-token-for-desktop-tests-" + "p" * 20
    config = app.Config(push_token=push, pull_token=TOKEN, store=app.MemoryStore())
    httpd = app.make_server(config, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        httpd.inbox.add(YOUTUBE, "From the bus")
        poll_rig.settings["relay_url"] = f"http://127.0.0.1:{httpd.server_address[1]}/"
        status = server._relay_poll_once()
        assert status["picked_up_total"] == 1 and httpd.inbox.list() == []
        assert poll_rig.tools.calls[-1] == ("uoink_note", {"title": "From my phone",
                                                          "text": f"From the bus\n\n{YOUTUBE}"})
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---- the thread, status and check routes ---------------------------------------------

def test_status_and_check_routes_are_token_gated(settings_route):
    for method, path in (("GET", "/relay/status"), ("POST", "/relay/check")):
        probe = Probe(path, method=method, headers={"X-Uoink-Token": "wrong"})
        getattr(probe, f"do_{method}")()
        assert probe.status == 403


def test_status_route_reports_without_the_token(settings_route):
    post_settings({"relay_token": TOKEN, "relay_url": "https://r.example", "relay_enabled": True})
    probe = Probe("/relay/status", method="GET")
    probe.do_GET()
    assert probe.status == 200
    assert set(probe.payload) == {"ok", "enabled", "configured", "last_poll_at", "last_ok_at",
                                  "last_error", "last_capture_error", "picked_up_total",
                                  "last_pending_count", "polling"}
    assert probe.payload["enabled"] is True and probe.payload["configured"] is True
    assert TOKEN not in json.dumps(probe.payload)


def test_check_when_off_returns_at_once(settings_route):
    probe = Probe("/relay/check")
    probe.do_POST()
    assert probe.status == 200 and probe.payload["enabled"] is False
    assert not server._relay_wake.is_set()


def test_check_now_wakes_the_thread_and_it_stops_promptly(poll_rig, monkeypatch):
    poll_rig.relay.add(PAGE)
    poll_rig.state["next_due"] = 10 ** 12   # not due: only the wake can poll
    thread = server._start_relay_inbox_thread()
    try:
        assert thread.name == "relay-inbox" and thread.daemon
        status = server._relay_request_check(wait=5)
        assert status["picked_up_total"] == 1 and poll_rig.relay.links == []
    finally:
        server._stop_relay_inbox_thread()
        thread.join(5)
    assert not thread.is_alive()


def test_tick_respects_the_interval(poll_rig):
    server._relay_tick()
    assert len(poll_rig.relay.requests) == 1
    server._relay_tick()
    assert len(poll_rig.relay.requests) == 1   # not due for another minute
    server._relay_tick(force=True)
    assert len(poll_rig.relay.requests) == 2


def test_poll_logs_hold_no_token_url_or_note(poll_rig, caplog):
    caplog.set_level(logging.INFO, logger="uoink")
    poll_rig.relay.add(YOUTUBE, note="private words")
    poll_rig.relay.add(PAGE)
    poll_rig.tools.raises.add(PAGE)
    server._relay_poll_once()
    poll_rig.token["value"] = "wrong-token-" + "w" * 30
    server._relay_poll_once()
    for secret in (TOKEN, "wrong-token-", YOUTUBE, "jNQXAC9IVRw", PAGE, "private words", poll_rig.relay.base):
        assert secret not in caplog.text
    assert "relay: checked 2 link(s)" in caplog.text

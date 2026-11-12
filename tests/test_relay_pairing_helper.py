"""Helper side of the phone QR: POST /relay/pairing asks the saved relay for
its push token with the saved pull token. The dashboard never sees the pull
token. Uses the real relay/app.py on loopback where it can."""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest

import server
from tests.test_relay_inbox import (  # noqa: F401  (fixtures)
    TOKEN, Probe, poll_rig, relay_state, settings_route)

PUSH = "push-token-for-desktop-tests-" + "p" * 20


@pytest.fixture
def real_relay(monkeypatch, poll_rig):
    spec = importlib.util.spec_from_file_location(
        "uoink_relay_app_for_pairing", Path(__file__).resolve().parents[1] / "relay" / "app.py")
    app = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, app)
    spec.loader.exec_module(app)
    config = app.Config(push_token=PUSH, pull_token=TOKEN, store=app.MemoryStore())
    httpd = app.make_server(config, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    poll_rig.settings["relay_url"] = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield poll_rig
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_pairing_returns_the_push_token_from_a_current_relay(real_relay):
    assert server._relay_pairing() == {"ok": True, "state": "paired", "push_token": PUSH}


def test_a_wrong_pull_token_is_reported_without_a_push_token(real_relay):
    real_relay.token["value"] = "wrong-token-" + "w" * 30
    result = server._relay_pairing()
    assert result["state"] == "error" and "didn't accept the pull token" in result["message"]
    assert PUSH not in json.dumps(result)


def test_the_push_token_cannot_be_used_as_the_pull_token(real_relay):
    real_relay.token["value"] = PUSH
    result = server._relay_pairing()
    assert result["state"] == "error" and "push token" in result["message"]


def test_a_relay_from_before_this_feature_is_detected_as_old(poll_rig):
    # The fake relay lists links but has no /v1/pairing: simulate its 404.
    real = server._relay_http

    def http(method, url, token, timeout=90):
        if url.endswith("/v1/pairing"):
            return 404, {"ok": False, "error": "not found"}
        return real(method, url, token, timeout)
    server._relay_http, saved = http, server._relay_http
    try:
        result = server._relay_pairing()
    finally:
        server._relay_http = saved
    assert result["state"] == "old_relay" and "Manual Deploy" in result["message"]


def test_a_wrong_address_is_not_mistaken_for_an_old_relay(poll_rig):
    poll_rig.relay.list_status = 404
    real = server._relay_http
    server._relay_http = lambda m, u, t, timeout=90: (404, {}) if u.endswith("/v1/pairing") else real(m, u, t, timeout)
    try:
        result = server._relay_pairing()
    finally:
        server._relay_http = real
    assert result["state"] == "error" and "no relay at this address" in result["message"]


def test_unreachable_relay_is_plain(poll_rig):
    poll_rig.relay.close()
    result = server._relay_pairing()
    assert result["state"] == "error" and result["message"].startswith("Couldn't reach the relay")


def test_not_configured_contacts_nothing(poll_rig):
    poll_rig.token["value"] = ""
    assert server._relay_pairing()["state"] == "not_configured"
    assert poll_rig.relay.requests == []


def test_pairing_route_is_token_gated_and_returns_the_push_token(settings_route, real_relay):
    bad = Probe("/relay/pairing", headers={"X-Uoink-Token": "wrong"})
    bad.do_POST()
    assert bad.status == 403
    good = Probe("/relay/pairing")
    good.do_POST()
    assert good.status == 200 and good.payload["push_token"] == PUSH
    assert TOKEN not in json.dumps(good.payload)


def test_status_remembers_when_the_last_link_was_picked_up(poll_rig):
    from tests.test_relay_inbox import PAGE
    assert server._relay_status_payload(poll_rig.settings)["last_pickup_at"] is None
    poll_rig.relay.add(PAGE)
    status = server._relay_poll_once()
    assert status["picked_up_total"] == 1
    assert status["last_pickup_at"] and status["last_pickup_at"].endswith("Z")

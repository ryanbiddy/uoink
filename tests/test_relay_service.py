"""Uoink Relay service (relay/app.py): the real HTTP server on an ephemeral
loopback port with MemoryStore, plus KeyValueStore against a fake client.

Standard library only; redis-py is never imported.
"""
from __future__ import annotations

import http.client
import importlib.util
import json
import re
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUSH = "push-token-for-tests-" + "p" * 24
PULL = "pull-token-for-tests-" + "q" * 24
START = 1_800_000_000.0


def _load_app():
    spec = importlib.util.spec_from_file_location("uoink_relay_app", ROOT / "relay" / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


app = _load_app()


class Clock:
    def __init__(self, value=START):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class Relay:
    def __init__(self, server, clock):
        self.server, self.clock = server, clock
        self.port = server.server_address[1]

    def request(self, method, path, body=None, *, token=None, content_type=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        sent = dict(headers or {})
        if token is not None:
            sent["Authorization"] = f"Bearer {token}"
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
            content_type = content_type or "application/json"
        elif isinstance(body, str):
            body = body.encode("utf-8")
        if content_type:
            sent["Content-Type"] = content_type
        try:
            conn.request(method, path, body=body, headers=sent)
            response = conn.getresponse()
            raw = response.read()
            headers_out = {k.lower(): v for k, v in response.getheaders()}
            status = response.status
        finally:
            conn.close()
        payload = None
        if headers_out.get("content-type", "").startswith("application/json"):
            payload = json.loads(raw.decode("utf-8"))
        return status, payload, headers_out, raw

    def push(self, url="https://www.youtube.com/watch?v=jNQXAC9IVRw", note=None, **kw):
        body = {"url": url} if note is None else {"url": url, "note": note}
        return self.request("POST", "/v1/links", body, token=kw.pop("token", PUSH), **kw)

    def pull(self, **kw):
        return self.request("GET", "/v1/links", token=kw.pop("token", PULL), **kw)


@pytest.fixture
def relay():
    clock = Clock()
    config = app.Config(push_token=PUSH, pull_token=PULL, store=app.MemoryStore(clock), clock=clock)
    server = app.make_server(config, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield Relay(server, clock)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


# ---- auth ---------------------------------------------------------------

@pytest.mark.parametrize("method,path,token,status", [
    ("GET", "/v1/links", None, 401), ("GET", "/v1/links", "wrong-" + "x" * 40, 401),
    ("POST", "/v1/links", None, 401), ("POST", "/v1/links", "wrong-" + "x" * 40, 401),
    ("DELETE", "/v1/links/0000000000000-000000000000", None, 401),
    ("GET", "/v1/links", PUSH, 403),
    ("DELETE", "/v1/links/0000000000000-000000000000", PUSH, 403),
    ("POST", "/v1/links", PULL, 403),
])
def test_tokens_are_required_and_their_roles_never_cross(relay, method, path, token, status):
    body = {"url": "https://example.com/a"} if method == "POST" else None
    got, payload, headers, _ = relay.request(method, path, body, token=token)
    assert got == status and payload["ok"] is False
    if status == 401:
        assert headers["www-authenticate"] == "Bearer"
    # Nothing was added by a rejected push.
    assert relay.pull()[1]["links"] == []


def test_bearer_scheme_is_required(relay):
    status, *_ = relay.request("GET", "/v1/links", headers={"Authorization": PULL})
    assert status == 401
    status, *_ = relay.request("GET", "/v1/links", headers={"Authorization": f"bearer {PULL}"})
    assert status == 200


# ---- body formats and shared text ------------------------------------------

def test_json_push_lists_and_deletes(relay):
    status, payload, headers, _ = relay.push(note="Watch the opening")
    assert status == 201 and payload["ok"] is True
    assert re.fullmatch(r"\d{13}-[0-9a-f]{12}", payload["id"])
    assert payload["expires_at"] == app._iso(START + 604800)
    status, listed, *_ = relay.pull()
    assert status == 200
    assert listed == {"ok": True, "links": [{
        "id": payload["id"], "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "note": "Watch the opening", "created_at": app._iso(START)}]}
    status, deleted, *_ = relay.request("DELETE", f"/v1/links/{payload['id']}", token=PULL)
    assert status == 200 and deleted == {"ok": True}
    assert relay.request("DELETE", f"/v1/links/{payload['id']}", token=PULL)[0] == 404
    assert relay.pull()[1]["links"] == []


@pytest.mark.parametrize("body,content_type,url,note", [
    ("url=https%3A%2F%2Fexample.com%2Fa&title=A+page", "application/x-www-form-urlencoded",
     "https://example.com/a", "A page"),
    ("text=Read+this+https%3A%2F%2Fexample.com%2Fb", "application/x-www-form-urlencoded",
     "https://example.com/b", "Read this"),
    ("title=Only+a+title&text=https%3A%2F%2Fexample.com%2Fc", "application/x-www-form-urlencoded",
     "https://example.com/c", "Only a title"),
    ("A good video https://youtu.be/jNQXAC9IVRw", "text/plain; charset=utf-8",
     "https://youtu.be/jNQXAC9IVRw", "A good video"),
    ("https://example.com/plain", "text/plain", "https://example.com/plain", None),
    ("Look (https://en.wikipedia.org/wiki/Foo_(bar)). Then https://example.com/second",
     "text/plain", "https://en.wikipedia.org/wiki/Foo_(bar)", "Look ( ). Then https://example.com/second"),
    ("Title - https://example.com/d.", "text/plain", "https://example.com/d", "Title"),
])
def test_form_and_text_bodies_take_the_first_link(relay, body, content_type, url, note):
    status, payload, *_ = relay.request("POST", "/v1/links", body, token=PUSH, content_type=content_type)
    assert status == 201, payload
    assert relay.pull()[1]["links"][0]["url"] == url
    assert relay.pull()[1]["links"][0]["note"] == note


def test_json_url_field_can_hold_shared_text_and_a_typed_note_wins(relay):
    status, *_ = relay.push("Title https://example.com/x")
    assert status == 201
    relay.clock.advance(1)
    status, *_ = relay.push("Title https://example.com/y", note="Mine")
    assert status == 201
    links = relay.pull()[1]["links"]
    assert [(l["url"], l["note"]) for l in links] == [
        ("https://example.com/x", "Title"), ("https://example.com/y", "Mine")]


def test_extract_url_skips_an_invalid_candidate():
    url, remaining, reason = app.extract_url("bad https://user:pw@example.com/ then https://ok.example/p")
    assert url == "https://ok.example/p" and reason is None and "then" in remaining
    assert app.extract_url("nothing here")[0] is None


# ---- validation -------------------------------------------------------------

@pytest.mark.parametrize("body,content_type,message", [
    ({"url": "ftp://example.com/file"}, None, "no http(s) link found"),
    ({"url": "https://"}, None, "no http(s) link found"),
    ({"url": "https://user:pw@example.com/"}, None, "username or password"),
    ({"url": "https://example.com/" + "a" * 2048}, None, "longer than 2048"),
    ({"url": "https://example.com/", "note": "n" * 501}, None, "longer than 500"),
    ({"url": 42}, None, "url must be a string"),
    ({"url": "https://example.com/", "note": 7}, None, "note must be a string"),
    ({}, None, "no http(s) link found"),
    ([1, 2], None, "JSON body must be an object"),
    ("{not json", "application/json", "not valid JSON"),
])
def test_invalid_shares_are_refused(relay, body, content_type, message):
    status, payload, *_ = relay.request("POST", "/v1/links", body, token=PUSH, content_type=content_type)
    assert status == 400 and message in payload["error"]
    assert relay.pull()[1]["links"] == []


def test_url_rules_and_note_cleaning():
    assert app.validate_url("http://example.com:8080/x?y=1#z") == "http://example.com:8080/x?y=1#z"
    for bad in ("https://example.com:99999/", "https://exa mple.com/", "javascript:alert(1)", "https:///x"):
        with pytest.raises(app.ShareError):
            app.validate_url(bad)
    assert app.clean_note("a\x00b‮\tc\r\nd", derived=False) == "ab c d"
    long = app.clean_note("x" * 900, derived=True)
    assert len(long) == 500 and long.endswith("…")
    assert app.clean_note("   ", derived=False) is None


def test_body_size_content_type_and_length_limits(relay):
    big = json.dumps({"url": "https://example.com/", "note": "x" * (16 * 1024)})
    status, payload, *_ = relay.request("POST", "/v1/links", big, token=PUSH, content_type="application/json")
    assert status == 413
    status, *_ = relay.request("POST", "/v1/links", b"<x/>", token=PUSH, content_type="application/xml")
    assert status == 415
    conn = http.client.HTTPConnection("127.0.0.1", relay.port, timeout=10)
    conn.putrequest("POST", "/v1/links")
    conn.putheader("Authorization", f"Bearer {PUSH}")
    conn.putheader("Content-Type", "application/json")
    conn.endheaders()
    assert conn.getresponse().status == 411
    conn.close()


# ---- dedupe, cap, delete ------------------------------------------------------

def test_pending_url_is_idempotent_and_delete_removes_the_dedupe_key(relay):
    first = relay.push("https://example.com/same")[1]["id"]
    status, again, *_ = relay.push("https://example.com/same", note="later")
    assert status == 200 and again["id"] == first and again["duplicate"] is True
    assert len(relay.pull()[1]["links"]) == 1
    keys = relay.server.inbox.store.keys(app.KEY_PREFIX)
    assert sorted(k.split(":")[1] for k in keys) == ["link", "url"]
    assert relay.request("DELETE", f"/v1/links/{first}", token=PULL)[0] == 200
    assert relay.server.inbox.store.keys(app.KEY_PREFIX) == []
    status, fresh, *_ = relay.push("https://example.com/same")
    assert status == 201 and fresh["id"] != first


def test_links_list_oldest_first_and_at_most_100(relay):
    for n in range(105):
        relay.clock.advance(1)
        relay.server.inbox.add(f"https://example.com/{n}", None)
    links = relay.pull()[1]["links"]
    assert len(links) == 100
    assert [l["url"] for l in links[:3]] == ["https://example.com/0", "https://example.com/1", "https://example.com/2"]
    assert [l["id"] for l in links] == sorted(l["id"] for l in links)


def test_inbox_full_answers_429(relay):
    relay.server.inbox._max_pending = 2
    assert relay.push("https://example.com/1")[0] == 201
    assert relay.push("https://example.com/2")[0] == 201
    status, payload, *_ = relay.push("https://example.com/3")
    assert status == 429 and payload["error"] == "inbox full"
    # A pending duplicate is still answered while full.
    assert relay.push("https://example.com/1")[0] == 200


@pytest.mark.parametrize("link_id", ["nope", "0000000000000-zzzzzzzzzzzz", "../x", "0000000000000-000000000000"])
def test_delete_unknown_or_malformed_id_is_404(relay, link_id):
    assert relay.request("DELETE", f"/v1/links/{link_id}", token=PULL)[0] == 404


# ---- expiry -------------------------------------------------------------------

def test_links_and_dedupe_keys_expire_after_seven_days(relay):
    first = relay.push("https://example.com/old")[1]["id"]
    relay.clock.advance(604800 - 1)
    assert len(relay.pull()[1]["links"]) == 1
    relay.clock.advance(1)
    assert relay.pull()[1]["links"] == []
    assert relay.server.inbox.store.keys(app.KEY_PREFIX) == []
    status, payload, *_ = relay.push("https://example.com/old")
    assert status == 201 and payload["id"] != first


# ---- health, page, headers -------------------------------------------------------

def test_healthz_reports_the_store_and_nothing_else(relay):
    relay.push()
    status, payload, headers, _ = relay.request("GET", "/healthz")
    assert status == 200 and payload == {"ok": True, "store": "memory"}

    def broken():
        raise ConnectionError("down")
    relay.server.inbox.store.ping = broken
    status, payload, *_ = relay.request("GET", "/healthz")
    assert status == 503 and payload == {"ok": False, "store": "memory"}


def test_security_headers_and_the_landing_page(relay):
    for path in ("/healthz", "/v1/links", "/nope"):
        _, _, headers, _ = relay.request("GET", path, token=PULL)
        assert headers["cache-control"] == "no-store"
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["content-security-policy"].startswith("default-src 'none'")
        assert headers["server"] == "uoink-relay"
    relay.push(note="private note")
    status, _, headers, raw = relay.request("GET", "/")
    page = raw.decode("utf-8")
    assert status == 200 and headers["content-type"].startswith("text/html")
    assert app.DOCS_URL in page and "jNQXAC9IVRw" not in page and "private note" not in page
    csp = headers["content-security-policy"]
    assert "default-src 'none'" in csp and "'unsafe-inline'" not in csp and "style-src 'sha256-" in csp
    assert headers["cache-control"] == "no-store"


def test_unknown_routes_and_methods(relay):
    assert relay.request("GET", "/v1/other", token=PULL)[0] == 404
    assert relay.request("POST", "/v1/other", {"url": "https://example.com"}, token=PUSH)[0] == 404
    assert relay.request("PUT", "/v1/links", {"url": "https://example.com"}, token=PUSH)[0] == 405
    assert relay.request("GET", "/v1/links/0000000000000-000000000000", token=PULL)[0] == 405


# ---- abuse limits -----------------------------------------------------------------

def test_failed_auth_limit_per_client_ip(relay):
    attacker = {"X-Forwarded-For": "203.0.113.9, 10.0.0.1"}
    for _ in range(30):
        assert relay.request("GET", "/v1/links", token="w" * 40, headers=attacker)[0] == 401
    status, payload, headers, _ = relay.request("GET", "/v1/links", token="w" * 40, headers=attacker)
    assert status == 429 and headers["retry-after"] == "600"
    # The limited address is blocked even with the right token...
    assert relay.request("GET", "/v1/links", token=PULL, headers=attacker)[0] == 429
    # ...another address is not, and the window passes.
    assert relay.request("GET", "/v1/links", token=PULL, headers={"X-Forwarded-For": "198.51.100.4"})[0] == 200
    relay.clock.advance(600)
    assert relay.request("GET", "/v1/links", token=PULL, headers=attacker)[0] == 200


def test_push_rate_limit_is_sixty_a_minute(relay):
    for n in range(60):
        assert relay.push(f"https://example.com/{n}")[0] == 201
    status, payload, headers, _ = relay.push("https://example.com/61")
    assert status == 429 and headers["retry-after"] == "60"
    relay.clock.advance(60)
    assert relay.push("https://example.com/62")[0] == 201


def test_sliding_window_memory_is_bounded():
    window = app.SlidingWindow(3, 60, Clock(), max_keys=5)
    for n in range(50):
        window.hit(f"10.0.0.{n}")
    assert len(window._events) == 5


# ---- logging ---------------------------------------------------------------------

def test_logs_hold_no_tokens_urls_notes_or_ips(relay, caplog):
    caplog.set_level("INFO", logger="uoink-relay")
    secret_url = "https://example.com/secret-path-123"
    note = "a very private note"
    ip = "192.0.2.77"
    relay.push(secret_url, note=note, headers={"X-Forwarded-For": ip})
    link_id = relay.pull(headers={"X-Forwarded-For": ip})[1]["links"][0]["id"]
    relay.request("GET", "/v1/links", token="bad-" + "z" * 40, headers={"X-Forwarded-For": ip})
    relay.request("DELETE", f"/v1/links/{link_id}", token=PULL, headers={"X-Forwarded-For": ip})
    relay.request("POST", "/v1/links", "no link here " + note, token=PUSH, content_type="text/plain")
    relay.request("GET", "/healthz")
    text = caplog.text
    for secret in (PUSH, PULL, "bad-" + "z" * 40, secret_url, "secret-path", note, ip, link_id, "127.0.0.1"):
        assert secret not in text
    lines = [r.getMessage() for r in caplog.records if r.name == "uoink-relay"]
    assert len(lines) >= 6
    for line in lines:
        assert re.fullmatch(r"(GET|POST|DELETE|OTHER) (/|/healthz|/v1/links|/v1/links/\{id\}|other) \d{3} \d+ms", line), line
    assert "DELETE /v1/links/{id} 200" in text


# ---- startup refusal -------------------------------------------------------------

GOOD = {"RELAY_PUSH_TOKEN": PUSH, "RELAY_PULL_TOKEN": PULL, "RELAY_DEV_MEMORY": "1"}


@pytest.mark.parametrize("change,message", [
    ({"RELAY_PUSH_TOKEN": None}, "RELAY_PUSH_TOKEN is not set"),
    ({"RELAY_PULL_TOKEN": ""}, "RELAY_PULL_TOKEN is not set"),
    ({"RELAY_PUSH_TOKEN": "short"}, "shorter than 32"),
    ({"RELAY_PULL_TOKEN": "p" * 31}, "shorter than 32"),
    ({"RELAY_PULL_TOKEN": PUSH}, "must be different"),
    ({"RELAY_PUSH_TOKEN": "has space " + "x" * 40}, "spaces"),
    ({"RELAY_DEV_MEMORY": None}, "No store configured"),
    ({"RELAY_DEV_MEMORY": "true"}, "No store configured"),
    ({"PORT": "http"}, "PORT must be a number"),
])
def test_refuses_to_start_with_bad_configuration(change, message, capsys):
    env = {**GOOD, **change}
    env = {k: v for k, v in env.items() if v is not None}
    with pytest.raises(app.ConfigError, match=re.escape(message)):
        app.load_config(env)
    assert app.main(env) == 2
    err = capsys.readouterr().err
    assert "will not start" in err and message in err
    assert PUSH not in err and PULL not in err


def test_good_configuration_and_store_choice():
    config = app.load_config({**GOOD, "PORT": "18095"})
    assert config.port == 18095 and isinstance(config.store, app.MemoryStore)
    assert app.load_config(GOOD).port == 10000
    seen = []
    fake_store = object()
    config = app.load_config({**GOOD, "RELAY_KEYVALUE_URL": "redis://red-x:6379"},
                             keyvalue_factory=lambda url: seen.append(url) or fake_store)
    assert config.store is fake_store and seen == ["redis://red-x:6379"]


# ---- KeyValueStore with a fake redis client -------------------------------------

class FakeRedis:
    """Implements only what KeyValueStore may call, returning bytes like a
    client without decode_responses would."""

    def __init__(self, clock):
        self.clock, self.data, self.calls = clock, {}, []

    def _alive(self, key):
        item = self.data.get(key)
        if item and item[1] is not None and item[1] <= self.clock():
            del self.data[key]
            return None
        return item

    def ping(self):
        self.calls.append(("ping",))
        return True

    def set(self, key, value, ex=None):
        self.calls.append(("set", key, ex))
        self.data[key] = (value.encode("utf-8"), self.clock() + ex if ex else None)
        return True

    def get(self, key):
        self.calls.append(("get", key))
        item = self._alive(key)
        return item[0] if item else None

    def delete(self, *keys):
        self.calls.append(("delete", *keys))
        return sum(1 for key in keys if self._alive(key) and self.data.pop(key))

    def scan_iter(self, match=None, count=None):
        self.calls.append(("scan_iter", match, count))
        prefix = match[:-1]
        assert match.endswith("*") and "*" not in prefix and "?" not in prefix and "[" not in prefix
        for key in list(self.data):
            if key.startswith(prefix) and self._alive(key):
                yield key.encode("utf-8")


def test_keyvalue_store_drives_the_inbox_with_native_ttl():
    clock = Clock()
    client = FakeRedis(clock)
    store = app.KeyValueStore(client)
    inbox = app.Inbox(store, clock=clock)
    assert store.ping() is True and store.kind == "keyvalue"
    link, created = inbox.add("https://example.com/kv", "note")
    assert created
    sets = [c for c in client.calls if c[0] == "set"]
    assert [c[2] for c in sets] == [604800, 604800]
    assert {c[1].rsplit(":", 1)[0] for c in sets} == {"uoink-relay:link", "uoink-relay:url"}
    again, created = inbox.add("https://example.com/kv", None)
    assert not created and again["id"] == link["id"]
    assert inbox.list() == [{"id": link["id"], "url": "https://example.com/kv", "note": "note",
                             "created_at": app._iso(START)}]
    assert ("scan_iter", "uoink-relay:link:*", 500) in client.calls
    assert inbox.delete(link["id"]) is True
    deletes = [c for c in client.calls if c[0] == "delete"]
    assert len(deletes) == 1 and len(deletes[0]) == 3  # link key and url key together
    assert client.data == {}
    assert inbox.delete(link["id"]) is False
    inbox.add("https://example.com/kv2", None)
    clock.advance(604800)
    assert inbox.list() == []


def test_keyvalue_store_tolerates_missing_and_corrupt_records():
    clock = Clock()
    client = FakeRedis(clock)
    inbox = app.Inbox(app.KeyValueStore(client), clock=clock)
    link, _ = inbox.add("https://example.com/a", None)
    client.data[app.LINK_PREFIX + "1234567890123-abcdefabcdef"] = (b"{not json", None)
    client.data[app.LINK_PREFIX + "not-an-id"] = (b"{}", None)
    assert [l["id"] for l in inbox.list()] == [link["id"]]
    # A dedupe key whose link vanished does not block a new push.
    del client.data[app.LINK_PREFIX + link["id"]]
    again, created = inbox.add("https://example.com/a", None)
    assert created and again["id"] != link["id"]


# ---- deploy files -------------------------------------------------------------------

def test_requirements_pin_one_exact_hashed_redis():
    text = (ROOT / "relay" / "requirements.txt").read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    assert re.fullmatch(r"redis==\d+\.\d+\.\d+ \\", lines[0])
    assert all(re.fullmatch(r"--hash=sha256:[0-9a-f]{64}( \\)?", line) for line in lines[1:])
    assert len(lines) >= 2


def test_render_blueprint_matches_the_documented_shape():
    yaml = pytest.importorskip("yaml")
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    web, kv = blueprint["services"]
    assert {k: web[k] for k in ("type", "name", "runtime", "plan", "rootDir", "buildCommand",
                                "startCommand", "healthCheckPath", "autoDeployTrigger")} == {
        "type": "web", "name": "uoink-relay", "runtime": "python", "plan": "free", "rootDir": "relay",
        "buildCommand": "pip install -r requirements.txt", "startCommand": "python app.py",
        "healthCheckPath": "/healthz", "autoDeployTrigger": "off"}
    env = {item["key"]: item for item in web["envVars"]}
    assert env["PYTHON_VERSION"]["value"] == "3.14.8"
    assert env["RELAY_PUSH_TOKEN"] == {"key": "RELAY_PUSH_TOKEN", "generateValue": True}
    assert env["RELAY_PULL_TOKEN"] == {"key": "RELAY_PULL_TOKEN", "generateValue": True}
    assert env["RELAY_KEYVALUE_URL"]["fromService"] == {
        "type": "keyvalue", "name": "uoink-relay-kv", "property": "connectionString"}
    assert kv == {"type": "keyvalue", "name": "uoink-relay-kv", "plan": "free",
                  "ipAllowList": [], "maxmemoryPolicy": "noeviction"}
    assert set(env) == {"PYTHON_VERSION", "RELAY_PUSH_TOKEN", "RELAY_PULL_TOKEN", "RELAY_KEYVALUE_URL"}

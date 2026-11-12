"""The credential store can't freeze the helper, and test profiles never touch it.

1. A keyring call that hangs (a Keychain prompt, a locked store, a slow Windows
   Credential Manager) is given up on after CREDENTIAL_STORE_TIMEOUT_SEC.
   /health and GET /settings keep answering, the save says so plainly, and
   nothing is marked saved or switched on.
2. Calls run in request order, so a call that finishes late never lands on top
   of a newer value, and a caller that gave up never has its call run later.
3. An isolated profile (or UOINK_CREDENTIAL_STORE=file) keeps its secrets in
   its own credentials.json and never imports or calls keyring.

Fake keyrings only: no real credential store, OS prompt or outside network.
"""
from __future__ import annotations

import http.client
import io
import json
import os
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

import migrate_install
import server
import uoink_install_isolation as iso

HELPER_TOKEN = "fixture-helper-token"
TOKEN_A = "pull-token-a-" + "a" * 32
TOKEN_B = "pull-token-b-" + "b" * 32
TOKEN_C = "pull-token-c-" + "c" * 32
TOKEN_D = "pull-token-d-" + "d" * 32
API_KEY = "sk-ant-synthetic-fixture-" + "k" * 20
SC_KEY = "synthetic-sc-key-never-a-real-credential"
RELAY = "https://relay.example.com"
TIMEOUT = 1.0
DIDNT_ANSWER = {"ok": False, "code": "credential_store_unavailable",
                "error": ("The system credential store didn't answer. "
                          "Unlock it or allow access, then select Save again.")}
DIDNT_SAVE = {"ok": False, "code": "credential_store_unavailable",
              "error": ("The system credential store didn't save this. "
                        "Unlock it or allow access, then select Save again.")}


class FakeKeyring:
    """In-memory keyring. set_password for a held value waits on its gate,
    like a call stuck behind a Keychain prompt."""

    def __init__(self):
        self.values: dict[tuple[str, str], str] = {}
        self.calls: list[tuple] = []
        self.gates: dict[str, threading.Event] = {}
        self.entered: dict[str, threading.Event] = {}
        self.fail_with: Exception | None = None

    def hold(self, value: str) -> threading.Event:
        self.gates[value] = threading.Event()
        self.entered[value] = threading.Event()
        return self.gates[value]

    def get_password(self, service, username):
        self.calls.append(("get", username))
        return self.values.get((service, username))

    def set_password(self, service, username, value):
        self.calls.append(("set", username, value))
        if self.fail_with is not None:
            raise self.fail_with
        if value in self.gates:
            self.entered[value].set()
            self.gates[value].wait(30)
        self.values[(service, username)] = value

    def delete_password(self, service, username):
        self.calls.append(("delete", username))
        self.values.pop((service, username), None)

    def sets(self) -> list[str]:
        return [call[2] for call in self.calls if call[0] == "set"]


class Probe(server.Handler):
    def __init__(self, path, body=None, *, method="POST"):
        self.command = method
        self.path = path
        self.client_address = ("127.0.0.1", 1)
        raw = json.dumps(body if body is not None else {}).encode()
        self.rfile = io.BytesIO(raw)
        self.headers = {"Host": f"127.0.0.1:{server.PORT}", "X-Uoink-Token": HELPER_TOKEN,
                        "Content-Type": "application/json", "Content-Length": str(len(raw))}
        self.status = self.payload = None

    def _send_json(self, status, payload):
        self.status, self.payload = status, payload


def post_settings(body):
    probe = Probe("/settings", body)
    probe.do_POST()
    return probe


def in_thread(fn, *args):
    box: dict = {}

    def run():
        started = time.monotonic()
        try:
            box["value"] = fn(*args)
        except BaseException as e:
            box["error"] = e
        box["seconds"] = time.monotonic() - started

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, box


def wait_idle(turns, seconds=5.0):
    deadline = time.monotonic() + seconds
    while turns.busy_for() and time.monotonic() < deadline:
        time.sleep(0.01)


def settings_view_patches(monkeypatch, folder):
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {})
    monkeypatch.setattr(server, "_reliability_model_status", lambda *args: {})
    monkeypatch.setattr(server, "DESKTOP_ROOT", folder / "output")
    monkeypatch.setattr(server, "TOKEN", HELPER_TOKEN)
    monkeypatch.setattr(server, "_relay_settings_changed", lambda: None)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """The OS credential store path, through a fake keyring, with settings in
    tmp_path. (An isolated profile uses its own file by default.)"""
    fake = FakeKeyring()
    monkeypatch.setattr(server, "_keyring", fake)
    monkeypatch.setattr(server, "_isolated_binding", lambda: SimpleNamespace(profile=tmp_path))
    monkeypatch.setattr(server, "_credential_store_mode", lambda: "keyring")
    monkeypatch.setattr(server, "CREDENTIAL_STORE_TIMEOUT_SEC", TIMEOUT)
    monkeypatch.setattr(server, "_credential_turns", server._CredentialTurns())
    monkeypatch.setattr(server, "_credential_last_seen", {})
    settings_view_patches(monkeypatch, tmp_path)
    turns = server._credential_turns
    yield SimpleNamespace(fake=fake, folder=tmp_path,
                          service=server._isolated_keyring_service(tmp_path))
    for gate in fake.gates.values():
        gate.set()
    wait_idle(turns)


# ---- a stuck store never freezes the helper ---------------------------------

def _request(port, method, path, body=None, timeout=10.0):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    headers = {"Host": f"127.0.0.1:{port}", "X-Uoink-Token": HELPER_TOKEN}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers.update({"Content-Type": "application/json", "Content-Length": str(len(data))})
    started = time.monotonic()
    try:
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        payload = json.loads(response.read() or b"{}")
        return response.status, payload, time.monotonic() - started
    finally:
        conn.close()


@pytest.fixture
def helper(store):
    """The real request handler on a loopback port."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1]
    finally:
        for gate in store.fake.gates.values():
            gate.set()
        httpd.shutdown()
        httpd.server_close()


def test_a_stuck_save_never_freezes_health_or_settings_and_says_what_happened(store, helper):
    port = helper
    # Warm the health caches so the timed calls below measure waiting only.
    assert _request(port, "GET", "/health")[0] == 200
    store.fake.hold(TOKEN_A)
    save, result = in_thread(_request, port, "POST", "/settings",
                             {"relay_url": RELAY, "relay_token": TOKEN_A, "relay_enabled": True})
    assert store.fake.entered[TOKEN_A].wait(5)

    for path in ("/health", "/settings"):
        status, payload, seconds = _request(port, "GET", path, timeout=5)
        assert status == 200 and payload["ok"] is True, payload
        assert seconds < 1.0, f"{path} waited {seconds:.2f}s behind the stuck save"

    save.join(10)
    status, payload, seconds = result["value"]
    assert status == 200 and payload == DIDNT_ANSWER
    assert TIMEOUT * 0.9 <= seconds < TIMEOUT + 3

    # The store is still stuck. Nothing says the relay is set up or on, and
    # reads don't wait behind the stuck call.
    status, payload, seconds = _request(port, "GET", "/settings", timeout=5)
    settings = payload["settings"]
    assert (settings["relay_url"], settings["relay_enabled"], settings["relay_token_set"]) == ("", False, False)
    assert seconds < 1.0
    assert TOKEN_A not in json.dumps(payload)
    assert not (store.folder / "settings.json").exists()


@pytest.mark.parametrize("field,value", [
    ("relay_token", TOKEN_A), ("anthropic_key", API_KEY), ("scrapecreators_key", SC_KEY)])
def test_every_secret_save_gives_up_on_a_stuck_store(store, monkeypatch, field, value):
    monkeypatch.setattr(server, "CREDENTIAL_STORE_TIMEOUT_SEC", 0.5)
    store.fake.hold(value)
    started = time.monotonic()
    probe = post_settings({field: value, "relay_enabled": True})
    assert probe.status == 200 and probe.payload == DIDNT_ANSWER
    assert time.monotonic() - started < 3
    assert not (store.folder / "settings.json").exists()


@pytest.mark.parametrize("field,value", [
    ("relay_token", TOKEN_A), ("anthropic_key", API_KEY), ("scrapecreators_key", SC_KEY)])
def test_a_store_error_is_reported_plainly_without_the_secret(store, caplog, field, value):
    store.fake.fail_with = RuntimeError(f"backend echoed {value}")
    probe = post_settings({field: value, "relay_enabled": True})
    assert probe.status == 200 and probe.payload == DIDNT_SAVE
    assert value not in caplog.text and value not in json.dumps(probe.payload)
    assert not (store.folder / "settings.json").exists()


def test_a_normal_save_works_and_the_settings_lock_is_free_during_the_call(store):
    lock_free = []
    original = store.fake.set_password

    def set_password(service, username, value):
        # From the worker thread: is anyone (the request) holding the lock?
        got = server._settings_lock.acquire(timeout=0.5)
        if got:
            server._settings_lock.release()
        lock_free.append(got)
        original(service, username, value)

    store.fake.set_password = set_password
    probe = post_settings({"relay_url": RELAY, "relay_token": TOKEN_A, "relay_enabled": True})
    assert probe.status == 200 and probe.payload["ok"] is True, probe.payload
    settings = probe.payload["settings"]
    assert (settings["relay_url"], settings["relay_enabled"], settings["relay_token_set"]) == (RELAY, True, True)
    assert lock_free == [True]
    assert store.fake.values == {(store.service, "relay_pull_token"): TOKEN_A}
    assert TOKEN_A not in (store.folder / "settings.json").read_text(encoding="utf-8")


# ---- a late call never overwrites a newer value -------------------------------

def test_a_late_save_lands_before_a_newer_one_so_the_newest_token_wins(store, monkeypatch):
    monkeypatch.setattr(server, "CREDENTIAL_STORE_TIMEOUT_SEC", 2.0)
    gate = store.fake.hold(TOKEN_A)
    first = post_settings({"relay_token": TOKEN_A})
    assert first.payload == DIDNT_ANSWER
    # The first call is still inside the store. A newer save waits its turn...
    second, result = in_thread(post_settings, {"relay_token": TOKEN_B})
    time.sleep(0.3)
    assert "value" not in result
    # ...the prompt is answered: the old call lands, then the newer one runs.
    gate.set()
    second.join(5)
    assert result["value"].payload["ok"] is True
    assert result["value"].payload["settings"]["relay_token_set"] is True
    assert store.fake.sets() == [TOKEN_A, TOKEN_B]
    assert store.fake.values[(store.service, "relay_pull_token")] == TOKEN_B
    assert server._get_saved_relay_token() == TOKEN_B


def test_saves_run_in_order_and_one_that_gave_up_never_runs_later(store, monkeypatch):
    gate = store.fake.hold(TOKEN_A)
    in_thread(server._store_saved_relay_token, TOKEN_A)
    assert store.fake.entered[TOKEN_A].wait(5)
    with pytest.raises(server.CredentialStoreTimeout):
        server._store_saved_relay_token(TOKEN_B)  # waits its turn, then gives up
    monkeypatch.setattr(server, "CREDENTIAL_STORE_TIMEOUT_SEC", 5.0)
    third, third_result = in_thread(server._store_saved_relay_token, TOKEN_C)
    time.sleep(0.1)
    fourth, fourth_result = in_thread(server._store_saved_relay_token, TOKEN_D)
    time.sleep(0.1)
    gate.set()
    third.join(5)
    fourth.join(5)
    assert "error" not in third_result and "error" not in fourth_result
    assert store.fake.sets() == [TOKEN_A, TOKEN_C, TOKEN_D]
    assert server._get_saved_relay_token() == TOKEN_D


def test_reads_never_wait_behind_a_stuck_call(store):
    server._store_saved_relay_token(TOKEN_A)
    server._store_saved_anthropic_key(API_KEY)
    gate = store.fake.hold(TOKEN_B)
    stuck, _ = in_thread(server._store_saved_relay_token, TOKEN_B)
    assert store.fake.entered[TOKEN_B].wait(5)
    started = time.monotonic()
    # The last values this process saw, or "" for one it never saw.
    assert server._get_saved_relay_token() == TOKEN_A
    assert server._get_saved_anthropic_key() == API_KEY
    assert server._get_saved_scrapecreators_key() == ""
    assert time.monotonic() - started < 1.0
    gate.set()
    stuck.join(5)
    assert server._get_saved_relay_token() == TOKEN_B


def test_a_401_for_a_key_replaced_mid_check_is_ignored(store, monkeypatch):
    server._store_saved_scrapecreators_key(SC_KEY)
    original = server._get_saved_scrapecreators_key

    def read_while_a_save_starts():
        value = original()
        server._store_saved_scrapecreators_key(SC_KEY + "-new")
        return value

    monkeypatch.setattr(server, "_get_saved_scrapecreators_key", read_while_a_save_starts)
    server._mark_scrapecreators_key_invalid(expected_key=SC_KEY)
    assert server._read_settings()["scrapecreators_key_invalid"] is False
    monkeypatch.setattr(server, "_get_saved_scrapecreators_key", original)
    server._mark_scrapecreators_key_invalid(expected_key=SC_KEY + "-new")
    assert server._read_settings()["scrapecreators_key_invalid"] is True


# ---- isolated profiles never touch the OS store --------------------------------

def forbid_keyring(monkeypatch) -> list:
    touched: list = []

    def forbidden(*args, **kwargs):
        touched.append(args[:2])
        raise AssertionError("touched the OS credential store")

    fake = SimpleNamespace(get_password=forbidden, set_password=forbidden, delete_password=forbidden)
    monkeypatch.setattr(server, "_keyring", fake)
    monkeypatch.setattr(server, "_keyring_module", forbidden)
    monkeypatch.setitem(sys.modules, "keyring", fake)
    return touched


def test_an_isolated_profile_keeps_secrets_in_its_own_file_and_never_calls_keyring(tmp_path, monkeypatch):
    touched = forbid_keyring(monkeypatch)
    profile, other = tmp_path / "profile", tmp_path / "other"
    profile.mkdir()
    other.mkdir()
    with iso.bound_isolation(profile=profile, port=5180):
        assert server._credential_store_mode() == "file"
        server._store_saved_relay_token(TOKEN_A)
        server._store_saved_anthropic_key(API_KEY)
        server._store_saved_scrapecreators_key(SC_KEY)
        assert (server._get_saved_relay_token(), server._get_saved_anthropic_key(),
                server._get_saved_scrapecreators_key()) == (TOKEN_A, API_KEY, SC_KEY)
        saved = json.loads((profile / "credentials.json").read_text(encoding="utf-8"))
        assert saved == {"version": 1, "entries": {
            "relay_pull_token": TOKEN_A, "anthropic_key": API_KEY, "scrapecreators_key": SC_KEY}}
        server._store_saved_relay_token("")
        assert server._get_saved_relay_token() == ""
        assert "relay_pull_token" not in json.loads(
            (profile / "credentials.json").read_text(encoding="utf-8"))["entries"]
        public = server._public_settings({})
        assert public["anthropic_key_set"] is True and public["relay_token_set"] is False
        assert server._credential_store_error() is None
    with iso.bound_isolation(profile=other, port=5180):
        assert server._get_saved_anthropic_key() == ""
    assert touched == []
    assert not [p.name for p in profile.iterdir() if p.name.endswith(".tmp")]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_the_credentials_file_is_owner_only(tmp_path, monkeypatch):
    forbid_keyring(monkeypatch)
    with iso.bound_isolation(profile=tmp_path, port=5180):
        server._store_saved_relay_token(TOKEN_A)
    assert (tmp_path / "credentials.json").stat().st_mode & 0o777 == 0o600


def test_saving_the_relay_token_in_an_isolated_profile_uses_the_file(tmp_path, monkeypatch):
    touched = forbid_keyring(monkeypatch)
    monkeypatch.setattr(server, "_isolated_binding", lambda: SimpleNamespace(profile=tmp_path))
    settings_view_patches(monkeypatch, tmp_path)
    probe = post_settings({"relay_url": RELAY, "relay_token": TOKEN_A, "relay_enabled": True})
    assert probe.status == 200 and probe.payload["ok"] is True, probe.payload
    assert probe.payload["settings"]["relay_token_set"] is True
    entries = json.loads((tmp_path / "credentials.json").read_text(encoding="utf-8"))["entries"]
    assert entries == {"relay_pull_token": TOKEN_A}
    assert TOKEN_A not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert touched == []


def test_an_unreadable_credentials_file_is_left_alone(tmp_path, monkeypatch):
    forbid_keyring(monkeypatch)
    monkeypatch.setattr(server, "_isolated_binding", lambda: SimpleNamespace(profile=tmp_path))
    (tmp_path / "credentials.json").write_text("{not json " + TOKEN_B, encoding="utf-8")
    assert server._get_saved_relay_token() == ""
    with pytest.raises(server.CredentialStoreError) as caught:
        server._store_saved_relay_token(TOKEN_A)
    assert TOKEN_B not in str(caught.value)
    assert (tmp_path / "credentials.json").read_text(encoding="utf-8") == "{not json " + TOKEN_B


def test_uoink_credential_store_file_works_without_isolation(tmp_path, monkeypatch):
    touched = forbid_keyring(monkeypatch)
    monkeypatch.setattr(server, "_isolated_binding", lambda: None)
    monkeypatch.setattr(server, "_settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setenv("UOINK_CREDENTIAL_STORE", "file")
    assert server._credential_store_mode() == "file"
    server._store_saved_anthropic_key(API_KEY)
    assert server._get_saved_anthropic_key() == API_KEY
    assert json.loads((tmp_path / "credentials.json").read_text(encoding="utf-8"))["entries"] == {
        "anthropic_key": API_KEY}
    assert touched == []
    monkeypatch.delenv("UOINK_CREDENTIAL_STORE")
    assert server._credential_store_mode() == "keyring"


def test_without_isolation_the_os_store_keeps_its_names_and_its_timeout(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(server, "_keyring", fake)
    monkeypatch.setattr(server, "_isolated_binding", lambda: None)
    monkeypatch.delenv("UOINK_CREDENTIAL_STORE", raising=False)
    monkeypatch.setattr(server, "_credential_turns", server._CredentialTurns())
    monkeypatch.setattr(server, "_credential_last_seen", {})
    turns = server._credential_turns
    assert server._credential_store_mode() == "keyring"
    server._store_saved_relay_token(TOKEN_A)
    server._store_saved_anthropic_key(API_KEY)
    server._store_saved_scrapecreators_key(SC_KEY)
    assert fake.values == {("Uoink", "relay_pull_token"): TOKEN_A, ("Uoink", "anthropic_key"): API_KEY,
                           ("Uoink", "scrapecreators_key"): SC_KEY}
    assert server._get_saved_anthropic_key() == API_KEY
    monkeypatch.setattr(server, "CREDENTIAL_STORE_TIMEOUT_SEC", 0.3)
    gate = fake.hold(TOKEN_B)
    try:
        with pytest.raises(server.CredentialStoreTimeout):
            server._store_saved_relay_token(TOKEN_B)
    finally:
        gate.set()
        wait_idle(turns)


def test_migration_never_touches_the_os_store_in_an_isolated_profile(tmp_path, monkeypatch):
    touched = forbid_keyring(monkeypatch)
    with iso.bound_isolation(profile=tmp_path, port=5180):
        assert migrate_install._legacy_keyring_key_present() is False
        assert migrate_install._migrate_keyring(dry_run=False) == "skipped: keyring unavailable"
    monkeypatch.setattr(iso, "current_binding", lambda: None)
    monkeypatch.setenv("UOINK_CREDENTIAL_STORE", "file")
    assert migrate_install._legacy_keyring_key_present() is False
    assert touched == []


def test_the_legacy_key_probe_gives_up_on_a_stuck_store(monkeypatch):
    gate, entered = threading.Event(), threading.Event()

    def get_password(service, username):
        entered.set()
        gate.wait(30)
        return "legacy"

    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=get_password))
    monkeypatch.setattr(iso, "current_binding", lambda: None)
    monkeypatch.delenv("UOINK_CREDENTIAL_STORE", raising=False)
    monkeypatch.setattr(migrate_install, "KEYRING_TIMEOUT_SEC", 0.3)
    turn = threading.Lock()
    monkeypatch.setattr(migrate_install, "_keyring_turn", turn)
    try:
        started = time.monotonic()
        assert migrate_install._legacy_keyring_key_present() is False
        assert entered.is_set()
        # Still stuck: the next probe answers at once instead of adding a thread.
        assert migrate_install._legacy_keyring_key_present() is False
        assert time.monotonic() - started < 2
    finally:
        gate.set()
        assert turn.acquire(timeout=5)
        turn.release()

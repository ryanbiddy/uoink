from __future__ import annotations

import copy
import hashlib
import json
import inspect
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import server
import writer_peer

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = (
    ROOT / "tests" / "fixtures" / "suite_integration_v1"
    / "writer-provider.json"
)
PROVENANCE_PATH = FIXTURE_PATH.with_name("writer-provider.provenance.json")
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
SHARED_UI_PATH = FIXTURE_PATH.with_name("runtime-lease.json")
SHARED_UI_PROVENANCE_PATH = SHARED_UI_PATH.with_name(
    "runtime-lease.provenance.json"
)


def _negative(group, name):
    if group == "runtime_lease":
        payload = copy.deepcopy(FIXTURE["valid"]["runtime_lease"])
    elif group == "service_manifest":
        payload = copy.deepcopy(FIXTURE["valid"]["service_manifest"])
    elif group == "health":
        payload = copy.deepcopy(FIXTURE["valid"]["health"])
    else:
        raise AssertionError(f"unknown fixture group: {group}")
    mutation = FIXTURE["negative"][group][name]
    cursor = payload
    parts = mutation["path"].split(".")
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    final = parts[-1]
    assert mutation["operation"] == "set"
    if isinstance(cursor, list):
        cursor[int(final)] = mutation["value"]
    else:
        cursor[final] = mutation["value"]
    return payload


def _shared_ui_case(case_id):
    fixture = json.loads(SHARED_UI_PATH.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in fixture["cases"]}
    case = cases[case_id]
    payload = copy.deepcopy(cases[case["base"]]["payload"])
    for mutation in case.get("mutations", []):
        assert mutation["op"] == "set"
        cursor = payload
        for part in mutation["path"][:-1]:
            cursor = cursor[part]
        cursor[mutation["path"][-1]] = mutation["value"]
    return case, payload


class FixtureWriter(BaseHTTPRequestHandler):
    requests = []
    mode = "ready"

    def log_message(self, format, *args):  # noqa: A002
        return

    def _send(self, payload, status=200):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        type(self).requests.append({
            "path": self.path,
            "token": self.headers.get("X-Writer-Token"),
        })
        if self.path == "/.well-known/suite-service.json":
            payload = copy.deepcopy(FIXTURE["valid"]["service_manifest"])
            if type(self).mode == "wrong_service":
                payload["service"]["id"] = "not-writer"
            elif type(self).mode == "manifest_drift":
                payload["service"]["unknown"] = True
            return self._send(payload)
        if self.path == "/api/suite/v1/health":
            payload = copy.deepcopy(FIXTURE["valid"]["health"])
            if type(self).mode == "unhealthy":
                payload["ok"] = False
                payload["state"] = "needs_attention"
                payload["checks"][1]["status"] = "failed"
            return self._send(payload)
        if self.path == "/api/writer/v1/status":
            if self.headers.get("X-Writer-Token") != "writer-fixture-token":
                return self._send({"ok": False}, 403)
            return self._send({
                "ok": True,
                "contract": "writer.api",
                "version": 1,
                "data": {
                    "service": "writer",
                    "schema_version": 1,
                    "database": "ready",
                    "uoink": "configured",
                    "counts": {
                        "drafts": 2,
                        "pieces": 3,
                        "scripts": 1,
                        "voice_samples": 1,
                    },
                },
            })
        self._send({"ok": False}, 404)


@pytest.fixture
def fixture_writer(monkeypatch):
    FixtureWriter.requests = []
    FixtureWriter.mode = "ready"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FixtureWriter)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = int(httpd.server_address[1])
    monkeypatch.setenv(
        "UOINK_WRITER_URL", f"http://127.0.0.1:{port}")
    try:
        yield port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_status_is_exact_peer_v1_path_free_and_uses_writer_credential(
        fixture_writer, monkeypatch):
    monkeypatch.setenv("UOINK_WRITER_TOKEN", "writer-fixture-token")
    status = writer_peer.status()
    assert status == {
        "ok": True,
        "contract": "ryan.suite.peer",
        "version": 1,
        "peer": "writer",
        "state": "available",
        "capabilities": [
            "writer.api/1",
            "writer.shot-list/1",
        ],
    }
    assert FixtureWriter.requests[-1] == {
        "path": "/api/writer/v1/status",
        "token": "writer-fixture-token",
    }
    serialized = json.dumps(status).casefold()
    assert "writer-fixture-token" not in serialized
    assert "127.0.0.1" not in serialized
    assert ".db" not in serialized


def test_detected_but_unconfigured_does_not_read_writer_files(
        fixture_writer, monkeypatch):
    monkeypatch.delenv("UOINK_WRITER_TOKEN", raising=False)
    status = writer_peer.status()
    assert status == {
        "ok": True,
        "contract": "ryan.suite.peer",
        "version": 1,
        "peer": "writer",
        "state": "unconfigured",
        "capabilities": [],
    }
    assert FixtureWriter.requests == [
        {"path": "/.well-known/suite-service.json", "token": None},
        {"path": "/api/suite/v1/health", "token": None},
    ]


def test_peer_url_must_be_loopback(monkeypatch):
    monkeypatch.setenv("UOINK_WRITER_URL", "https://example.com")
    monkeypatch.setenv("UOINK_WRITER_TOKEN", "secret")
    status = writer_peer.status()
    assert status["ok"] is False
    assert status["state"] == "unhealthy"
    assert status["error"]["code"] == "invalid_configuration"
    assert status["error"]["retryable"] is False


def test_writer_provider_fixture_is_pinned_to_public_writer_main():
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    assert hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest().upper() == (
        provenance["local_copy_sha256"]
    )
    assert provenance == {
        "repository": "ryanbiddy/writer",
        "commit": "1d2ce1abf1a8db631e5b694c7db4f4f6aacae53e",
        "fixture": "tests/fixtures/suite_integration_v1/writer-provider.json",
        "git_blob_sha": "6c9a7f2743beddfbfe59d094d67c100d55fedf2b",
        "fixture_sha256": (
            "CD653E76CCC991E2AB8176C8641CEC82C1C9C4DA31782ABE2633CF9FDF8809F2"
        ),
        "local_copy_sha256": (
            "CD653E76CCC991E2AB8176C8641CEC82C1C9C4DA31782ABE2633CF9FDF8809F2"
        ),
        "copy_note": (
            "The local copy is byte-for-byte identical to the pinned Writer blob."
        ),
    }
    assert FIXTURE["_fixture"]["provider"] == "Writer"


def test_strict_writer_lease_manifest_and_health_validators():
    assert writer_peer.validate_runtime_lease(
        FIXTURE["valid"]["runtime_lease"],
        pid_checker=lambda _pid: True,
    )["service_id"] == "writer"
    assert writer_peer.validate_service_manifest(
        FIXTURE["valid"]["service_manifest"]
    )["service"]["id"] == "writer"
    assert writer_peer.validate_health(
        FIXTURE["valid"]["health"]
    )["state"] == "ready"

    for name in FIXTURE["negative"]["runtime_lease"]:
        with pytest.raises(writer_peer.WriterPeerError) as raised:
            writer_peer.validate_runtime_lease(
                _negative("runtime_lease", name),
                pid_checker=lambda _pid: True,
            )
        assert raised.value.code == "invalid_lease"

    stale = copy.deepcopy(FIXTURE["valid"]["runtime_lease"])
    with pytest.raises(writer_peer.WriterPeerError) as raised:
        writer_peer.validate_runtime_lease(
            stale,
            pid_checker=lambda _pid: False,
        )
    assert raised.value.code == "stale_lease"
    assert raised.value.retryable is True

    wrong_identity = copy.deepcopy(FIXTURE["valid"]["runtime_lease"])
    wrong_identity["service_id"] = "uoink"
    with pytest.raises(writer_peer.WriterPeerError) as raised:
        writer_peer.validate_runtime_lease(
            wrong_identity,
            pid_checker=lambda _pid: True,
        )
    assert raised.value.code == "invalid_lease"

    for group, validator in (
        ("service_manifest", writer_peer.validate_service_manifest),
        ("health", writer_peer.validate_health),
    ):
        for name in FIXTURE["negative"][group]:
            with pytest.raises(writer_peer.WriterPeerError):
                validator(_negative(group, name))


def test_shared_ui_fixture_is_pinned_to_zing_provider():
    provenance = json.loads(
        SHARED_UI_PROVENANCE_PATH.read_text(encoding="utf-8")
    )
    digest = hashlib.sha256(SHARED_UI_PATH.read_bytes()).hexdigest().upper()
    assert digest == provenance["fixture_sha256"]
    assert provenance == {
        "repository": "ryanbiddy/zing",
        "commit": "8775c43c35456635e282b8a3e2bb2920f488db1a",
        "fixture": "tools/eval/fixtures/suite_v1/runtime-lease.json",
        "git_blob_sha": "74fb47e0baf3159ce7dbe19556bdaf4029f4a4ee",
        "fixture_sha256": (
            "F22C3CF37CA0470B39557693696A4B57F237BDFB10C09DC521FA72A500B3B06F"
        ),
        "copy_note": (
            "The local copy is byte-for-byte identical to the pinned Zing blob."
        ),
    }


@pytest.mark.parametrize(
    "case_id",
    [
        "valid_service_local_ui_paths",
        "network_path_home",
        "backslash_home",
        "absolute_url_home",
        "network_path_route",
        "backslash_route",
        "absolute_url_route",
    ],
)
def test_shared_ui_paths_cover_writer_lease_and_manifest(case_id):
    case, shared = _shared_ui_case(case_id)
    lease = copy.deepcopy(FIXTURE["valid"]["runtime_lease"])
    lease["ui"] = shared["ui"]
    manifest = copy.deepcopy(FIXTURE["valid"]["service_manifest"])
    manifest["service"]["ui"] = shared["ui"]

    if case["expected_valid"]:
        assert writer_peer.validate_runtime_lease(
            lease, pid_checker=lambda _pid: True
        )
        assert writer_peer.validate_service_manifest(manifest)
    else:
        with pytest.raises(writer_peer.WriterPeerError) as lease_error:
            writer_peer.validate_runtime_lease(
                lease, pid_checker=lambda _pid: True
            )
        assert lease_error.value.code == "invalid_lease"
        with pytest.raises(writer_peer.WriterPeerError) as manifest_error:
            writer_peer.validate_service_manifest(manifest)
        assert manifest_error.value.code == "contract_mismatch"


def test_discovery_order_is_explicit_then_writer_lease_then_default(
        fixture_writer, tmp_path):
    registry = tmp_path / "services.d"
    registry.mkdir()
    lease = copy.deepcopy(FIXTURE["valid"]["runtime_lease"])
    lease["pid"] = os.getpid()
    lease["base_url"] = f"http://127.0.0.1:{fixture_writer}"
    lease["health_url"] = lease["base_url"] + "/api/suite/v1/health"
    lease["manifest_url"] = (
        lease["base_url"] + "/.well-known/suite-service.json"
    )
    (registry / "writer.json").write_text(
        json.dumps(lease),
        encoding="utf-8",
    )

    target = writer_peer.resolve_writer_target(
        environ={},
        registry_dir=registry,
        pid_checker=lambda _pid: True,
        check_permissions=False,
    )
    assert target.source == "lease"
    assert target.base_url.endswith(f":{fixture_writer}")

    explicit = writer_peer.resolve_writer_target(
        environ={"UOINK_WRITER_URL": "http://127.0.0.1:61999"},
        registry_dir=registry,
        pid_checker=lambda _pid: True,
        check_permissions=False,
    )
    assert explicit.source == "explicit"
    assert explicit.base_url.endswith(":61999")

    default = writer_peer.resolve_writer_target(
        environ={},
        registry_dir=tmp_path / "missing",
        pid_checker=lambda _pid: True,
        check_permissions=False,
    )
    assert default.source == "default"
    assert default.base_url == "http://127.0.0.1:5181"


def test_status_consumes_valid_writer_runtime_lease(
        fixture_writer, tmp_path):
    registry = tmp_path / "services.d"
    registry.mkdir()
    lease = copy.deepcopy(FIXTURE["valid"]["runtime_lease"])
    lease["pid"] = os.getpid()
    lease["base_url"] = f"http://127.0.0.1:{fixture_writer}"
    lease["health_url"] = lease["base_url"] + "/api/suite/v1/health"
    lease["manifest_url"] = (
        lease["base_url"] + "/.well-known/suite-service.json"
    )
    (registry / "writer.json").write_text(
        json.dumps(lease),
        encoding="utf-8",
    )
    status = writer_peer.status(
        environ={"UOINK_WRITER_TOKEN": "writer-fixture-token"},
        registry_dir=registry,
        timeout=0.5,
        check_permissions=False,
    )
    assert status["state"] == "available"
    assert status["capabilities"] == [
        "writer.api/1",
        "writer.shot-list/1",
    ]


def test_invalid_or_stale_lease_is_unhealthy_without_default_fallback(
        tmp_path):
    registry = tmp_path / "services.d"
    registry.mkdir()
    (registry / "writer.json").write_text(
        json.dumps(_negative("runtime_lease", "unknown_key")),
        encoding="utf-8",
    )
    invalid = writer_peer.status(
        environ={},
        registry_dir=registry,
        default_base_url="http://127.0.0.1:1",
        check_permissions=False,
    )
    assert invalid["error"]["code"] == "invalid_lease"

    (registry / "writer.json").write_text(
        json.dumps(FIXTURE["valid"]["runtime_lease"]),
        encoding="utf-8",
    )
    stale = writer_peer.status(
        environ={},
        registry_dir=registry,
        default_base_url="http://127.0.0.1:1",
        pid_checker=lambda _pid: False,
        check_permissions=False,
    )
    assert stale["error"]["code"] == "stale_lease"


def test_default_refusal_is_absent_but_explicit_refusal_is_unhealthy(tmp_path):
    absent = writer_peer.status(
        environ={},
        registry_dir=tmp_path / "missing",
        default_base_url="http://127.0.0.1:1",
        timeout=0.05,
    )
    assert absent["ok"] is True
    assert absent["state"] == "absent"

    unhealthy = writer_peer.status(
        environ={"UOINK_WRITER_URL": "http://127.0.0.1:1"},
        registry_dir=tmp_path / "missing",
        timeout=0.05,
    )
    assert unhealthy["ok"] is False
    assert unhealthy["state"] == "unhealthy"
    assert unhealthy["error"]["code"] in {"unavailable", "timeout"}


def test_status_preserves_auth_wrong_service_contract_and_health_errors(
        fixture_writer):
    base = f"http://127.0.0.1:{fixture_writer}"
    auth = writer_peer.status(
        environ={
            "UOINK_WRITER_URL": base,
            "UOINK_WRITER_TOKEN": "wrong-token",
        },
        registry_dir=Path("missing"),
        timeout=0.5,
    )
    assert auth["error"]["code"] == "authentication_failed"

    FixtureWriter.mode = "wrong_service"
    wrong = writer_peer.status(
        environ={"UOINK_WRITER_URL": base},
        registry_dir=Path("missing"),
        timeout=0.5,
    )
    assert wrong["error"]["code"] == "wrong_service"

    FixtureWriter.mode = "manifest_drift"
    drift = writer_peer.status(
        environ={"UOINK_WRITER_URL": base},
        registry_dir=Path("missing"),
        timeout=0.5,
    )
    assert drift["error"]["code"] == "contract_mismatch"

    FixtureWriter.mode = "unhealthy"
    health = writer_peer.status(
        environ={"UOINK_WRITER_URL": base},
        registry_dir=Path("missing"),
        timeout=0.5,
    )
    assert health["error"]["code"] == "peer_unhealthy"


def test_explicit_timeout_is_unhealthy_and_retryable(monkeypatch):
    def timed_out(_url, *, timeout):
        raise writer_peer._TransportError(
            "timeout",
            "Writer suite probe timed out",
            retryable=True,
            absence_eligible=True,
        )

    monkeypatch.setattr(writer_peer, "_get_json", timed_out)
    result = writer_peer.status(
        environ={"UOINK_WRITER_URL": "http://127.0.0.1:5181"},
        timeout=0.05,
    )
    assert result["state"] == "unhealthy"
    assert result["error"] == {
        "code": "timeout",
        "message": "Writer suite probe timed out",
        "retryable": True,
    }


def test_legacy_generate_routes_remain_the_default_compatibility_path():
    source = inspect.getsource(server)
    assert source.count("writer_peer.status()") == 1
    for route, handler in (
            ('bare == "/writing/tweet"', "_handle_writing_tweet"),
            ('bare == "/writing/blog"', "_handle_writing_blog"),
            ('bare == "/writing/draft"', "_handle_writing_draft_save"),
            ('bare == "/script/generate"', "_handle_script_generate"),
            ('bare == "/script/revise"', "_handle_script_revise"),
            ('bare == "/workspace/critique"', "_handle_workspace_critique"),
    ):
        assert route in source
        assert hasattr(server.Handler, handler)


class QuietUoink(server.Handler):
    def log_message(self, format, *args):  # noqa: A002
        return


def request_uoink(port, *, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/writer-peer/v1/status",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_uoink_exposes_authenticated_read_only_peer_status(monkeypatch):
    expected = {
        "ok": True,
        "contract": "ryan.suite.peer",
        "version": 1,
        "peer": "writer",
        "state": "absent",
        "capabilities": [],
    }
    monkeypatch.setattr(writer_peer, "status", lambda: expected)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuietUoink)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = int(httpd.server_address[1])
        status, payload = request_uoink(port)
        assert status == 200
        assert payload == expected
        denied, body = request_uoink(port, token=False)
        assert denied == 403
        assert body["ok"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

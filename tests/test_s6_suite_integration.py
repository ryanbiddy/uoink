"""S6 conformance tests for Uoink's product-owned suite boundaries."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import engagement_contract
import index as index_mod
import media_handoff
import regenerate_suite_integration_v1_fixture as regenerate
import server
import suite_service


class _QuietHandler(server.Handler):
    def log_message(self, format, *args):  # noqa: A002
        return


def _request(
    port: int,
    method: str,
    path: str,
    *,
    body: dict | None = None,
    token: bool = True,
) -> tuple[int, dict]:
    headers = {}
    data = None
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


@pytest.fixture
def live_server(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path / "corpus")
    monkeypatch.setattr(server, "_path_integrity_status", lambda: {"ok": True})
    monkeypatch.setattr(server, "_index_recovering", False)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(httpd.server_address[1]), idx
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        idx.close()


def _insert_item(
    idx: index_mod.Index,
    root: Path,
    item_id: str,
    *,
    sidecar: dict,
) -> Path:
    folder = root / item_id
    folder.mkdir(parents=True)
    corpus_path = folder / f"{item_id}.md"
    sidecar_path = folder / f"{item_id}.json"
    corpus_path.write_text("# Fixture\n", encoding="utf-8")
    sidecar_path.write_text(
        json.dumps(sidecar, sort_keys=True),
        encoding="utf-8",
    )
    idx.upsert_yoink(
        {
            "video_id": item_id,
            "slug": item_id,
            "title": "Fixture",
            "yoinked_at": "2026-07-19T12:00:00Z",
            "corpus_path": str(corpus_path),
            "sidecar_path": str(sidecar_path),
            "metadata_json": json.dumps(
                {"url": "https://example.test/short/123"}
            ),
        },
        content="Fixture",
    )
    return folder


def _event(event_id: str, item_id: str = "short-123") -> dict:
    return {
        "event_id": event_id,
        "item_ref": f"uoink://item/{item_id}",
        "event_type": "cite",
        "source_product": "writer",
        "occurred_at": "2026-07-19T12:00:00Z",
    }


def test_uoink_suite_provider_matches_conformance_fixture():
    expected = json.loads(regenerate.FIXTURE_PATH.read_text(encoding="utf-8"))
    actual = regenerate.generate_fixture()
    assert actual == expected
    assert expected["_fixture"] == {
        "contracts": [
            "ryan.suite.runtime-lease/1",
            "ryan.suite.service/1",
            "ryan.suite.health/1",
            "uoink.media.handoff/1",
            "uoink.engagement.ingest/1",
        ],
        "provider": "Uoink",
        "regenerate": (
            "python tests/regenerate_suite_integration_v1_fixture.py"
        ),
        "check": (
            "python tests/regenerate_suite_integration_v1_fixture.py --check"
        ),
        "data": "synthetic",
        "network": "none",
    }


def test_service_manifest_and_health_are_exact_and_public(
    live_server, monkeypatch
):
    port, _idx = live_server
    status, manifest = _request(
        port,
        "GET",
        "/.well-known/suite-service.json",
        token=False,
    )
    assert status == 200
    assert manifest == suite_service.service_manifest(server.VERSION)
    assert set(manifest) == {"ok", "contract", "version", "service"}
    assert set(manifest["service"]) == {
        "id",
        "name",
        "service_version",
        "api_version",
        "resident",
        "default_port",
        "health",
        "capabilities",
        "ui",
        "mcp",
    }
    assert manifest["service"]["capabilities"] == sorted(
        manifest["service"]["capabilities"]
    )
    assert all(
        word not in json.dumps(manifest).lower()
        for word in ("token_path", "command", "working_directory")
    )

    status, health = _request(
        port, "GET", "/api/suite/v1/health", token=False
    )
    assert status == 200
    assert health == suite_service.health_payload(
        server.VERSION,
        index_recovering=False,
        corpus_paths_ok=True,
    )
    assert [check["id"] for check in health["checks"]] == [
        "core",
        "index",
        "corpus_paths",
    ]

    monkeypatch.setattr(server, "_index_recovering", True)
    status, health = _request(
        port, "GET", "/api/suite/v1/health", token=False
    )
    assert status == 200
    assert health["ok"] is True
    assert health["state"] == "ready_with_limits"
    assert health["checks"][1]["status"] == "busy"

    monkeypatch.setattr(server, "_path_integrity_status", lambda: {"ok": False})
    status, health = _request(
        port, "GET", "/api/suite/v1/health", token=False
    )
    assert status == 200
    assert health["ok"] is False
    assert health["state"] == "needs_attention"
    assert health["checks"][2]["status"] == "failed"


def test_runtime_lease_is_atomic_token_free_and_owned_on_cleanup(tmp_path):
    registry = tmp_path / "services.d"
    started_at = "2026-07-19T12:00:00Z"
    lease_path = suite_service.write_runtime_lease(
        registry,
        service_version="3.6.0",
        pid=1234,
        started_at=started_at,
    )
    assert lease_path == registry / "uoink.json"
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    assert lease == suite_service.runtime_lease(
        "3.6.0", pid=1234, started_at=started_at
    )
    assert set(lease) == {
        "contract",
        "version",
        "service_id",
        "service_version",
        "api_version",
        "base_url",
        "health_url",
        "manifest_url",
        "capabilities",
        "ui",
        "pid",
        "started_at",
    }
    rendered = json.dumps(lease).lower()
    assert all(
        word not in rendered
        for word in (
            "token",
            "command",
            "arguments",
            "working_directory",
            "database_path",
            "corpus_path",
        )
    )
    assert list(registry.glob("*.tmp")) == []

    assert suite_service.remove_runtime_lease(
        lease_path,
        pid=9999,
        started_at=started_at,
    ) is False
    assert lease_path.exists()
    assert suite_service.remove_runtime_lease(
        lease_path,
        pid=1234,
        started_at=started_at,
    ) is True
    assert not lease_path.exists()


def test_registry_paths_are_per_user_and_platform_specific(tmp_path):
    assert suite_service.runtime_registry_dir(
        platform_name="win32",
        environ={"LOCALAPPDATA": str(tmp_path / "Local")},
        home=tmp_path,
    ) == tmp_path / "Local" / "RyanSuite" / "services.d"
    assert suite_service.runtime_registry_dir(
        platform_name="darwin",
        environ={},
        home=tmp_path,
    ) == tmp_path / "Library" / "Application Support" / "RyanSuite" / "services.d"
    assert suite_service.runtime_registry_dir(
        platform_name="linux",
        environ={"XDG_STATE_HOME": str(tmp_path / "state")},
        home=tmp_path,
    ) == tmp_path / "state" / "ryan-suite" / "services.d"


def test_kept_media_resolver_available_not_kept_and_missing(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        folder = _insert_item(
            idx,
            tmp_path,
            "short-123",
            sidecar={
                "schema_version": 2,
                "url": "https://example.test/short/123",
                "media_file": "video.mp4",
            },
        )
        media = b"\x00\x00\x00\x18ftypmp4-suite-fixture"
        (folder / "video.mp4").write_bytes(media)
        payload = media_handoff.resolve(idx, "short-123")
        assert payload["data"] == {
            "item_ref": "uoink://item/short-123",
            "state": "available",
            "source_url": "https://example.test/short/123",
            "media": {
                "path": str((folder / "video.mp4").resolve()),
                "media_type": "video/mp4",
                "byte_length": len(media),
                "sha256": hashlib.sha256(media).hexdigest(),
            },
            "provenance": {
                "kind": "uoink_sidecar",
                "sidecar_schema_version": 2,
                "field": "media_file",
            },
        }

        _insert_item(
            idx,
            tmp_path,
            "not-kept",
            sidecar={"schema_version": 2},
        )
        assert media_handoff.resolve(idx, "not-kept")["data"]["state"] == "not_kept"
        assert media_handoff.resolve(idx, "not-kept")["data"]["media"] is None

        _insert_item(
            idx,
            tmp_path,
            "missing-media",
            sidecar={"schema_version": 2, "media_file": "gone.mp4"},
        )
        assert media_handoff.resolve(idx, "missing-media")["data"]["state"] == "missing"
        assert media_handoff.resolve(idx, "missing-media")["data"]["media"] is None
    finally:
        idx.close()


@pytest.mark.parametrize("source_url", [
    "file:///tmp/source.mp4",
    "C:\\Users\\Ryan\\source.mp4",
    "/tmp/source.mp4",
    "ftp://example.test/source.mp4",
    "https://",
    {"not": "a URL"},
])
def test_kept_media_rejects_non_http_source_url(tmp_path, source_url):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        item_id = "bad-source-" + hashlib.sha256(
            repr(source_url).encode()).hexdigest()[:8]
        _insert_item(
            idx,
            tmp_path,
            item_id,
            sidecar={"schema_version": 2, "url": source_url},
        )
        payload, status = media_handoff.resolve_http(idx, item_id)
        assert status == 500
        assert payload["error"]["code"] == "provider_nonconformant"
        assert payload["error"]["retryable"] is False
        assert payload["error"]["message"] == (
            "kept media source_url must be null or an HTTP(S) URL")
    finally:
        idx.close()


@pytest.mark.parametrize(
    "media_file",
    ("../outside.mp4", "C:\\outside.mp4", "/tmp/outside.mp4"),
)
def test_kept_media_rejects_absolute_and_traversal(tmp_path, media_file):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        _insert_item(
            idx,
            tmp_path,
            f"unsafe-{hashlib.sha256(media_file.encode()).hexdigest()[:8]}",
            sidecar={"schema_version": 2, "media_file": media_file},
        )
        item_id = f"unsafe-{hashlib.sha256(media_file.encode()).hexdigest()[:8]}"
        payload, status = media_handoff.resolve_http(idx, item_id)
        assert status == 500
        assert payload["error"]["code"] == "provider_nonconformant"
        assert payload["error"]["retryable"] is False
    finally:
        idx.close()


def test_kept_media_rejects_outside_folder_symlink(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        folder = _insert_item(
            idx,
            tmp_path,
            "symlink-media",
            sidecar={"schema_version": 2, "media_file": "video.mp4"},
        )
        outside = tmp_path / "outside.mp4"
        outside.write_bytes(b"outside")
        try:
            (folder / "video.mp4").symlink_to(outside)
        except OSError as error:
            pytest.skip(f"symlink creation unavailable: {error}")
        payload, status = media_handoff.resolve_http(idx, "symlink-media")
        assert status == 500
        assert payload["error"]["code"] == "provider_nonconformant"
    finally:
        idx.close()


def test_kept_media_http_is_token_gated(live_server, tmp_path):
    port, idx = live_server
    folder = _insert_item(
        idx,
        tmp_path,
        "http-media",
        sidecar={"schema_version": 2, "media_file": "video.mp4"},
    )
    (folder / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp4-http")

    status, payload = _request(
        port,
        "GET",
        "/api/corpus/v1/items/http-media/kept-media",
        token=False,
    )
    assert status == 403
    assert payload["ok"] is False

    status, payload = _request(
        port,
        "GET",
        "/api/corpus/v1/items/http-media/kept-media",
    )
    assert status == 200
    assert payload["contract"] == "uoink.media.handoff"
    assert payload["data"]["state"] == "available"


def test_engagement_batch_is_idempotent_and_partially_accounts(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        _insert_item(
            idx,
            tmp_path,
            "short-123",
            sidecar={"schema_version": 2},
        )
        parsed = engagement_contract.parse_request(
            {
                "contract": "uoink.engagement.ingest",
                "version": 1,
                "events": [
                    _event("writer-one"),
                    _event("writer-missing", "missing-item"),
                ],
            }
        )
        first = idx.ingest_suite_engagement(parsed)
        assert first == {
            "submitted": 2,
            "accepted": 1,
            "duplicates": 0,
            "rejected": [
                {
                    "event_id": "writer-missing",
                    "code": "not_found",
                    "message": "corpus item not found",
                    "retryable": False,
                }
            ],
        }
        assert (
            first["submitted"]
            == first["accepted"] + first["duplicates"] + len(first["rejected"])
        )

        second = idx.ingest_suite_engagement(parsed)
        assert second["accepted"] == 0
        assert second["duplicates"] == 1
        assert len(second["rejected"]) == 1
        count = idx._conn.execute(
            "SELECT COUNT(*) FROM engagement_events WHERE event_id='writer-one'"
        ).fetchone()[0]
        assert count == 1
    finally:
        idx.close()


def test_engagement_validation_is_exact_and_bounded():
    valid = {
        "contract": "uoink.engagement.ingest",
        "version": 1,
        "events": [_event("writer-one")],
    }
    assert engagement_contract.parse_request(valid) == valid["events"]

    cases = [
        {**valid, "unknown": True},
        {**valid, "version": 2},
        {**valid, "events": []},
        {**valid, "events": [_event(f"event-{i}") for i in range(101)]},
        {
            **valid,
            "events": [{**_event("bad-event"), "event_type": "recent_open"}],
        },
        {
            **valid,
            "events": [{**_event("bad-source"), "source_product": "dashboard"}],
        },
        {
            **valid,
            "events": [{**_event("bad-time"), "occurred_at": "2026-07-19T12:00:00"}],
        },
        {
            **valid,
            "events": [{**_event("bad-ref"), "item_ref": "file:///tmp/item"}],
        },
        {
            **valid,
            "events": [{**_event("bad-key"), "extra": True}],
        },
    ]
    for case in cases:
        with pytest.raises(engagement_contract.ContractError) as raised:
            engagement_contract.parse_request(case)
        assert raised.value.code == "invalid_request"
        assert raised.value.retryable is False


def test_engagement_transaction_rolls_back_all_accepted_events(tmp_path):
    idx = index_mod.Index.open(tmp_path / "index.db")
    try:
        _insert_item(
            idx,
            tmp_path,
            "short-123",
            sidecar={"schema_version": 2},
        )
        idx._conn.executescript(
            """
            CREATE TRIGGER fail_suite_event
            BEFORE INSERT ON engagement_events
            WHEN NEW.event_id = 'writer-fail'
            BEGIN
              SELECT RAISE(ABORT, 'forced rollback');
            END;
            """
        )
        events = engagement_contract.parse_request(
            {
                "contract": "uoink.engagement.ingest",
                "version": 1,
                "events": [
                    _event("writer-before-fail"),
                    _event("writer-fail"),
                ],
            }
        )
        with pytest.raises(sqlite3.DatabaseError):
            idx.ingest_suite_engagement(events)
        count = idx._conn.execute(
            "SELECT COUNT(*) FROM engagement_events "
            "WHERE event_id IN ('writer-before-fail', 'writer-fail')"
        ).fetchone()[0]
        assert count == 0
    finally:
        idx.close()


def test_engagement_http_contract_and_auth(live_server, tmp_path):
    port, idx = live_server
    _insert_item(
        idx,
        tmp_path,
        "short-123",
        sidecar={"schema_version": 2},
    )
    body = {
        "contract": "uoink.engagement.ingest",
        "version": 1,
        "events": [_event("writer-http")],
    }

    status, payload = _request(
        port,
        "POST",
        "/api/engagement/v1/events",
        body=body,
        token=False,
    )
    assert status == 403
    assert payload["ok"] is False

    status, payload = _request(
        port,
        "POST",
        "/api/engagement/v1/events",
        body=body,
    )
    assert status == 200
    assert payload == engagement_contract.success(
        {
            "submitted": 1,
            "accepted": 1,
            "duplicates": 0,
            "rejected": [],
        }
    )

    status, payload = _request(
        port,
        "POST",
        "/api/engagement/v1/events",
        body={**body, "unknown": True},
    )
    assert status == 400
    assert payload["contract"] == "uoink.engagement.ingest"
    assert payload["error"]["code"] == "invalid_request"

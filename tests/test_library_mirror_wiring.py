"""Phase 4 AV-2s: corpus-mirror wiring (settings, intent, seams, dashboard).

Covers settings validation, the intent-then-enable flow, destination-change
reset, and that each named seam fires once when the mirror is enabled and
never when it is disabled. No live index, no port 5179, no model.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import index as index_mod
import server
from library_work import LibraryWorkService, RequestContext
from tests.test_library_work_apply_undo import (
    make_apply_environment,
    submit_accepted_result,
)

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")
LOOPBACK_ORIGIN = f"http://127.0.0.1:{server.PORT}"
CONSENT_A = {
    "destination": "",  # filled per-test
    "scope": server.LIBRARY_MIRROR_SCOPE_ALL,
    "allowlist": [],
    "consented_at_ms": 1_700_000_000_000,
    "marker": "uoink-vol-testmarker01",
}


class FakeMirror:
    def __init__(self):
        self.events = []
        self.enabled = True

    def on_committed_event(self, kind, *, video_id=None, shelf_id=None, brief_hash=None):
        self.events.append((kind, {
            "video_id": video_id, "shelf_id": shelf_id, "brief_hash": brief_hash,
        }))

    def preview(self, destination, scope, allowlist=None):
        return {
            "ok": True,
            "planned_paths": ["Library.md", ".uoink-mirror/manifest.json"],
            "counts": {"items": 1, "shelves": 0, "briefs": 0},
            "notice": server.LIBRARY_MIRROR_INDEXING_NOTICE,
            "third_party_indexing": server.LIBRARY_MIRROR_INDEXING_NOTICE,
            "conflicts": [],
            "destination": destination,
            "scope": scope,
        }

    def status(self):
        return {
            "ok": True,
            "enabled": True,
            "pending": 1,
            "synced": 2,
            "stale": 0,
            "conflicts": {},
            "deletion_pending": 0,
            "destination_state": "available",
            "state": "ready",
        }

    def resync(self, **_kwargs):
        return {"ok": True, "synced": 1, "enabled": True}


class Probe(server.Handler):
    def __init__(self, method: str, path: str, body=None, headers=None):
        self.command = method
        self.path = path
        self.client_address = ("127.0.0.1", 1)
        raw = b""
        if body is not None:
            raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.rfile = io.BytesIO(raw)
        base = {"X-Uoink-Token": server.TOKEN}
        if body is not None:
            base["Content-Type"] = "application/json"
            base["Content-Length"] = str(len(raw))
        base.update(headers or {})
        self.headers = base
        self.status = None
        self.payload = None

    def _reject_bad_host(self) -> bool:
        return False

    def _send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


def post(path, body=None, headers=None) -> Probe:
    probe = Probe("POST", path, body, headers)
    server.Handler.do_POST(probe)
    return probe


def get(path, headers=None) -> Probe:
    probe = Probe("GET", path, headers=headers)
    server.Handler.do_GET(probe)
    return probe


@pytest.fixture(autouse=True)
def _isolate_mirror_state(monkeypatch, tmp_path):
    server._mirror_intents.clear()
    server._mirror_previews.clear()
    monkeypatch.setattr(server, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: None)
    monkeypatch.setattr(server, "_autostart_enabled", lambda: False)
    monkeypatch.setattr(server, "_load_topics", lambda: {"topics": []})
    yield
    server._mirror_intents.clear()
    server._mirror_previews.clear()


def _vault(tmp_path: Path, name: str = "vault") -> Path:
    path = tmp_path / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _consent(tmp_path: Path, *, name: str = "vault", **overrides) -> dict:
    body = dict(CONSENT_A)
    body["destination"] = str(_vault(tmp_path, name))
    body.update(overrides)
    return body


def _enable_settings(monkeypatch, tmp_path, fake: FakeMirror, *, enabled: bool = True):
    consent = _consent(tmp_path)
    monkeypatch.setattr(server, "_library_mirror", lambda **_k: fake)
    if enabled:
        server._write_settings({
            "library_mirror_enabled": True,
            "library_mirror_consent": consent,
        })
    else:
        server._write_settings({
            "library_mirror_enabled": False,
            "library_mirror_consent": consent,
        })
    return consent


# ---------------------------------------------------------------------------
# Settings projection and POST validation
# ---------------------------------------------------------------------------

def test_mirror_settings_default_off_and_public():
    defaults = server._default_settings()
    assert defaults["library_mirror_enabled"] is False
    assert defaults["library_mirror_consent"] is None
    public = server._public_settings({})
    assert public["library_mirror_enabled"] is False
    assert public["library_mirror_consent"] is None
    assert server._normalize_settings({"library_mirror_enabled": "true"})[
        "library_mirror_enabled"] is False
    assert server._normalize_settings({"library_mirror_enabled": True})[
        "library_mirror_enabled"] is False  # no consent -> forced off


def test_settings_post_rejects_enable_without_intent(tmp_path):
    vault = _vault(tmp_path)
    probe = object.__new__(server.Handler)
    responses = []
    probe._send_json = lambda status, payload: responses.append((status, payload))
    server.Handler._handle_settings_post(probe, {"library_mirror_enabled": True})
    assert responses[-1][0] == 400
    assert "intent" in responses[-1][1]["error"]

    responses.clear()
    server.Handler._handle_settings_post(probe, {
        "library_mirror_consent": {
            "destination": str(vault),
            "scope": "not-a-scope",
            "allowlist": [],
            "consented_at_ms": 1,
            "marker": "x",
        },
    })
    assert responses[-1][0] == 400

    responses.clear()
    server.Handler._handle_settings_post(probe, {"library_mirror_consent": "vault"})
    assert responses[-1][0] == 400
    assert "object or null" in responses[-1][1]["error"]

    responses.clear()
    server.Handler._handle_settings_post(probe, {"library_mirror_enabled": "yes"})
    assert responses[-1][0] == 400


def test_settings_post_stores_consent_without_enabling(tmp_path):
    vault = _vault(tmp_path)
    probe = object.__new__(server.Handler)
    responses = []
    probe._send_json = lambda status, payload: responses.append((status, payload))
    server.Handler._handle_settings_post(probe, {
        "library_mirror_consent": {
            "destination": str(vault),
            "scope": server.LIBRARY_MIRROR_SCOPE_ALL,
            "allowlist": [],
            "consented_at_ms": 42,
            "marker": "uoink-vol-abc",
        },
    })
    assert responses[-1][0] == 200, responses[-1]
    settings = responses[-1][1]["settings"]
    assert settings["library_mirror_enabled"] is False
    assert settings["library_mirror_consent"]["destination"] == str(vault.resolve())
    assert settings["library_mirror_consent"]["scope"] == server.LIBRARY_MIRROR_SCOPE_ALL


def test_settings_destination_change_disables_mirror(tmp_path):
    vault_a = _vault(tmp_path, "a")
    vault_b = _vault(tmp_path, "b")
    server._write_settings({
        "library_mirror_enabled": True,
        "library_mirror_consent": {
            "destination": str(vault_a),
            "scope": server.LIBRARY_MIRROR_SCOPE_ALL,
            "allowlist": [],
            "consented_at_ms": 1,
            "marker": "mark-a",
        },
    })
    probe = object.__new__(server.Handler)
    responses = []
    probe._send_json = lambda status, payload: responses.append((status, payload))
    server.Handler._handle_settings_post(probe, {
        "library_mirror_consent": {
            "destination": str(vault_b),
            "scope": server.LIBRARY_MIRROR_SCOPE_ALL,
            "allowlist": [],
            "consented_at_ms": 2,
            "marker": "mark-b",
        },
    })
    assert responses[-1][0] == 200, responses[-1]
    settings = responses[-1][1]["settings"]
    assert settings["library_mirror_enabled"] is False
    assert Path(settings["library_mirror_consent"]["destination"]) == vault_b.resolve()


# ---------------------------------------------------------------------------
# Intent then enable
# ---------------------------------------------------------------------------

def test_intent_then_enable_flow(tmp_path, monkeypatch):
    fake = FakeMirror()
    monkeypatch.setattr(server, "_library_mirror", lambda **_k: fake)
    vault = _vault(tmp_path)
    body = {
        "destination": str(vault),
        "scope": server.LIBRARY_MIRROR_SCOPE_ALL,
        "allowlist": [],
    }
    preview = post("/library/mirror", {"op": "preview", **body})
    assert preview.status == 200 and preview.payload.get("ok") is True, preview.payload
    assert "notice" in preview.payload or "third_party_indexing" in preview.payload

    forbidden = post("/library/mirror-intent", {
        "operation": body, "confirmed": True,
    }, headers={"Origin": "https://evil.example"})
    assert forbidden.status == 403

    unconfirmed = post("/library/mirror-intent", {
        "operation": body,
    }, headers={"Origin": LOOPBACK_ORIGIN, "Sec-Fetch-Site": "same-origin"})
    assert unconfirmed.status == 403

    minted = post("/library/mirror-intent", {
        "operation": body, "confirmed": True,
    }, headers={"Origin": LOOPBACK_ORIGIN, "Sec-Fetch-Site": "same-origin"})
    assert minted.status == 200, minted.payload
    token = minted.payload["user_intent_token"]
    assert len(token) >= 43

    no_token = post("/library/mirror", {"op": "enable", **body})
    assert no_token.status == 403

    enabled = post("/library/mirror", {
        "op": "enable", **body, "user_intent_token": token,
    })
    assert enabled.status == 200, enabled.payload
    assert enabled.payload.get("enabled") is True
    stored = server._read_settings()
    assert stored["library_mirror_enabled"] is True
    assert Path(stored["library_mirror_consent"]["destination"]) == vault.resolve()

    public = get("/settings")
    assert public.status == 200
    assert public.payload["settings"]["library_mirror_enabled"] is True

    replay = post("/library/mirror", {
        "op": "enable", **body, "user_intent_token": token,
    })
    assert replay.status == 200
    assert replay.payload.get("enabled") is True


def test_enable_without_preview_is_rejected(tmp_path, monkeypatch):
    fake = FakeMirror()
    monkeypatch.setattr(server, "_library_mirror", lambda **_k: fake)
    vault = _vault(tmp_path)
    body = {
        "destination": str(vault),
        "scope": server.LIBRARY_MIRROR_SCOPE_ALL,
        "allowlist": [],
    }
    minted = post("/library/mirror-intent", {
        "operation": body, "confirmed": True,
    }, headers={"Origin": LOOPBACK_ORIGIN})
    token = minted.payload["user_intent_token"]
    refused = post("/library/mirror", {
        "op": "enable", **body, "user_intent_token": token,
    })
    assert refused.status == 400
    assert "preview" in refused.payload["error"]
    assert server._read_settings()["library_mirror_enabled"] is False


def test_disable_and_status_and_resync(tmp_path, monkeypatch):
    fake = FakeMirror()
    _enable_settings(monkeypatch, tmp_path, fake, enabled=True)
    status = post("/library/mirror", {"op": "status"})
    assert status.status == 200
    assert status.payload.get("pending") == 1
    assert status.payload.get("synced") == 2
    resync = post("/library/mirror", {"op": "resync"})
    assert resync.status == 200 and resync.payload.get("ok") is True
    disabled = post("/library/mirror", {"op": "disable"})
    assert disabled.status == 200
    assert disabled.payload.get("enabled") is False
    assert server._read_settings()["library_mirror_enabled"] is False


def test_mirror_routes_are_token_gated():
    probe = Probe("POST", "/library/mirror", {"op": "status"},
                  headers={"X-Uoink-Token": "nope"})
    server.Handler.do_POST(probe)
    assert probe.status == 403


# ---------------------------------------------------------------------------
# Named seams
# ---------------------------------------------------------------------------

def _index_one(tmp_path: Path, video_id: str = "vid-capture-1"):
    folder = tmp_path / "topic" / video_id
    folder.mkdir(parents=True, exist_ok=True)
    corpus = folder / "corpus.md"
    corpus.write_text("hello capture", encoding="utf-8")
    sidecar_path = folder / f"{video_id}.json"
    sidecar = {"video_id": video_id, "title": "Capture", "channel": "Ch"}
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    return server._index_yoink(folder, sidecar, corpus, sidecar_path)


def test_each_seam_fires_once_when_enabled_and_never_when_disabled(tmp_path, monkeypatch):
    fake = FakeMirror()
    monkeypatch.setattr(server, "_library_mirror", lambda **_k: fake)
    idx = index_mod.Index.open(tmp_path / "index.db")
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)

    def kinds():
        return [k for k, _ in fake.events]

    # --- enabled ---
    _enable_settings(monkeypatch, tmp_path, fake, enabled=True)
    fake.events.clear()

    assert _index_one(tmp_path) is True
    assert kinds().count("capture") == 1

    class _Src:
        def refresh_source(self, *_a, **_k):
            return {"ok": True}

        def note_corpus_deleted(self, *_a, **_k):
            return None

    monkeypatch.setattr(server, "_source_service", lambda: _Src())
    monkeypatch.setattr(server, "_source_operator_context", lambda: object())
    server._refresh_source_via_service("src_x")
    assert kinds().count("source_refresh") == 1

    # soft delete + restore
    video_id = "vid-del-1"
    folder = tmp_path / "AI and ML" / "del-slug"
    folder.mkdir(parents=True, exist_ok=True)
    corpus = folder / "corpus.md"
    corpus.write_text("body", encoding="utf-8")
    idx.upsert_yoink({
        "video_id": video_id, "slug": "del-slug", "channel": "Ch",
        "title": "Del", "topic": "AI and ML", "yoinked_at": "2026-01-01T00:00:00",
        "corpus_path": str(corpus), "sidecar_path": "", "source_type": "note",
    }, content="body")
    handler = object.__new__(server.Handler)
    replies = []
    handler._send_json = lambda status, payload: replies.append((status, payload))
    server.Handler._handle_memory_delete(handler, {"video_id": video_id})
    assert replies[-1][0] == 200, replies[-1]
    assert kinds().count("soft_delete") == 1

    server.Handler._handle_memory_restore(handler, {"video_id": video_id})
    assert replies[-1][0] == 200, replies[-1]
    assert kinds().count("restore") == 1

    deleted = []

    class _PurgeIdx:
        def prune_trash(self, _now):
            return ["vid-purge-1"]

        def get_yoink(self, vid):
            return {
                "video_id": vid,
                "corpus_path": str(tmp_path / "gone" / "corpus.md"),
                "deleted_at": "2000-01-01T00:00:00",
            }

        def delete_yoink(self, vid):
            deleted.append(vid)

    monkeypatch.setattr(server, "_get_index", lambda: _PurgeIdx())
    assert server._purge_trash() == 1
    assert kinds().count("hard_purge") == 1

    # library_work pin / undo (undo the pin) and apply on a fresh service
    pin_items = [{"video_id": "vid_pin_wire", "target_shelf": "shelf_alpha"}]
    _work_idx, svc, ctx_op, _clock = make_apply_environment(
        tmp_path / "work-pin", items=pin_items)
    svc.event_hook = server._mirror_event
    ctx_user = RequestContext(
        authenticated=True, client_id="user_admin", session_id="s_user",
        local_user_confirmed=True)
    pin_op = {
        "video_id": "vid_pin_wire",
        "shelf_id": "shelf_alpha",
        "action": "pin",
        "expected_projection_revision": 0,
        "operation_key": "op_pin_wire",
    }
    intent = svc.mint_user_intent(ctx_user, {"kind": "pin", "operation": pin_op})
    assert intent.get("ok") is True, intent
    pin_res = svc.pin_shelf(ctx_user, dict(pin_op, user_intent_token=intent["user_intent_token"]))
    assert pin_res.get("ok") is True, pin_res
    assert pin_res.get("apply_id"), pin_res
    assert kinds().count("pin") == 1

    undo_op = {
        "apply_id": pin_res["apply_id"],
        "expected_projection_revision": pin_res["after_revision"],
        "operation_key": "op_undo_wire",
    }
    intent_undo = svc.mint_user_intent(ctx_user, {"kind": "undo", "operation": undo_op})
    assert intent_undo.get("ok") is True, intent_undo
    undone = svc.undo_apply(
        ctx_user, dict(undo_op, user_intent_token=intent_undo["user_intent_token"]))
    assert undone.get("ok") is True, undone
    assert kinds().count("undo") == 1

    apply_items = [{"video_id": f"v_apply_wire_{i}", "target_shelf": "shelf_alpha"} for i in range(2)]
    _apply_idx, apply_svc, apply_ctx, _clock2 = make_apply_environment(
        tmp_path / "work-apply", items=apply_items)
    apply_svc.event_hook = server._mirror_event
    ctx_client = RequestContext(
        authenticated=True, client_id="client_worker", session_id="s_worker")
    claim = apply_svc.claim_work(ctx_client, {
        "action": "claim", "run_id": "run_apply_01",
        "client_id": "client_worker", "max_items": 2, "lease_seconds": 600,
    })
    assert claim.get("ok") is True, claim
    for work in claim["work"]:
        submit_accepted_result(apply_svc, ctx_client, work)
    prev = apply_svc.preview_apply(apply_ctx, {
        "mode": "preview", "run_id": "run_apply_01",
        "expected_projection_revision": 0,
    })
    assert prev.get("ok") is True, prev
    approve = apply_svc.approve_preview(apply_ctx, {
        "preview_id": prev["preview_id"],
        "delta_hash": prev["delta_hash"],
        "operation_key": "op_apply_wire",
        "expected_projection_revision": 0,
    })
    assert approve.get("ok") is True, approve
    applied = apply_svc.apply_preview(apply_ctx, {
        "mode": "apply",
        "preview_id": prev["preview_id"],
        "expected_projection_revision": 0,
        "delta_hash": prev["delta_hash"],
        "operation_key": "op_apply_wire",
    })
    assert applied.get("ok") is True, applied
    assert kinds().count("apply") == 1

    for kind in ("capture", "source_refresh", "soft_delete", "restore",
                 "hard_purge", "pin", "apply", "undo"):
        assert kinds().count(kind) == 1, (kind, kinds())

    # --- disabled: none of the seams reach the mirror ---
    _enable_settings(monkeypatch, tmp_path, fake, enabled=False)
    fake.events.clear()
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    _index_one(tmp_path, video_id="vid-capture-off")
    server._refresh_source_via_service("src_x")
    server.Handler._handle_memory_delete(handler, {"video_id": video_id})
    # restore may 409 if already deleted; still must not record
    server.Handler._handle_memory_restore(handler, {"video_id": video_id})
    monkeypatch.setattr(server, "_get_index", lambda: _PurgeIdx())
    server._purge_trash()
    apply_svc._emit_mirror_event("apply")
    svc._emit_mirror_event("pin", video_id="vid_pin_wire", shelf_id="shelf_alpha")
    svc._emit_mirror_event("undo")
    server._mirror_event("capture", video_id="nope")
    assert fake.events == []


def test_library_work_default_event_hook_is_noop(tmp_path):
    idx = index_mod.Index.open(tmp_path / "idx.db")
    svc = LibraryWorkService(idx, tmp_path / "library")
    svc._emit_mirror_event("apply", video_id="x")  # must not raise


# ---------------------------------------------------------------------------
# Dashboard panel
# ---------------------------------------------------------------------------

def test_dashboard_library_mirror_panel():
    assert 'id="library-mirror"' in DASHBOARD
    for marker in (
        'id="libraryMirrorStatus"',
        'id="libraryMirrorCounts"',
        'id="libraryMirrorDestination"',
        'id="libraryMirrorScope"',
        'id="libraryMirrorIndexingNotice"',
        'id="libraryMirrorEnable"',
        'id="libraryMirrorDisable"',
        'id="libraryMirrorResync"',
        'id="libraryMirrorPreview"',
        "/library/mirror-intent",
        'op: "enable"',
        'op: "disable"',
        'op: "resync"',
        'op: "status"',
        "Existing third-party indexing",
    ):
        assert marker in DASHBOARD, marker
    assert DASHBOARD.find('id="tab-settings"') < DASHBOARD.find('id="library-mirror"')

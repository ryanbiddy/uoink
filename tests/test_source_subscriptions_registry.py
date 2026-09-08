"""Phase 3 gate S19 (registry parity and adversarial input) plus the consent
receipt semantics of "Consent and enrollment". Contract:
docs/library/PHASE3-CONTRACT-2026-09-07.md.

Payloads run through the direct service and the MCP adapter
(uoink_mcp_tools.sources_call with an injected service); server.py's HTTP
routes call the same adapter, so HTTP parity is one thin layer above this
(Gemini's dashboard/API tests cover the transport itself).

Run: python -m pytest -q tests/test_source_subscriptions_registry.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_subscriptions_fixtures import (  # noqa: E402
    CHANNEL_ID, CHANNEL_URL, Clock, FEED_URL, FakeAdapter, MINUTE_MS, OPERATOR, PLAYLIST_ID,
    PLAYLIST_URL, REGISTRY, SESSION, USER, T0, make_service, mint, open_index, register,
    rows, set_consent, snapshot, status, turn_off, turn_on, vid,
)

import source_subscriptions as ss  # noqa: E402
import uoink_mcp_tools as tools  # noqa: E402


@pytest.fixture
def env(tmp_path):
    idx = open_index(tmp_path)
    clock = Clock()
    service = make_service(idx, clock=clock, adapter=FakeAdapter([snapshot([vid(1)])]))
    tools.set_sources_service(service)
    try:
        yield idx, service, clock
    finally:
        tools.set_sources_service(None)
        idx.close()


def _code(result):
    return (result.get("error") or {}).get("code")


# ---- Schemas are the contract's, on every transport --------------------------
def test_tool_manifest_matches_contract_document():
    doc = (Path(__file__).resolve().parents[1] / "docs" / "library"
           / "PHASE3-CONTRACT-2026-09-07.md").read_text(encoding="utf-8")
    start = doc.index("```json", doc.index("## Registry and dashboard contract"))
    end = doc.index("```", start + 7)
    frozen = json.loads(doc[start + 7:end])
    assert ss.tool_manifest() == frozen
    for name in ss.TOOL_NAMES:
        assert tools.TOOL_REGISTRY[name].input_schema == ss.TOOL_SCHEMAS[name]
    assert set(ss.TOOL_NAMES) == set(tools.SOURCES_TOOL_NAMES)
    assert ss.CONTRACT_VERSION == tools.SOURCES_CONTRACT_VERSION == "phase3-v1-2026-09-07"


def test_envelope_fields_on_every_success_and_error(env):
    idx, service, clock = env
    ok = service.list_sources(REGISTRY, {})
    assert ok["ok"] is True and ok["schema_version"] == 1
    assert ok["contract_version"] == "phase3-v1-2026-09-07"
    assert ok["sources"] == [] and ok["next_cursor"] is None and ok["as_of_ms"] == T0
    bad = service.source_status(REGISTRY, {"source_id": "src_" + "0" * 64})
    assert bad["ok"] is False and bad["schema_version"] == 1
    assert bad["contract_version"] == "phase3-v1-2026-09-07"
    assert set(bad["error"]) == {"code", "message", "retryable", "details"}
    assert bad["error"]["code"] == "not_found"
    assert _code(tools.sources_call("source_status", {"source_id": "src_" + "0" * 64})) == "not_found"


ADVERSARIAL = [
    ("register_source", {"kind": "podcast_rss", "url": FEED_URL, "actor": "operator"}),
    ("register_source", {"kind": "podcast_rss", "url": FEED_URL, "daily_cap": 100}),
    ("register_source", {"kind": "podcast_rss", "url": FEED_URL, "poll_interval_min": 5}),
    ("register_source", {"kind": "podcast_rss", "url": FEED_URL, "poll_interval_min": "60"}),
    ("register_source", {"kind": "podcast_rss", "url": FEED_URL, "poll_interval_min": True}),
    ("register_source", {"kind": "podcast_rss", "url": FEED_URL, "poll_interval_min": 60.0}),
    ("register_source", {"kind": "tiktok", "url": FEED_URL}),
    ("register_source", {"kind": "podcast_rss"}),
    ("register_source", {"kind": "podcast_rss", "url": ""}),
    ("register_source", {"kind": "podcast_rss", "url": "x" * 2049}),
    ("register_source", {"kind": "podcast_rss", "url": FEED_URL, "display_name": "n" * 201}),
    ("list_sources", {"limit": 0}),
    ("list_sources", {"limit": 101}),
    ("list_sources", {"include_archived": 1}),
    ("list_sources", {"consent_state": "maybe"}),
    ("list_sources", {"cursor": ""}),
    ("source_status", {"source_id": "src_short"}),
    ("source_status", {"source_id": "SRC_" + "a" * 64}),
    ("source_status", {"source_id": "src_" + "a" * 64, "item_limit": 0}),
    ("source_status", {}),
    ("set_source_consent", {"source_id": "src_" + "a" * 64, "consent_state": "on",
                            "expected_revision": 0, "operation_key": "k", "user_intent_token": "t" * 43}),
    ("set_source_consent", {"source_id": "src_" + "a" * 64, "consent_state": "off",
                            "expected_revision": 0, "expected_cursor_revision": 0,
                            "operation_key": "k", "user_intent_token": "t" * 43}),
    ("set_source_consent", {"source_id": "src_" + "a" * 64, "consent_state": "on",
                            "expected_revision": 0, "expected_cursor_revision": 0,
                            "operation_key": "bad key!", "user_intent_token": "t" * 43}),
    ("set_source_consent", {"source_id": "src_" + "a" * 64, "consent_state": "on",
                            "expected_revision": 0, "expected_cursor_revision": 0,
                            "operation_key": "k", "user_intent_token": "short"}),
    ("set_source_consent", {"source_id": "src_" + "a" * 64, "consent_state": "on",
                            "expected_revision": -1, "expected_cursor_revision": 0,
                            "operation_key": "k", "user_intent_token": "t" * 43}),
    ("set_source_consent", {"source_id": "src_" + "a" * 64, "consent_state": "on",
                            "expected_revision": 0, "expected_cursor_revision": 0,
                            "operation_key": "k", "user_intent_token": "t" * 43, "cap": 99}),
]


@pytest.mark.parametrize("tool,args", ADVERSARIAL)
def test_s19_adversarial_payloads_rejected_identically_on_service_and_mcp(env, tool, args):
    idx, service, clock = env
    direct = getattr(service, tool)(REGISTRY, dict(args))
    via_mcp = tools.sources_call(tool, dict(args))
    assert direct["ok"] is False and via_mcp["ok"] is False
    assert _code(direct) == "validation_error", (tool, args, direct)
    assert _code(via_mcp) == "validation_error", (tool, args, via_mcp)
    assert rows(service, "SELECT COUNT(*) AS n FROM source_subscriptions")[0]["n"] == 0


def test_s19_strict_json_decoder_rejects_duplicates_nan_depth_and_size(env):
    idx, service, clock = env
    assert _code(service.list_sources(REGISTRY, '{"limit": 5, "limit": 6}')) == "validation_error"
    assert _code(service.list_sources(REGISTRY, '{"limit": NaN}')) == "validation_error"
    assert _code(service.list_sources(REGISTRY, '{"limit": Infinity}')) == "validation_error"
    deep = "{" * 20 + "}" * 20
    assert _code(service.list_sources(REGISTRY, '{"cursor": ' + '[' * 17 + ']' * 17 + '}')) == "validation_error"
    assert _code(service.list_sources(REGISTRY, deep.replace("{}", '{"a":1}'))) == "validation_error"
    huge ='{"kind": "podcast_rss", "url": "https://a.example/f", "display_name": "' + "z" * 17000 + '"}'
    assert _code(service.register_source(REGISTRY, huge)) == "validation_error"
    assert _code(service.list_sources(REGISTRY, b'{"limit": 1, "x": "\xff"}')) == "validation_error"
    assert _code(service.list_sources(REGISTRY, [1, 2])) == "validation_error"


MALICIOUS_URLS = [
    ("podcast_rss", "http://127.0.0.1/feed.xml"),
    ("podcast_rss", "http://[::1]/feed.xml"),
    ("podcast_rss", "http://169.254.169.254/latest/meta-data/"),
    ("podcast_rss", "http://10.0.0.5/feed.xml"),
    ("podcast_rss", "http://192.168.1.1/feed.xml"),
    ("podcast_rss", "http://localhost:5179/feed.xml"),
    ("podcast_rss", "https://user:pw@show.example/feed.xml"),
    ("podcast_rss", "https://show.example/feed.xml#frag"),
    ("podcast_rss", "ftp://show.example/feed.xml"),
    ("podcast_rss", "javascript:alert(1)"),
    ("podcast_rss", "file:///etc/passwd"),
    ("podcast_rss", "show.example/feed.xml"),
    ("podcast_rss", "https://show.example/feed\x00.xml"),
    ("podcast_rss", "https://show.example/feed\n.xml"),
    ("youtube_channel", "https://www.youtube.com/@handle"),
    ("youtube_channel", "https://www.youtube.com/user/legacy"),
    ("youtube_channel", "https://www.youtube.com/c/custom"),
    ("youtube_channel", "https://www.youtube.com/channel/UCshort"),
    ("youtube_channel", "https://www.youtube.com/channel/HC" + "a" * 22),
    ("youtube_channel", f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}&channel_id={CHANNEL_ID}"),
    ("youtube_channel", f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}&playlist_id={PLAYLIST_ID}"),
    ("youtube_channel", f"https://evil.example/channel/{CHANNEL_ID}"),
    ("youtube_channel", f"https://www.youtube.com.evil.example/channel/{CHANNEL_ID}"),
    ("youtube_playlist", "https://www.youtube.com/playlist?list=WL"),
    ("youtube_playlist", "https://www.youtube.com/playlist?list=LL"),
    ("youtube_playlist", "https://www.youtube.com/playlist?list=RDabcdef"),
    ("youtube_playlist", f"https://www.youtube.com/playlist?list={PLAYLIST_ID}&list={PLAYLIST_ID}"),
    ("youtube_playlist", "https://www.youtube.com/playlist?list=" + "p" * 201),
    ("youtube_playlist", "https://www.youtube.com/playlist?list=a"),
    ("youtube_playlist", "https://www.youtube.com/playlist?list=bad list"),
    ("youtube_playlist", f"https://www.youtube.com/feeds/videos.xml?playlist_id={PLAYLIST_ID}&channel_id={CHANNEL_ID}"),
    ("youtube_playlist", "https://www.youtube.com/playlist"),
]


@pytest.mark.parametrize("kind,url", MALICIOUS_URLS)
def test_s19_malicious_urls_create_no_row_and_no_network(env, kind, url):
    idx, service, clock = env
    result = service.register_source(REGISTRY, {"kind": kind, "url": url})
    assert result["ok"] is False, (kind, url, result)
    assert _code(result) in ("validation_error", "unsupported_source"), (kind, url, result)
    assert rows(service, "SELECT COUNT(*) AS n FROM source_subscriptions")[0]["n"] == 0
    assert service.adapters["podcast_rss_v1"].calls == []


def test_identity_is_stable_across_display_forms_and_duplicates_are_unchanged(env):
    idx, service, clock = env
    a = register(service, "youtube_channel", CHANNEL_URL, display_name="First", poll_interval_min=120)
    b = service.register_source(REGISTRY, {
        "kind": "youtube_channel",
        "url": f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}",
        "display_name": "Second", "poll_interval_min": 15})
    assert b["created"] is False and b["source"]["source_id"] == a["source_id"]
    assert b["source"]["display_name"] == "First" and b["source"]["poll_interval_min"] == 120
    assert a["source_id"] == ss.source_identity("youtube_channel", CHANNEL_ID)
    assert a["canonical_url"] == CHANNEL_URL and a["adapter"] == "youtube_channel_rss_v1"
    p1 = register(service, "youtube_playlist", PLAYLIST_URL)
    p2 = service.register_source(REGISTRY, {
        "kind": "youtube_playlist", "url": f"https://www.youtube.com/watch?v={vid(1)}&list={PLAYLIST_ID}"})
    assert p2["created"] is False and p2["source"]["source_id"] == p1["source_id"]
    f1 = register(service, "podcast_rss", "HTTPS://Show.Example:443/feed.xml")
    f2 = service.register_source(REGISTRY, {"kind": "podcast_rss", "url": FEED_URL})
    assert f2["created"] is False and f2["source"]["source_id"] == f1["source_id"]
    assert f1["canonical_url"] == FEED_URL
    assert service.adapters["podcast_rss_v1"].calls == []


def test_capture_keys_and_corpus_identity_follow_the_contract():
    assert ss.capture_key_for("youtube_channel", CHANNEL_ID, vid(1)) == f"youtube:{vid(1)}"
    assert ss.capture_key_for("youtube_playlist", PLAYLIST_ID, vid(1)) == f"youtube:{vid(1)}"
    assert ss.capture_key_for("podcast_rss", FEED_URL, "guid-1") == \
        "podcast:" + ss.sha256_text(f"{FEED_URL}\nguid-1")
    assert ss.item_identity("src_x", "e") == "si_" + ss.sha256_text("src_x\ne")
    import podcasts
    assert ss.podcast_corpus_id(FEED_URL, "guid-1") == podcasts._episode_corpus_id(
        {"feed_url": FEED_URL, "guid": "guid-1"})[0]
    assert ss.classification_run_id("youtube:abc") == "ss_" + ss.sha256_text("youtube:abc")


# ---- Consent capability, receipts and idempotency ----------------------------
def test_registry_callers_cannot_mint_or_forge_intent(env):
    idx, service, clock = env
    source = register(service)
    operation = {"source_id": source["source_id"], "consent_state": "on", "expected_revision": 0,
                 "expected_cursor_revision": 0, "operation_key": "on-1"}
    denied = service.mint_consent_intent(REGISTRY, {"operation": operation})
    assert _code(denied) == "user_intent_required"
    no_session = service.mint_consent_intent(
        ss.RequestContext(authenticated=True, local_user_confirmed=True), {"operation": operation})
    assert _code(no_session) == "user_intent_required"
    with_token = service.mint_consent_intent(USER, {"operation": dict(operation, user_intent_token="x" * 43)})
    assert _code(with_token) == "validation_error"
    forged = service.set_source_consent(REGISTRY, dict(operation, user_intent_token="f" * 43))
    assert _code(forged) == "invalid_user_intent"
    assert status(service, source["source_id"])["source"]["consent_state"] == "off"
    assert rows(service, "SELECT COUNT(*) AS n FROM source_consent_receipts")[0]["n"] == 0
    # MCP adapter carries no user authority either.
    via = tools.sources_mint_consent_intent({"operation": operation, "confirmed": True},
                                            session_hash="s" * 64)
    assert via["ok"] is True and via["user_intent_token"]
    unconfirmed = tools.sources_mint_consent_intent({"operation": operation}, session_hash="s" * 64)
    assert _code(unconfirmed) == "user_intent_required"


def test_token_binds_operation_session_source_and_expiry(env):
    idx, service, clock = env
    source = register(service)
    other = register(service, "youtube_playlist", PLAYLIST_URL)
    sid = source["source_id"]
    operation = {"source_id": sid, "consent_state": "on", "expected_revision": 0,
                 "expected_cursor_revision": 0, "operation_key": "on-1"}
    minted = mint(service, operation)
    token = minted["user_intent_token"]
    assert minted["expires_ms"] == T0 + 5 * MINUTE_MS
    assert minted["confirmation"]["daily_cap"] == 10 and minted["confirmation"]["back_catalog_cap"] == 25
    assert "up to 25" in minted["confirmation"]["effect"]
    # Changed request under the same token.
    changed = service.set_source_consent(USER, dict(operation, operation_key="on-2", user_intent_token=token))
    assert _code(changed) == "invalid_user_intent"
    # Cross-session.
    other_session = ss.RequestContext(authenticated=True, session_id="other", local_user_confirmed=True)
    assert _code(service.set_source_consent(other_session, dict(operation, user_intent_token=token))) == "invalid_user_intent"
    # Wrong source with a valid-looking operation.
    assert _code(service.set_source_consent(USER, dict(operation, source_id=other["source_id"],
                                                       user_intent_token=token))) in ("invalid_user_intent", "stale_revision")
    # Expired.
    clock.advance(5 * MINUTE_MS)
    expired = service.set_source_consent(USER, dict(operation, user_intent_token=token))
    assert _code(expired) == "invalid_user_intent"
    assert status(service, sid)["source"]["consent_state"] == "off"
    assert rows(service, "SELECT COUNT(*) AS n FROM source_consent_receipts")[0]["n"] == 0
    # A fresh token works and is consumed exactly once.
    token2 = mint(service, operation)["user_intent_token"]
    first = service.set_source_consent(USER, dict(operation, user_intent_token=token2))
    assert first["ok"] and first["changed"] is True
    assert first["before_revision"] == 0 and first["after_revision"] == 1
    assert first["consent_epoch"] == 1 and first["boundary"] == "initial"
    assert first["released_reservations"] == 0 and first["in_flight"] == []
    assert first["recorded_at_ms"] == clock.now
    replay = service.set_source_consent(USER, dict(operation, user_intent_token=token2))
    assert replay == first, "identical retry returns the stored receipt"
    clock.advance(10 * MINUTE_MS)
    assert service.set_source_consent(USER, dict(operation, user_intent_token=token2)) == first
    conflict_args = {k: v for k, v in operation.items() if k != "expected_cursor_revision"}
    conflict = service.set_source_consent(USER, dict(conflict_args, consent_state="off", user_intent_token=token2))
    assert _code(conflict) == "idempotency_conflict"
    reuse = service.set_source_consent(USER, dict(operation, operation_key="on-3", expected_revision=1,
                                                  user_intent_token=token2))
    assert _code(reuse) == "invalid_user_intent", "consumed token cannot authorize a new operation"


def test_stale_revision_and_stale_cursor_write_nothing_and_report_current(env):
    idx, service, clock = env
    source = register(service)
    sid = source["source_id"]
    service.detection_pass()  # cursor revision 0 -> 1
    current = status(service, sid)["source"]
    assert current["detection"]["cursor_revision"] == 1
    stale_cursor = {"source_id": sid, "consent_state": "on", "expected_revision": 0,
                    "expected_cursor_revision": 0, "operation_key": "on-1"}
    result = service.mint_consent_intent(USER, {"operation": stale_cursor})
    assert _code(result) == "stale_cursor"
    assert result["error"]["details"] == {"current_revision": 0, "current_cursor_revision": 1}
    good = dict(stale_cursor, expected_cursor_revision=1)
    token = mint(service, good)["user_intent_token"]
    # Revision moves under the token (an unrelated same-state receipt does not
    # move it; archive does). Simulate with a direct revision bump.
    with idx.write_transaction() as conn:
        conn.execute("UPDATE source_subscriptions SET revision=revision+1 WHERE source_id=?", (sid,))
    stale = service.set_source_consent(USER, dict(good, user_intent_token=token))
    assert _code(stale) == "stale_revision"
    assert stale["error"]["details"]["current_revision"] == 1
    assert status(service, sid)["source"]["consent_state"] == "off"
    assert rows(service, "SELECT consumed_by FROM source_user_intents")[0]["consumed_by"] is None
    # Disabling does not depend on cursor freshness.
    with idx.write_transaction() as conn:
        conn.execute("UPDATE source_subscriptions SET revision=0 WHERE source_id=?", (sid,))
    turn_on(service, sid)
    service.detection_pass()
    off = turn_off(service, sid)
    assert off["changed"] is True and off["consent_state"] == "off"


def test_same_state_request_records_no_change_receipt(env):
    idx, service, clock = env
    source = register(service)
    sid = source["source_id"]
    turn_on(service, sid)
    before = rows(service, "SELECT * FROM source_subscriptions WHERE source_id=?", (sid,))[0]
    again = set_consent(service, sid, "on", operation_key="on-again")
    assert again["ok"] and again["changed"] is False
    assert again["before_revision"] == again["after_revision"] == before["revision"]
    assert again["consent_epoch"] == before["consent_epoch"] and again["boundary"] == "initial"
    after = rows(service, "SELECT * FROM source_subscriptions WHERE source_id=?", (sid,))[0]
    assert after == before
    assert rows(service, "SELECT COUNT(*) AS n FROM source_consent_receipts")[0]["n"] == 2


def test_archived_source_refuses_consent_and_reads_stay_side_effect_free(env):
    idx, service, clock = env
    source = register(service)
    sid = source["source_id"]
    archived = service.archive_source(USER, {"source_id": sid})
    assert archived["ok"] and archived["changed"] is True
    operation = {"source_id": sid, "consent_state": "on", "expected_revision": archived["revision"],
                 "expected_cursor_revision": 0, "operation_key": "on-1"}
    assert _code(service.mint_consent_intent(USER, {"operation": operation})) == "source_archived"
    hidden = service.list_sources(REGISTRY, {})
    assert hidden["sources"] == []
    shown = service.list_sources(REGISTRY, {"include_archived": True})
    assert [s["source_id"] for s in shown["sources"]] == [sid]
    snapshot_before = rows(service, "SELECT * FROM source_subscriptions")
    for _ in range(3):
        status(service, sid)
        service.list_sources(REGISTRY, {"include_archived": True})
    assert rows(service, "SELECT * FROM source_subscriptions") == snapshot_before
    assert service.adapters["podcast_rss_v1"].calls == []


def test_keyset_pagination_binds_cursor_to_filters_and_source(env):
    idx, service, clock = env
    ids = []
    for i in range(5):
        ids.append(register(service, "youtube_channel",
                            f"https://www.youtube.com/channel/UC{i:022d}")["source_id"])
    page1 = service.list_sources(REGISTRY, {"limit": 2})
    assert [s["source_id"] for s in page1["sources"]] == sorted(ids)[:2]
    assert page1["next_cursor"]
    page2 = service.list_sources(REGISTRY, {"limit": 2, "cursor": page1["next_cursor"]})
    assert [s["source_id"] for s in page2["sources"]] == sorted(ids)[2:4]
    page3 = service.list_sources(REGISTRY, {"limit": 2, "cursor": page2["next_cursor"]})
    assert [s["source_id"] for s in page3["sources"]] == sorted(ids)[4:]
    assert page3["next_cursor"] is None
    foreign = service.list_sources(REGISTRY, {"limit": 2, "cursor": page1["next_cursor"],
                                              "kind": "podcast_rss"})
    assert _code(foreign) == "invalid_cursor"
    assert _code(service.list_sources(REGISTRY, {"cursor": "not-a-cursor"})) == "invalid_cursor"
    assert _code(service.list_sources(REGISTRY, {"cursor": "eyJ2IjoxfQ"})) == "invalid_cursor"
    # Item pages: (first_seen_ms, item_id) keyset bound to the source.
    sid = sorted(ids)[0]
    with idx.write_transaction() as conn:
        for n in range(4):
            conn.execute(
                "INSERT INTO source_items (item_id, source_id, entry_id, capture_key, first_seen_ms, "
                "last_seen_ms, first_scan_revision, metadata_json) VALUES (?,?,?,?,?,?,1,'{}')",
                (f"si_{n:064d}", sid, vid(n), f"youtube:{vid(n)}", T0 + (n // 2), T0))
    first = status(service, sid, item_limit=3)
    assert len(first["items"]) == 3 and first["next_item_cursor"]
    second = status(service, sid, item_cursor=first["next_item_cursor"], item_limit=3)
    assert len(second["items"]) == 1 and second["next_item_cursor"] is None
    seen = [i["item_id"] for i in first["items"]] + [i["item_id"] for i in second["items"]]
    assert seen == sorted(seen, key=lambda i: (T0 + (int(i[3:]) // 2), i))
    stolen = service.source_status(REGISTRY, {"source_id": sorted(ids)[1],
                                              "item_cursor": first["next_item_cursor"]})
    assert _code(stolen) == "invalid_cursor"


def test_item_records_never_leak_tokens_or_paths(env):
    idx, service, clock = env
    source = register(service)
    sid = source["source_id"]
    turn_on(service, sid)
    service.detection_pass()
    claim = service.claim_start(sid)
    assert claim["outcome"] == "reserved"
    result = status(service, sid)
    blob = json.dumps(result)
    assert claim["owner_token"] not in blob
    assert "owner_instance" not in blob and "metadata_json" not in blob
    assert result["in_flight"][0]["start_id"] == claim["start_id"]
    assert result["in_flight"][0]["start_state"] == "reserved"
    item = result["items"][0]
    for key in ("item_id", "entry_id", "title", "canonical_url", "eligibility", "capture_state",
                "blocked_reason", "actual_attempts", "retry_at_ms", "start_id", "charged_utc_day",
                "video_id", "committed_at_ms", "classification"):
        assert key in item
    assert item["classification"] == {"state": "not_captured", "work_id": None}
    assert item["charged_utc_day"] is None


def test_mcp_registry_entries_route_to_the_same_service(env):
    idx, service, clock = env
    created = tools.call_tool("register_source", {"kind": "youtube_channel", "url": CHANNEL_URL})
    assert created["ok"] is True and created["created"] is True
    listed = tools.call_tool("list_sources", {})
    assert [s["source_id"] for s in listed["sources"]] == [created["source"]["source_id"]]
    assert tools.call_tool("source_status", {"source_id": created["source"]["source_id"]})["ok"]
    assert _code(tools.call_tool("list_sources", {"limit": "5"})) == "validation_error"
    denied = tools.call_tool("set_source_consent", {
        "source_id": created["source"]["source_id"], "consent_state": "on", "expected_revision": 0,
        "expected_cursor_revision": 0, "operation_key": "k", "user_intent_token": "t" * 43})
    assert _code(denied) == "invalid_user_intent"
    saved_backend = tools._backend
    tools.set_sources_service(None)
    try:
        tools.bind_backend(type("B", (), {"_source_service": staticmethod(lambda: None),
                                          "_library_session_hash": staticmethod(lambda: "s" * 64)})())
        assert _code(tools.sources_call("list_sources", {})) == "service_unavailable"
    finally:
        tools._backend = saved_backend

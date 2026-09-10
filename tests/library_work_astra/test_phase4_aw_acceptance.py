"""AW acceptance regressions against phase4-v1; no models, network or listeners.

These assert the contract, so unresolved candidate defects intentionally fail.
Run with the isolated profile documented in PHASE4-ACCEPTANCE-2026-09-08.md.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

import library_briefs as briefs
import library_cards
import library_mirror as mirror
import library_prompts
import library_resources as resources
from tests.phase4_fixtures import (
    MockClock, build_test_card, make_disposable_index, parse_fenced_document,
    seed_shelf, seed_yoink_item,
)


@pytest.fixture
def env(tmp_path_factory):
    # Short names keep both final and unique temp paths below the mirror's cap
    # even in the control room's deeply nested dedicated worktree.
    root = tmp_path_factory.mktemp("a")
    idx = make_disposable_index(root)
    clock = MockClock(start_wall=1788868800.0)  # 2026-09-08 12:00 UTC
    for vid in ("a", "b"):
        seed_yoink_item(
            idx, root, video_id=vid, slug=vid, title=f"Source {vid}",
            corpus_text=f"Original corpus {vid}.",
            clips=[{"text": f"Original evidence {vid}.", "start": 0, "end": 10}],
        )
    reader = resources.LibraryReader(
        idx, data_root=root / "d", clock=clock.monotonic, wall_clock=clock.wall)
    store = briefs.BriefStore.for_reader(reader)
    vault = root / "v"
    vault.mkdir()
    consent = mirror.MirrorConsent(str(vault), mirror.SCOPE_ALL, (), 1, "aw-volume")
    delivery = mirror.Mirror(
        idx, reader, store, data_root=root / "d", consent=consent,
        enabled=True, clock=clock.monotonic, wall_clock=clock.wall)
    obj = SimpleNamespace(root=root, idx=idx, clock=clock, reader=reader,
                          store=store, vault=vault, mirror=delivery)
    yield obj
    idx.close()


def item_file(env, vid="a"):
    return env.vault / mirror.MIRROR_ROOT / mirror.item_relpath(vid)


def export(env, *ids):
    for vid in ids or ("a",):
        env.mirror.on_committed_event("capture", video_id=vid)
    result = env.mirror.resync()
    assert result["ok"], result
    for vid in ids or ("a",):
        assert item_file(env, vid).is_file(), result


def mutate_clip(env, vid="a"):
    with env.idx._lock:
        env.idx._conn.execute("UPDATE clips SET text=? WHERE video_id=?",
                              (f"Changed evidence {vid}.", vid))
        env.idx._conn.commit()


def delete_item(env, vid="a"):
    with env.idx._lock:
        env.idx._conn.execute("UPDATE yoinks SET deleted_at=? WHERE video_id=?",
                              ("2026-09-08T12:00:00", vid))
        env.idx._conn.commit()


def publication_args(env, *, document="Original evidence b.", submission_key="aw-brief"):
    packet = env.store.prepare_input("2026-09-08", "aw-run")
    entry = next(e for e in packet["cards"] if e["item_id"] == "b")
    quote = entry["card"]["excerpts"][0]
    citation = dict(item_id="b", source_revision=entry["source_revision"],
                    card_hash=entry["card_hash"], excerpt_id=quote["excerpt_id"],
                    quote=quote["text"], evidence_kind=quote["evidence_kind"],
                    start=quote["start"], end=quote["end"])
    return dict(
        job_key=packet["job_key"], input_hash=packet["input_hash"], input_packet=packet,
        submission_key=submission_key, document=document, citations=[citation],
        usage=None)


def publish(env, **kwargs):
    return env.store.publish(**publication_args(env, **kwargs), client_identity="aw-fixture")


def test_baseline_owned_export_and_brief_are_real(env):
    export(env)
    assert "Original evidence a." in item_file(env).read_text(encoding="utf-8")
    receipt = publish(env)
    assert "Original evidence b." in env.store.read(receipt["date"], receipt["brief_hash"])["contents"][0]["text"]


def test_d1_real_index_lock_obeys_service_deadline(env):
    reader = resources.LibraryReader(env.idx, data_root=env.root / "d")
    held = threading.Event()
    release = threading.Event()

    def holder():
        with env.idx._lock:
            held.set()
            release.wait(2.4)

    thread = threading.Thread(target=holder)
    thread.start()
    assert held.wait(1)
    started = time.monotonic()
    try:
        with pytest.raises(resources.ResourceError) as error:
            reader.get_item(video_id="a")
        elapsed = time.monotonic() - started
    finally:
        release.set()
        thread.join(3)
    assert error.value.code == "deadline_exceeded"
    assert elapsed < 2.2, f"2 s deadline only detected after {elapsed:.3f} s blocked read"


def test_card_refuses_deletion_during_build(env, monkeypatch):
    uri = resources.card_uri("a", build_test_card(env.idx, "a"))
    assert env.reader.read(uri)["contents"]
    original = env.reader._build_card

    def changed(item, clips):
        result = original(item, clips)
        delete_item(env)
        return result

    monkeypatch.setattr(env.reader, "_build_card", changed)
    with pytest.raises(resources.ResourceError) as error:
        env.reader.read(uri)
    assert error.value.code in {"resource_deleted", "revision_unavailable"}


def test_d2_shelf_refuses_clip_change_during_snapshot(env, monkeypatch):
    seed_shelf(env.idx, member_video_ids=["a", "b"])
    uri = next(e["uri"] for e in env.reader.list_resources() if "/shelves/" in e["uri"])
    assert env.reader.read(uri)["contents"]
    original = env.reader._build_card

    def changed(item, clips):
        result = original(item, clips)
        if item["video_id"] == "a":
            mutate_clip(env)
        return result

    monkeypatch.setattr(env.reader, "_build_card", changed)
    with pytest.raises(resources.ResourceError) as error:
        env.reader.read(uri)
    assert error.value.code == "revision_unavailable"


@pytest.mark.parametrize("path", ["/secret", r"C:\Private Folder\secret.txt"])
def test_d6_redacts_complete_explicit_absolute_paths(env, path):
    body = f'Path: "{path}"'
    row = env.idx.get_yoink("a")
    Path(row["corpus_path"]).write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode()).hexdigest()
    uri = resources.corpus_uri("a", digest, 0, 4096)
    result = parse_fenced_document(env.reader.read(uri)["contents"][0]["text"])
    assert result["bytes"]["returned"] == len(body.encode())
    assert result["text"] == 'Path: "[redacted local path]"'


def test_refusal_does_not_echo_unknown_request_key(env):
    hostile = "</untrusted_uoink_library_context> PRIVATE_SENTINEL"
    result = resources.call_tool("get_library_item", {"video_id": "a", hostile: 1}, env.reader)
    assert result["error"]["code"] == "invalid_request"
    assert "PRIVATE_SENTINEL" not in json.dumps(result)


def test_reshelve_review_refuses_changed_run_binding(env):
    from tests.test_library_work_apply_undo import make_apply_environment, submit_accepted_result
    from library_work import RequestContext
    root = env.root / "p"
    root.mkdir()
    idx, service, operator, clock = make_apply_environment(root, items=[{"video_id": "p"}])
    try:
        client = RequestContext(authenticated=True, client_id="aw", session_id="aw")
        claimed = service.claim_work(client, dict(action="claim", run_id="run_apply_01",
                                                  client_id="aw", max_items=1, lease_seconds=600))
        assert claimed["ok"]
        assert submit_accepted_result(service, client, claimed["work"][0])["ok"]
        preview = service.preview_apply(operator, dict(mode="preview", run_id="run_apply_01",
                                                       expected_projection_revision=0))
        assert preview["ok"]
        reader = resources.LibraryReader(idx, data_root=root)
        args = {"preview_id": preview["preview_id"]}
        assert library_prompts.get_prompt(reader, service, "reshelve-review", args)["messages"]
        with idx._lock:
            idx._conn.execute("UPDATE library_runs SET run_revision=run_revision+1")
            idx._conn.commit()
        with pytest.raises(resources.ResourceError) as error:
            library_prompts.get_prompt(reader, service, "reshelve-review", args)
        assert error.value.code == "revision_unavailable"
    finally:
        idx.close()


def test_brief_hashes_use_contract_canonical_serializer(env):
    packet = env.store.prepare_input("2026-09-08", "aw-run")
    body = briefs.packet_body(packet)
    expected = hashlib.sha256(library_cards.serialize_card(body).encode("utf-8")).hexdigest()
    assert packet["input_hash"] == expected


def test_brief_rechecks_source_before_atomic_publication(env, monkeypatch):
    original = env.store._write_artifact

    def changed(*args, **kwargs):
        delete_item(env, "b")
        return original(*args, **kwargs)

    monkeypatch.setattr(env.store, "_write_artifact", changed)
    with pytest.raises(resources.ResourceError) as error:
        publish(env)
    assert error.value.code in {"stale_brief", "resource_deleted", "revision_unavailable"}


def test_brief_read_invalidates_changed_projection(env):
    receipt = publish(env)
    assert env.store.read(receipt["date"], receipt["brief_hash"])["ok"]
    with env.idx._lock:
        env.idx._conn.execute("UPDATE library_meta SET projection_revision=projection_revision+1")
        env.idx._conn.commit()
    with pytest.raises(resources.ResourceError) as error:
        env.store.read(receipt["date"], receipt["brief_hash"])
    assert error.value.code in {"stale_brief", "revision_unavailable"}


def test_server_hard_purge_cleans_briefs_when_mirror_disabled(env, monkeypatch):
    import server
    receipt = publish(env)
    artifact = env.store.root / receipt["date"] / receipt["brief_hash"]
    monkeypatch.setattr(server, "DATA_ROOT", env.root / "d")
    monkeypatch.setattr(server, "_get_index", lambda: env.idx)
    monkeypatch.setattr(server, "_read_settings", lambda: {"library_mirror_enabled": False})
    monkeypatch.setattr(server, "_trash_folder_for", lambda row: env.root / "absent-trash")
    monkeypatch.setattr(env.idx, "prune_trash", lambda now: ["b"])
    delete_item(env, "b")
    assert server._purge_trash() == 1
    assert env.idx.get_yoink("b") is None
    assert not artifact.exists(), "hard purge left service-owned document and input packet"


def test_brief_tool_publication_emits_committed_mirror_event(env, monkeypatch):
    import server
    events = []
    monkeypatch.setattr(server, "DATA_ROOT", env.root / "d")
    monkeypatch.setattr(server, "_get_existing_index", lambda: env.idx)
    monkeypatch.setattr(resources, "make_reader", lambda backend: env.reader)
    monkeypatch.setattr(server, "_read_settings", lambda: {"library_mirror_enabled": True})
    monkeypatch.setattr(server, "_mirror_event", lambda kind, **kw: events.append((kind, kw)))
    result = resources.dispatch_tool("publish_library_brief", publication_args(env), server)
    assert result["ok"], result
    assert (env.store.root / result["date"] / result["brief_hash"] / "document.md").exists()
    assert events == [("brief_published", {"brief_hash": result["brief_hash"]})]


def test_resync_rebuilds_from_current_sources_without_prior_events(env):
    assert env.mirror.preview(str(env.vault), mirror.SCOPE_ALL)["counts"]["items"] == 2
    result = env.mirror.resync()
    assert item_file(env).exists() and item_file(env, "b").exists(), result


@pytest.mark.parametrize("event", ["source_refresh", "apply", "undo"])
def test_bulk_wiring_events_schedule_current_derivatives(env, event):
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event(event)  # Exactly the current server/service seam.
    env.mirror.resync()
    assert "Changed evidence a." in item_file(env).read_text(encoding="utf-8")


def test_scope_narrowing_cleans_previously_exported_items(env):
    export(env, "a", "b")
    env.mirror.consent = replace(env.mirror.consent, scope="allowlist", allowlist=("a",))
    env.mirror.resync()
    assert not item_file(env, "b").exists()
    assert "Source b" not in (env.vault / "Uoink/Library.md").read_text(encoding="utf-8")


def test_real_brief_dependencies_enforce_mirror_allowlist(env):
    receipt = publish(env)
    env.mirror.consent = replace(env.mirror.consent, scope="allowlist", allowlist=("a",))
    env.mirror.on_committed_event("brief_published", brief_hash=receipt["brief_hash"])
    env.mirror.resync()
    exported = env.vault / "Uoink" / mirror.brief_relpath(receipt["date"], receipt["brief_hash"])
    assert not exported.exists(), "brief citing excluded item b was exported"


def test_real_brief_mirror_is_removed_when_dependency_deleted(env):
    receipt = publish(env)
    env.mirror.on_committed_event("brief_published", brief_hash=receipt["brief_hash"])
    env.mirror.resync()
    exported = env.vault / "Uoink" / mirror.brief_relpath(receipt["date"], receipt["brief_hash"])
    assert exported.exists()
    delete_item(env, "b")
    env.mirror.tombstone("b")
    assert not exported.exists(), "old generated brief still contains deleted source text"


def test_disabled_mirror_retains_pending_deletes_and_cleans_owned_files(env):
    export(env)
    delete_item(env)
    env.mirror.on_committed_event("hard_purge", video_id="a")
    assert env.mirror.status()["deletion_pending"] > 0
    env.mirror.enabled = False
    status = env.mirror.status()
    env.mirror.resync()
    assert status["deletion_pending"] > 0
    assert not item_file(env).exists()


def test_missing_manifest_stops_replacement_for_reconciliation(env):
    export(env)
    before = item_file(env).read_bytes()
    (env.vault / "Uoink/.uoink-mirror/manifest.json").unlink()
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    result = env.mirror.resync()
    assert item_file(env).read_bytes() == before, result
    assert result.get("reconciliation") or not result["ok"]


def test_unowned_temp_named_like_item_is_preserved(env):
    export(env)
    personal = item_file(env).with_suffix(".tmp")
    personal.write_bytes(b"USER OWNED TEMP")
    env.mirror.resync()
    assert personal.exists() and personal.read_bytes() == b"USER OWNED TEMP"


def test_purge_removes_intent_owned_actual_temp_name(env, monkeypatch):
    export(env)
    target = item_file(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    original_replace, original_unlink = env.mirror._io_replace, env.mirror._io_unlink

    def fail_replace(src, dst):
        if Path(dst) == target:
            raise OSError("fixture interrupted replace")
        return original_replace(src, dst)

    def fail_temp_cleanup(path, *args, **kwargs):
        if path.parent == target.parent and path.name.startswith(target.name + "."):
            raise OSError("fixture interrupted cleanup")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(env.mirror, "_io_replace", fail_replace)
        patch.setattr(env.mirror, "_io_unlink", fail_temp_cleanup)
        env.mirror.resync()
    orphans = list(target.parent.glob(target.name + ".*.tmp"))
    assert len(orphans) == 1
    orphan = orphans[0]
    intent = env.mirror._load_intents()[mirror.item_key("a")]
    assert hashlib.sha256(orphan.read_bytes()).hexdigest() == intent["content_hash"]
    delete_item(env)
    env.mirror.purge("a")
    assert not orphan.exists(), "writer creates 24 hex temp suffix; cleanup only recognizes 12"


def test_mirror_rechecks_authoritative_deletion_before_replace(env, monkeypatch):
    env.mirror.on_committed_event("capture", video_id="a")
    original = env.mirror._atomic_vault

    def changed(dest, data, root, *, recheck):
        if dest == item_file(env):
            delete_item(env)
        return original(dest, data, root, recheck=recheck)

    monkeypatch.setattr(env.mirror, "_atomic_vault", changed)
    env.mirror.resync()
    target = item_file(env)
    assert not target.exists() or b"Original evidence a." not in target.read_bytes()


def test_timed_out_vault_worker_cannot_publish_after_return(env, monkeypatch):
    env.mirror._clock = time.monotonic
    env.mirror.on_committed_event("capture", video_id="a")
    original = env.mirror._atomic_vault
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_work = env.mirror._vault_work

    def complete_work(plan):
        try:
            return original_work(plan)
        finally:
            finished.set()

    def blocked(dest, data, root, *, recheck):
        if dest != item_file(env):
            return original(dest, data, root, recheck=recheck)
        entered.set()
        assert release.wait(3)
        return original(dest, data, root, recheck=recheck)

    monkeypatch.setattr(env.mirror, "_atomic_vault", blocked)
    monkeypatch.setattr(env.mirror, "_vault_work", complete_work)
    try:
        result = env.mirror.resync(budget_s=0.05)
        assert entered.is_set()
        assert result["ok"] is False
    finally:
        release.set()
        assert finished.wait(3)
    assert not item_file(env).exists(), "abandoned daemon wrote after timeout and lock release"


def test_manifest_failure_keeps_recovery_intent_and_no_success(env, monkeypatch):
    env.mirror.on_committed_event("capture", video_id="a")
    original = env.mirror._atomic_vault

    def fail_manifest(dest, data, root, *, recheck):
        if dest.name == "manifest.json":
            raise OSError("fixture manifest failure")
        return original(dest, data, root, recheck=recheck)

    monkeypatch.setattr(env.mirror, "_atomic_vault", fail_manifest)
    result = env.mirror.resync()
    assert result.get("synced", 0) == 0, result
    assert env.mirror._intent_path(mirror.item_key("a")).exists()


def test_missing_volume_marker_is_not_adopted_after_prior_sync(env):
    export(env)
    # Simulate unplugging this fixture volume and replacing it with another.
    env.vault.rename(env.root / "old-vault")
    env.vault.mkdir()
    env.mirror.on_committed_event("source_refresh", video_id="a")
    result = env.mirror.resync()
    assert not result["ok"] and not item_file(env).exists(), result


def test_shelf_links_resolve_to_exported_item_files(env):
    seed_shelf(env.idx, member_video_ids=["a"])
    export(env)
    env.mirror.on_committed_event("apply", shelf_id="shelf-test-01")
    env.mirror.resync()
    shelf = env.vault / "Uoink" / mirror.shelf_relpath("shelf-test-01")
    text = shelf.read_text(encoding="utf-8")
    expected = "../" + mirror.item_relpath("a")
    assert f"]({expected})" in text
    assert (shelf.parent / expected).is_file()


def test_generated_index_escapes_raw_identity_markup(env):
    hostile = "` <img src=https://example.invalid/aw-sentinel>"
    seed_yoink_item(env.idx, env.root, video_id=hostile, slug="markup", title="Safe title",
                    url="https://example.com/aw", corpus_text="Safe corpus",
                    clips=[{"text": "Safe quote", "source_deep_link": "https://example.com/aw"}])
    export(env, hostile)
    index = (env.vault / "Uoink/Library.md").read_text(encoding="utf-8")
    assert "<img" not in index


def test_mirror_preserves_user_edit_between_hash_and_replace(env, monkeypatch):
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    original = env.mirror._atomic_vault
    personal = b"USER EDIT DURING REPLACEMENT"

    def user_edit(dest, data, root, *, recheck):
        if dest == item_file(env):
            dest.write_bytes(personal)
        return original(dest, data, root, recheck=recheck)

    monkeypatch.setattr(env.mirror, "_atomic_vault", user_edit)
    env.mirror.resync()
    assert item_file(env).read_bytes() == personal


def test_destination_lock_is_shared_across_local_ledgers(env):
    other = mirror.Mirror(env.idx, env.reader, env.store, data_root=env.root / "other",
                          consent=env.mirror.consent, enabled=True)
    with env.mirror._exclusive(timeout=0.05):
        with pytest.raises(mirror._LockTimeout):
            with other._exclusive(timeout=0.05):
                pass

"""AW-2 contract regressions; disposable storage only, no client/model/listener.

These are acceptance assertions, not xfails. See PHASE4-ACCEPTANCE-2-2026-09-08.md
for the isolated profile and short temporary-path runner.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest

import library_briefs as briefs
import library_mirror as mirror
import library_prompts
import library_resources as resources
from tests.library_work_astra.test_phase4_aw_acceptance import (
    env, delete_item, export, item_file, mutate_clip, publication_args, publish,
)
from tests.phase4_fixtures import parse_fenced_document, seed_shelf


def test_d01_backend_open_lock_obeys_deadline(env, monkeypatch):
    import server
    monkeypatch.setattr(server, "_index_singleton", env.idx)
    held, release = threading.Event(), threading.Event()

    def holder():
        with server._index_open_lock:
            held.set()
            release.wait(2.4)

    thread = threading.Thread(target=holder)
    thread.start()
    assert held.wait(1)
    reader = resources.make_reader(server, guard=resources.ReadGuard())
    started = time.monotonic()
    try:
        with pytest.raises(resources.ResourceError) as error:
            reader.get_item(video_id="a")
        elapsed = time.monotonic() - started
    finally:
        release.set()
        thread.join(3)
    assert error.value.code == "deadline_exceeded"
    assert elapsed < 2.2, f"backend open lock returned after {elapsed:.3f}s"


def test_d01_sqlite_busy_wait_obeys_deadline(env):
    env.idx._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert env.idx._conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
    held, release = threading.Event(), threading.Event()

    def holder():
        connection = sqlite3.connect(env.root / "index.db")
        try:
            connection.execute("BEGIN EXCLUSIVE")
            held.set()
            release.wait(2.4)
        finally:
            connection.rollback()
            connection.close()

    thread = threading.Thread(target=holder)
    thread.start()
    assert held.wait(1)
    reader = resources.LibraryReader(env.idx, data_root=env.root / "d")
    started = time.monotonic()
    try:
        with pytest.raises(resources.ResourceError):
            reader.get_item(video_id="a")
        elapsed = time.monotonic() - started
    finally:
        release.set()
        thread.join(3)
    assert elapsed < 2.2, f"SQLite busy wait returned after {elapsed:.3f}s"


def test_d02_get_item_rechecks_after_corpus_admission(env, monkeypatch):
    original = env.reader._admit_corpus

    def changed(op, item):
        result = original(op, item)
        delete_item(env, item["video_id"])
        return result

    monkeypatch.setattr(env.reader, "_admit_corpus", changed)
    with pytest.raises(resources.ResourceError) as error:
        env.reader.get_item(video_id="a")
    assert error.value.code in {"resource_deleted", "revision_unavailable"}


@pytest.mark.parametrize("path", ["/7secret", "/私密", "/Private O'Brien/secret.txt"])
def test_d03_redacts_complete_explicit_path(env, path):
    body = f'Path: "{path}"'
    Path(env.idx.get_yoink("a")["corpus_path"]).write_text(body, encoding="utf-8")
    uri = resources.corpus_uri("a", hashlib.sha256(body.encode()).hexdigest(), 0, 4096)
    result = parse_fenced_document(env.reader.read(uri)["contents"][0]["text"])
    assert result["bytes"]["returned"] == len(body.encode())
    assert result["text"] == 'Path: "[redacted local path]"'


@pytest.fixture
def work_env(env):
    from tests.test_library_work_apply_undo import make_apply_environment
    root = env.root / "p"
    idx, service, operator, clock = make_apply_environment(root, items=[{"video_id": "b"}])
    reader = resources.LibraryReader(idx, data_root=root / "d", clock=env.clock.monotonic,
                                     wall_clock=env.clock.wall)
    store = briefs.BriefStore.for_reader(reader, service)
    yield SimpleNamespace(root=root, idx=idx, service=service, operator=operator,
                          reader=reader, store=store)
    idx.close()


def ready_preview(work_env):
    from library_work import RequestContext
    from tests.test_library_work_apply_undo import submit_accepted_result
    client = RequestContext(authenticated=True, client_id="aw2", session_id="aw2")
    claimed = work_env.service.claim_work(client, dict(action="claim", run_id="run_apply_01",
                                                      client_id="aw2", max_items=1, lease_seconds=600))
    assert claimed["ok"]
    assert submit_accepted_result(work_env.service, client, claimed["work"][0])["ok"]
    preview = work_env.service.preview_apply(work_env.operator, dict(mode="preview",
                 run_id="run_apply_01", expected_projection_revision=0))
    assert preview["ok"]
    return {"preview_id": preview["preview_id"]}


def test_d04_preview_refusal_does_not_disclose_exception(work_env, monkeypatch):
    args = ready_preview(work_env)
    assert library_prompts.get_prompt(work_env.reader, work_env.service, "reshelve-review", args)

    def unavailable(*args):
        raise OSError("PRIVATE_AW2_SENTINEL C:\\private\\source.txt")

    monkeypatch.setattr(work_env.service, "_recheck_preview", unavailable)
    with pytest.raises(resources.ResourceError) as error:
        library_prompts.get_prompt(work_env.reader, work_env.service, "reshelve-review", args)
    assert "PRIVATE_AW2_SENTINEL" not in json.dumps(error.value.envelope())


def test_d05_preview_recheck_is_pure_and_checks_evidence(work_env):
    args = ready_preview(work_env)
    before = work_env.idx._conn.total_changes
    assert library_prompts.get_prompt(work_env.reader, work_env.service, "reshelve-review", args)
    assert work_env.idx._conn.total_changes == before
    with work_env.idx.write_transaction() as conn:
        conn.execute("UPDATE clips SET text='changed source'")
    before = work_env.idx._conn.total_changes
    with pytest.raises(resources.ResourceError) as error:
        library_prompts.get_prompt(work_env.reader, work_env.service, "reshelve-review", args)
    assert error.value.code == "revision_unavailable"
    assert work_env.idx._conn.total_changes == before


def work_publication_args(work_env):
    args = publication_args(work_env)
    packet = work_env.store.prepare_input("2026-09-08", "run_apply_01")
    args.update(input_packet=packet, input_hash=packet["input_hash"], job_key=packet["job_key"])
    args["document"] = args["citations"][0]["quote"]
    return args


@pytest.mark.parametrize("surface", ["read", "discovery"])
def test_d07_read_and_discovery_recheck_queue(work_env, surface):
    receipt = work_env.store.publish(**work_publication_args(work_env), client_identity="aw2")
    assert work_env.store.read(receipt["date"], receipt["brief_hash"])["ok"]
    with work_env.idx.write_transaction() as conn:
        conn.execute("UPDATE library_work SET priority=priority+1")
    if surface == "read":
        with pytest.raises(resources.ResourceError) as error:
            work_env.store.read(receipt["date"], receipt["brief_hash"])
        assert error.value.code in {"stale_brief", "revision_unavailable"}
    else:
        assert work_env.store.latest_valid(receipt["date"]) is None


def test_d07_publication_rechecks_sampled_metadata(env, monkeypatch):
    original = env.store._write_artifact

    def changed(*args, **kwargs):
        with env.idx.write_transaction() as conn:
            conn.execute("UPDATE yoinks SET yoinked_at='2026-09-07' WHERE video_id='a'")
        return original(*args, **kwargs)

    monkeypatch.setattr(env.store, "_write_artifact", changed)
    with pytest.raises(resources.ResourceError) as error:
        publish(env)
    assert error.value.code in {"stale_brief", "revision_unavailable"}


def test_d07_publication_holds_source_lock_through_replace(env, monkeypatch):
    original = briefs.os.replace
    changed = threading.Event()
    threads = []
    deletion_before_replace = []

    def replace_after_competing_delete(src, dst):
        if Path(src).name.startswith(".tmp-") and Path(dst).parent.name == "2026-09-08":
            def competitor():
                delete_item(env, "b")
                changed.set()
            thread = threading.Thread(target=competitor)
            threads.append(thread)
            thread.start()
            # A source lock held through replacement keeps this writer out.
            changed.wait(0.15)
            deletion_before_replace.append(changed.is_set())
        return original(src, dst)

    monkeypatch.setattr(briefs.os, "replace", replace_after_competing_delete)
    try:
        receipt = publish(env)
    finally:
        for thread in threads:
            thread.join(3)
    assert not (receipt["ok"] and any(deletion_before_replace)), \
        "accepted artifact after source deletion committed between recheck and publication"


def test_d08_failed_store_initialization_retains_purge_retry(env, monkeypatch):
    import server
    receipt = publish(env)
    artifact = env.store.root / receipt["date"] / receipt["brief_hash"]
    monkeypatch.setattr(server, "DATA_ROOT", env.root / "d")
    monkeypatch.setattr(server, "_get_index", lambda: env.idx)
    monkeypatch.setattr(server, "_read_settings", lambda: {"library_mirror_enabled": False})
    monkeypatch.setattr(server, "_trash_folder_for", lambda row: env.root / "absent")
    monkeypatch.setattr(env.idx, "prune_trash", lambda now: ["b"])
    delete_item(env, "b")
    original = briefs.BriefStore

    def unavailable(*args, **kwargs):
        raise OSError("fixture store unavailable")

    monkeypatch.setattr(briefs, "BriefStore", unavailable)
    assert server._purge_trash() == 1
    monkeypatch.setattr(briefs, "BriefStore", original)
    monkeypatch.setattr(env.idx, "prune_trash", lambda now: [])
    server._purge_trash()
    assert not artifact.exists(), "purged identity was lost when BriefStore initialization failed"


def test_d08_interrupted_cleanup_cannot_report_success(env, monkeypatch):
    receipt = publish(env)
    final = env.store.root / receipt["date"] / receipt["brief_hash"]
    interrupted = final.with_name(".tmp-aw2")
    final.rename(interrupted)
    original = briefs.shutil.rmtree

    def blocked(path, *args, **kwargs):
        if Path(path) == interrupted:
            return  # models ignore_errors=True encountering an undeletable file
        return original(path, *args, **kwargs)

    monkeypatch.setattr(briefs.shutil, "rmtree", blocked)
    with pytest.raises(resources.ResourceError):
        env.store.purge_dependents("b")


def test_d09_resync_repairs_missed_refresh(env):
    export(env)
    mutate_clip(env)
    env.mirror.resync()
    assert "Changed evidence a." in item_file(env).read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", ["shelf", "brief"])
def test_d09_fresh_resync_exports_shelf_and_brief(env, kind):
    seed_shelf(env.idx, member_video_ids=["a"])
    receipt = publish(env)
    env.mirror.resync()
    expected = mirror.shelf_relpath("shelf-test-01") if kind == "shelf" else \
        mirror.brief_relpath(receipt["date"], receipt["brief_hash"])
    assert (env.vault / mirror.MIRROR_ROOT / expected).is_file()


def test_d09_scope_cleanup_keeps_local_brief(env):
    receipt = publish(env)
    export(env, "a", "b")
    env.mirror.consent = replace(env.mirror.consent, scope="allowlist", allowlist=("a",))
    env.mirror.resync()
    assert env.store.read(receipt["date"], receipt["brief_hash"])["ok"]


def test_d10_brief_dependencies_rechecked_at_replace(env, monkeypatch):
    receipt = publish(env)
    target = env.vault / mirror.MIRROR_ROOT / mirror.brief_relpath(receipt["date"], receipt["brief_hash"])
    env.mirror.on_committed_event("brief_published", brief_hash=receipt["brief_hash"])
    original = env.mirror._atomic_vault

    def changed(dest, data, root, *, recheck):
        if dest == target:
            delete_item(env, "b")
        return original(dest, data, root, recheck=recheck)

    monkeypatch.setattr(env.mirror, "_atomic_vault", changed)
    env.mirror.resync()
    assert not target.exists(), "brief exported after its dependency was deleted"


def test_d11_server_delivers_deletion_events_while_disabled(env, monkeypatch):
    import server
    export(env)
    delete_item(env)
    env.mirror.enabled = False
    monkeypatch.setattr(server, "_read_settings", lambda: {"library_mirror_enabled": False})
    monkeypatch.setattr(server, "_library_mirror", lambda: env.mirror)
    server._mirror_event("hard_purge", video_id="a")
    assert env.mirror.status()["deletion_pending"] > 0
    env.mirror.resync()
    assert not item_file(env).exists()


def test_d11_soft_delete_removes_item_source_text(env):
    export(env)
    delete_item(env)
    env.mirror.tombstone("a")
    assert not item_file(env).exists() or b"Original evidence a." not in item_file(env).read_bytes()


@pytest.mark.parametrize("suffix,content", [
    ("stem", b"My Interrupted personal draft"),
    ("unique", b"USER OWNED TEMP"),
])
def test_d12_unowned_temps_are_never_inferred_from_name_or_text(env, suffix, content):
    export(env)
    target = item_file(env)
    personal = target.with_suffix(".tmp") if suffix == "stem" else target.with_name(target.name + "." + "a" * 24 + ".tmp")
    personal.write_bytes(content)
    env.mirror.resync()
    assert personal.is_file() and personal.read_bytes() == content


def test_d13_replace_syscall_cannot_complete_after_timeout(env, monkeypatch):
    env.mirror._clock = time.monotonic
    target = item_file(env)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_replace, original_work = env.mirror._io_replace, env.mirror._vault_work

    def blocked_replace(src, dst):
        if Path(dst) == target:
            entered.set()
            assert release.wait(3)
        return original_replace(src, dst)

    def complete_work(plan):
        try:
            return original_work(plan)
        finally:
            finished.set()

    monkeypatch.setattr(env.mirror, "_io_replace", blocked_replace)
    monkeypatch.setattr(env.mirror, "_vault_work", complete_work)
    try:
        result = env.mirror.resync(budget_s=0.1)
        assert entered.is_set() and result["ok"] is False
        assert not target.exists()
    finally:
        release.set()
        assert finished.wait(3)
    assert not target.exists(), "timed-out worker published after return"


def test_d13_purge_rechecks_user_edit_before_unlink(env, monkeypatch):
    export(env)
    target = item_file(env)
    personal = b"USER EDIT DURING PURGE"
    delete_item(env)
    env.mirror.on_committed_event("hard_purge", video_id="a")
    original = mirror._sha256_file
    injected = []

    def edited_after_hash(path):
        digest = original(path)
        if Path(path) == target and not injected:
            target.write_bytes(personal)
            injected.append(True)
        return digest

    monkeypatch.setattr(mirror, "_sha256_file", edited_after_hash)
    env.mirror.resync()
    assert injected
    assert target.is_file() and target.read_bytes() == personal


def test_d14_index_has_recoverable_intent_on_manifest_failure(env, monkeypatch):
    original = env.mirror._atomic_vault

    def fail_manifest(dest, data, root, *, recheck):
        if dest.name == "manifest.json":
            raise OSError("fixture manifest failure")
        return original(dest, data, root, recheck=recheck)

    monkeypatch.setattr(env.mirror, "_atomic_vault", fail_manifest)
    result = env.mirror.resync()
    assert result.get("synced", 0) == 0
    assert (env.vault / "Uoink/Library.md").exists()
    assert mirror.index_key() in env.mirror._load_intents()


def test_d15_bound_volume_not_readopted_after_ledger_loss(env):
    export(env)
    env.mirror._ledger_path().unlink()
    env.vault.rename(env.root / "old-vault")
    env.vault.mkdir()
    result = env.mirror.resync()
    assert not result["ok"] and not item_file(env).exists()


def test_d16_shelf_title_cannot_introduce_markdown_image(env):
    with env.idx.write_transaction() as conn:
        conn.execute("UPDATE yoinks SET title=? WHERE video_id='a'",
                     ("![AW2](https://example.invalid/image)",))
    seed_shelf(env.idx, member_video_ids=["a"])
    env.mirror.on_committed_event("apply", shelf_id="shelf-test-01")
    env.mirror.resync()
    shelf = env.vault / "Uoink" / mirror.shelf_relpath("shelf-test-01")
    assert "![AW2](https://example.invalid/image)" not in shelf.read_text(encoding="utf-8")

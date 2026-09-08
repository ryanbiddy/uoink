"""AW-3 contract assertions on disposable storage; no model or listener.

Run under the isolated profile in PHASE4-ACCEPTANCE-3-2026-09-08.md.
These intentionally fail on unresolved defects; no xfails or weakened assertions.
"""
from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
import threading
import time

import pytest

import library_briefs as briefs
import library_mirror as mirror
import library_prompts
import library_resources as resources
from tests.library_work_astra.test_phase4_aw_acceptance import (
    env, delete_item, export, item_file, mutate_clip, publish,
)
from tests.phase4_fixtures import parse_fenced_document


def test_d01_cold_database_open_obeys_deadline(env, monkeypatch):
    """A real exclusive SQLite writer blocks Index.open's initial PRAGMA."""
    import server
    env.idx._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert env.idx._conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
    held, release = threading.Event(), threading.Event()

    def writer():
        conn = sqlite3.connect(env.root / "index.db")
        try:
            conn.execute("BEGIN EXCLUSIVE")
            held.set()
            release.wait(2.5)
        finally:
            conn.rollback()
            conn.close()

    thread = threading.Thread(target=writer)
    thread.start()
    assert held.wait(1)
    monkeypatch.setattr(server, "_index_singleton", None)
    monkeypatch.setattr(server, "INDEX_PATH", env.root / "index.db")
    monkeypatch.setattr(server, "DATA_ROOT", env.root / "d")
    reader = resources.make_reader(server, guard=resources.ReadGuard())
    started = time.monotonic()
    try:
        with pytest.raises(resources.ResourceError):
            reader.get_item(video_id="a")
        elapsed = time.monotonic() - started
    finally:
        release.set()
        thread.join(3)
        if server._index_singleton is not None:
            server._index_singleton.close()
    assert elapsed < 2.2, f"cold database open returned after {elapsed:.3f}s"


def test_d02_prompt_rechecks_cards_after_remaining_metadata_reads(env, monkeypatch):
    original = library_prompts._shelf_metadata
    visited = []

    def delete_after_metadata(scope, ids):
        result = original(scope, ids)
        assert "a" in ids
        delete_item(env, "a")
        visited.append(True)
        return result

    monkeypatch.setattr(library_prompts, "_shelf_metadata", delete_after_metadata)
    with pytest.raises(resources.ResourceError) as error:
        library_prompts.get_prompt(env.reader, None, "evidence-brief", {"topic": "Original"})
    assert visited
    assert error.value.code in {"resource_deleted", "revision_unavailable"}


@pytest.mark.parametrize("path", ["/@private/secret.txt", "/-private/secret.txt", "/\U0001f511private/secret.txt"])
def test_d03_punctuation_and_symbol_led_absolute_paths_are_redacted(env, path):
    text = f'Path: "{path}"'
    Path(env.idx.get_yoink("a")["corpus_path"]).write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    uri = resources.corpus_uri("a", digest, 0, 4096)
    body = parse_fenced_document(env.reader.read(uri)["contents"][0]["text"])
    assert body["bytes"]["returned"] == len(text.encode())
    assert body["text"] == 'Path: "[redacted local path]"'
    assert [(s["start_codepoint"], s["end_codepoint"]) for s in body["redactions"]] == [(7, 7 + len(path))]


def test_d07_publication_excludes_an_independent_sqlite_writer(env, monkeypatch):
    original = briefs.os.replace
    committed_before_replace = []

    def replace_after_external_writer(src, dst):
        if Path(src).name.startswith(".tmp-") and Path(dst).parent.name == "2026-09-08":
            committed = threading.Event()

            def writer():
                conn = sqlite3.connect(env.root / "index.db", timeout=0.08)
                try:
                    conn.execute("UPDATE yoinks SET deleted_at='2026-09-08T12:00:00' WHERE video_id='b'")
                    conn.commit()
                    committed.set()
                except sqlite3.OperationalError:
                    conn.rollback()
                finally:
                    conn.close()

            thread = threading.Thread(target=writer)
            thread.start()
            thread.join(1)
            assert not thread.is_alive()
            committed_before_replace.append(committed.is_set())
        return original(src, dst)

    monkeypatch.setattr(briefs.os, "replace", replace_after_external_writer)
    try:
        receipt = publish(env)
    except resources.ResourceError as error:
        assert error.code in {"stale_brief", "revision_unavailable", "resource_deleted"}
        return
    assert committed_before_replace
    assert not (receipt["ok"] and any(committed_before_replace)), \
        "an independent SQLite writer deleted the source before accepted publication"


def test_d08_unreadable_day_retains_local_brief_cleanup_retry(env, monkeypatch):
    import server
    receipt = publish(env)
    day = env.store.root / receipt["date"]
    artifact = day / receipt["brief_hash"]
    monkeypatch.setattr(server, "DATA_ROOT", env.root / "d")
    monkeypatch.setattr(server, "_get_index", lambda: env.idx)
    monkeypatch.setattr(server, "_read_settings", lambda: {"library_mirror_enabled": False})
    monkeypatch.setattr(server, "_trash_folder_for", lambda row: env.root / "absent")
    monkeypatch.setattr(server, "_mirror_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(env.idx, "prune_trash", lambda now: ["b"])
    delete_item(env, "b")
    original = Path.iterdir

    def unavailable(path):
        if path == day:
            raise PermissionError("fixture day unavailable")
        return original(path)

    with monkeypatch.context() as blocked:
        blocked.setattr(Path, "iterdir", unavailable)
        server._purge_trash()
    assert artifact.exists()
    monkeypatch.setattr(env.idx, "prune_trash", lambda now: [])
    server._purge_trash()
    assert not artifact.exists(), "day enumeration failed, but its cleanup retry was cleared"


def test_d09_resync_reexports_explicitly_readmitted_scope_item(env):
    export(env, "a", "b")
    env.mirror.consent = replace(env.mirror.consent, scope="allowlist", allowlist=("a",))
    assert env.mirror.resync()["ok"]
    assert not item_file(env, "b").exists()
    # Models a new, explicit scope choice with the same bound destination.
    env.mirror.consent = replace(env.mirror.consent, allowlist=("a", "b"), consented_at_ms=2)
    result = env.mirror.resync()
    assert item_file(env, "b").is_file(), result
    assert b"Original evidence b." in item_file(env, "b").read_bytes()


def test_d10_brief_source_revision_rechecked_at_replace(env, monkeypatch):
    receipt = publish(env)
    target = env.vault / mirror.MIRROR_ROOT / mirror.brief_relpath(receipt["date"], receipt["brief_hash"])
    original = env.mirror._atomic_vault
    visited = []

    def changed(dest, data, root, *, recheck):
        if dest == target:
            mutate_clip(env, "b")
            visited.append(True)
        return original(dest, data, root, recheck=recheck)

    monkeypatch.setattr(env.mirror, "_atomic_vault", changed)
    env.mirror.resync()
    assert visited
    assert not target.exists(), "brief exported an obsolete quote from a live, changed source"


def interrupted_item_temp(env, monkeypatch):
    """Leave an actually allocated and recorded temp after two I/O failures."""
    export(env)
    mutate_clip(env)
    target = item_file(env)
    original_replace, original_unlink = mirror.os.replace, Path.unlink
    allocated = []

    def failed_replace(src, dst):
        if Path(dst) == target:
            allocated.append(Path(src))
            raise OSError("fixture replacement failure")
        return original_replace(src, dst)

    def failed_unlink(path, *args, **kwargs):
        if path in allocated:
            raise PermissionError("fixture temp cleanup failure")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as blocked:
        blocked.setattr(mirror.os, "replace", failed_replace)
        blocked.setattr(Path, "unlink", failed_unlink)
        env.mirror.resync()
    assert len(allocated) == 1 and allocated[0].is_file()
    intent = env.mirror._load_intents()[mirror.item_key("a")]
    assert env.vault / mirror.MIRROR_ROOT / intent["temp_rel"] == allocated[0]
    return allocated[0]


def test_d12_retry_keeps_ownership_of_interrupted_temp(env, monkeypatch):
    temporary = interrupted_item_temp(env, monkeypatch)
    assert env.mirror.resync()["ok"]
    delete_item(env)
    env.mirror.on_committed_event("hard_purge", video_id="a")
    assert env.mirror.resync()["ok"]
    assert not temporary.exists(), "rewriting the intent orphaned source-bearing temp bytes"


def test_d12_control_hard_purge_removes_unedited_recorded_temp(env, monkeypatch):
    temporary = interrupted_item_temp(env, monkeypatch)
    delete_item(env)
    env.mirror.on_committed_event("hard_purge", video_id="a")
    assert env.mirror.resync()["ok"]
    assert not temporary.exists()


def test_d12_recorded_temp_path_does_not_authorize_deleting_user_replacement(env, monkeypatch):
    temporary = interrupted_item_temp(env, monkeypatch)
    temporary.unlink()
    personal = b"USER REPLACED THIS OLD TEMP PATH"
    temporary.write_bytes(personal)
    delete_item(env)
    env.mirror.on_committed_event("hard_purge", video_id="a")
    env.mirror.resync()
    assert temporary.is_file() and temporary.read_bytes() == personal


@pytest.mark.parametrize("observe", ["visibility", "user_edit"])
def test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes(env, monkeypatch, observe):
    env.mirror._clock = time.monotonic
    target = item_file(env)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_replace, original_work = mirror.os.replace, env.mirror._vault_work
    published = []
    personal = b"USER EDIT AFTER TIMEOUT"

    def blocked_replace(src, dst):
        if Path(dst) == target:
            entered.set()
            assert release.wait(3)
            original_replace(src, dst)
            published.append(target.read_bytes())
            if observe == "user_edit":
                target.write_bytes(personal)
            return
        return original_replace(src, dst)

    def complete_work(plan):
        try:
            return original_work(plan)
        finally:
            finished.set()

    monkeypatch.setattr(mirror.os, "replace", blocked_replace)
    monkeypatch.setattr(env.mirror, "_vault_work", complete_work)
    try:
        result = env.mirror.resync(budget_s=0.1)
        assert entered.is_set() and not result["ok"]
    finally:
        release.set()
        assert finished.wait(3)
    if observe == "visibility":
        assert not published, "source bytes were visible after the timeout, before rollback"
    else:
        assert target.is_file() and target.read_bytes() == personal, "rollback deleted the intervening user edit"


def test_d14_index_intent_matches_exact_published_bytes(env, monkeypatch):
    """A failed item is omitted from the delivered index, but not its intent."""
    target = item_file(env, "b")
    original = env.mirror._atomic_vault

    def fail_item_and_manifest(dest, data, root, *, recheck):
        if dest == target or dest.name == "manifest.json":
            raise OSError("fixture destination unavailable")
        return original(dest, data, root, recheck=recheck)

    monkeypatch.setattr(env.mirror, "_atomic_vault", fail_item_and_manifest)
    result = env.mirror.resync()
    assert not result["ok"] and result["synced"] == 0
    index_file = env.vault / mirror.MIRROR_ROOT / mirror.LIBRARY_INDEX_REL
    assert index_file.exists()
    intent = env.mirror._load_intents()[mirror.index_key()]
    assert hashlib.sha256(index_file.read_bytes()).hexdigest() == intent["content_hash"], \
        "the index intent cannot recover the bytes actually replaced before manifest failure"


def test_d13_timed_out_writer_cannot_erase_a_later_successful_sync(env, monkeypatch):
    env.mirror._clock = time.monotonic
    target = item_file(env)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_replace, original_work = mirror.os.replace, env.mirror._vault_work
    plans = []

    def blocked_first_replace(src, dst):
        if Path(dst) == target and not entered.is_set():
            entered.set()
            assert release.wait(3)
        return original_replace(src, dst)

    def complete_work(plan):
        plans.append(plan)
        try:
            return original_work(plan)
        finally:
            if plan is plans[0]:
                finished.set()

    monkeypatch.setattr(mirror.os, "replace", blocked_first_replace)
    monkeypatch.setattr(env.mirror, "_vault_work", complete_work)
    try:
        first = env.mirror.resync(budget_s=0.1)
        assert entered.is_set() and not first["ok"]
        mutate_clip(env)
        second = env.mirror.resync(budget_s=0.5)
        if second["ok"]:
            assert target.is_file()
            later_bytes = target.read_bytes()
            assert b"Changed evidence a." in later_bytes
        else:
            later_bytes = None  # Keeping exclusion until termination is permitted.
    finally:
        release.set()
        assert finished.wait(3)
    if later_bytes is not None:
        assert target.is_file() and target.read_bytes() == later_bytes, \
            "the abandoned worker erased a subsequently acknowledged write"


def test_d15_failed_destination_binding_persistence_does_not_allow_readoption(env, monkeypatch):
    binding = env.mirror._dest_binding_path()
    original = Path.write_text

    def unavailable(path, *args, **kwargs):
        if path == binding:
            raise PermissionError("fixture binding unavailable")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as blocked:
        blocked.setattr(Path, "write_text", unavailable)
        first = env.mirror.resync()
    if not first["ok"]:
        return  # A failed durable binding must refuse initialization.
    assert item_file(env).exists() and not binding.exists()
    env.mirror._ledger_path().unlink()
    env.vault.rename(env.root / "old-vault")
    env.vault.mkdir()
    result = env.mirror.resync()
    assert not result["ok"] and not item_file(env).exists(), \
        "acknowledged sync had no durable binding; old consent adopted a replacement volume"

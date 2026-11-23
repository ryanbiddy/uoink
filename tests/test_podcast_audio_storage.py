import json
import os
import threading
import time
from pathlib import Path
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import index
import podcasts
import server
from tests.test_library_adapters import Probe, post


@pytest.mark.parametrize("state", ["done", "queued", "missing", "empty", "shared", "outside", "locked", "alias", "absent", "download", "job", "persisted", "show", "show-runtime", "capture", "preparing", "writing"])
def test_cleanup_requires_owned_audio_and_finished_transcript(tmp_path, state, monkeypatch):
    with index.Index.open(tmp_path / "index.db") as idx:
        feed = podcasts.add_feed(idx, "https://feed.example.test/rss")
        podcasts.upsert_episodes(idx, feed["id"], [{"guid": "one", "title": "Episode"}])
        episode = podcasts.list_episodes(idx, feed_id=feed["id"])[0]["id"]
        folder = tmp_path if state == "outside" else tmp_path / "Podcasts" / "show"
        folder.mkdir(exist_ok=True, parents=True)
        audio = folder / "episode.mp3"
        audio.write_bytes(b"audio")
        transcript = audio.with_suffix(".transcript.json")
        if state != "missing":
            segments = [] if state == "empty" else [{"start": 0, "end": 2, "text": "Intro"}]
            transcript.write_text(json.dumps({"segments": segments}), encoding="utf-8")
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET audio_local_path=?, transcript_local_path=?, transcript_status=?",
                       (str(audio), str(transcript), "queued" if state == "queued" else "done"))
        if state in ("shared", "alias"):
            podcasts.upsert_episodes(idx, feed["id"], [{"guid": "two", "title": "Episode"}])
            with idx.write_transaction() as db:
                db.execute("UPDATE podcast_episodes SET audio_local_path=? WHERE id!=?", (str(audio) if state == "shared" else audio.parent.as_posix() + "/./" + audio.name, episode))
        untracked = tmp_path / "Podcasts" / "old-show" / "old-episode.wav"
        untracked.parent.mkdir(parents=True, exist_ok=True)
        untracked.write_bytes(b"old")
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(server, "_jobs", {})
        if state == "job":
            server._jobs["retry"] = dict(kind="podcast_transcribe", state="queued", episode_id=episode)
        if state == "persisted":
            job = dict(id="retry", kind="podcast_transcribe", state="queued",
                       episode_id=episode, audio_path=str(audio))
            idx.upsert_job(server._index_job_row(job))
        if state == "download":
            podcasts.set_episode_status(idx, episode, "queued")
        if state == "show-runtime":
            monkeypatch.setattr(server, "_show_podcast_runs", {episode: {"state": "downloading"}}, raising=False)
            monkeypatch.setattr(server, "_show_podcast_runs_lock", threading.Lock(), raising=False)
        if state == "show":
            monkeypatch.setattr(server, "show_capture", SimpleNamespace(
                _lock=threading.RLock(), list_jobs=lambda root: [
                    dict(kind="podcast_feed", state="running", url=feed["feed_url"],
                         episodes=[dict(state="queued", guid="one")])]), raising=False)
        if state == "absent":
            audio.unlink()
        lock_key = {"capture": server._podcast_capture_key(episode),
                    "preparing": f"podcast-queue:{episode}",
                    "writing": "podcast-audio:" + os.path.normcase(str(audio.resolve()))}.get(state)
        if lock_key:
            lock = server.source_subscriptions.CaptureLock.try_acquire(tmp_path, lock_key)
            assert lock
        request = Probe("GET", "/podcasts/audio-storage?refresh=1")
        request.do_GET()
        deadline = time.monotonic() + 3
        while request.status == 202 and time.monotonic() < deadline:
            time.sleep(.01)
            request = Probe("GET", "/podcasts/audio-storage")
            request.do_GET()
        assert request.status == 200
        usage = request.payload
        assert usage["bytes"] == (3 if state in ("outside", "absent") else 8)
        if state == "locked":
            def locked_file(root, path):
                assert path == audio
                raise PermissionError("File is in use")

            monkeypatch.setattr(podcasts, "_unlink_download", locked_file, raising=False)
        try:
            result = post("/podcasts/audio-storage/delete", {"episode_id": episode, "confirmed": True})
            assert result.status == 200 and result.payload["removed"] == (state == "done")
        finally:
            if lock_key:
                lock.release()
        assert usage["deletable_bytes"] == (5 if state in ("done", "locked") else 0)
        assert audio.exists() == (state not in ("done", "absent"))
        assert untracked.is_file()
        assert transcript.exists() == (state != "missing")
        row = podcasts.get_episode(idx, episode)
        assert bool(row["audio_local_path"]) == (state != "done")
        assert server._default_settings()["keep_podcast_audio"] is True


@pytest.mark.parametrize("location", ["library", "Podcasts", "folder", "audio", "transcript"])
def test_linked_root_but_no_links_below_it(tmp_path, location):
    root = tmp_path / "library"
    folder = root / "Podcasts" / "show"
    folder.mkdir(parents=True)
    audio = folder / "episode.mp3"
    transcript = folder / "episode.transcript.json"
    audio.write_bytes(b"audio")
    transcript.write_text(json.dumps({"segments": [{"start": 0, "end": 1, "text": "test"}]}))
    link = {"library": root, "Podcasts": folder.parent, "folder": folder, "audio": audio, "transcript": transcript}[location]
    target = tmp_path / "target"
    link.rename(target)
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError:
        if os.name != "nt" or not target.is_dir():
            pytest.skip("creating this symlink requires OS permission")
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    with index.Index.open(tmp_path / "index.db") as idx:
        feed = podcasts.add_feed(idx, "https://feed.example.test/rss")
        podcasts.upsert_episodes(idx, feed["id"], [{"guid": "one", "title": "Episode"}])
        episode = podcasts.list_episodes(idx, feed_id=feed["id"])[0]["id"]
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET audio_local_path=?, transcript_local_path=?, transcript_status='done'",
                       (str(audio), str(transcript)))
        usage = podcasts.audio_storage(idx, root)
        assert usage["episodes"] == ([episode] if location == "library" else [])
        assert usage["deletable_bytes"] == (5 if location == "library" else 0)
        assert podcasts.delete_transcribed_audio(idx, root, episode) == (location == "library")
        assert target.exists()


@pytest.mark.parametrize("operation", ["download", "retranscribe"])
def test_cleanup_during_job_admission(tmp_path, monkeypatch, operation):
    """Pause the real admission path before its DB status changes."""
    from concurrent.futures import ThreadPoolExecutor
    with index.Index.open(tmp_path / "index.db") as idx:
        feed = podcasts.add_feed(idx, "https://feed.example.test/rss")
        podcasts.upsert_episodes(idx, feed["id"], [{"guid": "one", "title": "Episode",
                                                   "audio_url": "https://example.test/episode.mp3"}])
        row, = podcasts.list_episodes(idx, feed_id=feed["id"])
        audio = podcasts._episode_audio_path(tmp_path, feed, row)
        audio.write_bytes(b"audio")
        transcript = audio.with_suffix(".transcript.json")
        transcript.write_text(json.dumps({"segments": [{"start": 0, "end": 1, "text": "ready"}]}))
        with idx.write_transaction() as db:
            db.execute("UPDATE podcast_episodes SET audio_local_path=?, transcript_local_path=?, transcript_status='done'",
                       (str(audio), str(transcript)))
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(server, "_jobs", {})
        entered, release = threading.Event(), threading.Event()

        def pause(*args, **kwargs):
            entered.set()
            assert release.wait(3)
            return False

        if operation == "download":
            monkeypatch.setattr(podcasts, "_record_audio_result", pause)
            def start():
                return podcasts.download_episode_audio(idx, row["id"], data_root=tmp_path)
        else:
            monkeypatch.setattr(server.whisper_runner, "is_transcription_available", pause)
            monkeypatch.setattr(server._platform, "capability_refusal", lambda _: None)
            monkeypatch.setattr(server._platform, "media_capability", lambda: {})
            def start():
                return server._queue_podcast_transcription(row["id"])

        with ThreadPoolExecutor(max_workers=1) as pool:
            job = pool.submit(start)
            try:
                assert entered.wait(2)
                result = post("/podcasts/audio-storage/delete", {"episode_id": row["id"], "confirmed": True})
                assert result.status == 200 and result.payload["removed"] is False
                assert audio.read_bytes() == b"audio"
            finally:
                release.set()
                job.result(timeout=3)


def test_storage_skips_one_unreadable_file(tmp_path, monkeypatch):
    with index.Index.open(tmp_path / "index.db") as idx:
        folder = tmp_path / "Podcasts" / "show"
        folder.mkdir(parents=True)
        good, denied = folder / "readable.wav", folder / "denied.mp3"
        good.write_bytes(b"audio")
        denied.write_bytes(b"hidden")
        real_stat = Path.stat
        real_is_file = Path.is_file
        monkeypatch.setattr(Path, "is_file", lambda path: True if path == denied else real_is_file(path))

        def stat(path, *args, **kwargs):
            if path == denied:
                raise PermissionError("file in use")
            return real_stat(path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", stat)
        assert podcasts.audio_storage(idx, tmp_path)["bytes"] == 5


def test_refresh_supersedes_pending_scan(monkeypatch):
    first, second = Future(), Future()
    assert first.set_running_or_notify_cancel()
    pool = Mock()
    pool.submit.side_effect = [first, second]
    monkeypatch.setattr(server, "_podcast_storage_pool", pool)
    monkeypatch.setattr(server, "_podcast_storage_scan", None)
    monkeypatch.setattr(server, "_get_index", lambda: None)

    def get(suffix):
        request = Probe("GET", "/podcasts/audio-storage" + suffix)
        request.do_GET()
        return request.status, request.payload

    assert get("")[0] == 202
    assert get("?refresh=1")[0] == 202
    if not first.cancelled():
        first.set_result({"bytes": 8})
    second.set_result({"bytes": 3})
    assert get("") == (200, {"ok": True, "bytes": 3})


def test_cleanup_http_action_requires_explicit_confirmation(tmp_path, monkeypatch):
    calls = []
    with index.Index.open(tmp_path / "index.db") as idx:
        feed = podcasts.add_feed(idx, "https://feed.example.test/rss")
        podcasts.upsert_episodes(idx, feed["id"], [{"guid": "one", "title": "Episode"}])
        episode = podcasts.list_episodes(idx, feed_id=feed["id"])[0]["id"]
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(server, "_jobs", {})
        monkeypatch.setattr(podcasts, "delete_transcribed_audio", lambda idx, root, ident: calls.append(ident) or True)
        for confirmed in (None, False, "true"):
            assert post("/podcasts/audio-storage/delete", {"episode_id": episode, "confirmed": confirmed}).status == 400
        assert calls == []
        result = post("/podcasts/audio-storage/delete", {"episode_id": episode, "confirmed": True})
        assert result.status == 200 and result.payload["removed"] and calls == [episode]


def test_delete_with_non_reentrant_show_lock(tmp_path, monkeypatch):
    lock = threading.Lock()

    class ShowLock:
        def __enter__(self):
            assert lock.acquire(timeout=.5), "delete deadlocked trying to reacquire the show lock"

        def __exit__(self, *_):
            lock.release()

    with index.Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "show_capture", SimpleNamespace(
            _lock=ShowLock(), list_jobs=lambda _: []), raising=False)
        def remove(*_):
            assert lock.locked()
            return True
        monkeypatch.setattr(podcasts, "delete_transcribed_audio", remove)
        assert server._delete_podcast_audio(1, finished_job="finished")


def test_storage_observes_busy_and_released_locks_without_acquiring(tmp_path, monkeypatch):
    key = "podcast-queue:1"
    capture_lock = server.source_subscriptions.CaptureLock
    lock = capture_lock.try_acquire(tmp_path, key)
    monkeypatch.setattr(capture_lock, "try_acquire", Mock(side_effect=AssertionError("scan took a lock")))
    monkeypatch.setattr(server, "_protected_podcast_episodes", Mock(return_value=set()))
    monkeypatch.setattr(server, "_podcast_capture_key", Mock(return_value="capture"))
    monkeypatch.setattr(podcasts, "audio_storage", lambda *_, available: available({"id": 1}, tmp_path / "audio"))
    try:
        assert not server._scan_podcast_storage(None, tmp_path)
    finally:
        lock.release()
    assert server._scan_podcast_storage(None, tmp_path)


def test_posix_scan_observes_owner_lifetime(tmp_path, monkeypatch):
    import sys
    import source_subscriptions as sources
    if os.name == "nt":
        # Exercise the POSIX owner record on Windows. Native flock contention
        # has its own POSIX integration test.
        monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(
            flock=Mock(), LOCK_EX=2, LOCK_NB=4, LOCK_UN=8))
        monkeypatch.setattr(sources, "os", SimpleNamespace(
            name="posix", path=os.path, makedirs=os.makedirs, getpid=os.getpid, SEEK_END=os.SEEK_END))
    monkeypatch.setattr(sources, "_current_process_created_ms", lambda: 1234)
    alive = Mock(return_value="alive")
    monkeypatch.setattr(sources, "_process_alive", alive)
    key = "podcast-queue:1"
    with sources.CaptureLock.try_acquire(tmp_path, key):
        assert sources.CaptureLock.in_use(tmp_path, key)
        alive.assert_called_once_with(os.getpid(), 1234)
        alive.return_value = "dead"
        assert not sources.CaptureLock.in_use(tmp_path, key)
    assert not sources.CaptureLock.in_use(tmp_path, key)
    assert alive.call_count == 2


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_storage_path_loop_returns_controlled_error(tmp_path, monkeypatch, method):
    loop = tmp_path / "loop"
    resolve = Path.resolve
    def resolve_or_loop(path, *args, **kwargs):
        if path == loop:
            raise RuntimeError("Symlink loop")
        return resolve(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve_or_loop)
    with index.Index.open(tmp_path / "index.db") as idx:
        monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "_podcast_capture_key", lambda _: "capture")
        monkeypatch.setattr(server, "_jobs", {"job": dict(kind="podcast_transcribe", state="queued", audio_path=str(loop))})
        if method == "GET":
            request = Probe("GET", "/podcasts/audio-storage?refresh=1")
            request.do_GET()
            if request.status == 202:
                from concurrent.futures import wait
                assert wait([server._podcast_storage_scan], timeout=2).done
                request = Probe("GET", "/podcasts/audio-storage")
                request.do_GET()
        else:
            request = post("/podcasts/audio-storage/delete", {"episode_id": 1, "confirmed": True})
        assert request.status == 503 and not request.payload["ok"]


@pytest.mark.skipif(os.name != "nt", reason="Win32 directory handles")
def test_windows_cleanup_requests_directory_read_access(tmp_path, monkeypatch):
    import _winapi
    folder = tmp_path / "Podcasts" / "feed"
    folder.mkdir(parents=True)
    audio = folder / "item.mp3"
    audio.touch()
    open_handle = _winapi.CreateFile
    unlink = Path.unlink
    directories = (tmp_path, folder.parent, folder)
    def check_pins_then_unlink(path):
        for directory in directories:
            with pytest.raises(PermissionError) as denied:
                # A second handle requesting DELETE must get a sharing violation.
                other = open_handle(str(directory), 0x10000, 7, 0, 3, 0x02200000, 0)
                _winapi.CloseHandle(other)
            assert denied.value.winerror == 32
        unlink(path)

    create = Mock(wraps=open_handle)
    monkeypatch.setattr(Path, "unlink", check_pins_then_unlink)
    monkeypatch.setattr(_winapi, "CreateFile", create)
    assert podcasts._unlink_download(tmp_path, audio)
    assert [(call.args[0], call.args[1] & 1, call.args[2] & 4) for call in create.call_args_list] == [
        (str(path), 1, 0) for path in directories]

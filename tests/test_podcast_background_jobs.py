"""Durable, serialized podcast transcription job behavior."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

import index as index_mod
import podcasts
import server


def _seed_downloaded_episodes(idx, tmp_path: Path, count: int = 2) -> list[int]:
    feed_id = podcasts.add_feed(idx, "https://jobs.example/feed.xml")["id"]
    episodes = []
    for number in range(count):
        audio = tmp_path / f"episode-{number}.mp3"
        audio.write_bytes(b"synthetic audio")
        episodes.append({
            "guid": f"job-episode-{number}", "title": f"Episode {number}",
            "audio_url": f"https://cdn.example/{number}.mp3",
            "episode_page_url": f"https://jobs.example/{number}",
        })
    podcasts.upsert_episodes(idx, feed_id, episodes)
    rows = podcasts.list_episodes(idx, feed_id=feed_id)
    for row in rows:
        audio = tmp_path / f"episode-{row['title'].split()[-1]}.mp3"
        podcasts._record_audio_result(
            idx, row["id"], local_path=str(audio), size_bytes=audio.stat().st_size,
            error=None, status=podcasts.EPISODE_STATUS_DOWNLOADED)
    return [row["id"] for row in rows]


def test_transcription_queue_is_single_worker_and_progress_is_durable(
        tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    episode_ids = _seed_downloaded_episodes(idx, tmp_path)
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(
        server.whisper_runner, "is_whisperx_available", lambda: True)
    monkeypatch.setattr(
        server.whisper_runner, "is_model_downloaded", lambda *_args: True)
    monkeypatch.setattr(
        server.whisper_runner, "set_current_thread_below_normal", lambda: True)

    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_transcribe(audio_path, **_kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.04)
        with lock:
            active -= 1
        return {
            "model": "base", "language": "en", "diarization_ran": False,
            "segments": [{"start": 0.0, "end": 1.0,
                          "text": Path(audio_path).stem}],
        }

    monkeypatch.setattr(server.whisper_runner, "transcribe_audio", fake_transcribe)
    first = server._queue_podcast_transcription(
        episode_ids[0], model="base", consent_given=False)
    duplicate = server._queue_podcast_transcription(
        episode_ids[0], model="base", consent_given=False)
    second = server._queue_podcast_transcription(
        episode_ids[1], model="base", consent_given=False)
    results = [first, second]
    assert all(status == 202 and result["ok"] for result, status in results)
    assert len({result["job_id"] for result, _status in results}) == 2
    assert duplicate[0]["reused_existing"] is True
    assert duplicate[0]["job_id"] == first[0]["job_id"]

    deadline = time.time() + 5
    while time.time() < deadline:
        jobs = [server._get_public_job(result["job_id"])
                for result, _status in results]
        if all(job and job["state"] == "completed" for job in jobs):
            break
        time.sleep(0.02)
    assert all(job["state"] == "completed" for job in jobs)
    assert max_active == 1
    assert all(job["progress"] == 100 for job in jobs)
    assert all(job["priority"] == "below_normal" for job in jobs)
    assert all(job["result"]["segments"] == 1 for job in jobs)
    assert all(
        podcasts.get_episode(idx, episode_id)["transcript_status"] == "done"
        for episode_id in episode_ids)

    persisted = {
        row["job_id"]: json.loads(row["metadata_json"])
        for row in idx.list_jobs(limit=20)
    }
    assert all(
        persisted[result["job_id"]]["state"] == "completed"
        for result, _status in results)
    idx.close()


def test_transcription_preflight_observes_consent_and_restart_requeues(
        tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    episode_id = _seed_downloaded_episodes(idx, tmp_path, count=1)[0]
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(
        server.whisper_runner, "is_whisperx_available", lambda: True)
    monkeypatch.setattr(
        server.whisper_runner, "is_model_downloaded", lambda *_args: False)

    result, status = server._queue_podcast_transcription(
        episode_id, model="large-v3-turbo", consent_given=False)
    assert status == 412
    assert result == {
        "ok": False,
        "consent_required": True,
        "model": "large-v3-turbo",
        "error": ("Whisper model 'large-v3-turbo' has not been downloaded; "
                  "explicit consent is required."),
    }

    restored = server._validate_persisted_job({
        "id": "job_restart", "kind": "podcast_transcribe",
        "state": "running", "episode_id": episode_id,
        "model": "base", "audio_path": str(tmp_path / "episode-0.mp3"),
        "consent_given": True, "progress": 45,
    })
    assert restored["state"] == "queued"
    assert restored["progress"] == 0
    assert restored["episode_id"] == episode_id
    assert "restarted" in restored["message"]
    idx.close()


@pytest.mark.parametrize("keep_audio", [True, False])
def test_restarted_job_reuses_a_completed_transcript(tmp_path, monkeypatch, keep_audio):
    idx = index_mod.Index.open(tmp_path / "index.db")
    episode_id = _seed_downloaded_episodes(idx, tmp_path, count=1)[0]
    episode = podcasts.get_episode(idx, episode_id)
    audio_path = tmp_path / "Podcasts" / "example-show" / "episode.mp3"
    audio_path.parent.mkdir(parents=True)
    Path(episode["audio_local_path"]).rename(audio_path)
    podcasts._record_audio_result(idx, episode_id, local_path=str(audio_path), size_bytes=audio_path.stat().st_size,
                                  error=None, status=podcasts.EPISODE_STATUS_DOWNLOADED)
    monkeypatch.setattr(server, "_read_settings", lambda: {"keep_podcast_audio": keep_audio})
    transcript = {
        "model": "base",
        "language": "en",
        "diarization_ran": False,
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "Already complete"}
        ],
    }
    transcript_path = server.whisper_runner.write_transcript(
        transcript, audio_path=audio_path)
    server.whisper_runner.update_episode_transcript_state(
        idx,
        episode_id,
        status=server.whisper_runner.STATUS_DONE,
        transcript_path=transcript_path,
        model_used="base",
    )
    restored = server._validate_persisted_job({
        "id": "job_restart_reuse",
        "kind": "podcast_transcribe",
        "state": "running",
        "episode_id": episode_id,
        "model": "base",
        "audio_path": str(audio_path),
        "consent_given": True,
        "progress": 95,
    })
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(
        server.whisper_runner,
        "transcribe_audio",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("a reusable DONE transcript must skip Whisper")
        ),
    )
    monkeypatch.setattr(
        server.whisper_runner,
        "write_transcript",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("a reusable transcript must not be rewritten")
        ),
    )
    with server._jobs_lock:
        server._jobs[restored["id"]] = restored
        server._persist_jobs_locked(restored)

    server._podcast_transcription_queue.put(restored["id"])
    server._ensure_podcast_transcription_worker()
    deadline = time.time() + 5
    while time.time() < deadline:
        job = server._get_public_job(restored["id"])
        if job and job["state"] == "completed":
            break
        time.sleep(0.02)

    assert job["state"] == "completed"
    assert job["result"]["transcript_reused"] is True
    assert audio_path.exists() == keep_audio
    assert transcript_path.is_file()
    assert job["result"]["transcript_path"] == str(transcript_path)
    assert job["result"]["segments"] == 1
    assert podcasts.get_episode(idx, episode_id)["transcript_status"] == "done"
    idx.close()


def test_auto_transcription_publishes_and_toasts_after_corpus_commit(
        tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    episode_id = _seed_downloaded_episodes(idx, tmp_path, count=1)[0]
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(
        server.whisper_runner, "is_whisperx_available", lambda: True)
    monkeypatch.setattr(
        server.whisper_runner, "is_model_downloaded", lambda *_args: True)
    monkeypatch.setattr(
        server.whisper_runner, "set_current_thread_below_normal", lambda: True)
    monkeypatch.setattr(server.whisper_runner, "transcribe_audio", lambda *_a, **_k: {
        "model": "base", "language": "en", "diarization_ran": False,
        "segments": [{"start": 0.0, "end": 1.0, "text": "Published"}],
    })
    monkeypatch.setattr(
        podcasts, "episode_to_corpus",
        lambda _idx, requested_id, **_kwargs: {
            "ok": True, "video_id": f"episode-{requested_id}"})
    toasts = []
    monkeypatch.setattr(
        server, "maybe_toast",
        lambda title, body, **_kwargs: toasts.append((title, body)))

    result, status = server._queue_podcast_transcription(
        episode_id, model="base", publish_to_corpus=True)
    assert status == 202
    deadline = time.time() + 5
    while time.time() < deadline:
        job = server._get_public_job(result["job_id"])
        if job and job["state"] == "completed":
            break
        time.sleep(0.02)

    assert job["state"] == "completed"
    assert job["publish_to_corpus"] is True
    assert job["result"]["corpus"] == {
        "ok": True, "video_id": f"episode-{episode_id}"}
    assert toasts == [
        ("Podcast added to Uoink", "Episode 0 is ready in your library.")]
    idx.close()


def test_auto_publish_failure_preserves_completed_transcript_for_retry(
        tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    episode_id = _seed_downloaded_episodes(idx, tmp_path, count=1)[0]
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(
        server.whisper_runner, "is_whisperx_available", lambda: True)
    monkeypatch.setattr(
        server.whisper_runner, "is_model_downloaded", lambda *_args: True)
    monkeypatch.setattr(
        server.whisper_runner, "set_current_thread_below_normal", lambda: True)
    monkeypatch.setattr(server.whisper_runner, "transcribe_audio", lambda *_a, **_k: {
        "model": "base", "language": "en", "diarization_ran": False,
        "segments": [{"start": 0.0, "end": 1.0, "text": "Durable"}],
    })
    monkeypatch.setattr(
        podcasts, "episode_to_corpus",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("temporary publish failure")))

    result, status = server._queue_podcast_transcription(
        episode_id, model="base", publish_to_corpus=True)
    assert status == 202
    deadline = time.time() + 5
    while time.time() < deadline:
        job = server._get_public_job(result["job_id"])
        if job and job["state"] == "completed":
            break
        time.sleep(0.02)

    assert job["state"] == "completed"
    assert job["result"]["corpus"] is None
    assert job["result"]["corpus_error"] == "temporary publish failure"
    assert "publish will retry" in job["message"]
    episode = podcasts.get_episode(idx, episode_id)
    assert episode["transcript_status"] == "done"
    assert episode["status"] == podcasts.EPISODE_STATUS_TRANSCRIBED
    idx.close()


def test_running_podcast_cancels_at_checkpoint_and_preserves_audio(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    episode = _seed_downloaded_episodes(idx, tmp_path, 1)[0]
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server.whisper_runner, "is_transcription_available", lambda: True)
    monkeypatch.setattr(server.whisper_runner, "is_model_downloaded", lambda *_: True)
    entered = threading.Event()
    def transcribe(path, **kw):
        entered.set()
        assert kw["cancel_event"].wait(3)
        kw["checkpoint"]({"end": 1})
        raise AssertionError("continued after cancellation")
    monkeypatch.setattr(server.whisper_runner, "transcribe_audio", transcribe)
    result, status = server._queue_podcast_transcription(episode)
    assert status == 202 and entered.wait(3)
    public, error, _ = server._cancel_playlist_job(result["job_id"])
    assert not error and public["state"] == "cancelled"
    server._podcast_transcription_queue.join()
    assert server._get_public_job(result["job_id"])["state"] == "cancelled"
    assert podcasts.get_episode(idx, episode)["transcript_status"] == "none"
    assert not list(tmp_path.glob("*.transcript.json"))
    idx.close()


def test_cancelling_queued_podcast_clears_episode_status(tmp_path, monkeypatch):
    idx = index_mod.Index.open(tmp_path / "index.db")
    episode = _seed_downloaded_episodes(idx, tmp_path, 1)[0]
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server.whisper_runner, "is_transcription_available", lambda: True)
    monkeypatch.setattr(server.whisper_runner, "is_model_downloaded", lambda *_: True)
    monkeypatch.setattr(server, "_ensure_podcast_transcription_worker", lambda: None)
    import queue
    monkeypatch.setattr(server, "_podcast_transcription_queue", queue.Queue())
    payload, status = server._queue_podcast_transcription(episode)
    assert status == 202
    job, error, _ = server._cancel_playlist_job(payload["job_id"])
    assert not error and job["state"] == "cancelled"
    assert podcasts.get_episode(idx, episode)["transcript_status"] == "none"
    idx.close()


def test_cancelled_worker_preserves_retry_badge(tmp_path, monkeypatch):
    import queue
    import pytest
    idx = index_mod.Index.open(tmp_path / "index.db")
    episode = _seed_downloaded_episodes(idx, tmp_path, 1)[0]
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server.whisper_runner, "is_transcription_available", lambda: True)
    monkeypatch.setattr(server.whisper_runner, "is_model_downloaded", lambda *_: True)
    monkeypatch.setattr(server, "_ensure_podcast_transcription_worker", lambda: None)
    jobs = queue.Queue()
    monkeypatch.setattr(server, "_podcast_transcription_queue", jobs)
    payload, _ = server._queue_podcast_transcription(episode)
    def cancel_and_retry(*a, **kw):
        server._cancel_playlist_job(payload["job_id"])
        retry, status = server._queue_podcast_transcription(episode)
        assert status == 202 and jobs.get_nowait() == retry["job_id"]
        kw["checkpoint"]({})
    monkeypatch.setattr(server.whisper_runner, "transcribe_audio", cancel_and_retry)
    monkeypatch.setattr(jobs, "get", lambda *a, **kw: queue.Queue.get(jobs, block=False))
    with pytest.raises(queue.Empty):
        server._podcast_transcription_worker()
    assert podcasts.get_episode(idx, episode)["transcript_status"] == "queued"
    idx.close()

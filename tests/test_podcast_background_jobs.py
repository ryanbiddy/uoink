"""Durable, serialized podcast transcription job behavior."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

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

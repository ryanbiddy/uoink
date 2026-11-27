"""Retry and cancellation while the previous transcription helper is stopped."""
import pytest

import server
import uoink_agent_runtime as runtime
from tests.test_podcast_job_transports import episode


@pytest.mark.parametrize("state", ["queued", "running"])
def test_retry_and_cancel_after_helper_stops(episode, monkeypatch, state):
    monkeypatch.setattr(runtime, "helper_running", lambda _: False)
    launches = []
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *a, **kw: launches.append(kw))
    request = {"episode_id": episode}
    initial = runtime.call_tool("transcribe_podcast_episode", request, server)
    job = dict(initial["job"], state=state, current_video_phase=state)
    idx = server._get_index()
    idx.upsert_job(server._index_job_row(job))
    launches.clear()
    retry = runtime.call_tool("transcribe_podcast_episode", request, server)
    assert retry["reused_existing"] and retry["job_id"] == job["id"] and len(launches) == 1
    # A new helper has reserved its queue but hasn't published its PID yet.
    with server.source_subscriptions.CaptureLock.try_acquire(server.DATA_ROOT, server.podcasts.PODCAST_WORKER_LOCK):
        busy = runtime.call_tool("cancel_job", {"job_id": job["id"]}, server)
        assert not busy["ok"] and "helper" in busy["error"]
        assert server._get_public_job(job["id"])["state"] == state
    cancel = runtime.call_tool("cancel_job", {"job_id": job["id"]}, server)
    assert cancel["ok"] and cancel["job"]["state"] == "cancelled"
    server._restore_jobs_from_disk()
    assert server._get_public_job(job["id"])["state"] == "cancelled"

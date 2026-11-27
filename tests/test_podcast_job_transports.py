"""Podcast transcription belongs to the helper even when a client exits."""

import json
import queue
import threading
import time

import pytest

import index
import server
import uoink_agent_runtime as runtime
import uoink_cli as cli
import uoink_mcp_tools as registry
from tests.test_podcast_background_jobs import _seed_downloaded_episodes


@pytest.fixture
def episode(tmp_path, monkeypatch):
    idx = index.Index.open(tmp_path / "index.db")
    episode_id = _seed_downloaded_episodes(idx, tmp_path, 1)[0]
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server, "_jobs", {})
    jobs = queue.Queue()
    monkeypatch.setattr(jobs, "get", lambda *a, **kw: queue.Queue.get(jobs, block=False))
    monkeypatch.setattr(server, "_podcast_transcription_queue", jobs)
    worker = server._podcast_transcription_worker

    def drain():
        try:
            worker()
        except queue.Empty:
            pass

    monkeypatch.setattr(server, "_podcast_transcription_worker", drain)
    monkeypatch.setattr(server, "_podcast_transcription_worker_thread", None)
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server.whisper_runner, "is_transcription_available", lambda: True)
    monkeypatch.setattr(server.whisper_runner, "is_model_downloaded", lambda *a: True)
    monkeypatch.setattr(registry, "_backend", server)
    monkeypatch.setattr(registry.TOOL_REGISTRY["transcribe_podcast_episode"].rate_limiter, "_calls", [])
    yield episode_id
    jobs.join()
    if server._podcast_transcription_worker_thread:
        server._podcast_transcription_worker_thread.join(2)
    idx.close()


@pytest.mark.parametrize("transport", ["cli", "stdio", "http"])
def test_slow_transcription_returns_a_job_before_the_worker_finishes(
        episode, monkeypatch, capsys, transport):
    from tests.test_mcp_full_toolset import call as stdio_call

    entered = threading.Event()
    release = threading.Event()
    forwarded = []

    def transcriber(*a, **kw):
        entered.set()
        release.wait(1.5)
        return {"model": "base", "segments": [], "language": "en"}

    def http_tool(name, args, **kwargs):
        forwarded.append(name)
        return {"ok": True, "result": registry.call_tool(name, args)}

    monkeypatch.setattr(runtime, "helper_running", lambda _: True)
    monkeypatch.setattr(server, "_TOKEN_OWNED", True)
    monkeypatch.setattr(server, "_call_http_registry_tool", http_tool)
    monkeypatch.setattr(server.whisper_runner, "transcribe_audio", transcriber)
    capsys.readouterr()
    started = time.monotonic()
    try:
        name = "transcribe_podcast_episode"
        args = {"episode_id": episode}
        if transport == "cli":
            assert cli.main(["call", name, f"episode_id={episode}"]) == 0
            job = json.loads(capsys.readouterr().out)
        elif transport == "stdio":
            job = stdio_call(name, args)
        else:
            handler = object.__new__(server.Handler)
            handler._send_mcp_result = lambda _id, body: body["structuredContent"]
            job = handler._handle_mcp_post("/mcp/v1", {
                "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
        assert time.monotonic() - started < .65
        assert job["ok"] and job["job"]["state"] == "queued"
        assert entered.wait(2)
        status = runtime.call_tool("get_job_status", {"job_id": job["job_id"]}, server)
        assert status["job"]["state"] == "running"
        assert 0 < status["job"]["progress"] < 100
        if transport != "http":
            assert "transcribe_podcast_episode" in forwarded
    finally:
        release.set()


def test_one_shot_offline_job_survives_client_exit(episode, monkeypatch, capsys):
    def unexpected_worker():
        server._podcast_transcription_queue.get_nowait()
        server._podcast_transcription_queue.task_done()
        pytest.fail("the client process must never run the transcriber")

    monkeypatch.setattr(runtime, "helper_running", lambda _: False)
    launches = []
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda cmd, **opts: launches.append((cmd, opts)))
    monkeypatch.setattr(server, "_ensure_podcast_transcription_worker", unexpected_worker)
    assert cli.main(["call", "transcribe_podcast_episode", f"episode_id={episode}"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert "Uoink" in first["job"]["message"]
    cmd, opts = launches[0]
    assert "--quiet" in cmd and any(arg.endswith("uoink_supervisor.py") for arg in cmd)
    assert all(opts[stream] == runtime.subprocess.DEVNULL for stream in ("stdin", "stdout", "stderr"))
    # A second one-shot process starts with no in-memory jobs.
    monkeypatch.setattr(server, "_jobs", {})
    assert cli.main(["call", "transcribe_podcast_episode", f"episode_id={episode}"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["reused_existing"] and second["job_id"] == first["job_id"]
    args = {"job_id": first["job_id"]}
    assert runtime.call_tool("get_job_status", args, server)["job"]["state"] == "queued"
    assert runtime.call_tool("cancel_job", args, server)["job"]["state"] == "cancelled"


def test_helper_adopts_an_offline_clients_job_once(episode, monkeypatch):
    monkeypatch.setattr(runtime, "helper_running", lambda _: False)
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *args, **opts: None)
    calls = []

    def transcriber(audio, **kwargs):
        calls.append(audio)
        return {"model": "base", "language": "en", "segments": [
            {"start": 0, "end": 1, "text": "Test transcript"}]}

    monkeypatch.setattr(server.whisper_runner, "transcribe_audio", transcriber)
    request = runtime.call_tool("transcribe_podcast_episode", {"episode_id": episode}, server)
    assert request["ok"] and not calls
    job_id = request["job_id"]
    # Startup and the periodic pass may both notice the client submission.
    server._restore_jobs_from_disk()
    server._pickup_waiting_podcast_jobs()
    server._pickup_waiting_podcast_jobs()
    server._podcast_transcription_queue.join()
    assert len(calls) == 1
    assert server._get_public_job(job_id)["progress"] == 100

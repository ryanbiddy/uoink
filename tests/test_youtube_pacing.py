"""Offline concurrency and cancellation regressions for YouTube pacing."""
from __future__ import annotations

from contextlib import contextmanager

import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402
import uoink_mcp_tools  # noqa: E402


URL = "https://www.youtube.com/watch?v=abcdef12345"


class ObservedCondition(threading.Condition):
    def __init__(self):
        super().__init__()
        self.waiting = threading.Event()

    def wait(self, timeout=None):
        self.waiting.set()
        return super().wait(timeout)


@pytest.fixture
def network(monkeypatch):
    limiter = server._YouTubeCallLimiter(jitter=lambda: 0)
    limiter._condition = ObservedCondition()
    state = SimpleNamespace(
        limiter=limiter, calls=[], blocks={}, started={}, returncode=0,
        launch_error=None, clock=time.monotonic,
    )
    guard = threading.Lock()

    class Process:
        def __init__(self, cmd, **kwargs):
            if state.launch_error is not None:
                raise state.launch_error
            self.cmd = cmd
            self.returncode = None
            self.result_code = state.returncode
            self.release = state.blocks.get(cmd[-1])
            self.record = {"cmd": cmd, "start": time.monotonic(), "end": None,
                           "clock": state.clock(),
                           "process_lock_held": server._extract_lock.locked()}
            self.stdout = json.dumps({"id": "abcdef12345", "description": "Channel",
                                      "entries": []})
            if not kwargs.get("text"):
                self.stdout = self.stdout.encode("utf-8")
            self.stderr = "ERROR: fixture failure" if kwargs.get("text") else b"ERROR: fixture failure"
            if "--write-comments" in cmd:
                folder = Path(cmd[cmd.index("-o") + 1]).parent
                (folder / "abcdef12345_yoink_comments.info.json").write_text(
                    json.dumps({"comments": [{"author": "Example", "text": "Comment",
                                              "like_count": 1}]}), encoding="utf-8")
            with guard:
                state.calls.append(self.record)
            state.started.setdefault(cmd[-1], threading.Event()).set()

        def communicate(self, timeout=None):
            if self.release is not None and not self.release.wait(timeout):
                raise subprocess.TimeoutExpired(self.cmd, timeout)
            self.returncode = self.result_code
            self.record["end"] = time.monotonic()
            return self.stdout, self.stderr

        def terminate(self):
            self.returncode = -15
            self.record["end"] = time.monotonic()
            if self.release is not None:
                self.release.set()

        kill = terminate

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    unexpected_io = Mock(side_effect=AssertionError("unmocked external I/O"))
    monkeypatch.setattr(server, "_youtube_call_limiter", limiter)
    monkeypatch.setattr(server, "_extract_lock", threading.Lock())
    monkeypatch.setattr(server._ManualOwnership, "_pacing", threading.local())
    monkeypatch.setattr(server._ServerCaptureBackend, "_pacing", threading.local())
    monkeypatch.setattr(server._ServerCaptureBackend, "_local_identities", {})
    monkeypatch.setattr(server._ServerCaptureBackend, "_identity_condition", ObservedCondition())
    monkeypatch.setattr(server.source_subscriptions, "current_capture_context", lambda: None)
    monkeypatch.setattr(subprocess, "Popen", Process)
    monkeypatch.setattr(subprocess, "run", unexpected_io)
    monkeypatch.setattr(subprocess, "check_output", unexpected_io)
    monkeypatch.setattr(server.urllib.request, "urlopen", unexpected_io)
    monkeypatch.setattr(server.socket.socket, "connect", unexpected_io)
    yield state
    unexpected_io.assert_not_called()


def block(network, url):
    network.blocks[url] = threading.Event()
    network.started[url] = threading.Event()


def assert_serial(calls):
    ordered = sorted(calls, key=lambda call: call["start"])
    assert all(call["end"] is not None for call in ordered)
    assert all(left["end"] <= right["start"]
               for left, right in zip(ordered, ordered[1:]))


@pytest.mark.parametrize("host", [
    "youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com",
])
def test_concurrent_youtube_extractions_are_serialised(network, host):
    other = f"https://{host}/watch?v=other123456"
    block(network, URL)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(server._fetch_metadata, URL)
        try:
            assert network.started[URL].wait(1)
            second = pool.submit(server._fetch_metadata, other)
            assert network.limiter._condition.waiting.wait(1)
            assert len(network.calls) == 1
        finally:
            network.blocks[URL].set()
        assert first.result(timeout=2)["id"] == "abcdef12345"
        assert second.result(timeout=2)["id"] == "abcdef12345"
    assert len(network.calls) == 2
    assert_serial(network.calls)


def test_other_hosts_run_concurrently_with_youtube_and_each_other(network):
    urls = [URL, "https://vimeo.com/12345", "https://vimeo.com/67890"]
    for url in urls:
        block(network, url)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(server._fetch_metadata, url) for url in urls]
        try:
            assert all(network.started[url].wait(1) for url in urls)
            assert len(network.calls) == 3
            assert all(call["end"] is None for call in network.calls)
        finally:
            for event in network.blocks.values():
                event.set()
        for future in futures:
            future.result(timeout=2)
    assert max(call["start"] for call in network.calls) < min(
        call["end"] for call in network.calls)


@pytest.mark.parametrize("fetch", [server._fetch_metadata, server._fetch_channel_context])
def test_cancellation_while_waiting_does_not_launch_or_block_next_call(network, fetch):
    cancel = threading.Event()
    block(network, URL)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(server._fetch_metadata, URL)
        try:
            assert network.started[URL].wait(1)
            second = pool.submit(fetch, URL, cancel_event=cancel)
            assert network.limiter._condition.waiting.wait(1)
            cancel.set()
            with pytest.raises(server.PlaylistJobCancelled):
                second.result(timeout=1)
            assert len(network.calls) == 1
        finally:
            network.blocks[URL].set()
        first.result(timeout=2)
    server._fetch_metadata(URL)
    assert len(network.calls) == 2
    assert_serial(network.calls)


def test_jitter_between_calls_uses_injected_clock_without_sleep(network, monkeypatch):
    now = [100.0]
    jitter = Mock(return_value=3.0)
    limiter = server._YouTubeCallLimiter(jitter=jitter, clock=lambda: now[0])
    waits = []

    def advance(timeout=None):
        waits.append(timeout)
        now[0] += timeout

    monkeypatch.setattr(limiter._condition, "wait", advance)
    monkeypatch.setattr(server, "_youtube_call_limiter", limiter)
    network.clock = lambda: now[0]
    server._fetch_metadata(URL)
    assert not waits
    server._run_subprocess([*server.YTDLP_CMD, "-f", "best", URL])
    server._run_subprocess([*server.YTDLP_CMD, "--skip-download", "--write-subs", URL])
    assert [call["clock"] for call in network.calls] == pytest.approx([100, 103, 106])
    assert sum(waits) == pytest.approx(6)
    assert jitter.call_count == 3
    now[0] += 10
    waits.clear()
    server._fetch_metadata(URL)
    assert not waits


def test_default_jitter_is_two_to_five_seconds(network, monkeypatch):
    jitter = Mock(return_value=3)
    monkeypatch.setattr(server.random, "uniform", jitter)
    monkeypatch.setattr(server, "_youtube_call_limiter", server._YouTubeCallLimiter())
    server._fetch_metadata(URL)
    jitter.assert_called_once_with(2.0, 5.0)


def test_cancellation_during_cooldown_does_not_launch(network, monkeypatch):
    cancel = threading.Event()
    limiter = server._YouTubeCallLimiter(jitter=lambda: 5, clock=lambda: 100)
    monkeypatch.setattr(server, "_youtube_call_limiter", limiter)
    monkeypatch.setattr(limiter._condition, "wait", lambda timeout=None: cancel.set())
    server._fetch_metadata(URL)
    with pytest.raises(server.PlaylistJobCancelled):
        server._fetch_metadata(URL, cancel_event=cancel)
    assert len(network.calls) == 1
    assert not limiter._active
    assert not limiter._waiting


@pytest.mark.parametrize("failure", ["launch", "exit", "timeout", "cancel"])
def test_failed_subprocess_releases_youtube_slot(network, failure):
    cancel = threading.Event()
    if failure == "launch":
        network.launch_error = OSError("fixture launch error")
        error = OSError
    elif failure == "exit":
        network.returncode = 1
        error = subprocess.CalledProcessError
    else:
        block(network, URL)
        error = (subprocess.TimeoutExpired if failure == "timeout"
                 else server.PlaylistJobCancelled)
    with ThreadPoolExecutor(max_workers=1) as pool:
        failed = pool.submit(server._run_subprocess, [*server.YTDLP_CMD, URL],
                             cancel_event=cancel, timeout=0 if failure == "timeout" else None)
        try:
            if failure == "cancel":
                assert network.started[URL].wait(1)
                cancel.set()
            with pytest.raises(error):
                failed.result(timeout=2)
        finally:
            for event in network.blocks.values():
                event.set()
    network.launch_error = None
    network.returncode = 0
    server._fetch_metadata(URL)
    assert not network.limiter._active


@pytest.mark.parametrize("cmd", [
    ["ffmpeg", "-i", URL],
    [*server.YTDLP_CMD, "--version"],
    [*server.YTDLP_CMD, "https://youtube.com.example.org/watch?v=123"],
    [*server.YTDLP_CMD, "https://youtube.com@example.org/watch?v=123"],
    [*server.YTDLP_CMD, "https://example.org/?url=https://youtube.com/watch?v=123"],
])
def test_non_youtube_or_offline_commands_bypass_pacing(network, monkeypatch, cmd):
    slot = Mock(side_effect=AssertionError("unexpected YouTube pacing"))
    monkeypatch.setattr(network.limiter, "slot", slot)
    server._run_subprocess(cmd)
    slot.assert_not_called()


def test_comments_and_channel_context_share_the_limiter(network, monkeypatch, tmp_path):
    for name in ("_replace_comments_section", "_update_sidecar_comments",
                 "_start_hook_type_thread", "_start_comment_intelligence_thread"):
        monkeypatch.setattr(server, name, Mock())
    block(network, URL)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(server._fetch_metadata, URL)
        try:
            assert network.started[URL].wait(1)
            comments = pool.submit(server._comments_worker, URL, tmp_path, tmp_path / "capture.md")
            channel = pool.submit(server._fetch_channel_context, "https://youtube.com/@example")
            assert network.limiter._condition.waiting.wait(1)
            assert len(network.calls) == 1
        finally:
            network.blocks[URL].set()
        first.result(timeout=2)
        comments.result(timeout=2)
        assert channel.result(timeout=2) == {"description": "Channel", "recent_videos": []}
    assert len(network.calls) == 3
    assert_serial(network.calls)
    assert any("--write-comments" in call["cmd"] for call in network.calls)
    server._update_sidecar_comments.assert_called_once()
    assert server._update_sidecar_comments.call_args.args[2] == "fetched"


@pytest.mark.parametrize("owner_kind", ["manual", "standing"])
def test_waiting_yields_process_lock_and_keeps_identity_on_cancel(network, monkeypatch, owner_kind):
    cancel = threading.Event()
    identity = SimpleNamespace(held=True)
    identity.release = Mock(side_effect=lambda: setattr(identity, "held", False))
    backend = server._ServerCaptureBackend()
    start = {"capture_key": "youtube:abcdef12345", "start_id": "fixture-start"}
    monkeypatch.setattr(server._ManualOwnership, "corpus_row", staticmethod(lambda _id: None))

    def acquire_identity(*_args, **_kwargs):
        assert not server._extract_lock.locked()
        return identity

    monkeypatch.setattr(server.source_subscriptions.CaptureLock, "acquire", acquire_identity)

    def waiting_capture():
        if owner_kind == "manual":
            with server._manual_extraction_ownership(URL) as owned:
                assert owned.lock is identity
                server._fetch_metadata(URL, cancel_event=cancel)
        else:
            server._extract_lock.acquire()
            backend._leases[start["capture_key"]] = (identity, True, start["start_id"])
            backend._pacing.owner = (backend, start)
            try:
                server._fetch_metadata(URL, cancel_event=cancel)
            finally:
                backend._pacing.owner = None
                backend.release(start)

    block(network, URL)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(server._fetch_metadata, URL)
        try:
            assert network.started[URL].wait(1)
            second = pool.submit(waiting_capture)
            assert network.limiter._condition.waiting.wait(1)
            assert identity.held
            assert server._extract_lock.acquire(blocking=False)
            try:
                cancel.set()
                with pytest.raises(server.PlaylistJobCancelled):
                    second.result(timeout=1)
                assert server._extract_lock.locked(), "cancellation released another caller's lock"
            finally:
                server._extract_lock.release()
            identity.release.assert_called_once()
            assert not identity.held
            assert len(network.calls) == 1
        finally:
            network.blocks[URL].set()
        first.result(timeout=2)


def test_concurrent_capture_steps_resume_process_ownership(network, monkeypatch):
    captures = ["https://youtube.com/watch?v=first123456",
                "https://youtube.com/watch?v=other123456"]
    entered = {url: threading.Event() for url in captures}
    identities = []

    def acquire_identity(*_args, **_kwargs):
        identity = Mock()
        identities.append(identity)
        return identity

    monkeypatch.setattr(server._ManualOwnership, "corpus_row", staticmethod(lambda _id: None))
    monkeypatch.setattr(server.source_subscriptions.CaptureLock, "acquire", acquire_identity)

    def capture(url):
        with server._manual_extraction_ownership(url):
            entered[url].set()
            server._fetch_metadata(url)
            server._run_subprocess([*server.YTDLP_CMD, "-f", "best", url])
            server._run_subprocess([*server.YTDLP_CMD, "--skip-download", "--write-subs", url])
            assert server._extract_lock.locked()

    block(network, URL)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(server._fetch_metadata, URL)
        try:
            assert network.started[URL].wait(1)
            futures = [pool.submit(capture, url) for url in captures]
            assert all(event.wait(1) for event in entered.values())
        finally:
            network.blocks[URL].set()
        first.result(timeout=2)
        for future in futures:
            future.result(timeout=2)
    assert len(network.calls) == 7
    assert_serial(network.calls)
    assert all(call["process_lock_held"] for call in network.calls[1:])
    assert not server._extract_lock.locked()
    assert len(identities) == 2
    for identity in identities:
        identity.release.assert_called_once()


def test_standing_capture_restores_process_slot_before_launch(network):
    backend = server._ServerCaptureBackend()
    start = {"capture_key": "youtube:abcdef12345", "start_id": "fixture-start"}
    identity = Mock()
    server._extract_lock.acquire()
    backend._leases[start["capture_key"]] = (identity, True, start["start_id"])
    backend._pacing.owner = (backend, start)
    try:
        server._fetch_metadata(URL)
        assert backend._leases[start["capture_key"]][1] is True
        assert network.calls[0]["process_lock_held"]
        assert server._extract_lock.locked()
    finally:
        backend._pacing.owner = None
        backend.release(start)
    assert not server._extract_lock.locked()
    identity.release.assert_called_once()


@pytest.mark.parametrize("fetch", [server._fetch_metadata, server._fetch_channel_context])
def test_standing_capture_losing_ownership_while_waiting_does_not_launch(network, monkeypatch, fetch):
    backend = server._ServerCaptureBackend()
    start = {"capture_key": "youtube:abcdef12345", "start_id": "fixture-start"}
    identity = Mock()
    server._extract_lock.acquire()
    backend._leases[start["capture_key"]] = (identity, True, start["start_id"])
    backend._pacing.owner = (backend, start)
    network.limiter._next_call = time.monotonic() + 5

    def settle_while_waiting(timeout=None):
        assert not server._extract_lock.locked()
        backend.release(start)
        network.limiter._next_call = 0

    monkeypatch.setattr(network.limiter._condition, "wait", settle_while_waiting)
    try:
        with pytest.raises(server.source_subscriptions.CaptureOwnershipUnavailable):
            fetch(URL)
    finally:
        backend._pacing.owner = None
    assert not network.calls
    assert not server._extract_lock.locked()
    assert not network.limiter._active
    identity.release.assert_called_once()


@pytest.mark.parametrize("owner_kind", ["manual", "standing"])
def test_process_waiter_leaves_youtube_slot_for_unregistered_lock_owner(network, monkeypatch, owner_kind):
    process_busy = threading.Event()
    resume_blocked = threading.Event()
    release_process = threading.Event()
    cancel = threading.Event()
    process_lock = threading.Lock()

    class ProcessLock:
        def acquire(self, blocking=True, timeout=-1):
            acquired = process_lock.acquire(blocking, timeout)
            if not acquired:
                resume_blocked.set()
            return acquired

        def release(self):
            process_lock.release()

        def locked(self):
            return process_lock.locked()

        def __enter__(self):
            self.acquire()

        def __exit__(self, *_args):
            self.release()

    monkeypatch.setattr(server, "_extract_lock", ProcessLock())
    monkeypatch.setattr(server._ManualOwnership, "corpus_row", staticmethod(lambda _id: None))
    identity = Mock()
    monkeypatch.setattr(server.source_subscriptions.CaptureLock, "acquire", lambda *_a, **_k: identity)
    backend = server._ServerCaptureBackend()
    start = {"capture_key": "youtube:abcdef12345", "start_id": "fixture-start"}

    def capture():
        if owner_kind == "manual":
            with server._manual_extraction_ownership(URL):
                server._fetch_metadata(URL, cancel_event=cancel)
        else:
            server._extract_lock.acquire()
            backend._leases[start["capture_key"]] = (identity, True, start["start_id"])
            backend._pacing.owner = (backend, start)
            try:
                server._fetch_metadata(URL, cancel_event=cancel)
            finally:
                backend._pacing.owner = None
                backend.release(start)

    def unregistered_owner():
        with server._extract_lock:
            assert getattr(server._ManualOwnership._pacing, "owner", None) is None
            assert getattr(server._ServerCaptureBackend._pacing, "owner", None) is None
            process_busy.set()
            assert resume_blocked.wait(1)
            server._fetch_metadata("https://music.youtube.com/watch?v=other123456")
            assert release_process.wait(2)

    block(network, URL)
    other_url = "https://music.youtube.com/watch?v=other123456"
    network.started[other_url] = threading.Event()
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(server._fetch_metadata, URL)
        try:
            assert network.started[URL].wait(1)
            waiting = pool.submit(capture)
            assert network.limiter._condition.waiting.wait(1)
            owner = pool.submit(unregistered_owner)
            assert process_busy.wait(1)
            network.blocks[URL].set()
            first.result(timeout=2)
            assert network.started[other_url].wait(1)
            assert not waiting.done(), "capture resumed without its process lock"
            assert len(network.calls) == 2
        finally:
            release_process.set()
            network.blocks[URL].set()
            if not network.started[other_url].is_set():
                cancel.set()
        owner.result(timeout=2)
        waiting.result(timeout=2)
    assert_serial(network.calls)
    assert len(network.calls) == 3
    assert not server._extract_lock.locked()
    identity.release.assert_called_once()


def test_generic_music_extraction_waits_without_process_lock(network, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    handler = SimpleNamespace(_send_json=lambda status, body: (status, body))
    block(network, URL)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(server._fetch_metadata, URL)
        try:
            assert network.started[URL].wait(1)
            network.returncode = 1  # Stop after metadata, before publication.
            second = pool.submit(server.Handler._handle_extract_any, handler, {
                "url": "https://music.youtube.com/watch?v=other123456"})
            assert network.limiter._condition.waiting.wait(1)
            assert server._extract_lock.acquire(blocking=False)
            server._extract_lock.release()
        finally:
            network.blocks[URL].set()
        first.result(timeout=2)
        status, body = second.result(timeout=2)
    assert status == 400
    assert body["platform"] == server.PLATFORM_GENERIC
    assert_serial(network.calls)
    assert [call["process_lock_held"] for call in network.calls] == [False, True]


@pytest.mark.parametrize("url", ["https://vimeo.com/12345", "https://soundcloud.com/example/track"])
def test_generic_non_youtube_metadata_keeps_process_lock(network, monkeypatch, tmp_path, url):
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    handler = SimpleNamespace(_send_json=lambda status, body: (status, body))
    network.returncode = 1  # Stop after metadata, before publication.
    status, body = server.Handler._handle_extract_any(handler, {"url": url})
    assert status == 400
    assert body["platform"] == server.PLATFORM_GENERIC
    assert len(network.calls) == 1
    assert network.calls[0]["process_lock_held"]
    assert not server._extract_lock.locked()


@pytest.mark.parametrize("owner_kind", ["manual", "standing"])
def test_manual_waiter_reuses_local_capture_beyond_identity_timeout(
        network, monkeypatch, tmp_path, owner_kind):
    backend = server._ServerCaptureBackend()
    start = {"capture_key": server._manual_capture_key(URL), "start_id": "fixture-start"}
    entered = threading.Event()
    finish = threading.Event()
    published = {}
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server.source_subscriptions, "MANUAL_CAPTURE_LOCK_TIMEOUT_S", 0)
    monkeypatch.setattr(server._ManualOwnership, "corpus_row",
                        staticmethod(lambda _id: published.get("row")))
    evidence = SimpleNamespace(complete=True)
    service = SimpleNamespace(publication_evidence_for_reuse=Mock(return_value=evidence))
    monkeypatch.setattr(server, "_source_service", lambda: service)
    monkeypatch.setattr(server, "_get_index", Mock(side_effect=OSError("fixture has no index")))

    def publish():
        entered.set()
        assert finish.wait(2)
        published["row"] = {"title": "Completed capture", "metadata_json": "{}",
                            "corpus_path": str(tmp_path / "capture.md")}

    def owner():
        if owner_kind == "manual":
            with server._manual_extraction_ownership(URL) as ownership:
                assert ownership.ok
                publish()
        else:
            assert backend.acquire(start, {}, {"kind": "youtube_channel"}) is None
            try:
                publish()
            finally:
                backend.release(start)

    def waiter():
        with server._manual_extraction_ownership(URL) as ownership:
            assert ownership.ok
            assert ownership.completed_while_waiting
            assert ownership.reused["reused"] is True
            return ownership.reused

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(owner)
        try:
            assert entered.wait(1)
            second = pool.submit(waiter)
            assert backend._identity_condition.waiting.wait(1)
            assert not second.done(), "local ownership must outlive the external wait bound"
        finally:
            finish.set()
        first.result(timeout=2)
        assert second.result(timeout=2)["title"] == "Completed capture"
    service.publication_evidence_for_reuse.assert_called_once_with("abcdef12345")
    assert not backend._local_identities
    assert not server._extract_lock.locked()
    assert not network.calls, "a reused capture must not start another extraction"


def test_standing_worker_waits_for_local_identity_without_process_lock(network, monkeypatch):
    backend = server._ServerCaptureBackend()
    key = server._manual_capture_key(URL)
    start = {"capture_key": key, "start_id": "fixture-start"}
    first_identity = Mock()
    second_identity = Mock()
    backend.register_identity(key, first_identity)
    acquire = Mock(return_value=second_identity)
    monkeypatch.setattr(server.source_subscriptions.CaptureLock, "acquire", acquire)
    with ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(backend._ensure_ownership, start)
        try:
            assert backend._identity_condition.waiting.wait(1)
            acquire.assert_not_called()
            assert server._extract_lock.acquire(blocking=False)
            server._extract_lock.release()
        finally:
            backend.release_identity(key, first_identity)
        waiting.result(timeout=2)
    try:
        assert backend._leases[key] == (second_identity, True, start["start_id"])
        assert server._extract_lock.locked()
    finally:
        backend.release(start)
    assert not backend._local_identities
    assert not server._extract_lock.locked()


def test_local_owner_acquired_during_identity_wait_is_allowed_to_finish(network, monkeypatch):
    backend = server._ServerCaptureBackend()
    key = server._manual_capture_key(URL)
    local_identity = Mock()
    next_identity = Mock()

    def acquire_after_race(*_args, **_kwargs):
        if acquire.call_count == 1:
            backend.register_identity(key, local_identity)
            return None
        return next_identity

    # Model another local owner acquiring just after the initial registry check.
    acquire = Mock(side_effect=acquire_after_race)
    monkeypatch.setattr(server.source_subscriptions.CaptureLock, "acquire", acquire)
    with ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(backend.acquire_identity, key)
        try:
            assert backend._identity_condition.waiting.wait(1)
            assert not waiting.done()
            assert not server._extract_lock.locked()
        finally:
            backend.release_identity(key, local_identity)
        assert waiting.result(timeout=2) is next_identity
    try:
        assert acquire.call_count == 2
    finally:
        backend.release_identity(key, next_identity)
    assert not backend._local_identities


@pytest.mark.parametrize("waiter_kind", ["manual", "standing"])
def test_external_identity_owner_still_has_bounded_wait(network, monkeypatch, waiter_kind):
    acquire = Mock(return_value=None)
    monkeypatch.setattr(server.source_subscriptions.CaptureLock, "acquire", acquire)
    monkeypatch.setattr(server._ManualOwnership, "corpus_row", staticmethod(lambda _id: None))
    key = server._manual_capture_key(URL)
    if waiter_kind == "manual":
        with server._manual_extraction_ownership(URL) as ownership:
            with pytest.raises(server.source_subscriptions.CaptureOwnershipUnavailable):
                ownership.raise_if_unavailable()
    else:
        with pytest.raises(server.source_subscriptions.CaptureOwnershipUnavailable):
            server._ServerCaptureBackend()._ensure_ownership(
                {"capture_key": key, "start_id": "fixture-start"})
    acquire.assert_called_once_with(
        server.DATA_ROOT, key, timeout=server.source_subscriptions.MANUAL_CAPTURE_LOCK_TIMEOUT_S)
    assert not server._extract_lock.locked()
    assert not server._ServerCaptureBackend._local_identities


@pytest.mark.parametrize("endpoint", ["poll", "scan", "mcp"])
def test_playlist_endpoints_wait_through_shared_limiter(network, monkeypatch, endpoint):
    playlist = {"id": 1, "playlist_url": "https://youtube.com/playlist?list=PLfixture",
                "enabled": True, "last_seen_video_ids": []}
    idx = SimpleNamespace(_lock=threading.Lock(), _conn=Mock())
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    monkeypatch.setattr(server, "_read_settings", lambda: {"auto_uoink_enabled": True})
    monkeypatch.setattr(server.mobile_playlists, "get_playlist", lambda *_a: playlist)
    monkeypatch.setattr(server.mobile_playlists, "list_playlists", lambda *_a, **_k: [playlist])
    monkeypatch.setattr(server.mobile_playlists, "_subscriptions",
                        lambda: SimpleNamespace(tables_present=lambda _conn: False))
    monkeypatch.setattr(server.taste_scoring, "build_taste_profile", lambda _idx: {})
    monkeypatch.setattr(server.taste_scoring, "make_filter",
                        lambda *_a: lambda _entry: {"capture": True})
    handler = SimpleNamespace(_send_json=lambda status, body: (status, body),
                              _parse_monitored_playlist_id=lambda _body: (1, None))
    handle = (server.Handler._handle_monitored_playlist_poll if endpoint == "poll"
              else server.Handler._handle_auto_uoink_scan)
    if endpoint == "mcp":
        monkeypatch.setattr(uoink_mcp_tools, "_backend", server)

        def handle(_handler, body):
            return 200, uoink_mcp_tools.poll_monitored_playlist(body)

    block(network, URL)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(server._fetch_metadata, URL)
        try:
            assert network.started[URL].wait(1)
            second = pool.submit(handle, handler, {"playlist_id": 1})
            assert network.limiter._condition.waiting.wait(1)
            assert idx._lock.acquire(blocking=False), "playlist wait held the index lock"
            idx._lock.release()
            assert not server._extract_lock.locked()
            assert len(network.calls) == 1
        finally:
            network.blocks[URL].set()
        first.result(timeout=2)
        status, body = second.result(timeout=2)
    assert status == 200 and body["ok"]
    items = body["captured"] if endpoint == "scan" else body["new"]
    assert len(items) == 1 and items[0]["video_id"] == "abcdef12345"
    assert len(network.calls) == 2
    assert "--flat-playlist" in network.calls[1]["cmd"]
    assert_serial(network.calls)


def test_playlist_discovery_preserves_entry_fields_and_errors(network, monkeypatch):
    cp = subprocess.CompletedProcess([], 0, '\n'.join([
        '', 'not JSON', '{}',
        json.dumps({"id": "first123456", "title": "First", "channel": "Channel"}),
        json.dumps({"id": "other123456", "title": "Other", "uploader": "Uploader"}),
        json.dumps({"id": "third123456", "uploader_id": "@handle"}),
    ]), '')
    run = Mock(return_value=cp)
    monkeypatch.setattr(server, "_run_subprocess", run)
    assert server._fetch_monitored_playlist_entries(URL) == [
        {"video_id": "first123456", "title": "First", "channel": "Channel"},
        {"video_id": "other123456", "title": "Other", "channel": "Uploader"},
        {"video_id": "third123456", "title": None, "channel": "@handle"},
    ]
    assert run.call_args.kwargs["timeout"] == server.mobile_playlists._PLAYLIST_LIST_TIMEOUT_SEC
    cp.returncode = 1
    cp.stderr = "ERROR: playlist unavailable"
    with pytest.raises(RuntimeError, match="ERROR: playlist unavailable"):
        server._fetch_monitored_playlist_entries(URL)


@pytest.fixture
def mcp_capture(network, monkeypatch, tmp_path):
    monkeypatch.setattr(uoink_mcp_tools, "_backend", server)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(server._ManualOwnership, "corpus_row", staticmethod(lambda _id: None))
    monkeypatch.setattr(server, "_classify_topic", lambda _metadata: "Test")
    monkeypatch.setattr(server, "_record_single_extract_job", Mock())

    def extract(url, _interval, folder, **_kwargs):
        assert server._manual_capture_key(url) in server._ServerCaptureBackend._local_identities
        server._run_subprocess([*server.YTDLP_CMD, "-f", "best", url])
        server._run_subprocess([*server.YTDLP_CMD, "--skip-download", "--write-subs", url])
        assert server._extract_lock.locked()
        return {"folder": str(folder), "yoink_md": "fixture capture"}

    monkeypatch.setattr(server, "_run_extraction", extract)


def test_mcp_capture_waits_without_process_lock(network, mcp_capture):
    block(network, URL)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(server._fetch_metadata, URL)
        try:
            assert network.started[URL].wait(1)
            second = pool.submit(uoink_mcp_tools.uoink_video, {"url": URL})
            assert network.limiter._condition.waiting.wait(1)
            assert server._extract_lock.acquire(blocking=False), "MCP wait held the process lock"
            server._extract_lock.release()
            assert len(network.calls) == 1
        finally:
            network.blocks[URL].set()
        first.result(timeout=2)
        result = second.result(timeout=2)
    assert result["ok"] and result["corpus_md"] == "fixture capture"
    assert len(network.calls) == 4
    assert_serial(network.calls)
    assert all(call["process_lock_held"] for call in network.calls[1:])
    assert not server._extract_lock.locked()
    server._record_single_extract_job.assert_called_once()


def test_mcp_capture_yields_process_lock_during_each_cooldown(network, mcp_capture, monkeypatch):
    now = [100.0]
    limiter = server._YouTubeCallLimiter(jitter=lambda: 3, clock=lambda: now[0])
    waits = []

    def advance(timeout=None):
        assert server._extract_lock.acquire(blocking=False), "MCP cooldown held the process lock"
        server._extract_lock.release()
        waits.append(timeout)
        now[0] += timeout

    monkeypatch.setattr(limiter._condition, "wait", advance)
    monkeypatch.setattr(server, "_youtube_call_limiter", limiter)
    network.clock = lambda: now[0]
    result = uoink_mcp_tools.uoink_video({"url": URL})
    assert result["ok"]
    assert [call["clock"] for call in network.calls] == pytest.approx([100, 103, 106])
    assert sum(waits) == pytest.approx(6)
    assert all(call["process_lock_held"] for call in network.calls)
    assert not server._extract_lock.locked()


@pytest.mark.parametrize("owner_kind", ["manual", "mcp"])
def test_mcp_and_manual_captures_reuse_completion_while_paced(
        network, mcp_capture, monkeypatch, tmp_path, owner_kind):
    entered = threading.Event()
    finish = threading.Event()
    published = {}
    corpus = tmp_path / "capture.md"
    monkeypatch.setattr(server.source_subscriptions, "MANUAL_CAPTURE_LOCK_TIMEOUT_S", 0)
    monkeypatch.setattr(server._ManualOwnership, "corpus_row",
                        staticmethod(lambda _id: published.get("row")))
    service = SimpleNamespace(publication_evidence_for_reuse=Mock(
        return_value=SimpleNamespace(complete=True)))
    monkeypatch.setattr(server, "_source_service", lambda: service)
    monkeypatch.setattr(server, "_get_index", Mock(side_effect=OSError("fixture has no index")))

    def publish():
        entered.set()
        assert finish.wait(2)
        corpus.write_text("Completed fixture capture", encoding="utf-8")
        published["row"] = {"title": "Completed capture", "metadata_json": "{}",
                            "corpus_path": str(corpus)}
        return {"folder": str(tmp_path), "yoink_md": corpus.read_text(encoding="utf-8")}

    extract = Mock(side_effect=lambda *_a, **_k: publish())
    monkeypatch.setattr(server, "_run_extraction", extract)

    def manual():
        with server._manual_extraction_ownership(URL) as ownership:
            assert ownership.ok
            if owner_kind == "manual":
                return publish()
            assert ownership.completed_while_waiting
            assert ownership.reused["reused"]
            return ownership.reused

    def mcp():
        result = uoink_mcp_tools.uoink_video({"url": URL})
        assert result["ok"] and result["corpus_md"] == "Completed fixture capture"
        return result

    owner, waiter = (manual, mcp) if owner_kind == "manual" else (mcp, manual)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(owner)
        try:
            assert entered.wait(1)
            second = pool.submit(waiter)
            assert server._ServerCaptureBackend._identity_condition.waiting.wait(1)
            assert not second.done()
        finally:
            finish.set()
        first.result(timeout=2)
        second.result(timeout=2)
    assert len(network.calls) == (1 if owner_kind == "mcp" else 0)
    assert extract.call_count == (1 if owner_kind == "mcp" else 0)
    service.publication_evidence_for_reuse.assert_called_once_with("abcdef12345")
    assert not server._ServerCaptureBackend._local_identities
    assert not server._extract_lock.locked()


def test_channel_context_fetch_has_a_timeout(monkeypatch):
    run = Mock(side_effect=subprocess.TimeoutExpired(cmd="yt-dlp", timeout=1))
    monkeypatch.setattr(server, "_run_subprocess", run)
    assert server._fetch_channel_context("https://youtube.com/@example") == {
        "description": "", "recent_videos": []}
    assert run.call_args.kwargs["timeout"] == server.COMMENTS_TIMEOUT_SEC


@pytest.mark.parametrize("reused", [
    {"reused": True, "corpus_path": None, "folder": None},
    {"reused": True, "corpus_path": None},
])
def test_mcp_reuse_without_paths_returns_an_error_not_a_crash(monkeypatch, tmp_path, reused):
    monkeypatch.setattr(uoink_mcp_tools, "_backend", server)
    monkeypatch.setattr(server, "DESKTOP_ROOT", tmp_path)
    monkeypatch.setattr(server, "_record_single_extract_job", Mock())
    ownership = SimpleNamespace(raise_if_unavailable=lambda: None, conflict=None,
                                completed_while_waiting=True, reused=dict(reused))

    @contextmanager
    def owned(_url):
        yield ownership

    monkeypatch.setattr(server, "_manual_extraction_ownership", owned)
    result = uoink_mcp_tools.uoink_video({"url": URL})
    assert result["ok"] is False
    assert "could not find its folder" in str(result)

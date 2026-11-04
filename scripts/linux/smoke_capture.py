"""Offline capture-image smoke. Fixture: episode.mp3 and expected.txt (one word
per line, in preference order; any listed word may match the transcription).
Run as uid 10001 with --network none and the installed app at /opt/uoink.
"""
from __future__ import annotations

import argparse
from collections import deque
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request


@contextmanager
def fixture_server(directory):
    audio = (directory / "episode.mp3").read_bytes()
    assert audio, "episode.mp3 is empty"

    class Handler(BaseHTTPRequestHandler):
        def serve(self, *, head=False):
            if self.path == "/feed.xml":
                body, content_type = feed, "application/rss+xml"
            elif self.path == "/episode.mp3":
                body, content_type = audio, "audio/mpeg"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def do_GET(self):
            self.serve()

        def do_HEAD(self):
            self.serve(head=True)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as httpd:
        origin = f"http://127.0.0.1:{httpd.server_port}"
        # Neither expected word appears in metadata: search must find ASR text.
        feed = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Capture fixture</title><link>{origin}/</link>
<description>Local test audio.</description><item>
<title>Offline capture sample</title>
<guid isPermaLink="false">uoink-capture-fixture-1</guid>
<pubDate>{format_datetime(datetime.now(timezone.utc))}</pubDate>
<enclosure url="{origin}/episode.mp3" type="audio/mpeg" length="{len(audio)}"/>
</item></channel></rss>'''.encode("utf-8")
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield origin
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


@contextmanager
def allow_fixture_origin(guards, origin):
    """The only test seam: admit this exact loopback origin in this process."""
    originals = {name: getattr(guards, name) for name in (
        "public_http_open", "resolve_public_http_url", "check_public_http_url")}
    authority = urllib.parse.urlsplit(origin).netloc

    def is_fixture(url):
        try:
            parsed = urllib.parse.urlsplit(url)
            return (parsed.scheme == "http" and parsed.netloc == authority
                    and not parsed.fragment and not any(ord(c) < 33 for c in url))
        except (TypeError, ValueError):
            return False

    class NoRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    # The fixture never redirects. Refuse any redirect instead of letting a
    # test-only urllib opener carry the allowance to another destination.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())

    def public_http_open(url, *, headers=None, timeout=30, method="GET", follow_redirects=True):
        if is_fixture(url):
            return opener.open(urllib.request.Request(
                url, headers=headers or {}, method=method), timeout=timeout)
        return originals["public_http_open"](
            url, headers=headers, timeout=timeout, method=method,
            follow_redirects=follow_redirects)

    def resolve_public_http_url(url, **kwargs):
        if is_fixture(url):
            return url
        return originals["resolve_public_http_url"](url, **kwargs)

    def check_public_http_url(url):
        if is_fixture(url):
            return url
        return originals["check_public_http_url"](url)

    guards.public_http_open = public_http_open
    guards.resolve_public_http_url = resolve_public_http_url
    guards.check_public_http_url = check_public_http_url
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(guards, name, original)


def mcp_search(arguments):
    """Fresh CLI process; use the bounded line-reader pattern from smoke_stdio."""
    child = subprocess.Popen(
        ["uoink", "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", env=os.environ.copy())
    responses = queue.Queue()
    errors = deque(maxlen=30)

    def drain_stdout():
        for line in child.stdout:
            responses.put(line)
        responses.put(None)

    def drain_stderr():
        for line in child.stderr:
            errors.append(line.rstrip())

    threads = [threading.Thread(target=drain_stdout, daemon=True),
               threading.Thread(target=drain_stderr, daemon=True)]
    for thread in threads:
        thread.start()

    def send(message):
        child.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        child.stdin.flush()

    def receive(request_id):
        deadline = time.monotonic() + 60
        while True:
            try:
                line = responses.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise AssertionError("MCP response timed out: " + "\n".join(errors)) from None
            assert line is not None, "MCP exited: " + "\n".join(errors)
            reply = json.loads(line)
            assert reply.get("jsonrpc") == "2.0", reply
            if "method" in reply and "id" not in reply:
                continue
            assert reply.get("id") == request_id and "result" in reply, reply
            return reply["result"]

    try:
        send({"id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "uoink-capture-smoke", "version": "1"}}})
        initialized = receive(1)
        assert initialized["serverInfo"]["version"], initialized
        assert "tools" in initialized["capabilities"], initialized
        send({"method": "notifications/initialized"})
        send({"id": 2, "method": "tools/call", "params": {
            "name": "search_uoinks", "arguments": arguments}})
        result = receive(2)
        assert not result.get("isError"), result
        texts = [part["text"] for part in result["content"] if part.get("type") == "text"]
        assert len(texts) == 1, result
        payload = json.loads(texts[0])
        assert payload.get("ok") is True, payload
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=2)
        child.stdout.close()
        child.stderr.close()
    assert child.returncode == 0, list(errors)
    return payload


class Smoke:
    def __init__(self):
        self.steps = []
        self.last_call = None
        self.transcript = None

    @contextmanager
    def step(self, name):
        started = time.monotonic()
        ok = False
        try:
            yield
            ok = True
        finally:
            self.steps.append({"step": name, "ok": ok,
                               "elapsed": round(time.monotonic() - started, 3)})

    def call(self, backend, name, arguments):
        from uoink_agent_runtime import call_tool
        self.last_call = {"tool": name, "arguments": arguments, "payload": None}
        payload = call_tool(name, arguments, backend)
        self.last_call["payload"] = payload
        assert isinstance(payload, dict) and payload.get("ok") is True, self.last_call
        return payload

    def run(self, directory, profile):
        sys.path.insert(0, "/opt/uoink")
        with self.step("initialize_backend"):
            assert os.getuid() == 10001, "Run the image as uoink (uid 10001)"
            assert os.environ.get("HF_HUB_OFFLINE") == "1", "Offline model loading is required"
            import uoink_install_isolation
            uoink_install_isolation.apply_from_process([
                "--isolated-profile", str(profile), "--isolated-port", "18192"])
            import server
            import uoink_mcp_tools
            uoink_mcp_tools.bind_backend(server)
            assert server.DATA_ROOT.resolve() == profile.resolve()
            assert server.PORT == 18192
            assert server.whisper_runner.transcription_engine() == "faster-whisper"
            model = server._reliability_model_status("base")
            assert model["cached"] and model["source"] == "bundled", model
            words = [line.strip() for line in (directory / "expected.txt").read_text(
                encoding="utf-8").splitlines() if line.strip()]
            assert words, "expected.txt must contain at least one search word"

        with fixture_server(directory) as origin, allow_fixture_origin(server.source_subscriptions, origin):
            with self.step("add_podcast_feed"):
                added = self.call(server, "add_podcast_feed", {"feed_url": origin + "/feed.xml"})
                feed_id = added["feed"]["id"]
                assert isinstance(feed_id, int), added
            with self.step("poll_podcast_feed"):
                polled = self.call(server, "poll_podcast_feed", {"feed_id": feed_id})
                assert polled["inserted"] == 1, polled
            with self.step("list_podcast_episodes"):
                listed = self.call(server, "list_podcast_episodes", {"feed_id": feed_id})
                assert listed["count"] == 1, listed
                episode = listed["episodes"][0]
                episode_id = episode["id"]
                assert episode["audio_url"] == origin + "/episode.mp3", listed
            with self.step("download_podcast_episode"):
                downloaded = self.call(server, "download_podcast_episode", {"episode_id": episode_id})
                audio = Path(downloaded["local_path"])
                assert audio.is_relative_to(profile) and audio.stat().st_size > 0, downloaded
                assert not downloaded.get("skipped_existing"), downloaded
                # yt-dlp may skip re-encoding an MP3 enclosure. Still require
                # the installed ffmpeg to decode the actual downloaded bytes.
                decoded = subprocess.run([
                    "ffmpeg", "-nostdin", "-v", "error", "-i", str(audio), "-f", "null", "-"],
                    capture_output=True, text=True, timeout=30)
                assert decoded.returncode == 0, decoded.stderr
            with self.step("transcribe_podcast_episode"):
                queued = self.call(server, "transcribe_podcast_episode", {
                    "episode_id": episode_id, "model": "base", "diarize": True, "consent_given": False})
                job_id = queued["job_id"]
                assert isinstance(job_id, str) and job_id, queued
            with self.step("get_job_status"):
                deadline = time.monotonic() + 300
                while True:
                    status = self.call(server, "get_job_status", {"job_id": job_id})
                    job = status["job"]
                    assert job["state"] not in ("failed", "cancelled"), status
                    if job["state"] == "completed":
                        break
                    assert time.monotonic() < deadline, {"error": "Transcription timed out", **status}
                    time.sleep(0.25)
                # The terminal state is written just before the worker releases
                # its capture lock. Drain as the CLI does before publishing.
                from uoink_cli import finish_call_work
                finish_call_work(server, "transcribe_podcast_episode", queued, set(threading.enumerate()))
                transcript_path = Path(job["result"]["transcript_path"])
                assert transcript_path.is_relative_to(profile), job
                self.transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
                assert self.transcript["engine"] == "faster-whisper", self.transcript
                assert self.transcript["model"] == "base" and self.transcript["language"], self.transcript
                assert self.transcript["diarization_ran"] is False, self.transcript
                assert "diarization_run" not in self.transcript, self.transcript
                text = " ".join(segment["text"] for segment in self.transcript["segments"])
                word = next((word for word in words if re.search(
                    r"\b" + re.escape(word) + r"\b", text, re.IGNORECASE)), None)
                assert word, {"expected_any": words, "transcript": self.transcript}
            with self.step("episode_to_corpus"):
                published = self.call(server, "episode_to_corpus", {"episode_id": episode_id})
                assert published["episode_id"] == episode_id and published["segments"] > 0, published
                assert Path(published["corpus_path"]).is_file(), published
                video_id = published["video_id"]
            search_args = {"query": word, "mode": "keyword"}
            with self.step("search_uoinks"):
                found = self.call(server, "search_uoinks", search_args)
                assert any(row["video_id"] == video_id for row in found["results"]), found

        # The fresh process inherits isolation, but no monkeypatches. Its
        # search must read the persisted index and transcript-derived corpus.
        with self.step("mcp_search_uoinks"):
            self.last_call = {"tool": "MCP search_uoinks", "arguments": search_args, "payload": None}
            found = mcp_search(search_args)
            self.last_call["payload"] = found
            assert any(row["video_id"] == video_id for row in found["results"]), found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    smoke = Smoke()
    ok = False
    try:
        with tempfile.TemporaryDirectory(prefix="uoink-capture-") as directory:
            # Import-time log handlers and capture prints must leave stdout for
            # the compact JSON report, just as in uoink_cli.backend().
            with redirect_stdout(sys.stderr):
                smoke.run(args.fixture.resolve(), Path(directory))
        ok = True
    except (Exception, SystemExit):
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"failing_tool": smoke.last_call, "transcript": smoke.transcript},
                         ensure_ascii=False), file=sys.stderr)
    print(json.dumps({"ok": ok, "steps": smoke.steps}, separators=(",", ":")))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""G-43 / E2E D4 + D5 -- retries-exhausted uoinks get an honest terminal
state, and the retry worker stops promising a retry after the final attempt.

Run: python tests/test_retry_exhaustion_g43.py

Before the fix:
  D5: after attempt 3 of a rate-limited pending row, the worker logged
      "still rate-limited; retry at ... (backoff ...)" while
      mark_pending_failed silently struck the row out -- the promised
      attempt 4 never ran, and log + queue state disagreed.
  D4: the struck-out row also vanished from /queue/status (terminal rows
      are not listed) with no job recorded, so the only user-visible trace
      of the uoink was rate-limit error text the dashboard renders as
      "Uoink needs a minute. Retrying..." forever.

After the fix:
  - Index.mark_pending_failed returns the resulting status ('pending' /
    'failed' / '') so callers can see a strike-out happen. Red on main:
    it returned None.
  - On the final strike the worker logs "gave up after N attempts", never
    "retry at ...", persists honest last_error copy, and records a
    terminal failed job with retry_exhausted=true + attempt_count so
    Activity shows the uoink honestly. Red on main: phantom "retry at"
    log, last_error "youtube_rate_limit", no job at all.
  - friendly_error's rate-limit copy stops promising "Retrying..." in
    terminal contexts.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import server  # noqa: E402


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def _past():
    return (datetime.now() - timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%S")


def _rate_limit_error():
    return subprocess.CalledProcessError(
        returncode=1, cmd=["yt-dlp"],
        stderr=b"ERROR: HTTP Error 429: Too Many Requests")


def main():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    server._get_index = lambda: idx  # type: ignore

    def _raise_429(url):
        raise _rate_limit_error()

    orig_fetch = server._fetch_metadata
    server._fetch_metadata = _raise_429  # type: ignore

    capture = _ListHandler()
    server.log.addHandler(capture)
    server.log.setLevel(logging.DEBUG)

    try:
        # 1. mark_pending_failed reports the resulting status.
        #    Red on main: the method returned None.
        pid = idx.enqueue_pending("https://youtu.be/gone", 30, _past())
        status = idx.mark_pending_failed(pid, "youtube_rate_limit", _past())
        _assert(status == "pending",
                f"attempt 1 must re-queue and say so, got {status!r}")
        status = idx.mark_pending_failed(pid, "youtube_rate_limit", _past())
        _assert(status == "pending",
                f"attempt 2 must re-queue and say so, got {status!r}")
        status = idx.mark_pending_failed(pid, "final copy", _past())
        _assert(status == "failed",
                f"attempt 3 must strike out and say so, got {status!r}")
        _assert(idx.mark_pending_failed(999999, "x", _past()) == "",
                "unknown pending_id must return ''")
        idx.cancel_pending(pid)  # keep it out of next_pending below
        print("ok  mark_pending_failed returns pending/failed/''")

        # 2. A non-final attempt still schedules a retry and logs it.
        url = "https://youtu.be/dQw4w9WgXcQ"
        pid = idx.enqueue_pending(url, 30, _past())
        capture.lines.clear()
        _assert(server._retry_pending_one() is True, "worker processed row")
        row = [r for r in idx.list_pending(limit=10, include_terminal=True)
               if r["pending_id"] == pid][0]
        _assert(row["status"] == "pending",
                f"attempt 1 of 3 must re-queue, got {row['status']}")
        _assert(any("retry at" in ln for ln in capture.lines),
                f"non-final attempt logs the scheduled retry: {capture.lines}")
        print("ok  non-final attempt -> re-queued, retry logged")

        # 3. Final attempt: no phantom retry, honest terminal state.
        idx.mark_pending_failed(pid, "youtube_rate_limit", _past())
        # row is now at attempt_count=2; the next worker pass is strike 3.
        capture.lines.clear()
        _assert(server._retry_pending_one() is True, "worker processed row")

        _assert(not any("retry at" in ln for ln in capture.lines),
                f"D5 red: final attempt logged a phantom retry: "
                f"{capture.lines}")
        _assert(any("gave up after 3 attempts" in ln
                    for ln in capture.lines),
                f"final attempt must log giving up: {capture.lines}")

        row = [r for r in idx.list_pending(limit=10, include_terminal=True)
               if r["pending_id"] == pid][0]
        _assert(row["status"] == "failed",
                f"row must be terminal, got {row['status']}")
        _assert(row["attempt_count"] == 3, f"attempts: {row['attempt_count']}")
        _assert("Retrying" not in (row["last_error"] or ""),
                f"terminal last_error must not promise a retry: "
                f"{row['last_error']}")
        _assert("stopped after 3 attempts" in (row["last_error"] or ""),
                f"terminal last_error says Uoink stopped: {row['last_error']}")

        jobs = [j for j in server._jobs.values()
                if j.get("source_url") == url]
        _assert(len(jobs) == 1,
                f"D4 red: no terminal job was recorded, got {len(jobs)}")
        job = server._public_job(jobs[0])
        _assert(job["state"] == "failed", f"job state: {job['state']}")
        _assert(job["retry_exhausted"] is True,
                f"job carries retry_exhausted: {job}")
        _assert(job["attempt_count"] == 3, f"job attempt_count: {job}")
        _assert("Retrying" not in (job["error"] or ""),
                f"job error must not promise a retry: {job['error']}")
        _assert("won't retry it on its own" in (job["error"] or ""),
                f"job error says no more retries: {job['error']}")
        _assert(job["message"] == "Uoink stopped after 3 attempts.",
                f"job message: {job['message']}")
        # The shipped dashboard prioritises error_detail when translating;
        # the detail must not contain any string its rate-limit matcher
        # turns into "Uoink needs a minute. Retrying..." (documented for
        # the frontend agent in the PR body).
        detail = (job["error_detail"] or "").lower()
        for needle in ("too many requests", "http error 429",
                       "rate-limit", "rate limit"):
            _assert(needle not in detail,
                    f"detail would re-trigger Retrying... copy: {detail}")
        print("ok  final attempt -> honest terminal queue row + job, "
              "no phantom retry")

        # 4. Ordinary jobs don't inherit the flag.
        plain = server._record_single_extract_job(
            "https://youtu.be/other0000ab", server._now_iso(),
            error="boom")
        _assert(plain["retry_exhausted"] is False,
                f"plain failed job must not claim exhaustion: {plain}")
        print("ok  plain failed jobs carry retry_exhausted=false")

        # 5. Rate-limit copy in terminal contexts stops saying Retrying...
        msg = server._plain_error_from_text(
            "HTTP Error 429: Too Many Requests")
        _assert("Retrying" not in msg,
                f"friendly rate-limit copy still promises a retry: {msg}")
        _assert("retry" in msg.lower(),
                f"copy should point at a user retry: {msg}")
        print("ok  friendly rate-limit copy is honest")

        print("\nall green")
    finally:
        server.log.removeHandler(capture)
        server._fetch_metadata = orig_fetch  # type: ignore
        idx.close()
        tmp.cleanup()


if __name__ == "__main__":
    main()

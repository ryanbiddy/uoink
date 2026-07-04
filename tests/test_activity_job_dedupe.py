"""G-14 -- Activity shows one row per single-video source (QA #42).

Run: python tests/test_activity_job_dedupe.py

Root cause: every /extract attempt mints a fresh job id, so re-extracting a
URL (rate-limit retry, retry worker, or a re-yoink) left a second failed
`single` job in _jobs. Both rendered in Activity as identical failed rows
(the OpenClaw job twice). The frontend dedupe only covers job-vs-queue,
never job-vs-job, so the backend now coalesces: a new single-video attempt
supersedes any prior terminal attempt for the same source URL.

This drives _record_single_extract_job (the real /extract code path) against
a real index and asserts /jobs returns a single row, and that a later
success replaces the earlier failure.

Red before the fix: two failed attempts -> two job rows.
"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import server  # noqa: E402

URL = "https://www.youtube.com/watch?v=openclaw123"
OTHER = "https://www.youtube.com/watch?v=different999"


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _single_jobs_for(url):
    return [j for j in server._list_public_jobs("single")
            if j.get("source_url") == url]


def main():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    server._get_index = lambda: idx  # type: ignore
    with server._jobs_lock:
        server._jobs.clear()
    try:
        # First failed attempt (e.g. YouTube rate-limit surfaced as failure).
        server._record_single_extract_job(
            URL, server._now_iso(), error="YouTube is rate-limiting.",
            failure_phase="fetch")
        _assert(len(_single_jobs_for(URL)) == 1, "one job after first attempt")

        # Second failed attempt for the SAME url (a retry). Pre-fix this left
        # two failed rows; now it supersedes.
        server._record_single_extract_job(
            URL, server._now_iso(), error="YouTube is rate-limiting.",
            failure_phase="fetch")
        rows = _single_jobs_for(URL)
        _assert(len(rows) == 1,
                f"retry must supersede, not duplicate: {len(rows)} rows")

        # A different URL is untouched -- coalescing is per source.
        server._record_single_extract_job(
            OTHER, server._now_iso(), error="boom", failure_phase="fetch")
        _assert(len(_single_jobs_for(URL)) == 1, "other url doesn't touch URL")
        _assert(len(_single_jobs_for(OTHER)) == 1, "other url recorded once")

        # A later SUCCESS for URL replaces the failed row (one row, completed).
        folder = Path(tmp.name) / "vid"
        folder.mkdir()
        server._record_single_extract_job(
            URL, server._now_iso(),
            result={"title": "OpenClaw", "folder": str(folder),
                    "screenshot_count": 3})
        rows = _single_jobs_for(URL)
        _assert(len(rows) == 1, f"success supersedes failure: {len(rows)} rows")
        _assert(rows[0]["state"] == "completed",
                f"surviving row is the success: {rows[0]['state']}")

        # The index agrees (no orphaned superseded rows persisted).
        persisted = [j for j in idx.list_jobs(kind="single", limit=100)
                     if (__import__("json").loads(j["metadata_json"] or "{}")
                         .get("source_url") == URL)]
        _assert(len(persisted) == 1,
                f"index also holds one row for URL: {len(persisted)}")
        print("ok  single-video retries coalesce to one Activity row")
        print("ok  later success supersedes the failed attempt")
        print("ok  index has no orphaned superseded rows")
    finally:
        with server._jobs_lock:
            server._jobs.clear()
        idx.close()
        tmp.cleanup()
    print("\nALL ACTIVITY JOB DEDUPE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

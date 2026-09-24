"""BA-5: activity storage waits consume the original transport deadline."""
import json
import sqlite3
import time
from datetime import datetime, timezone

import library_analysis as analysis
import library_resources
from tests import test_library_analysis_fixtures as seed
from tests.test_phase5_az5h import _activity_call, _run_stdio


def test_ba5_activity_storage_wait_keeps_inbound_elapsed_time(tmp_path, monkeypatch):
    conn = seed.create_fixture_db(tmp_path)
    seed.insert_yoink(conn, "ba5", yoinked_at="2026-09-05T12:00:00.000Z")
    conn.commit()
    conn.execute("PRAGMA journal_mode=DELETE")
    database = conn.execute("PRAGMA database_list").fetchone()[2]
    blocker = sqlite3.connect(database, timeout=0)
    blocker.execute("BEGIN EXCLUSIVE")
    analysis.reset_rate_limiter()
    monkeypatch.setattr(analysis, "_analysis_db_override", conn)
    original_read = analysis.get_library_activity
    original_clock = time.monotonic
    shift = [0.0]
    admitted = []

    def dispatched_after_elapsed_time(args):
        scope = library_resources.current_transport_scope()
        assert scope is not None and scope.owns_slot
        admitted.append(scope.admitted_at)
        # Time already spent between inbound admission and domain dispatch.
        # The real SQLite EXCLUSIVE holder then exercises the remaining wait.
        shift[0] += 1.5
        return original_read(args, clock=datetime(2026, 9, 8, 12, tzinfo=timezone.utc))

    monkeypatch.setattr(time, "monotonic", lambda: original_clock() + shift[0])
    monkeypatch.setattr(analysis, "get_library_activity", dispatched_after_elapsed_time)
    try:
        response = _run_stdio([_activity_call()])[0]
        finished = time.monotonic()
        assert len(admitted) == 1
        result = response["result"]
        assert result["isError"]
        envelope = json.loads(result["content"][0]["text"])
        assert envelope["error"]["code"] == "deadline_exceeded"
        assert finished - admitted[0] <= 2.25, \
            "Activity storage wait reset the original transport deadline"
        assert library_resources.process_guard()._active == 0
    finally:
        blocker.rollback()
        blocker.close()
        conn.close()
        analysis.reset_rate_limiter()


def test_ba5_actual_refusal_frame_stays_within_wire_cap(tmp_path, monkeypatch):
    conn = seed.create_fixture_db(tmp_path)
    seed.insert_yoink(conn, "ba5-wire", yoinked_at="2026-09-05T12:00:00.000Z")
    conn.commit()
    analysis.reset_rate_limiter()
    monkeypatch.setattr(analysis, "_analysis_db_override", conn)
    original_read = analysis.get_library_activity
    monkeypatch.setattr(analysis, "get_library_activity", lambda args: original_read(
        args, clock=datetime(2026, 9, 8, 12, tzinfo=timezone.utc)))
    try:
        # JSON-RPC permits string IDs. The bounded entry must reject an
        # excessive envelope before echoing an unbounded refusal frame.
        response = _run_stdio([_activity_call("r" * 65536)])[0]
        actual_bytes = len(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode())
        assert actual_bytes <= 65536, f"Actual refusal frame used {actual_bytes} bytes"
        assert "error" in response or response.get("result", {}).get("isError")
        assert library_resources.process_guard()._active == 0
    finally:
        analysis.reset_rate_limiter()
        conn.close()

"""AZ-5h2 implementation tests: inbound deadline and completed-frame cap.

Frozen BA-4/BA-5 acceptance files are not edited. These cases drive
``uoink_mcp.bounded_stdio_server``, the shipped stdio entry.
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from mcp import types as mcp_types

import library_analysis as analysis
import library_resources
from tests import test_library_analysis_fixtures as seed
from tests.test_phase5_az5h import (
    NOW,
    _activity_call,
    _run_stdio,
)


WIRE_CAP = 65536


@pytest.fixture(autouse=True)
def isolate_reader(monkeypatch):
    analysis.reset_rate_limiter()
    monkeypatch.setattr(analysis, "_analysis_db_override", None)
    yield
    analysis.reset_rate_limiter()


@pytest.fixture
def db(tmp_path: Path):
    conn = seed.create_fixture_db(tmp_path)
    yield conn
    conn.close()


def _frame_bytes(response) -> int:
    return len(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode())


def _bind_clocked_reader(monkeypatch, conn):
    monkeypatch.setattr(analysis, "_analysis_db_override", conn)
    original_read = analysis.get_library_activity
    monkeypatch.setattr(
        analysis, "get_library_activity",
        lambda args: original_read(args, clock=NOW),
    )
    return original_read


def test_az5h2_expired_inbound_refuses_before_storage(db, monkeypatch):
    seed.insert_yoink(db, "az5h2", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    original_read = analysis.get_library_activity
    original_connect = analysis._get_connection
    original_clock = time.monotonic
    shift = [0.0]
    storage = []

    def dispatched(args):
        scope = library_resources.current_transport_scope()
        assert scope is not None and scope.owns_slot
        shift[0] += 2.1
        return original_read(args, clock=NOW)

    def connect():
        storage.append(True)
        return original_connect()

    monkeypatch.setattr(analysis, "get_library_activity", dispatched)
    monkeypatch.setattr(analysis, "_get_connection", connect)
    monkeypatch.setattr(time, "monotonic", lambda: original_clock() + shift[0])

    response = _run_stdio([_activity_call()])[0]
    result = response["result"]
    assert result["isError"]
    envelope = json.loads(result["content"][0]["text"])
    assert envelope["error"]["code"] == "deadline_exceeded"
    assert storage == []
    assert library_resources.process_guard()._active == 0


def test_az5h2_remaining_budget_sqlite_wait_keeps_inbound_deadline(tmp_path, monkeypatch):
    conn = seed.create_fixture_db(tmp_path)
    seed.insert_yoink(conn, "az5h2-wait", yoinked_at="2026-09-05T12:00:00.000Z")
    conn.commit()
    conn.execute("PRAGMA journal_mode=DELETE")
    database = conn.execute("PRAGMA database_list").fetchone()[2]
    blocker = sqlite3.connect(database, timeout=0)
    blocker.execute("BEGIN EXCLUSIVE")
    monkeypatch.setattr(analysis, "_analysis_db_override", conn)
    original_read = analysis.get_library_activity
    original_clock = time.monotonic
    shift = [0.0]
    admitted = []

    def dispatched(args):
        scope = library_resources.current_transport_scope()
        assert scope is not None and scope.owns_slot
        admitted.append(scope.admitted_at)
        shift[0] += 1.5
        return original_read(args, clock=datetime(2026, 9, 8, 12, tzinfo=timezone.utc))

    monkeypatch.setattr(time, "monotonic", lambda: original_clock() + shift[0])
    monkeypatch.setattr(analysis, "get_library_activity", dispatched)
    try:
        response = _run_stdio([_activity_call()])[0]
        finished = time.monotonic()
        assert len(admitted) == 1
        result = response["result"]
        assert result["isError"]
        envelope = json.loads(result["content"][0]["text"])
        assert envelope["error"]["code"] == "deadline_exceeded"
        assert finished - admitted[0] <= 2.25
        assert library_resources.process_guard()._active == 0
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        blocker.rollback()
        blocker.close()
        conn.close()
        analysis.reset_rate_limiter()


@pytest.mark.parametrize("request_id", [2, "activity-ok"])
def test_az5h2_normal_accepted_ids_are_preserved(db, monkeypatch, request_id):
    seed.insert_yoink(db, "az5h2-id", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    _bind_clocked_reader(monkeypatch, db)
    response = _run_stdio([_activity_call(request_id)])[0]
    assert response["id"] == request_id
    assert "result" in response
    assert response["result"].get("isError") is not True
    assert _frame_bytes(response) <= WIRE_CAP
    assert library_resources.process_guard()._active == 0


def test_az5h2_deadline_and_rate_refusal_frames_stay_within_wire_cap(db, monkeypatch):
    seed.insert_yoink(db, "az5h2-ref", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    _bind_clocked_reader(monkeypatch, db)
    original_dump = mcp_types.JSONRPCMessage.model_dump_json
    original_clock = time.monotonic
    clock_shift = [0.0]

    def expensive_actual_serialization(message, *args, **kwargs):
        text = original_dump(message, *args, **kwargs)
        root = message.root
        if isinstance(root, mcp_types.JSONRPCResponse) and root.id == 2:
            clock_shift[0] += 3.0
        return text

    monkeypatch.setattr(mcp_types.JSONRPCMessage, "model_dump_json", expensive_actual_serialization)
    monkeypatch.setattr(time, "monotonic", lambda: original_clock() + clock_shift[0])
    deadline_response = _run_stdio([_activity_call()])[0]
    envelope = json.loads(deadline_response["result"]["content"][0]["text"])
    assert deadline_response["id"] == 2
    assert envelope["error"]["code"] == "deadline_exceeded"
    assert _frame_bytes(deadline_response) <= WIRE_CAP
    assert library_resources.process_guard()._active == 0

    analysis.reset_rate_limiter()
    guard = library_resources.process_guard()
    guard.admit()
    guard.admit()
    try:
        rate_response = _run_stdio([_activity_call(3)])[0]
        assert rate_response["id"] == 3
        assert "error" in rate_response or rate_response.get("result", {}).get("isError")
        if rate_response.get("result", {}).get("isError"):
            rate_envelope = json.loads(rate_response["result"]["content"][0]["text"])
            assert rate_envelope["error"]["code"] == "rate_limited"
        else:
            assert rate_response["error"]["data"]["error"]["code"] == "rate_limited"
        assert _frame_bytes(rate_response) <= WIRE_CAP
        assert guard._active == 2
    finally:
        guard.release()
        guard.release()
        analysis.reset_rate_limiter()
    assert library_resources.process_guard()._active == 0


def test_az5h2_protocol_rejection_uses_null_id_and_releases_admission(db, monkeypatch):
    seed.insert_yoink(db, "az5h2-proto", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    original_read = _bind_clocked_reader(monkeypatch, db)
    called = []

    def must_not_run(args):
        called.append(True)
        return original_read(args, clock=NOW)

    monkeypatch.setattr(analysis, "get_library_activity", must_not_run)
    response = _run_stdio([_activity_call("r" * 65536)])[0]
    assert called == []
    assert response.get("id") is None
    assert "error" in response
    assert response["error"]["code"] == -32600
    assert _frame_bytes(response) <= WIRE_CAP
    assert library_resources.process_guard()._active == 0


def test_az5h2_typed_error_frame_is_capped(db, monkeypatch):
    seed.insert_yoink(db, "az5h2-typed", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    _bind_clocked_reader(monkeypatch, db)
    original_dump = mcp_types.JSONRPCMessage.model_dump_json
    padded = [False]

    def padded_typed_error(message, *args, **kwargs):
        text = original_dump(message, *args, **kwargs)
        root = message.root
        if (
            not padded[0]
            and isinstance(root, mcp_types.JSONRPCResponse)
            and root.id == 2
            and isinstance(root.result, dict)
            and root.result.get("isError") is True
        ):
            padded[0] = True
            return text + ("x" * 70000)
        return text

    monkeypatch.setattr(mcp_types.JSONRPCMessage, "model_dump_json", padded_typed_error)
    response = _run_stdio([{
        "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "get_library_activity", "arguments": {"interval": "bad"},
        },
    }])[0]
    assert padded[0], "The typed error serializer was not exercised"
    assert response["id"] == 2
    assert "error" in response or response.get("result", {}).get("isError")
    if response.get("result", {}).get("isError"):
        envelope = json.loads(response["result"]["content"][0]["text"])
        assert envelope["error"]["code"] == "resource_too_large"
    assert _frame_bytes(response) <= WIRE_CAP
    assert library_resources.process_guard()._active == 0

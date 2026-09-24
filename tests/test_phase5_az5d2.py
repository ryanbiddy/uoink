"""AZ-5d2 implementation tests: actual stdio handler deadline and nested admission.

Frozen Astra helpers are not edited, replaced, or deselected. The BA-3 unary
clock wrapper case remains a separate reported failure.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

import library_analysis as analysis
import library_resources
import uoink_mcp
from mcp import types as mcp_types
from tests import test_library_analysis_fixtures as seed


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
INTERVAL = {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-07T00:00:00.000Z"}


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


def _call_stdio_handler(args: dict):
    request = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name="get_library_activity", arguments=args),
    )
    return asyncio.run(
        uoink_mcp.mcp._mcp_server.request_handlers[mcp_types.CallToolRequest](request)
    ).root


def test_az5d2_actual_handler_deadline_during_final_wire_serialization(db, monkeypatch):
    """Compatible unary wrapper; elapsed is injected in the adapter's wire_bytes."""
    seed.insert_yoink(db, "a", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)

    real_read = analysis.get_library_activity
    real_wire = library_resources.wire_bytes
    monotonic = time.monotonic
    finished = [False]
    elapsed = [0.0]
    held_during_wire = []
    guard = library_resources.process_guard()

    def compatible_read(args):
        packet = real_read(args, clock=NOW)
        finished[0] = True
        return packet

    def wire(payload):
        if finished[0]:
            held_during_wire.append(guard._active)
            elapsed[0] += 3.0
        return real_wire(payload)

    monkeypatch.setattr(analysis, "get_library_activity", compatible_read)
    monkeypatch.setattr(library_resources, "wire_bytes", wire)
    monkeypatch.setattr(time, "monotonic", lambda: monotonic() + elapsed[0])

    result = _call_stdio_handler({"interval": INTERVAL})
    envelope = json.loads(result.content[0].text)
    assert result.isError
    assert envelope["error"]["code"] == "deadline_exceeded"
    assert envelope["error"]["retryable"] is True
    assert held_during_wire and all(n > 0 for n in held_during_wire), held_during_wire
    assert guard._active == 0


def test_az5d2_nested_adapter_admission_does_not_discard_outer_scope(monkeypatch):
    dummy = {
        "ok": True,
        "schema_version": analysis.SCHEMA_VERSION,
        "contract_version": analysis.CONTRACT_VERSION,
    }
    monkeypatch.setattr(analysis, "_execute_activity", lambda *a, **k: dummy)
    guard = library_resources.process_guard()
    assert guard._active == 0
    with analysis.adapter_admission():
        assert guard._active == 1
        with analysis.adapter_admission():
            assert guard._active == 1
            packet = analysis.get_library_activity({"interval": INTERVAL})
            assert packet is dummy
            assert guard._active == 1
        assert guard._active == 1
    assert guard._active == 0

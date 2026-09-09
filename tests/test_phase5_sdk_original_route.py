"""Independent product cases for the installed SDK stdio route.

Frozen BA-4/AZ-5h files are not edited. These cases drive
`mcp.server.stdio.stdio_server` plus the registered low-level server, and
the shipped `bounded_stdio_server` entry, using disposable fixture data.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import anyio
import pytest
from mcp import types
from mcp.server.stdio import stdio_server

import library_analysis as analysis
import library_resources
import uoink_mcp
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
def db(tmp_path):
    conn = seed.create_fixture_db(tmp_path)
    yield conn
    conn.close()


class _Input:
    def __init__(self, stream):
        self.stream = stream

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.stream.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration


class _Output:
    def __init__(self, stream):
        self.stream = stream

    async def write(self, text):
        await self.stream.send(text)

    async def flush(self):
        pass


def _initialize():
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "sdk-original-route", "version": "1"}}}


def _activity_call(request_id=2):
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {
        "name": "get_library_activity", "arguments": {"interval": INTERVAL}}}


def _run_original_stdio(send_lines, collect=1):
    async def exchange():
        incoming, input_stream = anyio.create_memory_object_stream(4)
        output_stream, outgoing = anyio.create_memory_object_stream(4)
        responses = []

        async def serve():
            async with stdio_server(_Input(input_stream), _Output(output_stream)) as (reads, writes):
                low = uoink_mcp.mcp._mcp_server
                await low.run(reads, writes, low.create_initialization_options())

        async with anyio.create_task_group() as group:
            group.start_soon(serve)
            await incoming.send(json.dumps(_initialize()) + "\n")
            assert json.loads(await outgoing.receive())["id"] == 1
            await incoming.send(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            for line in send_lines:
                await incoming.send(json.dumps(line) + "\n")
            for _ in range(collect):
                responses.append(json.loads(await outgoing.receive()))
            group.cancel_scope.cancel()
        return responses

    return anyio.run(exchange)


def test_original_sdk_route_success_keeps_complete_packet(db, monkeypatch):
    seed.insert_yoink(db, "sdk-ok", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    original_read = analysis.get_library_activity
    monkeypatch.setattr(analysis, "get_library_activity", lambda args: original_read(args, clock=NOW))

    response = _run_original_stdio([_activity_call()])[0]
    assert response["id"] == 2
    result = response["result"]
    assert result.get("isError") is not True
    text = result["content"][0]["text"]
    open_at = text.index(library_resources.DOCUMENT_FENCE_OPEN) + len(library_resources.DOCUMENT_FENCE_OPEN)
    close_at = text.index(library_resources.DOCUMENT_FENCE_CLOSE)
    envelope = json.loads(text[open_at:close_at])
    assert envelope["ok"] is True
    assert envelope["interval"] == INTERVAL
    assert "items" in envelope
    assert "provenance" in envelope
    assert "pagination" in envelope
    assert library_resources.process_guard()._active == 0


def test_original_sdk_route_refuses_expired_actual_serialization(db, monkeypatch):
    seed.insert_yoink(db, "sdk-deadline", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    original_read = analysis.get_library_activity
    monkeypatch.setattr(analysis, "get_library_activity", lambda args: original_read(args, clock=NOW))
    original_dump = types.JSONRPCMessage.model_dump_json
    original_clock = time.monotonic
    clock_shift = [0.0]
    observed_active = []

    def expensive_actual_serialization(message, *args, **kwargs):
        text = original_dump(message, *args, **kwargs)
        if isinstance(message.root, types.JSONRPCResponse) and message.root.id == 2:
            observed_active.append(library_resources.process_guard()._active)
            clock_shift[0] += 3.0
        return text

    monkeypatch.setattr(types.JSONRPCMessage, "model_dump_json", expensive_actual_serialization)
    monkeypatch.setattr(time, "monotonic", lambda: original_clock() + clock_shift[0])

    response = _run_original_stdio([_activity_call()])[0]
    assert response["id"] == 2
    result = response["result"]
    assert observed_active, "The actual SDK serializer was not exercised"
    assert result["isError"], f"Expired actual serialization emitted success; active={observed_active}"
    envelope = json.loads(result["content"][0]["text"])
    assert envelope["error"]["code"] == "deadline_exceeded"
    assert envelope["error"]["retryable"] is True
    assert all(count > 0 for count in observed_active), observed_active
    assert library_resources.process_guard()._active == 0

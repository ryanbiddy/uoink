"""BA-4: observe the shipped SDK's real stdio serialization boundary.

Synthetic database and in-memory byte transport; no model or network.
Existing acceptance helpers are not involved or changed.
"""
import json
import time
from datetime import datetime, timezone

import anyio
from mcp import types
from mcp.server.stdio import stdio_server

import library_analysis as analysis
import library_resources
import uoink_mcp
from tests import test_library_analysis_fixtures as seed


def test_ba4_actual_sdk_serialization_retains_admission_and_deadline(tmp_path, monkeypatch):
    conn = seed.create_fixture_db(tmp_path)
    seed.insert_yoink(conn, "ba4", yoinked_at="2026-09-05T12:00:00.000Z")
    conn.commit()
    analysis.reset_rate_limiter()
    monkeypatch.setattr(analysis, "_analysis_db_override", conn)
    original_read = analysis.get_library_activity
    monkeypatch.setattr(analysis, "get_library_activity", lambda args: original_read(
        args, clock=datetime(2026, 9, 8, 12, tzinfo=timezone.utc)))
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

    class Input:
        def __init__(self, stream):
            self.stream = stream

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return await self.stream.receive()
            except anyio.EndOfStream:
                raise StopAsyncIteration

    class Output:
        def __init__(self, stream):
            self.stream = stream

        async def write(self, text):
            await self.stream.send(text)

        async def flush(self):
            pass

    async def exchange():
        incoming, input_stream = anyio.create_memory_object_stream(4)
        output_stream, outgoing = anyio.create_memory_object_stream(4)

        async def serve():
            async with stdio_server(Input(input_stream), Output(output_stream)) as (reads, writes):
                low = uoink_mcp.mcp._mcp_server
                await low.run(reads, writes, low.create_initialization_options())

        async with anyio.create_task_group() as group:
            group.start_soon(serve)
            await incoming.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "ba4-isolated-review", "version": "1"}}}) + "\n")
            assert json.loads(await outgoing.receive())["id"] == 1
            await incoming.send(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            await incoming.send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "get_library_activity", "arguments": {"interval": {
                    "start": "2026-09-05T00:00:00.000Z", "end": "2026-09-07T00:00:00.000Z"}}}}) + "\n")
            response = json.loads(await outgoing.receive())
            group.cancel_scope.cancel()
        return response

    try:
        response = anyio.run(exchange)
        assert response["id"] == 2
        result = response["result"]
        assert observed_active, "The actual SDK serializer was not exercised"
        assert result["isError"], f"Expired actual serialization emitted success; active admissions={observed_active}"
        envelope = json.loads(result["content"][0]["text"])
        assert envelope["error"]["code"] == "deadline_exceeded"
        assert envelope["error"]["retryable"] is True
        assert all(count > 0 for count in observed_active), observed_active
        assert library_resources.process_guard()._active == 0
    finally:
        analysis.reset_rate_limiter()
        conn.close()

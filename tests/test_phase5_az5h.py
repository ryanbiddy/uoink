"""AZ-5h implementation tests: actual shipped stdio serialization lifetime.

The frozen BA-4 probe uses the installed SDK ``stdio_server`` imported before
this product's transport wrapper and is not edited here. These cases drive
``uoink_mcp.bounded_stdio_server``, the shipped stdio entry.
"""
from __future__ import annotations

from tests.mcp_sdk import replace_handler

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import anyio
import pytest
from mcp import types as mcp_types

import library_analysis as analysis
import library_resources
import uoink_mcp
from tests import test_library_analysis_fixtures as seed


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
INTERVAL = {"start": "2026-09-05T00:00:00.000Z", "end": "2026-09-07T00:00:00.000Z"}
ACTIVITY_ARGS = {"interval": INTERVAL}


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
    def __init__(self, stream, *, fail_id=None):
        self.stream = stream
        self.fail_id = fail_id

    async def write(self, text):
        if self.fail_id is not None:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {}
            if payload.get("id") == self.fail_id:
                raise ConnectionError("broken transport")
        await self.stream.send(text)

    async def flush(self):
        pass


def _initialize():
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "az5h-actual-entry", "version": "1"}}}


def _activity_call(request_id=2):
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {
        "name": "get_library_activity", "arguments": ACTIVITY_ARGS}}


def _run_stdio(send_lines, *, fail_id=None, after_init=None, collect=1, modern=False):
    async def exchange():
        incoming, input_stream = anyio.create_memory_object_stream(8)
        output_stream, outgoing = anyio.create_memory_object_stream(8)
        sink = _Output(output_stream, fail_id=fail_id)
        responses = []

        async def serve():
            async with uoink_mcp.bounded_stdio_server(_Input(input_stream), sink) as (reads, writes):
                low = uoink_mcp.mcp
                await low.run(reads, writes, low.create_initialization_options())

        async with anyio.create_task_group() as group:
            group.start_soon(serve)
            from tests.test_mcp_wire import modern_params
            opening = {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": modern_params()} if modern else _initialize()
            await incoming.send(json.dumps(opening) + "\n")
            init = json.loads(await outgoing.receive())
            assert init["id"] == 1
            if not modern:
                await incoming.send(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            if after_init is not None:
                await after_init(incoming, outgoing)
            for line in send_lines:
                if modern:
                    line = dict(line, params=modern_params(line.get("params")))
                await incoming.send(json.dumps(line) + "\n")
            for _ in range(collect):
                responses.append(json.loads(await outgoing.receive()))
            group.cancel_scope.cancel()
        return responses

    return anyio.run(exchange)


def test_az5h_shipped_entry_is_bounded_stdio():
    from pathlib import Path
    source = Path(uoink_mcp.__file__).read_text(encoding="utf-8")
    assert "anyio.run(run_bounded_stdio_async)" in source
    assert 'mcp.run(reads, writes, mcp.create_initialization_options())' in source


@pytest.mark.parametrize("modern", [False, True])
def test_az5h_actual_stdio_entry_deadline_during_sdk_serialization(db, monkeypatch, modern):
    seed.insert_yoink(db, "az5h", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    original_read = analysis.get_library_activity
    monkeypatch.setattr(analysis, "get_library_activity", lambda args: original_read(args, clock=NOW))
    original_dump = mcp_types.JSONRPCResponse.model_dump_json
    original_clock = time.monotonic
    clock_shift = [0.0]
    observed_active = []

    def expensive_actual_serialization(message, *args, **kwargs):
        text = original_dump(message, *args, **kwargs)
        root = message
        if isinstance(root, mcp_types.JSONRPCResponse) and root.id == 2:
            observed_active.append(library_resources.process_guard()._active)
            clock_shift[0] += 3.0
        return text

    monkeypatch.setattr(mcp_types.JSONRPCResponse, "model_dump_json", expensive_actual_serialization)
    monkeypatch.setattr(time, "monotonic", lambda: original_clock() + clock_shift[0])

    response = _run_stdio([_activity_call()], modern=modern)[0]
    assert response["id"] == 2
    result = response["result"]
    if modern:
        from tests.test_mcp_wire import modern_domain
        result = modern_domain(result)
    else:
        assert "resultType" not in result and "_meta" not in result
    assert observed_active, "The actual SDK serializer was not exercised"
    assert result["isError"], f"Expired actual serialization emitted success; active={observed_active}"
    envelope = json.loads(result["content"][0]["text"])
    assert envelope["error"]["code"] == "deadline_exceeded"
    assert envelope["error"]["retryable"] is True
    assert all(count > 0 for count in observed_active), observed_active
    assert library_resources.process_guard()._active == 0


@pytest.mark.parametrize("modern", [False, True])
def test_stdio_cancel_sends_no_response_and_releases_admission(db, monkeypatch, modern):
    # SDK 2 settles through the public unanswered hook without a cancel frame.
    seed.insert_yoink(db, "az5h", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    original_read = analysis.get_library_activity
    monkeypatch.setattr(analysis, "get_library_activity", lambda args: original_read(args, clock=NOW))
    low = uoink_mcp.mcp
    original_handler = low.get_request_handler("tools/call").handler
    started = anyio.Event()

    async def delayed_handler(ctx, params):
        if params.name == "get_library_activity":
            started.set()
            await anyio.sleep(30)
        return await original_handler(ctx, params)

    async def after_init(incoming, outgoing):
        call = _activity_call()
        if modern:
            from tests.test_mcp_wire import modern_params
            call["params"] = modern_params(call["params"])
        await incoming.send(json.dumps(call) + "\n")
        with anyio.fail_after(5):
            await started.wait()
        assert library_resources.process_guard()._active == 1
        await incoming.send(json.dumps({
            "jsonrpc": "2.0", "method": "notifications/cancelled",
            "params": {"requestId": 2}}) + "\n")
        with anyio.fail_after(5):
            while library_resources.process_guard()._active:
                await anyio.sleep(0.01)
        assert library_resources.transport_scope(2) is None
        with anyio.move_on_after(0.15) as quiet:
            unexpected = await outgoing.receive()
            pytest.fail(f"Cancellation produced a frame: {unexpected}")
        assert quiet.cancel_called

    with replace_handler(low, "tools/call", delayed_handler):
        response = _run_stdio([{"jsonrpc": "2.0", "id": 3, "method": "tools/list" if modern else "ping"}],
                              after_init=after_init, modern=modern)[0]
    if modern:
        from tests.test_mcp_wire import GOLDEN, modern_domain
        assert response["id"] == 3
        assert modern_domain(response["result"], cacheable=True) == {"tools": GOLDEN["tools"]}
    else:
        assert response == {"jsonrpc": "2.0", "id": 3, "result": {}}
    assert library_resources.process_guard()._active == 0


def test_az5h_actual_stdio_entry_releases_on_broken_write(db, monkeypatch):
    seed.insert_yoink(db, "az5h", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    original_read = analysis.get_library_activity
    monkeypatch.setattr(analysis, "get_library_activity", lambda args: original_read(args, clock=NOW))

    try:
        _run_stdio([_activity_call()], fail_id=2)
    except BaseException:
        pass
    assert library_resources.process_guard()._active == 0


def test_az5h_phase4_resource_list_deadline_uses_same_transport(monkeypatch):
    monkeypatch.setattr(library_resources.LibraryReader, "_bind_index", lambda self, op: None)
    monkeypatch.setattr(
        library_resources.LibraryReader, "_list_resources",
        lambda self, op: [{"uri": "uoink://library/v1/x", "name": "x"}])
    original_dump = mcp_types.JSONRPCResponse.model_dump_json
    original_clock = time.monotonic
    clock_shift = [0.0]
    observed_active = []

    def expensive_actual_serialization(message, *args, **kwargs):
        text = original_dump(message, *args, **kwargs)
        root = message
        if isinstance(root, mcp_types.JSONRPCResponse) and root.id == 2:
            observed_active.append(library_resources.process_guard()._active)
            clock_shift[0] += 3.0
        return text

    monkeypatch.setattr(mcp_types.JSONRPCResponse, "model_dump_json", expensive_actual_serialization)
    monkeypatch.setattr(time, "monotonic", lambda: original_clock() + clock_shift[0])

    response = _run_stdio([{"jsonrpc": "2.0", "id": 2, "method": "resources/list"}])[0]
    assert response["id"] == 2
    assert observed_active and all(count > 0 for count in observed_active), observed_active
    assert "error" in response
    assert response["error"]["data"]["error"]["code"] == "deadline_exceeded"
    assert response["error"]["data"]["error"]["retryable"] is True
    assert library_resources.process_guard()._active == 0


@pytest.mark.parametrize("modern", [False, True])
def test_az5h_oversize_actual_frame_is_resource_too_large(db, monkeypatch, modern):
    seed.insert_yoink(db, "az5h", yoinked_at="2026-09-05T12:00:00.000Z")
    db.commit()
    monkeypatch.setattr(analysis, "_analysis_db_override", db)
    original_read = analysis.get_library_activity
    monkeypatch.setattr(analysis, "get_library_activity", lambda args: original_read(args, clock=NOW))
    original_dump = mcp_types.JSONRPCResponse.model_dump_json

    def huge_success(message, *args, **kwargs):
        text = original_dump(message, *args, **kwargs)
        root = message
        if isinstance(root, mcp_types.JSONRPCResponse) and root.id == 2:
            if isinstance(root.result, dict) and root.result.get("isError") is not True:
                return text + ("x" * 70000)
        return text

    monkeypatch.setattr(mcp_types.JSONRPCResponse, "model_dump_json", huge_success)
    response = _run_stdio([_activity_call()], modern=modern)[0]
    assert response["id"] == 2
    envelope = json.loads(response["result"]["content"][0]["text"])
    assert response["result"]["isError"]
    assert envelope["error"]["code"] == "resource_too_large"
    assert envelope["error"]["retryable"] is False
    assert library_resources.process_guard()._active == 0


def test_az5h_notifications_and_initialize_do_not_hold_admission():
    observed = []

    async def after_init(incoming, outgoing):
        observed.append(library_resources.process_guard()._active)

    _run_stdio([], after_init=after_init, collect=0)
    assert observed == [0]
    assert library_resources.process_guard()._active == 0

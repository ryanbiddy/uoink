"""M4: exercise the shipped SDK 2 writer and runner in both protocol eras."""
import asyncio
from contextlib import asynccontextmanager
import json
import threading
import time

import anyio
from mcp import types
import pytest

import library_resources as lr
import uoink_mcp as u
from tests.mcp_sdk import replace_handler
from tests.mcp_wire import initialize_request, rpc
from tests.test_mcp_wire import modern_domain, modern_params
from tests.test_phase5_az5h import _Input
from tests.test_discovery_scrapecreators import rig


@pytest.fixture(autouse=True)
def guard(monkeypatch):
    assert not lr._TRANSPORT_SCOPES
    guard = lr.ReadGuard(admissions_per_minute=1000)
    guard.releases = 0
    original = guard.release

    def release():
        assert guard._active > 0, "Admission released more than once"
        guard.releases += 1
        original()

    guard.release = release
    monkeypatch.setattr(lr, "_PROCESS_GUARD", guard)
    yield guard
    assert guard._active == 0
    assert not lr._TRANSPORT_SCOPES


class Session:
    def __init__(self, modern, sink=None):
        self.modern = modern
        self.input, self.reads = anyio.create_memory_object_stream(32)
        self.output, self.frames = anyio.create_memory_object_stream(32)
        self.states = None
        self.sink = sink or self
        self.flushed = anyio.Event()

    async def write(self, text):
        await self.output.send(text)

    async def flush(self):
        self.flushed.set()

    async def send(self, message):
        await self.input.send(json.dumps(message, ensure_ascii=False) + "\n")

    async def request(self, ident=2, *, name="get_library_item", method="tools/call", params=None):
        if params is None:
            params = {"name": name, "arguments": {}} if method == "tools/call" else {}
        await self.send(rpc(ident, method, modern_params(params) if self.modern else params))

    async def cancel(self, ident=2):
        await self.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": ident}})

    async def receive(self):
        with anyio.fail_after(5):
            return await self.frames.receive()

    async def until(self, predicate):
        with anyio.fail_after(5):
            while not predicate():
                await anyio.sleep(0.001)

    async def quiet(self):
        with anyio.move_on_after(0.03) as scope:
            pytest.fail(f"Unexpected response: {await self.receive()}")
        assert scope.cancel_called


@asynccontextmanager
async def session(modern, sink=None):
    client = Session(modern, sink)

    async def serve():
        async with u.bounded_stdio_server(_Input(client.reads), client.sink) as (reads, writes):
            client.states = u._stdio_requests.get()
            await u.mcp.run(reads, writes, u.mcp.create_initialization_options())

    with anyio.fail_after(8):
        async with anyio.create_task_group() as group:
            group.start_soon(serve)
            await client.send(rpc(1, "server/discover", modern_params()) if modern else initialize_request("2025-11-25"))
            assert json.loads(await client.receive())["id"] == 1
            if not modern:
                await client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            try:
                yield client
            finally:
                await client.input.aclose()
        assert client.states == {}


def result(text="ok", error=False):
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=error)


def handler_returning(factory):
    async def handler(ctx, params):
        u._request_state(ctx.request_id).protocol_version = ctx.protocol_version
        return factory(ctx, params)
    return handler


@pytest.mark.parametrize("modern", [False, True])
def test_shipped_path_prepares_each_message_once(modern, monkeypatch, guard):
    prepared = []
    original = u._prepare_inbound

    def prepare(message):
        prepared.append((message.message.method, getattr(message.message, "id", None)))
        return original(message)

    monkeypatch.setattr(u, "_prepare_inbound", prepare)

    async def check():
        with replace_handler(u.mcp, "tools/call", handler_returning(lambda *_: result())):
            async with session(modern) as client:
                await client.request()
                assert json.loads(await client.receive())["id"] == 2
                await client.cancel(999)
                await client.request(3, method="tools/list")
                assert json.loads(await client.receive())["id"] == 3

    anyio.run(check)
    expected = [("server/discover", 1)] if modern else [
        ("initialize", 1), ("notifications/initialized", None)]
    assert prepared == expected + [("tools/call", 2), ("notifications/cancelled", None), ("tools/list", 3)]
    assert guard.releases == 1


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("error", [False, True, "rpc"])
def test_exact_final_utf8_boundary_and_oversized_errors(modern, error, guard):
    from mcp.shared.exceptions import MCPError
    payload = [""]

    def response(ctx, params):
        if error == "rpc":
            raise MCPError(code=-32602, message=payload[0])
        return result(payload[0], error)

    async def check():
        async with session(modern) as client:
            await client.request()
            baseline = await client.receive()
            overhead = len(baseline.rstrip("\n").encode())
            for extra in (-1, 0, 1):
                # Each emoji needs four UTF-8 bytes. ASCII pads the remainder.
                budget = 65536 + extra - overhead
                payload[0] = "\U0001f9ea" * (budget // 4) + "x" * (budget % 4)
                await client.request()
                frame = await client.receive()
                raw = frame.rstrip("\n").encode()
                parsed = json.loads(frame)
                if extra <= 0:
                    assert len(raw) == 65536 + extra
                    text = parsed["error"]["message"] if error == "rpc" else parsed["result"]["content"][0]["text"]
                    assert text == payload[0]
                else:
                    assert len(raw) < 2048
                    domain = modern_domain(parsed["result"]) if modern else parsed["result"]
                    assert json.loads(domain["content"][0]["text"])["error"]["code"] == "resource_too_large"
            await client.until(lambda: not client.states)
    with replace_handler(u.mcp, "tools/call", handler_returning(response)):
        anyio.run(check)
    assert guard.releases == 4


@pytest.mark.parametrize("modern", [False, True])
def test_full_inventory_and_equal_sized_normal_result(modern):
    payload = [""]

    async def check():
        async with session(modern) as client:
            await client.request(method="tools/list")
            listing = await client.receive()
            size = len(listing.rstrip("\n").encode())
            assert 65536 < size <= 262144
            domain = json.loads(listing)["result"]
            assert len((modern_domain(domain, cacheable=True) if modern else domain)["tools"]) == 91
            await client.request(name="search_clips")
            baseline = await client.receive()
            payload[0] = "x" * (size - len(baseline.rstrip("\n").encode()))
            await client.request(name="search_clips")
            refusal = json.loads(await client.receive())
            assert refusal["error"]["code"] == -32600
    with replace_handler(u.mcp, "tools/call", handler_returning(lambda *_: result(payload[0]))):
        anyio.run(check)


@pytest.mark.parametrize("modern", [False, True])
def test_modern_metadata_counts_against_same_cap(modern):
    # One payload fits the legacy frame exactly; modern identity/resultType
    # overhead makes that same payload too large.
    base = types.JSONRPCResponse(jsonrpc="2.0", id=2, result={
        "content": [{"type": "text", "text": ""}], "isError": False})
    text = "x" * (65536 - len(base.model_dump_json(by_alias=True, exclude_none=True).encode()))

    async def check():
        async with session(modern) as client:
            await client.request(name="search_clips")
            frame = await client.receive()
            response = json.loads(frame)
            if modern:
                assert response["error"]["code"] == -32600
            else:
                assert len(frame.rstrip("\n").encode()) == 65536
                assert response["result"]["content"][0]["text"] == text
    with replace_handler(u.mcp, "tools/call", handler_returning(lambda *_: result(text))):
        anyio.run(check)


@pytest.mark.parametrize("modern", [False, True])
def test_replacement_refusal_is_bounded_even_with_large_id(modern):
    # The small protocol refusal fits this ID; the domain refusal does not.
    ident = "i" * (65536 - len(u._stdio_protocol_rejection_frame("").encode()))

    async def check():
        async with session(modern) as client:
            # Direct admission avoids the independent inbound-line cap, proving
            # the final writer's fallback even with an internally supplied ID.
            u_token = u._stdio_requests.set(client.states)
            try:
                state = u._begin_inbound_transport_scope(types.JSONRPCRequest(
                    jsonrpc="2.0", id=ident, method="tools/call", params={"name": "get_library_item"}))
                state.protocol_version = "2026-07-28" if modern else "2025-11-25"
                from mcp.shared.message import SessionMessage
                await u._deliver_bounded_outbound(SessionMessage(types.JSONRPCResponse(
                    jsonrpc="2.0", id=ident, result={"content": "x" * 70000})), client)
                frame = await client.receive()
                assert len(frame.rstrip("\n").encode()) <= 65536
                assert json.loads(frame) == json.loads(u._stdio_protocol_rejection_frame(None))
            finally:
                u._stdio_requests.reset(u_token)
    anyio.run(check)


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("failure", [None, "write", "flush", "pipe"])
def test_writer_holds_admission_through_write_and_flush(modern, failure, guard):
    observations = []
    client_ref = []

    class Sink:
        target = False

        async def write(self, text):
            self.target = json.loads(text).get("id") == 2
            if self.target:
                observations.append(("write", guard._active))
                if failure in ("write", "pipe"):
                    raise (BrokenPipeError if failure == "pipe" else OSError)("synthetic write failure")
            await client_ref[0].output.send(text)

        async def flush(self):
            if self.target:
                observations.append(("flush", guard._active))
                if failure == "flush":
                    raise OSError("synthetic flush failure")

    async def check():
        # Assign before opening so the initialization frame also uses the sink.
        original = Session.__init__
        def init(self, *args, **kwargs):
            original(self, *args, **kwargs)
            client_ref.append(self)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(Session, "__init__", init)
            async with session(modern, Sink()) as client:
                await client.request()
                await client.until(lambda: guard.releases == 1)
    with replace_handler(u.mcp, "tools/call", handler_returning(lambda *_: result())):
        if failure:
            with pytest.raises(ExceptionGroup) as caught:
                anyio.run(check)
            assert "synthetic" in str(caught.value.exceptions)
        else:
            anyio.run(check)
    assert observations == ([("write", 1)] if failure in ("write", "pipe") else [("write", 1), ("flush", 1)])
    assert guard.releases == 1


@pytest.mark.parametrize("modern", [False, True])
def test_predump_and_copy_leave_admission_owned(modern, guard):
    observations = []

    def prepared(ctx, params):
        response = types.JSONRPCResponse(jsonrpc="2.0", id=2, result={"local": "diagnostic"})
        response.model_dump_json()
        response.model_copy(deep=True).model_dump_json()
        observations.append((guard._active, lr.transport_scope(2).released))
        return result()

    async def check():
        async with session(modern) as client:
            await client.request()
            assert json.loads(await client.receive())["result"]["isError"] is False
    with replace_handler(u.mcp, "tools/call", handler_returning(prepared)):
        anyio.run(check)
    assert observations == [(1, False)]
    assert guard.releases == 1


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("stage", ["queued", "preparation", "output"])
def test_cancel_at_each_async_boundary_and_id_reuse(modern, stage, guard, monkeypatch):
    async def check():
        entered, release = anyio.Event(), anyio.Event()
        original_prepare = u._prepare_inbound
        original_deliver = u._deliver_bounded_outbound
        calls = []

        async def handler(ctx, params):
            calls.append(ctx.request_id)
            if stage == "preparation" and len(calls) == 1:
                entered.set()
                await release.wait()
            return result()

        async def deliver(message, stdout):
            if stage == "output" and message.message.id == 2 and not entered.is_set():
                entered.set()
                await release.wait()
            await original_deliver(message, stdout)

        def prepare(message):
            prepared = original_prepare(message)
            if stage == "queued" and getattr(message.message, "id", None) == 2 and not entered.is_set():
                # Admission exists, but SDK dispatch has not received it yet.
                entered.set()
                original_prepare(type(message)(types.JSONRPCNotification(
                    jsonrpc="2.0", method="notifications/cancelled", params={"requestId": 2})))
            return prepared

        monkeypatch.setattr(u, "_prepare_inbound", prepare)
        monkeypatch.setattr(u, "_deliver_bounded_outbound", deliver)
        with replace_handler(u.mcp, "tools/call", handler):
            async with session(modern) as client:
                # A cancel for an unissued ID cannot poison a later request.
                await client.cancel(2)
                await client.request()
                await entered.wait()
                if stage != "queued":
                    await client.cancel()
                    await client.until(lambda: not client.states or client.states[2].cancelled)
                release.set()
                await client.until(lambda: 2 not in client.states)
                await client.quiet()
                assert guard.releases == 1
                await client.request()
                assert json.loads(await client.receive())["id"] == 2
        assert guard.releases == 2
    anyio.run(check)


@pytest.mark.parametrize("modern", [False, True])
def test_paid_worker_reserves_id_until_thread_settles(modern, monkeypatch):
    release = threading.Event()

    async def check():
        entered = anyio.Event()
        loop = asyncio.get_running_loop()

        def worker(*args):
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(5)
            return {"ok": True}

        monkeypatch.setattr(u.uoink_mcp_tools, "call_tool", worker)
        try:
            async with session(modern) as client:
                await client.request(name="discover_candidates")
                await entered.wait()
                state = client.states[2]
                await client.cancel()
                await client.until(lambda: state.cancelled)
                assert not state.settled
                await client.request(name="discover_candidates")
                refusal = json.loads(await client.receive())
                assert refusal.get("id") is None and refusal["error"]["code"] == -32600
                assert client.states[2] is state
                release.set()
                await client.until(lambda: state.settled)
                await client.quiet()
                await client.request(name="discover_candidates")
                assert json.loads(await client.receive())["result"]["isError"] is False
        finally:
            release.set()
    anyio.run(check)


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("original_writer", [False, True])
def test_real_delay_in_concrete_sdk_serializer(modern, original_writer, guard, monkeypatch):
    from tests.test_phase5_sdk_original_route import _run_original_stdio
    monkeypatch.setitem(lr.LIMITS, "service_deadline_s", 0.1)
    original = types.JSONRPCResponse.model_dump_json
    observed = []

    def slow(message, *args, **kwargs):
        text = original(message, *args, **kwargs)
        if message.id == 2 and not observed:
            scope = lr.transport_scope(2)
            assert scope is not None and not scope.expired()
            observed.append(guard._active)
            time.sleep(0.12)
            assert scope.expired()
        return text

    monkeypatch.setattr(types.JSONRPCResponse, "model_dump_json", slow)

    async def check():
        async with session(modern) as client:
            await client.request()
            return json.loads(await client.receive())

    with replace_handler(u.mcp, "tools/call", handler_returning(lambda *_: result())):
        response = (_run_original_stdio([rpc(2, "tools/call", {"name": "get_library_item", "arguments": {}})],
                                       modern=modern)[0] if original_writer else anyio.run(check))
    domain = modern_domain(response["result"]) if modern else response["result"]
    assert json.loads(domain["content"][0]["text"])["error"]["code"] == "deadline_exceeded"
    assert observed == [1] and guard.releases == 1


@pytest.mark.parametrize("modern", [False, True])
def test_inventory_allowance_also_has_an_exact_final_cap(modern):
    size = [0]

    async def handler(ctx, params):
        return types.ListToolsResult(tools=[types.Tool(name="fixture", description="x" * size[0], input_schema={"type": "object"})])

    async def check():
        async with session(modern) as client:
            await client.request(method="tools/list")
            overhead = len((await client.receive()).rstrip("\n").encode())
            size[0] = 262144 - overhead
            await client.request(method="tools/list")
            assert len((await client.receive()).rstrip("\n").encode()) == 262144
            size[0] += 1
            await client.request(method="tools/list")
            frame = await client.receive()
            assert len(frame.encode()) < 1024
            assert json.loads(frame)["error"]["code"] == -32600
    with replace_handler(u.mcp, "tools/list", handler):
        anyio.run(check)


@pytest.mark.parametrize("modern", [False, True])
def test_cancel_before_admission_is_ignored(modern, guard):
    async def check():
        async with session(modern) as client:
            await client.cancel()
            await client.quiet()
            assert client.states == {} and guard._active == 0
            await client.request()
            assert json.loads(await client.receive())["result"]["isError"] is False
    with replace_handler(u.mcp, "tools/call", handler_returning(lambda *_: result())):
        anyio.run(check)
    assert guard.releases == 1


@pytest.mark.parametrize("modern", [False, True])
def test_eof_with_inflight_request_releases_capacity(modern, guard):
    async def check():
        started = anyio.Event()

        async def handler(ctx, params):
            started.set()
            await anyio.sleep_forever()

        with replace_handler(u.mcp, "tools/call", handler):
            async with session(modern) as client:
                await client.request()
                await started.wait()
                assert guard._active == 1
                # Context exit sends EOF; no test-side cancellation rescues it.
    anyio.run(check)
    assert guard.releases == 1


@pytest.mark.parametrize("modern", [False, True])
def test_id_stays_reserved_until_flush_and_late_cancel_is_ignored(modern, guard, monkeypatch):
    async def check():
        flushing, release = anyio.Event(), anyio.Event()
        original_flush = Session.flush

        async def flush(client):
            if 2 in client.states and not flushing.is_set():
                flushing.set()
                await release.wait()
            await original_flush(client)

        monkeypatch.setattr(Session, "flush", flush)
        with replace_handler(u.mcp, "tools/call", handler_returning(lambda *_: result())):
            async with session(modern) as client:
                await client.request()
                assert json.loads(await client.receive())["id"] == 2
                await flushing.wait()
                state = client.states[2]
                assert guard._active == 1 and guard.releases == 0
                await client.cancel()
                await client.request()
                # The duplicate is refused at input, while output is held.
                await anyio.sleep(0.02)
                assert client.states[2] is state and not state.cancelled
                release.set()
                assert json.loads(await client.receive())["error"] == {
                    "code": -32600, "message": "Duplicate in-flight request ID"}
                await client.until(lambda: state.settled)
                assert guard.releases == 1
                await client.request()
                assert json.loads(await client.receive())["id"] == 2
        assert guard.releases == 2
    anyio.run(check)


@pytest.mark.parametrize("modern", [False, True])
def test_cancelled_unadmitted_request_cannot_release_another_slot(modern, guard):
    from mcp.shared.message import SessionMessage

    async def check():
        async with session(modern) as client:
            token = u._stdio_requests.set(client.states)
            try:
                def admit(ident):
                    return u._begin_inbound_transport_scope(types.JSONRPCRequest(
                        jsonrpc="2.0", id=ident, method="tools/call", params={"name": "get_library_item"}))
                # Lane S raised the reader limit. Fill the configured capacity
                # before testing cancellation of a request that owns no slot.
                admitted = [admit(ident) for ident in range(2, 2 + guard.max_active)]
                refused_id = 2 + guard.max_active
                refused = admit(refused_id)
                assert refused.scope.refusal.code == "rate_limited"
                assert guard._active == len(admitted)
                u._begin_inbound_transport_scope(types.JSONRPCNotification(
                    jsonrpc="2.0", method="notifications/cancelled", params={"requestId": refused_id}))
                await u._deliver_bounded_outbound(SessionMessage(types.JSONRPCResponse(
                    jsonrpc="2.0", id=refused_id, result={})), client)
                await client.quiet()
                refused.settle()
                assert guard._active == len(admitted) and guard.releases == 0
                for state in admitted:
                    state.settle()
                assert guard.releases == len(admitted)
            finally:
                u._release_stdio_requests()
                u._stdio_requests.reset(token)
    anyio.run(check)


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("alias", ["2", "02", "+2"])
def test_numeric_id_alias_cannot_bypass_settlement(modern, alias, guard):
    async def check():
        entered = anyio.Event()

        async def handler(ctx, params):
            if not entered.is_set():
                entered.set()
                await anyio.sleep_forever()
            return result()

        with replace_handler(u.mcp, "tools/call", handler):
            async with session(modern) as client:
                await client.request()
                await entered.wait()
                await client.request(alias)
                refusal = json.loads(await client.receive())
                assert refusal.get("id") is None and refusal["error"]["code"] == -32600
                assert guard._active == 1
                await client.cancel(alias)
                await client.until(lambda: 2 not in client.states)
                await client.quiet()
                assert guard.releases == 1
                await client.request(alias)
                assert json.loads(await client.receive())["id"] == alias
        assert guard.releases == 2
    anyio.run(check)


@pytest.mark.parametrize("modern", [False, True])
def test_paid_discovery_lock_and_credit_settle_once_after_cancel(modern, rig, monkeypatch):
    import discovery_scrapecreators as discovery
    from tests.test_discovery_scrapecreators import ARGS, fixture
    release = threading.Event()

    class Lock:
        def __init__(self):
            self.lock = threading.Lock()
            self.releases = 0

        def acquire(self, **kwargs):
            return self.lock.acquire(**kwargs)

        def release(self):
            assert self.lock.locked()
            self.releases += 1
            self.lock.release()

    gate = Lock()
    monkeypatch.setattr(discovery, "_network_lock", gate)
    monkeypatch.setattr(discovery, "_last_sent_at", None)
    monkeypatch.setattr(u.server, "_get_discovery_service", lambda: rig.service)
    monkeypatch.setattr(u.uoink_mcp_tools.TOOL_REGISTRY["discover_candidates"].rate_limiter, "_calls", [])

    async def check():
        entered = anyio.Event()
        loop = asyncio.get_running_loop()

        def transport(method, url, headers, timeout, max_bytes):
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(5)
            return discovery.TransportResponse(200, json.dumps(fixture()).encode(), url)

        monkeypatch.setattr(rig.service, "transport", transport)
        params = {"name": "discover_candidates", "arguments": {**ARGS, "confirm_credits": 1}}
        try:
            async with session(modern) as client:
                await client.request(params=params)
                await entered.wait()
                state = client.states[2]
                await client.cancel()
                await client.until(lambda: state.cancelled)
                assert not state.settled and gate.lock.locked() and gate.releases == 0
                await client.request(3, params=params)
                busy = json.loads(await client.receive())
                assert busy["id"] == 3 and busy["result"]["isError"] is True
                error = json.loads(busy["result"]["content"][0]["text"])["error"]
                assert error["code"] == "rate_limited" and error["details"]["retry_after_ms"] == 1000
                assert gate.releases == 0
                release.set()
                await client.until(lambda: state.settled)
                await client.quiet()
                assert gate.releases == 1 and not gate.lock.locked()
                assert rig.service._credits_today(rig.idx) == 1
                await client.request(params=params)
                assert json.loads(await client.receive())["result"]["isError"] is False
                assert gate.releases == 2 and rig.service._credits_today(rig.idx) == 2
        finally:
            release.set()
    anyio.run(check)

import socket
import threading
from contextlib import ExitStack
from unittest.mock import Mock

import pytest
import server


def stream(stack, origin, client=None):
    peer, connection = socket.socketpair()
    stack.callback(connection.close)
    stack.callback(peer.close)
    ready = threading.Event()
    headers = {"Host": "page.test"}
    if origin is not None:
        headers["Origin"] = origin
    if client is not None:
        headers["X-Uoink-Stream"] = client
    handler = Mock(connection=connection, headers=headers)
    handler._jobs_snapshot.return_value = {}
    handler._jobs_map.return_value = {}
    handler._sse_emit.side_effect = lambda *_: ready.set()
    handler._send_json.side_effect = lambda *_: ready.set()
    thread = threading.Thread(target=server.Handler._handle_jobs_stream, args=(handler,), daemon=True)
    thread.start()
    assert ready.wait(2)
    return peer, thread, handler


@pytest.mark.parametrize("origin", [None, "http://page.test"])
@pytest.mark.parametrize("unissued", [None, "popup", "?", "0" * 32])
def test_only_origin_and_issued_page_id_can_replace_at_capacity(monkeypatch, unissued, origin):
    monkeypatch.setattr(server, "_SSE_TICK_SEC", .02)
    monkeypatch.setattr(server, "_SSE_MAX_STREAMS", 2)
    with ExitStack() as stack:
        _, first, handler = stream(stack, origin, unissued)
        ident = handler._sse_emit.call_args.args[1]["stream_id"]
        assert ident != unissued
        popup, other, handler = stream(stack, "http://other.test", ident)
        assert handler._sse_emit.call_args.args[1]["stream_id"] != ident
        _, _, denied = stream(stack, origin, unissued)
        assert denied._send_json.call_args.args[0] == 503
        assert first.is_alive() and other.is_alive()
        page, replacement, handler = stream(stack, origin, ident)
        first.join(1)
        assert not first.is_alive() and other.is_alive()
        for peer, thread in ((page, replacement), (popup, other)):
            peer.close()
            thread.join(1)
            assert not thread.is_alive()


def test_invalid_select_descriptor_releases_slot(monkeypatch):
    handler = Mock(headers={})
    handler._jobs_snapshot.return_value = {}
    monkeypatch.setattr(server.select, "select", Mock(side_effect=ValueError("closed descriptor")))
    server.Handler._handle_jobs_stream(handler)
    assert handler.connection not in server._sse_active.values()

import socket
import threading
from contextlib import ExitStack
from unittest.mock import Mock

import server


def stream(stack, client):
    peer, connection = socket.socketpair()
    stack.callback(connection.close)
    stack.callback(peer.close)
    opened = threading.Event()
    handler = Mock(connection=connection, headers={"X-Uoink-Stream": client})
    handler._sse_emit.side_effect = lambda *args: opened.set()
    handler._jobs_map.return_value = {}
    thread = threading.Thread(target=server.Handler._handle_jobs_stream, args=(handler,), daemon=True)
    thread.start()
    return peer, thread, opened


def test_reload_replaces_only_its_stream_and_close_frees_slot(monkeypatch):
    monkeypatch.setattr(server, "_SSE_MAX_STREAMS", 2)
    monkeypatch.setattr(server, "_SSE_TICK_SEC", .02)
    with ExitStack() as stack:
        _, first, opened = stream(stack, "dashboard")
        assert opened.wait(1)
        popup, other, opened = stream(stack, "popup")
        assert opened.wait(1)
        page, replacement, opened = stream(stack, "dashboard")
        assert opened.wait(1)
        first.join(1)
        assert not first.is_alive() and other.is_alive()
        for peer, thread in ((page, replacement), (popup, other)):
            peer.close()
            thread.join(1)
            assert not thread.is_alive()

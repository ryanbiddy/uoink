"""Direct adapter checks through SDK 2's public typed handler API.

Wire negotiation and serialization belong in mcp_wire. This helper is for
fixtures that must keep storage, clocks or thread identity in the test process.
"""
from contextlib import contextmanager
from mcp.server.context import ServerRequestContext


def handler_for(server, method):
    entry = server.get_request_handler(method)
    assert entry is not None, method

    async def invoke(request):
        import library_resources
        assert request.method == method
        params = request.params
        raw = {} if params is None else params.model_dump(by_alias=True, exclude_none=True)
        typed = entry.params_type.model_validate(raw, by_name=False)
        scope = library_resources.current_transport_scope()
        ctx = ServerRequestContext(
            session=None, lifespan_context={}, protocol_version="2025-11-25",
            method=method, params=raw,
            request_id=scope.request_id if scope is not None else None)
        return await entry.handler(ctx, typed)

    return invoke


@contextmanager
def replace_handler(server, method, handler):
    """Patch registration via public methods and restore it with the fixture."""
    entry = server.get_request_handler(method)
    assert entry is not None
    server.add_request_handler(method, entry.params_type, handler)
    try:
        yield
    finally:
        server.add_request_handler(method, entry.params_type, entry.handler)

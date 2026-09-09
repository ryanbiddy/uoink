"""Final transport settlement must not be triggered by a local diagnostic dump."""
import json
from mcp import types
import library_analysis as analysis
import library_resources
from tests.test_phase5_sdk_original_route import (
    NOW, _activity_call, _run_original_stdio, db, isolate_reader, seed,
)


def test_local_response_copy_does_not_settle_the_outgoing_request(db, monkeypatch):
    seed.insert_yoink(db, 'sdk-local-copy', yoinked_at='2026-09-05T12:00:00.000Z')
    db.commit()
    monkeypatch.setattr(analysis, '_analysis_db_override', db)
    read = analysis.get_library_activity
    observations = []

    def read_with_diagnostic(args):
        before = library_resources.process_guard()._active
        copy = types.JSONRPCMessage(types.JSONRPCResponse(
            jsonrpc='2.0', id=2, result={'diagnostic': 'local copy only'}))
        assert json.loads(copy.model_dump_json())['id'] == 2
        observations.append((before, library_resources.process_guard()._active,
                             library_resources.transport_scope(2) is not None))
        return read(args, clock=NOW)

    monkeypatch.setattr(analysis, 'get_library_activity', read_with_diagnostic)
    response = _run_original_stdio([_activity_call()])[0]
    assert response['result'].get('isError') is not True
    assert observations == [(1, 1, True)], observations
    assert library_resources.process_guard()._active == 0

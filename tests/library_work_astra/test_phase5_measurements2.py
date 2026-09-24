"""BA-2 measurement audit: capture the supplied benchmark and its actual adapter.

This module runs the expensive supplied benchmark once, and reuses only its
test-session observations. It does not introduce an application report cache.
"""
import asyncio
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

import library_analysis
import uoink_mcp
from mcp import types as mcp_types
from tests import test_library_analysis_fixtures as az


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def benchmark_capture(tmp_path_factory):
    real_read = library_analysis.get_library_activity
    records = []

    def measured_read(args, **kwargs):
        conn = kwargs["db"]
        record = {name: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for name, table in [("items", "yoinks"), ("memberships", "item_shelves"), ("observations", "source_items"), ("applies", "library_applies")]}
        record["journal_bytes"] = conn.execute("SELECT COALESCE(SUM(LENGTH(CAST(forward_json AS BLOB))+LENGTH(CAST(inverse_json AS BLOB))),0) FROM library_applies").fetchone()[0]
        packet = real_read(args, **kwargs)
        record.update(ok=packet["ok"], interval=args["interval"], raw_bytes=len(json.dumps(packet, ensure_ascii=False).encode()))
        if packet["ok"]:
            record["baseline"] = packet["coverage"]["cov_shelf_activity"]
            record["rows"] = {"events": len(packet["events"]["rows"]), "creators": len(packet["items"]["by_creator_hint"]), "joint": len(packet["items"]["by_type_creator_hint"]), "sources": len(packet["sources"]["details"]), "shelves": len(packet["shelf_activity"]["shelves"])}
            request = mcp_types.CallToolRequest(method="tools/call", params=mcp_types.CallToolRequestParams(name="get_library_activity", arguments=args))
            # Feed the captured reader packet through the actual shipped adapter.
            # This isolates serialization and avoids a second benchmark read.
            with patch.object(library_analysis, "get_library_activity", lambda arguments: packet):
                actual = asyncio.run(uoink_mcp.mcp._mcp_server.request_handlers[mcp_types.CallToolRequest](request)).root
            wire = mcp_types.JSONRPCResponse(jsonrpc="2.0", id=1, result=actual.model_dump(mode="json", exclude_none=True))
            record["actual_stdio_bytes"] = len(wire.model_dump_json(by_alias=True, exclude_none=True).encode())
            record["actual_stdio_is_error"] = actual.isError
            if actual.isError:
                record["actual_stdio_error"] = json.loads(actual.content[0].text)
        else:
            record["error"] = packet["error"]
        records.append(record)
        return packet

    library_analysis.reset_rate_limiter()
    try:
        with patch.object(library_analysis, "get_library_activity", measured_read):
            az.test_activity_cost_548_and_10000(tmp_path_factory.mktemp("measurement_audit"))
    finally:
        library_analysis.reset_rate_limiter()
    print("BA-2 DIMENSIONS AND ACTUAL STDIO: " + json.dumps(records, sort_keys=True))
    return records


def test_phase5_ba2_measurement_document_payloads_match_capture(benchmark_capture):
    doc = (ROOT / "docs/library/PHASE5-AZ-MEASUREMENTS-2026-09-08.md").read_text(encoding="utf-8")
    row = re.search(r"\*\*Wire Response Payload\*\*\s*\|\s*([\d,]+) bytes\s*\|\s*([\d,]+) bytes", doc)
    assert row, "Record payload sizes with their serialization layer"
    published = [int(row[1].replace(",", "")), int(row[2].replace(",", ""))]
    captured = [benchmark_capture[i]["raw_bytes"] for i in (0, 1)]
    assert published == captured, {"published": published, "captured_raw": captured}


@pytest.mark.parametrize("index", [0, 1])
def test_phase5_ba2_measurement_normal_fixture_succeeds_on_actual_stdio(benchmark_capture, index):
    record = benchmark_capture[index]
    assert record["ok"]
    assert not record["actual_stdio_is_error"], record
    assert record["actual_stdio_bytes"] <= 65536


def test_phase5_ba2_measurement_multi_operation_case_proves_replay(benchmark_capture):
    record = next(r for r in benchmark_capture if r["applies"] == 10)
    assert record["ok"]
    assert record["baseline"]["coverage_status"] == "journal_complete", record
    assert not record["baseline"]["reasons"]

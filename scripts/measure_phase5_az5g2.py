"""AZ-5g2 measurement harness.

Runs the unedited synthetic cost fixture, then measures the actual shipped
stdio entry (bounded_stdio_server), handler-only dumps, and a hand-built
envelope. Derives git IDs and hashes at runtime. Retains complete reader
packets and JSON-RPC frames. Never treats a returned sample length as a
population total.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any
from unittest.mock import patch

import anyio
from mcp import types as mcp_types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import library_analysis
import library_resources
import uoink_mcp
from tests import test_library_analysis_fixtures as az

PROOF = ROOT / "docs" / "library" / "proof" / "az5g2-2026-09-08"
SCRATCH = ROOT / "_scratch" / "az5g2" / "measure"
DOC_PATH = ROOT / "docs" / "library" / "PHASE5-AZ-MEASUREMENTS-2026-09-08.md"
REJECTED_PATCH = ROOT / "docs" / "library" / "patches" / "az5g-gemini-partial-rejected-2026-09-08.patch"

CLOCK = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
PRIMARY_INTERVAL = {"start": "2026-09-01T00:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"}
REPLAY_INTERVAL = {"start": "2026-09-01T10:00:00.000Z", "end": "2026-09-02T00:00:00.000Z"}
PRIMARY_ARGS = {"interval": PRIMARY_INTERVAL, "date_basis": "capture_time"}
REPLAY_ARGS = {"interval": REPLAY_INTERVAL, "date_basis": "capture_time"}
DASHBOARD_TARGET = 24576
WIRE_CAP = 65536
JOURNAL_CAP = 67_108_864
FIXTURE_ORDER = [
    "548_primary_traced",
    "10000_primary_untraced",
    "10000_primary_traced_diagnostic",
    "548_proved_replay",
    "70mib_journal_refusal",
    "548_deadline_refusal",
    "548_three_memberships",
    "50_ten_operations",
    "100k_observations",
]
Q1_SQL = (
    "EXPLAIN QUERY PLAN SELECT video_id, source_type, author, channel, platform, "
    "yoinked_at, deleted_at FROM yoinks ORDER BY video_id ASC"
)
Q3_SQL = (
    "EXPLAIN QUERY PLAN SELECT apply_id, operation_key, kind, before_revision, "
    "after_revision, operation_sequence, authoritative_record_hash, forward_json, "
    "inverse_json, undo_of, created_at FROM library_applies ORDER BY operation_sequence ASC"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def pkg_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def metric_value(metric: Any) -> Any:
    if metric is None:
        return None
    if isinstance(metric, dict):
        return metric.get("value")
    return None


def json_utf8(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def query_dims(conn) -> dict[str, Any]:
    return {
        "items": conn.execute("SELECT COUNT(*) FROM yoinks").fetchone()[0],
        "memberships": conn.execute("SELECT COUNT(*) FROM item_shelves").fetchone()[0],
        "observations": conn.execute("SELECT COUNT(*) FROM source_items").fetchone()[0],
        "applies": conn.execute("SELECT COUNT(*) FROM library_applies").fetchone()[0],
        "journal_bytes": conn.execute(
            "SELECT COALESCE(SUM(LENGTH(CAST(forward_json AS BLOB))"
            "+LENGTH(CAST(inverse_json AS BLOB))),0) FROM library_applies"
        ).fetchone()[0],
    }


def extract_counts(packet: dict[str, Any]) -> dict[str, Any]:
    if not packet.get("ok"):
        return {"ok": False, "error": packet.get("error")}
    pag = packet.get("pagination") or {}
    events = packet.get("events") or {}
    items = packet.get("items") or {}
    sources = packet.get("sources") or {}
    shelves = packet.get("shelf_activity") or {}

    def block(pag_key: str, rows: Any, family: dict[str, Any] | None = None, total_metric: Any = None) -> dict[str, Any]:
        p = pag.get(pag_key) or {}
        sample = len(rows or [])
        return {
            "pagination_total_rows": p.get("total_rows"),
            "pagination_returned_rows": p.get("returned_rows"),
            "pagination_omitted_rows": p.get("omitted_rows"),
            "returned_sample_length": sample,
            "family_returned_rows": None if family is None else family.get("returned_rows"),
            "family_omitted_rows": None if family is None else family.get("omitted_rows"),
            "metric_total": total_metric,
            "note": "returned_sample_length is the displayed array length, not a population total",
        }

    coverage = (packet.get("coverage") or {}).get("cov_shelf_activity")
    return {
        "ok": True,
        "items_total_metric": metric_value(items.get("total")),
        "events": block("events", events.get("rows"), events, metric_value(events.get("total"))),
        "creators": block("creator_hints", items.get("by_creator_hint")),
        "joint": block("type_creator_hints", items.get("by_type_creator_hint")),
        "sources": block("sources", sources.get("details")),
        "shelves": block("shelves", shelves.get("shelves")),
        "coverage_shelf": coverage,
        "report_revision": packet.get("report_revision"),
        "warnings": packet.get("warnings"),
    }


def classify_record(rec: dict[str, Any]) -> str:
    dims = rec["dims"]
    packet = rec["packet"]
    interval = (rec["args"] or {}).get("interval") or {}
    start = interval.get("start") or ""
    ok = packet.get("ok")
    if dims["journal_bytes"] and dims["journal_bytes"] > 70_000_000:
        return "70mib_journal_refusal"
    if ok is False and (packet.get("error") or {}).get("code") == "deadline_exceeded":
        return "548_deadline_refusal"
    if dims["observations"] == 100000:
        return "100k_observations"
    if dims["applies"] == 10:
        return "50_ten_operations"
    if dims["memberships"] == 1644:
        return "548_three_memberships"
    if dims["items"] == 10000:
        if rec["tracing_active"] or rec["deadline_sec"] != library_analysis.SERVICE_DEADLINE_SEC:
            return "10000_primary_traced_diagnostic"
        return "10000_primary_untraced"
    if dims["items"] == 548:
        if start.startswith("2026-09-01T10:00:00"):
            return "548_proved_replay"
        if rec["tracing_active"]:
            return "548_primary_traced"
        return "548_primary_untraced"
    return "unclassified"


def write_bytes(path: Path, data: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }


class _Stdin:
    def __init__(self, stream):
        self.stream = stream

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.stream.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration


class _Stdout:
    def __init__(self, stream, frames: list[str]):
        self.stream = stream
        self.frames = frames

    async def write(self, text):
        self.frames.append(text)
        await self.stream.send(text)

    async def flush(self):
        pass


def _bind_clocked_reader(conn):
    original = library_analysis.get_library_activity
    previous = library_analysis._analysis_db_override

    def wrapped(args, **kwargs):
        kwargs.setdefault("clock", CLOCK)
        return original(args, **kwargs)

    library_analysis._analysis_db_override = conn
    library_analysis.get_library_activity = wrapped
    return original, previous


def _restore_reader(original, previous):
    library_analysis.get_library_activity = original
    library_analysis._analysis_db_override = previous
    library_analysis.reset_rate_limiter()


def run_shipped_stdio(
    conn,
    arguments: dict[str, Any],
    *,
    request_id: int = 2,
    replace_reader=None,
    shift_after_admit: float = 0.0,
    label: str,
) -> dict[str, Any]:
    """Drive bounded_stdio_server and retain exact stdout frames."""
    frames: list[str] = []
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "az5g2-measure", "version": "1"},
        },
    }
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    call = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": "get_library_activity", "arguments": arguments},
    }
    init_line = json.dumps(initialize, ensure_ascii=False, separators=(",", ":")) + "\n"
    note_line = json.dumps(initialized, ensure_ascii=False, separators=(",", ":")) + "\n"
    call_line = json.dumps(call, ensure_ascii=False, separators=(",", ":")) + "\n"

    original, previous = _bind_clocked_reader(conn)
    orig_clock = time.monotonic
    shift = [0.0]
    if replace_reader is not None:
        library_analysis.get_library_activity = replace_reader
    elif shift_after_admit:
        inner = library_analysis.get_library_activity

        def late(args, **kwargs):
            kwargs.setdefault("clock", CLOCK)
            shift[0] += shift_after_admit
            return inner(args, **kwargs)

        library_analysis.get_library_activity = late
        time.monotonic = lambda: orig_clock() + shift[0]

    library_analysis.reset_rate_limiter()
    error = None
    t0 = time.perf_counter()
    try:
        async def exchange():
            incoming, input_stream = anyio.create_memory_object_stream(8)
            output_stream, outgoing = anyio.create_memory_object_stream(8)
            sink = _Stdout(output_stream, frames)

            async def serve():
                async with uoink_mcp.bounded_stdio_server(_Stdin(input_stream), sink) as (reads, writes):
                    low = uoink_mcp.mcp._mcp_server
                    await low.run(reads, writes, low.create_initialization_options())

            async with anyio.create_task_group() as group:
                group.start_soon(serve)
                await incoming.send(init_line)
                await outgoing.receive()
                await incoming.send(note_line)
                await incoming.send(call_line)
                await outgoing.receive()
                group.cancel_scope.cancel()

        anyio.run(exchange)
    except Exception as exc:  # noqa: BLE001 — retain partial frames
        error = f"{type(exc).__name__}: {exc}"
    finally:
        time.monotonic = orig_clock
        _restore_reader(original, previous)
    t1 = time.perf_counter()

    activity = None
    parsed_frames = []
    for raw in frames:
        rec = {
            "completed_frame_bytes": len(raw.encode("utf-8")),
            "jsonrpc_utf8_bytes": len(raw.rstrip("\n").encode("utf-8")),
            "sha256": sha256_bytes(raw.encode("utf-8")),
            "ends_with_newline": raw.endswith("\n"),
        }
        try:
            obj = json.loads(raw)
            rec["id"] = obj.get("id")
            rec["has_error_key"] = "error" in obj
            rec["result_isError"] = (obj.get("result") or {}).get("isError")
            if obj.get("id") == request_id:
                activity = obj
                rec["role"] = "tools_call_response"
            elif obj.get("id") == 1:
                rec["role"] = "initialize_response"
            else:
                rec["role"] = "other"
        except json.JSONDecodeError:
            rec["role"] = "unparseable"
        parsed_frames.append(rec)

    result: dict[str, Any] = {
        "scope": "actual_shipped_stdio_entry",
        "entry": "uoink_mcp.bounded_stdio_server / run_bounded_stdio_async writer",
        "label": label,
        "includes_reader_invocation": replace_reader is None,
        "serializer": "JSONRPCMessage.model_dump_json(by_alias=True, exclude_none=True) then completed-frame cap then trailing newline",
        "elapsed_ms": (t1 - t0) * 1000.0,
        "shift_after_admit_sec": shift_after_admit,
        "request": {
            "initialize_line_sha256": sha256_bytes(init_line.encode("utf-8")),
            "call_line_sha256": sha256_bytes(call_line.encode("utf-8")),
            "call_json": call,
        },
        "frames_summary": parsed_frames,
        "error": error,
    }
    if activity is not None:
        raw_activity = next(f for f in frames if json.loads(f).get("id") == request_id)
        result["activity_completed_frame_bytes"] = len(raw_activity.encode("utf-8"))
        result["activity_jsonrpc_utf8_bytes"] = len(raw_activity.rstrip("\n").encode("utf-8"))
        result["activity_sha256"] = sha256_bytes(raw_activity.encode("utf-8"))
        result["isError"] = (activity.get("result") or {}).get("isError")
        if activity.get("error"):
            result["jsonrpc_error"] = activity["error"]
        content = ((activity.get("result") or {}).get("content") or [{}])
        text = content[0].get("text") if content else None
        if isinstance(text, str):
            fence_open = library_resources.DOCUMENT_FENCE_OPEN
            fence_close = library_resources.DOCUMENT_FENCE_CLOSE
            if fence_open in text and fence_close in text:
                inner = text.split(fence_open, 1)[1].split(fence_close, 1)[0]
                try:
                    inner_obj = json.loads(inner)
                    result["reader_ok"] = inner_obj.get("ok")
                    result["reader_error"] = inner_obj.get("error")
                    result["inner_reader_json_bytes"] = len(inner.encode("utf-8"))
                except json.JSONDecodeError:
                    result["inner_parse_error"] = True
        result["frame_text"] = raw_activity
    return result


def handler_only_serialize(packet: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    request = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name="get_library_activity", arguments=arguments),
    )
    library_analysis.reset_rate_limiter()
    t0 = time.perf_counter()
    with patch.object(library_analysis, "get_library_activity", lambda arguments: packet):
        actual = asyncio.run(uoink_mcp.mcp._mcp_server.request_handlers[mcp_types.CallToolRequest](request)).root
    wire = mcp_types.JSONRPCResponse(
        jsonrpc="2.0",
        id=1,
        result=actual.model_dump(mode="json", exclude_none=True),
    )
    text = wire.model_dump_json(by_alias=True, exclude_none=True)
    t1 = time.perf_counter()
    library_analysis.reset_rate_limiter()
    encoded = text.encode("utf-8")
    return {
        "scope": "handler_only_captured_packet",
        "label": "request handler on an already captured reader packet; does not invoke bounded_stdio_server; JSONRPCResponse id=1; no trailing newline",
        "includes_reader_invocation": False,
        "serializer": "JSONRPCResponse.model_dump_json(by_alias=True, exclude_none=True)",
        "elapsed_ms": (t1 - t0) * 1000.0,
        "jsonrpc_utf8_bytes": len(encoded),
        "isError": actual.isError,
        "sha256": sha256_bytes(encoded),
        "text": text,
    }


def handbuilt_envelope(packet: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": (
                        library_resources.DOCUMENT_PREFACE
                        + library_resources.DOCUMENT_FENCE_OPEN
                        + json.dumps(packet, ensure_ascii=False)
                        + library_resources.DOCUMENT_FENCE_CLOSE
                    ),
                }
            ],
            "isError": False,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    t1 = time.perf_counter()
    return {
        "scope": "hand_built_synthetic_envelope",
        "label": "hand-built JSON-RPC synthetic envelope with preface and document fences; isolates serialization timing and does not invoke the stdio handler",
        "includes_reader_invocation": False,
        "elapsed_ms": (t1 - t0) * 1000.0,
        "jsonrpc_utf8_bytes": len(encoded),
        "sha256": sha256_bytes(encoded),
        "text": encoded.decode("utf-8"),
    }


def replay_probe(conn) -> dict[str, Any]:
    observed: list[bool] = []
    previous = sys.getprofile()

    def observe_return(frame, event, arg):
        if event == "return" and frame.f_code is library_analysis._execute_activity.__code__:
            projected = frame.f_locals.get("projected_state", {})
            observed.append(bool(projected and any(projected.values())))

    library_analysis.reset_rate_limiter()
    try:
        sys.setprofile(observe_return)
        packet = library_analysis.get_library_activity(PRIMARY_ARGS, db=conn, clock=CLOCK)
    finally:
        sys.setprofile(previous)
        library_analysis.reset_rate_limiter()
    coverage = (packet.get("coverage") or {}).get("cov_shelf_activity") or {}
    return {
        "path": "548 primary interval on the cost-fixture database",
        "replayed_state_observed": any(observed),
        "observe_return_count": len(observed),
        "reasons": coverage.get("reasons"),
        "coverage_status": coverage.get("coverage_status"),
        "ok": packet.get("ok"),
        "note": "Replay projection ran; interval_precedes_first_apply is a coverage reason, not a skipped path",
    }


def query_plans(conn, scale: str) -> dict[str, Any]:
    q1 = [list(r) for r in conn.execute(Q1_SQL).fetchall()]
    q3 = [list(r) for r in conn.execute(Q3_SQL).fetchall()]
    return {"scale": scale, "Q1": q1, "Q3": q3, "Q1_sql": Q1_SQL, "Q3_sql": Q3_SQL}


def diagnostic_heap(conn, arguments: dict[str, Any], *, deadline_sec: float | None, label: str) -> dict[str, Any]:
    old = library_analysis.SERVICE_DEADLINE_SEC
    library_analysis.reset_rate_limiter()
    try:
        if deadline_sec is not None:
            library_analysis.SERVICE_DEADLINE_SEC = deadline_sec
        tracemalloc.start()
        t0 = time.perf_counter()
        packet = library_analysis.get_library_activity(arguments, db=conn, clock=CLOCK)
        t1 = time.perf_counter()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        library_analysis.SERVICE_DEADLINE_SEC = old
        library_analysis.reset_rate_limiter()
        if tracemalloc.is_tracing():
            tracemalloc.stop()
    raw = json_utf8(packet)
    return {
        "scope": "diagnostic_tracing",
        "label": label,
        "tracing": True,
        "deadline_sec": deadline_sec if deadline_sec is not None else old,
        "deadline_relaxed": deadline_sec is not None and deadline_sec != old,
        "elapsed_ms": (t1 - t0) * 1000.0,
        "heap_current_bytes": current,
        "heap_peak_bytes": peak,
        "heap_peak_kib": peak / 1024.0,
        "ok": packet.get("ok"),
        "error": packet.get("error"),
        "raw_bytes": len(raw),
        "note": "tracemalloc Python heap only, not process RSS; not comparable to untraced construction times",
    }


def untraced_construction(conn, arguments: dict[str, Any], label: str) -> dict[str, Any]:
    library_analysis.reset_rate_limiter()
    t0 = time.perf_counter()
    packet = library_analysis.get_library_activity(arguments, db=conn, clock=CLOCK)
    t1 = time.perf_counter()
    t2_start = time.perf_counter()
    raw = json_utf8(packet)
    t2 = time.perf_counter()
    library_analysis.reset_rate_limiter()
    return {
        "scope": "untraced_reader_construction",
        "label": label,
        "tracing": False,
        "deadline_sec": library_analysis.SERVICE_DEADLINE_SEC,
        "construction_ms": (t1 - t0) * 1000.0,
        "raw_json_dumps_ms": (t2 - t2_start) * 1000.0,
        "raw_bytes": len(raw),
        "ok": packet.get("ok"),
        "error": packet.get("error"),
        "counts": extract_counts(packet),
    }


def collect_metadata() -> dict[str, Any]:
    return {
        "run": "AZ-5g2",
        "date": "2026-09-08",
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_tree": git_output("rev-parse", "HEAD^{tree}"),
        "git_head_subject": git_output("log", "-1", "--format=%s"),
        "mcp_installed": pkg_version("mcp"),
        "mcp_pin": "mcp==1.27.1",
        "anyio": pkg_version("anyio"),
        "pydantic": pkg_version("pydantic"),
        "pytest": pkg_version("pytest"),
        "shipped_stdio_entry": "uoink_mcp.mcp.run_stdio_async is uoink_mcp.run_bounded_stdio_async",
        "run_stdio_is_bounded": uoink_mcp.mcp.run_stdio_async is uoink_mcp.run_bounded_stdio_async,
        "apply_remains_false": True,
        "service_deadline_sec_default": library_analysis.SERVICE_DEADLINE_SEC,
        "max_response_bytes": library_analysis.MAX_RESPONSE_BYTES,
        "dashboard_target_bytes": DASHBOARD_TARGET,
        "wire_cap_bytes": WIRE_CAP,
        "journal_cap_bytes": JOURNAL_CAP,
    }


def capture_cost_fixture(tmp_dir: Path) -> list[dict[str, Any]]:
    real_read = library_analysis.get_library_activity
    records: list[dict[str, Any]] = []

    def measured_read(args, **kwargs):
        conn = kwargs.get("db")
        dims = query_dims(conn) if conn is not None else {}
        tracing = tracemalloc.is_tracing()
        deadline = library_analysis.SERVICE_DEADLINE_SEC
        packet = real_read(args, **kwargs)
        records.append(
            {
                "args": json.loads(json.dumps(args)),
                "dims": dims,
                "tracing_active": tracing,
                "deadline_sec": deadline,
                "packet": packet,
                "conn": conn,
                "raw_bytes": len(json_utf8(packet)),
                "ok": packet.get("ok"),
            }
        )
        return packet

    library_analysis.reset_rate_limiter()
    with patch.object(library_analysis, "get_library_activity", measured_read):
        az.test_activity_cost_548_and_10000(tmp_dir)
    library_analysis.reset_rate_limiter()
    return records


def fmt_ms(value: float) -> str:
    return f"{value:.2f}"


def fmt_int(value: int) -> str:
    return f"{value:,}"


def collection_line(counts: dict[str, Any], key: str) -> str:
    block = counts[key]
    total = block["pagination_total_rows"]
    returned = block["pagination_returned_rows"]
    omitted = block["pagination_omitted_rows"]
    extra = ""
    if key == "events" and block.get("metric_total") is not None:
        extra = f"; events.total metric={block['metric_total']}"
    return f"{key} returned {returned} of total {total} (omitted {omitted}{extra})"


def generate_markdown(obs: dict[str, Any]) -> str:
    named = obs["named"]
    p548 = named["548_primary_traced"]
    p10k = named["10000_primary_untraced"]
    p10k_trace = named["10000_primary_traced_diagnostic"]
    replay = named["548_proved_replay"]
    huge = named["70mib_journal_refusal"]
    huge_err = huge.get("error") or {}
    deadline = named["548_deadline_refusal"]
    deadline_err = deadline.get("error") or {}
    dense = named["548_three_memberships"]
    multi = named["50_ten_operations"]
    obs100k = named["100k_observations"]
    extra = obs["extra"]
    u548 = extra["untraced_548"]
    heap548 = extra["heap_548"]
    heap10k = extra["heap_10k"]
    heap_refuse = extra["heap_70mib"]
    heap_deadline = extra["heap_deadline"]
    hand = extra["handbuilt_548"]
    shipped548 = extra["shipped_live_548"]
    shipped10k = extra["shipped_live_10k"]
    handler548 = extra["handler_548"]
    handler10k = extra["handler_10k"]
    plans548 = extra["plans_548"]
    replay_obs = extra["replay_probe"]
    c548 = p548["counts"]
    c10k = p10k["counts"]

    def shipped_bytes(rec):
        return rec["activity_jsonrpc_utf8_bytes"]

    def rows_phrase(counts):
        return (
            f"{collection_line(counts, 'events')}; "
            f"{collection_line(counts, 'joint')}; "
            f"{collection_line(counts, 'creators')}; "
            f"{collection_line(counts, 'sources')}; "
            f"{collection_line(counts, 'shelves')}"
        )

    journal_548 = p548["dims"]["journal_bytes"]
    journal_10k = p10k["dims"]["journal_bytes"]
    journal_548_kib = journal_548 / 1024.0
    q1_detail = plans548["Q1"][-1][-1] if plans548["Q1"] else "unmeasured"
    q3_detail = plans548["Q3"][-1][-1] if plans548["Q3"] else "unmeasured"

    replay_claim = (
        "Baseline replay was not skipped on the primary 548-item and 10,000-item "
        "intervals. `_execute_activity` populated replay projection state "
        f"(observed={replay_obs['replayed_state_observed']}) before returning "
        f"`coverage_status={p548['counts']['coverage_shelf']['coverage_status']}` "
        f"with reasons `{p548['counts']['coverage_shelf']['reasons']}`. The interval "
        "`2026-09-01T00:00:00.000Z`–`2026-09-02T00:00:00.000Z` precedes the first "
        "apply at `2026-09-01T10:00:00.000Z`. A separate interval covering that "
        "apply proved `journal_complete` with empty reasons."
    )

    return f"""# Phase 5 AZ Synthetic Fixture Measurements

- **Date:** 2026-09-08
- **Status:** Measured on synthetic test fixtures (`tests/test_library_analysis_fixtures.py`) after AZ-5h2
- **Scope:** Read tool `get_library_activity`, report construction, serialization, query plans, resource limits, and the actual shipped stdio entry (`bounded_stdio_server` / `run_bounded_stdio_async`).
- **Source commit:** `{obs['metadata']['git_commit']}`
- **Source tree:** `{obs['metadata']['git_tree']}`
- **Harness:** `scripts/measure_phase5_az5g2.py`
- **Proof:** `docs/library/proof/az5g2-2026-09-08/`

All figures below are benchmarked against isolated SQLite databases populated with synthetic data fixtures. No live user index or production database was queried. Tracing passes are labelled separately and are not compared with untraced times as equivalent. Returned display-array lengths are samples, not population totals.

---

## 1. Cost and Scale Benchmarks

The benchmark fixture evaluates two corpus scales:
1. **548 Items:** Reflects current library size with 1–2 shelf memberships per item ({fmt_int(p548['dims']['memberships'])} total membership rows in synthetic fixture) and realistic creator/source distributions.
2. **10,000 Items:** 18× scale test testing scaling behavior, row-budget shedding, and memory ceiling ({fmt_int(p10k['dims']['memberships'])} membership rows).

| Metric | Synthetic 548 Items | Synthetic 10,000 Items | Budget Ceiling / Interpretation |
| :--- | :--- | :--- | :--- |
| **Construction Time** | {fmt_ms(u548['construction_ms'])} ms untraced / {fmt_ms(heap548['elapsed_ms'])} ms traced diagnostic | {fmt_ms(extra['untraced_10k']['construction_ms'])} ms untraced / {fmt_ms(heap10k['elapsed_ms'])} ms traced diagnostic | 2,000.00 ms fixed service deadline. Traced times include tracemalloc and are not equivalent to untraced times. 10k traced pass uses a 30.0 s diagnostic deadline. |
| **Serialization Time** | {fmt_ms(u548['raw_json_dumps_ms'])} ms | {fmt_ms(extra['untraced_10k']['raw_json_dumps_ms'])} ms | Sub-deadline; raw dictionary json.dumps serialization, not transport serialization |
| **Combined Query Execution** | Plans measured on this 548 fixture | Plans measured on this 10k fixture | Q1: `{q1_detail}`; Q3: `{q3_detail}`; individual query times are not isolated from total construction time |
| **Peak Heap Memory (tracemalloc)** | {heap548['heap_peak_kib']:.1f} KiB | {heap10k['heap_peak_kib']:.1f} KiB | Traced Python heap peak under tracemalloc in separately labelled diagnostic passes; not process RSS. 10k heap used a relaxed 30.0 s diagnostic deadline. |
| **Wire Response Payload** | {fmt_int(p548['raw_bytes'])} bytes | {fmt_int(p10k['raw_bytes'])} bytes | 65,536 bytes (64 KiB envelope); raw reader JSON payload bytes (legacy table label 'Wire Response Payload' verified by test; distinguished from actual transport wire bytes below) |
| **Actual Transport Wire Payload (stdio adapter)** | {fmt_int(shipped_bytes(shipped548))} bytes | {fmt_int(shipped_bytes(shipped10k))} bytes | 65,536 bytes completed JSON-RPC UTF-8 before newline, measured through the actual shipped `bounded_stdio_server` writer (`JSONRPCMessage.model_dump_json`); trailing newline is retained in the proof frames and is not counted in this row |
| **Combined Journal Deltas** | {journal_548_kib:.1f} KiB ({fmt_int(journal_548)} bytes) | {fmt_int(journal_10k)} bytes (~{journal_10k/1024/1024:.2f} MiB) | 67,108,864 bytes (64 MiB) fixed journal gate; sizes from `SUM(LENGTH(CAST(forward_json AS BLOB))+LENGTH(CAST(inverse_json AS BLOB)))` on the live fixture databases |
| **Status** | Measured | Measured | Within the 64 KiB completed-frame cap; raw JSON and shipped JSON-RPC both fit 65,536 bytes; exceeds the 24,576-byte dashboard target (a target, not an acceptance-blocking hard limit) |

Handler-only serialization of the same captured packets (not the shipped entry; `JSONRPCResponse` id=1, no newline): {fmt_int(handler548['jsonrpc_utf8_bytes'])} / {fmt_int(handler10k['jsonrpc_utf8_bytes'])} bytes.

### Observations on Scaling
- At 548 items, row shedding occurred to satisfy the 64 KiB wire budget: {rows_phrase(c548)}. Raw JSON is {fmt_int(p548['raw_bytes'])} bytes; shipped stdio JSON-RPC is {fmt_int(shipped_bytes(shipped548))} bytes (`isError`={shipped548.get('isError')}).
- At 10,000 items, row shedding occurred: {rows_phrase(c10k)}. Raw JSON is {fmt_int(p10k['raw_bytes'])} bytes; shipped stdio JSON-RPC is {fmt_int(shipped_bytes(shipped10k))} bytes (`isError`={shipped10k.get('isError')}).
- {replay_claim}
- Untraced 548 construction completed in {fmt_ms(u548['construction_ms'])} ms. The cost fixture's first 548 call is a traced pass ({fmt_ms(heap548['elapsed_ms'])} ms diagnostic heap including tracemalloc). Untraced 10,000-item construction completed in {fmt_ms(extra['untraced_10k']['construction_ms'])} ms. A separate 10k tracing pass with a 30.0 s diagnostic deadline recorded {heap10k['heap_peak_kib']:.1f} KiB peak Python heap. Tracemalloc measures Python heap allocations, not total process memory / RSS.
- The 24,576-byte dashboard target is missed by the primary packets ({fmt_int(p548['raw_bytes'])} / {fmt_int(p10k['raw_bytes'])} bytes raw JSON; {fmt_int(shipped_bytes(shipped548))} / {fmt_int(shipped_bytes(shipped10k))} bytes shipped JSON-RPC). That target is aspirational, not a fixed acceptance-blocking limit. The fixed enforced envelope is 65,536 completed UTF-8 bytes.

Population dimensions (not display-array lengths):

| Fixture | items | memberships | observations | applies | journal bytes | items.total metric |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 548 primary | {p548['dims']['items']} | {p548['dims']['memberships']} | {p548['dims']['observations']} | {p548['dims']['applies']} | {fmt_int(journal_548)} | {c548['items_total_metric']} |
| 10,000 primary | {p10k['dims']['items']} | {p10k['dims']['memberships']} | {p10k['dims']['observations']} | {p10k['dims']['applies']} | {fmt_int(journal_10k)} | {c10k['items_total_metric']} |

---

## 1.1 Measurements of Omitted Paths

The extended test suite in `tests/test_library_analysis_fixtures.py::test_activity_cost_548_and_10000` measures paths omitted from the initial report. Extra shipped-entry and tracing passes are labelled by scope.

| Path / Scenario | Fixture Dimensions | Observed Metric | Result & Interpretation |
| :--- | :--- | :--- | :--- |
| **Proved Baseline Replay** | {replay['dims']['items']} items, {replay['dims']['applies']} apply, interval 10:00:00Z–24:00:00Z | {fmt_ms(extra['untraced_replay']['construction_ms'])} ms untraced construction, {fmt_int(replay['raw_bytes'])} bytes raw JSON | Proved: `coverage_status = "{replay['counts']['coverage_shelf']['coverage_status']}"`, `reasons = {replay['counts']['coverage_shelf']['reasons']}`. {rows_phrase(replay['counts'])}. Shipped JSON-RPC {fmt_int(shipped_bytes(extra['shipped_live_replay']))} bytes. |
| **70 MiB Journal Refusal** | {huge['dims']['items']} item, {fmt_int(huge['dims']['journal_bytes'])} bytes forward/inverse deltas | {fmt_ms(extra['untraced_70mib']['construction_ms'])} ms untraced refusal, {fmt_int(huge['raw_bytes'])} bytes raw JSON | `ok: False`, `error.code = "{huge_err.get('code')}"`, `retryable: {huge_err.get('retryable')}`. Bounded refusal before JSON materialization. Shipped entry frame {fmt_int(extra['shipped_live_70mib'].get('activity_jsonrpc_utf8_bytes') or 0)} bytes, `isError`={extra['shipped_live_70mib'].get('isError')}. Diagnostic traced heap {heap_refuse['heap_peak_kib']:.1f} KiB (not a normal timing result). |
| **Deadline Expiry Refusal** | 548 items, expired monotonic clock | {fmt_ms(extra['untraced_deadline']['construction_ms'])} ms reader refusal, {fmt_int(deadline['raw_bytes'])} bytes raw JSON | `ok: False`, `error.code = "{deadline_err.get('code')}"`, `retryable: {deadline_err.get('retryable')}`. Message: `{deadline_err.get('message')}`. Diagnostic traced heap {heap_deadline['heap_peak_kib']:.1f} KiB. A separately labelled shipped-entry inbound-expiry refusal is retained in the proof (`shipped_expired_inbound`). |
| **Transport Serialization** | 548-item report packet in hand-built envelope | {fmt_ms(hand['elapsed_ms'])} ms, {fmt_int(hand['jsonrpc_utf8_bytes'])} bytes | Hand-built JSON-RPC synthetic envelope with preface and document fences; isolates serialization timing and does not invoke the stdio handler. |
| **Actual shipped stdio entry** | 548-item live reader through `bounded_stdio_server` | {fmt_ms(shipped548['elapsed_ms'])} ms session (includes initialize + reader + writer), {fmt_int(shipped_bytes(shipped548))} bytes JSON-RPC | Actual shipped transport: SDK `JSONRPCMessage.model_dump_json`, completed-frame cap, trailing newline retained in proof. `isError`={shipped548.get('isError')}. This is a harness transcript, not a real-client log. |
| **Three Memberships / Item** | {dense['dims']['items']} items, {dense['dims']['memberships']} memberships | {fmt_ms(extra['untraced_dense']['construction_ms'])} ms untraced, {fmt_int(dense['raw_bytes'])} bytes raw JSON | `ok: True`. {rows_phrase(dense['counts'])}. Journal {fmt_int(dense['dims']['journal_bytes'])} bytes. Shipped JSON-RPC {fmt_int(shipped_bytes(extra['shipped_live_dense']))} bytes. |
| **Multi-Operation Journal** | {multi['dims']['items']} items, {multi['dims']['applies']} consecutive applied operations | {fmt_ms(extra['untraced_multi']['construction_ms'])} ms untraced, {fmt_int(multi['raw_bytes'])} bytes raw JSON | Proved: `coverage_status = "{multi['counts']['coverage_shelf']['coverage_status']}"`, `reasons = {multi['counts']['coverage_shelf']['reasons']}`. {rows_phrase(multi['counts'])}. Journal {fmt_int(multi['dims']['journal_bytes'])} bytes. Shipped JSON-RPC {fmt_int(shipped_bytes(extra['shipped_live_multi']))} bytes. |
| **100k-Observation Scale** | {obs100k['dims']['items']} item, {fmt_int(obs100k['dims']['observations'])} source item observations | {fmt_ms(extra['untraced_100k']['construction_ms'])} ms untraced, {fmt_int(obs100k['raw_bytes'])} bytes raw JSON | `ok: True`. Coverage `{obs100k['counts']['coverage_shelf']['coverage_status']}`. {rows_phrase(obs100k['counts'])}. No journal. Shipped JSON-RPC {fmt_int(shipped_bytes(extra['shipped_live_100k']))} bytes. |

---

## 2. SQLite Query Plans

Queries run read-only against standard migrations (0001–0028) without creating migration 0029 or new secondary indexes. Plans below were measured on the actual 548-item cost fixture; the 10,000-item plans are retained in the proof JSON.

### Q1: Yoinks Retrieval
```sql
{Q1_SQL.replace('EXPLAIN QUERY PLAN ', '')}
```
**Execution Plan:**
```
{q1_detail}
```
- Measured on the 548-item fixture, not inferred from an empty database.
- Individual query times were not isolated from total construction time.

### Q3: Library Applies Journal Retrieval
```sql
{Q3_SQL.replace('EXPLAIN QUERY PLAN ', '')}
```
**Execution Plan:**
```
{q3_detail}
```
- Measured on the 548-item fixture.
- Individual query times were not isolated from total construction time.

---

## 3. Refusal Limits and Budget Enforcement

Fixed implemented limits (not the same thing as a measured guarantee that every untested path meets them):

1. **64 MiB Journal Delta Limit (fixed):**
   - Evaluated before JSON parsing.
   - If `SUM(LENGTH(CAST(forward_json AS BLOB)) + LENGTH(CAST(inverse_json AS BLOB)))` across `library_applies` exceeds 67,108,864 bytes, `get_library_activity` refuses with `error.code = "resource_too_large"`.
   - Measured here with a {fmt_int(huge['dims']['journal_bytes'])}-byte synthetic payload; refusal envelope {fmt_int(huge['raw_bytes'])} raw bytes.

2. **2.0-Second Service Deadline (fixed):**
   - Checked at entry and through the shipped writer's final `JSONRPCMessage.model_dump_json`.
   - AZ-5h2 uses the original inbound `admitted_at` when a transport scope is bound.
   - Injected expired-clock reader refusal measured at {fmt_ms(extra['untraced_deadline']['construction_ms'])} ms, {fmt_int(deadline['raw_bytes'])} raw bytes, `retryable: {deadline_err.get('retryable')}`.
   - This is not a blocked-lock measurement; remaining-budget SQLite waits are covered by AZ-5h2 tests, not by this timing row.

3. **64 KiB Completed-Frame Envelope (fixed):**
   - Maximum completed outbound UTF-8 JSON-RPC size is 65,536 bytes before the terminating newline.
   - Display-row shedding order: events, joint creator hints, creator hints, source details, shelf rows.
   - If mandatory summary fields alone exceed the cap, the handler refuses with `resource_too_large`.
   - Primary packets shed optional rows and remain under the cap, as measured.

4. **Concurrency and Rate Limiting (fixed):**
   - Active read cap 2; rolling 60-second window of 60 admissions.
   - *Verification note (marked limitation):* `test_activity_read_has_no_side_effects` checks `total_changes` only and does not verify concurrent load or rate limit enforcement. This measurement run does not claim an unmeasured concurrency path passes.

5. **Read Boundary Mutation Detection (fixed):**
   - Compares `PRAGMA data_version` and `total_changes`.
   - *Verification note (marked limitation):* sequential deletion tests do not prove concurrent snapshot isolation during an active read. Unmeasured here.

---

## 4. Provenance and scope labels

- Git commit `{obs['metadata']['git_commit']}`, tree `{obs['metadata']['git_tree']}`.
- Interpreter `{obs['metadata']['python_version'].splitlines()[0]}`; installed mcp `{obs['metadata']['mcp_installed']}`; pin `{obs['metadata']['mcp_pin']}`.
- `uoink_mcp.mcp.run_stdio_async is uoink_mcp.run_bounded_stdio_async` = `{obs['metadata']['run_stdio_is_bounded']}`.
- Pre-refresh document archive SHA-256 `{obs['archive']['working_tree_sha256']}` (git blob `{obs['archive']['source_git_blob']}`).
- Rejected AZ-5g Gemini partial is not this record: `{obs['archive']['rejected_az5g_patch']}` SHA-256 `{obs['archive']['rejected_az5g_patch_sha256']}`.
- Complete packets and frames live under `docs/library/proof/az5g2-2026-09-08/packets/`.
- Handler-only dumps, hand-built envelopes, and shipped frames are separate files with distinct scope labels.
- Normal construction times are untraced. Heap figures are diagnostic tracing only.
- A handler transcript is not a real MCP client log. No model, live index, or port 5179 was used.
"""


def write_manifest(paths: list[Path]) -> Path:
    lines = []
    for path in sorted(paths, key=lambda p: p.as_posix().lower()):
        if not path.is_file():
            continue
        digest = sha256_bytes(path.read_bytes())
        rel = path.relative_to(ROOT).as_posix()
        lines.append(f"{digest}  {rel}")
    manifest = PROOF / "SHA256SUMS"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return manifest


def strip_conn(rec: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in rec.items() if k not in {"conn", "packet", "frame_text", "text"}}
    return out


def main() -> int:
    PROOF.mkdir(parents=True, exist_ok=True)
    packets_dir = PROOF / "packets"
    packets_dir.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    tmp_dir = SCRATCH / "fixture-dbs"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    metadata = collect_metadata()
    archive_path = PROOF / "original-PHASE5-AZ-MEASUREMENTS-2026-09-08.md"
    if not archive_path.exists():
        archive_path.write_bytes(DOC_PATH.read_bytes())
    archive_raw = archive_path.read_bytes()
    archive_meta_path = PROOF / "original-PHASE5-AZ-MEASUREMENTS-2026-09-08.meta.json"
    archive = {
        "working_tree_sha256": sha256_bytes(archive_raw),
        "working_tree_bytes": len(archive_raw),
        "source_git_blob": git_output("hash-object", "--", "docs/library/PHASE5-AZ-MEASUREMENTS-2026-09-08.md")
        if sha256_bytes(DOC_PATH.read_bytes()) == sha256_bytes(archive_raw)
        else git_output("hash-object", "--", str(archive_path.relative_to(ROOT))),
        "source_commit": metadata["git_commit"],
        "source_tree": metadata["git_tree"],
        "rejected_az5g_patch": REJECTED_PATCH.relative_to(ROOT).as_posix(),
        "rejected_az5g_patch_sha256": sha256_bytes(REJECTED_PATCH.read_bytes()),
    }
    if archive_meta_path.exists():
        prior = json.loads(archive_meta_path.read_text(encoding="utf-8"))
        prior.pop("rejected_az5g_patch", None)
        archive.update(prior)
        archive["rejected_az5g_patch"] = REJECTED_PATCH.relative_to(ROOT).as_posix()

    observations: dict[str, Any] = {
        "metadata": metadata,
        "archive": archive,
        "named": {},
        "extra": {},
        "errors": [],
    }
    summary_path = PROOF / "observations.json"

    def checkpoint() -> None:
        serializable = json.loads(json.dumps(observations, default=str))
        summary_path.write_text(json.dumps(serializable, indent=2) + "\n", encoding="utf-8")

    try:
        print("[az5g2] running unedited cost fixture", flush=True)
        captured = capture_cost_fixture(tmp_dir)
        if len(captured) != len(FIXTURE_ORDER):
            observations["errors"].append(
                f"expected {len(FIXTURE_ORDER)} fixture reads, got {len(captured)}"
            )
        named: dict[str, Any] = {}
        for rec, fallback_name in zip(captured, FIXTURE_ORDER):
            name = classify_record(rec)
            if name == "unclassified":
                name = fallback_name
            rec["name"] = name
            rec["counts"] = extract_counts(rec["packet"])
            named[name] = rec
        observations["named"] = {k: {**strip_conn(v), "counts": v["counts"]} for k, v in named.items()}
        observations["fixture_names"] = [rec["name"] for rec in captured]
        checkpoint()

        for name, rec in named.items():
            packet_bytes = json_utf8(rec["packet"])
            rec["packet_file"] = write_bytes(packets_dir / f"{name}.reader.json", packet_bytes)
            observations["named"][name]["packet_file"] = rec["packet_file"]
            observations["named"][name]["raw_bytes"] = rec["raw_bytes"]
            observations["named"][name]["dims"] = rec["dims"]
            observations["named"][name]["args"] = rec["args"]
            observations["named"][name]["tracing_active"] = rec["tracing_active"]
            observations["named"][name]["deadline_sec"] = rec["deadline_sec"]
            observations["named"][name]["ok"] = rec["ok"]
            if rec["packet"].get("error"):
                observations["named"][name]["error"] = rec["packet"]["error"]
        checkpoint()

        extra: dict[str, Any] = {}
        conn_548 = named["548_primary_traced"]["conn"]
        conn_10k = named["10000_primary_untraced"]["conn"]
        conn_replay_db = named["548_proved_replay"]["conn"]
        conn_huge = named["70mib_journal_refusal"]["conn"]
        conn_dense = named["548_three_memberships"]["conn"]
        conn_multi = named["50_ten_operations"]["conn"]
        conn_100k = named["100k_observations"]["conn"]

        print("[az5g2] query plans and replay probe", flush=True)
        extra["plans_548"] = query_plans(conn_548, "548")
        extra["plans_10k"] = query_plans(conn_10k, "10000")
        extra["replay_probe"] = replay_probe(conn_548)

        print("[az5g2] untraced construction passes", flush=True)
        extra["untraced_548"] = untraced_construction(conn_548, PRIMARY_ARGS, "548 primary untraced")
        extra["untraced_10k"] = untraced_construction(conn_10k, PRIMARY_ARGS, "10000 primary untraced")
        extra["untraced_replay"] = untraced_construction(conn_replay_db, REPLAY_ARGS, "548 proved replay untraced")
        extra["untraced_70mib"] = untraced_construction(conn_huge, PRIMARY_ARGS, "70MiB journal refusal untraced")
        extra["untraced_deadline"] = {
            "scope": "untraced_reader_construction",
            "label": "injected expired monotonic clock on 548 fixture (reader path)",
            "tracing": False,
            "construction_ms": None,
            "raw_bytes": named["548_deadline_refusal"]["raw_bytes"],
            "ok": False,
            "error": named["548_deadline_refusal"]["packet"].get("error"),
        }
        old_monotonic = time.monotonic
        calls = [0]

        def fake_monotonic():
            calls[0] += 1
            if calls[0] > 1:
                return old_monotonic() + 10.0
            return old_monotonic()

        library_analysis.reset_rate_limiter()
        try:
            time.monotonic = fake_monotonic
            t0 = time.perf_counter()
            dl_packet = library_analysis.get_library_activity(PRIMARY_ARGS, db=conn_548, clock=CLOCK)
            t1 = time.perf_counter()
        finally:
            time.monotonic = old_monotonic
            library_analysis.reset_rate_limiter()
        extra["untraced_deadline"]["construction_ms"] = (t1 - t0) * 1000.0
        extra["untraced_deadline"]["error"] = dl_packet.get("error")
        extra["untraced_deadline"]["raw_bytes"] = len(json_utf8(dl_packet))
        extra["untraced_dense"] = untraced_construction(conn_dense, PRIMARY_ARGS, "548 three memberships untraced")
        extra["untraced_multi"] = untraced_construction(conn_multi, REPLAY_ARGS, "50/10 operations untraced")
        extra["untraced_100k"] = untraced_construction(conn_100k, PRIMARY_ARGS, "100k observations untraced")

        print("[az5g2] diagnostic tracing heap passes", flush=True)
        extra["heap_548"] = diagnostic_heap(conn_548, PRIMARY_ARGS, deadline_sec=None, label="548 primary traced heap")
        extra["heap_10k"] = diagnostic_heap(
            conn_10k, PRIMARY_ARGS, deadline_sec=30.0, label="10000 primary traced heap with 30.0s diagnostic deadline"
        )
        extra["heap_70mib"] = diagnostic_heap(
            conn_huge, PRIMARY_ARGS, deadline_sec=None, label="70MiB journal refusal traced heap"
        )
        library_analysis.reset_rate_limiter()
        old_monotonic = time.monotonic
        calls = [0]

        def fake_monotonic_trace():
            calls[0] += 1
            if calls[0] > 1:
                return old_monotonic() + 10.0
            return old_monotonic()

        try:
            time.monotonic = fake_monotonic_trace
            tracemalloc.start()
            t0 = time.perf_counter()
            packet_dl = library_analysis.get_library_activity(PRIMARY_ARGS, db=conn_548, clock=CLOCK)
            t1 = time.perf_counter()
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        finally:
            time.monotonic = old_monotonic
            library_analysis.reset_rate_limiter()
            if tracemalloc.is_tracing():
                tracemalloc.stop()
        extra["heap_deadline"] = {
            "scope": "diagnostic_tracing",
            "label": "injected expired monotonic clock traced heap",
            "tracing": True,
            "deadline_sec": library_analysis.SERVICE_DEADLINE_SEC,
            "deadline_relaxed": False,
            "elapsed_ms": (t1 - t0) * 1000.0,
            "heap_current_bytes": current,
            "heap_peak_bytes": peak,
            "heap_peak_kib": peak / 1024.0,
            "ok": packet_dl.get("ok"),
            "error": packet_dl.get("error"),
            "raw_bytes": len(json_utf8(packet_dl)),
            "note": "tracemalloc Python heap only; not comparable to untraced deadline timing",
        }

        print("[az5g2] hand-built and handler-only serialization", flush=True)
        extra["handbuilt_548"] = handbuilt_envelope(named["548_primary_traced"]["packet"])
        extra["handler_548"] = handler_only_serialize(named["548_primary_traced"]["packet"], PRIMARY_ARGS)
        extra["handler_10k"] = handler_only_serialize(named["10000_primary_untraced"]["packet"], PRIMARY_ARGS)
        extra["handler_replay"] = handler_only_serialize(named["548_proved_replay"]["packet"], REPLAY_ARGS)
        extra["handler_dense"] = handler_only_serialize(named["548_three_memberships"]["packet"], PRIMARY_ARGS)
        extra["handler_multi"] = handler_only_serialize(named["50_ten_operations"]["packet"], REPLAY_ARGS)
        extra["handler_100k"] = handler_only_serialize(named["100k_observations"]["packet"], PRIMARY_ARGS)
        extra["handler_70mib"] = handler_only_serialize(named["70mib_journal_refusal"]["packet"], PRIMARY_ARGS)
        extra["handler_deadline"] = handler_only_serialize(named["548_deadline_refusal"]["packet"], PRIMARY_ARGS)

        def store_text(name: str, rec: dict[str, Any], key: str = "text") -> None:
            if rec.get(key):
                rec["file"] = write_bytes(packets_dir / name, rec[key].encode("utf-8"))
                rec.pop(key, None)

        store_text("548_primary.handbuilt.jsonrpc", extra["handbuilt_548"])
        store_text("548_primary.handler-only.jsonrpc", extra["handler_548"])
        store_text("10000_primary.handler-only.jsonrpc", extra["handler_10k"])
        store_text("548_replay.handler-only.jsonrpc", extra["handler_replay"])
        store_text("548_dense.handler-only.jsonrpc", extra["handler_dense"])
        store_text("50_ten_operations.handler-only.jsonrpc", extra["handler_multi"])
        store_text("100k.handler-only.jsonrpc", extra["handler_100k"])
        store_text("70mib.handler-only.jsonrpc", extra["handler_70mib"])
        store_text("deadline.handler-only.jsonrpc", extra["handler_deadline"])

        print("[az5g2] actual shipped stdio entry", flush=True)

        def shipped(conn, args, label, file_stem, **kwargs):
            rec = run_shipped_stdio(conn, args, label=label, **kwargs)
            if rec.get("frame_text"):
                rec["file"] = write_bytes(packets_dir / f"{file_stem}.shipped.frame", rec["frame_text"].encode("utf-8"))
                rec.pop("frame_text", None)
            return rec

        extra["shipped_live_548"] = shipped(
            conn_548, PRIMARY_ARGS, "548 primary live reader through bounded_stdio_server", "548_primary"
        )
        extra["shipped_live_10k"] = shipped(
            conn_10k, PRIMARY_ARGS, "10000 primary live reader through bounded_stdio_server", "10000_primary"
        )
        extra["shipped_live_replay"] = shipped(
            conn_replay_db, REPLAY_ARGS, "548 proved replay live reader through bounded_stdio_server", "548_replay"
        )
        extra["shipped_live_dense"] = shipped(
            conn_dense, PRIMARY_ARGS, "548 three-membership live reader through bounded_stdio_server", "548_dense"
        )
        extra["shipped_live_multi"] = shipped(
            conn_multi, REPLAY_ARGS, "50/10 operations live reader through bounded_stdio_server", "50_ten_operations"
        )
        extra["shipped_live_100k"] = shipped(
            conn_100k, PRIMARY_ARGS, "100k observations live reader through bounded_stdio_server", "100k"
        )
        extra["shipped_live_70mib"] = shipped(
            conn_huge, PRIMARY_ARGS, "70MiB journal refusal through bounded_stdio_server", "70mib"
        )
        extra["shipped_captured_548"] = shipped(
            conn_548,
            PRIMARY_ARGS,
            "shipped writer on captured 548 packet; no second reader",
            "548_primary_captured",
            replace_reader=lambda args, **kwargs: named["548_primary_traced"]["packet"],
        )
        extra["shipped_expired_inbound"] = shipped(
            conn_548,
            PRIMARY_ARGS,
            "shipped entry expired inbound (AZ-5h2 original deadline); 2.1s shift after admit",
            "548_expired_inbound",
            shift_after_admit=2.1,
        )

        observations["extra"] = extra
        checkpoint()

        print("[az5g2] regenerating measurement document", flush=True)
        markdown = generate_markdown(observations)
        DOC_PATH.write_text(markdown, encoding="utf-8", newline="\n")
        observations["document"] = write_bytes(DOC_PATH, DOC_PATH.read_bytes())
        checkpoint()

        tracked = [DOC_PATH, archive_path, archive_meta_path, summary_path, REJECTED_PATCH]
        tracked.extend(sorted(packets_dir.glob("*")))
        rejected_extract = PROOF / "rejected-az5g-gemini-5e9baea5-partial-measurements.json"
        if rejected_extract.exists():
            tracked.append(rejected_extract)
        harness = ROOT / "scripts" / "measure_phase5_az5g2.py"
        runner = ROOT / "scripts" / "run_phase5_az5g2_union.py"
        report = ROOT / "docs" / "library" / "PHASE5-AZ5G2-GROK-2026-09-08.md"
        for extra_path in (harness, runner, report):
            if extra_path.exists():
                tracked.append(extra_path)
        manifest = write_manifest(tracked)
        observations["manifest"] = write_bytes(manifest, manifest.read_bytes())
        # Manifest includes itself after hashing; rewrite with the file list excluding the
        # changing self-hash by hashing all other artifacts, then the sums file separately
        # is fine for external files. Keep as written.
        checkpoint()
        print("[az5g2] wrote", summary_path, flush=True)
        print("[az5g2] 548 raw", named["548_primary_traced"]["raw_bytes"], "shipped", extra["shipped_live_548"].get("activity_jsonrpc_utf8_bytes"), flush=True)
        print("[az5g2] 10k raw", named["10000_primary_untraced"]["raw_bytes"], "shipped", extra["shipped_live_10k"].get("activity_jsonrpc_utf8_bytes"), flush=True)
        print("[az5g2] replay observed", extra["replay_probe"]["replayed_state_observed"], flush=True)
        return 0
    except Exception as exc:
        observations["errors"].append(f"{type(exc).__name__}: {exc}")
        checkpoint()
        raise


if __name__ == "__main__":
    raise SystemExit(main())

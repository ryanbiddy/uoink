"""Validate real client payloads against the tightened receiver, entirely offline."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from tests.fixtures.usage_receiver import validate_ping
from tests.test_usage_sharing import enabled, store  # noqa: F401
import uoink_mcp_tools as tools
import uoink_usage as usage


@pytest.fixture
def payload_shapes(store):
    shapes = {"off_sample": usage.disclosure()["next_payload"], "fresh_install": enabled()}
    for transport in ("stdio", "http"):
        usage.set_enabled(False)
        enabled()
        usage.mcp_call("search_library", transport)
        usage.count("mcp_clients", "codex-mcp-client")
        usage._queue.join()
        shapes[transport + "_only"] = usage.disclosure()["next_payload"]
    with usage._transaction() as state:
        state["counts"] = {"tools": {name: 1 for name in tools.TOOL_REGISTRY}}
        shapes["all_tools"] = usage._payload(state, time.time())
        state["counts"] = {
            "tools": {name: usage.MAX_COUNT for name in tools.TOOL_REGISTRY},
            "mcp_clients": {name: usage.MAX_COUNT for name in set(usage.CLIENTS.values()) | {"other"}},
            "transports": {name: usage.MAX_COUNT for name in ("stdio", "http")},
            "captures": {s + ":" + o: usage.MAX_COUNT for s in usage.SOURCES for o in ("ok", "failed")},
            "searches": {"count": usage.MAX_COUNT},
        }
        shapes["max_counts"] = usage._payload(state, state["since"] + 1e10)
    return shapes


def test_real_payloads_match_tightened_receiver(payload_shapes):
    assert set(payload_shapes["all_tools"]["tools"]) == set(tools.TOOL_REGISTRY)
    assert len(tools.TOOL_REGISTRY) <= usage.MAX_TOOL_KEYS == 128
    for shape, payload in payload_shapes.items():
        assert validate_ping(payload) == payload, shape
        assert set(payload["transports"]) == {"stdio", "http"}
        assert len(usage._encode(payload)) <= 4096
    sample = payload_shapes["off_sample"]
    assert sample["install_id"] == sample["report_id"] == usage.SAMPLE_ID
    assert sample["tools"] == sample["captures"] == sample["mcp_clients"] == {}
    assert sample["searches"] == sample["period_hours"] == 0


def contract_cases(base):
    cases = [(True, base)]
    legacy = copy.deepcopy(base)
    legacy.pop("report_id")
    cases.append((True, legacy))
    for changes in (
        {"version": "1.2.3-rc.1+001", "os_major": "007", "arch": "other"},
        {"period_hours": 100000, "searches": 100000, "os_major": "unknown"},
        {"tools": {"abc": 1}, "mcp_clients": {}, "captures": {}},
        {"tools": {f"tool_{i}": 0 for i in range(128)}, "searches": 1.0},
        {"report_id": base["report_id"].upper(), "install_id": base["install_id"].upper()},
    ):
        cases.append((True, {**base, **changes}))
    for field, invalid in (
        ("schema", [True, "1", 2]),
        ("report_id", [None, "", base["report_id"] + "\n", "00000000-0000-0000-0000-000000000000"]),
        ("install_id", [False, base["install_id"] + "\n"]),
        ("version", ["v1.2.3", "01.2.3", "1.2.3-01", "1.2", "1.2.3\n", "1.2.3-١"]),
        ("os", ["Windows", "windows\n"]),
        ("os_major", ["private text", "1234", "١", "1\n", 1]),
        ("arch", ["x86", "private computer", "arm64\n"]),
        ("install_kind", ["private path", "source\n"]),
        ("period_hours", [True, -1, 100001, 10 ** 400, "24"]),
        ("transports", [{}, {"stdio": 1}, {"stdio": 0, "http": 0, "extra": 0}, {"stdio": True, "http": 0}]),
        ("tools", [{"private.tool": 1}, {"a": 1}, {"bad-tool": 1}, {"abc\n": 1},
                   {f"tool_{i}": 0 for i in range(129)}, {"abc": 100001}, {"abc": 0.5}, []]),
        ("mcp_clients", [{"claude-ai": 1}, {"codex-mcp-client": 1}, {"other\n": 1}, None]),
        ("captures", [{"nytimes.com": {"ok": 1, "failed": 0}}, {"page": {"ok": 1}},
                      {"page": {"ok": 1, "failed": 0, "extra": 0}}, {"page": {"ok": True, "failed": 0}}]),
        ("searches", [True, -1, 100001, 1.5, "1"]),
    ):
        cases.extend((False, {**base, field: value}) for value in invalid)
    cases.extend([(False, {**base, "private": "extra"}), (False, None), (False, []),
                  (False, {key: value for key, value in base.items() if key != "transports"}),
                  (False, {**base, "version": "1.2.3+" + "a" * 4096})])
    boundary = {**base, "version": "1.2.3+"}
    boundary["version"] += "a" * (4096 - len(usage._encode(boundary)))
    cases.append((True, boundary))
    cases.append((False, {**boundary, "version": boundary["version"] + "a"}))
    return cases


def test_mirror_rejects_non_contract_shapes(payload_shapes):
    for expected, payload in contract_cases(payload_shapes["fresh_install"]):
        if expected:
            validate_ping(payload)
        else:
            with pytest.raises(ValueError):
                validate_ping(payload)


def test_local_receiver_and_mirror_agree(payload_shapes):
    node = shutil.which("node")
    source = Path(os.environ.get("UOINK_USAGE_VALIDATION_TS", "E:/AI/projects/uoink-usage/src/validation.ts"))
    if not node or not source.is_file():
        pytest.skip("Local Node receiver unavailable; independent Python R1 mirror still runs")
    cases = [(True, p) for p in payload_shapes.values()] + contract_cases(payload_shapes["fresh_install"])
    script = r'''
import fs from 'node:fs';
const {readPing} = await import(process.argv[1]);
const bodies = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = [];
for (const body of bodies) {
  // Request is an in-memory body here. No fetch, socket or endpoint is used.
  try {
    await readPing(new Request('https://receiver-test.invalid/v1/ping', {
      method: 'POST', body
    }));
    results.push(true);
  } catch { results.push(false); }
}
process.stdout.write(JSON.stringify(results));
'''
    result = subprocess.run([node, "--experimental-transform-types", "--input-type=module", "-e", script,
                             source.resolve().as_uri()], input=json.dumps([usage._encode(p).decode("utf-8") for _, p in cases]),
                            capture_output=True, text=True, timeout=15)
    if "bad option: --experimental-transform-types" in result.stderr:
        pytest.skip("Node cannot load this TypeScript; independent Python R1 mirror still runs")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [expected for expected, _ in cases]

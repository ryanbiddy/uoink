"""API, MCP and CLI smoke against a running isolated helper (no browser).

Imported by scripts/qa_smoke.py. Uses only the standard library and talks to
the helper over HTTP; the CLI checks run uoink_cli.py in child processes with
the same isolated environment. Each check returns one result row.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

EXPECTED_TOOL_COUNTS = {"full": 99, "core": 36, "search": 9, "research": 7}
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Client:
    def __init__(self, base_url: str, profile: Path):
        self.base_url = base_url.rstrip("/")
        self.profile = Path(profile)

    def token(self) -> str:
        return (self.profile / "token.txt").read_text(encoding="utf-8").strip()

    def call(self, path: str, *, method: str = "GET", body: dict | None = None, auth: bool = True):
        headers = {"X-Uoink-Token": self.token()} if auth else {}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with _OPENER.open(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, {"raw": raw[:300]}


def _check(name, fn):
    started = time.monotonic()
    try:
        detail = fn()
        ok = True
    except AssertionError as exc:
        ok, detail = False, str(exc) or "assertion failed"
    except Exception as exc:  # a crash in a check is a failure, not a harness error
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return {"suite": "api", "name": name, "ok": ok, "detail": str(detail or "")[:400],
            "seconds": round(time.monotonic() - started, 2)}


def api_checks(client: Client, expect: dict, state: str) -> list[dict]:
    rows = []
    total = int(expect.get("total", 0))

    def health():
        status, data = client.call("/health", auth=False)
        assert status == 200 and data.get("ok") is True, f"/health answered {status}: {data}"
        assert data.get("index_recovering") is False, "index is recovering"
        return f"version {data.get('version')}, migration {data.get('migration_version')}"
    rows.append(_check("health", health))

    def library_list():
        status, data = client.call("/memory/search?limit=50")
        assert status == 200, f"/memory/search answered {status}: {data}"
        assert data.get("corpus_total") == total, f"library has {data.get('corpus_total')}, seeded {total}"
        assert len(data.get("results") or []) == min(total, 50), f"listed {len(data.get('results') or [])}"
        return f"{data.get('corpus_total')} items"
    rows.append(_check("list", library_list))

    if state != "seeded":
        return rows

    phrase = expect["search_phrase"]
    item_id = expect["search_item_id"]

    def search():
        q = urllib.parse.quote(phrase)
        status, data = client.call(f"/memory/search?q={q}&match=strict&limit=5")
        assert status == 200, f"/memory/search answered {status}: {data}"
        hits = data.get("results") or []
        assert hits and hits[0].get("video_id") == item_id, f"top hit {hits[:1]}"
        passage = hits[0].get("passage") or {}
        assert phrase in (passage.get("text") or "").lower(), "the passage does not quote the phrase"
        seconds = hits[0].get("timestamp_seconds")
        assert seconds is not None and expect["search_seconds"] - 60 <= seconds <= expect["search_seconds"], \
            f"timestamp {seconds} is not at the phrase ({expect['search_seconds']}s)"
        return f"{len(hits)} hit(s), top at {seconds}s"
    rows.append(_check("search", search))

    def get_item():
        status, data = client.call(f"/yoinks/{item_id}/details")
        assert status == 200 and data.get("ok"), f"details answered {status}: {data}"
        return "details ok"
    rows.append(_check("get", get_item))

    def corpus_read():
        status, data = client.call(f"/api/corpus/v1/items/{item_id}")
        assert status == 200 and data.get("ok"), f"corpus get answered {status}: {data}"
        item = (data.get("data") or {}).get("item") or {}
        assert item.get("title") == expect["search_item_title"], f"title {item.get('title')}"
        q = urllib.parse.quote(phrase)
        status, data = client.call(f"/api/corpus/v1/search?q={q}&limit=3")
        assert status == 200 and data.get("ok"), f"corpus search answered {status}: {data}"
        found = json.dumps(data)
        assert item_id in found, "corpus search did not return the item"
        return "item + search ok"
    rows.append(_check("corpus read", corpus_read))

    def mcp_tools():
        status, data = client.call("/mcp/v1", method="POST",
                                   body={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                         "params": {"clientInfo": {"name": "uoink-qa-smoke", "version": "1"}}})
        assert status == 200 and "result" in data, f"initialize answered {status}: {data}"
        status, data = client.call("/mcp/v1", method="POST", body={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert status == 200 and "result" in data, f"tools/list answered {status}: {data}"
        count = len(data["result"].get("tools") or [])
        assert count == EXPECTED_TOOL_COUNTS["full"], f"MCP HTTP lists {count} tools, expected 99"
        status, data = client.call("/mcp/v1", method="POST", body={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "search_library", "arguments": {"query": phrase, "limit": 3}}})
        assert status == 200 and not data.get("result", {}).get("isError"), f"tools/call answered {status}: {data}"
        assert item_id in json.dumps(data), "search_library over MCP did not find the item"
        return f"{count} tools, search_library ok"
    rows.append(_check("mcp http", mcp_tools))
    return rows


def cli_checks(repo: Path, env: dict, expect: dict, state: str) -> list[dict]:
    """Run `uoink` agent commands (uoink_cli.py) against the isolated profile."""
    cli = [sys.executable, str(repo / "uoink_cli.py")]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    def run(*args):
        proc = subprocess.run([*cli, *args], cwd=str(repo), env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120, creationflags=flags)
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            raise AssertionError(f"uoink {' '.join(args)} printed no JSON (exit {proc.returncode}): "
                                 f"{proc.stdout[-200:]} {proc.stderr[-300:]}")
        assert proc.returncode == 0 and data.get("ok") is not False, \
            f"uoink {' '.join(args)} exit {proc.returncode}: {json.dumps(data)[:300]}"
        return data

    rows = []

    def status():
        data = run("status")
        assert data.get("helper_running") is True, "status says the helper is not running"
        assert Path(data.get("data_dir", "")).resolve() == Path(env["UOINK_ISOLATED_PROFILE"]).resolve(), \
            f"status data_dir {data.get('data_dir')} is not the isolated profile"
        return f"version {data.get('version')}"
    rows.append(_check("cli status", status))

    def tools():
        counts = {}
        for toolset, want in EXPECTED_TOOL_COUNTS.items():
            data = run("tools", "--toolset", toolset)
            counts[toolset] = len(data.get("tools") or [])
        assert counts == EXPECTED_TOOL_COUNTS, f"tool counts {counts}, expected {EXPECTED_TOOL_COUNTS}"
        return " / ".join(str(counts[k]) for k in EXPECTED_TOOL_COUNTS)
    rows.append(_check("cli tools 99/36/9/7", tools))

    def recent():
        data = run("recent", "--limit", "5")
        n = len(data.get("yoinks") or data.get("items") or [])
        assert n == min(5, int(expect.get("total", 0))), f"recent listed {n}"
        return f"{n} items"
    rows.append(_check("cli recent", recent))

    if state == "seeded":
        def search():
            data = run("search", expect["search_phrase"], "--limit", "3")
            hits = data.get("hits") or []
            assert hits and hits[0].get("item_id") == expect["search_item_id"], f"top hit {hits[:1]}"
            return f"top hit at {hits[0].get('start')}s"
        rows.append(_check("cli search", search))

        def get():
            data = run("get", expect["search_item_id"])
            assert (data.get("card") or {}).get("title") == expect["search_item_title"], "wrong card"
            return "card ok"
        rows.append(_check("cli get", get))
    for row in rows:
        row["suite"] = "cli"
    return rows

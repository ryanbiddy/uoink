"""V-3 -- /auto-uoink/scan opt-in gate + /auto-uoink/status contract.

Run: python tests/test_auto_uoink_scan.py  (or via pytest tests/)

Red on unpatched main: the routes 404, and /settings has no
auto_uoink_enabled field, so the default-OFF + gate assertions fail.

Green with the fix:
  * auto_uoink_enabled defaults OFF in /settings (opt-in safety);
  * POST /auto-uoink/scan with the toggle OFF -> 409, captures nothing;
  * with the toggle ON but no monitored sources -> honest needs_sources
    response (no crawler, no capture);
  * GET /auto-uoink/status reflects enabled + source count + token gate.
"""
from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import index as index_mod  # noqa: E402
import server  # noqa: E402

PORT = 5261


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _req(method, path, *, token=True, body=None):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", headers=headers,
        data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def test_auto_uoink_scan():
    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    server._get_index = lambda: idx  # type: ignore
    server.SETTINGS_PATH = Path(tmp.name) / "settings.json"  # type: ignore
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        # 1. Default OFF (opt-in safety).
        status, res = _req("GET", "/settings")
        _assert(status == 200, f"/settings ok: {status}")
        s = res.get("settings") or {}
        _assert(s.get("auto_uoink_enabled") is False,
                f"auto-uoink must default OFF: {s.get('auto_uoink_enabled')}")
        _assert(s.get("auto_uoink_threshold") is not None,
                "threshold surfaced in settings")
        print("ok  auto_uoink_enabled defaults OFF")

        # 2. Token gate on status.
        status, _ = _req("GET", "/auto-uoink/status", token=False)
        _assert(status == 403, f"status without token -> 403, got {status}")
        print("ok  /auto-uoink/status is token-gated")

        # 3. Scan while OFF -> 409, captures nothing.
        status, res = _req("POST", "/auto-uoink/scan", body={})
        _assert(status == 409, f"scan while off -> 409, got {status}: {res}")
        _assert(res.get("enabled") is False, f"reports disabled: {res}")
        print("ok  scan refuses while opt-in is off (409)")

        # 4. Turn it ON.
        server._write_settings({"auto_uoink_enabled": True})  # type: ignore
        status, res = _req("GET", "/auto-uoink/status")
        _assert(res["auto_uoink"]["enabled"] is True,
                f"status reflects enabled: {res}")
        _assert(res["auto_uoink"]["monitored_sources"] == 0,
                f"no sources yet: {res}")
        _assert(res["auto_uoink"]["needs_sources"] is True,
                f"needs_sources flagged: {res}")
        print("ok  status reflects enabled + zero sources")

        # 5. Scan with no monitored sources -> honest explanation, no crawl.
        status, res = _req("POST", "/auto-uoink/scan", body={})
        _assert(status == 200, f"scan ok shape, got {status}: {res}")
        _assert(res.get("needs_sources") is True,
                f"scan explains it needs sources: {res}")
        _assert(res.get("captured") == [],
                f"nothing captured without sources: {res}")
        _assert("Add a monitored playlist" in (res.get("message") or ""),
                f"honest message: {res.get('message')}")
        print("ok  scan with no sources explains itself, captures nothing")

        print("\nall green")
    finally:
        httpd.shutdown()
        idx.close()
        tmp.cleanup()


if __name__ == "__main__":
    test_auto_uoink_scan()

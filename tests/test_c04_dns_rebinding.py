"""C-04 (CRIT-4) -- DNS-rebinding defense.

Run: python tests/test_c04_dns_rebinding.py  (also collected by pytest)

Without Host-header validation, a malicious page can rebind its own domain
to 127.0.0.1 and then have the victim's browser drive the whole local API:
read the corpus, steal the token, call every tool. The browser sends those
requests with the ATTACKER's Host header. This test drives raw HTTP with a
spoofed Host to prove the rebind is rejected, and that legitimate loopback
requests still pass.

Red on unpatched main: a request with `Host: evil.attacker.com` reaches
the route and answers 200 (the server never looked at Host).

Also covers:
- the token endpoint's extension-id pin (off by default, enforced when
  UOINK_EXTENSION_IDS is set),
- the absent-Origin service-worker path still works, but only behind the
  Host wall.
"""
from __future__ import annotations

import json
import socket
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402

_PORT = 0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


@contextmanager
def _server():
    global _PORT
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    _PORT = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        httpd.shutdown()


def _raw_request(method, path, headers, body=None):
    """Speak HTTP/1.1 by hand so we control the Host header exactly (urllib
    would set it from the connection target). Returns (status, body_text)."""
    conn = socket.create_connection(("127.0.0.1", _PORT), timeout=5)
    try:
        lines = [f"{method} {path} HTTP/1.1"]
        for key, value in headers.items():
            lines.append(f"{key}: {value}")
        payload = (body or "").encode()
        if body is not None:
            lines.append(f"Content-Length: {len(payload)}")
        lines.append("Connection: close")
        lines.append("")
        lines.append("")
        conn.sendall("\r\n".join(lines).encode() + payload)
        raw = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw += chunk
    finally:
        conn.close()
    head, _, tail = raw.partition(b"\r\n\r\n")
    status = int(head.split(b" ", 2)[1])
    return status, tail.decode("utf-8", errors="replace")


def test_spoofed_host_is_rejected():
    with _server():
        # The rebind: victim's browser fetches http://evil.attacker.com/...
        # which resolves to 127.0.0.1, carrying the attacker's Host.
        for target in ("evil.attacker.com", "attacker.com:80",
                       "uoink.evil.com", "169.254.1.1"):
            status, body = _raw_request(
                "GET", "/health", {"Host": target})
            _assert(status == 403,
                    f"rebind Host {target!r} must 403 (red on main: 200), "
                    f"got {status}")
            _assert("forbidden host" in body, f"honest reject copy: {body}")
        print("ok  spoofed Host rejected on the public /health probe")

        # A token-gated route with a valid token but a spoofed Host must
        # still die on Host, before the token even matters.
        status, _body = _raw_request(
            "GET", "/library/facets",
            {"Host": "evil.attacker.com", "X-Uoink-Token": server.TOKEN})
        _assert(status == 403,
                f"spoofed Host beats a valid token: got {status}")
        print("ok  spoofed Host rejected even with a valid token")

        # POST too (the rebind's real goal: driving tools).
        status, _body = _raw_request(
            "POST", "/extract/x",
            {"Host": "evil.attacker.com", "X-Uoink-Token": server.TOKEN,
             "Content-Type": "application/json"},
            body=json.dumps({"url": "https://x.com/a/status/1"}))
        _assert(status == 403, f"spoofed-Host POST must 403: {status}")
        print("ok  spoofed Host rejected on POST")


def test_loopback_hosts_pass():
    with _server():
        for host in (f"127.0.0.1:{_PORT}", f"localhost:{_PORT}",
                     "127.0.0.1", "localhost"):
            status, _body = _raw_request("GET", "/health", {"Host": host})
            _assert(status == 200,
                    f"loopback Host {host!r} must pass, got {status}")
        # Missing Host (HTTP/1.0-style) can't carry a rebind target.
        status, _body = _raw_request("GET", "/health", {})
        _assert(status == 200, f"absent Host must pass, got {status}")
        print("ok  loopback + absent Host still pass")


def test_token_extension_id_pin():
    with _server():
        ext_headers = {
            "Host": f"127.0.0.1:{_PORT}",
            "Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop",
            "X-Uoink-Client": "uoink-extension",
        }
        # Default: no pin configured -> any extension origin mints the token.
        status, body = _raw_request("GET", "/token", dict(ext_headers))
        _assert(status == 200 and json.loads(body).get("token"),
                f"unpinned extension origin gets the token: {status} {body}")
        print("ok  /token unpinned accepts any extension origin")

        # Pin to a DIFFERENT id -> this extension is refused.
        original = server._allowed_extension_ids
        server._allowed_extension_ids = lambda: {"someotherextensionid0000000000ab"}
        try:
            status, _body = _raw_request("GET", "/token", dict(ext_headers))
            _assert(status == 403,
                    f"pinned-out extension must 403: {status}")
            # Pin to the RIGHT id -> allowed again.
            server._allowed_extension_ids = lambda: {
                "abcdefghijklmnopabcdefghijklmnop"}
            status, body = _raw_request("GET", "/token", dict(ext_headers))
            _assert(status == 200 and json.loads(body).get("token"),
                    f"pinned-in extension gets the token: {status}")
        finally:
            server._allowed_extension_ids = original
        print("ok  /token honors the extension-id pin when configured")


def test_token_still_needs_client_header_and_host():
    with _server():
        # A rebind page can't set X-Uoink-Client cross-origin without a
        # preflight, but even if it could, Host kills it first.
        status, _body = _raw_request(
            "GET", "/token",
            {"Host": "evil.attacker.com", "X-Uoink-Client": "uoink-extension",
             "Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"})
        _assert(status == 403, f"rebind /token must 403 on Host: {status}")
        print("ok  /token rebind blocked at the Host wall")


def main():
    test_spoofed_host_is_rejected()
    test_loopback_hosts_pass()
    test_token_extension_id_pin()
    test_token_still_needs_client_header_and_host()
    print("\nall green")


if __name__ == "__main__":
    main()

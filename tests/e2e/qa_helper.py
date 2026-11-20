"""Run an isolated Uoink helper for the QA smoke suite. Dev only.

usage: python tests/e2e/qa_helper.py [--fixture HOST=PORT] [--break NAME ...]

The helper is the real server.py, imported and started with --quiet inside
the isolated profile named by UOINK_ISOLATED_PROFILE / UOINK_ISOLATED_PORT
(port 5179 is refused). Test seams, all in this process only:

- Rate limits on /token and /memory/search are raised. A scripted browser
  reloads the dashboard far more often than a person does.
- Desktop balloons are off (they spawn PowerShell on Windows).
- The helper's public fetch boundary only reaches the fixture host given with
  --fixture (mapped to a local test server). Every other fetch fails, so a
  smoke run never touches the network.
- --break search-500 makes library search return HTTP 500.
  --break search-hidden serves a dashboard copy whose search box is hidden.
  Both exist to prove the suite goes red.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PRODUCTION_PORT = 5179
FAULTS = ("search-500", "search-hidden")
HIDE_SEARCH_CSS = "<style id=\"qa-fault\">#searchInput{display:none!important}</style>"


def _guard():
    import uoink_install_isolation as iso

    if not (os.environ.get(iso.ENV_PROFILE) and os.environ.get(iso.ENV_PORT)):
        raise SystemExit("qa_helper: refusing to run without UOINK_ISOLATED_PROFILE and UOINK_ISOLATED_PORT")
    binding = iso.apply_from_process(argv=[], environ=os.environ)
    if binding is None or binding.port == PRODUCTION_PORT:
        raise SystemExit("qa_helper: refusing to run outside an isolated profile")
    return binding


def fixture_opener(fixtures: dict[str, int]):
    """A public_http_open stand-in that only reaches the mapped fixture hosts."""

    def open_url(url, *, headers=None, timeout=10.0, method="GET", follow_redirects=True):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if host not in fixtures:
            raise urllib.error.URLError(f"network is off in the QA smoke run ({host or url})")
        local = urlunsplit(("http", f"127.0.0.1:{fixtures[host]}", parts.path or "/", parts.query, ""))
        request = urllib.request.Request(local, headers=headers or {}, method=method)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=timeout)

    return open_url


def apply_seams(server, *, fixtures: dict[str, int], faults: list[str], scratch: Path) -> None:
    import source_subscriptions

    server._TOKEN_RATE_LIMIT = 100_000
    server._MEMORY_SEARCH_RATE_LIMIT = 100_000
    server._platform.show_toast = lambda *args, **kwargs: None
    source_subscriptions.public_http_open = fixture_opener(fixtures)

    def refuse(url, *args, **kwargs):
        host = (urlsplit(url).hostname or "").lower()
        if host in fixtures:
            return url
        raise source_subscriptions.ServiceError("network_off", "network is off in the QA smoke run")

    if hasattr(source_subscriptions, "check_public_http_url"):
        source_subscriptions.check_public_http_url = refuse

    if "search-500" in faults:
        def broken_search(self, *args, **kwargs):
            return self._send_json(500, {"ok": False, "error": "QA fault: search is broken on purpose"})
        server.Handler._handle_memory_search = broken_search
        if hasattr(server.Handler, "_handle_corpus_v1_search"):
            server.Handler._handle_corpus_v1_search = broken_search
    if "search-hidden" in faults:
        html = Path(server.DASHBOARD_PATH).read_text(encoding="utf-8")
        patched = scratch / "dashboard-search-hidden.html"
        patched.write_text(html.replace("</head>", HIDE_SEARCH_CSS + "</head>", 1), encoding="utf-8")
        server.DASHBOARD_PATH = patched


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Isolated Uoink helper for the QA smoke suite")
    ap.add_argument("--fixture", action="append", default=[], metavar="HOST=PORT",
                    help="map a fixture host to a local test server port")
    ap.add_argument("--break", dest="faults", action="append", default=[], choices=FAULTS,
                    help="break one thing on purpose (the suite must go red)")
    args = ap.parse_args(argv)
    binding = _guard()
    fixtures = {}
    for item in args.fixture:
        host, _, port = item.partition("=")
        fixtures[host.strip().lower()] = int(port)

    import server  # noqa: E402  (after the isolation guard)

    if Path(server.DATA_ROOT).resolve() != Path(binding.profile).resolve() or server.PORT == PRODUCTION_PORT:
        raise SystemExit("qa_helper: server did not bind to the isolated profile")
    scratch = Path(tempfile.mkdtemp(prefix="qa-helper-", dir=str(binding.profile)))
    apply_seams(server, fixtures=fixtures, faults=args.faults, scratch=scratch)
    print(f"QA helper: profile={binding.profile} port={binding.port} faults={','.join(args.faults) or 'none'}",
          flush=True)
    return server.run_cli(["--quiet"])


if __name__ == "__main__":
    raise SystemExit(main())

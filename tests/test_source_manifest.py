"""Tests for the v3.2.1 product manifests (/sources, /creators, /developers).

Validates structure + status vocabulary + Voice DNA cleanliness of every
user-visible string, and verifies the routes answer WITHOUT a token (public
product metadata) via a throwaway server.

Run: python tests/test_source_manifest.py
"""
from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import source_manifest as sm  # noqa: E402

EM_DASHES = ("—", "–")
BANNED = ("leverage", "utilize", "delve", "robust", "game-changer",
          "supercharge", "straightforward", "dive into")


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def test_voice_dna_clean():
    for builder in (
        sm.build_sources(),
        sm.build_creators(),
        sm.build_developers(tool_count=63, mcp_endpoint="http://x/mcp/v1",
                            openapi_spec_path="/openapi/v1/spec.json"),
    ):
        for s in _walk_strings(builder):
            low = s.lower()
            for ed in EM_DASHES:
                _assert(ed not in s, f"em dash in manifest string: {s!r}")
            for b in BANNED:
                _assert(b not in low, f"banned phrase {b!r} in: {s!r}")
    print("ok  manifests: no em dashes, no banned phrases")


def test_sources_shape():
    data = sm.build_sources()
    _assert(data["total"] == len(data["sources"]) >= 12, "expected 12+ sources")
    valid = {sm.SHIPPED, sm.IN_FLIGHT, sm.PLANNED}
    slugs = set()
    for s in data["sources"]:
        for key in ("slug", "name", "status", "capture", "lands", "best_for", "category"):
            _assert(key in s and s[key], f"source missing {key}: {s}")
        _assert(s["status"] in valid, f"bad status {s['status']}")
        _assert(s["slug"] not in slugs, f"duplicate slug {s['slug']}")
        slugs.add(s["slug"])
    # counts add up
    _assert(sum(data["counts"].values()) == data["total"], "counts don't sum")
    # the shipped sources we already have
    shipped = {s["slug"] for s in data["sources"] if s["status"] == sm.SHIPPED}
    _assert({"youtube", "twitter", "podcasts"} <= shipped, "core shipped sources missing")
    # reddit is in-flight (being built this sprint)
    reddit = next(s for s in data["sources"] if s["slug"] == "reddit")
    _assert(reddit["status"] == sm.IN_FLIGHT, "reddit should be in-flight")
    print(f"ok  sources: {data['total']} sources, counts {data['counts']}")


def test_creators_developers_shape():
    c = sm.build_creators()
    _assert([s["step"] for s in c["steps"]] == [1, 2, 3, 4, 5], "5-step story wrong")
    pillar_keys = {p["key"] for p in c["pillars"]}
    _assert(pillar_keys == {"local", "voice", "credit"}, "missing a pillar")

    d = sm.build_developers(tool_count=63, mcp_endpoint="http://127.0.0.1:5179/mcp/v1",
                            openapi_spec_path="/openapi/v1/spec.json")
    _assert(d["tool_count"] == 63, "tool count not threaded")
    access_keys = {a["key"] for a in d["access"]}
    _assert(access_keys == {"mcp", "openapi"}, "missing an access path")
    print("ok  creators: 5 steps + 3 pillars; developers: mcp + openapi")


def test_public_routes_no_token():
    import server  # noqa: E402
    httpd = ThreadingHTTPServer(("127.0.0.1", 5192), server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        for path in ("/sources/manifest", "/creators/manifest", "/developers/manifest"):
            # No token header at all -- these must be public.
            with urllib.request.urlopen(f"http://127.0.0.1:5192{path}", timeout=5) as r:
                payload = json.loads(r.read().decode())
            _assert(r.status == 200 and payload.get("ok"), f"{path} not public/ok")
        print("ok  /sources, /creators, /developers manifests are public + 200")
    finally:
        httpd.shutdown()


def main():
    test_voice_dna_clean()
    test_sources_shape()
    test_creators_developers_shape()
    test_public_routes_no_token()
    print("\nALL SOURCE-MANIFEST TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

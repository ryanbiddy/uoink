"""V-2c -- X (Twitter) ARTICLE capture: x_article_extractor.py + the
content-script DOM path + POST /extract/x-article + pasted-URL fallback.

Run: python tests/test_v2c_x_article.py  (also collected by pytest tests/)

Red on unpatched main: x_article_extractor doesn't exist, POST
/extract/x-article 404s, and the extension has no article content script.

No real (copyrighted) article text appears here — every fixture is
synthetic. Real content only ever lands in the user's local corpus at
capture time.

Coverage:
- Extractor: canonical URL matcher; build_extract_result shapes a valid
  parsed payload for persist_page_yoink; empty/thin/bad-url payloads fail
  honestly. (The pasted-URL login-wall guard is page_extractor's single
  _is_x_login_wall implementation, covered by tests/test_v333_live_fixes.py.)
- Route: POST /extract/x-article is token-gated, persists an x_article yoink
  UNDER THE OUTPUT ROOT (not %LOCALAPPDATA%), and relays honest errors.
- Server classifier: a pasted X article URL classifies as x_article and
  routes the best-effort fallback at /extract/page.
- Extension wiring: the content script, manifest match, popup action, and lib
  helpers exist and are wired.
- JS harnesses: the parser test (mock Article DOM -> markdown) and the
  classifier test run green; node --check passes on every extension JS file.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import x_article_extractor  # noqa: E402
import index as index_mod  # noqa: E402
import server  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
_PORT = 0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---- extractor ------------------------------------------------------------

def _good_payload(**over):
    payload = {
        "url": "https://x.com/synthauthor/article/1900000000001",
        "title": "Synthetic Field Notes",
        "author": "Synthetic Author (@synthauthor)",
        "author_name": "Synthetic Author",
        "author_handle": "synthauthor",
        "markdown": ("**Synthetic Author (@synthauthor)**\n\n"
                     "## A Subheading\n\nA paragraph long enough to clear the "
                     "thin-parse guard with room to spare.\n\n"
                     "- one\n- two\n\n"
                     "![Chart alt](https://pbs.twimg.com/media/synthetic.jpg)"),
        "images": [{"src": "https://pbs.twimg.com/media/synthetic.jpg",
                    "alt": "Chart alt"}],
    }
    payload.update(over)
    return payload


def test_url_matcher():
    yes = [
        "https://x.com/synthauthor/article/1900000000001",
        "https://twitter.com/i/article/1900000000002?s=20",
        "https://mobile.twitter.com/a/article/ABC12345",
    ]
    no = [
        "https://x.com/synthauthor/status/1900000000003",
        "https://x.com/home",
        "https://youtube.com/watch?v=abc",
        "",
    ]
    for url in yes:
        _assert(x_article_extractor.is_x_article_url(url), f"should match: {url}")
    for url in no:
        _assert(not x_article_extractor.is_x_article_url(url), f"must not match: {url}")
    _assert(x_article_extractor.canonical_article_url(
        "https://twitter.com/i/article/1900000000002?s=20")
        == "https://x.com/i/article/1900000000002", "canonicalise /i/article")
    _assert(x_article_extractor.canonical_article_url(
        "https://x.com/synthauthor/article/1900000000001")
        == "https://x.com/synthauthor/article/1900000000001", "canonicalise handle")
    print("ok  URL matcher + canonicaliser")


def test_build_extract_result_shape():
    res = x_article_extractor.build_extract_result(_good_payload())
    _assert(res.get("ok") is True, f"valid payload should build: {res}")
    _assert(res["url"] == "https://x.com/synthauthor/article/1900000000001",
            "canonical url")
    _assert(res["title"] == "Synthetic Field Notes", "title preserved")
    _assert(res["extraction_engine"] == "x-article-dom", "engine tag")
    _assert("## A Subheading" in res["markdown"], "body markdown carried through")
    _assert(res["metadata"]["author_handle"] == "synthauthor", "handle in metadata")
    _assert(res["metadata"]["image_count"] == 1, "image counted")
    _assert(len(res["images"]) == 1, "images carried")
    print("ok  build_extract_result shapes for persist_page_yoink")


def test_build_extract_result_honest_failures():
    # Empty markdown + no title -> honest 'empty', nothing to persist.
    empty = x_article_extractor.build_extract_result(
        _good_payload(title="", markdown="", images=[]))
    _assert(empty.get("ok") is False and empty.get("code") == "empty",
            f"empty payload must fail honestly: {empty}")
    # A title but thin body still persists (title is real signal).
    titled = x_article_extractor.build_extract_result(
        _good_payload(markdown="tiny", images=[]))
    _assert(titled.get("ok") is True, "a real title keeps the capture")
    # Bad URL rejected without persisting.
    bad = x_article_extractor.build_extract_result(
        _good_payload(url="https://x.com/synthauthor/status/9"))
    _assert(bad.get("ok") is False and bad.get("code") == "bad_url",
            f"non-article URL rejected: {bad}")
    print("ok  extractor fails honestly on empty / bad-url payloads")


# ---- server classifier ----------------------------------------------------

def test_server_classifier_recognises_x_article():
    cls = server._classify_capture_url(
        "https://x.com/synthauthor/article/1900000000001")
    _assert(cls.get("ok") and cls.get("source") == "x_article",
            f"pasted article URL should classify as x_article: {cls}")
    _assert(cls.get("endpoint") == "/extract/page",
            "pasted article routes best-effort to /extract/page")
    _assert(cls.get("canonical") == "https://x.com/synthauthor/article/1900000000001",
            "classifier canonicalises the article URL")
    print("ok  server classifier recognises pasted X article URLs")


# ---- route ---------------------------------------------------------------

def _post(path, payload, *, token=True):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    req = urllib.request.Request(
        f"http://127.0.0.1:{_PORT}{path}",
        data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


@contextmanager
def _server(settings=None):
    global _PORT
    original_read = server._read_settings
    server._read_settings = lambda: dict(settings or {})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    _PORT = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        httpd.shutdown()
        server._read_settings = original_read


def test_route_token_gated():
    with _server():
        status, _res = _post("/extract/x-article", _good_payload(), token=False)
        _assert(status == 403, f"no token must 403 (red on main: 404), got {status}")
    print("ok  /extract/x-article is token-gated")


def test_route_relays_honest_errors():
    with _server():
        status, res = _post("/extract/x-article",
                            {"url": "https://x.com/a/article/1900000000009",
                             "markdown": ""})
        _assert(status == 200 and res.get("ok") is False
                and res.get("code") == "empty",
                f"empty article must relay honest failure: {status} {res}")
    print("ok  route relays the extractor's honest empty-parse error")


def test_route_persists_under_output_root():
    # The v3.3.2 output-root discipline: an X ARTICLE capture must write its
    # corpus under the configured output root (server.DESKTOP_ROOT), NOT
    # hardcoded into %LOCALAPPDATA% (server.DATA_ROOT).
    with tempfile.TemporaryDirectory() as out_root, \
            tempfile.TemporaryDirectory() as d:
        out_root = Path(out_root).resolve()
        idx = index_mod.Index.open(Path(d) / "index.db")
        original_get_index = server._get_index
        original_root = server.DESKTOP_ROOT
        server._get_index = lambda: idx
        server.DESKTOP_ROOT = out_root
        try:
            with _server():
                status, res = _post("/extract/x-article", _good_payload())
                _assert(status == 200 and res.get("ok") is True,
                        f"capture failed: {status} {res}")
                _assert(res.get("video_id"), f"persisted id missing: {res}")
                _assert(res.get("image_count") == 1, f"image count: {res}")
                row = idx.get_yoink(res["video_id"])
                _assert(row and row.get("source_type") == "x_article",
                        f"index row source_type: {row}")
                corpus = Path((row or {}).get("corpus_path") or "").resolve()
                _assert(str(corpus).startswith(str(out_root)),
                        f"corpus must be under the output root {out_root}, "
                        f"got {corpus}")
                _assert(server.DATA_ROOT.resolve() not in corpus.parents,
                        f"corpus must NOT be under %LOCALAPPDATA% "
                        f"({server.DATA_ROOT}), got {corpus}")
                _assert(corpus.exists(), f"corpus file should exist: {corpus}")
                text = corpus.read_text(encoding="utf-8")
                _assert("Synthetic Field Notes" in text, "title in corpus")
                _assert("## A Subheading" in text, "body in corpus")
        finally:
            server._get_index = original_get_index
            server.DESKTOP_ROOT = original_root
            idx.close()
    print("ok  route persists an x_article yoink under the output root")


# ---- extension wiring -----------------------------------------------------

def test_extension_wiring():
    ext = REPO_ROOT / "extension"
    manifest = json.loads((ext / "manifest.json").read_text(encoding="utf-8"))
    matches = [m for cs in manifest.get("content_scripts", [])
               for m in cs.get("matches", [])]
    _assert(any("/article/" in m for m in matches),
            "manifest must match X article pages")
    _assert(any(cs.get("js") == ["lib/x-article.js", "content-x-article.js"]
                for cs in manifest.get("content_scripts", [])),
            "the article content script + parser are registered together")
    _assert((ext / "content-x-article.js").exists(),
            "content-x-article.js exists")
    _assert((ext / "lib" / "x-article.js").exists(),
            "lib/x-article.js parser exists")

    popup = (ext / "popup.js").read_text(encoding="utf-8")
    _assert("captureXArticle" in popup, "popup routes X articles via captureXArticle")
    _assert("uoinkParseXArticle" in popup,
            "popup asks the content script to parse the DOM (primary path)")
    _assert("postExtractPage" in popup, "popup keeps the /extract/page fallback")
    _assert('x_article: "Uoink this article"' in popup,
            "the article tab shows the 'Uoink this article' primary label")

    lib = (ext / "lib" / "extract.js").read_text(encoding="utf-8")
    _assert('"/extract/x-article"' in lib and "postExtractXArticle," in lib,
            "lib exposes postExtractXArticle on STC")
    _assert("normalizeXArticleUrl" in lib and "x_article:" in lib,
            "lib classifies X article URLs")

    bg = (ext / "background.js").read_text(encoding="utf-8")
    _assert("stcExtractXArticle" in bg,
            "background proxies the in-page article capture")
    print("ok  extension content script + popup + lib + background are wired")


# ---- JS harnesses ---------------------------------------------------------

def _run_node(script):
    proc = subprocess.run(["node", str(REPO_ROOT / "tests" / "js" / script)],
                          cwd=str(REPO_ROOT), capture_output=True, text=True)
    return proc


def test_js_parser_harness():
    if shutil.which("node") is None:
        print("skip  node not available; parser harness needs Node")
        return
    proc = _run_node("x_article_parser_test.mjs")
    _assert(proc.returncode == 0,
            f"parser harness failed:\n{proc.stdout}\n{proc.stderr}")
    print("ok  X Article parser harness (mock DOM -> markdown) green")


def test_js_classifier_harness():
    if shutil.which("node") is None:
        print("skip  node not available; classifier harness needs Node")
        return
    proc = _run_node("classifier_test.mjs")
    _assert(proc.returncode == 0,
            f"classifier harness failed:\n{proc.stdout}\n{proc.stderr}")
    print("ok  classifier harness (incl. x_article) green")


def test_node_check_extension_js():
    if shutil.which("node") is None:
        print("skip  node not available; node --check needs Node")
        return
    ext = REPO_ROOT / "extension"
    js_files = sorted(ext.glob("*.js")) + sorted((ext / "lib").glob("*.js"))
    _assert(js_files, "should find extension JS files")
    for f in js_files:
        proc = subprocess.run(["node", "--check", str(f)],
                              capture_output=True, text=True)
        _assert(proc.returncode == 0,
                f"node --check failed on {f.name}:\n{proc.stderr}")
    print(f"ok  node --check clean on {len(js_files)} extension JS files")


def main():
    for fn in (
        test_url_matcher,
        test_build_extract_result_shape,
        test_build_extract_result_honest_failures,
        test_server_classifier_recognises_x_article,
        test_route_token_gated,
        test_route_relays_honest_errors,
        test_route_persists_under_output_root,
        test_extension_wiring,
        test_js_parser_harness,
        test_js_classifier_harness,
        test_node_check_extension_js,
    ):
        fn()
    print("\nall green")


if __name__ == "__main__":
    main()

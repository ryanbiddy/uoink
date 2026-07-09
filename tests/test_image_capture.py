"""Context-layer item 3 -- image / meme capture.

An image is a first-class uoink: the user drops / pastes / picks a picture, it
lands in the same corpus as everything else (source_type='image',
platform='image', author='You'), classified for a topic, and queryable by their
AI over MCP and by them via search + facets, with no special-casing.

Run: python tests/test_image_capture.py  (also collected by pytest tests/)

Red on unpatched main: images.py doesn't exist, POST /images 404s, and the
platform/source-type facet has no 'image' label.

Local-first: nothing here calls a cloud vision or OCR service. The image is
caption-, filename-, and source-searchable, and reachable to a vision-capable
MCP client via the path + /file URL get_uoink_corpus returns. OCR is deferred
(no local OCR ships), so this suite does NOT assert text-inside-the-image
search; it asserts caption search + file reachability instead.

Coverage:
- images.build_image: derives a title from caption then filename, defaults
  author to You, and fails honestly on empty / oversized / non-image bytes
  (nothing saved).
- images.persist_image: writes the image bytes + a thumbnail + a corpus
  UNDER THE OUTPUT ROOT (not %LOCALAPPDATA%) as source_type='image', with a
  classified topic; corpus file is named <slug>.md so the disk-walk fallback
  finds it.
- Route POST /images: token-gated, persists a real image, relays honest
  non-image error.
- The image surfaces in /recent, /memory/search (by caption + source_type),
  and /library/facets; MCP reads it with no special-casing and hands a vision
  client a reachable image path + /file URL; the /file route serves the bytes.
"""
from __future__ import annotations

import io
import json
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import images  # noqa: E402
import index as index_mod  # noqa: E402
import server  # noqa: E402
import uoink_mcp_tools  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
_PORT = 0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _synthetic_png(width=48, height=32, color=(180, 83, 9)) -> bytes:
    """A tiny real PNG via Pillow (already a dependency). Real magic bytes so
    the magic-byte guards on save and on /file both pass."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---- pure image logic -----------------------------------------------------

def test_build_image_derives_title_and_author():
    data = _synthetic_png()
    built = images.build_image(data, caption="A meme about local AI context")
    _assert(built.get("ok"), f"valid image should build: {built}")
    _assert(built["title"] == "A meme about local AI context",
            f"title from caption first line: {built['title']}")
    _assert(built["author"] == "You", f"default author is You: {built}")
    _assert(built["video_id"].startswith("image_"), f"image id shape: {built}")
    _assert(built["mime"] == "image/png" and built["ext"] == "png",
            f"mime sniffed from bytes: {built}")
    _assert(built["slug"].startswith("a-meme-about-local-ai-context-"),
            f"readable slug from title: {built['slug']}")

    # No caption: the filename stem becomes the title.
    from_name = images.build_image(data, filename="doge-classic.png")
    _assert(from_name["title"] == "doge-classic",
            f"title from filename stem: {from_name['title']}")

    # No caption, no filename: plain fallback, still saveable.
    bare = images.build_image(data)
    _assert(bare["title"] == "Saved image", f"fallback title: {bare['title']}")

    # Explicit author (a capture from a page/tweet) wins.
    over = images.build_image(data, caption="x", author="Jane (@jane)")
    _assert(over["author"] == "Jane (@jane)", f"explicit author honoured: {over}")
    print("ok  build_image derives title + defaults author to You")


def test_build_image_rejects_bad_input():
    # Empty bytes.
    empty = images.build_image(b"")
    _assert(empty.get("ok") is False and empty.get("code") == "empty",
            f"empty must fail honestly: {empty}")
    # Not an image (plain text, right length).
    not_image = images.build_image(b"this is not an image file, just text.")
    _assert(not_image.get("ok") is False and not_image.get("code") == "unsupported",
            f"non-image bytes must fail honestly: {not_image}")
    # Oversized.
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (images.MAX_IMAGE_BYTES + 1)
    too_big = images.build_image(big)
    _assert(too_big.get("ok") is False and too_big.get("code") == "too_large",
            f"oversized must fail honestly: {too_big}")
    print("ok  build_image rejects empty / non-image / oversized (nothing saved)")


def test_persist_image_writes_under_output_root():
    with tempfile.TemporaryDirectory() as out_root, \
            tempfile.TemporaryDirectory() as d:
        out_root = Path(out_root).resolve()
        idx = index_mod.Index.open(Path(d) / "index.db")
        try:
            data = _synthetic_png()
            built = images.build_image(
                data, caption="Kubernetes autoscaling meme for the migration")
            vid = images.persist_image(
                idx, built, data, data_root=out_root,
                topic_classifier=lambda ctx: "DevOps")
            _assert(vid == built["video_id"], f"returns the video_id: {vid}")
            row = idx.get_yoink(vid)
            _assert(row and row.get("source_type") == "image",
                    f"row source_type=image: {row}")
            _assert(row.get("platform") == "image", f"row platform=image: {row}")
            _assert(row.get("author") == "You", f"row author=You: {row}")
            _assert(row.get("topic") == "DevOps", f"topic classified: {row}")

            corpus = Path((row or {}).get("corpus_path") or "").resolve()
            _assert(str(corpus).startswith(str(out_root)),
                    f"corpus under output root {out_root}: {corpus}")
            _assert(server.DATA_ROOT.resolve() not in corpus.parents,
                    f"corpus must NOT be under %LOCALAPPDATA% "
                    f"({server.DATA_ROOT}): {corpus}")
            _assert(corpus.exists() and corpus.name == f"{row['slug']}.md",
                    f"corpus named after slug: {corpus}")
            _assert(corpus.parent.parent.name == "Images",
                    f"corpus under Images/: {corpus}")

            # The image bytes + a thumbnail are on disk next to the corpus.
            folder = corpus.parent
            image_file = folder / f"{row['slug']}.png"
            _assert(image_file.exists() and image_file.read_bytes() == data,
                    f"original image bytes persisted: {image_file}")
            _assert((folder / "thumbnail.jpg").exists(),
                    "thumbnail.jpg written for the Library card preview")

            # Sidecar carries the taxonomy + image pointers + dimensions.
            sidecar = json.loads((folder / f"{row['slug']}.json").read_text(
                encoding="utf-8"))
            _assert(sidecar.get("source_type") == "image"
                    and sidecar.get("image_filename") == f"{row['slug']}.png"
                    and sidecar.get("mime") == "image/png"
                    and sidecar.get("width") == 48 and sidecar.get("height") == 32,
                    f"sidecar image fields: {sidecar}")
            # OCR is deferred on purpose; the sidecar says so honestly.
            _assert(sidecar.get("ocr") is None, f"OCR deferred: {sidecar}")
        finally:
            idx.close()
    print("ok  persist_image writes source_type=image + bytes + thumbnail under root")


def test_persist_image_caption_is_searchable():
    with tempfile.TemporaryDirectory() as out_root, \
            tempfile.TemporaryDirectory() as d:
        idx = index_mod.Index.open(Path(d) / "index.db")
        try:
            data = _synthetic_png()
            built = images.build_image(data, caption="Zettelkasten fleeting idea")
            vid = images.persist_image(
                idx, built, data, data_root=Path(out_root),
                topic_classifier=lambda ctx: None)
            hits = {r.get("video_id") for r in idx.search("Zettelkasten", limit=10)}
            _assert(vid in hits, f"caption text must be FTS-searchable: {hits}")
        finally:
            idx.close()
    print("ok  persist_image indexes the caption for search")


# ---- route ---------------------------------------------------------------

def _post_image(data: bytes, *, mime="image/png", query="", token=True):
    headers = {"Content-Type": mime}
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    url = f"http://127.0.0.1:{_PORT}/images"
    if query:
        url += "?" + query
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _get(path, *, token=True, raw=False):
    headers = {}
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    req = urllib.request.Request(
        f"http://127.0.0.1:{_PORT}{path}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if raw:
                return r.status, r.read(), r.headers.get("Content-Type")
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if raw:
            return e.code, e.read(), None
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
        status, _res = _post_image(_synthetic_png(), token=False)
        _assert(status == 403, f"no token must 403 (red on main: 404): {status}")
    print("ok  /images is token-gated")


def test_route_rejects_non_image():
    with _server():
        status, res = _post_image(b"not an image, just text bytes here",
                                  mime="image/png")
        _assert(status == 200 and res.get("ok") is False
                and res.get("code") == "unsupported",
                f"non-image must relay honest failure: {status} {res}")
    print("ok  route relays the honest non-image error")


def test_route_persists_and_surfaces_everywhere():
    with tempfile.TemporaryDirectory() as out_root, \
            tempfile.TemporaryDirectory() as d:
        out_root = Path(out_root).resolve()
        idx = index_mod.Index.open(Path(d) / "index.db")
        original_get_index = server._get_index
        original_root = server.DESKTOP_ROOT
        original_mcp_base = getattr(uoink_mcp_tools, "_backend", None)
        server._get_index = lambda: idx
        server.DESKTOP_ROOT = out_root
        uoink_mcp_tools.bind_backend(server)
        try:
            with _server():
                status, res = _post_image(
                    _synthetic_png(),
                    query="caption=Zettelkasten+meme+about+fleeting+ideas"
                          "&filename=fleeting.png")
                _assert(status == 200 and res.get("ok") is True,
                        f"image capture failed: {status} {res}")
                vid = res.get("video_id")
                slug = res.get("slug")
                _assert(vid and slug, f"persisted id/slug missing: {res}")
                _assert(res.get("source_type") == "image"
                        and res.get("platform") == "image"
                        and res.get("author") == "You",
                        f"response taxonomy: {res}")

                # /recent includes the image.
                st, recent = _get("/recent")
                ids = {r.get("video_id") or r.get("slug")
                       for r in (recent.get("recent") or [])}
                _assert(st == 200 and (vid in ids or slug in ids),
                        f"image must show in /recent: {recent}")

                # /memory/search finds it by caption + filters to it.
                st, ms = _get("/memory/search?q=Zettelkasten")
                vids = {r.get("video_id") for r in (ms.get("results") or [])}
                _assert(st == 200 and vid in vids,
                        f"image must be searchable by caption: {ms}")
                st, msf = _get("/memory/search?source_type=image")
                fvids = {r.get("video_id") for r in (msf.get("results") or [])}
                _assert(vid in fvids,
                        f"image must filter by source_type=image: {msf}")

                # /library/facets exposes it as a filterable platform + type.
                st, facets = _get("/library/facets")
                blob = json.dumps(facets)
                _assert(st == 200 and '"image"' in blob,
                        f"facets must include image: {facets}")

                # MCP reads it with no special-casing, and hands a vision client
                # a reachable image (path + /file URL) so it can see the pixels.
                mcp_search = uoink_mcp_tools.search_uoinks({"query": "Zettelkasten"})
                mslugs = {r.get("slug") for r in (mcp_search.get("results") or [])}
                _assert(slug in mslugs,
                        f"MCP search must find the image: {mcp_search}")
                mcp_corpus = uoink_mcp_tools.get_uoink_corpus({"slug": slug})
                _assert(mcp_corpus.get("ok") is not False,
                        f"MCP must read the image corpus: {mcp_corpus}")
                img = mcp_corpus.get("image") or {}
                _assert(img.get("path") and Path(img["path"]).exists(),
                        f"MCP must return a reachable image path: {mcp_corpus}")
                _assert(img.get("file_url", "").startswith("/file?path="),
                        f"MCP must return a /file URL for the image: {img}")

                # The /file route actually serves the image bytes to a client.
                fstatus, fbytes, ctype = _get(
                    img["file_url"], raw=True)
                _assert(fstatus == 200 and fbytes[:8] == b"\x89PNG\r\n\x1a\n",
                        f"/file must serve the real image bytes: {fstatus}")
                _assert((ctype or "").startswith("image/"),
                        f"/file must serve an image content-type: {ctype}")
        finally:
            server._get_index = original_get_index
            server.DESKTOP_ROOT = original_root
            if original_mcp_base is not None:
                uoink_mcp_tools.bind_backend(original_mcp_base)
            idx.close()
    print("ok  image persists + surfaces in /recent, /memory/search, facets, MCP, /file")


def main() -> int:
    test_build_image_derives_title_and_author()
    test_build_image_rejects_bad_input()
    test_persist_image_writes_under_output_root()
    test_persist_image_caption_is_searchable()
    test_route_token_gated()
    test_route_rejects_non_image()
    test_route_persists_and_surfaces_everywhere()
    print("\nall image-capture tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

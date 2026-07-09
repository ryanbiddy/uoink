"""Image / meme capture -- an image is a first-class uoink.

Third item-model extension toward the context layer (handoff/
CONTEXT-LAYER-VISION-2026-07-08.md, build sequence item 3). An image you save
(a meme, a screenshot, a diagram) lands in the same corpus as everything else:
the same platform / source-type / author / topic taxonomy v3.5.0 shipped,
queryable by your AI over MCP and by you via search, with no special-casing.

This module owns the pure image logic:
- validate the bytes the user dropped / pasted / picked (real PNG, JPEG, or
  WebP, within a sane size cap),
- derive a title from the caption, then the filename, then a plain fallback,
- persist the image bytes + a readable corpus folder + a thumbnail under the
  configured output root (NOT %LOCALAPPDATA%).

Transport (the POST /images route + token gate + raw-body read) is owned by
server.py. Topic classification is injected by the caller
(server._classify_topic) so this module stays standalone and unit-testable.

Local-first, zero telemetry: nothing here calls a cloud vision or OCR service.
We store the image + the user's caption + where it came from. The AI that
QUERIES the corpus (Claude over MCP) already has vision, so the image file is
made reachable to it at query time (get_uoink_corpus returns the absolute path
+ a token-gated /file URL). OCR is deferred on purpose: no pure-Python OCR
ships in the embedded runtime, and bundling a Tesseract binary is out of scope
for this item. An image is caption-, filename-, and source-searchable today,
and fully describable by a vision client on demand.

Voice DNA applies to every user-visible string here.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

# The taxonomy helpers (platform + source-type vocabulary) live in
# page_extractor so every source agrees on one set of tags. An image is
# source_type='image' on platform='image'.
from page_extractor import PLATFORM_IMAGE

log = logging.getLogger("uoink.images")

# Source-type tag persisted on the yoink row. Parallels 'page', 'x_article',
# 'reddit_thread', 'episode', 'video', 'note', 'short_video'.
SOURCE_TYPE = "image"
PLATFORM = PLATFORM_IMAGE
EXTRACTION_ENGINE = "image"

# The default "who" when the image wasn't captured from an authored page. A
# meme you saved to yourself is authored by you until we know better; a capture
# from a page/tweet can pass the real author through.
DEFAULT_AUTHOR = "You"

# Image bytes bigger than this fail honestly rather than bloating the corpus.
# Matches server.MAX_SERVED_FILE_BYTES so anything we save stays servable back
# out through the /file route without hitting its own cap.
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_IMAGE_BYTES = 8  # smaller than any real header -> not an image
MAX_TITLE_CHARS = 200
MAX_CAPTION_CHARS = 20_000

# The only formats we accept, keyed by the extension we write on disk. Kept in
# lockstep with server._SERVED_IMAGE_TYPES so a saved image reads back through
# /file with the right Content-Type.
_MIME_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_LEAD_MARKER_RE = re.compile(r"^\s*(?:#{1,6}\s+|>\s+|[-*+]\s+|\d+\.\s+)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def _slugify(value: str, *, max_len: int = 40) -> str:
    """Lowercase, ASCII-ish, hyphen-joined slug for a readable folder name.
    Empty / all-punctuation input returns ''."""
    text = _SLUG_STRIP_RE.sub("-", str(value or "").lower()).strip("-")
    return text[:max_len].strip("-")


def sniff_mime(data: bytes) -> str | None:
    """Return the image MIME from the file's magic bytes, or None if the bytes
    are not a PNG, JPEG, or WebP. We trust the bytes, never the caller's
    Content-Type, so a mislabeled or hostile upload can't smuggle a non-image
    into the corpus (the /file route applies the same check on the way out)."""
    if not data or len(data) < 12:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def derive_title(caption: str | None, filename: str | None) -> str:
    """Title from the caption's first non-blank line (markdown marker stripped),
    else the filename stem, else a plain fallback. Never empty."""
    for raw_line in (caption or "").splitlines():
        line = _LEAD_MARKER_RE.sub("", raw_line).strip()
        if line:
            if len(line) > MAX_TITLE_CHARS:
                line = line[:MAX_TITLE_CHARS].rstrip() + "..."
            return line
    stem = Path((filename or "").strip()).stem.strip()
    if stem:
        if len(stem) > MAX_TITLE_CHARS:
            stem = stem[:MAX_TITLE_CHARS].rstrip() + "..."
        return stem
    return "Saved image"


def build_image(image_bytes: bytes, *, mime: str | None = None,
                filename: str | None = None, caption: str | None = None,
                source_url: str | None = None,
                author: str | None = None) -> dict:
    """Validate dropped/pasted/picked image bytes and shape them for
    persist_image.

    Returns {ok: True, ...} with a stable id + readable slug, or
    {ok: False, code, error} when the bytes are missing, too big, or not a
    real PNG/JPEG/WebP (nothing gets saved).
    """
    if not image_bytes or len(image_bytes) < MIN_IMAGE_BYTES:
        return {"ok": False, "code": "empty",
                "error": "No image came through. Nothing was saved."}
    if len(image_bytes) > MAX_IMAGE_BYTES:
        mb = MAX_IMAGE_BYTES // (1024 * 1024)
        return {"ok": False, "code": "too_large",
                "error": f"That image is over {mb} MB. Nothing was saved."}

    real_mime = sniff_mime(image_bytes)
    if real_mime is None:
        return {"ok": False, "code": "unsupported",
                "error": "That file isn't a PNG, JPEG, or WebP image. "
                         "Nothing was saved."}
    # The bytes win over any declared type, but if the caller declared a
    # different real image type we honour the bytes silently.
    ext = _MIME_EXT[real_mime]

    clean_caption = (caption or "").strip()
    if len(clean_caption) > MAX_CAPTION_CHARS:
        clean_caption = clean_caption[:MAX_CAPTION_CHARS]

    clean_source = (source_url or "").strip() or None
    clean_filename = (filename or "").strip() or None

    title = derive_title(clean_caption, clean_filename)
    who = (author or "").strip() or DEFAULT_AUTHOR

    image_uuid = uuid.uuid4().hex
    video_id = f"image_{image_uuid[:11]}"
    slug = f"{_slugify(title) or 'image'}-{image_uuid[:8]}"

    return {
        "ok": True,
        "video_id": video_id,
        "slug": slug,
        "title": title,
        "author": who,
        "caption": clean_caption,
        "source_url": clean_source,
        "filename": clean_filename,
        "mime": real_mime,
        "ext": ext,
        "yoinked_at": _now_iso(),
    }


def _write_thumbnail(image_path: Path, thumb_path: Path,
                     *, max_width: int = 800) -> tuple[int | None, int | None]:
    """Best-effort JPEG thumbnail for the Library card preview, plus the source
    image's pixel dimensions. Reuses the same Pillow path the clipboard corpus
    uses (lazy import so dev boxes without Pillow still save the image; the
    bundled installer always ships it). Returns (width, height) or (None, None)
    when Pillow is unavailable or the decode fails -- the image still persists,
    the card just falls back to no preview."""
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        log.info("Pillow not installed; skipping image thumbnail")
        return None, None
    try:
        with Image.open(image_path) as img:
            width, height = img.width, img.height
            preview = img.convert("RGB") if img.mode != "RGB" else img.copy()
        if preview.width > max_width:
            new_h = max(1, int(preview.height * (max_width / preview.width)))
            preview = preview.resize((max_width, new_h), Image.LANCZOS)
        preview.save(thumb_path, format="JPEG", quality=80, optimize=True)
        return width, height
    except Exception as e:  # decode/encode failure must never block the save
        log.warning("image thumbnail failed: %s", e)
        return None, None


def _searchable_text(title: str, caption: str, filename: str | None,
                     source_url: str | None) -> str:
    """The text a query hits: title, caption, the original filename (meme names
    carry meaning), and where it came from. This is what makes an image
    findable today; a vision client fills in what's inside the image at query
    time."""
    parts = [title, caption or "", filename or "", source_url or ""]
    return "\n".join(p for p in parts if p).strip()


def persist_image(idx, built: dict, image_bytes: bytes, *,
                  data_root: Path | None = None, subfolder: str = "Images",
                  topic_classifier=None) -> str | None:
    """Persist a built image as a yoink row + a readable corpus folder.

    Mirrors notes.persist_note / page_extractor.persist_page_yoink. Under
    <data_root>/Images/<slug>/ it writes:
    - <slug>.<ext>   the original image bytes (served back out via /file),
    - thumbnail.jpg  a preview so the Library card renders like any other card,
    - <slug>.md      a human-readable corpus file that embeds the image and
                     records the caption + source (VS Code / Obsidian render it,
                     and the disk-walk fallback + MCP corpus read find it),
    - <slug>.json    the sidecar with the full taxonomy + image pointers.

    Then upserts the row so the image surfaces in /recent, /memory/search,
    /library/facets, and the MCP tools with no special-casing. Returns the
    video_id, or None if the build is invalid or the upsert fails.
    """
    if not isinstance(built, dict) or not built.get("ok"):
        return None
    if not image_bytes:
        return None

    video_id = built["video_id"]
    slug = built["slug"]
    title = built["title"]
    author = built["author"]
    caption = built.get("caption") or ""
    source_url = built.get("source_url")
    filename = built.get("filename")
    mime = built["mime"]
    ext = built["ext"]
    yoinked_at = built.get("yoinked_at") or _now_iso()

    # Classify a topic over the caption / title / filename so images join the
    # topic facet instead of piling into Uncategorized. Injected by the caller;
    # a classify failure never blocks the save.
    topic = None
    if topic_classifier is not None:
        try:
            topic = topic_classifier({
                "title": title or "",
                "description": (caption or "")[:2000],
                "channel": author or "",
            }) or None
        except Exception as e:  # defensive: never block a save on classify
            log.warning("persist_image topic classify failed: %s", e)
            topic = None

    corpus_path = None
    sidecar_path = None
    image_filename = f"{slug}.{ext}"
    width = height = None
    if data_root is not None:
        folder = Path(data_root) / subfolder / slug
        folder.mkdir(parents=True, exist_ok=True)
        image_path = folder / image_filename
        image_path.write_bytes(image_bytes)

        thumb_path = folder / "thumbnail.jpg"
        width, height = _write_thumbnail(image_path, thumb_path)
        has_thumb = thumb_path.exists()

        corpus_path = folder / f"{slug}.md"
        sidecar_path = folder / f"{slug}.json"

        md_lines = [f"# {title}", ""]
        md_lines.append(f"![{caption or title}]({image_filename})")
        md_lines.append("")
        if caption:
            md_lines.append(caption)
            md_lines.append("")
        if source_url:
            md_lines.append(f"Source: {source_url}")
            md_lines.append("")
        corpus_path.write_text("\n".join(md_lines), encoding="utf-8")

        sidecar_path.write_text(json.dumps({
            "schema_version": 2,
            "source_type": SOURCE_TYPE,
            "platform": PLATFORM,
            "author": author,
            "title": title,
            "caption": caption or None,
            "source_url": source_url,
            "image": image_filename,
            "image_filename": image_filename,
            "original_filename": filename,
            "mime": mime,
            "width": width,
            "height": height,
            "thumbnail": "thumbnail.jpg" if has_thumb else None,
            "ocr": None,  # deferred: no local OCR ships yet (see module docstring)
            "extraction_engine": EXTRACTION_ENGINE,
            "yoinked_at": yoinked_at,
            "extracted_at": yoinked_at,
            "video_id": video_id,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    metadata_json = json.dumps({
        "author": author,
        "platform": PLATFORM,
        "source_type": SOURCE_TYPE,
        "image": True,
        "image_filename": image_filename,
        "mime": mime,
        "source_url": source_url,
    }, ensure_ascii=False)

    content = _searchable_text(title, caption, filename, source_url)

    try:
        idx.upsert_yoink({
            "video_id": video_id,
            "slug": slug,
            # `channel` stays populated for every path that still reads it
            # (search, the channel/author picker): the image's author.
            "channel": author,
            "platform": PLATFORM,
            "author": author,
            "title": title[:240] if title else None,
            "topic": topic,
            "yoinked_at": yoinked_at,
            "corpus_path": str(corpus_path) if corpus_path else None,
            "sidecar_path": str(sidecar_path) if sidecar_path else None,
            "metadata_json": metadata_json,
            "source_type": SOURCE_TYPE,
        }, content=content[:65000])
    except Exception as e:
        log.warning("persist_image upsert failed: %s", e)
        return None
    return video_id

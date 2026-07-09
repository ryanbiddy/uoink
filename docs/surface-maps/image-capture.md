# Surface map: image / meme capture

Captures an **image the user saved** (a meme, a screenshot, a diagram) into the
local corpus as a first-class uoink with `source_type='image'` on
`platform='image'`, authored by **You** by default. Third item-model extension
toward the context layer (`handoff/CONTEXT-LAYER-VISION-2026-07-08.md`, build
sequence item 3).

An image is the same universal item as everything else: source + author +
content + topic + timestamp. No new corpus shape, no new query path. It reads
back through `/recent`, `/memory/search`, `/library/facets`, and every MCP tool
with no special-casing.

## Local-first, zero telemetry (design constraint)

Uoink makes no outbound cloud AI calls, so nothing here calls a cloud vision or
OCR service. The model for "queryable images" is:

- **Store** the image bytes + an optional caption + the source (a page/tweet URL
  when captured from one, else none) + timestamp + topic.
- **Query** happens two ways. The human searches the caption, the original
  filename (meme filenames carry meaning), and the source URL, all indexed into
  FTS. The AI queries over MCP and already has vision, so the image file is made
  reachable to it at query time (see MCP below); the vision-capable client reads
  and describes the pixels itself. That is how an image becomes "queryable by
  your AI" without us running vision.

### OCR is deferred (honest judgment call)

Text inside a meme is **not** OCR'd today. There is no pure-Python OCR in the
embedded runtime, and a real OCR path (Tesseract) means bundling a heavy new
binary plus language data, which is out of scope for this item and a cloud OCR is
off the table by the local-first rule. So OCR is deferred on purpose. The image
is still caption-, filename-, and source-searchable now, and fully describable
by a vision client on demand. The sidecar records `"ocr": null` so the honest
state is visible. When a bundleable local OCR lands, it drops into the same
`content` string with no schema change.

## Taxonomy choice

Reuses the v3.5.0 taxonomy (platform / source-type / author / topic):

- **`source_type = "image"`** and **`platform = "image"`**, kept 1:1 the way
  every other source maps (`x_thread` -> `x`, `page` -> `web`, `note` ->
  `note`). An image is not from a source network, but it slots into the Platform
  facet so it filters like any other uoink. (Contrast `short_video`, which is
  multi-platform and derives platform from the URL host; an image has no host, so
  the 1:1 note-style mapping is the right one.)
- **`author`** = the user by default, the plain honest **"You"** (no
  user-identity setting exists yet). `POST /images` accepts an optional `author`
  override so an image captured from an authored page/tweet can carry the real
  "who".
- **`topic`** = classified over the caption / title / filename via the existing
  keyword classifier (`server._classify_topic`). Unclassified reads as
  **Uncategorized**, never a hard failure.

Both new tags are registered in `page_extractor` (`PLATFORM_IMAGE`,
`_SOURCE_TYPE_PLATFORM["image"]`, `author_for` image branch) and labeled in
`server._FACET_LABELS` (platform + source_type -> "Image").

## Module: `images.py`

Owns the pure image logic (transport lives in `server.py`); standalone and
unit-testable, mirroring `notes.py`.

- **`build_image(image_bytes, *, mime=None, filename=None, caption=None,
  source_url=None, author=None)`** -> `{ok, video_id, slug, title, author,
  caption, source_url, filename, mime, ext, yoinked_at}` or `{ok: False, code,
  error}`. The bytes are trusted only after a **magic-byte sniff** (PNG / JPEG /
  WebP); a mislabeled or non-image upload fails honestly. Derives the title from
  the caption's first line, then the filename stem, then "Saved image"; defaults
  author to "You"; mints an `image_<uuid>` id + a readable slug. Empty /
  oversized (> 10 MB) / non-image all fail, nothing is saved.
- **`persist_image(idx, built, image_bytes, *, data_root, topic_classifier=None)`**
  -> the `video_id`. Writes the image bytes, a JPEG thumbnail, a readable corpus
  `.md`, and a `.json` sidecar, classifies a topic, and upserts the row with the
  same field set every capture uses (`idx.upsert_yoink` + FTS content).

## Route: `POST /images` (token-gated)

The body is the **raw image bytes** (`Content-Type: image/png|jpeg|webp`), not
JSON, because a base64 image blows past the 64KB JSON body cap. Metadata rides
the query string: `?caption=&source_url=&author=&filename=`. `do_POST` routes to
`_handle_create_image` **before** the JSON body reader, and reads the raw body
itself (capped at 10 MB, `images.MAX_IMAGE_BYTES`). Token gate is `do_POST`'s
unconditional `_require_token`.

| Case | Status | Body |
|---|---|---|
| Saved | 200 | `{ok:true, video_id, slug, title, author, source_type, platform}` |
| Empty / not an image / oversized | 200 (413 on size) | `{ok:false, code, error}` (honest, nothing saved) |
| Persist failed | 500 | `{ok:false, error}` |
| No/bad token | 403 | |

## Storage root (v3.3.2 discipline)

The image lands under the configured output root (`DESKTOP_ROOT` /
`UOINK_OUTPUT_DIR`) at
`<output_root>/Images/<title-slug>-<id>/`, holding:

- `<slug>.<ext>` the original image bytes (served back out via `/file`),
- `thumbnail.jpg` a preview so the Library card renders like any other card,
- `<slug>.md` a human-readable corpus file that embeds the image and records the
  caption + source (VS Code / Obsidian render it; the disk-walk fallback + MCP
  corpus read find it),
- `<slug>.json` the sidecar with the full taxonomy + image pointers + pixel
  dimensions.

It does **not** write to `%LOCALAPPDATA%` (`DATA_ROOT`). The corpus file is named
after the folder slug, so the disk-walk fallback resolves it too, not just the
index. Pinned by `test_persist_image_writes_under_output_root`.

## Dashboard UI

A **"Save an image"** surface (`#imageCapture`) sits with the capture surfaces on
the Sources tab, under the "Jot a note" box: a drop zone that accepts a
**drag-and-drop**, a **paste** (Ctrl/Cmd+V after a screenshot), or a **click to
pick a file**, an optional caption field, and a **Save image** button (enabled
once an image is selected, with a live preview). On save it `POST`s the raw bytes
to `/images`, clears, toasts "Saved your image. It's in your Library.", then
reloads the Library + facets so the image is immediately visible and filterable.
The Library card renders source-type **"image"**, platform chip **"Image"**, and
author **"You"**, with the real thumbnail as the card preview (the existing
`thumbnail.jpg` -> `/file` pipeline, reused).

## MCP: serving the image to a vision-capable client

No new tools. The image is an ordinary indexed row + corpus file, so
`search_uoinks` (FTS over caption / filename / source) finds it and
`get_uoink_corpus` reads it by slug with no special-casing.

For an image, `get_uoink_corpus` additionally returns an **`image`** block so a
vision client can read the pixels the same honest way the rest of the codebase
serves files:

```
image: { path, file_url, mime, caption, source_url, width, height }
```

`path` is the absolute image path (a client with local filesystem access, e.g.
Claude Desktop or Claude Code, opens it directly); `file_url` is the token-gated
`/file?path=` route the dashboard already renders previews through. MCP tool
results are wrapped as text/JSON (no image content block in the transport today),
so the reachable pointer is the honest mechanism, matching how `folder` and
citation `file_path`s are already handed out. Verified by
`test_route_persists_and_surfaces_everywhere` (asserts the returned path exists
and the `/file` route serves the real image bytes).

## Tests / proof

`tests/test_image_capture.py` (red on main: `images` module absent, `POST
/images` 404s, no `image` facet label):

- `build_image`: title from caption then filename then fallback, default author
  You, mime sniffed from bytes; empty / non-image / oversized all fail honestly.
- `persist_image`: image bytes + `thumbnail.jpg` + corpus **under the output
  root** (not `%LOCALAPPDATA%`) as `source_type='image'`, `author='You'`, topic
  classified-or-empty, file named `<slug>.md` under `Images/`; sidecar records
  dimensions and `ocr: null`.
- Caption is FTS-searchable.
- Route: token gate, honest non-image relay.
- The image surfaces in `/recent`, `/memory/search` (by caption +
  `source_type=image` filter), `/library/facets`, the MCP tools (`search_uoinks`
  + `get_uoink_corpus`), and the returned image path is reachable via `/file`.

Playwright drove the real dashboard against an isolated temp corpus on a spare
port: picked and dropped an image, saw both persist (`POST /images` 200), then
filtered the Library to source-type = Image and saw the cards render their real
thumbnail previews (author "You", type "Image"). No console errors.

## Follow-up (out of scope here)

An extension **right-click "Save this image"** (page image -> Uoink via
`contexts:["image"]` + `info.srcUrl`) was deferred to avoid scope creep: the
extension has no image-context scaffolding today (new context menu, click branch,
host-permission fetch, and its own JS tests), and the same discipline that
deferred the notes popup affordance applies. Images are fully capturable now from
the dashboard (drop / paste / pick) and `POST /images` directly. Spotify / intent
status, "ask your corpus", and mobile share-to-Uoink are separate later sequence
items.

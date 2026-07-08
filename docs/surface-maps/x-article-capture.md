# Surface map: X (Twitter) Article capture (V-2c)

Captures an **X long-form Article** (`x.com/<handle>/article/<id>` or
`x.com/i/article/<id>`) into the local corpus as a yoink with
`source_type='x_article'`.

X Articles are **not** served by the public syndication endpoint the
post/thread path (`/extract/x`, `x_extractor.py`) leans on — that endpoint
only returns tweets. So the reliable capture reads the **rendered Article DOM
out of the user's already-authenticated page**, exactly the model the shipped
Reddit content script uses. That side-steps X's login wall.

Two paths, primary + fallback:

## PRIMARY — content-script DOM capture

- **`extension/lib/x-article.js`** — the parser (`XArticle.parseXArticle`),
  a classic-script IIFE (loads without touching the DOM, so it's unit-testable
  under Node via eval). Turns the live Article DOM into structured markdown:
  title, author (`Name (@handle)`), body (headings / paragraphs / lists /
  quotes / inline links + bold / italic / code), and image references
  (`![alt](src)` plus an `images[]` array).
- **`extension/content-x-article.js`** — detects an Article page, injects a
  floating **"Uoink this article"** button in the shipped button visual
  language (rust pill, status dot, U icon, spinner/success/error states), and
  on click parses the DOM and proxies the parsed payload to the helper through
  the background SW (`stcExtractXArticle` → `STC.postExtractXArticle`). It also
  answers a `{type:"uoinkParseXArticle"}` message from the popup so the popup
  can drive the same parse.
- **`manifest.json`** — a `content_scripts` entry matching
  `https://x.com/*/article/*`, `https://x.com/i/article/*`, and the
  `twitter.com` equivalents, loading `lib/x-article.js` + `content-x-article.js`.
  (`x.com` is already in `host_permissions`.)
- **Popup** (`popup.js`) — the source-aware primary button reads
  **"Uoink this article"** on an Article tab (`x_article` classification in
  `STC.classifyCaptureUrl`) and routes through `captureXArticle`: it messages
  the content script for the parsed DOM, then POSTs it to `/extract/x-article`.
- **Route `POST /extract/x-article`** (token-gated) — takes the pre-parsed
  `{url, title, author, markdown, images}`, validates it via
  `x_article_extractor.build_extract_result`, and persists through
  `page_extractor.persist_page_yoink(source_type="x_article", subfolder="X",
  slug_prefix="x-article", data_root=DESKTOP_ROOT)`. **The server never
  fetches X** — the parse already happened in the authenticated page.

**Storage root** (v3.3.2 discipline): the corpus lands under the configured
output root (`DESKTOP_ROOT` / `UOINK_OUTPUT_DIR`) at
`<output_root>/X/<url-digest>/x-article.md` — the same root video captures,
the corpus scan, and the stale-path heal use. It does **not** write to
`%LOCALAPPDATA%` (`DATA_ROOT`). Pinned by
`test_route_persists_under_output_root`.

| Case | Status | Body |
|---|---|---|
| Saved | 200 | `{ok:true, video_id, title, image_count, metadata}` |
| Empty / thin / bad-url parse | 200 | `{ok:false, code, error}` (extractor's honest copy) |
| Persist failed | 500 | `{ok:false, error}` |
| No/bad token | 403 | |

## FALLBACK — best-effort `/extract/page`

If the content script isn't present (SPA navigation, not injected) or the
parse returns thin, the capture degrades to the universal web-page path:

- **Popup**: `captureXArticle` falls back to `STC.postExtractPage(url)`.
- **Pasted URL / dashboard universal box**: `server._classify_capture_url`
  now recognises an X Article URL as source `x_article` and routes it to
  `/extract/page` (a **real** attempt, not a vague "couldn't pull it"), with a
  note that the in-page button is the reliable path.
- **Honest login-wall handling**: this is owned by a single, engine-agnostic
  implementation shared with the v3.3.3 fixes -- `page_extractor.extract_page`
  calls `_is_x_login_wall(url, result)` (host is x/twitter **and** the markdown
  leads with "JavaScript is not available" **and** there is no real `<title>`).
  When the logged-out fetch comes back as X's wall, `extract_page` returns
  `{ok:false, code:"x_login_wall", error}` before `persist_page_yoink` runs, so
  it persists **nothing** instead of saving a stub. The error copy points at
  the in-page **Uoink this article** button. See `x-text-capture.md`.

## Resilient selectors + maintenance risk

X ships obfuscated, churning class names, so the parser **never** keys off
them. It matches on stable, semantic signals in priority order:

1. `data-testid` (the most durable hooks X exposes) —
   `twitterArticleRichTextTitle` / `…RichTextComponent`, `User-Name`.
2. ARIA `role` / `aria-level` (`[role="heading"][aria-level="1"]`).
3. Plain HTML tag structure (`article h1`, then a structural block walk).

The candidate selector lists live in one place (`TITLE_SELECTORS`,
`BODY_SELECTORS`, `AUTHOR_SELECTORS` in `lib/x-article.js`) — the single spot
to update when X changes markup. **Maintenance risk is real and acknowledged:**
if X renames a testid the parser degrades to the structural walk; if it can't
find any recognised **article body container** it **fails honestly**
(`{ok:false, code:"empty"}`) rather than serialising page chrome as if it were
the article. Failing honest was the deliberate choice over guessing.

## Tests / proof (mock-based)

`tests/test_v2c_x_article.py` (Python) + `tests/js/x_article_parser_test.mjs`
(Node) + `tests/js/mini_dom.mjs` (a dependency-free HTML→DOM for the parser
test):

- Parser: a **synthetic** mock Article DOM → correct structured markdown
  (title, `Name (@handle)` byline, heading, inline link/bold, list,
  blockquote, image + figcaption) and the `images[]` array; a blocked /
  login-walled page (no article container) and a thin body **fail honestly**.
- Extractor: URL matcher/canonicaliser, `build_extract_result` shape, honest
  failures on empty/bad-url payloads.
- Route: token gate, honest error relay, and corpus persisted **under the
  output root** as `x_article`.
- Classifier: pasted X Article URL classifies as `x_article` (both the
  extension `STC.classifyCaptureUrl` harness and server `_classify_capture_url`).
- `node --check` clean on every extension JS file.

**No real (copyrighted) article text appears anywhere in code or tests** — all
fixtures are synthetic. Real content only lands in the user's local corpus at
capture time.

## Categorization Phase 1 — authoritative routing + honest feedback (A1/A2)

Phase 1 closed the gap where an Article was reachable but the entry point
mislabelled or misrouted it, and where a walled capture read as a silent no-op.

**A1 — one authoritative Article definition; every entry point uses it.**

- **One Python definition.** `x_extractor.is_x_article_url` now delegates to the
  strict `x_article_extractor.is_x_article_url` (the single canonical shape:
  `/i/article/<id>` or `/<handle>/article/<id>`, id ≥ 5 chars). The server
  capture classifier (`_classify_capture_url`) and the persist path can no
  longer disagree — the old loose copy (matched a no-id `/article` path) is
  gone.
- **One JS definition.** `XArticle.normalizeXArticleUrl` in `lib/x-article.js`
  is the sole owner; `STC.normalizeXArticleUrl`/`isXArticleUrl`
  (`lib/extract.js`) delegate to it. `x-article.js` loads before `extract.js`
  everywhere STC classifies an Article tab (`popup.html`, `background.js`
  `importScripts`).
- **Context menu (`background.js`).** The former static **"Uoink this page
  (article)"** that skipped detection and hit `/extract/page` is gone. The menu
  item's title now flips to **"Uoink this article"** per tab
  (`updateArticleMenuTitle` on `tabs.onActivated`/`onUpdated`), and on click an
  X Article routes to `captureXArticleFromTab` — the in-page DOM parse
  (`uoinkParseXArticle` → `/extract/x-article`), with the best-effort
  `/extract/page` only as a fallback. Generic pages still take `/extract/page`.
- **Popup (`popup.js`).** `detectCurrentSource` now probes the live tab DOM
  (`probeXArticleDom`, via `activeTab`+`scripting`, selectors mirroring
  `XArticle.BODY_SELECTORS`) and resolves through `STC.resolveTabSource(url,
  {hasArticleDom})`. A live-DOM article signal **wins over URL-shape guessing**,
  so an article reached via its announcing `/status/` tweet, a `t.co` redirect,
  or an unsettled SPA route is still labelled **"Uoink this article"** instead
  of silently degrading to "Uoink this page".

**A2 — a walled/failed capture is honest and visible.**

- **Popup** surfaces the X login wall (and any failure to serve a pasted link)
  as a **persistent alert** (`#current-source-alert`, `showSourceAlert`) — not
  the 1.8s toast — with actionable copy ("click the Uoink this article button
  on the page") and an explicit "Nothing was saved."
- **Context menu** uses a persistent notification (`notifyWalledXArticle`,
  `requireInteraction:true`) with the same honest copy, replacing the generic
  auto-dismissing "Uoink failed".
- **Stale-token 403.** `/extract/page` and `/extract/x-article` ride
  `_authedFetch`'s 403 retry, which refreshes the token (and now falls back to
  the stored token if `/token` momentarily returns nothing) so a stale token
  can't cause a second dead end.

Pinned by `tests/test_cat_p1_routing_feedback.py` (detector agreement + variants,
server classifier, walled-fails-nothing-persisted, context-menu/popup routing +
persistent feedback, 403 refresh, Voice-DNA dash check) and
`tests/js/x_article_routing_test.mjs` (`resolveTabSource` + STC→XArticle
delegation across `/article/`, `/i/article/`, via-status, and t.co-normalized
variants).

## Live-vs-mock note

X Articles are login-walled to logged-out fetches, and no headed
authenticated browser was drivable in this build environment, so **the primary
DOM parse was verified against the synthetic fixture, not a live X Article**.
The selector lists are best-effort against X's current markup and are the
expected maintenance point. The fallback `/extract/page` login-wall behaviour
is exercised by `page_extractor._is_x_login_wall` coverage in
`tests/test_v333_live_fixes.py`.

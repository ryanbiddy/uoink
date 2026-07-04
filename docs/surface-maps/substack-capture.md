# Surface map: Substack post capture (Q-01, AMBER)

Captures a free Substack article or newsletter post as a yoink. First
source of the v3.3 expansion (D-6 locked priority: Substack, then LinkedIn
video, then Reddit). **AMBER**: built behind a flag, shipped as a draft PR
for Ryan to flip live; nothing here activates on its own.

## The flag

`substack_capture_enabled` (boolean settings key, absent/false by default).
`POST /extract/substack` answers `{ok: false, code: "disabled", error:
"...substack_capture_enabled..."}` before touching the network while off.
No UI references the feature yet; SITE/AG own the /sources card and copy
when Ryan flips it (per D-6's split).

## Backend: `substack_extractor.py`

House pattern of `reddit_extractor.py`: fetch split from parse/render,
`_fetch` injection for tests, `extract_result` shaped for
`page_extractor.persist_page_yoink`.

- **Scope**: `https://<publication>.substack.com/p/<slug>` only. Custom-
  domain publications are out for this pass (nothing in the URL says
  they're Substack); both the `bad_url` copy and the 404 copy say so.
- **Endpoint**: the publication's public JSON API,
  `https://<pub>.substack.com/api/v1/posts/<slug>`. No key, no login.
- **Free posts only, honestly**: `audience != "everyone"` or
  `should_show_paywall` -> `code: "paywalled"` with copy explaining that
  saving the teaser would pretend to be the article. Nothing persists.
- **HTML -> markdown**: stdlib `HTMLParser` converter
  (`_MarkdownHTMLParser`) covering what Substack bodies actually contain:
  h1-h6, p, ul/ol/li (nested), blockquote, a, strong/em, pre/inline code,
  img (as `![alt](src)`), hr; script/style suppressed; 400k-char body cap.
- **Markdown shape**: `# title`, `*subtitle*`, byline/date/wordcount meta,
  `**Source:**` link, then the converted body.
- **Failure copy**: 404 (removed / wrong slug / custom domain), 429 rate
  limit, unreachable, non-JSON block page, missing body.

## Route: `POST /extract/substack` (token-gated)

`{url}` -> flag gate -> `extract_substack_post` ->
`persist_page_yoink(source_type="substack_post", subfolder="Substack",
slug_prefix="substack")`.

| Case | Status | Body |
|---|---|---|
| Flag off | 200 | `{ok: false, code: "disabled", error}` |
| Saved | 200 | `{ok: true, video_id, title, metadata}` |
| Paid post | 200 | `{ok: false, code: "paywalled", error}` |
| Bad URL / fetch failed | 200 | `{ok: false, code, error}` |
| Persist failed | 500 | `{ok: false, error}` |
| No/bad token | 403 | |

`metadata`: `{author, subtitle, post_date, wordcount, post_type}`.

## Deliberately not in this PR

- Extension button / site card / dashboard copy (SITE + AG per D-6).
- Custom-domain publications (needs content sniffing, not URL matching).
- Comments (Substack's comment API is a separate, heavier surface).

## Tests / proof

`tests/test_q01_substack_capture.py` (red on unpatched main: no module,
route 404): URL matcher + API mapping, free post to structured markdown
(headings/lists/links/emphasis/blockquote/code all asserted), paywall
refusal on either signal, specific failure copy, flag-off default, token
gate, persist round-trip through a real `Index` with the paywall refusal
relayed. Live Substack traffic is not exercised in CI.

# Dashboard Layout Surface Map

The dashboard is a single HTML app in `assets/dashboard/index.html`, served by the helper at `/dashboard`. It uses one fixed sidebar on desktop and a top rail below 1080px.

## Shell

- `.app` is the root grid.
- `.sidebar` holds the wordmark, tab buttons, count badges, the running status, and secondary actions.
- `.content` is the scrolling pane. Each `[data-tab-panel]` is hidden until its tab is active.
- At widths above 1080px, the sidebar stays in the left column and `.content` owns vertical scroll.
- At widths of 1080px and below, the sidebar becomes a top rail. Count badges sit directly beside their labels, with a 6px gap, so labels and counts read as one unit.

## Library

The Library tab starts with the headline, two learning links, and `.control-grid`.

Controls:

- `#searchInput` spans the full first row on narrow layouts.
- `#channelFilter`, `#topicFilter`, `#hookFilter`, `#formatFilter`, `#performanceFilter`, `#lengthFilter`, `#dateFrom`, `#dateTo`, and `#sortFilter` share the grid.
- Desktop controls use `minmax(150px, 1fr)`. Native selects reserve 38px of right padding for the chevron.
- At 1080px and below, Library controls use 2 columns. At 620px and below, they stack to 1 column.

Facet states:

- Populated facets stay enabled and show a neutral all-state label such as `All channels`, `All topics`, or `Any hook`.
- Empty classification facets are disabled and use short labels: `Format`, `Performance`, `Length`.
- Each empty facet carries a `title` that explains why it is empty.
- If `/library/facets` is unavailable, the built-in defaults stay enabled and `#facetStatus` explains the fallback.

The Library also opens with `#resumeCard`, the R-02 "resume where you left
off" open-loop, above the headline. It is populated by `GET /resume` on boot
and stays hidden when nothing qualifies. See
[corpus-digest.md](corpus-digest.md).

Routes consumed:

- `GET /memory/search`
- `GET /library/facets`
- `GET /engagement/scores`
- `GET /resurface`
- `GET /resume`

## Sources

The Sources tab opens with the headline, three learning links, then the `.get-extension` card, then `#sourceMap`.

`.get-extension` (id `#getExtensionCard`) is the in-app path to the browser button (UX-07). It carries:

- An `Open extension folder` button with `data-open-extension`. The delegated click handler calls `GET /open-extension`, which reveals `%LOCALAPPDATA%\Uoink\extension` in the OS file manager so the user can point `Load unpacked` at a folder they can see.
- A three-step load-unpacked list (extensions page, Developer mode, Load unpacked) whose copy matches the site `/install` steps for Chrome, Edge, and Brave.

The empty Library state (`setLibraryEmptyState("empty")` and the static `#libraryEmpty` fallback) carries the same `data-open-extension` button next to `Open Sources`, so a new user with an empty corpus has a direct install path.

Routes consumed:

- `GET /sources/manifest`
- `GET /open-extension`

## Uoink detail (saved-source view)

The `#tab-yoink` panel is the "uoink screen" opened from a Library card. Its
header (`.page-head`) carries the six action buttons in a
`.inline-row.yoink-actions` toolbar: Open folder, Open transcript file,
Re-capture source, Re-transcribe, Evidence, Write from this.

- On v3.3.2 the toolbar sat in the right column of a `space-between` flex
  `.page-head`, competing with the heading. Even at 1280 CSS px it wrapped
  into two cramped rows in the top-right, and on a DPI-scaled window (a
  physical 1280x800 window at 125-150% Windows scaling renders at ~1024-853
  CSS px) it degraded further, so not every action read as reachable.
- v3.3.3 scopes a rule to this header only: `#tab-yoink .page-head` is
  `flex-wrap: wrap`, the heading block is `flex: 1 1 320px`, and
  `.yoink-actions` is `flex: 1 1 100%`. The toolbar always drops to its own
  full-width row under the heading and wraps its buttons within the full
  content width, so at 1280 all six sit on one clean row and at narrower
  widths they wrap to two rows -- every action reachable, none cut off.
  Other tabs' `.page-head` layout is unchanged.

Verified with Playwright at 1280x800 and the DPI-scaled equivalents
(1024x640, 853x533): `document.body` never gains horizontal scroll and no
action button's right edge exceeds the viewport.

## Generate

Generate uses `.writing-layout`: a left form and a right draft/refine column.

The output picker is `#writingModePicker`, a `.radio-grid` using `repeat(auto-fit, minmax(118px, 1fr))`. This keeps `Newsletter` readable at 1100px and lets labels wrap instead of slicing words.

Routes consumed:

- `GET /memory/search`
- `GET /corpus/channels`
- `GET /writing/recent-ctas`
- `GET /writing/style-anchors/defaults`
- `GET /writing/style-anchors`
- `POST /writing/generate`
- `POST /writing/draft`

## Settings Topics

The topics editor lives in `#topicList`.

Each `.topic-row` uses 2 columns:

- Column 1 holds the topic name input.
- Column 2 holds the Remove button.
- The Keywords textarea spans the full row below them.

Keyword textareas start at 112px tall, use a 1.45 line-height, and auto-size on render and on edit. That keeps the third line visible and removes the half-line slicing seen in the v3.2.5 audit.

Routes consumed:

- `GET /settings`
- `POST /settings`
- `GET /settings/mcp-config`
- `GET /diagnose`
- `GET /channels`
- `GET /extract/page/allowlist`
- `GET /playlists/monitored`
- `GET /podcasts/feeds`

## Regression Checks

The permanent clipping probe lives at `E:\AI\projects\uoink\handoff\qa-harness-playwright\u10-clipping-sweep-check.js`.

It serves the dashboard HTML with mocked routes, captures 1280x800, 1100x800, and 900x800 screenshots, and checks:

- native select labels with canvas `measureText`
- the `Newsletter` radio label against the pill's real remaining space
- Settings topic-name inputs against their visible text area
- keyword textareas against `scrollHeight` versus `clientHeight`
- the 900px Library control grid
- the 900px sidebar badge gap

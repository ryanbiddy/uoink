# Surface Map: Source-Aware Popup Capture

How the extension popup captures **every shipped source** from the active
tab. Before this, the popup only understood YouTube — a Reddit / X / podcast /
article tab showed "Open a YouTube video tab, then reopen this popup." Now one
adaptive primary button classifies the active tab client-side and routes to the
right capture path.

## 1. Client-side classifier (`extension/lib/extract.js`)

`STC.classifyCaptureUrl(url)` returns `{ok, source, label, endpoint, action,
canonical, note}`. It reuses the existing normalizers and mirrors the
precedence of the dashboard's server-side `_classify_capture_url` — so the
popup can never disagree with the capture route. **It does not call the
helper's `/detect` route**, which is absent from the shipped build.

| Source (`source`) | Detector | `action` | Capture route |
|---|---|---|---|
| `youtube_video` | `normalizeYouTubeUrl` | `video` | `POST /extract` |
| `youtube_playlist` | `normalizePlaylistUrl` | `playlist` | `POST /playlist/start` |
| `x_video` | `normalizeTwitterUrl` | `x_video` | `POST /extract` |
| `reddit_thread` | `normalizeRedditUrl` | `reddit` | `POST /extract/reddit` |
| `podcast_feed` | `looksLikeFeedUrl` | `podcast` | `POST /podcasts/feeds` |
| `web_page` | `normalizeAnyUrl` | `page` | `POST /extract/page` |
| unsupported | — | — | "Nothing to uoink here" |

Precedence: a `watch?v=…&list=…` URL is a **video** (video is checked before
playlist), matching the server.

## 2. Popup DOM (`extension/popup.html`)

The current-tab affordance moved out of the first-run-only Quick Start panel
into its own always-visible `#current-source-panel` (single mode), so it helps
returning users too:

- `#current-source-preview` — tab title / canonical URL.
- `#uoink-current-btn` — the adaptive primary button. Label per source:
  "Uoink this video / playlist / post / thread / podcast / page".
- `#uoink-x-text-btn` — secondary; **only** shown on an X status when the
  server's `x_text_capture_enabled` flag is on (text capture is opt-in).
- `#uoink-podcast-btn` — secondary "Add this podcast feed"; shown when a web
  page advertises an RSS/Atom feed (see §4).
- `#uoink-allow-retry-btn` — secondary "Allow this site and retry"; shown when
  an article capture hits the allowlist wall (see §3).
- `#current-source-note` — honest per-source note, sourced from the
  classifier's `note`. For X it reads "Captures the post text and the
  author's thread — plus the video if the post has one," matching the
  text-first V-2b behavior and the dashboard's wording (the old
  "Captures the video. Post + thread text is a separate toggle." lagged the
  ship and was corrected after the v3.3.1 capture test).
- `#popup-version` — the footer version label. Sourced from
  `chrome.runtime.getManifest().version` at boot (`showVersion()` in
  `popup.js`) so it tracks the real build instead of a hardcoded string that
  drifts — the v3.3.1 capture test caught it stuck at "v2.1".

## 2a. Popup layout shell — pinned header + primary, one scroll region

Chrome caps a popup at ~600px and, before this, the whole `body` scrolled
as one long page: with `#more-options` open (or a populated Recent /
active-uoink / resurface state) the primary "Uoink this ..." button scrolled
off the top and every action needed the janky Chrome popup arrow-scroll.

The shell now fixes that:

- `body` is a fixed-height (`580px`) flex column with `overflow: hidden`, so
  the popup no longer grows past the cap or scrolls as a whole.
- `.popup-header` (logo + status dot) is `flex: 0 0 auto` and stays pinned.
- `.popup-scroll` is the single `overflow-y: auto` region holding every
  banner, mode panel, and the footer. It carries the only scrollbar.
- `#current-source-panel.sticky-primary` is `position: sticky; top: 0`
  inside `.popup-scroll`, so in single-video mode the adaptive
  "Uoink this ..." button is always visible while the secondary panels
  (Send to, prompts, Recent, More options) scroll cleanly beneath it.

Fixed height is a deliberate trade: short states (helper-offline, a picker
with few shots) show some empty space below the footer, in exchange for a
stable window and a primary action that never hides. Picker and playlist
modes swap their own content into the same scroll region.

## 3. Article capture + one-click allowlist (P1)

`page` action → `STC.postExtractPage(url)`.

- On `code: host_not_allowed`, the popup does **not** dead-end: it reveals
  "Allow this site and retry", stashing the tab hostname.
- Clicking it → `STC.addAllowedSite(host)` (`POST /extract/page/allowlist
  {action:"add", url_pattern:<host>}`) then re-fires `postExtractPage`. The
  server matches a bare host against the host **and** its subdomains.

## 4. Podcast RSS sniff — the one source needing page access (P1)

The feed URL isn't in the tab URL; it lives in
`<link rel="alternate" type="application/rss+xml">`. On a `web_page`, the popup
reads it via `chrome.scripting.executeScript` (granted by **`activeTab`** — the
only new capability is the `scripting` permission). If a feed is found, the
"Add this podcast feed" secondary appears → `STC.postPodcastFeed(feedUrl)`
(`POST /podcasts/feeds`). A news article's feed is offered as an *extra* option
rather than relabeling the page as a podcast, keeping the primary honest. If no
feed is found, nothing is claimed.

## 5. X video decoupled from the text flag (P0)

X video is now the **primary** button ("Uoink this post" → `POST /extract`,
which accepts x.com/twitter via `_normalize_video_url`). The
`x_text_capture_enabled` flag gates **only** the extra text/thread button — an
X video is uoinkable from the popup regardless of that flag.

## 6. Context-menu parity (P2)

`background.js` adds "Uoink this page (article)" for `http(s)` pages, routed
through the queue via `job.usePage` → `STC.postExtractPage`. Existing YouTube,
X, and Reddit menus are unchanged. Podcast right-click is intentionally omitted
(it would need background page access to sniff the feed).

## 7. Message / routing flow

```
popup detectCurrentSource()
   └─ chrome.tabs.query(active) → STC.classifyCaptureUrl(url)
          ├─ web_page → chrome.scripting.executeScript (RSS sniff)
          └─ render adaptive button + secondaries

click → runPopupUoinkCurrent() dispatches on currentSource.action:
   video/x_video → STC.postExtract       ─┐
   reddit        → STC.postExtractReddit  ├─ handleCorpusCapture()
   page          → STC.postExtractPage    ─┘  (clipboard + open Claude)
   playlist      → STC.playlistStart
   podcast       → STC.postPodcastFeed
```

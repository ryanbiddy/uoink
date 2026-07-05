# Surface map: sidebar nav, routing, and shell hygiene

Covers the dashboard's navigation model after U-07 (UX-15) plus the three
shell dedupes/copy fixes bundled with it (UX-12, UX-16, UX-17). File:
`assets/dashboard/index.html`.

## Navigation model

**Router**: `switchTab(tab)` is the single router. It maps legacy tabs
(`build`/`script` -> `writing`), toggles panel visibility
(`[data-tab-panel]`), triggers per-tab loaders, and sets nav active state.
`applyHashRoute()` translates `#<tab>` URLs into `switchTab` calls, so
hash arrivals get correct nav state too.

**Nav entries** (`[data-tab-button]`, wired by one loop in `wireEvents`):

- Main nav: Library (count), Sources (count), For You (count), Generate
  (count), Settings.
- Sidebar bottom: **Activity** (`#viewActivity`, count badge) is a real
  nav entry now, not a one-off button with its own listener.
- "More controls" disclosure: **About Uoink** (new; the About page held
  the version, update links, quick start, and hooks link while being
  reachable only by URL hash).

**Orphan panels** (no nav entry of their own) highlight their logical
parent through the `NAV_OWNER` map in `switchTab`:

| Panel | Highlights |
|---|---|
| `yoink` (detail view) | Library |
| `evidence` | Library |
| `features` | Sources |

Invariant: exactly one nav entry is active for every reachable panel; the
sidebar never lies (old bug: Activity showed with zero active entries, or
with Settings still lit).

## Style anchors: one manager (UX-12)

- The right-column **Style anchors panel** (`#styleAnchorManager` +
  defaults browser + add form) is the ONLY anchor library manager, and
  owns the only active-count badge (`#styleAnchorSummary`, "N/10
  active"). The form panel-head's duplicate "0/10 anchors" badge is gone.
- The form keeps a **per-draft selector** (`#writingAnchorSelect`): the
  checkbox list that feeds `selectedAnchorIds()` (up to 5 for "From
  anchors", 1 for "Specific anchor") in the generate payload. It is NOT
  a duplicate manager: it picks which anchors ground the current draft.
  Labeled "Anchors for this draft", hidden while Style = Default voice
  (`syncWritingStyleUi` on the radio change), and linked to the manager
  via "Manage anchors ->" (smooth-scrolls the manager panel into view).

## Connection JSON: one disclosure (UX-16)

"Advanced: connection JSON" exists exactly once: the static `<details>`
in Settings > Agent connection (textarea `#mcpConfig` + copy button).
`agentSetupMarkup()` no longer embeds a second identical disclosure into
every status-card variant (which used to render two toggles 40px apart in
Settings, since the settings card and the static details are siblings).

## Activity headline (UX-17)

`#activityHeadline` is rendered by the activity refresh:

- zero active work: "Nothing uoinking right now."
- otherwise: "N in flight uoinking..."

The old markup interpolated a bare count into fixed copy, which read as
broken English at zero.

## Tests / proof

- `tests/test_u07_nav_hygiene.py` -- static contract for all four fixes.
- `handoff/qa-harness-playwright/u07-nav-hygiene-check.js` -- live at
  1280/1100/900: Activity/About hold single active nav state, detail view
  highlights Library, zero-state headline reads as a sentence, anchor
  selector hides for Default voice and shows with the manage link for
  From anchors, exactly one counter and one connection-JSON disclosure.

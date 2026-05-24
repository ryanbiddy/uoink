# Uoink extension pre-launch audit

**Date:** 2026-05-16
**Branch audited:** `claude/v2-sprint13` (off `v2-integration` @ `4087486`)
**Scope:** `extension/popup.js`, `extension/popup.html`,
`extension/lib/*.js`, `extension/content.js`. Read-only — no code was
modified. `setup.html` / `setup.js` were explicitly out of scope
(Codex's lane); `manifest.json` is out of the literal sweep but is
referenced where it gates audited code.

**Verification note:** no JavaScript runtime is installed on the audit
host, so `node --check` could not be run. Findings are from manual code
review.

## Summary

| Severity | Count |
|---|---:|
| BLOCKER  | 2 |
| SERIOUS  | 1 |
| POLISH   | 5 |
| **Total** | **8** |

Both blockers already have an *uncommitted* fix in the working tree (see
each finding). They are still blockers: an uncommitted edit is not a
shipped fix, and a clean checkout of `v2-integration` builds broken.

---

## BLOCKER findings

### B1 — Shorts content script never loads; Sprint 11 button is dead code
- **Ref:** `extension/manifest.json:33-39` (`content_scripts.matches`)
- **Summary:** The committed manifest matches only
  `https://www.youtube.com/watch*`, so `content.js` is never injected on
  `/shorts/<id>` pages — Sprint 11's floating Shorts button can never
  execute, regardless of how correct its code is.
- **Fix:** Add `"https://www.youtube.com/shorts/*"` to
  `content_scripts.matches`. An uncommitted edit in the working tree
  already does exactly this; it must be committed before launch.

### B2 — Mock API still enabled; playlist mode talks to mocks, not the helper
- **Ref:** `extension/popup.js:8` (`const USE_MOCK_API = true`)
- **Summary:** In committed `v2-integration`, `USE_MOCK_API` is `true`,
  so `STC.playlist*` / `jobStatus` / `jobCancel` route through
  `lib/mock-api.js` instead of the real helper — playlist mode is
  non-functional for real users. The store-listing pre-submission
  checklist (`docs/store-listing.md:145`) explicitly requires `false`.
- **Fix:** Set `USE_MOCK_API = false`. An uncommitted edit in the
  working tree already does this; it must be committed before launch.

---

## SERIOUS findings

### S1 — Unconditional console.log of every extraction request
- **Ref:** `extension/lib/extract.js:167`
- **Summary:** `console.log("[Uoink] POST", targetUrl, requestBody)` runs
  on every single extraction (happy path, not an error path), printing
  the request URL and body to the console of every YouTube page and the
  service worker — noisy and unprofessional for a public ship.
- **Fix:** Remove the line, or gate it behind a debug flag. (The
  `console.error` calls at lines 179/181/188/193 are genuine error-path
  diagnostics and are fine to keep.)

---

## POLISH findings

### P1 — Link-styled controls are not keyboard accessible
- **Ref:** `extension/popup.html:651` (`#status-help`), `:666`
  (`#picker-select-all`), `:723` (`#open-index`), `:891`
  (`#open-settings`), `:892` (`#open-mcp-setup`)
- **Summary:** These five `<a>` elements have click handlers but no
  `href`, `role`, or `tabindex`, so they are not in the tab order and
  are not announced as controls by screen readers.
- **Fix:** Add `role="button" tabindex="0"` plus an Enter/Space keydown
  handler — the `#active-playlist-pill` element (`popup.html:694`)
  already implements this pattern correctly and can be copied.

### P2 — Playlist URL input has no accessible label
- **Ref:** `extension/popup.html:797` (`#pl-url`)
- **Summary:** The input relies on a `placeholder` only; the
  `YouTube playlist URL` panel title above it is not programmatically
  associated, so the field has no accessible name.
- **Fix:** Add a `<label for="pl-url">` or an `aria-label` on the input.

### P3 — Dead ternary with two identical branches
- **Ref:** `extension/popup.js:1792`
- **Summary:** `pickerCopyBtn.textContent = kind === "copy" ? "Copying…"
  : "Copying…";` — both arms are identical, a leftover artifact.
- **Fix:** Replace with a plain assignment, or give the `"cancel"` path
  its own wording.

### P4 — Native alert()/confirm() used inside the popup
- **Ref:** `extension/popup.js:215, 230, 255, 262`
- **Summary:** Session start/cancel/end use `alert()` and `confirm()`.
  These work but are visually jarring in an extension popup and
  inconsistent with the in-popup toast/inline-error affordances used
  elsewhere.
- **Fix:** Optional — route these through the existing `showToast` /
  inline-error elements for a consistent look.

### P5 — Shorts floating button placement is unverified in-browser
- **Ref:** `extension/content.js:64-75` (`.stc-yt-shorts-floating` CSS)
- **Summary:** The Sprint 11 Shorts button is `position: fixed;
  right: 24px; bottom: 84px; z-index: 2000`. The logic is sound, but the
  exact offsets were never confirmed against the live Shorts DOM and
  could overlap the Shorts comment panel or look off on small windows.
- **Fix:** Visually confirm placement during the pre-merge Shorts
  smoke test (already planned) and nudge the offsets if it collides.

---

## Sprint 11 Shorts button — code review

Reviewed `extension/content.js` lines 30, 59-79, 343-349, 496-567,
619-633 for the edge cases called out in the sprint brief:

- **Shorts page without a player / bare `/shorts/`:** `extractVideoId`
  (`extract.js:118`) requires a 6+ char id, so a Shorts URL with no
  valid id makes `isSupportedVideoPage()` false and no button is built.
  No crash. The floating button is parented to `<body>`, so it never
  depends on the player element existing. **Handled.**
- **Rapid Shorts-to-Shorts scroll:** the floating button lives on
  `<body>`, which YouTube does not tear down between reels, so it
  persists with no re-injection. The MutationObserver does a cheap
  `getElementById` + `isShortsPage()` check per mutation and only
  rebuilds on a `/watch` ↔ `/shorts` variant mismatch. **Handled.**
- **Navigating off Shorts:** `injectButton()` removes the stale floating
  button when `isSupportedVideoPage()` is false. **Handled.**
- **Click during a reel transition:** the click handler reads
  `window.location.href` at click time, so it yoinks whichever Short the
  URL currently reflects. Correct by design.

**Conclusion:** the Shorts button implementation itself is sound. Its
only blocking problem is external — the manifest match pattern (B1).
Once B1 is fixed, the code is expected to work; placement still wants a
visual check (P5).

## Task #60 assessment — `clipboard_screenshot_cap` save button

Searched `popup.js`, `popup.html`, and `content.js`: there is **no**
`clipboard_screenshot_cap` (or `screenshot_cap`) reference anywhere in
the audited code. The only setting surfaced inside the popup is
`interval` (`popup.js:128-134`), which auto-saves on the input's
`change` event and shows a transient "Saved." confirmation — there is no
save button and therefore no placement nit.

**Verdict:** task #60 is purely a `setup.html` issue. It is not a
problem in the extension code in this audit's scope. It should be
assessed and fixed (if needed) in Codex's `setup.html` lane.

## Out-of-scope observations (FYI, not findings)

- `setup.html:509` and `setup.js:22-30` carry `1.0.0` strings
  (`Uoink-Setup-1.0.0.exe`, version comments). These are in Codex's lane
  and were not audited; flagged only so Codex/Ryan can confirm whether
  the installer keeps its own `1.0.0` versioning independent of the
  extension's `2.0.0`.
- All `MOCK_FORCE_*` flags in `lib/mock-api.js:42-55` are `false`,
  satisfying the store-listing checklist item about no mock-force flags
  committed as `true`.

## Open question for the version owner

`manifest.json:5` is still `"version": "1.0.0"` and Sprint 12 is **not**
merged into `v2-integration`. The store-listing checklist
(`docs/store-listing.md:144`) requires `2.0.0` for the v2 launch. This
is presumably Sprint 12's bump — confirm Sprint 12 lands (and bumps it)
before the release is tagged.

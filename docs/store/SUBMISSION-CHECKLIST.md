# Chrome Web Store submission checklist — Uoink

**This submission is a manual Ryan step.** This folder is the ready-to-submit
package. Nothing here submits anything; it's copy, images, and a checklist.

## What's in this folder

| File | Use |
|---|---|
| `listing.md` | Item name, summary, detailed description, single purpose, category, support email, privacy URL, website — all copy-paste ready. |
| `permissions-justification.md` | Per-permission justifications + data-use affirmations for the reviewer. |
| `screenshots/01…05-*.png` | The 5 store screenshots, exactly 1280×800. Upload in filename order. |
| `tiles/promo-small-440x280.png` | Small promo tile. |
| `tiles/promo-marquee-1400x560.png` | Marquee promo tile. |
| `tiles/promo-large-920x680.png` | Spare large promo / social. |

## Pre-submission (verify before uploading)

- [ ] `hi@uoink.app` mailbox receives mail.
- [ ] `https://uoink.app/privacy` resolves and is current.
- [ ] `https://uoink.app` resolves.
- [ ] `extension/manifest.json` version matches the explicitly approved submission tag.
- [ ] `USE_MOCK_API = false` in `extension/popup.js`.
- [ ] `PUBLISHED_INSTALLER_VERSION` in `extension/setup.js` matches a
  non-draft GitHub release whose `Uoink-Setup-<version>.exe` asset resolves.
- [ ] License compliance clean (CRIT-2): confirm the shipped build no longer bundles AGPL/GPL deps and `THIRD-PARTY-NOTICES.md` is current — CWS rejects license-mismatched extensions.
- [ ] Final extension `.zip` produced from a clean checkout (`build.ps1` zips `extension/`).
- [ ] Tested in a clean Chrome profile with the helper running: in-page button, `Alt+U`, and right-click all work on a real YouTube video.

## Submission steps

1. Log in at https://chrome.google.com/webstore/devconsole/.
2. Select the existing Uoink listing (or create a new item) and upload the
   clean `extension-uoink-<approved-version>.zip`.
3. Confirm the store title is `Uoink — Local corpus for AI` (or `Uoink` if the long title is rejected).
4. Paste from `listing.md`: summary, detailed description, single purpose statement, category (Productivity), language (English US), support email, privacy URL, website.
5. Paste from `permissions-justification.md`: each permission justification + the data-use affirmations.
6. Upload the 5 screenshots from `screenshots/` (in order) and the promo tiles from `tiles/`.
7. Complete the Privacy practices form (Website content — selected only; no sale; limited use).
8. Click **Submit for review**.

## Notes / open items

- **Domains were migrated uoink.video → uoink.app.** All copy in this folder uses uoink.app. If any older asset still shows uoink.video, do not use it.
- Screenshots are dashboard + extension shots resized from `marketing/assets/2026-07-06-final` and `2026-07-06`. If a fresher extension-on-YouTube capture exists at submission time, swap screenshot #1 for it (it's the search-results thumbnail).
- The 6th "podcast diarization / evidence panel" screenshots from the older CWS draft are optional; the 5 here tell the core story (capture → own → write → search → organize).

# Prompt 5 — Web Store assets prep

Generate everything needed to submit to the Chrome Web Store next weekend.

**Before running this prompt:** Make sure your AI-generated logo files are saved in `assets/` (e.g., `assets/logo.png`, `assets/logo.svg`). If you haven't generated a logo yet, do that first — see Tier 0 in the weekend plan.

## TASK 1 — EXTENSION ICONS

We have a logo from Recraft / Midjourney saved in `assets/`. Generate the required Chrome Web Store icon sizes from it:

- 16x16 (toolbar)
- 32x32 (Windows)
- 48x48 (extension management page)
- 128x128 (store listing)

Save them in `extension/icons/` as `icon-16.png`, `icon-32.png`, `icon-48.png`, `icon-128.png`. Update `manifest.json`'s icons block to point at all four.

If the source logo doesn't downscale well at 16x16, use a simplified mark (just the symbol, no wordmark) for the 16/32 sizes and the full logo for the 48/128 sizes.

If image processing libraries aren't available, write a Python script that uses Pillow (`pip install pillow`) to do the resizing, and run it. If Pillow can't be installed, document the dimensions in `assets/icons-needed.md` so the user can generate them manually.

## TASK 2 — PROMOTIONAL IMAGES

The Chrome Web Store requires:

- **1 small promo tile:** 440 x 280 (required)
- **1 large promo tile:** 920 x 680 (optional but recommended)
- **Marquee promo tile:** 1400 x 560 (optional)

Generate placeholder versions in `assets/store/` — these don't have to be final, but the dimensions and rough composition need to exist so finalization next weekend is straightforward.

For the small tile: black background, "Yoink" wordmark on the left, "The missing layer between YouTube and your AI" tagline below in smaller type, a small mock screenshot of the YouTube button on the right.

If image generation tools aren't available locally, write `assets/store/README.md` describing exactly what each tile needs to look like so the user can produce them in Figma or Canva.

## TASK 3 — STORE LISTING DRAFT

Create `docs/store-listing.md` with the canonical-voice copy for the Chrome Web Store listing:

```markdown
# Chrome Web Store Listing — Yoink

## Title (45 chars max)
Yoink — Yoink any YouTube video into your AI

## Short description (132 chars max)
[Draft this in canonical voice. Should answer "what does this do" in one sentence and reference Claude/ChatGPT.]

## Long description
[Draft this — full pitch, feature list, how it works, local + free + open source. Use the 100-word pitch as a starting point and expand. Aim for ~500 words.]

## Category
Productivity

## Language
English

## Support email
yoink@replayryan.com (or your existing email)

## Privacy policy URL
https://yoink.video/privacy (placeholder for now — must exist before submission)

## Website
https://yoink.video
```

## TASK 4 — SCREENSHOTS

The Web Store wants 1-5 screenshots at 1280x800 or 640x400. Create `docs/screenshot-list.md` with a list of 5 screenshots to capture next weekend with the actual product:

```markdown
# Screenshots needed for Web Store submission

All screenshots: 1280x800 PNG. Use Cleanshot or Snagit for capture and annotation.

## 1. Yoink button under a YouTube video
- **Setup:** Open a public YouTube video (pick a recent video from a creator with relevant subject matter)
- **Crop:** Tight on the action button row. Show Like, Share, and Yoink button side by side
- **Annotation:** Subtle arrow pointing at the Yoink button, label "One click to yoink"

## 2. The popup with two destination buttons + prompts
- **Setup:** Click the Yoink extension icon while a yoink is fresh
- **Crop:** Full popup, no surrounding browser chrome
- **Annotation:** Highlight the destination buttons and prompt library

## 3. The yoink.md file open in a markdown viewer
- **Setup:** Open the generated yoink.md in VS Code or Obsidian to show the structure
- **Crop:** Show the metadata header, transcript, and screenshot section
- **Annotation:** None needed — let the structure speak

## 4. Claude.ai with a yoink corpus pasted in, mid-conversation
- **Setup:** Paste a corpus into Claude, ask "Decode the hook," show the response
- **Crop:** Show the user message (truncated corpus visible) and Claude's analysis
- **Annotation:** "Yoink → Claude in one click"

## 5. The Desktop\Yoink folder with topic-organized subfolders
- **Setup:** Open File Explorer at Desktop\Yoink showing 4-5 topic folders
- **Crop:** Show the folder tree with a few yoinks visible inside each
- **Annotation:** "Auto-organized by topic"
```

## TASK 5 — SUPPORT EMAIL

The Web Store requires a support email. Add `yoink@replayryan.com` (or your existing email) to the listing draft. Note in the docs that this email must be deliverable before submission.

## WHEN DONE

- Report all generated files
- Confirm the icons render correctly at all four sizes
- List the placeholder promo tiles you created (or the documentation files if image generation wasn't possible)
- Print: `=== PROMPT 5 COMPLETE ===` so the orchestrator knows to advance

The user will manually next weekend:
- Capture the 5 screenshots
- Finalize promo tiles
- Submit to Web Store

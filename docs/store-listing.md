# Chrome Web Store Listing — Uoink

## Title (45 chars max)
Uoink — any YouTube video into your AI

<!-- 38 chars. Real Web Store cap is 45; the old "35 chars" target was stale. -->

## Short description (132 chars max)
The YouTube layer for any AI. Uoink any video into Claude, ChatGPT, or your agent — transcript, screenshots, comments, all of it.

<!-- 127 chars. -->

## Long description

You see a video that's clearly working. You want to know why. So you paste the link into Claude and hope it can "watch" it. It can't. It hallucinates titles, invents quotes, and gives up past the first paragraph. You give up too — and watch the whole thing on 2x while taking notes by hand.

Uoink is the missing layer between YouTube and your AI. (The magnet logo? Always a U.)

Click the Uoink button under any YouTube video and you get one structured markdown corpus, auto-loaded onto your clipboard:

- The full timestamped transcript, chapter-aware
- Timestamped screenshots, with a paste-safe subset embedded in the clipboard
- The top 50 comments, with author and like count
- Full video metadata — views, likes, tags, description, upload date
- The thumbnail
- Channel context — subscriber count and the channel's last 5 videos

Paste it into Claude or ChatGPT. Ask "Decode the hook," "Outline the structure," "What would make this 2x better." Uoink ships with an 11-prompt starter library.

THREE WAYS TO USE UOINK

As a Chrome extension — one click on the in-page button, your clipboard fills, the chat opens. Paste, prompt, analyze.

As an MCP server — Uoink ships a local MCP server with 13 tools your agent calls directly: uoink_video, uoink_playlist, list_recent_uoinks, search_uoinks, analyze_comments, classify_hook, get_citation_map, get_uoink_health, find_mentions, and more. Tell Claude "uoink that video and decode the hook" — it does both. Officially tested with Claude Desktop and Cursor.

As an operator Skill — a portable SKILL.md (agentskills.io standard) that adds citation discipline, hook-autopsy tweet mode, and the Uoink Hook Type taxonomy on top of the MCP tools.

WHY PEOPLE USE UOINK

- One click in, ready to analyze. No copy-pasting transcripts.
- The full picture, not just the words — comments, channel context, screenshots.
- Playlist mode — up to 10 videos at a time, combined corpus + per-video files.
- Auto-organized on disk into topic folders under Desktop\Uoink\.
- Local-first. No accounts, no cloud, no required telemetry.
- Free and open source. MIT-licensed.

OPTIONAL AI FEATURES (BYO ANTHROPIC KEY)

Uoink stays free and local by default. Comment Intelligence, Hook Type classification, and Entity Extraction call the Anthropic API with your own key (stored in Windows Credential Manager, never plaintext). Off by default. Uoink itself collects nothing.

Windows 10/11 today; macOS in this release. Chrome or any Chromium browser. uoink.video

---

*Uoink is part of the [ReplayRyan](https://replayryan.com) family of tools.*

## Category
Productivity

## Language
English (United States)

## Support email
hi@uoink.video

> **Note:** This support email must be deliverable before submission. Confirm `hi@uoink.video` is receiving mail.

## Privacy policy URL
https://uoink.video/privacy

> **Note:** This URL must resolve before submission. The Web Store reviewer will fetch it.
>
> The v2.1 privacy policy is **drafted** at `docs/privacy-policy.md` in
> this repo. To go live, publish that file's content (rendered as a web
> page) at `https://uoink.video/privacy`. It already covers the
> required points:
> 1. Core extraction is fully local. Uoink itself collects nothing.
> 2. Optional AI features (Comment Intelligence, Hook Type, Entity Extraction) call the Anthropic API with the user's own API key when enabled by the user. Smart Screenshot Picker is opt-in but stays fully local — it does not call Anthropic.
> 3. The user's API key is stored in Windows Credential Manager and never transmitted anywhere except to Anthropic in the headers of those API calls.
> 4. No analytics, telemetry, or remote logging.

## Website
https://uoink.video

## Permissions justification

The Web Store will ask why each permission is requested. Pre-drafted answers:

- **`clipboardWrite`** — Uoink writes the extracted markdown corpus to the user's clipboard so they can paste it into Claude or ChatGPT.
- **`notifications`** — surfaces success and error toasts (e.g., "Uoinked ★ Saved to: Social Media Research.") so the user knows when an extraction completes.
- **`storage`** — persists user settings (screenshot interval, clipboard screenshot cap, active research session, queue state, last-uoink affordance state) across browser sessions.
- **`contextMenus`** — adds 'Uoink this video' and 'Uoink this page' entries on YouTube right-click menus; adds a third 'Uoink into session: <name>' entry when a research session is active.
- **`activeTab`** — reads the current YouTube URL when the user clicks the extension action.
- **`offscreen`** — the MV3 service worker uses an offscreen document to access the clipboard API (the only supported path in MV3).
- **Host permissions:**
  - `https://www.youtube.com/*`, `https://m.youtube.com/*`, `https://youtu.be/*`, `http://127.0.0.1:5179/*`, `http://localhost:5179/*` — content script matches www.youtube.com/watch* and www.youtube.com/shorts/* only; the extension communicates with the local Uoink helper server

## Single purpose statement

Uoink has one purpose: extract a structured markdown corpus (transcript, screenshots, comments, metadata) from a YouTube video and make it available to the user's AI of choice — either via clipboard (Chrome extension flow) or via MCP tools (agent flow).

## Pre-submission checklist

- [ ] All 5 screenshots captured at 1280x800 (see `docs/screenshot-list.md`)
- [ ] Promo tiles finalized in Figma (placeholders in `assets/store/`), regenerated with the v3.1 magnet-U wordmark
- [ ] Privacy policy live at https://uoink.video/privacy with v2.1 accurate language (covers BYO Anthropic key + keyring storage)
- [ ] Support email hi@uoink.video receiving mail
- [ ] uoink.video landing page live (or holding page is fine)
- [ ] Extension version in `manifest.json` matches release tag (2.1.0 for the rename release)
- [ ] `USE_MOCK_API = false` in `extension/popup.js`
- [ ] `INSTALLER_PUBLISHED = true` in `extension/setup.js`
- [ ] Final `.zip` of the `extension/` folder produced (no dev artifacts, no `MOCK_FORCE_*` flags committed as true)
- [ ] Tested install + first uoink on a clean Chrome profile
- [ ] Tested MCP setup flow on a clean Claude Desktop install (the v2 launch headliner)

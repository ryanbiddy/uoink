# Chrome Web Store Listing: Uoink

## Title (45 chars max)
Uoink - Local corpus for AI

<!-- 28 chars. -->

## Short description (132 chars max)
Save videos, podcasts, and articles on your disk, then hand a cited corpus to your AI for writing.

<!-- 94 chars. -->

## Long description

Uoink keeps the videos, podcasts, and articles you study on your own disk, then hands them to your AI as a cited corpus you can write from in your voice.

This Chrome extension adds the fastest capture path for YouTube. Click the Uoink button under a video, press Alt+U, or right-click a YouTube video link. Uoink saves the source as a structured local corpus on your computer. The clipboard version is ready for Claude, ChatGPT, or your agent. The full files stay on disk.

For YouTube sources, Uoink captures:

- Timestamped transcript text
- Timestamped screenshots, with a paste-safe subset in the clipboard
- Top comments, authors, and like counts
- Video title, channel, description, tags, views, and upload date
- Thumbnail and channel context
- A JSON sidecar for agents and scripts

Use it when a source is worth studying, quoting, remixing, or writing from later.

### Ways To Use Uoink

**Chrome extension**
Click the in-page Uoink button, use Alt+U, or right-click a YouTube video link. Uoink saves the source, copies the useful version to your clipboard, and keeps the full corpus on your machine.

**Local dashboard**
Search your Library, filter by topic or channel, inspect Evidence, and turn saved videos, podcasts, and articles into credited tweets, threads, blog drafts, or scripts.

**MCP and agent tools**
Connect Claude Desktop, Cursor, or another MCP-capable client to the local Uoink helper. Tools include `uoink_video`, `uoink_playlist`, `list_recent_uoinks`, `search_uoinks`, `get_uoink_corpus`, `analyze_comments`, `classify_hook`, `get_citation_map`, `get_uoink_health`, and `find_mentions`.

### Why Creators Use It

- **One click, full source.** Skip transcript copying and screenshot juggling on supported videos.
- **Context travels with the transcript.** Comments, metadata, and frames stay close to the words.
- **Local-first by default.** Files, screenshots, and the search index stay on your computer.
- **Agent-friendly.** Your AI can call Uoink tools directly through the local helper.
- **Writing-aware.** Uoink can draft from saved sources while keeping creator credit visible.

### Optional AI Features

Core capture works without an API key. Optional features use your own Anthropic API key:

- Comment Intelligence groups comment themes and notable disagreements.
- Hook Type classification labels the opening style.
- Entity Extraction finds people, tools, products, companies, and topics across your library.

These features are off by default. Your key is stored with the operating system credential store and is only sent to Anthropic for the calls you choose.

### Privacy Summary

- Uoink runs without accounts or a Uoink cloud.
- The helper runs on `127.0.0.1`.
- Saved corpora live under your chosen local folder, usually `Desktop\Uoink`.
- Optional AI features send source text to Anthropic only when you enable them.
- Smart Screenshot Picker stays local.

Full policy: `https://uoink.video/privacy`

### Requirements

- Windows 10 or Windows 11
- Chrome or a Chromium-based browser
- The Uoink local helper, installed from the GitHub release

## Category
Productivity

## Language
English (United States)

## Support email
hi@uoink.video

> Confirm this mailbox receives mail before submission.

## Privacy policy URL
https://uoink.video/privacy

> Confirm this URL resolves before submission. The policy draft lives at `docs/privacy-policy.md`.

## Website
https://uoink.video

## Permissions Justification

- **`clipboardWrite`**: Uoink writes the extracted markdown corpus to the user's clipboard so it can be pasted into Claude, ChatGPT, or a notes app.
- **`notifications`**: Uoink shows success and error messages when a capture finishes, fails, or needs the local helper.
- **`storage`**: Uoink saves local extension settings such as screenshot count, queue state, active session, and setup state.
- **`contextMenus`**: Uoink adds right-click actions for supported YouTube video pages and links.
- **`activeTab`**: Uoink reads the current YouTube URL when the user clicks the extension action.
- **`offscreen`**: Chrome MV3 requires an offscreen document for clipboard access from the service worker.
- **Host permissions**: YouTube hosts are used for the in-page button and video-link actions. `127.0.0.1:5179` and `localhost:5179` are used to talk to the local Uoink helper.

## Single Purpose Statement

Uoink saves supported source pages, starting with YouTube videos, into a structured local corpus and makes that corpus available through the clipboard, dashboard, and local MCP tools.

## Pre-Submission Checklist

- [ ] 5 screenshots captured at 1280x800, see `docs/screenshot-list.md`
- [ ] Promo tiles regenerated from `assets/build_store_assets.py`
- [ ] Privacy policy live at `https://uoink.video/privacy`
- [ ] `hi@uoink.video` receiving mail
- [ ] Website live at `https://uoink.video`
- [ ] `extension/manifest.json` version matches the release tag
- [ ] `USE_MOCK_API = false` in `extension/popup.js`
- [ ] `INSTALLER_PUBLISHED = true` in `extension/setup.js`
- [ ] Final extension zip produced from a clean checkout
- [ ] Clean Chrome profile tested with the helper running
- [ ] Right-click, Alt+U, and the in-page button tested on a real YouTube video

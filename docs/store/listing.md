# Chrome Web Store listing — Uoink (copy-paste ready)

Everything below is ready to paste into the CWS Developer Console. Facts current
as of v3.2.8. Domains/emails updated to **uoink.app**. Submission is a manual
Ryan step — see `SUBMISSION-CHECKLIST.md`.

---

## Item name (45 chars max)
```
Uoink — Local corpus for AI
```
<!-- 27 chars -->

## Summary / short description (132 chars max)
```
Save videos, podcasts, and articles to your own disk, then hand your AI a cited corpus to write from.
```
<!-- 101 chars -->

## Category
Productivity

## Language
English (United States)

---

## Detailed description

Uoink keeps the videos, podcasts, and articles you study on your own disk, then hands them to your AI as a cited corpus you can write from in your voice.

Paste a bare YouTube link into Claude and it will happily invent what the video says. Give it a Uoink corpus and it quotes the transcript, cites timestamps, and reads the comments.

This extension is the fastest capture path. Click the Uoink button under a video, press Alt+U, or right-click a video link. Uoink saves the source as a structured corpus on your computer, puts a paste-ready version on your clipboard for Claude, ChatGPT, or your agent, and keeps the full files on disk.

Uoink captures more than YouTube:

- **YouTube** — timestamped transcript, timestamped screenshots (a paste-safe subset in the clipboard), top comments with authors and like counts, title, channel, description, tags, views, upload date, thumbnail, and a JSON sidecar for agents and scripts.
- **X / Twitter** — video transcripts and post text with author credit.
- **Podcasts** — RSS feeds and episodes, transcribed locally with Whisper, with speaker labels for long interviews.
- **Web pages and articles** — readable text into the same corpus format.
- **Reddit** — threads and top comments as clean Markdown.

Use it when a source is worth studying, quoting, remixing, or writing from later.

### Three ways to use Uoink

**Chrome extension.** One click on a video page (or Alt+U, or right-click). Uoink saves the source, loads your clipboard, and keeps the full corpus on your machine.

**Local dashboard.** Search your Library, filter by topic or channel, inspect Evidence, and turn saved videos, podcasts, and articles into credited tweets, threads, blog drafts, or scripts — in your own voice.

**MCP and agent tools.** Connect Claude Desktop, Cursor, Cline, or another MCP-capable client to the local Uoink helper. Tools include `uoink_video`, `uoink_playlist`, `list_recent_uoinks`, `search_uoinks`, `get_uoink_corpus`, `analyze_comments`, `classify_hook`, `get_citation_map`, `get_uoink_health`, and `find_mentions`.

### Why creators use it

- **One click, full source.** Skip transcript copying and screenshot juggling on supported videos.
- **Context travels with the transcript.** Comments, metadata, and frames stay close to the words.
- **Local-first by default.** Files, screenshots, and the search index stay on your computer.
- **Agent-friendly.** Your AI can call Uoink tools directly through the local helper.
- **Writing-aware.** Uoink can draft from saved sources while keeping creator credit visible.

### Optional AI features

Core capture works without an API key. Optional features use your own Anthropic API key:

- Comment Intelligence groups comment themes and notable disagreements.
- Hook Type classification labels the opening style.
- Entity Extraction finds people, tools, products, companies, and topics across your library.

These features are off by default. Your key lives in the operating system credential store and goes only to Anthropic, only for the calls you choose.

### Privacy summary

- Uoink runs without accounts or a Uoink cloud.
- The helper runs on 127.0.0.1.
- Saved corpora live under your chosen local folder, usually `Desktop\Uoink`.
- Optional AI features send source text to Anthropic only when you enable them.
- Smart Screenshot Picker stays local.

Full policy: https://uoink.app/privacy

### Requirements

- Windows 10 or Windows 11
- Chrome or a Chromium-based browser
- The free Uoink local helper, installed from the GitHub release (https://uoink.app/install)

Uoink is completely free and open source (MIT). Users are responsible for ensuring their use of captured media complies with the Terms of Service and copyright policies of YouTube, Reddit, X (Twitter), and any other source platforms.

---

## Single purpose statement (1,000 chars max)
```
Uoink saves supported source pages — starting with YouTube videos, plus X posts, podcasts, and web pages — into a structured local corpus (transcript, screenshots, comments, and metadata) and makes that corpus available through the clipboard, a local dashboard, and local MCP tools for AI agents.
```

## Support email
```
hi@uoink.app
```
> Confirm this mailbox receives mail before submission.

## Privacy policy URL
```
https://uoink.app/privacy
```
> Confirm this URL resolves before submission.

## Website / homepage
```
https://uoink.app
```

---

## Screenshots (docs/store/screenshots/, all 1280×800)

The Web Store accepts up to 5. The first appears in search results — lead with the button on YouTube.

| # | File | Suggested caption |
|---|---|---|
| 1 | `01-uoink-button-on-youtube.png` | One click under any YouTube video saves the full source to your disk. |
| 2 | `02-your-local-library.png` | Your captured videos, podcasts, and articles — one local library you own. |
| 3 | `03-write-from-your-corpus.png` | Turn saved sources into credited drafts in your own voice. |
| 4 | `04-search-your-corpus.png` | Search and filter everything you've saved by topic and channel. |
| 5 | `05-auto-organized-by-topic.png` | Captures auto-sort into topic folders as you go. |

## Promo tiles (docs/store/tiles/)

| Asset | File | CWS field |
|---|---|---|
| Small promo tile | `promo-small-440x280.png` | Small promo tile (440×280) |
| Marquee promo tile | `promo-marquee-1400x560.png` | Marquee promo tile (1400×560) |
| Large promo (spare) | `promo-large-920x680.png` | Optional / social |

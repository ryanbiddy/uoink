# Prompt 1 — Project rebrand and repo setup

We are rebranding this project from "yt-extractor" / "YouTube Extractor" to "Yoink" (the product) by ReplayRyan (the personal brand). The product lives at yoink.video. The GitHub repo is at github.com/ryanbiddy/yoink.

**Before running this prompt, replace ryanbiddy above with your actual GitHub username.**

## TASK 1 — RENAME PROJECT EVERYWHERE

Find every occurrence of these strings and replace them. Use a careful search-and-replace; don't blindly rename strings that happen to coincide.

```
"yt-extractor"          -> "yoink"
"YouTube Extractor"     -> "Yoink"
"YouTube Extracts"      -> "Yoink"  (this affects folder paths too)
```

Update at minimum:
- server.py: app name, log file paths, output folder paths, comments
- extension/manifest.json: name, description, short_name
- extension/popup.html: any visible "YouTube Extractor" text
- extension/popup.js: any user-visible strings
- extension/content.js: button label stays "Yoink" (was "Send to Claude" — keep both for now, see Task 4)
- extension/background.js: notification titles
- All README files, status docs, comments, log strings

The output folder on disk MUST change from:
```
%USERPROFILE%\Desktop\YouTube Extracts\
```
to:
```
%USERPROFILE%\Desktop\Yoink\
```

Don't migrate existing folders. New extractions go to the new path. Old folder stays where it is for archive purposes.

## TASK 2 — CREATE THREE CANONICAL DOCS

Create these three files in the project root.

### File 1: README.md

REPLACE any existing README. Use this skeleton, filling in feature list and manual setup details from the existing project state:

```markdown
# Yoink
*The missing layer between YouTube and your AI.*

Yoink any YouTube video into Claude or ChatGPT — full transcript, screenshots, and metadata in one structured doc.

## Why Yoink

You see a video that's clearly working. You want to know why. So you paste the YouTube link into Claude and hope it can "watch" it. It can't. It hallucinates. You give up and watch the whole thing on 2x while taking notes by hand.

Yoink fixes that. Click the button under any YouTube video and you get the full transcript, timestamped screenshots, top comments, channel context, and video metadata — automatically copied to your clipboard, ready for Claude, ChatGPT, or your notes app of choice.

## Features (v1)

- One-click "Yoink" button under every YouTube video
- Right-click any thumbnail to yoink without opening the video
- Full timestamped transcript with chapter awareness
- Timestamped screenshots throughout the video
- Top 50 comments with author and like count
- Full video metadata (views, likes, tags, description, upload date)
- Thumbnail image
- Channel context (subscriber count, recent videos)
- Auto topic-classification into folders on disk
- Editable prompt library for fast follow-up analysis
- Two destination buttons: Send to Claude, Send to ChatGPT
- Local-first, no cloud, no accounts, fully open source

## Install

*One-click installer ships in the v1 launch. Manual setup until then — see [REQUIREMENTS.md](./REQUIREMENTS.md).*

## How it works

1. Click "Yoink" under any YouTube video
2. Yoink extracts transcript, screenshots, comments, metadata
3. Markdown corpus copied to clipboard, opens Claude or ChatGPT
4. Paste, run a prompt, get analysis

## Roadmap

See [BACKLOG.md](./BACKLOG.md) for v2/v3 plans.

## License

MIT. See LICENSE.

---

*Yoink is part of the [ReplayRyan](https://replayryan.com) family of tools.*
```

### File 2: BACKLOG.md

```markdown
# Yoink — Backlog

This is the canonical list of ideas that aren't in the current shipped version. Every entry has a destination, rationale, and trigger condition.

## Format
- **Idea:** one line
- **Destination:** v2 / v3 / never / undecided
- **Rationale:** why it's not v1
- **Trigger:** what has to happen for this to move forward

---

## V2 candidates (build if v1 hits traction signal)

### Channel Decoder
- **Destination:** v2 headline feature
- **Rationale:** requires multi-video corpus mechanics; will be the v2 launch story
- **Trigger:** v1 launch ships and gets qualitative traction signal (unsolicited feature requests, non-friend GitHub stars, organic community posts)

### Niche Corpus mode
- **Destination:** v2 headline feature
- **Rationale:** same as above; co-headline with Channel Decoder
- **Trigger:** same

### Comment intelligence (clustering, themes, mentioned products)
- **Destination:** v2
- **Rationale:** needs AI dependency, breaks local-only purity for free tier
- **Trigger:** v2 build kickoff

### Thumbnail pattern analysis
- **Destination:** v2
- **Rationale:** vision model dependency; better with corpus context
- **Trigger:** v2 build kickoff

### Notion / Obsidian / Google Docs integrations
- **Destination:** v2
- **Rationale:** each integration is 2 weeks of auth + schema + maintenance
- **Trigger:** signal that paste-from-clipboard isn't enough for power users

### Hook taxonomy
- **Destination:** v2 moat-builder
- **Rationale:** builds compounding labeled dataset
- **Trigger:** v2 build kickoff

### Script structure parser
- **Destination:** v2 moat-builder
- **Trigger:** v2 build kickoff

### Bulk and batch operations
- **Destination:** v2 paid-tier feature
- **Trigger:** v2 paid-tier launch

### Mac installer
- **Destination:** v1.5 (between v1 launch and v2 build)
- **Rationale:** doubles QA load; ship Windows first
- **Trigger:** v1 launch ships and runs clean for 2 weeks

---

## V3 candidates (build if Yoink becomes the thing)

### Critique-against-corpus
- **Destination:** v3 headline feature, possibly standalone product
- **Rationale:** requires v2 corpus features to exist. User drops their own video script or rough cut, Yoink compares against high-performing videos in their niche.
- **Trigger:** v2 ships and gets traction

### Lineage detection
- **Destination:** v3
- **Rationale:** novel feature, hard to build well, needs data scale
- **Trigger:** v3 build kickoff

### Hosted version + accounts + payments
- **Destination:** v3
- **Rationale:** breaks local-only, introduces ops overhead
- **Trigger:** paid v2 tier hits $5k MRR

### Leaderboard of most-yoinked videos
- **Destination:** v2 conditional, v3 likely
- **Rationale:** requires hosted layer; network effect potential
- **Trigger:** hosted-layer architecture decision in v2 or v3

### API access
- **Destination:** v3
- **Rationale:** only valuable if other tools want to embed
- **Trigger:** 3+ inbound requests from third parties

### Creator clone mode
- **Destination:** v3
- **Rationale:** ethically gray; needs careful positioning
- **Trigger:** deliberate strategic decision, not feature pull

### Trend detection within saved niches
- **Destination:** v3
- **Trigger:** paid tier exists with saved-niches feature

### Multi-language support
- **Destination:** v2 announcement
- **Rationale:** Whisper handles it natively; market expansion play
- **Trigger:** v2 build kickoff

---

## Likely never (capture so they stop nagging)

### Mobile app with auto-sync
- **Destination:** never
- **Rationale:** 4-month build for a workflow people already do via "text yourself the link"
- **Trigger:** 50+ unsolicited user requests

### Built-in video editor
- **Destination:** never
- **Rationale:** scope creep into a different product category

### Auto-clip generator (shorts/reels)
- **Destination:** never
- **Rationale:** Opus Clip and Submagic own this category and have funding

### Live video monitoring
- **Destination:** never
- **Rationale:** most analysis happens after the fact; live adds infrastructure cost for marginal value
```

### File 3: STYLE.md

```markdown
# Yoink — Style Guide

## Voice — Canonical (polished)

Used in: README, landing page, Chrome Web Store description, About pages, demo video voiceover (mostly), launch blog posts, anywhere a serious researcher, content strategist, or potential acquirer would read.

Characteristics: complete sentences, no slang, no in-jokes, confident but not breathless, technical accuracy, leads with user benefit.

Reference: how Linear writes.

## Voice — Punchy (launch)

Used in: launch tweets, Show HN title and body, X bio, in-product copy (button labels, success notifications, error messages), Discord drops, in-the-moment engagement.

Characteristics: shorter sentences, strong verbs, occasional slang, willing to make jokes, names the pain bluntly, ends with a kick.

Reference: how Pieter Levels writes.

## When in doubt

If you'd say it on a podcast, it's punchy. If you'd put it in a pitch deck, it's polished. If you can't decide, default polished — it's harder to recover from being too casual on a serious surface than from being too serious on a casual surface.
```

## TASK 3 — KEEP "SEND TO CLAUDE" AS BUTTON LABEL FOR NOW

The button under YouTube videos currently says "Send to Claude." We are generalizing this in Prompt 3 to support both Claude and ChatGPT. For this prompt, leave the button label as "Send to Claude" — we'll change it to "Yoink" in Prompt 3.

## TASK 4 — GIT INITIALIZATION

If this folder is not yet a git repo:
- `git init`
- Create a .gitignore that excludes: `node_modules`, `__pycache__`, `*.pyc`, `server.log`, `.env`, `dist/`, `build/`, `*.zip`, the `video.*` temp files yt-dlp creates, and the existing `YouTube Extracts` folder if it's nested in the repo
- `git add .`
- `git commit -m "Initial commit: Yoink v0 (rebranded from yt-extractor)"`
- `git remote add origin https://github.com/ryanbiddy/yoink.git`
- `git push -u origin main`

If this is already a git repo, just commit the rebrand changes:
- `git add .`
- `git commit -m "Rebrand to Yoink"`
- `git push` (or set the remote first if not set)

## WHEN DONE

- Report what files were modified
- Report any references to the old name you found in unexpected places
- Confirm the git push succeeded (or report the error if it failed — auth issues are common on first push)
- Print: `=== PROMPT 1 COMPLETE ===` so the orchestrator knows to advance

The user will then do a quick smoke test:
1. Refresh the extension
2. Click "Send to Claude" on any YouTube video
3. Confirm the new path `%USERPROFILE%\Desktop\Yoink\` is created and populated correctly

# Yoink — Backlog

This is the canonical list of ideas that aren't in the current shipped version. Every entry has a destination, rationale, and trigger condition.

## Format
- **Idea:** one line
- **Destination:** v2 / v3 / v4 / never / undecided
- **Rationale:** why it's not v1
- **Trigger:** what has to happen for this to move forward

---

## V2 candidates (build if v1 hits traction signal)

### Channel Decoder
- **Destination:** v2 headline feature
- **Rationale:** requires multi-video corpus mechanics; v2 launch story headliner
- **Trigger:** v1 launch ships and gets qualitative traction signal (unsolicited feature requests, non-friend GitHub stars, organic community posts)

### Niche Corpus mode
- **Destination:** v2 headline feature
- **Rationale:** co-headliner with Channel Decoder
- **Trigger:** same as Channel Decoder

### YouTube playlist mode (multi-video batch extraction)
- **Destination:** v2 (alongside Channel Decoder and Niche Corpus)
- **Strategic fit:** Very strong. Users already curate playlists for research. Yoink honors that grouping. Manual version of Niche Corpus — user supplies the videos instead of Yoink searching for them.
- **Architecture:** Free. yt-dlp supports playlist URLs natively. `--flat-playlist` returns video list, iterate through each. No new dependencies, no new API costs.
- **User behavior:** Right-click any YouTube playlist URL or playlist page → "Yoink this playlist" → Yoink processes all videos sequentially, writes to session folder named after playlist, outputs individual video corpora plus unified playlist corpus with cross-video summaries.
- **Why v2 vs v3:** Same multi-video corpus mechanics as Channel Decoder and Niche Corpus. Co-shipping reduces v2 build cost relative to standalone effort. Playlist is the most viscerally understandable of the three.
- **v2 headline becomes three modes instead of two:** Channel Decoder, Niche Corpus, Playlist Mode. Cleaner story.
- **Trigger:** v2 build kickoff

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

### Multi-language support
- **Destination:** v2 announcement
- **Rationale:** Whisper handles it natively; market expansion play
- **Trigger:** v2 build kickoff

### First-run onboarding / topic intake form
- **Destination:** v2
- **Rationale:** Asks user about their interests on install, generates a personalized topics.json. Front-loads work currently solved by editing topics.json directly. Worth building once we have user data on which default topics get misclassified most often, what topics users add manually, and whether onboarding completion rates would justify the build. Real intake forms benefit from progressive disclosure ("we'll learn from your first 5 yoinks") rather than asking everything upfront.
- **Trigger:** v2 build kickoff AND signal that default topics.json + manual editing is insufficient (e.g., 5+ users report bad classifications in first week of use)

### Mac installer
- **Destination:** v1.5 (between v1 launch and v2 build)
- **Rationale:** doubles QA load; ship Windows first
- **Trigger:** v1 launch ships and runs clean for 2 weeks

---

## V3 candidates (build if Yoink becomes the thing)

### Critique-against-corpus
- **Destination:** v3 headline feature, possibly standalone product
- **Rationale:** requires v2 corpus features to exist. User drops their own video script or rough cut, Yoink compares against high-performing videos in their niche, surfacing where hook is weak, structure deviates, pacing differs from winners.
- **Trigger:** v2 ships and gets traction

### Lineage detection (idea propagation across niches)
- **Destination:** v3
- **Rationale:** novel feature, hard to build well, needs data scale. Show how an idea originated, scaled, and spread across creators.
- **Trigger:** v3 build kickoff

### Trend detection within saved niches
- **Destination:** v3
- **Rationale:** track topic frequency over time within a niche, surface what's rising/falling. Paid newsletter quality output.
- **Trigger:** paid tier exists with saved-niches feature

### Creator clone mode
- **Destination:** v3
- **Rationale:** ethically gray; needs careful positioning. Extract voice, structure, transitions, opening patterns from a creator's videos into a system prompt.
- **Trigger:** deliberate strategic decision, not feature pull

### Agent-friendly architecture: MCP server
- **Destination:** v3
- **Strategic fit:** Very strong. Probably the most important strategic question for v3. Determines whether Yoink stays an "app users click" or becomes "infrastructure agents call."
- **Why this matters now:** The agent-callable layer of the software stack is forming right now. Anthropic's MCP shipped late 2024. ChatGPT Tasks shipped 2025. Manus and similar autonomous agent frameworks are active. Tools that can't be called by agents become invisible in agent-mediated workflows.
- **What it ships:** Yoink MCP server that Claude Desktop and Claude API can connect to. User configures once, then any Claude conversation can call Yoink: "yoink that video for me" → Claude calls Yoink → corpus returns → analysis inline. No clipboard step.
- **Architecturally low-risk:** Works with existing local-only architecture. Local Python server already 80% of an MCP server. Adding tool definitions is a 1-2 weekend project.
- **Reach constraint:** MCP only works for Claude users on Claude Desktop or via API integrations. Most consumer claude.ai users don't currently have MCP access. Will likely change over time.
- **Three tools to expose:**
  - `yoink_video(url, interval)` — single video, structured corpus return
  - `yoink_channel(channel_url, count)` — Channel Decoder accessible to agents (v2 feature, agent-callable)
  - `yoink_niche(query, count)` — Niche Corpus accessible to agents (v2 feature, agent-callable)
- **Killer use case:** Researcher tells Claude "research the top 30 videos on AI agents from the last 90 days and give me the patterns." Claude calls `yoink_niche`. Yoink builds corpus locally on user's machine. Claude analyzes. User never touches a button.
- **Strategic note:** Don't conflate "agent-friendly" with "hosted." MCP gets you most of the way agent-friendly while staying local. Being early to MCP is a moat. Being late is invisibility.
- **Trigger:** v2 ships AND Channel Decoder + Niche Corpus features stable AND deliberate decision to enter MCP ecosystem

### Yoink integration with Claude/ChatGPT Projects
- **Destination:** v3 (Send to Project shortcut), v4+ (true API sync when available)
- **Strategic fit:** Strong. Projects are where serious AI research happens. Without Project integration, every yoink is ephemeral. With it, Yoink becomes the engine that builds research bases.
- **Technical reality:** Neither Claude nor ChatGPT currently exposes a public API for adding files to Projects from external tools. No OAuth flow, no documented endpoint, no MCP tool. Three workarounds: brittle UI automation (don't), MCP-based future approach (depends on Anthropic shipping API), local Project mirror (manual sync, works today).
- **Project capacity constraint:** Claude Projects (~25 files, ~200K context) and ChatGPT Projects (similar) aren't built for research bases of 50+ corpora. Each yoink is 100KB+. Auto-sync would hit caps within 5-10 yoinks. Right mental model: Projects are curated workspaces, not data lakes. The product feature is "selectively send to Project," not "auto-sync everything."
- **Shippable v3 version:** "Send to Project" button in popup alongside Send to Claude / Send to ChatGPT. User configures Project list, picks one, Yoink opens the Project in browser, user drags the file in. One drag instead of three steps.
- **Multi-Project sync (Claude AND ChatGPT):** Treat Yoink's local folder as source of truth, manual sync to both Projects as needed. Don't be the bidirectional sync layer.
- **Trigger:** v3 build kickoff for the manual "Send to Project" version. Full API sync conditional on Anthropic/OpenAI shipping Project APIs.

### Podcast extraction (Yoink expands beyond video)
- **Destination:** v3 expansion or sibling product under ReplayRyan
- **Strategic fit:** Strong. Same job-to-be-done as YouTube ("structured input from long-form content for AI research"). Same audience (creators, researchers, content strategists). Medium is incidental to the user.
- **Architectural divergence from YouTube:**
  - No equivalent to yt-dlp. Data acquisition fragments across Apple Podcasts (no public API, scrape iTunes Search), Spotify (Web API for metadata, transcripts locked to authenticated users), and RSS (universal substrate for episode metadata, audio URLs, show notes, sometimes chapters; no transcripts).
  - Transcripts require Whisper running on audio files. ~10-15 min compute per hour of audio on local hardware.
  - No comments equivalent. Closest signal is sparse Apple/Spotify reviews.
  - No screenshots — audio-only content. Drop that corpus section or substitute waveforms (low value).
  - Engagement metrics weak. No public view/like/subscriber counts. Download estimates require paid APIs (Chartable, Listen Notes).
- **Corpus shape:** 4-5 sections vs YouTube's 8 (metadata header, full transcript, show notes/description, chapters if present, host context). Thinner output by design.
- **UX implications:** Whisper compute means podcasts take 10-20 min vs YouTube's 30-90 sec. Different user pattern — fire-and-forget background processing with notification on completion. Local Whisper preserves architectural promise; hosted Whisper breaks it (~$0.01/min compute).
- **Competitive landscape:** No direct competitor doing "structured podcast corpus → paste into your AI tool." Snipd, Podscribe, Listen Notes, Castmagic all serve adjacent but different jobs.
- **Branding decision (deferred):** Either expand Yoink to cover podcasts (risk: dilutes "missing layer between YouTube and your AI" positioning) or sibling product under ReplayRyan family with shared infrastructure (risk: doubles maintenance load). Default lean: same audience suggests one product, but require user signal before committing.
- **Trigger:** v2 ships and gets clear traction AND deliberate decision to expand product surface AND user demand from existing Yoink users (vs speculative)
- **Don't launch alongside v2** — would dilute v2's Channel Decoder + Niche Corpus story.

### Strategic ranking: agent-friendly vs podcasts for v3
- Agent-friendly is the higher-leverage v3 bet. Category-positioning play. Compounds harder.
- Podcasts is a market-expansion play. Real value but slower compounding.
- If only one ships in v3: MCP server first.
- Both are independent decisions — could ship either, both, or neither.

---

## V4+ candidates

### Hosted version + accounts + payments
- **Destination:** v4
- **Rationale:** breaks local-only differentiation, introduces ops overhead. Right move only when paid v2 tier hits clear revenue floor.
- **Trigger:** paid v2 tier hits $5k MRR

### Public HTTPS API (Yoink-as-a-service)
- **Destination:** v4 or never
- **Rationale:** Exposes yoink-as-a-service with public endpoints other developers can call. Unlocks: tools building on Yoink, custom engineering agents, ChatGPT Custom GPTs with Actions, IFTTT/Zapier-style automation. Requires hosted infrastructure (auth, rate limiting, abuse handling, operational availability). 4-6 week build minimum + ongoing ops cost. Breaks local-only promise.
- **Trigger:** v4 hosted architecture decision AND 3+ unsolicited requests from third parties wanting to embed Yoink

### Leaderboard of most-yoinked videos
- **Destination:** v4 conditional
- **Rationale:** requires hosted layer; network effect potential. Most-yoinked videos in a category becomes a discovery surface and a reason to install.
- **Trigger:** hosted-layer architecture decision in v4

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

### Twitter/X content extraction
- **Destination:** likely never; possibly sibling product under ReplayRyan
- **Strategic fit:** Weak as Yoink feature. Different research workflow (real-time monitoring vs corpus research), different audience time investment, hostile platform.
- **Architectural barriers:** X API is $200/mo minimum (kills free positioning), scraping violates ToS and is fragile, manual paste defeats one-click value. Twitter bookmarks are not exposed via API at all — only UI scraping path.
- **Existing competition:** Sprout Social, Brandwatch, Tweet Hunter, Hypefury all serve adjacent jobs. None are AI-corpus tools, but the audience for "structured tweet input for my AI" is much smaller than YouTube's equivalent.
- **Trigger:** X API economics or ToS landscape changes meaningfully (unlikely under current ownership), AND clear competitor demonstrates the demand.

### In-page button chooser (Claude vs ChatGPT before yoink)
- **Destination:** v1.5 if user research demands, otherwise never
- **Rationale:** Adding a chooser to the in-page button slows the most-used path. The popup destinations exist for users who care about which AI to send to. Default flow stays one-click. Worth revisiting if usage data shows users consistently want destination control upfront.
- **Trigger:** 5+ unsolicited user requests for click-time destination choice, OR usage data showing the popup destinations are heavily used over the in-page button

### Folder-mirrored Projects (yoink topic folders → Claude/ChatGPT Projects auto-sync)
- **Destination:** never as designed; superseded by "Send to Project" in v3 candidates
- **Rationale:** Claude and ChatGPT Projects have hard file count and context limits (~25 files, ~200K context). Yoinks can be 100KB+ each. Auto-stuffing topic folders into Projects would hit limits fast and silently drop content. Also defeats Projects' value as curated workspaces. The viable version (selective "send to Project") is captured in v3 candidates.
- **Trigger:** never (this specific design)
### Multi-platform video extraction (beyond YouTube)
- **Destination:** v3 (after YouTube depth is established)
- **Strategic fit:** Real but risks diluting the core positioning. yt-dlp supports 1,800+ sites � extraction layer is largely solved. The hard part is corpus quality across platforms (comments, creator context, engagement metrics differ wildly per platform).
- **Three viable paths if pursued:**
  1. **Targeted expansion** (preferred): Pick 2-3 high-value platforms with their own corpus extractors. Most likely candidates: Vimeo (professional creators, similar architecture to YouTube), Twitch VODs (different audience, same job), TED/conference talks (defined audience, valuable corpus).
  2. **Generic "any video URL" mode** (degraded): Lowest-common-denominator corpus across all yt-dlp-supported sites � transcript, screenshots, basic metadata only. No comments, no creator context. Fast to build but dilutes corpus quality, may confuse users about what Yoink actually delivers.
  3. **Vertical platforms** (different product surface): Podcast extraction is already a separate v3 backlog item. Treat each major content type as its own product effort, not a feature toggle.
- **Why deferred to v3:**
  - Corpus density is Yoink's moat. Diluting across platforms erodes the differentiation that makes it valuable.
  - YouTube alone is enormous (2.5B users) and where Yoink's target audience does video research.
  - Multi-platform support multiplies maintenance burden � each extractor breaks independently when its platform changes.
  - Strategic clarity matters for launch. "Yoink for YouTube research" is sharper positioning than "Yoink for video, sort of, depending on the site."
- **Trigger:** v2 ships and YouTube depth (Channel Decoder, Niche Corpus, Playlist mode) is stable AND clear user demand for specific platforms (10+ unsolicited requests for the same platform)
- **Marketing hint for v1:** Optionally include a small "Podcast support and other platforms on the roadmap" line on the landing page or FAQ to signal ambition without overpromising

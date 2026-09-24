# The Living Library: what uoink becomes

**Date:** 2026-09-04 · **Author:** Fable (orchestrator) · **Status:** direction + build path, unratified. Nothing built, nothing published, nothing spent.
**Origin:** Ryan's reframe of Morgan's idea (2026-09-04): not a question-jury, but resident agents that keep the library growing, re-shelve it as ideas change, spot patterns, remind you what you have, and make the corpus the thing every model consults.

**Inputs integrated**
1. Control Room round 2, run 073b6589: Codex, Grok, Claude Opus, **Gemini 3.8 Flash** sealed packets + Opus synthesis, 21 min, read-only (`CONTROL-ROOM-RUN-073b6589-2026-09-04.md`, `SYNTHESIS-OPUS-RUN-073b6589-2026-09-04.md`)
2. `LANDSCAPE-MEMO-2026-09-04.md`: 30+ products on five axes, Sep 2026, URLs
3. `METHODS-MEMO-2026-09-04.md`: taxonomy, memory, trend, recall, media-ingestion and local-model methods with numbers, 111 sources
4. `GAP-MAP-2026-09-04.md`: what 3.8.0 has, partial, missing, file:line
5. Round 1 (`FINDINGS-2026-09-04.md`), the agentic audit (`handoff/agentic-2026-09/`), Ryan's Hermes research (HQ, 2026-08-23)
6. My own verification against the live index `%LOCALAPPDATA%\Uoink\index.db` and the checkout

---

## 0. The answer on one screen

**Yes to the library. No to the picture of four thinking agents living inside the app.** The agents are real, but they split in two:

- **Watchers are dumb and live in uoink.** Polling, fetching, transcribing. No model needed. They already half-exist (podcast scheduler, 30-second tick, per-feed opt-in).
- **The Librarian, the Analyst and Recall are jobs uoink prepares and any model runs.** uoink assembles the evidence and a work queue; Claude Code routines, Hermes cron, Gemini scheduled actions, Codex, or a local model claim the work and hand results back. That keeps the locked "server does no inference" rule, keeps corpus text off vendors you didn't choose, and means the same library serves every model you have. All four engines landed here independently.

**The finding that reorders everything:** uoink already holds **143,997 timestamped, deep-linked citations** (129,832 transcript chunks + 14,165 screenshots) across 515 of 537 items, and **none of them are searchable**. Search runs at item level only. The media differentiator every engine proposed building is already on disk, un-indexed. The first sprint is not watchers and not a taxonomy engine. It is making the clip layer retrievable, which is also the cheap evidence substrate the Librarian, Recall and the Analyst all consume.

**Positioning line (Grok's, adopted):** *The local library for the videos and podcasts you study. Watchers pull new episodes. The Librarian shelves them. Any model you use can look them up.*

**Two things gate all of it:** the helper still dies silently (down ~20 h on Sep 3 with health reporting OK), and half the corpus has no topic with no code path that could ever change that.

---

## 1. Ryan's spitball, organized

| What Ryan said | What it is | Name | Where it lands |
|---|---|---|---|
| "Specialized agents deploy and research specific topics... things start yoinking things for you" · Morgan's Bible YouTuber, every new video captured | Standing capture from subscribed sources | **Watchers** | Phase 3, in-process, no LLM, opt-in per source |
| "One specialized agent that's just about topics... is 'loop engineering' a new term? Reassess the entire corpus... Dewey Decimal system" | Continuous hierarchical classification that re-shelves the back catalog when a concept emerges | **The Librarian** | Phase 2, client-run over a work queue, over evidence cards |
| "Another agent is just looking through trends and patterns and pulling out insights" | Statistics over shelves and time, narrated on trigger | **The Analyst** | Phase 5, after claims are populated |
| "I forget that I yoinked something about X... it would be great if uoink could remind me... be part of a council and consult" | Proactive resurfacing at the moment of relevance; a seat at the table | **Recall** | Phase 4, via client hooks and MCP resources; the round-1 council becomes a Recall seat |
| "This history is backed up automatically to all of their LLMs... MD file or whatever... 'I want to tweet about X' → it looks through uoink" | The corpus as every model's context layer | **Reachability** | Phase 4: MCP dual-era + Obsidian/Basic Memory mirror + client configs. Ruling: *queried by* every model, never *copied into* vendor memory |
| "Super specialized in organizing and dissecting the content media scene... podcasts, YouTube, Twitch, from humans" | Clip-grained, speaker-aware, timestamped media corpus | **Media depth** | Phase 1 (clip index) now, Phase 6 (chapters, speakers, Twitch) later |
| "Feels like I have a bunch of Yoinks" | The experience the above adds up to | **The library** | The whole thesis |
| "GPT-6 Astra just dropped... how do we uplevel uoink and make it big" | Repositioning after autonomous frontier agents | §2, §9 | Astra makes reachability table stakes; it does not build the library |

The Bible example, walked through: Morgan subscribes to the channel (Watcher: RSS detects the upload, fetches captions, transcribes if needed). The Librarian files it under Scripture → New Testament → Parables, and its inclusion cues also match "money" and "work", so it lands on those shelves too. A month later, ten videos mention "stewardship"; the Librarian proposes a new shelf, re-checks every older summary against it, and moves four videos from 2024 onto it. The Analyst notices "stewardship" burst across three creators this month. When Morgan opens Claude and types "help me think about tithing", Recall says: you have 6 clips on this, here are the three most-cited, with timestamps.

Ryan's own example: "loop engineering" is a real term, coined by Addy Osmani on **June 7, 2026** (O'Reilly republished it June 22). The Librarian's job is exactly to notice that burst and re-check the "AI and ML" pile (198 items) for older videos that were about it before the word existed.

---

## 2. What changed since uoink was built (September 2026)

| Change | Fact | What it means for uoink |
|---|---|---|
| **GPT-6 Astra** rolled out Sep 3 (public Sep 5) | 1.05M context, 128K out, tools include `mcp`, computer use, API $10/$50 per M. An action model. Nothing in its coverage subscribes to a source or builds a corpus. | The reader and the clock are commodities. A big window is worthless without something good to put in it. Reachability over MCP is now table stakes |
| **ChatGPT Pulse retired** June 17 | Replaced by scheduled tasks + web-monitoring tasks (Plus 5, Pro 15) | Proactive briefs are a prompt now; the corpus underneath is not |
| **NotebookLM → Gemini Notebook** July 16 | 30M+ users, 600K orgs; YouTube captions since 2024; Discover/Deep Research find sources once; no standing subscription; sources don't refresh; no consumer API/MCP | The default "chat with my saved videos" is Google's. uoink must win on *standing capture + re-shelving + open serving*, not on chat |
| **Claude routines** (Apr 14) and **Cowork scheduled tasks** | Cloud routines: Pro 5/day, Max 15. Cowork tasks that need local files run only locally and "can't be tied to a folder" | A client-side scheduler exists for the Librarian. Local files still need something local |
| **Hermes Agent** (Nous) | 241K stars; memory is two ~2KB files; eight memory providers, none a media library; cron built in | Hermes is a runtime for uoink's jobs and a distribution channel: be the memory provider that holds other people's videos |
| **MCP 2026-07-28 revision** is final | Stateless; no `initialize`; `subscriptions/listen` replaces push; sampling/roots/logging deprecated. uoink pins `mcp==1.27.1`, speaks 2025-11-25, exposes tools only | Unsolicited push is gone. Recall rides a client hook. Dual-era MCP is a build |
| **"Loop engineering"** | Real: Osmani June 7, 2026. Five moves: discovery, handoff, verification, persistence, scheduling | uoink can *be* the persistence-and-scheduling loop for personal media and own the vocabulary early |
| **Consumer local-first PKM graveyard** | Reor archived Mar 2026; Khoj Cloud sunset Apr 2026 ("cloud-first... six clients... difficult to scale in utility"); survivors are $4–15/mo | Stay narrow. Media only. One helper, one library, every client |

---

## 3. The gap, honestly

**Where nobody plays** (from 30+ products scored on five axes):
1. Nobody watches a channel, podcast or streamer *into a user-owned corpus*. ChatGPT and Gemini monitor "the web"; Notebook discovers once; Karakeep's RSS stores pages, not understanding.
2. Nobody re-shelves. Every tool is flat tags or a graph. Only Letta's "Dreaming" restructures hierarchy, and that is agent memory, not a library.
3. Nobody runs an analyst across *your* subtopics; Deep Research runs on the open web.
4. Recall everywhere is quiz-shaped (Readwise, Recall, Snipd). Nobody says "you already saved 4 things about this" at the moment you start writing.
5. Spoken media is second-class everywhere except Snipd, and Snipd has no MCP. Transcripts with speakers, timestamps and chapters served over MCP to any model is unclaimed.
6. Local Windows is empty ground, and nobody serves Hermes agents a media library.

**The honest counter-case** (three engines said it unprompted):
- Astra + a markdown folder + Claude routines is roughly 70% of this for a user who already captures.
- If Watchers stay ToS-fragile and classification stays keywords, uoink is a worse Recall with a Windows helper that dies overnight.
- If YouTube or Spotify build native listener-side libraries, standalone capture retreats to a privacy niche.

**The thesis that survives both:** frontier memory remembers *you*. It does not stand up a durable, clip-addressable index of *other people's* long-form audio and video on your disk, keep pulling new episodes as they publish, re-file them when the ideas change, and serve the same cited corpus to Claude, Codex, ChatGPT, Hermes and a local model alike. That intersection is the product. The moat is thin against Recall + Snipd + Readwise combined unless clip-grained cited retrieval across *recurring* sources is visibly better than any of them. Phase 1 is the test.

---

## 4. What uoink actually has today (live index, verified 2026-09-04)

| Fact | Number | Consequence |
|---|---|---|
| Timestamped citations with deep links | **143,997** (129,832 transcript chunks, 14,165 screenshots) across 515/537 items | The media differentiator exists and is unsearchable (FTS is item-level only) |
| Average transcript chunk | 37 chars, overlapping caption cues | Index *merged windows* (30–120 s), not raw cues, or hits will be noise |
| Items with no `source_type` | 461/537 (86%) | Provenance repair before any shelving |
| Uncategorized | 278/537; AI and ML 198; career 4; tools 1 | Topic is a keyword match run once at capture; no code path ever revisits a row |
| `claims` table rows | 0 | Every contradiction-detection design is on an empty table; populate before analyzing |
| Stranded podcast episodes | 147 at `status=new`, `auto_ingest_requested=0`, all three feeds off | Flag frozen at insert and ANDed with the feed flag: flipping the switch yields zero. Data repair |
| Playlist watcher | interval persisted, **no thread polls it** | Only podcasts have a real scheduler |
| Helper liveness | down ~20 h on Sep 3; `main()` exits 0 on bind failure; `--doctor` exits 0; `/health` ok | Audit P0 N3. A library that files itself while dead files nothing |
| MCP | 23 stdio / 65 registry tools; protocol 2025-11-25; **no resources, no prompts, no sampling** | Every Recall-over-resources design is a build, not config |
| D-17 ("server never calls an LLM") | Already moved: 3 of 4 Anthropic callers are server-initiated background jobs; entity extraction gated by key presence alone; `usage` never read | Re-state D-17 honestly and close the flag gap; bulk classification is unimplemented (HTTP 501), not forbidden |
| Chapters | Markdown headings only, zero schema | Not queryable yet |
| Diarization | Ships (WhisperX + pyannote community-1), opt-in, off by default, labels never reach the markdown | Media depth is closer than it looks |

---

## 5. The architecture

```
Sources ──► Watchers (in-process, NO LLM)            RSS/feed poll, dedupe, fetch, WhisperX
              │                                      supervised · opt-in per source · default off
              ▼
         Corpus on disk (markdown + JSON sidecars)   canonical, model-independent
              │
         SQLite: yoinks · clips(+fts) · shelves      rebuildable derivative
              │                                      ★ clip-grained retrieval (the wedge)
              ▼
         library_work queue (leases, retries)        uoink offers work; never performs inference
              │
    ┌─────────┴──────────────┐
    ▼                        ▼
Client agents            (later, optional) local worker
Claude Code routines ·   LM Studio resident model
Hermes cron · Gemini     for summaries + assignment
scheduled actions ·
Codex
    │  claim → bounded evidence packet → structured result
    └─► Librarian (shelve) · Analyst (deltas) · Recall (rank)

Reachability: MCP (dual-era) · Obsidian/Basic Memory mirror · client configs for every model
```

**Principles (unanimous across four engines):**
1. Compute policy = option (iii): agents run in the user's client on a schedule; uoink exposes tools plus a durable work queue. D-17 survives, **re-stated**: *the server performs no LLM reasoning on the user's behalf except through named, default-off, metered feature flags; all agent cognition happens in the calling client.* Then close the gap: put entity extraction behind a named flag like the other two jobs, and read the `usage` field.
2. Watchers are carved out as non-LLM in-process work. Detection (channel RSS) and capture (yt-dlp) are separate permission questions.
3. "Backed up to all your LLMs" means *queried by* all of them, never *copied into* vendor memory. Markdown on disk is canonical; SQLite is a rebuildable derivative; the vault mirror is a mirror.
4. Every watcher defaults to off, per source, mirroring `podcast_feeds.auto_ingest`.
5. TnT-LLM-shaped taxonomy (induce rarely on a sample, assign cheaply in bulk) over GraphRAG or a temporal graph at this scale.
6. User corrections are immutable. The Librarian never moves a pinned item.
7. The Analyst detects with statistics and narrates with an LLM, never the reverse.

**The one disagreement evidence cannot settle:** if the Librarian only runs when a client runs, a GUI-only user's library never organizes itself. Gemini wants a local small-model daemon as fallback; Grok calls the same hole "a hidden product dependency I did not price." That is a product-scope question (who is the user?) and it is Ryan's decision #2.

---

## 6. The agents, designed

### Watchers
- **Detector:** YouTube channel RSS (`youtube.com/feeds/videos.xml?channel_id=UC…`, 15 latest, verified live), podcast RSS (exists), playlists (schema exists, needs the thread). Twitch: EventSub `stream.online` needs no user auth; VODs expire in 7–60 days; ToS bans scraping → **notify-only**. X: no server-side watcher (Nitter dead, capture already truncates at 280 chars) → **deferred**.
- **Capture:** captions via yt-dlp from a home residential IP at low rate (cloud IPs are blocked; PO tokens ~12 h; ~300 videos/hour guest limit). Only ~3% of podcast episodes ship transcripts, so local ASR (WhisperX, or Parakeet TDT at RTFx 3,333) is the default.
- **Rules:** per-source opt-in, default off; back-catalog cap and daily ingest cap; visible watcher health; no "go deeper" in v0. Generalize `podcast_feeds` + `monitored_playlists` into one `source_subscriptions` registry on the existing 30-second tick.
- **Prerequisite:** helper watchdog (Scheduled Task restart-on-failure), non-zero exit on bind failure, `--doctor` exit 1.

### The Librarian
- **Substrate:** *evidence cards* (about ten citation snippets + a 300–500-token structured summary per item), never raw transcripts. That is why Phase 1 comes first.
- **Shelves:** 3-level paths with per-node definition, inclusion cues and exclusion cues (EvoTaxo's concept memory bank), versioned. Items can sit on several shelves (Morgan's "this is about jobs, this is about money").
- **Loop:** nightly, assign new summaries with confidence + evidence quote; queue anything under 0.6 or with no fitting leaf as `unmapped`. Structural triggers: ≥10 unmapped, a leaf over 40 items, a term burst absent from node cues, or a user correction → a taxonomy-update prompt (cloud Sonnet-class, batch) proposes rename/merge/split/add on a **new version**. On any structural change, **re-classify every summary** against the new version (the part no published system does; it is ours to write).
- **Stability:** new shelves stay hidden until they hold ≥5 items across two passes; merges need cue overlap plus a dedup vote; keep prior versions; alert if churn exceeds 15%.
- **Human loop:** corrections immutable, injected as few-shot examples into node cues, excluded from re-shelving.
- **Cost (arithmetic, gated on measurement):** summary re-shelve ≈ $1 per 500 items on Haiku, $4–10 per 5,000; full-text would be $8–80. Local 27B: only viable *resident* (Q3/IQ4_XS, or the 35B-A3B MoE); the current Q4_K_M spills 10–15 layers to CPU, which is the 7–22 tok/s regime and makes full-text passes take days. Resident summary-based: 500 items ≈ 1.5 h.
- **Evaluation:** a stratified 60–100 item human-labelled gold set (Uncategorized, AI/ML, podcasts, non-YouTube); hierarchical F1, churn, unmapped rate, monthly spot-check with kappa. Nobody has measured local assignment quality; that is a gate, not an assumption.

### The Analyst
- **Stats first:** Kleinberg burst detection on weekly bins, document-level presence, entity-normalized terms; week-over-week deltas per shelf. Snapchat's 2026 production trend system (LLM phrases → burst lift → LLM canonicalize; 92.8% precision) is the template.
- **Claims:** populate the empty `claims` table first (Claimify-style: select → disambiguate → decompose, with timestamps). Contradictions: always ask for *disagreeing sentence pairs*, never yes/no (GPT-4 recall 8% on yes/no vs 70% evidence hit-rate on pairs).
- **Slop control:** a "trend" needs ≥3 items from ≥2–3 distinct creators or it is labelled a single-source signal; faithfulness ≥0.9 on a sample before anything is shown.

### Recall
- **At the moment of writing:** a Claude Code `UserPromptSubmit`/`SessionStart` hook runs clip search on the prompt and returns `additionalContext` with 3–5 related clips ("you have 6 yoinks about X"). This is the cleanest path the current MCP era allows.
- **Every client:** MCP `resources` and `prompts` (a build; they don't exist), a `SKILL.md` consult rule ("before topical answers, search the library"), a daily brief as one markdown file, and the Obsidian/Basic Memory mirror extended from TASTE/USER to the corpus (Ryan's Hermes setup already treats a Basic Memory vault as universal memory).
- **Daily pick:** Readwise-style: half never-resurfaced, half decayed-interest (the 30-day engagement half-life already exists).
- **The council seat:** round 1's finding stands. A council is a Recall seat over the library, not a product.

---

## 7. What it costs and what runs where

| Job | Where | Estimate | Note |
|---|---|---|---|
| Watch, fetch, transcribe | uoink helper, local | $0 | WhisperX ~70× realtime; diarization opt-in |
| One-time summaries, 537 items | local resident model (~30 s/item) or Haiku batch ≈ $3 | hours local / $3 cloud | prerequisite for cards |
| Nightly assignment of new items | local resident or Haiku | cents | grammar-constrained JSON, non-thinking |
| Taxonomy revision | cloud Sonnet-class, batch | dollars, rare | the frontier-model step every paper needed |
| Full re-shelve over summaries | Haiku batch ≈ $1 / 500 items; local ≈ 1.5 h | | on structural change only |
| Weekly Analyst | local stats + one cloud narration | cents | |
| Steady state at 5,000 items | | **< $15/month cloud** | all arithmetic; gate G4 replaces it with a measured run |

Hardcoded Haiku pricing in `server.py` was verified 2026-05-12 and is stale. Live Anthropic list (2026-09-04): Haiku 4.5 $1/$5, Sonnet 4.6 $3/$15, Sonnet 5 $2/$10 per MTok; batch 50%; cache read 0.1×.

---

## 8. The build path

Ordered. Each gate passes before the next phase starts. Phase 0 runs alongside Phase 1.

**Phase 0 — the library must be true** (prerequisite, not a feature). Helper watchdog + non-zero exit + `--doctor` exit 1 (N3). Backfill `source_type` for 461 items. Repair the 147 stranded episodes. Register `uoink_url` / notes / X capture on the tool registry (N2). Ship `uoink.cmd` (N1). Fix X truncation (N4). *Proves:* the helper's death is visible and every item knows what it is.

**Phase 1 — index the clip layer** ★ the first two-week sprint. *Proves:* uoink answers "who said X, when, with a link" across 515 items, zero egress, zero new dependencies.

**Phase 2 — Librarian substrate.** `shelves` / `shelf_versions` / `item_shelves` (evidence, confidence, version, lock) + `library_work` queue (leases, retries, idempotent results) + registry tools `list_library_work`, `claim_library_work`, `submit_library_result`, `apply_reshelving`, `pin_shelf`; the gold set; a **dry run over all 537 applying nothing**; a client skill that runs the loop nightly. *Proves:* re-shelving is reversible, evidenced and cheap, measured.

**Phase 3 — Watcher v0.** `source_subscriptions` registry; YouTube channel RSS on the 30-second tick; per-source `auto_ingest` default off; back-catalog cap; watcher health in the Sources tab. *Proves:* a new upload on an opted-in channel lands, shelved, without a click.

**Phase 4 — Recall + reachability.** MCP `resources` + `prompts`; `UserPromptSubmit` hook; SKILL.md rewrite (currently stale, still says "YouTube creator research analyst" and demands an API key); daily brief file; Obsidian/Basic Memory mirror of the corpus; client configs for Claude Code, Codex, Gemini, Windsurf, Hermes; then dual-era MCP (rewrite off FastMCP, `server/discover`, `ttlMs`). *Proves:* every model Ryan uses reaches the same corpus.

**Phase 5 — Analyst.** Populate claims, bursts over shelves, week-over-week deltas, cross-creator contradiction pairs, LLM narration on trigger.

**Phase 6 — media depth.** Chapter rows, speaker labels into markdown and clips, cross-video speaker identity, cited clip-range export, Twitch notify-only. X watching deferred until a compliant path exists.

### The first sprint, specified

Chosen because it is pure upside: no egress, no new dependency, no ToS exposure, no policy question, and it is the substrate Phases 2, 4 and 5 consume.

1. **Migration `0024_clips.sql`:** a `clips` table derived from `citations` by merging consecutive `transcript_chunk` cues into 30–120 s windows on sentence boundaries, snapped to yt-dlp chapters when present, carrying `{video_id, start, end, text, speaker (null for now), source_deep_link}`; plus `clips_fts` (FTS5, external content) with triggers. Backfill is idempotent (`citations` has `UNIQUE (video_id, kind, seq)`); `--rebuild-index` reproduces it from disk.
2. **`index.search_clips`** returning `{video_id, slug, title, start, end, text, source_deep_link}`; `source_deep_link` is already source-neutral so podcasts and YouTube behave identically.
3. **bm25 column weights** on the existing item-level `yoinks_fts` (title and channel currently rank the same as body).
4. **Registry-first MCP tool `search_clips`** (HTTP/OpenAPI registry, not stdio, to avoid the 23-tool CI lock-step).
5. **Evidence-card generator:** N clip snippets + metadata per item; the Librarian's input.
6. **One measured classification pass** over the live 537 using cards, cost and quality published, **no labels applied**.

**Gates:** G0 clean upgrade from a populated fixture, idempotent migration, rebuild reproduces `clips_fts` · G1 clip search returns a correct deep link for a YouTube item *and* a podcast item; 515 covered; the 22 without citations reported, not dropped · G2 bm25 weighting beats the unweighted baseline on a 20-query hand-scored set, else revert · G3 zero new network calls, no LLM SDK import in new modules, stdio JSON-clean, HTTP/stdio parity · G4 measured cost of one full evidence-card pass within 2× of any estimate before a single label is applied.

---

## 9. Positioning and becoming big

- **User:** Morgan-class *followers of humans who publish audio and video* who follow 20–100 recurring long-form sources and need evidence from them (researchers, serious hobbyists, creator-researchers, analysts). Not "everyone with bookmarks." Not generic PKM.
- **Pitch:** *The local library for the videos and podcasts you study. Watchers pull new episodes. The Librarian shelves them. Any model you use can look them up.*
- **Wedge:** standing spoken-media capture + clip-grained cited retrieval + a local MCP server every model consults. Recall is the cloud twin. NotebookLM is a 50-source project. Snipd is a player. Karakeep is links.
- **Distribution:** GitHub + `.mcpb` + the MCP Registry (`server.json` still missing, audit N18) + Chrome Web Store once watchers work; **a Hermes memory provider** (241K-star runtime, no media library among its eight providers); **a Readwise-style official ChatGPT app / Claude connector** once resources exist; the Obsidian community via the vault mirror; creator communities via a five-source onboarding challenge that produces a useful weekly brief; own the "loop engineering for your library" language while it is fresh.
- **Free vs paid:** the library and BYO inference are free and open source. Do not meter the library. The only credible paid line anyone proposed: **managed encrypted sync, mobile delivery, watcher uptime, compute bookkeeping at $12–15/month**, priced against Recall's $10 Plus.
- **Suite:** uoink = library, keep and expand. Writing Studio, scripts, critique and Voice DNA leave uoink for Writer (they are still live in the checkout; freeze growth now). Zing stays a sibling consumer. Hub stays dormant and may not spend. "For You as home" dies; Library is home.
- **Comps (traction):** Gemini Notebook 30M users; Hermes 241K stars; Fabric 43.8K; Khoj 37.1K (cloud dead); Karakeep 28.8K ($4/mo cloud); Letta 24.6K; Recall 500–700K users (vendor-claimed); Snipd "hundreds of thousands" at $6.99; Readwise 27 staff, bootstrapped.

---

## 10. Decisions only Ryan can make

1. **The wedge.** Recurring-source follower (Morgan), creator-operator, or researcher/analyst. Distribution differs per answer.
2. **The GUI-only user.** Accept that the Librarian only runs when a client runs (pure option iii), or fund an optional local small-model daemon as fallback. The one architectural disagreement evidence cannot settle.
3. **D-17's re-ratified wording**, and whether entity extraction gets a named feature flag like the other two background jobs.
4. **yt-dlp posture:** status quo capture, or RSS detection + creator-uploaded captions only. Detection and capture are separable; this decides only capture.
5. **Watcher consent defaults** and the per-channel back-catalog / daily ingest cap.
6. **Suite removals:** confirm Writing Studio / Voice DNA leave uoink; zing sibling; hub dormant; For-You demoted.
7. **Encrypted sync in or out of scope.** It is the only paid line.
8. **Priority against the P1 integration queue** (49 unmerged drafts per the suite status doc; not re-verified in either round).
9. **Twitch notify-only and X deferred:** confirm.

---

## 11. If Ryan says go: the first dispatch

Non-overlapping, one contract owner per surface, all gated on the decisions above. Nothing is authorized yet.

- **Codex:** the Phase 1 sprint end to end (migration, merged windows, `search_clips`, bm25 weights, cards, gates G0–G3) and the *shape* of the Phase 2 tables so nothing else collides.
- **Grok:** the platform-policy memo behind decisions 4, 5 and 9 with current ToS citations; the **measured** cost model for G4 against the live 537; refresh the stale Haiku pricing.
- **Gemini:** the stratified gold set; TnT-LLM induction/assignment prompt specs that run against evidence cards; benchmark local assignment quality on 16 GB and publish the numbers nobody has.
- **Claude:** D-17's re-ratified wording and the work-queue contract; scope the MCP resources/prompts build and the Obsidian mirror extension; adjudicate the Phase 2 tables and tool registry; write the decision memo.
- **Phase 0 repairs** (watchdog, source_type backfill, stranded episodes, registry parity, CLI) run in parallel with a single owner (Codex or Fable), because they are bug fixes with known files, not design.

---

## 12. Lessons from this run

- Both rounds' engines read the checkout and missed the live index. The 143,997-citation finding, the 0-row claims table and the 147 stranded episodes all came from querying the user's database. **Ground truth for a personal-corpus feature is the user's data, not the repo.**
- Gemini 3.8 Flash sealed in 3.5 minutes and made four factual errors the lead caught (chapters "shipped", claims "usable", MCP "conforms to 2026-07-28", wrong Recall). Speed is not evidence; the sealed-packet-plus-verification pattern is what made it safe to use.
- Every cost figure from every source is arithmetic. G4 exists to replace all of them with one measured number.

## Files in `handoff\council\`

- `THE-LIVING-LIBRARY-2026-09-04.md` — this document
- `LIBRARY-THESIS-BRIEF-2026-09-04.md` — the round-2 brief (Ryan's spitball organized + nine questions)
- `SYNTHESIS-OPUS-RUN-073b6589-2026-09-04.md` — the lead synthesis with 12 rulings
- `CONTROL-ROOM-RUN-073b6589-2026-09-04.md` — all four round-2 packets + synthesis
- `LANDSCAPE-MEMO-2026-09-04.md`, `METHODS-MEMO-2026-09-04.md`, `GAP-MAP-2026-09-04.md` — the research base
- Round 1: `FINDINGS-2026-09-04.md`, `CONTROL-ROOM-RUN-294631ce-2026-09-03.md`, `RESEARCH-MEMO-2026-09-03.md`, `ARCH-BRIEF-2026-09-03.md`, `COUNCIL-RESEARCH-BRIEF-2026-09-03.md`

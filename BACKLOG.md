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

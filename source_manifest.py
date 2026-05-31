"""Machine-readable product manifests for the v3.2.1 site + dashboard.

Backs three endpoints (POSITIONING-LOCK-V3.3.md Sections 2-3):
- GET /sources/manifest    -> the category shelf (the visual home for "any
                              source", Claude Design Phase 5)
- GET /creators/manifest   -> the creator audience door (capture -> library ->
                              writing studio -> voice DNA -> attribution)
- GET /developers/manifest -> the developer audience door (MCP + OpenAPI +
                              copy-config)

Pure data. No DB, no network. The site (static export) can bake these at
build time; the dashboard Sources tab reads them live. Status values are the
single source of truth for "shipped / in-flight / planned" so the site and
dashboard never drift from each other.

Voice DNA applies to every string here (user-visible). No em dashes, plain
language, specifics over adjectives.
"""
from __future__ import annotations

# Status vocabulary. Keep these three exact tokens; the UI maps them to chips.
SHIPPED = "shipped"
IN_FLIGHT = "in-flight"
PLANNED = "planned"

# One row per source. `lands` = what ends up in the local corpus; `best_for`
# = the output it feeds; `slug` = the /sources/<slug> + /features route stem.
_SOURCES: list[dict] = [
    {
        "slug": "youtube", "name": "YouTube", "category": "video", "status": SHIPPED,
        "capture": "Click the rust U under any video, or right-click a link.",
        "lands": "Transcript, screenshots on an interval, comments, channel context.",
        "best_for": "Studying a channel, grounding a script or thread.",
    },
    {
        "slug": "twitter", "name": "X video", "category": "video", "status": SHIPPED,
        "capture": "Right-click an X video, or paste the post URL.",
        "lands": "Transcript and creator citation for the clip.",
        "best_for": "Citing a clip in a credited thread.",
    },
    {
        "slug": "podcasts", "name": "Podcasts", "category": "audio", "status": SHIPPED,
        "capture": "Add an RSS feed; episodes transcribe on demand.",
        "lands": "Speaker-labeled transcript (WhisperX diarization), episode metadata.",
        "best_for": "Pulling a quote from a long interview.",
    },
    {
        "slug": "web", "name": "Web pages", "category": "text", "status": SHIPPED,
        "capture": "Allowlist a site, then uoink any page on it.",
        "lands": "Clean reader text in markdown, on your disk.",
        "best_for": "Keeping an article next to the videos you studied.",
    },
    {
        "slug": "reddit", "name": "Reddit", "category": "text", "status": IN_FLIGHT,
        "capture": "Paste a thread URL.",
        "lands": "The post plus a depth-limited, score-ranked comment tree.",
        "best_for": "Capturing what builders actually argue about a tool.",
    },
    {
        "slug": "substack", "name": "Substack", "category": "text", "status": PLANNED,
        "capture": "Paste an article URL, or add the publication feed.",
        "lands": "Full post text in markdown; the feed keeps new posts coming.",
        "best_for": "Building a research corpus from the writers you follow.",
    },
    {
        "slug": "linkedin-videos", "name": "LinkedIn videos", "category": "video", "status": PLANNED,
        "capture": "Paste a LinkedIn post or video URL.",
        "lands": "Transcript and author metadata for the native video.",
        "best_for": "B2B creators citing a talk or demo.",
    },
    {
        "slug": "bluesky", "name": "Bluesky", "category": "social", "status": PLANNED,
        "capture": "Paste a post URL.",
        "lands": "The post plus its reply thread.",
        "best_for": "Saving a thread from the post-Twitter diaspora.",
    },
    {
        "slug": "mastodon", "name": "Mastodon", "category": "social", "status": PLANNED,
        "capture": "Paste a status URL from any public instance.",
        "lands": "The status plus its reply context.",
        "best_for": "Keeping a federated thread you want to write from.",
    },
    {
        "slug": "threads", "name": "Threads", "category": "social", "status": PLANNED,
        "capture": "Planned once Meta exposes a stable public read path.",
        "lands": "Post text plus replies, when supported.",
        "best_for": "Parity with the other micro-post sources.",
    },
    {
        "slug": "beehiiv", "name": "Beehiiv", "category": "text", "status": PLANNED,
        "capture": "Add the newsletter feed or paste a web-archive URL.",
        "lands": "Full issue text in markdown, trackers stripped.",
        "best_for": "Following a newsletter into your corpus.",
    },
    {
        "slug": "ghost", "name": "Ghost", "category": "text", "status": PLANNED,
        "capture": "Add the publication feed or paste a post URL.",
        "lands": "Full post text in markdown.",
        "best_for": "Indexing an independent publication.",
    },
    {
        "slug": "buttondown", "name": "Buttondown", "category": "text", "status": PLANNED,
        "capture": "Add the newsletter feed or paste an archive URL.",
        "lands": "Clean issue text in markdown.",
        "best_for": "Capturing a developer newsletter.",
    },
]

# The 5-step Uoink story (POSITIONING-LOCK Ryan final-pass #3).
_CREATOR_STEPS: list[dict] = [
    {"step": 1, "name": "Capture", "copy": "One click on any video, podcast, or post. The source lands on your disk."},
    {"step": 2, "name": "Library", "copy": "Everything you study, searchable, with hook and topic facets."},
    {"step": 3, "name": "Workspace", "copy": "Assemble the source material for the thing you're about to make."},
    {"step": 4, "name": "Iterate", "copy": "Draft in your voice with Voice DNA, grounded in the real transcript."},
    {"step": 5, "name": "Distribute", "copy": "Ship the thread or blog with creator credit baked in."},
]


def build_sources() -> dict:
    counts = {SHIPPED: 0, IN_FLIGHT: 0, PLANNED: 0}
    for s in _SOURCES:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    return {
        "sources": _SOURCES,
        "total": len(_SOURCES),
        "counts": counts,
        "categories": ["video", "audio", "text", "social"],
    }


def build_creators() -> dict:
    return {
        "audience": "creators",
        "headline": "Save the source, write from it in your voice.",
        "jtbd": ("Turn what you watch, read, and study into reusable source "
                 "material for the next post, script, thread, or blog, with "
                 "credit to the people you learned from."),
        "steps": _CREATOR_STEPS,
        "pillars": [
            {"key": "local", "label": "On your disk", "copy": "No account, no cloud. The corpus is a file you own."},
            {"key": "voice", "label": "In your voice", "copy": "Voice DNA keeps drafts sounding like you, not like AI."},
            {"key": "credit", "label": "Creator credit", "copy": "Every generated post cites the source creator. Non-suppressible."},
        ],
    }


def build_developers(*, tool_count: int, mcp_endpoint: str,
                       openapi_spec_path: str) -> dict:
    return {
        "audience": "developers",
        "headline": "A local corpus your agent can call.",
        "jtbd": ("Make distribution feel like a local dev tool: a corpus your "
                 "agent queries, files you own, a visible MCP server, and a "
                 "fast path from source to launch thread."),
        "access": [
            {"key": "mcp", "label": "MCP", "endpoint": mcp_endpoint,
             "copy": f"{tool_count} local tools over MCP for Claude, Cursor, and Cline."},
            {"key": "openapi", "label": "OpenAPI", "endpoint": openapi_spec_path,
             "copy": "The same tools over plain HTTP for any agent that reads an OpenAPI spec."},
        ],
        "tool_count": tool_count,
        "local_first": "BYO Anthropic key. No third-party key, no cloud relay.",
    }

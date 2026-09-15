# uoink 3.8: Living Library

Private release draft, updated September 15. Publish after the final installer
and matching verification receipts are recorded. The release scope is decided;
packaging and final verification remain unfinished.

Living Library helps you return to what you saved. Find a note or source, inspect
the evidence behind an answer, and open a brief with citations back to your library.
For saved media with suitable timing, chapters and cited ranges help you find
the relevant passage.

This release adds:

- Evidence cards and bounded excerpts that an MCP client can read, with source
  and revision information attached. Stale citations are refused when their
  underlying evidence has changed.
- Shelf suggestions you can review. Autonomous filing stays disabled.
- Standing capture with explicit source consent, visible limits, pause and
  recovery. Capture starts off until you enable it.
- Cited briefs, client resources and prompts, plus an optional file mirror that
  requires its own consent and preserves user edits.
- Reports describing activity in your saved library, with coverage and supporting
  evidence. These reports do not measure social-platform popularity.
- Chapters and cited media ranges. Speaker attribution is outside this release.

The desktop fixes include Unicode search, saved-note details that no longer show
irrelevant video warnings, and media details that distinguish stored timestamps
from missing timing. Library and capture recovery messages reflect their saved
state.

Your library is stored on your machine. Fetching sources, obtaining missing model
resources and using external clients can involve network services; this is not a
promise that every workflow runs offline. uoink is MIT-licensed, and bundled
dependencies have their own licences in the third-party notices.

The candidate's native Uoink window has been exercised on isolated test data;
client coverage is **tested with Claude Code**. Claude Desktop is **unverified**
unless a separate receipt is completed before packaging. Some X links remain blocked with HTTP 403.
Speaker attribution and Phase 5 Part B are deferred. Shelf-quality and dashboard
response-size targets retain their recorded misses.

3.8.0 keeps Torch 2.8.0 / WhisperX 3.8.6. The existing model-loader path and
retained security limitations are described in [security.md](../security.md).
The Windows installer is unsigned; publisher signing is planned for 3.9.
An old AT6 receipt lacks its original process exit status. That unrecoverable
historical gap is disclosed and does not block this release.

Shelf proposals remain reviewable suggestions. The 0.90 threshold for autonomous
filing is unchanged and `librarian_apply_enabled` stays false.

Before publishing, attach the final Windows installer and SHA256, matching MCP
bundle and extension assets, tested client versions, upgrade and rollback steps,
and a support link. This draft does not publish or approve a download.

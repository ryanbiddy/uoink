# uoink 3.8: Living Library

Private release draft. The candidate remains on hold. Publish only after the
final installer, client support and release decisions are recorded. The public
release is still [uoink 3.7.0](https://github.com/ryanbiddy/uoink/releases/tag/v3.7.0).

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

The candidate's native Uoink window and Claude Code integration have been
exercised on isolated test data. Claude Desktop acceptance is still pending and
must not be advertised as tested. Some X links remain blocked with HTTP 403.
Speaker attribution and Phase 5 Part B are deferred. Shelf-quality and dashboard
response-size targets retain their recorded misses.

Before this draft can become release notes, attach the approved Windows installer
and its hash/signing result, matching MCP bundle and extension assets, supported
client versions, upgrade and rollback instructions, and a support link. Retained
dependency findings and the missing historical receipt require explicit release
dispositions. No installer or public announcement is approved by this draft.

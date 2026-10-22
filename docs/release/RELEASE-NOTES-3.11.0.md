# Uoink 3.11.0

## What's new

- **Search that finds things.** Search no longer needs every word: it skips common words and ranks the best matches first. **Exact words** keeps the old way. In a fixed 30-question test, the right source made the top 5 for 24, up from 10.
- **Optional semantic search.** In Settings > Semantic search, accept the Gemma terms and Uoink downloads EmbeddingGemma once (about 330 MB). It is never bundled, runs on your computer and works offline after setup. The right source then made the top 5 for 28 of 30; all 10 keyword questions passed in every mode.
- **Citations you can quote.** Each result names its source ID. It adds the passage and, for timed sources, its timestamp only when that passage really contains the match.
- **An MCP update that keeps today's apps working.** Uoink now runs on the official MCP Python SDK 2.3.0. Current apps connect as before, and newer ones can use the 2026-07-28 protocol. Claude Code 2.1.307 and Codex 0.153.4 connected and called tools. Still 91 tools (35 in core mode).
- **Anonymous usage counts, off by default.** See Privacy.
- **Connect.** `uoink connect` shows Linux paths where a client has them, the dashboard detects a connected Continue, and there are 10 new client recipes.

## Install or update

1. Download `Uoink-Setup-3.11.0.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256. Windows 10/11.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.11.0.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

## Upgrading

- Your library and captures stay in place.
- The first start rebuilds the search index once, which takes a few seconds on large libraries.
- Reload the Uoink extension in `chrome://extensions`.
- Claude Desktop: reinstall `uoink-3.11.0.mcpb` and restart Desktop.

## Privacy

- Usage counts are off unless you turn them on in Settings > App > Usage sharing. Then Uoink sends usage.uoink.app one report a day: counts of tool calls (by tool name and by stdio or HTTP), AI apps from a fixed list, captures by source and result, and searches, plus a random install ID and report ID, app version, operating system and major version, processor type, install type and hours covered. Never content, URLs, titles, file paths, search text or account names. **See what is sent** shows each report; turning sharing off deletes the ID and counts. [Details](https://github.com/ryanbiddy/uoink/blob/v3.11.0/docs/usage-sharing.md)
- The semantic model downloads only after you accept the Gemma terms. Searches and saved text stay on your computer.

## Known limits

- Chrome (tested). Edge and Brave may work but are not tested.
- Semantic search needs the Uoink app running; otherwise search uses keywords and says so. The first semantic build runs in the background (about 40 minutes for 693 sources on one PC).
- Most connect recipes are not yet tested in the client itself.

## Checksums

| File | SHA-256 |
| --- | --- |
| `Uoink-Setup-3.11.0.exe` | `639bf5c9c452a480afbfb71cbd5c9f6ba506b881f562f42e4078f6dbbe6e0bab` |
| `uoink-3.11.0.mcpb` | `3b29aeb457349e68e31e1465179d0d475b554771f6cd526d6538c6c847e945e6` |

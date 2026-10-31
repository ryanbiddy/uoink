# Uoink for Claude

Ask Claude about the YouTube videos, podcasts, articles, X posts, Reddit
threads and notes you saved with [Uoink](https://uoink.app). Claude searches
your local library and cites the timestamp. It can also capture new links,
save notes, and write in your voice from your own saved evidence.

## What's in this plugin

- **The Uoink skill** (`skills/uoink/SKILL.md`). It teaches Claude how to find
  saved evidence, cite timestamps, capture URLs and save notes, through Uoink's
  MCP tools or the `uoink` command.
- **An MCP server entry** (`.mcp.json`). It starts the MCP server that the Uoink
  app installed on your computer.

## Requirements

Install Uoink from [uoink.app/install](https://uoink.app/install): 3.10 or later
on Windows, or 3.11.2 or later for the macOS preview.
The MCP server entry uses the default Windows install path. On a Mac, or on a
custom install, run `uoink connect claude-code` and use the command it prints;
the skill also works through the `uoink` command alone.

## What it runs and sends

- **Runs:** the Uoink app's bundled Python with `uoink_mcp.py`, from your
  Uoink install folder. The plugin contains no server code of its own.
- **Reads:** your local Uoink library. Searching and reading saved items make
  no network calls and need no API key.
- **Fetches:** only the source you ask Uoink to capture (YouTube, X, Reddit,
  a podcast feed or a web page). Truncated X posts may use the FxTwitter
  fallback.
- **Optional, off by default:** AI analysis features send relevant source text
  to Anthropic with your own API key. ScrapeCreators discovery uses your own key
  with a credit cap. Anonymous usage counts go to usage.uoink.app only if you
  turn them on.

Uoink has no account and no cloud library. See the
[privacy policy](https://uoink.app/privacy).

## License

MIT. See [LICENSE](LICENSE).

# Uoink for Obsidian

Cite the videos, podcasts, articles and notes you saved with
[Uoink](https://uoink.app) without leaving your note. Search your library,
insert a quote that links to the exact timestamp, and save new links.

## Commands

| Command | What it does |
|---|---|
| **Insert citation from library** | Search as you type. Pick a result to insert a citation that links to the matched moment. With an empty search, pick a recent capture to insert its title, source and timestamped excerpts. |
| **Search library and open the moment** | Same search; picking a result opens the source at that timestamp in your browser. |
| **Save a link to the library** | Uoink a YouTube video or playlist, X post, Reddit thread, podcast feed or web page. Uses the selected text if it's a link, otherwise asks (prefilled from the clipboard). |

A citation looks like this:

```markdown
> Working memory holds about four chunks at once.
>
> — [How memory works @ 4:12](https://www.youtube.com/watch?v=abc123&t=252s)
```

Only saved source text (a transcript clip or an article passage) is quoted,
and "…" marks a quote that was cut short. A result that matched only the title or metadata is
inserted as a link, such as `[How memory works](https://www.youtube.com/watch?v=abc123)`.
The Raycast, Alfred and Flow Launcher integrations copy the same formats.

## Requirements

- Obsidian on desktop (Windows or macOS). The plugin is desktop-only.
- [Uoink](https://uoink.app/install) 3.10 or later on Windows, or 3.11.2 or
  later for the macOS preview. A default install (`%LOCALAPPDATA%\Uoink`, or
  `Uoink.app` in `/Applications` or `~/Applications`) is found automatically.
  Otherwise set **Uoink command** in the plugin's options to
  `Uoink.app`, its `Contents/Helpers/uoink` command, or `cli\uoink.cmd` in your Uoink folder.

The Uoink window doesn't need to be open.

## Disclosures

- **Runs a program outside Obsidian.** The plugin starts the `uoink` command
  that the Uoink app installed, with an argument list and never through a
  shell. On Windows it runs Uoink's bundled Python with `uoink_cli.py` directly.
- **Reads files outside your vault**, through that command: your Uoink
  library (`%LOCALAPPDATA%\Uoink` on Windows, `~/Library/Application Support/Uoink`
  on macOS). It writes to your vault only where you insert text.
- **Network use.** The plugin makes no network requests. Searching is local.
  **Save a link** asks Uoink to fetch the link you entered, and nothing else.
- No account, no payment, no telemetry.

## Develop

```sh
npm install
npm run dev     # rebuilds main.js on change
npm run build   # type-check and production build
npm run lint    # Obsidian's review rules
```

Copy `main.js` and `manifest.json` into `<vault>/.obsidian/plugins/uoink/` to try it.

## Publishing

The community directory needs `manifest.json`, `README.md` and `LICENSE` at the
root of a dedicated repository, plus a GitHub release with `main.js` and
`manifest.json`. Copy this folder to a new repository such as
`ryanbiddy/obsidian-uoink`; pushing a tag like `1.0.0` runs
`.github/workflows/release.yml`, which builds the plugin and drafts the
release. Publish the draft, then submit the repository at
[community.obsidian.md](https://community.obsidian.md).

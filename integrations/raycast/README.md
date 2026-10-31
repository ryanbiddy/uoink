# Uoink for Raycast

Search the videos, podcasts, articles and notes you saved with [Uoink](https://uoink.app), and cite the exact moment, without leaving Raycast. Save new links from any app.

Uoink is free, open source and local. This extension talks to the Uoink app on your computer through its `uoink` command. Nothing goes to a Uoink server.

## Setup

1. Install Uoink from [uoink.app/install](https://uoink.app/install): 3.10 or later on Windows 10/11, or 3.11.2 or later for the macOS preview (macOS 15+ on Apple Silicon).
2. That's it for a default install. The extension finds Uoink in `/Applications/Uoink.app` or `~/Applications/Uoink.app` on macOS and in `%LOCALAPPDATA%\Uoink` on Windows.
3. Installed somewhere else? Open the extension preferences and set **Uoink CLI** to your `Uoink.app`, its `Contents/Helpers/uoink` command, or `cli\uoink.cmd` in your Uoink folder.

The Uoink window does not need to be open. Library search reads your local index directly.

## Commands

| Command | What it does |
|---|---|
| **Search Library** | Search transcripts, articles and notes as you type; results show their timestamps. **Enter copies a Markdown citation** that links to the exact moment: a quote when Uoink verified the passage, otherwise just the link. ⌘O opens the source at that timestamp, ⌘⇧V pastes the citation, and ⌘I shows the full item. |
| **Uoink This URL** | Save the link on your clipboard. If the clipboard has no link, it saves the page in your browser's active tab instead (macOS, with the [Raycast browser extension](https://www.raycast.com/browser-extension)). A video's transcript Markdown is copied to your clipboard when it's done; you can turn this off. |
| **Recent Saves** | Your last 20 saves. Enter shows the item; you can also show it in Finder or File Explorer. |
| **Save Note** | Save an idea or quote as a searchable note. |

On Windows, Uoink This URL uses the clipboard only, because Raycast's browser-tab API isn't available on Windows yet.

Long videos can take a few minutes, because Uoink transcribes and takes screenshots before it reports back. Web pages follow Uoink's site allowlist; allow a new site from the Uoink dashboard first.

Every command works on the free Raycast plan. Only the Raycast AI features below need a plan that includes AI.

## Raycast AI

With Raycast AI, type `@uoink` in AI Chat or Quick AI:

- "@uoink what have I saved about pricing pages?" searches your library and cites timestamps as links.
- "@uoink what did I save this week?" lists recent captures.
- "@uoink save https://youtu.be/…" captures a link after you confirm.

In AI Chat you can also pick a saved item from the `@` menu under Uoink to hand the AI its timestamped excerpts.

The AI tools only return what's in your library and ask before they save anything. Raycast AI features need a Raycast plan that includes AI.

## Uoink's MCP server instead

Uoink also ships a full MCP server with 91 tools. To use it from Raycast AI instead of, or alongside, this extension, run `uoink connect raycast` in a terminal and follow the printed steps.

## Troubleshooting

- **"Uoink isn't set up"**: Uoink isn't at its default location. Install it, or set **Uoink CLI** in the preferences.
- **"No link to uoink"**: copy the link first. On macOS, Uoink This URL can also read the active tab once the Raycast browser extension is installed and the browser is open.
- **A web page won't save**: allow the site in the Uoink dashboard, then try again.

## Publishing

Publishing to the Raycast Store needs the owner's Raycast handle in `package.json`'s `author` field; `ray lint` rejects a handle Raycast doesn't know.

# Uoink 3.17.0 listing fields

Use the manifest name and summary below. They are already in the upload zip.
The dashboard may populate them from the manifest instead of offering editable
fields. Paste the detailed description into Store listing.

Lines marked **[if shipped]** describe 3.17.0 features that were still being
built when this was written. Before pasting, keep each line whose feature is in
the release and delete its marker. Delete the whole line for a feature that was
cut. Every unmarked line is true of the app today.

## Name

Uoink

## Summary

Save YouTube transcripts, frames and comments to a local library your AI can search and cite. Needs the Uoink app on Windows or Mac.

## Category and language

Productivity. Choose the Research & Education subcategory if offered.
English (United States).

## Detailed description

Save a source while you browse, then find it again in your own library.

Uoink captures YouTube transcripts, frames, comments and source details on your computer. It also supports X posts and articles, Reddit threads, and supported web pages and podcast links. What gets saved depends on the source.

The free Uoink desktop app for Windows or Apple-silicon Macs is required. It saves everything to your own disk. Install it from https://uoink.app/install and keep it running. Right after you add the extension, a setup page checks for the app, links the right download for your computer, and shows "Connected" when it is running. Without the app, the extension shows Offline and explains how to connect it. Capture controls stay disabled until it connects.

To save a source:

1. Click Uoink on a supported page, open the toolbar popup, press Alt+U, or use the right-click menu.
2. Choose what to save. You can also paste a supported link into the popup.
3. Open the local Library to search the saved text and read it with its source details. Copy a capture when you want to use it in another app.

What you can do once it is running:

- Search your whole library by what was said, and open the exact passage with its source details.
- Let your AI search it too. The desktop app can connect Claude, ChatGPT and other AI apps to your library so they can search and cite what you saved.
- Save podcast episodes and sources you follow, and keep new ones coming into the same library.
- [if shipped] Choose what happens after a save, such as a notification with buttons to copy the capture for Claude or ChatGPT.
- [if shipped] See suggestions for what to save or read next, based on your own library.
- [if shipped] Send a link from your phone to your own Uoink inbox and have it saved on your computer.

YouTube captures can include a timestamped transcript, selected frames, comments and metadata. X Articles can be captured from the article you can already read in your browser. Uoink does not unlock paywalls or grant access to private content. Save only material you have permission to use.

Your library stays on your computer. Uoink has no account or hosted library. The extension talks to the helper at 127.0.0.1:5179, which means your own computer. It stores capture state locally; the screenshot interval preference can sync through your browser account.

Some previews load source thumbnails. After a capture is copied, the extension can open Claude in a new tab. It does not paste or submit the capture for you. You choose what to share with Claude, ChatGPT or a connected AI app.

Optional helper features can send selected material to Anthropic using your own API key. Authorized discovery requests can contact ScrapeCreators. Transcription runs locally with a model that ships with the helper; optional extra models download on request, and model-library telemetry can make outside connections. These details and controls are explained in the privacy policy.

Usage sharing is off by default. If you turn it on in the helper, it sends daily usage counts and app details to usage.uoink.app. Reports include random install and report IDs, but no captured content, URLs, titles, file paths, search text, prompts, API keys or account details. Settings shows the report and lets you turn sharing off.

Uoink is free and open source. Requires a Chromium browser (Chrome, Edge, Brave, Arc, Opera or Vivaldi) and the Uoink desktop app on Windows 10 or 11, or on macOS 15 or later with Apple silicon. Intel Macs are not supported yet. Optional third-party services can charge for use.

Install the desktop app: https://uoink.app/install
Privacy and network calls: https://uoink.app/privacy
Source code and support: https://github.com/ryanbiddy/uoink

## Single purpose

Save sources the user chooses while browsing into a local research library, with source details and text they can search, read and copy for use with their AI tools. The extension supplies capture buttons, a popup, a shortcut and context-menu actions. The required Uoink helper app processes and stores the selected material on the user's computer.

## Other fields

| Field | Value |
|---|---|
| Website | https://uoink.app |
| Privacy policy | https://uoink.app/privacy |
| Support URL | https://github.com/ryanbiddy/uoink/issues |
| Support email | hi@uoink.app |
| Price | Free |
| Mature content | No; the listing has no mature content |

Verify that the support mailbox receives mail. This pass did not send mail.
Upload the screenshots in the order listed in [SCREENSHOTS.md](SCREENSHOTS.md).

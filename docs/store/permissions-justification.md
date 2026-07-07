# Permissions justification — Uoink (CWS reviewer notes)

Paste each justification into the matching field in the CWS Developer Console
under **Privacy practices → Permission justifications**.

## Extension permissions

- **`alarms`** — Runs a periodic health check to see whether the local helper is responsive, and updates the toolbar badge color accordingly.
- **`clipboardWrite`** — Copies the extracted Markdown corpus and base64-encoded screenshots to the user's clipboard so they can paste it into Claude, ChatGPT, or a notes app.
- **`notifications`** — Shows capture success messages and local-helper-offline warnings.
- **`storage`** — Persists local extension settings: screenshot count, active research session name, mobile queue sync state, and setup state. No browsing data.
- **`contextMenus`** — Adds right-click actions to trigger extraction on supported video links and thumbnails.
- **`activeTab`** — Reads the current tab's URL and injects the extraction content script only when the user clicks the extension action on a supported video tab.
- **`scripting`** — Injects the in-page Uoink button and the extraction content script on supported pages via the MV3 scripting API, only in response to a user action.
- **`offscreen`** — Manifest V3 service workers cannot reach the clipboard API directly; an offscreen document is the only supported path for clipboard writes.

## Host permissions

- **`https://www.youtube.com/*`, `https://m.youtube.com/*`, `https://youtu.be/*`** — Runs the in-page Uoink button and reads public transcripts, comments, and chapter metadata on YouTube.
- **`https://x.com/*`, `https://twitter.com/*`, `https://mobile.twitter.com/*`** — Validates video links and triggers context-menu extraction on X / Twitter pages.
- **`https://*.reddit.com/*`** — Reads a public Reddit thread and its top comments when the user runs a capture on a Reddit page.
- **`http://127.0.0.1:5179/*`, `http://localhost:5179/*`** — Talks to the local Uoink helper process listening on port 5179. All heavy processing and storage happen there, on the user's machine.

## Data use affirmations (CWS "Data usage" section)

- **Website content — collected, "selected" only.** The extension reads the transcript, comments, and metadata of videos the user explicitly chooses to process. It is processed locally.
- **Not sold to third parties.**
- **Not used or transferred for any purpose unrelated to the single purpose** (video/podcast/page extraction).
- **Not used for creditworthiness or lending.**
- **Complies with the Chrome Web Store Limited Use policy and User Data policy.**

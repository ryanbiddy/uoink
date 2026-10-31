# Permission justifications for 3.12

Paste each paragraph into the matching Privacy practices field. All eight
API permissions remain because they have live callers. Three unused host
entries were removed: `https://youtu.be/*`, `https://mobile.twitter.com/*`
and `http://localhost:5179/*`.

## alarms

Checks whether the local Uoink helper is available and updates the toolbar badge. The service worker uses a 30-second alarm so it can refresh status after waking. It does not collect browsing history.

## clipboardWrite

Writes the capture the user requested to the clipboard, including its text and supported image representation. Users can then paste it into an app of their choice. The extension does not read the existing clipboard.

## notifications

Shows the result of a user-requested capture or copy, including failures and an unavailable helper. Notifications do not contain advertising. Queued jobs do not trigger desktop notifications.

## storage

Stores the helper authentication token, setup state, active session, pending capture results and recent failures in extension-local or session storage. These records can contain selected source URLs and titles. The screenshot interval preference uses browser sync storage. No general browsing-history log is collected.

## contextMenus

Adds capture actions to the right-click menu for supported links and pages, plus a page-capture action. The chosen URL is sent to the local helper only when the user selects the action.

## activeTab

Reads the active tab's URL after the user opens the extension or invokes a capture action. It also supplies temporary access for reading feed links and preview metadata on a page the user chooses, without asking for persistent access to all websites.

## scripting

Runs bundled code to read a selected page's feed links or preview metadata, and to inject the bundled X Article parser into an already-open tab after installation or update. No script is downloaded or evaluated from a server.

## offscreen

Creates a packaged offscreen document so capture work in the Manifest V3 service worker can write to the clipboard. The same document checks the browser's color-scheme preference. It does not load a remote document.

## Host permissions

| Manifest entry | Text for the reviewer |
|---|---|
| `https://www.youtube.com/*`, `https://m.youtube.com/*` | Supports the in-page capture button and access to supported YouTube tabs. The content script starts on the site's other pages so navigation to a video works without reloading. Capture is user-triggered; the helper retrieves the selected source. |
| `https://x.com/*`, `https://twitter.com/*` | Supports the X Article button and the bundled parser on articles the user can already read, including script injection into already-open tabs. The rendered article is sent to the local helper when requested. |
| `https://*.reddit.com/*` | Supports Reddit thread tabs and the in-page capture control across Reddit's site variants. The selected thread URL is passed to the local helper for extraction. |
| `http://127.0.0.1:5179/*` | Connects to the required Uoink helper app on the user's own computer for health checks, authentication, capture requests and local results. The helper binds to loopback and checks exact extension origins and a per-install token. This is not an internet server. |

The declared content scripts also cover `www.x.com`, `www.twitter.com` and
Reddit thread pages. They are visible site access in the manifest, even though
these are not all repeated in `host_permissions`. Generic page capture and
short links do not need persistent host grants; they use user-selected URLs
and the helper. No `<all_urls>`, cookies, history, downloads or tabs permission
is requested.

See [POLICY-AUDIT.md](POLICY-AUDIT.md) for file and line evidence and
[privacy-practices.md](privacy-practices.md) for the data declarations.

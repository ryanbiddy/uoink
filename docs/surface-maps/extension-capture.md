# Surface Map: Reddit Extension Capture

This document describes the flow, user interface elements, DOM selectors, messaging, and API endpoints involved in capturing Reddit comment threads via the Uoink browser extension.

## 1. Overview
The Reddit capture feature allows users to save whole comment threads from Reddit directly to their local markdown corpus using the public `.json` Reddit endpoint. Sideloaded extensions inject a native Uoink button on thread pages and context menu items for thread links and pages.

## 2. DOM Selector Anchors (`content-reddit.js`)
To inject the Uoink capture button, the content script queries the page for the following elements:
- **Old Reddit**: `div.top-matter ul.flat-list.buttons` (appends as a `<li>` list item).
- **Modern Reddit (shreddit)**:
  1. `<shreddit-post-actions>`: Inserts adjacent to the action bar buttons.
  2. `<shreddit-action-share>`: Inserts as a sibling to the share button.
  3. `<div slot="footer">`: Appends to the post footer.
  4. `<shreddit-post>`: Appends directly to the post element as a fallback.

## 3. Visual States and DOT indicators
The button uses status dots to reflect the helper's online state:
- **Checking (pulsing grey)**: Extension is pinging localhost helper.
- **Online (green)**: Helper is active and ready. Hovering details the action.
- **Offline (red)**: Helper is inactive. Clicking redirects to `setup.html?source=offline`.
- **Working (spinner)**: Captured URL is being extracted and processed by the local helper.
- **Success (green background)**: Sideload completed and copied successfully.
- **Error (dark red background)**: Extraction failed.

## 4. Message Flow and Background Routing
```
[content-reddit.js] (Click)
       │
       ▼ (sendMessage: "stcExtract")
[background.js] (Routes based on URL)
       │
       ├─► (if Reddit URL) ──► STC.postExtractReddit()
       └─► (otherwise)   ──► STC.postExtract()
```

- When the in-page button is clicked, `content-reddit.js` calls `chrome.runtime.sendMessage({ type: "stcExtract", url, interval })`.
- In `background.js`, the message handler detects the Reddit URL using `STC.normalizeRedditUrl(url)` and routes the request to `STC.postExtractReddit` (which hits the local helper at `POST /extract/reddit`).
- Upon success, the helper returns the thread title, comments count, and extracted markdown, which background script copies to the clipboard and redirects to Claude/ChatGPT.

## 5. Popup List and Retries (`popup.js`)
- **Platform Badge**: Reddit captures are displayed with a dedicated `"Reddit"` label and orange platform chip (`.platform-chip.reddit`).
- **Thumbnail Fallback**: Since Reddit threads lack video thumbnails, the popup renders the default Uoink extension icon instead of pulling broken YouTube thumbnail templates.
- **Retries**: Retrying failed captures opens the Reddit URL directly in a new tab without requiring a YouTube video ID.

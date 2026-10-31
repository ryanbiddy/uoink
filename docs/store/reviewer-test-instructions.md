# Reviewer test instructions

Paste everything from here down to **Notes for Ryan** into the dashboard's
**Test instructions** tab.

No Uoink account, login credentials, paid API key or usage-sharing opt-in is needed.

## Without installing the helper

1. Install the extension. The setup tab opens once on first installation.
2. It shows "Set up your first capture", a helper download link, a
   connection check and a first-capture button.
3. With the helper absent, the status becomes **Uoink is offline**. It tells
   Windows users to open the Start Menu and start Uoink Server. The download
   link is available if the helper has not been installed.
4. **Uoink this video** stays disabled. **Check again** checks the connection;
   it does not start a capture. While the tab is visible it retries automatically.
5. Open the toolbar popup. It shows **Offline** and **Start Uoink from the
   Start menu, then try again.** The paste-submit and capture buttons are disabled.
6. Supported pages can still show the Uoink button. A capture cannot finish
   until the helper is installed and running. No demo data is substituted.

This checks installation and the missing-helper flow. It does not demonstrate
successful extraction. The store zip contains no mock API. The local helper
is a disclosed requirement, not a hidden login or paywall.

## Full capture on Windows 10/11 or macOS 15+

1. Download the helper using the setup tab or https://uoink.app/install.
   The current release is https://github.com/ryanbiddy/uoink/releases/tag/v3.12.0
   (a Windows installer, and a DMG for Apple Silicon Macs). Use the release's
   checksum instructions before running it. On a Mac, open Uoink from
   Applications instead of the Start menu; the other steps are the same.
2. Start Uoink Server. Keep it running. Use the extension installed from this
   review item; do not also load the bundled developer extension.
3. Return to setup and click **Check again**. Expect **Running on this PC**.
4. Open a YouTube video you own or have permission to save. Use the in-page
   button or open the popup and capture that video. The popup can also accept
   a full supported URL. Wait for completion, then open Library to read the
   saved text and source details.
5. Copy a completed capture. Confirm that text reaches the clipboard. Some
   completed capture paths open Claude, but do not paste or submit the text.
6. Close the helper. Check setup or the popup again and confirm the offline
   state returns. Restarting the helper restores the connection.

## Local connection and authentication

127.0.0.1 means the user's own computer. The helper listens on port 5179 and
handles downloading the selected source, extraction and local storage.
The extension sends JSON requests and reads JSON or image data back. It does
not download or execute JavaScript from the helper. Plain HTTP is confined
to loopback; optional outside service calls use HTTPS. The helper rejects
unknown extension origins, checks the local Host header and uses a per-install
token for protected operations. There are no wildcard origin grants.

The helper trusts this store item's ID from version 3.11.2 on, so capture
authentication works with the extension installed from this listing.

## Notes for Ryan (don't paste)

The offline smoke was tested in Chrome for Testing 153 with a disposable
profile. No helper was started or contacted. Failed localhost network requests
are expected while offline; there were no JavaScript exceptions or console
warnings in the final run. Full capture with the store-assigned ID remains a
release check after Ryan creates the item.

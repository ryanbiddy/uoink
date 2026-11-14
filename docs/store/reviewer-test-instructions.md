# Reviewer test instructions

Paste everything from here down to **Notes for the owner** into the dashboard's
**Test instructions** tab.

No Uoink account, login credentials, paid API key or usage-sharing opt-in is needed.

## Without installing the desktop app

1. Install the extension. The setup tab opens once on first installation.
2. It shows a panel titled **Uoink needs its free desktop app**, with a line
   explaining why (Uoink saves transcripts to the user's own disk), a badge naming
   the detected system (Windows 10 or 11, Mac with Apple silicon, Mac with an
   Intel chip, or Linux), and the right download button. The button goes to
   uoink.app's download redirect, which counts the download without IP addresses
   or cookies and forwards to the GitHub release file. Intel Macs and Linux see a
   plain note and manual instructions instead of a download.
3. Clicking the download button changes the panel to **Waiting for Uoink to
   start**. The page keeps checking the local app by itself and needs no refresh.
4. With the app absent, the status stays **Uoink is offline**. **Uoink this
   video** stays disabled. **Check again** checks the connection; it does not
   start a capture. While the tab is visible it retries automatically.
5. Open the toolbar popup. It shows **Offline** and **Start Uoink from the
   Start menu, then try again.** The paste-submit and capture buttons are disabled.
6. Supported pages can still show the Uoink button. A capture cannot finish
   until the app is installed and running. No demo data is substituted.

This checks installation and the missing-app flow. It does not demonstrate
successful extraction. The store zip contains no mock API. The local app is a
disclosed requirement, not a hidden login or paywall.

## Full capture on Windows 10/11 or macOS 15+

1. Download the app using the setup tab or https://uoink.app/install.
   The current release is on https://github.com/ryanbiddy/uoink/releases/latest
   (a Windows installer, and a DMG for Apple silicon Macs). Use the release's
   checksum instructions before running it. On a Mac, open Uoink from
   Applications instead of the Start menu; the other steps are the same.
2. Start Uoink Server. Keep it running. Use the extension installed from this
   review item; do not also load the bundled developer extension.
3. Return to the setup tab. Within a few seconds the panel changes by itself to
   **Connected**, and the status reads **Running on this PC** (or Mac). Click
   **Check again** if you do not want to wait.
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

## Notes for the owner (don't paste)

The offline smoke was tested in Chrome for Testing 153 with a disposable
profile. No helper was started or contacted. Failed localhost network requests
are expected while offline; there were no JavaScript exceptions or console
warnings in the final run. Full capture with the store-assigned ID remains a
release check after the owner creates the item.

# Uoink 3.9.0

The dashboard and extension have a new design, including the library reader,
capture activity, settings, popup and setup page.

## What's new

- Generate → Research brings five playbooks for outlier posts, transcripts,
  comments, creator teardowns and repurposing. Work from your saved captures,
  review citations, save a report as a draft, or turn it into a tweet or thread.
  Use a connected agent, your Anthropic key, or a prompt you can copy into Claude.
- Sources → Discover can find candidates through ScrapeCreators. Discovery is
  off by default. Enable it in Settings → Connected services with your own key;
  confirmed searches use your credits. Review the results before queueing captures.

## Reliability and security

- A corrupt library index can be rebuilt from saved captures while preserving
  the damaged database. Other storage errors stop recovery without deleting files.
- Video capture folders distinguish sources with the same title and check
  ownership before reusing an existing folder.
- By default, live-stream captures wait for the recording. Cancellation works while
  waiting or running. Logs rotate instead of growing without a limit.
- YouTube caption rate limits (HTTP 429) are handled separately from video
  rate limits. Captures can fall back to local transcription with a caption-refusal note.
- Extension token access is pinned to Uoink's extension identity, with support
  for explicitly trusted IDs. An unrelated extension cannot request a token.
- Page, podcast and thumbnail fetch checks block private-network destinations.
  These checks do not cover requests inside yt-dlp or redirects and subresources
  in browser rendering. See the
  [network policy](https://github.com/ryanbiddy/uoink/blob/v3.9.0/docs/security.md#url-and-identifier-validation).
- Errors shown in the dashboard and extension hide local paths and credentials.
  Dashboard external links are checked before opening to block unsafe destinations.

## Installing

Download `Uoink-Setup-3.9.0.exe` from this release. Windows 10/11 is supported.
The installer is unsigned, so SmartScreen may warn. Check the file's SHA-256
against the value on this release page, then choose **More info -> Run anyway**.

## After updating

Open `chrome://extensions` and reload the Uoink extension so the new popup,
setup page and token handshake load. An old extension build cannot get a token
from the 3.9.0 helper. If the extension ID changes, reapply its preferences;
your helper library and captures stay in place.

## Privacy

See the [privacy policy](https://uoink.app/privacy) for storage and network details.
Optional connections include Anthropic with your own key for AI features,
ScrapeCreators with your own key and credits if discovery is enabled, and
Hugging Face for model downloads when you request speaker labeling. Speaker
labeling runs on local audio.

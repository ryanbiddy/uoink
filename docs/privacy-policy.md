# Uoink Privacy Policy

**Repository draft — not yet effective. Last reviewed 2026-10-16.**

This policy explains exactly what Uoink does and does not do with your
data. It is written to be read, not to be skimmed past. If anything here
is unclear, email us (see *Contact* below).

> Uoink was previously named Yoink. The magnet logo was always a U. Nothing
> about how your data is handled changed in the rename.

## The short version

Uoink does not collect anything about you. There is no Uoink account, no
Uoink server in the cloud, no analytics, and no telemetry. Uoink runs on
your own machine. It contacts a source service when you ask it to capture
that source, the GitHub release API only when you click **Check now**, and
Anthropic only with your own API key: for automatic AI analysis you turn on,
a key test, or an AI action that you or a connected agent start on demand.
Optional ScrapeCreators discovery sends your search terms or creator identifier
with your key only after you enable it and authorize the call. The rest of
this document names those requests, browser visits from dashboard links,
and the local data they create.

## 1. What Uoink collects about you

Nothing.

Uoink has no user accounts, no sign-in, and no usage tracking. It does
not phone home. The local helper writes a diagnostic log to
`%LOCALAPPDATA%\Uoink\server.log` on your own computer to help you
troubleshoot; that log never leaves your machine and is never sent
anywhere.

## 2. What leaves your computer, and when

Uoink makes these outbound requests:

- **Source capture — when you ask for it.** A YouTube capture downloads
  public video data, thumbnails, transcripts, comments, and metadata from
  YouTube and its delivery hosts. A pasted Reddit thread uses Reddit's public
  JSON endpoint. A pasted X post uses X's public syndication endpoint at
  `cdn.syndication.twimg.com`. A web-page or podcast capture requests the
  user-supplied web page or podcast feed. Those services receive the ordinary
  request metadata needed to answer, such as your IP address and Uoink's user
  agent, and may redirect the request to their own CDN.
- **Anthropic API requests — only with your own key.** Uoink has no
  Anthropic key of its own and calls Anthropic's API only with your key
  (the one you saved, or one you type to test it), in these cases:
  - *Automatic AI analysis you turn on* (each is off by default): Comment
    Intelligence sends a capture's comments; Hook Type classification sends
    its title, channel, description, transcript opening and top comment,
    plus up to 8 of your past hook corrections (other captures' titles and
    channels with your reasons) as examples; Entity Extraction sends its
    title, channel and transcript. Each runs after a capture.
  - *On-demand AI actions that you or a connected agent start*: Comment
    Intelligence or Hook Type analysis requested through Uoink's MCP tools
    (these run even when the automatic options are off); Writing Studio
    generation that uses your saved key, from the dashboard when no agent is
    connected or when an agent asks for it (up to 8,000 characters of the
    chosen transcript or corpus text plus its grounding); and research
    playbook runs through authenticated `POST /playbooks/run` requests
    (including connected-agent requests using the saved key), which
    send the playbook instructions and a bounded packet from your library
    relevant to that playbook, such as titles, channel and creator names,
    URLs, chapters, transcript excerpts, top comments, earlier analysis
    summaries and metrics, including saved discovery rows when available,
    plus active writing style anchors for repurposing.
  - *A key test* when you choose to test your key (it sends only a short
    test message, no library text).

  Each on-demand action makes its own paid request (Comment Intelligence and
  Writing Studio may retry once, so one action can make two); a saved key
  starts nothing by itself. Local MCP playbook packets and copying a prompt make no
  Anthropic request from Uoink. The dashboard Research controls are still
  pending.
- **ScrapeCreators discovery: only if you turn it on and add your own key.**
  Discovery sends the creator handle, YouTube channel ID or search words you
  type, your key in the `x-api-key` header, and the Uoink user agent to
  `api.scrapecreators.com`. It sends no library content, transcripts or
  comments. Each confirmed request uses credits, with a default daily cap of
  25. Connected agents can spend only if you separately enable agent discovery;
  dashboard calls require an intent token from that click. Results are saved
  on this PC without third-party thumbnails. Picking results puts their URLs
  into the normal capture queue, which then contacts the source service.
- **Speaker labeling (diarization): when requested.** WhisperX uses pyannote
  to label speakers in local audio. Its alignment and speaker-model loaders
  may download model files, including from Hugging Face. The pyannote loader
  receives a Hugging Face token if supplied through `HF_TOKEN`,
  `HUGGINGFACE_TOKEN` or `HUGGING_FACE_HUB_TOKEN`, when the installed WhisperX
  supports it. These model-loading requests
  are separate from Anthropic analysis and the cached-only transcription-model
  check; Uoink passes the local audio path to the speaker-labeling pipeline.
- **GitHub release check — only when you click `Check now`.** The dashboard
  requests the latest Uoink release record from `api.github.com`. It sends no
  corpus content or usage event. GitHub receives the normal request metadata.

The dashboard and extension use bundled Inter, Bungee and JetBrains Mono
fonts. They make no Google Fonts requests to `fonts.googleapis.com` or
`fonts.gstatic.com`.

The dashboard makes no features-manifest request to
`https://uoink.app/api/features-manifest`, on load or when switching views.
The Features view, remote loader, and bundled fallback catalogue have been
removed.

Dashboard links open when you click them. The dashboard checks three kinds
of external link before opening a browser:

1. **Remote or server-supplied URLs**, except captured source links, must use
   HTTPS and have the host `uoink.app` or a subdomain of it. Uoink help links
   use this same restriction.
2. **Fixed product links** must match an exact origin and path: the repository
   at `https://github.com/ryanbiddy/uoink`, its `/blob/main/CHANGELOG.md`,
   `/releases`, and `/issues` pages; `https://claude.ai/new`;
   `https://claude.ai/download`; `https://twitter.com/intent/tweet`; or
   `https://youtube.com`. Queries and fragments are blocked, except the
   tweet intent's dashboard-built `text` and/or `url` parameters, each at
   most once. Opening X sends the draft in that query. Send to Claude copies
   the Markdown locally and opens a new chat; you paste it there yourself.
3. **Captured-content source links** include Watch on the source, Markdown
   links, reader timestamps, and Activity source names. They may use HTTP
   or HTTPS, but cannot contain credentials or a non-default port. All
   IP-literal hosts are blocked, including loopback (`127.0.0.0/8`, `::1`),
   `0.0.0.0`, private ranges (`10/8`, `172.16/12`, `192.168/16`, `fc00::/7`),
   and link-local ranges (`169.254/16`, `fe80::/10`). `localhost`,
   `*.localhost`, `.local`, and `.internal` hosts are also blocked, including
   trailing-dot forms. This checks the URL, not DNS resolutions or redirects.

All three kinds reject embedded credentials, control characters, backslashes,
and malformed URLs. A refused link shows a blocked message and calls neither
the native URL opener nor the browser opener. A copy action cannot replace
that message with a success toast. The local Startup action is a separate,
narrow exception: the exact `/splash` URL on the dashboard's own loopback
origin, without a query or fragment. Open YouTube uses the fixed product
link through the same check, with no helper-side open or focus request.
Allowed visits send the destination site ordinary browser request metadata.

Uoink sends no analytics, telemetry, usage tracking, or crash reports. The
extracted corpus, screenshots, and files are written only to folders on your
own computer.

### Local data persistence

Uoink currently ships only for Windows. There is no current macOS build,
`.dmg`, or `Uoink.app`; macOS paths and Keychain support described in planning
documents are not deployed storage.

Uoink stores the following on your Windows machine:

- **Uoinked corpora** — `%USERPROFILE%\Desktop\Uoink\<topic>\<slug>\` (an upgraded install may keep a pre-rename `%USERPROFILE%\Desktop\Yoink\` until you opt in to move it). Plain markdown + JSON + screenshots. Yours to read, edit, delete.
- **Library index** — `%LOCALAPPDATA%\Uoink\index.db`. SQLite database with FTS5 search index, taxonomy classifications, entity graph, queue, and corrections. Local-only; never transmitted.
- **Anthropic API key** — Windows Credential Manager, via Python `keyring`. Service `Uoink` (migrated from the legacy `Yoink` service on first launch), username `anthropic_key`. Never stored in plaintext in any settings file.
- **ScrapeCreators API key** — Windows Credential Manager, via `keyring`,
  username `scrapecreators_key` in the same service. Isolated profiles use
  `Uoink-isolated-<hash>` for both keys, with no fallback to the normal profile.
- **Discovery runs** — `discovery\runs\<YYYY-MM>\<run_id>.json` beneath the
  local data folder. These store the submitted query, handle or channel_id;
  run identity, provider, endpoint, mode, platform and fetch time; credit counts,
  daily cap and page/item coverage; normalized candidates (URLs, IDs, author,
  caption, publication time, duration and metrics), computed baselines, queue
  receipts and capture state. Standard error envelopes are also stored for
  partial and failed runs. Raw vendor responses, thumbnails and API keys are
  not stored in run files. All these run records are removed by the daily purge
  once older than 90 days. Local playbooks may reuse eligible snapshots up to
    30 days old. Local library lookup or credit-summary errors do not discard
    fetched candidates. If saving a fetched run fails, its normalized results are
  returned to the dashboard and retained in helper memory until a local save
  succeeds or the helper exits. The dashboard shows the save failure and can
  retry saving without another provider request. Deleted and unavailable
  captures are shown separately from failed capture attempts.
- **Soft-deleted uoinks** — when you delete a uoink from the Memory page, the folder moves to `%USERPROFILE%\Desktop\Uoink\_yoink-trash\<topic>\<slug>__deleted-<timestamp>\`. The content remains readable on disk for 30 days, then is automatically purged by the helper on startup or every 24 hours thereafter. To delete immediately, manually remove the folder from `_yoink-trash`.
- **Helper state** — `server.log`, `token.txt`, `server.pid`, the v2.1 migration markers (`.migration-complete`, `.migrated-from-yoink`), and migrated legacy files (`jobs.json.migrated`, `taxonomy.json.migrated`) live alongside `index.db` under `%LOCALAPPDATA%\Uoink\`.

Library text leaves your machine through Uoink's Anthropic integration only
with your saved key, for the automatic analysis you turn on or an on-demand
AI action that you or a connected agent start (see section 2).

## 3. Your API keys

Optional AI features use your own Anthropic key; optional discovery uses your
own ScrapeCreators key. Uoink stores both in **Windows Credential Manager**,
the operating system's encrypted credential store. Neither key is kept in
plaintext, written into `settings.json`, or returned by `GET /settings`.

Your Anthropic key goes only to `api.anthropic.com` in the request header for
automatic analysis you enable, a key test, or an on-demand AI action that you
or a connected agent start. Turning off automatic analysis does not disable
those agent-requested calls with the saved key. Your ScrapeCreators key goes
only to `api.scrapecreators.com` in the `x-api-key` header for a confirmed,
authorized discovery call or balance test. There is no Uoink cloud server
that receives either key.

## 4. Your control over your data

- **Clear your API key at any time** from dashboard Settings > AI features. If
  Anthropic rejects the key (for example, an expired key), Uoink also
  clears it automatically.
- **Disable automatic AI analysis at any time** from dashboard Settings > AI features.
  Key tests and on-demand AI actions (agent-requested Comment Intelligence or
  Hook Type analysis, Writing Studio saved-key generation and research
  playbook runs) remain separate actions. Clear your saved key to prevent
  any of them from using Uoink's Anthropic route.
- **Clear the ScrapeCreators key and turn discovery off** in settings to stop
  paid discovery. Agent discovery has its own off-by-default setting. A
  ScrapeCreators 401/403 marks the key invalid but keeps it until you replace
  or clear it. Previously saved candidates can still be queued with a new
  dashboard intent or enabled agent consent; that action uses no SC credits.
- **Uninstall Uoink at any time.**
  To fully remove Uoink and its data:
  1. Remove the extension from `chrome://extensions/`.
  2. Uninstall the helper from Windows Settings → Apps.
  3. Optionally delete `%LOCALAPPDATA%\Uoink\` and
     `%USERPROFILE%\Desktop\Uoink\` to remove all Uoink-managed data,
     including the index, trash, and uoinked corpora. (A pre-rename install
     may also leave `Yoink` copies for up to 7 days before the helper removes
     them.)

## 5. Third parties

Uoink contains no data brokers, analytics SDKs, advertising networks, or
third-party trackers. The third parties it can contact are the source service
you ask it to capture (for example YouTube, Reddit, X, or a supplied web/feed
host), Anthropic for enabled automatic analysis, key tests or AI actions that
you or a connected agent start with your key, ScrapeCreators for authorized
discovery or balance checks after you enable it, Hugging Face for model
loading during requested speaker labeling, and GitHub when you request an
update check. Their handling of request data is governed by their own
policies and, where applicable, the terms of your account.

## 6. Children

Uoink is a productivity tool for capturing and analyzing source material. It is
not directed at children under 13. Uoink has no age gate because it
collects no personal information from anyone — there is nothing to
age-gate.

## 7. Changes to this policy

This repository copy is a draft and is not yet effective. Before a policy
update takes effect, its header will name the version and effective date. A
material change to how Uoink handles data will also be communicated through an
in-app notice or the release notes of the extension update that introduces it.

## 8. Contact

Questions, concerns, or corrections: **hi@uoink.video**

---

*Uoink is free and open source (MIT-licensed). You can read exactly what
it does in the source code at https://github.com/ryanbiddy/uoink.*

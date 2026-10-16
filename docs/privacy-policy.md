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
that source, GitHub only when you click **Check now**, and Anthropic only
with your own API key: for automatic AI analysis you turn on, a key test,
or an AI action that you or a connected agent start on demand. The
rest of this document names those requests and the local data they create.

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
    playbook runs (**Run** in the dashboard without a connected agent), which
    send the playbook instructions and a bounded packet from your library
    relevant to that playbook, such as titles, channel and creator names,
    URLs, chapters, transcript excerpts, top comments, earlier analysis
    summaries and metrics, plus active writing style anchors for repurposing.
  - *A key test* when you choose to test your key (it sends only a short
    test message, no library text).

  Each on-demand action makes its own paid request (Comment Intelligence and
  Writing Studio may retry once, so one action can make two); a saved key
  starts nothing by itself. Local MCP playbook packets and copying a prompt make no
  Anthropic request from Uoink. The dashboard Research controls are still
  pending.
- **GitHub release check — only when you click `Check now`.** The dashboard
  requests the latest Uoink release record from `api.github.com`. It sends no
  corpus content or usage event. GitHub receives the normal request metadata.

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
- **Soft-deleted uoinks** — when you delete a uoink from the Memory page, the folder moves to `%USERPROFILE%\Desktop\Uoink\_yoink-trash\<topic>\<slug>__deleted-<timestamp>\`. The content remains readable on disk for 30 days, then is automatically purged by the helper on startup or every 24 hours thereafter. To delete immediately, manually remove the folder from `_yoink-trash`.
- **Helper state** — `server.log`, `token.txt`, `server.pid`, the v2.1 migration markers (`.migration-complete`, `.migrated-from-yoink`), and migrated legacy files (`jobs.json.migrated`, `taxonomy.json.migrated`) live alongside `index.db` under `%LOCALAPPDATA%\Uoink\`.

Library text leaves your machine through Uoink's Anthropic integration only
with your saved key, for the automatic analysis you turn on or an on-demand
AI action that you or a connected agent start (see section 2).

## 3. Your Anthropic API key

If you use the optional AI features, you supply your own Anthropic API
key. Uoink stores that key in **Windows Credential Manager**, the
operating system's encrypted credential store. It is not kept in
plaintext, and it is not written into Uoink's settings file.

Your key is never transmitted anywhere except to Anthropic
(`api.anthropic.com`), in the authorization header of the API calls you
asked Uoink to make. Uoink itself never receives or stores your key on
any server — there is no Uoink server to receive it.

## 4. Your control over your data

- **Clear your API key at any time** from the Uoink setup page. If
  Anthropic rejects the key (for example, an expired key), Uoink also
  clears it automatically.
- **Disable automatic AI analysis at any time** from the setup page.
  Key tests and on-demand AI actions (agent-requested Comment Intelligence or
  Hook Type analysis, Writing Studio saved-key generation and research
  playbook runs) remain separate actions. Clear your saved key to prevent
  any of them from using Uoink's Anthropic route.
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
host), Anthropic when you opt into an AI feature, and GitHub when you request
an update check. Their handling of request data is governed by their own
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

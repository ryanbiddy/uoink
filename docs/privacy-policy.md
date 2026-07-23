# Uoink Privacy Policy

**Version 2.1 — effective 2026-XX-XX**

This policy explains exactly what Uoink does and does not do with your
data. It is written to be read, not to be skimmed past. If anything here
is unclear, email us (see *Contact* below).

> Uoink was previously named Yoink. The magnet logo was always a U. Nothing
> about how your data is handled changed in the rename.

## The short version

Uoink does not collect anything about you. There is no Uoink account, no
Uoink server in the cloud, no analytics, and no telemetry. Uoink runs on
your own machine, talks to YouTube to do its job, and — only if you turn
on the optional AI features — talks to Anthropic using an API key you
provide. That's the whole story. The rest of this document is detail.

## 1. What Uoink collects about you

Nothing.

Uoink has no user accounts, no sign-in, and no usage tracking. It does
not phone home. The local helper writes a diagnostic log to
`%LOCALAPPDATA%\Uoink\server.log` on your own computer to help you
troubleshoot; that log never leaves your machine and is never sent
anywhere.

## 2. What leaves your computer, and when

Two things, and only two:

- **YouTube requests — always.** To extract a video's transcript,
  screenshots, comments, and metadata, Uoink downloads that public data
  from YouTube. This is the one network call Uoink cannot do without. It
  happens every time you uoink a video.
- **Anthropic API requests — only if you opt in.** If you enable
  *Comment Intelligence* or *Hook Type classification* **and** provide
  your own Anthropic API key, Uoink sends the relevant video text
  (comments or transcript opening) to Anthropic's API to be analyzed.
  These features are off by default. If you never turn them on, Uoink
  never contacts Anthropic.

Nothing else leaves your machine. No analytics. No telemetry. No usage
tracking. No crash reporting. The extracted corpus, screenshots, and
files are written only to folders on your own computer.

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

None of this data leaves your machine unless you explicitly enable an optional AI feature that calls the Anthropic API with your key.

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
- **Disable any AI feature at any time** from the setup page. With them
  off, Uoink makes no Anthropic calls at all.
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

Uoink shares data with exactly one third party, and only when you
choose to use the optional AI features: **Anthropic**, the provider of
the Claude API. Their handling of that data is governed by Anthropic's
own privacy policy and the terms of your Anthropic account.

Uoink contains no data brokers, no analytics SDKs, no advertising
networks, and no third-party trackers of any kind.

(Separately, extracting a video necessarily contacts **YouTube** to
download its public data — the same as visiting the video in your
browser.)

## 6. Children

Uoink is a productivity tool for analyzing YouTube videos with AI. It is
not directed at children under 13. Uoink has no age gate because it
collects no personal information from anyone — there is nothing to
age-gate.

## 7. Changes to this policy

This policy carries a version number and effective date at the top. If
we make a material change to how Uoink handles data, we will update the
version, and the change will be communicated through an in-app notice or
noted in the release notes of the extension update that introduces it.

## 8. Contact

Questions, concerns, or corrections: **hi@uoink.video**

---

*Uoink is free and open source (MIT-licensed). You can read exactly what
it does in the source code at https://github.com/ryanbiddy/uoink.*

# Chrome Web Store and MV3 audit, 2026-10-24

Scope: 3.11.0 extension, helper origin/configuration boundary, install prompts,
and store materials in this worktree. This is a source and offline runtime
audit, not a Google approval or a successful capture test against a store item.

## Identity decision

Google lists `key` as a supported [MV3 manifest field](https://developer.chrome.com/docs/extensions/reference/manifest).
Its [key guide](https://developer.chrome.com/docs/extensions/reference/manifest/key)
uses it to keep a development install's identity consistent with a draft store
item's public key. The current prepare, publish and program-policy pages do
not state a blanket requirement to remove this field from uploads. Keeping a
development key is not a documented way to assign the store item's identity.

Therefore, do not assume the uploaded item will keep
`bkcapfidedhfcjpmjabeopfbcjcbmdmi`. Use the draft Item ID Google supplies.
The builder omits `key` as a conservative packaging choice, not because these
docs establish that every manifest key is forbidden. The source key remains
at `extension/manifest.json:3`; the developer pin remains at `server.py:353`.

The only new identity/link configuration is `extension/store-config.json:1`.
`uoink_store.py:12` validates a store ID as exactly 32 letters a through p and
ties any store URL to that ID. Invalid/missing config fails closed.
`server.py:356` adds the store ID to the existing pin and configured extra IDs.
`server.py:13501` still matches a complete origin and checks set membership.
No wildcard, suffix, prefix, path or port-based extension-origin approval was
added. The exact YouTube origins in `ALLOWED_ORIGINS` at `server.py:332` remain
unchanged. `tests/test_sec_token_pin.py` covers developer, store and malformed
origins, including authentication and CORS.

## Policy findings

The applicable [program policies](https://developer.chrome.com/docs/webstore/program-policies/policies)
require a clear single purpose, minimal permissions, accurate disclosures,
Limited Use and reviewable MV3 code. Server-side data processing is allowed;
remote executable extension logic is restricted. These are the findings for
this code, rather than a promise of approval.

| Area | Finding and file evidence | Action/status |
|---|---|---|
| Single purpose | Capture a selected source into a local research library. `extension/manifest.json:7`, `extension/background.js:192`, `extension/popup.js:833`, `extension/lib/extract.js:335`. | Listing leads with capture and makes the Windows helper requirement prominent. Avoid selling the whole helper tool catalog as unrelated extension purposes. |
| MV3 | Packaged service worker at `extension/manifest.json:43`; bundled imports at `extension/background.js:20`; no persistent background page. | Ready. Health alarms now use 0.5 minutes at `extension/background.js:67`, matching modern Chrome's minimum. |
| Remote code | CSP uses self for script/object/font sources at `extension/manifest.json:47`. HTML script sources are local at `extension/popup.html:148`, `extension/setup.html:132`, `extension/offscreen.html:12`. `extension/popup.js:62` injects a local function; `extension/background.js:1413` injects bundled files. | No eval, Function constructor, remote script, downloaded WASM, executable response interpreter or source-map link found in the shipped scripts. Prompts and helper responses are data. |
| Production package | `scripts/build_cws.py:16` lists every shipped file. `extension/lib/extract.js:12` sets USE_MOCK_API false; `extension/lib/extract.js:450` prevents activation through globals. | Mock module excluded, unexpected files rejected, fixed ZIP timestamps/order and a hash receipt. No helper files or store artwork in the ZIP. |
| Local helper | `extension/lib/extract.js:10` and `extension/setup.js:4` use 127.0.0.1:5179. Token bootstrap is at `extension/lib/extract.js:41`; exact origin check at `server.py:13501`; Host validation uses `server.py:346`. | Reviewer instructions explain the local HTTP connection and protected calls. Do not describe a browser host grant as the authentication boundary. |
| Missing helper | `extension/setup.js:84` controls setup availability; `extension/popup.js:817` sets Offline and disables captures. | Confirmed in an extracted copy of the upload ZIP, with no helper contacted. Browser records expected failed requests; no JavaScript errors or warnings in the final run. |
| Data use | Token/local storage at `extension/lib/extract.js:22`; sync interval at `extension/lib/extract.js:271`; saved failure URLs at `extension/popup.js:614`; thumbnail at `extension/popup.js:728`; Claude tab at `extension/background.js:1354`. | Privacy form explicitly covers content, selected URLs/titles, authentication and activity. Removed the old inaccurate "No browsing data" storage justification. |
| Optional usage counts | Endpoint at `uoink_usage.py:33`, opt-in state at `uoink_usage.py:145`, bounded payload at `uoink_usage.py:350`, POST at `uoink_usage.py:447`. | Listing/form match the live policy's opt-in counts. Do not promise zero network traffic or conflate helper model telemetry with this switch. |
| Limited Use | Usage counts support product operation; captures serve the disclosed purpose. No ads, sale, creditworthiness use or unrelated extension-data transfer found. Public-policy snapshot: `_scratch/cws/privacy-live.html`. | **Before submission:** publish the affirmative Limited Use statement prepared in `docs/store/privacy-practices.md`. It was absent from the live page. |
| Store metadata | Existing image files in `docs/store/screenshots/` show July UI; the prior listing said 3.2.8. | Text refreshed for 3.11. Recapture plan in `SCREENSHOTS.md`; old images remain reference-only. |
| Review authentication | New store ID is loaded at `server.py:360`. Existing public installer predates this work. | **Before submission:** Ryan must create the item, paste its ID and release the matching helper. The health probe alone does not prove capture authentication. |

Google's [User Data FAQ](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq)
requires disclosure even for local-only handling. The live
[uoink.app policy](https://uoink.app/privacy) was fetched with HTTP 200 on the
audit date. It includes opt-in usage counts, browser sync, source requests,
thumbnails, the Claude tab, Anthropic, ScrapeCreators and model telemetry.
Its receiver-retention statements were read, not independently audited.
The repository privacy draft still has historical text; it is not the CWS URL.

## Permission evidence

| Permission | Live use | Decision |
|---|---|---|
| alarms | `extension/background.js:67`, alarm listener at `:117` | Keep. Helper status/badge. |
| clipboardWrite | `extension/offscreen.js:30`; capture-to-offscreen handoff at `extension/background.js:714` | Keep. Write requested capture, no clipboard reads. |
| notifications | `extension/background.js:562` and notification actions at `:644` | Keep. Outcomes and recoverable capture failures. |
| storage | `extension/lib/extract.js:29`, `:271`; queue at `extension/background.js:810` | Keep. Token, preference, session and capture state. |
| contextMenus | `extension/background.js:192`, click listener at `:279` | Keep. Explicit right-click capture. |
| activeTab | `extension/popup.js:136`, `:62`, `:729` | Keep. Current URL and selected-page metadata/feed inspection. |
| scripting | `extension/popup.js:62`, `:102`, `:731`; `extension/background.js:1413` | Keep. Bundled functions/files, invoked from user actions. |
| offscreen | `extension/background.js:679`, `extension/offscreen.js:8`, `:21` | Keep. Clipboard and media-query support unavailable in the worker. Startup race fixed and regression-tested. |

| Host grant | Evidence | Decision |
|---|---|---|
| www.youtube.com, m.youtube.com | `extension/manifest.json:51`, `extension/content.js:1`, `extension/popup.js:136` | Keep for supported tabs and in-page capture, including SPA navigation. |
| x.com, twitter.com | `extension/manifest.json:86`, `extension/content-x-article.js:207`, `extension/background.js:1413` | Keep for visible article parsing and reinjection into existing tabs. |
| *.reddit.com | `extension/manifest.json:69`, `extension/content-reddit.js:295` | Keep for Reddit thread capture on site variants. |
| 127.0.0.1:5179 | `extension/lib/extract.js:10`, `extension/setup.js:4` | Keep for the required local API. |
| youtu.be, mobile.twitter.com | Normalization/menu patterns in `extension/lib/extract.js:145`, `:177`, `extension/background.js:39`; no script runs or extension fetches on these hosts. | Removed. Link capture still works through activeTab/context-menu selection and helper processing. |
| localhost:5179 | All extension network bases are the literal 127.0.0.1 endpoint. | Removed. Helper-side exact localhost Host support remains for other local clients. |

Content-script matches still grant site access on YouTube, X aliases and Reddit
threads. No new sites were added. The Reddit subdomain wildcard is a website
match pattern, not a wildcard helper origin check.

## Likely reasons for closer review

These are risk assessments, not known decisions from Google. Its
[review guide](https://developer.chrome.com/docs/webstore/review-process)
names new developers/items and powerful permissions as review-time factors.

1. **Required native helper and local HTTP.** A reviewer cannot complete a
   capture from the extension alone. Provide the source repository, direct
   helper download, no-credentials test steps, exact-ID setup and clear offline
   state. Explain the JSON boundary, Host/origin checks and loopback scope.
   This is an extension, not a deprecated packaged Chrome App; do not apply the
   policy subsection for packaged/hosted Apps as an automatic extension ban.
2. **scripting, offscreen, clipboard and persistent site access.** Keep the
   granular justifications, readable source and strict package list. Explain
   that content scripts wait for the user's capture action. A future redesign
   could make site access optional, but would change the always-visible buttons.
3. **YouTube/media capture and logged-in X Articles.** Test with owned or
   licensed material. Describe transcripts, research and source credit accurately.
   Do not advertise bypassing access controls or unauthorized media downloads.
   Google may examine the helper's retrieval behavior too.
4. **Optional services and telemetry.** The live policy is broader than the
   extension alone. Keep the listing and form consistent with it, make opt-in
   counts clear, and publish Limited Use before submission. Do not hide model
   telemetry behind claims that everything stays offline.
5. **Misleading screenshots or helper version mismatch.** Replace July UI
   images and test the actual download with the draft identity. An Offline
   screen is an honest fallback, not evidence that the full product works.

The current materials reduce these risks; they cannot guarantee acceptance.

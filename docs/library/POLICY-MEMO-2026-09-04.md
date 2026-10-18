# Platform policy memo (Living Library decisions 4, 5, 9)

**Author:** grok · **Read date:** 2026-09-04 · **Not legal advice.** Quotes are from the vendor pages fetched that day.

Ryan's contract: status-quo yt-dlp capture from a home residential IP at low rate; detection and capture stay separable; per-source opt-in, default off; back-catalog cap 25 / daily ingest cap 10 (placeholders); Twitch notify-only; X watching deferred.

## Verdict

| Question | Answer |
|---|---|
| Does anything read today make **decision 4 untenable**? | **No.** YouTube's consumer ToS is still the 15 Dec 2023 text. Automated access and downloading were already banned when status-quo capture was chosen. The official caption API still cannot fetch third-party tracks. |
| What would make decision 4 untenable later? | A ToS change that adds X-style liquidated damages; a written C&D against personal-library caption fetch; or a working official path that covers third-party captions (none exists today). |
| Residual risk decision 4 accepts | yt-dlp caption fetch is a **contract breach** of YouTube ToS Permissions and Restrictions (1), (2) and (3). Keep it on a residential IP, opt-in, capped. Never from a cloud IP. |
| Decision 5 (consent caps) | Fits every source. Not required by any ToS; they are the product control that keeps a watcher from looking like bulk harvest. |
| Decision 9 | Confirmed by current Twitch and X terms. |

---

## YouTube channel RSS (detection only)

| | |
|---|---|
| What | Poll `https://www.youtube.com/feeds/videos.xml?channel_id=UC…` for new public uploads. Metadata only. No video, no captions. |
| Terms allow? | **Not as a watcher.** Consumer ToS bans accessing the Service "using any automated means (such as robots, botnets or scrapers)" except public search engines following `robots.txt`, or prior written permission. |
| Exact cite | YouTube Terms of Service, **Your Use of the Service → Permissions and Restrictions (3)**. Effective **15 Dec 2023**. URL: https://www.youtube.com/t/terms?hl=en&gl=US&override_hl=1 · read 2026-09-04. Quote: "access the Service using any automated means (such as robots, botnets or scrapers) except (a) in the case of public search engines, in accordance with YouTube’s robots.txt file; or (b) with YouTube’s prior written permission." |
| robots.txt | `User-agent: *` / `Disallow: /feeds/videos.xml`. Fetched https://www.youtube.com/robots.txt on 2026-09-04. A uoink watcher is not a public search engine, so the ToS exception does not apply, and the path is disallowed for `*`. |
| API overlay | YouTube API Services Terms (last updated 2026-04-28, https://developers.google.com/youtube/terms/api-services-terms-of-service) + Developer Policies III.D.7 (last updated 2026-06-24, https://developers.google.com/youtube/terms/developer-policies): "You must not use undocumented APIs without express permission. You must access data from YouTube API services only according to the means stipulated in the authorized documentation." Channel RSS is not a Data API method. |
| Posture | **Detection-only, per-source opt-in, default off, cap 25 back-catalog / 10 per day.** Poll on a human RSS cadence (minutes, not the 30-second podcast tick). Do not follow into capture automatically unless that source is opted in. Separable from decision 4. |
| Makes D4 untenable? | No. Detection is not capture. |

---

## yt-dlp caption capture (residential IP)

| | |
|---|---|
| What | Status-quo helper: yt-dlp fetches public caption / timed-text tracks (and, when needed, audio for local ASR) from a home residential IP at low rate. |
| Terms allow? | **No.** Three independent bans, all still live. |
| Exact cite (download) | YouTube ToS, Permissions and Restrictions **(1)**. Effective 15 Dec 2023. Same URL as above, read 2026-09-04. Quote: "access, reproduce, download, distribute, transmit, broadcast, display, sell, license, alter, modify or otherwise use any part of the Service or any Content except: (a) as expressly authorized by the Service; or (b) with prior written permission from YouTube and, if applicable, the respective rights holders." Personal viewing is authorized; bulk download of caption files is not. |
| Exact cite (automation) | Same section **(3)**, quote in the RSS table. yt-dlp is automated access. |
| Exact cite (circumvention) | Same section **(2)**. Quote: "circumvent, disable, fraudulently engage with, or otherwise interfere with any part of the Service (or attempt to do any of these things), including security-related features or features that (a) prevent or restrict the copying or other use of Content or (b) limit the use of the Service or Content." PO-token / botguard workarounds sit here. |
| Official caption API | `captions.download` "requires the user to have permission to edit the video." OAuth scopes `youtube.force-ssl` or `youtubepartner`. Last updated 2026-06-01. https://developers.google.com/youtube/v3/docs/captions/download · read 2026-09-04. There is **no** Data API path that downloads a third-party public caption track. |
| API audiovisual rule | Developer Policies **III.E.1 Audiovisual Content** (updated 2026-06-24): API clients must not "download, import, backup, cache, or store copies of YouTube audiovisual content without YouTube's prior written approval." https://developers.google.com/youtube/terms/developer-policies |
| Undocumented clients | Developer Policies **III.D.7**: no undocumented APIs. InnerTube / timedtext scraping is this. |
| Posture | **Keep decision 4: status-quo yt-dlp, residential IP, low rate, per-source opt-in, 25 / 10 caps.** Captions-first; media download only when captions are absent and the user opted that source in. Never run this from a datacenter IP. Do not wrap it as a YouTube API client. |
| Makes D4 untenable? | **No.** The bans are the same text as 2023. The official API still cannot replace it for other people's videos. Decision 4 is an accepted contract risk, not a newly broken plan. Revisit if YouTube adds liquidated damages or ships a viewer-accessible caption export. |

---

## Podcast RSS + enclosure download + local ASR

| | |
|---|---|
| What | Poll a publisher's RSS/Atom feed; download the `enclosure` the feed advertises; transcribe locally (WhisperX / existing helper). No vendor LLM. |
| Terms allow? | **Yes, as a podcast client, on an opted-in feed.** RSS 2.0 defines `<enclosure>` as the media object attached to the item (required attrs `url`, `length`, `type`; `url` must be http). Fetching that URL is the distribution mechanism podcast apps use. |
| Exact cite | RSS 2.0.11, **Elements of `<item>` → `<enclosure>`**. Published 30 Mar 2009, current spec. https://www.rssboard.org/rss-specification · read 2026-09-04. Quote: "`<enclosure>` is an optional sub-element of `<item>`. It has three required attributes. url says where the enclosure is located, length says how big it is in bytes, and type says what its type is, a standard MIME type. The url must be an http url." |
| Copyright | Each episode remains the publisher's work. The enclosure is an invitation to fetch a copy for listening. Local ASR of that personal copy, kept on disk, not republished, is the same class as a podcast app's "download for offline" plus notes. Feed-level `<copyright>`, paid/private RSS, and `<itunes:block>` still bind. |
| uoink already | `podcasts.py` treats `auto_ingest` as a separate per-feed flag, default off. Matches decision 5. |
| Posture | **Per-feed opt-in, default off, 25 back-catalog / 10 per day.** Download only the enclosure URL in the feed (no site scrape). Skip feeds that require credentials uoink does not have. Local ASR only. Do not upload episode audio to a vendor. |
| Makes D4 untenable? | No. This source class does not use YouTube. |

---

## Twitch

| | |
|---|---|
| What | Decision 9: **notify-only** when an opted-in channel goes live. No VOD grab, no live scrape, no ASR of Twitch. |
| Terms allow notify-only? | **Yes, via EventSub.** `stream.online` authorization: "No authorization required." App/webhook EventSub is the published interface. |
| Exact cite (EventSub) | Twitch EventSub Subscription Types, **stream.online**. https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/#streamonline · read 2026-09-04. Quote: "The `stream.online` subscription type sends a notification when the specified broadcaster starts a stream." Authorization: "No authorization required." |
| Terms allow VOD/live download? | **No.** |
| Exact cite (ToS) | Twitch Terms of Service, **§7 License**. Last modified **12 Aug 2026**. https://www.twitch.tv/p/en/legal/terms-of-service/ (canonical https://legal.twitch.com/en/legal/terms-of-service/) · read 2026-09-04. Quote: the license "does not permit you to engage in any of the following: … (d) use of any data mining, robots, or similar data gathering or extraction methods; (e) downloading (except page caching) of any portion of the Twitch Services, the Materials, or any information contained in them, except as expressly permitted on the Twitch Services; or (f) any use of the Twitch Services or the Materials except for their intended purposes." |
| Posture | **Notify-only.** EventSub `stream.online` / `stream.offline` on opted-in broadcaster IDs. Surface a "live now" notice. Do not download VODs, clips, or HLS. Caps 25 / 10 are unused here because nothing is ingested. |
| Makes D4 untenable? | No. Twitch is decision 9, not 4. |

---

## X

| | |
|---|---|
| What | Decision 9: **watching deferred.** Existing paste-a-URL capture is not a standing watcher and is out of this memo's build. |
| Terms allow a watcher? | **No, unless it is the official X API under the Developer Agreement.** Scraping / browser automation is a permanent-suspension offense. Nitter is dead (C&D Aug 2026); there is no remaining public HTML/RSS path. |
| Exact cite (ToS) | X Terms of Service (US), Restrictions. PDF dated **10 Apr 2026**: https://cdn.cms-twdigitalassets.com/content/dam/legal-twitter/site-assets/x-terms-of-service-2026-04-10/en/x-terms-of-service-2026-04-10.pdf · HTML https://x.com/tos. Quote: "access or search or attempt to access or search the Services by any means (automated or otherwise) other than through our currently available, published interfaces that are provided by us (and only pursuant to the applicable terms and conditions), unless you have been specifically allowed to do so in a separate agreement with us (NOTE: crawling or scraping the Services in any form, for any purpose without our prior written consent is expressly prohibited)." |
| Exact cite (developer rules) | X Developer Guidelines, **Data & Research** and **Prohibited activities**. https://docs.x.com/developer-guidelines · read 2026-09-04. Table row: "App scrapes X via browser automation (not API)" → "**Permanent suspension** — API only." Prohibited: "Non-API Automation: Browser scripting, scraping, any automation outside official API." Automated accounts: "Use only the official X API. No scraping, browser automation, or unofficial methods. Violations result in permanent suspension." |
| Liquidated damages | Same US ToS: $15,000 per 1,000,000 posts accessed in a 24-hour period in violation. This is the clause YouTube still lacks. |
| Posture | **Deferred.** No RSS, no Nitter, no GraphQL scrape, no headless browser. Reopen only if there is a paid official API path that licenses storing posts in a user-owned library (Developer Agreement 27 Apr 2026 still forbids training on X data except Grok; storage/redistribution limits still apply). |
| Makes D4 untenable? | No. X is decision 9. Do not analogize YouTube risk to X: X added liquidated damages; YouTube has not. |

---

## Consent caps (decision 5) against these terms

| Cap | Why it is in the posture |
|---|---|
| Per-source opt-in, default off | Matches existing `podcast_feeds.auto_ingest`. Makes every watcher a user action, which is the only honest reading of "expressly authorized" / "intended purposes." |
| Back-catalog 25 | Stops a newly opted-in channel from looking like a bulk archive job. Placeholder; tune after Phase 3. |
| Daily 10 per source | Keeps residential YouTube capture in a human-viewer band. Placeholder; tune after Phase 3. |

Neither cap legalizes yt-dlp. They only keep the accepted ToS risk small and reversible.

---

## Addendum: FxTwitter v2 enrichment (SEC-05), 2026-09-04

**No code in this increment.** Capture still calls `fetch_fxtwitter_status_json` on every X post (`x_extractor.py:156–175`). This page is the posture for a later flag, not that flag.

### What leaves the machine today

| | |
|---|---|
| Trigger | Every successful syndication fetch in `fetch_tweet_json`, not only truncated posts. |
| Request | HTTP GET `https://api.fxtwitter.com/2/status/{tweet_id}` |
| Data in the URL | The numeric tweet id. No handle, no post body, no cookies, no X auth token. |
| Headers | `User-Agent: Uoink (+https://uoink.app)`; `Accept: application/json` |
| Also leaves | The home machine's source IP, TLS SNI `api.fxtwitter.com`, and the fact that this user just saved that tweet. |
| What comes back | JSON. If `code==200`, the id matches, and `status.text` is longer than syndication text, the helper **overwrites** local post text (`_merge_fxtwitter_full_text`). A third-party compromise can poison the corpus. |
| Failure | Any HTTP/URL/JSON error returns `None`; syndication text is kept. |

FxTwitter (FixTweet) is a community unofficial JSON API, not an X product.

### Recommended opt-in posture

| | |
|---|---|
| Settings key | `fxtwitter_enrichment_enabled` |
| Default | **off** |
| When off | Syndication only. Long posts that X truncates stay truncated. No `api.fxtwitter.com` call. |
| When on | User has opted into a third-party unofficial tweet-id lookup for full text. Still fail open to syndication. Do not treat FxTwitter as authoritative identity. |
| Why default off | IP + tweet-id leak, content-poisoning path, and X ToS (below). Matches decision 5's opt-in pattern and decision 9's "no unofficial X path" spirit. Paste-a-URL capture can ship without this supplement. |

Do not grandfather current auto-call behavior. Same clean default-off as D-17.

### ToS position

| | |
|---|---|
| Does X allow this? | **No.** It is not a published X interface. |
| Exact cite (ToS) | X Terms of Service (US), Restrictions. PDF dated **10 Apr 2026**: https://cdn.cms-twdigitalassets.com/content/dam/legal-twitter/site-assets/x-terms-of-service-2026-04-10/en/x-terms-of-service-2026-04-10.pdf · HTML https://x.com/tos. Quote already in the X table: access or search other than through "currently available, published interfaces" is prohibited; "crawling or scraping the Services in any form, for any purpose without our prior written consent is expressly prohibited." |
| Exact cite (developer rules) | X Developer Guidelines, Prohibited activities. https://docs.x.com/developer-guidelines · read 2026-09-04. "Non-API Automation: Browser scripting, scraping, any automation outside official API." Unofficial methods → permanent suspension. |
| Liquidated damages | Same US ToS: $15,000 per 1,000,000 posts accessed in a 24-hour period in violation. A personal-library lookup is not that volume; the clause is why X is not analogized to YouTube. |
| Decision 9 | Watching stays deferred. This addendum does not reopen a watcher. It is capture-time enrichment of a URL the user pasted. That is still unofficial access. |
| Makes D4 untenable? | No. YouTube and X are different contracts. |
| Recommended product reading | Keep paste-a-URL capture. Put FxTwitter behind `fxtwitter_enrichment_enabled`, default off. Reopen only for an official X API path that licenses storing posts in a user-owned library. |

Not legal advice. No live call to `api.fxtwitter.com` was made for this addendum.

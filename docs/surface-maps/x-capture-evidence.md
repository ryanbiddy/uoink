# X capture evidence

New X post and extension Article captures save `metadata.x_capture` in their JSON sidecar and index metadata. Read it through `get_evidence_card`, `get_library_item`, or `uoink call get_evidence_card video_id=<id>`. CLI JSON retains the structured evidence; CLI `--text` shows capture limits. Existing captures are not rewritten.

Each entry in `x_capture.posts` includes:

| Field | Meaning |
|---|---|
| `text_completeness` | `complete`, `truncated`, or `unknown`, for this post's text only |
| `text_completeness_reason` | The response signal used to choose that state |
| `capture_provider` | Provider of the retained text: `syndication`, `FxTwitter`, or `extension DOM` |
| `providers`, `provider_status` | Sources that supplied evidence and any failed supplement |
| `quote` | Quoted ID, author, URL, text, completeness, entities, metrics, and media; `null` when unavailable |
| `expanded_links`, `entities`, `raw_text` | Supplied URL expansions, mentions, hashtags, other entities, and FxTwitter facets |
| `media` | Photo URL and nullable alt text; video and GIF URLs, variants, and poster; supplied dimensions and format fields |
| `media_extra`, `attachments` | Other supplied media objects, polls, link cards, Articles, and community notes |
| `missing_parent` | Parent ID and the reason the walk stopped, or `null` |
| `engagement` | Likes, reposts, quotes, replies, views, and bookmarks. `null` means unavailable; `0` remains zero |

The markdown includes quote text, links, media descriptors, and missing-data disclosures. Links expand only from response entities or facets. There are no redirect lookups. The post route has no photo download step; `images` contains descriptors for sidecar persistence. This change adds no automatic media downloads.

The walker still visits only the shared post and earlier posts by that author, with the existing 25-ancestor cap. It does not capture descendants or a full conversation. Embedded parents receive the same FxTwitter supplement as separately fetched ancestors. Missing parents, unknown authors, other-author boundaries, cycles, and the cap all leave a marker. A failed supplement retains the evidence already received.

Longer text wins when sources disagree. An equal FxTwitter text can confirm completeness. A shorter response can add entities and media without replacing the retained text. A syndication `note_tweet` marker or trailing ellipsis marks truncation; the reason field identifies the signal. Syndication text without a conclusive signal stays `unknown`. Extension Article DOM text also stays `unknown`, since the parser cannot prove that collapsed or unloaded content was captured. A complete text field does not certify that all quotes, media, or metrics were supplied.

Full evidence cards include `x_capture`. When a card's byte budget requires shortening, the card retains capture disclosures and marks `x_capture` in `truncation.fields`, with `details_omitted: true` and a pointer to the saved sidecar. Source revisions include the supplied capture evidence. The `corpus.read/1` fixed-key objects and source identity remain unchanged; no new key is added to that v1 contract.

The response mapping is original Python based on the published MIT-licensed [FxEmbed v2 schema](https://github.com/FxEmbed/FxEmbed/blob/d0c0f6923752bba00c19a81686e0efab867bb47a/packages/atmosphere/src/types/api-schemas.ts) and [react-tweet response types](https://github.com/vercel/react-tweet/blob/cb5070e392fe707f43cdcfcddbd9e3972142eb43/packages/react-tweet/src/api/types/tweet.ts). No project code or new dependency was imported. `tests/fixtures/x_capture_evidence.json` contains synthetic saved responses derived from those schemas and the existing long-post fixture. Tests never request live provider responses.

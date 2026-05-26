# Yoink v2 Hook Type contract

Status: implemented in v2.0. Taxonomy capture moved into `index.db` in Sprint 15; A3 self-calibrating corrections added in Sprint 17.

## Overview

Hook Type is an optional BYO Anthropic-key feature that classifies a video's opening style after extraction. It uses the same saved Anthropic API key as Comment Intelligence, but has its own `hook_type_enabled` setting. Normal Yoink extraction works without it.

## Settings shape

`GET /settings` returns:

```json
{
  "ok": true,
  "settings": {
    "comment_intelligence_enabled": true,
    "hook_type_enabled": true,
    "smart_screenshot_picker_enabled": false,
    "clipboard_screenshot_cap": 4,
    "anthropic_key_set": true
  }
}
```

`POST /settings` accepts partial updates. Omitted fields keep their existing values:

```json
{
  "hook_type_enabled": true,
  "smart_screenshot_picker_enabled": false,
  "clipboard_screenshot_cap": 4
}
```

Field rules:

- `hook_type_enabled` defaults to `false`.
- `smart_screenshot_picker_enabled` defaults to `false`.
- `clipboard_screenshot_cap` defaults to `4`, accepts `0-12`, and controls single-video clipboard screenshot embedding only.
- Hook Type uses the existing Anthropic API key stored in the OS keyring.
- The key is never returned by `GET /settings`.

## Invocation flow

1. `_run_extraction()` writes the normal per-video `.md` and JSON sidecar.
2. `_start_comments_thread()` starts the existing comments fetch in the background.
3. Hook Type waits for that comments worker to finish updating the Top Comments section. It runs after comments are fetched, marked disabled, or marked unavailable.
4. If `hook_type_enabled` is true, an Anthropic key is set, and the video has a title or description, Yoink starts a Hook Type thread.
5. The thread calls `analyze_hook_type(context)` with:
   - video title
   - channel name
   - description
   - first 250 words of transcript
   - top comment, when comments were fetched
6. Sprint 17 fetches relevant past corrections from `taxonomy_corrections` and injects up to 8 as few-shot calibration anchors.
7. The analysis writes/replaces a Hook Analysis section near the top of the per-video markdown and patches the sidecar.

Playlist jobs do not wait for Hook Type. The combined playlist corpus snapshots whatever per-video hook sections exist when the job transitions to `completed`.

## Categories

The model must return exactly one lowercase snake_case category:

- `curiosity_gap`
- `question`
- `contrarian`
- `story_open`
- `promise_list`
- `demo`
- `authority`
- `stakes`
- `other`

## Corpus markdown format

Hook Type lands immediately after the existing metadata block, before the first horizontal rule:

```markdown
## Hook Analysis
<!-- HOOK_START -->
**Hook Type:** Curiosity Gap
**Analysis:** The intro promises a counter-intuitive answer that creates anticipation in the first 10 seconds.
<!-- HOOK_END -->
```

Markers make re-runs idempotent. If the markers already exist, the whole Hook Analysis block is replaced.

## Sidecar shape

The per-video JSON sidecar includes:

```json
{
  "hook_type_status": "pending|completed|failed|skipped",
  "hook_type": "curiosity_gap",
  "hook_explanation": "The intro promises a counter-intuitive answer that creates anticipation.",
  "hook_type_confidence": 4,
  "hook_type_error": null,
  "hook_type_updated_at": "2026-05-11T09:30:00"
}
```

Initial sidecar status is:

- `pending` when Hook Type is enabled, key is set, and title or description exists.
- `skipped` otherwise.

## Skip conditions

Hook Type skips silently when:

- `hook_type_enabled` is false.
- No Anthropic API key is set.
- The saved key was marked invalid after a 401.
- The video has no title and no description.

Skipped analysis must not turn a successful yoink into an error.

## Error handling

Anthropic 429, 5xx, network failures, invalid JSON, and unexpected response shapes:

- Log a short reason without the key.
- Write this failure section in place of Hook Analysis:

```markdown
## Hook Analysis
<!-- HOOK_START -->
Hook Type: analysis failed - <short reason>
<!-- HOOK_END -->
```

- Update the sidecar with `hook_type_status: "failed"` and `hook_type_error`.
- Do not retry automatically.

Anthropic 401:

- Clear the saved key and mark it invalid.
- Subsequent `GET /settings` returns `anthropic_key_set: false`.
- Comment Intelligence and Hook Type both skip until the user saves a key again.

## A3: Self-calibrating classification

Sprint 17 turns Hook Type into a self-calibrating classifier. The user can correct a classification in the popup, Yoink stores that correction locally, and future classifications receive relevant past corrections as few-shot calibration anchors.

### Correction flow

1. Popup renders a Hook Type chip with confidence, for example `Curiosity Gap · confidence 4/5`.
2. User clicks `wrong?`.
3. Popup shows a dropdown of the 9 Hook Type categories.
4. User chooses the corrected category.
5. Popup calls token-gated `POST /taxonomy/correct` with:

```json
{
  "video_id": "abc123DEF45",
  "corrected_hook_type": "story_open",
  "user_reason": ""
}
```

6. Backend appends a row to `taxonomy_corrections`.
7. Backend updates `taxonomy.hook_type` for the same `video_id`, making the corrected value canonical.
8. Setup renders recent corrections in the "Hook Type calibration" section via `GET /taxonomy/corrections?limit=20` when that endpoint is available.

Sprint 17 intentionally omits a free-text reason field in the popup. The endpoint accepts `user_reason` so a richer Sprint 17.5 UI can add it without changing storage.

### Similarity-based few-shot injection

Before a Hook Type call, Yoink looks up relevant corrections for the current video:

1. Same channel corrections first.
2. Same topic corrections second.
3. Most-recent corrections as a fallback.

The result is deduplicated and capped at 8 corrections. These are injected into the system prompt as examples like: "classifier said `promise_list`, user corrected to `story_open`." The prompt treats them as calibration anchors, not hard rules.

Concrete example: after 5 corrections on a channel where the user repeatedly disagrees with default `promise_list` calls and prefers `story_open`, subsequent classifications for that channel see those corrections before deciding. The classifier should start matching the user's preferred `story_open` framing when the opening really follows that pattern.

### Confidence scoring

Sprint 17 asks the model for an explicit confidence score from 1-5:

- `5`: very confident, hook clearly fits exactly one category.
- `4`: confident, mild ambiguity.
- `3`: moderate, hook could fit one of two categories.
- `2`: uncertain, borderline or likely `other`.
- `1`: guessing, no clear pattern.

The backend parses this as `confidence` on MCP `classify_hook`, stores it as `taxonomy.confidence`, and patches the sidecar as `hook_type_confidence`. Pre-Sprint-17 taxonomy rows have NULL confidence.

`classify_hook` also returns `similar_corrections_used`, the number of correction anchors included in the prompt. `0` means the classifier ran without prior user calibration.

### Local-only dataset

Corrections live in `%LOCALAPPDATA%\Yoink\index.db` inside the `taxonomy_corrections` table. They are local-first data, not uploaded to a Yoink service. The table intentionally becomes a labeled local dataset that can support v2.5 taxonomy and correction-analysis surfaces.

## Smart Screenshot Picker setting

`smart_screenshot_picker_enabled` is a backend-persisted UI preference for the popup's screenshot picker. Playlists remain text-only in the clipboard regardless of this flag.

## Aggregation

Starting in v2.0, every successful Hook Type classification is captured in `%LOCALAPPDATA%\Yoink\index.db` in the `taxonomy` table:

```json
{
  "video_id": "abc123DEF45",
  "hook_type": "curiosity_gap",
  "hook_explanation": "The opening creates anticipation by promising a counter-intuitive answer.",
  "channel": "Example Channel",
  "title": "A practical guide to creator research",
  "classified_at": "2026-05-11T09:30:00",
  "confidence": 4
}
```

Records dedupe by `video_id`: re-classifying the same video updates the existing taxonomy record instead of appending a duplicate. Legacy `taxonomy.json` is imported into `index.db` during Sprint 15 migration and renamed to `taxonomy.json.migrated`. Sprint 10 exposes the captured rows through token-gated `GET /taxonomy` and the MCP `get_taxonomy` tool.

# Prompt 2 — Metadata enrichment + corpus format rewrite

We are upgrading the corpus format to v1 spec. The current corpus has transcript + screenshots. The v1 spec adds: full metadata, video description, tags, top comments, thumbnail, and channel context.

## TASK 1 — METADATA EXTRACTION

In `server.py`'s `_run_extraction` function, before downloading the video for screenshots, run yt-dlp with `--dump-single-json --no-download` to get the full metadata blob. Parse it and extract:

- title
- channel (uploader)
- channel_id
- channel_url
- upload_date (format as ISO, "YYYY-MM-DD")
- duration (seconds, format for display as HH:MM:SS or MM:SS if under an hour)
- view_count
- like_count
- comment_count
- tags (list)
- description (full text)
- thumbnail (URL of highest-res available)
- chapters (if present — list of {start_time, title})
- channel subscriber count (channel_follower_count in yt-dlp output)

Cache this metadata blob — write it to `metadata.json` in the output folder so debugging later doesn't require re-downloading.

## TASK 2 — THUMBNAIL DOWNLOAD

After metadata extraction, download the thumbnail to `<output_folder>/thumbnail.jpg` using yt-dlp's `--write-thumbnail`. If yt-dlp gives you a webp, convert it to jpg via ffmpeg (we already have ffmpeg installed).

## TASK 3 — TOP COMMENTS

Run yt-dlp again with `--write-comments` and `--extractor-args "youtube:max_comments=100,all,all,all"` to fetch comments. (yt-dlp will write a `.info.json` file containing them.)

Parse the comments file and extract the top 50 by like_count, sorted desc. For each comment keep: author, text, like_count, timestamp_text (yt-dlp gives a "time_text" field like "2 weeks ago").

If comments fetching fails (some videos have comments disabled), don't fail the whole extraction — just write a "Comments are disabled on this video" note in the corpus and continue.

**IMPORTANT** — comments fetching can be slow for popular videos (30-90 seconds). Run it in a background thread and have the main extraction proceed without waiting. Write the corpus first WITHOUT the comments section, then when comments finish, append the comments section to the existing `yoink.md`. The user gets the transcript and screenshots fast, comments stream in shortly after.

## TASK 4 — CHANNEL CONTEXT

After the main video extraction succeeds, do one more lightweight yt-dlp call to fetch the channel's last 5 videos:

```
yt-dlp --flat-playlist --playlist-end 5 --dump-json <channel_url>
```

For each, capture: title, view_count, upload_date. Don't download anything.

Also extract the channel description (it's in the channel-level metadata — yt-dlp can fetch via the channel URL with the right extractor args).

## TASK 5 — RENAME OUTPUT FILE

Rename `combined.md` to `yoink.md` everywhere. Keep `transcript.txt` as-is. The clipboard payload is the contents of `yoink.md`.

## TASK 6 — REWRITE THE CORPUS FORMAT

Rewrite the markdown generation in `server.py` to produce this exact structure:

```markdown
# [Video Title]

**Channel:** [Channel Name] ([subscriber count formatted, e.g. "13.5K"] subscribers)
**Uploaded:** [YYYY-MM-DD] | **Duration:** [HH:MM:SS] | **Views:** [formatted, e.g. "29,142"] | **Likes:** [formatted]
**URL:** [original YouTube URL]
**Yoinked:** [ISO timestamp of extraction]
**Topic:** [auto-classified topic]

---

## Thumbnail

![Thumbnail](thumbnail.jpg)

## Description

[full description, preserved as-is]

## Tags

[tag1, tag2, tag3, ...] (or "No tags" if empty)

---

## Transcript

[00:00] [transcript line]
[00:15] [transcript line]
...

If the video has chapters, prefix each chapter section with:
### Chapter: [Chapter Title] ([start time])
[transcript lines for that chapter]

---

## Screenshots

### [00:00]
![Screenshot at 0:00](screenshots/shot_0001.jpg)

### [00:30]
![Screenshot at 0:30](screenshots/shot_0002.jpg)
...

---

## Top Comments

[If comments are still being fetched at write time, this section is initially:
"*Fetching comments... they'll appear here when ready.*"
Then appended/replaced when comments finish.]

**[Author 1]** ([N] likes, [time_text])
> [comment text, preserve line breaks]

**[Author 2]** ([N] likes, [time_text])
> [comment text]
...

[If comments disabled: "*Comments are disabled on this video.*"]

---

## Channel Context

**About [Channel Name]:**
[channel description]

**Recent videos from this channel:**
- [Title 1] ([formatted view count] views, [date])
- [Title 2] ([views], [date])
- [Title 3] ([views], [date])
- [Title 4] ([views], [date])
- [Title 5] ([views], [date])

---

*Yoinked with [Yoink](https://yoink.video) by ReplayRyan*
```

## TASK 7 — HELPER FUNCTIONS

Add helper functions for:
- `format_count(n)`: turns 13500 -> "13.5K", 1500000 -> "1.5M"
- `format_duration(seconds)`: turns 3725 -> "01:02:05", 245 -> "04:05"
- `format_subscribers(n)`: same as format_count

Use these consistently. No raw "13500" anywhere in user-facing output.

## TASK 8 — UPDATE THE CLIPBOARD PAYLOAD

The `/extract` endpoint returns `combined_md`. Rename to `yoink_md` in the JSON response. Update `extension/lib/extract.js` to read `response.yoink_md` instead of `response.combined_md`. Update `background.js` similarly.

## WHEN DONE

- Report what changed
- Print: `=== PROMPT 2 COMPLETE ===` so the orchestrator knows to advance

The user will then do a smoke test:
1. Restart the server
2. Reload the extension
3. Yoink a real YouTube video (pick something with comments enabled and a real channel — not a private/listed video)
4. Open the resulting `yoink.md` and verify ALL sections are populated: metadata, thumbnail, description, tags, transcript, screenshots, comments (may take 30-90 sec to appear), channel context
5. Verify the clipboard contains the full `yoink.md` content

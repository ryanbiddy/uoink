# BD-27 normal-browser player observation

**Player observation satisfied on 2026-09-08, approximately 17:22–17:25 PDT.**
Observer: Astra through the Windows computer-use runtime. Browser: the user's
normal Comet window, in a new tab. This is a Comet observation, not a Chrome
receipt. Authority: Ryan's explicit request and the
[normal-browser brief](PHASE6-BD27-NORMAL-BROWSER-BRIEF-2026-09-08.md), committed
at `e31f976`. The two prior automated Chrome/503 observations remain partial.

Opened the exact supplied [YouTube link](https://www.youtube.com/watch?v=D_FCYsshMI4&t=34s)
once. The page identified the video as **Computer use in Codex**, by OpenAI.
The first player screenshot shows **0:35 / 11:25** and the pause control, with
actual video imagery. Playback subsequently advanced to 1:03 before it was
paused. There was no observed advertisement, error or stalled-media screen.

Expanded the source description and observed **00:34 Why computer use**, followed
by **02:06 Codex works across local apps**. Clicking that 00:34 link within the
same loaded page returned to the passage and played; the next capture shows
0:36 and the pause control. This is within the frozen interval [34,126).
The requested link and source chapter therefore lead to observable playback.

For Ryan's requested still, the player was paused and positioned on the same
timeline until the displayed clock read **0:34**. That final image records a
manual still position; it is not presented as the initial autoplay frame.
The initial playing frame is retained separately at 0:35. These observations
do not measure subsecond seek accuracy or change the study's numeric results.

| Evidence | What is directly visible |
|---|---|
| [Initial playback](proof/bd-player-normal-2026-09-08/01-playing-0035.jpg) | Video title, 0:35 clock and pause control |
| [Source chapter list](proof/bd-player-normal-2026-09-08/02-chapter-list.jpg) | OpenAI source and “00:34 Why computer use” |
| [Chapter-link playback](proof/bd-player-normal-2026-09-08/03-chapter-link-playing-0036.jpg) | 0:36 after the source's chapter link |
| [Requested 0:34 still](proof/bd-player-normal-2026-09-08/05-paused-0034.jpg) | Paused video at displayed 0:34 |

All seven raw image/metadata artifacts are sealed in
[SHA256SUMS](proof/bd-player-normal-2026-09-08/SHA256SUMS). Images are unmodified
JPEG captures; their extensions match the returned encoding. Metadata times
record when the observation was written, not a separately measured capture
timestamp (`01-observation.json` uses the earlier label `observed_at`). The
images include browser chrome and are internal evidence, not a public export.

No reload, media download, login, like, comment, subscription, capture button,
resident-helper request or live-index operation was issued by this observer.
Existing browser tabs were preserved; the new tab is left paused at 0:34.
The normal browser's extensions were not changed. This is UI observation, not
a network trace of unrelated browser background activity.

Only the player-observation gate closes. Phase 6 implementation/review work,
legacy ticket-fixture ruling and speaker annotations remain outstanding.

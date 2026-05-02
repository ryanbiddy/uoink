# Prompt 4 — Polish, error states, smoke tests

Round off the rough edges. Better error messages, better notifications, the canonical visible-language pass.

## TASK 1 — ERROR STATES PASS

Audit every place the user could see an error message and rewrite for clarity + punchy voice. Examples of changes:

| Bad | Good |
| --- | --- |
| `Required tool not found on PATH: [WinError 2]...` | `Yoink can't find yt-dlp or ffmpeg. Install instructions: https://yoink.video/install` |
| `Server unreachable` | `Yoink server is offline. Start it from your system tray, or run start_server.bat from the install folder.` |
| `Failed to fetch` | `Yoink couldn't reach the local server. Make sure it's running.` |

Apply this pass to:
- extension notifications
- popup error messages
- server log messages that get shown to users
- `content.js` button error states

## TASK 2 — SUCCESS COPY PASS

Same pass for success messages. Use the punchy voice. Examples:

- "Yoinked! Paste in Claude with Ctrl+V."
- "Yoinked! Saved to: Social Media Research."
- "Comments still loading — they'll appear in yoink.md when ready."

## TASK 3 — SERVER STATUS IN POPUP

The popup currently has a server health indicator (green/red dot for `/ping`). Verify it works.

- If green, label it "Yoink is running."
- If red, label it "Yoink server is offline" with a one-line "How to start" link

## TASK 4 — TOPIC NOTIFICATION

When a yoink succeeds, the notification body should include the auto-classified topic:

> "Yoinked! Saved to: <topic>."

This helps the user notice when a video lands in `_Uncategorized` so they can refine `topics.json`.

## TASK 5 — POPUP COPY PASS

Make sure every visible string in `popup.html` is on-voice:

- Section headers in punchy voice
- Button labels: short, action-oriented
- "Recent yoinks" section if it exists, with the last 3 yoinks shown (title + topic + click-to-open-folder)

## TASK 6 — STARTUP MESSAGE

When the server starts, log this on the first line:

```
Yoink server v[VERSION] running on http://127.0.0.1:5179
Ready to yoink. Click any YouTube video's Yoink button.
```

## TASK 7 — VERSION CONSTANT

Set the server version to `1.0.0` (we're shipping v1 next weekend). Update `manifest.json` version to `1.0.0` too.

## WHEN DONE

- Report what was rewritten
- Print: `=== PROMPT 4 COMPLETE ===` so the orchestrator knows to advance

The user will then do a final smoke test:
1. Reload extension and restart server
2. Yoink a real video. Confirm everything works end to end
3. Stop the server. Try to yoink. Confirm the error message is the new clean version, not the old technical one
4. Restart server. Confirm popup health indicator updates correctly

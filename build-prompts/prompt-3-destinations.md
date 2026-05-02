# Prompt 3 — Generalize destinations + prompt library

## TASK 1 — TWO DESTINATION BUTTONS

The current single "Send to Claude" flow opens claude.ai/new with the clipboard loaded. Generalize this to two destinations.

In `extension/popup.html` and `extension/popup.js`:

- The popup, after a successful yoink, shows two buttons side by side: **"Send to Claude"** and **"Send to ChatGPT"**
- "Send to Claude" opens `https://claude.ai/new` in a new tab
- "Send to ChatGPT" opens `https://chat.openai.com/?model=gpt-4o` in a new tab
- Both rely on the clipboard already being loaded with `yoink_md`
- Both fire the existing toast notification ("Yoinked! Paste with Ctrl+V")

The in-page button under YouTube videos KEEPS its current behavior — it copies to clipboard and opens claude.ai/new directly. Don't change the in-page button to a chooser; that would slow the flow down.

The popup is where the user picks destination. Default-open the popup after a successful yoink (`chrome.action.openPopup` if available, otherwise rely on the user clicking the extension icon — Chrome MV3 has restrictions here, do your best).

## TASK 2 — RENAME THE BUTTON

Change the in-page button label from "Send to Claude" to **"Yoink"** in `extension/content.js`. Keep the same icon (or use a simpler one — your call). Width and styling stay the same.

Update success notification text from "Combined.md is in your clipboard..." to:

> "Yoinked! Paste with Ctrl+V in Claude or ChatGPT — the Yoink popup also has quick links."

## TASK 3 — PROMPT LIBRARY

Create `extension/prompts.json` with this content:

```json
[
  {
    "id": "decode-hook",
    "label": "Decode the hook",
    "prompt": "I just pasted a Yoink corpus from a YouTube video. Decode the hook of this video. What's the opening line, what emotional or curiosity lever does it pull, and how does the thumbnail/title/first 30 seconds work together? Be specific."
  },
  {
    "id": "outline-structure",
    "label": "Outline the structure",
    "prompt": "Outline the structure of this video with timestamps. Identify intro, hook, value proposition, demonstration, social proof, and call to action — or whatever sections actually exist. Note pacing changes."
  },
  {
    "id": "quotable-moments",
    "label": "Find quotable moments",
    "prompt": "Find the 3 most quotable moments in this video. For each, give me the timestamp, the exact quote, and one sentence on why it lands."
  },
  {
    "id": "would-improve",
    "label": "What would make this 2x better",
    "prompt": "What would make this video 2x better? Be specific and constructive — name what's working, what's underperforming, and what 3 changes would matter most."
  },
  {
    "id": "tactics-list",
    "label": "Pull every concrete tactic",
    "prompt": "Pull out every concrete tactic, technique, or piece of advice mentioned in this video. Group by theme. Cite timestamps."
  },
  {
    "id": "tools-mentioned",
    "label": "List tools and resources",
    "prompt": "List every tool, product, app, book, or resource referenced in this video. For each, note the timestamp and what context it was mentioned in."
  },
  {
    "id": "comment-themes",
    "label": "What are commenters saying",
    "prompt": "Analyze the top comments. What themes recur? What questions do viewers ask? What praise or criticism stands out? What does this tell us about what landed and what didn't?"
  },
  {
    "id": "plan-my-video",
    "label": "Help me plan a video on this topic",
    "prompt": "Based on this video, help me plan a video of my own on a similar topic. Suggest a hook, a structure, key points to hit, and what to avoid based on what this video did well or poorly. Ask me clarifying questions about my niche and angle before drafting."
  }
]
```

## TASK 4 — PROMPT LIBRARY UI

In `extension/popup.html`, add a "Quick Prompts" section below the destination buttons:

- Section heading: "After pasting, copy a starter prompt:"
- List of buttons, one per prompt, showing the label
- Click on a prompt button = copy that prompt to clipboard + show a small "Prompt copied! Paste in Claude after the corpus." toast
- A small "Edit prompts" link at the bottom of the section that opens the `prompts.json` file location in Explorer (so user can edit it without digging through the extension folder)

The popup stays compact. If the prompt list is too long, make the section scrollable rather than expanding the popup height.

## TASK 5 — PROMPTS.JSON IS USER-EDITABLE

Document in the README that users can edit `prompts.json` to add their own. The extension reads `prompts.json` at popup-open time, so changes take effect immediately on next popup open. No reload required.

## WHEN DONE

- Report what changed
- Print: `=== PROMPT 3 COMPLETE ===` so the orchestrator knows to advance

The user will then test:
1. Reload the extension
2. Yoink a video
3. Open the popup. Confirm "Send to Claude" and "Send to ChatGPT" both work
4. Click a prompt button. Confirm clipboard gets the prompt text
5. Open `prompts.json`, add a custom prompt, save. Reopen the popup. Confirm the new prompt shows up

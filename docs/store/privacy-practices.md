# Privacy practices form for 3.11

Use these answers with the public [privacy policy](https://uoink.app/privacy),
retrieved successfully on 2026-10-24. It covers opt-in usage counts, browser
sync, thumbnails, the Claude tab, optional AI, discovery and model telemetry.
Do not claim that all processing is offline or that no data is handled.
Google requires disclosure even for [data kept locally](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq).

## Form answers

- Single purpose: paste the Single purpose paragraph from `listing.md`.
- Permission justifications: paste from `permissions-justification.md`.
- Remote code: **No, I am not using remote code.** All extension JavaScript,
  HTML, styles and fonts are bundled. The helper returns data, not executable
  extension code. No remote scripts, eval or downloaded WebAssembly are used.
- Privacy policy URL: **https://uoink.app/privacy**.

Select these data types. Include optional handling and local storage, not
only information sent to Uoink's usage service.

| Dashboard data type | Answer | What is handled |
|---|---|---|
| Personally identifiable information | Yes | Author names and usernames in selected posts/comments; random install and report identifiers in optional helper usage reports. No Uoink account or identity profile is required. |
| Authentication information | Yes | The extension obtains and stores a local helper token. Optional service API keys belong to the helper, not a Uoink account. The extension does not read login cookies or passwords from websites. |
| Web history | Yes | URLs and titles of the current/selected source and recent captures, used to identify and save that source. No general record of sites visited. |
| User activity | Yes | Capture state and optional daily usage counts by tool, client, transport, source/result and searches. The counts do not contain keystrokes, mouse tracking or search text. |
| Website content | Yes | User-selected text, articles, comments, transcripts, metadata and supported images/frames. |
| Health information | No | Not requested as a data category or measured by Uoink. |
| Financial and payment information | No | No billing or payment data is collected by the extension. |
| Personal communications | No | No access to inboxes, chat histories or private-message APIs. Public source text is Website content. |
| Location | No | No geolocation API, address lookup or location tracking. Ordinary outside requests expose connection metadata to their destination. |

These are conservative product-wide disclosures, including the required
helper. Captured web text can incidentally contain sensitive information;
do not claim to strip or anonymize that source text.

Check all three certifications:

1. Data is not sold to third parties, outside the approved use cases.
2. Data is not used or transferred for purposes unrelated to the stated single purpose.
3. Data is not used or transferred to determine creditworthiness or for lending.

These form controls are described in Google's [privacy fields guide](https://developer.chrome.com/docs/webstore/cws-dashboard-privacy).

## Explanation for the reviewer

Selected source data goes to the local helper at 127.0.0.1:5179. Capture files
and the index stay on disk. The screenshot interval preference can use browser
sync. The extension can load source thumbnails and open Claude after copying;
it does not automatically paste or submit the captured material.

The helper sends Uoink usage reports only after opt-in. Reports contain bounded
counts and app details, including random IDs, app version, OS and processor
type, install type and reporting hours. They contain no captured content,
URLs, titles, paths, search text, prompts, keys or account details. The public
policy states the receiver keeps daily totals, no raw reports or IP addresses;
the hosting provider still sees connection IPs. This pass verified the published
statement, not the receiver's infrastructure.

Optional helper integrations have their own disclosures and controls in the
same policy. Automatic AI analysis starts off; an allowed on-demand agent
request can use a saved Anthropic key separately. Do not describe a disabled
automatic-analysis switch as blocking every AI request. Model-library telemetry
is separate from Uoink usage sharing.

## Required public Limited Use statement

The live policy did not contain an affirmative Chrome Web Store Limited Use
statement when checked. Add this text on `/privacy` before submitting:

> Uoink's use and transfer of user data complies with the Chrome Web Store User Data Policy, including its Limited Use requirements.

Link "Chrome Web Store User Data Policy" to
https://developer.chrome.com/docs/webstore/program-policies/policies#protecting_user_privacy.
This worktree includes the copy; it does not publish the website.

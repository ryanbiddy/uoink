# Surface Map: Honesty Disclosures & Disclaimers

This surface map documents the location and content of the brand-critical trust disclaimers and privacy disclosures added under **C-06**.

## Overview
To protect user trust and clarify the limits of local privacy guarantees, we plainly disclose all network boundaries, third-party terms of service, and site-level analytics.

## Disclaimers & Disclosures Locations

### 1. Main Project README
- **File**: [README.md](file:///E:/AI/projects/uoink/checkouts/Yoink/README.md)
- **Content**: Added a dedicated **Disclaimer & Terms of Use** section.
- **Wording**: Emphasizes that Uoink is for personal research/study, and the user is responsible for compliance with YouTube, Reddit, X (Twitter), and other source platforms.

### 2. Chrome Web Store Listing
- **File**: [store-listing.md](file:///E:/AI/projects/uoink/checkouts/Yoink/docs/store-listing.md)
- **Content**: Added the **Disclaimer & Terms of Use** statement prior to the requirements.

### 3. Website Privacy Policy
The orchestrator updates the website separately. The following describes the
new repository policy, not a verified change to the live website.

- **File**: [pages.ts](file:///E:/AI/projects/uoink/site/app/content/pages.ts) (under `privacy` section)
- **Content**: Uoink sends no usage data by default. If you turn on "Share anonymous usage counts", it sends daily counts to usage.uoink.app: calls by tool name, known MCP clients, stdio or HTTP calls, captures by source and result, and library searches. Reports include a random install ID, app version, operating system and major version, processor type, install type and hours counted. They never include content, URLs, titles, paths, search text, usernames, IP addresses or account details. Website analytics are separate from the local library and settings.
- **Update Check Disclosure**: Plainly details that the manual "Check now" updates button queries the `api.github.com` endpoints to compare tags, sending no telemetry or library data.

### 4. Website Terms of Use
- **File**: [pages.ts](file:///E:/AI/projects/uoink/site/app/content/pages.ts) (under `terms` section)
- **Content**: Expands the "Your responsibility" section to assert that Uoink is built for personal research and study, and users must follow platform terms of service.

### 5. Local Dashboard Settings
- **File**: [index.html](file:///E:/AI/projects/uoink/checkouts/Yoink/assets/dashboard/index.html)
- **Content**: Appended a small caption under the Updates "Check now" button to disclose the `api.github.com` request.

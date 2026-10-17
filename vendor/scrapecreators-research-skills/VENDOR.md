# ScrapeCreators research skills — design reference

Uoink's five local research playbooks adapt documentation from
[ScrapeCreators/social-media-research-skills](https://github.com/ScrapeCreators/social-media-research-skills).

- Pinned commit: `64ba7b4dea71e130d2712ffb6c1c1024b3b7c4b2` (2026-08-26).
- License: MIT, Copyright (c) 2026 ScrapeCreators.
- Pin recorded: 2026-10-15.

This is a design-only pin. No upstream scripts or runtime code are vendored or
shipped. `research_playbooks.py` adapts workflow steps, output templates,
outlier thresholds and pitfalls from these files:

| Upstream `skills/…/SKILL.md` | Uoink playbook |
|---|---|
| `outlier-post-finder` | `outlier-posts` |
| `transcript-intelligence` | `transcript-intel` |
| `comment-mining`, `product-demand-research` | `comment-mining`, lenses `voc` and `demand` |
| `creator-profile-teardown` | `creator-teardown` |
| `content-repurposing` | `repurpose-pack` |

The Uoink implementation reads local captures and saved discovery snapshots.
Python computes the metrics; the calling agent writes the report. The upstream
network and API-key instructions are not part of the adapted prompts.

The [upstream license](../../third-party-notices/scrapecreators-social-media-research-skills-MIT-LICENSE.txt)
is copied verbatim from the pinned Git blob, preserving its LF line endings
(1,071 bytes; SHA-256 `37a2301a00eef329530cc65ddb9f1c1085a2fbfb1bb748adb9eb6fa05bde4f9b`).
The notice generator retains attribution on regeneration, and `build.ps1`
stages the module and license.

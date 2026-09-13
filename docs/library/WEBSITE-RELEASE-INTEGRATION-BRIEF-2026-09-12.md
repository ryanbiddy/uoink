# Give Living Library a clear release page

The current public GitHub release is **v3.7.0**, published July 25, with a Windows
installer and MCP bundle. This was checked through GitHub's releases/latest API
during this review. Living Library 3.8.0 is still the held candidate described in
RELEASE-NOTES-LIVING-LIBRARY.md. A branch backup does not publish that candidate.
[Current public release](https://github.com/ryanbiddy/uoink/releases/tag/v3.7.0).

The latest committed personal-site source is in Replay Ryan HQ at commit
7d62d1e, September 3: 03-sites/site/src/index.template.html and build.py. The build
generates 03-sites/site/index.html. Its existing Uoink row links to GitHub and
says shipped, while Zing says pre-alpha and X Radar says running local. The
Uoink label can describe the existing 3.7.0 release; it must not imply that the
Living Library candidate has shipped.

HQ now prioritizes the Social Content workflow. Its current working tree has
uncommitted content-factory and governance changes. This review inspected the
site source and project instructions without editing, building or publishing
that project. It did not visually qualify the site. The site still identifies
its copy as a draft, and identity/publication decisions remain with Ryan.

## The change to make after release acceptance

Keep Ryan's selected site direction. Edit the template, regenerate the page and
add one Uoink destination from the existing product row. That page should answer
four questions in order: what it saves, how someone retrieves evidence, what
stays on the machine, and how to install the exact approved Windows release.
It should have release notes, supported-client instructions and a troubleshooting
path beside the download. Do not send visitors through internal phase reports.

Use the first-run journey as the page's example: save a source, find it in the
library, open its evidence card, follow a citation and open a cited brief. Show a
chapter jump only for a client/player combination that has passed the recorded
check. Use actual approved screenshots from the final build. Synthetic receipt
fixtures are test evidence and must be labelled if used in a demo.

| Public point | Evidence to bind before publishing |
|---|---|
| Windows download | Approved tag, exact installer hash, final signing status, installation verdict and rollback instructions |
| Agent access | Tested client/version and its actual tool/resource/prompt flows; Desktop results cannot be inferred from CLI results |
| Evidence and citations | Final source's retrieval, stale-input refusal and cited-range checks |
| Shelves | Reviewable suggestions; keep the 0.90 autonomous threshold and apply disabled |
| Standing capture | Explicit consent, visible allowances, pause/recovery and user control |
| Chapters | Recorded chapter/range provenance; no speaker attribution or unsupported precise-seek claim |
| Activity reports | Describe saved-library activity, not social-platform trends or engagement |
| Local processing | Explain initial software/model downloads and optional external client accounts accurately; do not imply all dependencies share the app's MIT licence |

The installer, MCP bundle and browser extension need a single release identity.
Before changing any download URL, check the existing tag/draft inventory, build
the applicable artifacts and verify that every advertised asset exists. The
extension's published-version link must follow the actual approved asset, not a
candidate filename. Keep prior downloads available for the documented rollback.

## Completion checks

On the product side, finish the security repairs, full candidate tree, installed
checks and owner dispositions already in the orchestration queue. The added
signing path at 0b3629d is not in package 08 and has not produced a signed Uoink
artifact. The historical AT6 failure remains visible. Phase 5 Part B and speaker
attribution remain outside this release.

On the website side, check desktop and phone layouts, keyboard navigation,
reduced motion, internal routes and every download/help link. Build from the
template rather than editing generated HTML. Review the release page's claims
against the final receipt, then obtain Ryan's publication approval. The current
branch-only backup authorization does not cover main, a GitHub release, the
website or marketing publication.

After those checks, the launch package should contain the approved binaries and
hashes, concise release notes, upgrade/rollback instructions, the product page,
an actual first-use demo and a support checklist. Social posts can then be
written around that demonstrated journey. None of this requires a new brand,
framework, paid service or additional product feature to be invented first.

Further UX work should follow observed friction from that journey. A larger
desktop redesign, more autonomous agents and additional analytics are separate
iterations; they should not replace the unfinished security and acceptance work.

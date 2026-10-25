# Supplemental upstream notices

These two cached Python wheels contain no license-text member. The files beside this index preserve the exact upstream text identified through retained wheel-member hashes and official source records. They supplement the metadata inventory in [THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md). No wheel metadata is changed.

**ANTLR Python runtime 4.9.3.** [Complete upstream license](antlr4-python3-runtime-4.9.3-LICENSE.txt), copyright 2012–2017 The ANTLR Project. The official `4.9.3` tag resolves to commit `e4c1a74c66bd5290364ea2b36c97cd724b247357`. Its Python setup declares 4.9.3, and `Recognizer.py` matches the retained wheel member. That source header identifies the BSD 3-clause license. The full upstream file also contains an MIT section explicitly scoped to `codepointat.js` and `fromcodepoint.js`; this is not a claim that those JavaScript files ship in the Python wheel.

- Cached wheel: `antlr4_python3_runtime-4.9.3-py3-none-any.whl`, 144,613 bytes, SHA-256 `d50ab331bff062b5e7f74e19fb16a2e891a47e893d805bcdbff8e6e6beb09c37`.
- Notice: 2,699 bytes, SHA-256 `b1b379fcaf3219593a4c433feb1b35c780bed23fafaae440b1ae2771a9521e3a`.
- Sources: [versioned license](https://github.com/antlr/antlr4/blob/e4c1a74c66bd5290364ea2b36c97cd724b247357/LICENSE.txt), [matching Python source header](https://github.com/antlr/antlr4/blob/e4c1a74c66bd5290364ea2b36c97cd724b247357/runtime/Python3/src/antlr4/Recognizer.py).

**Proxy-tools 0.1.0: metadata conflict retained.** [Complete upstream license](proxy-tools-0.1.0-UPSTREAM-LICENSE.txt), copyright 2013 Armin Ronacher and 2014 Jonathan Tushman. The wheel/PyPI metadata and historical `setup.py` declare MIT. The matching source header and repository license instead say BSD. This index reports both declarations; it does not choose an SPDX identifier or resolve the conflict. The license file is unchanged, including its literal `<COPYRIGHT HOLDER>` placeholder and malformed trailing sentence.

- Cached wheel: `proxy_tools-0.1.0-py3-none-any.whl`, 2,943 bytes, SHA-256 `a049f8570f5ce89b723ba282b90291ac3aa1fdcbd7d7100426ff659447400c68`.
- Notice: 1,436 bytes, SHA-256 `a428fb8a2e762af3eb0a6edbbb88e9b42ccfee80fd9b423958bcacf9b9abbfe4`.
- Official pre-upload commit `f82ae43524fd6d9917b0e9490c7d0394dff8d155` declares 0.1.0; the package module matches the retained wheel member. The captured official tag list was empty. This does not establish an exact release commit or publisher-signed artifact.
- Sources: [historical license](https://github.com/jtushman/proxy_tools/blob/f82ae43524fd6d9917b0e9490c7d0394dff8d155/LICENSE.txt), [matching source header](https://github.com/jtushman/proxy_tools/blob/f82ae43524fd6d9917b0e9490c7d0394dff8d155/proxy_tools/__init__.py), [conflicting setup metadata](https://github.com/jtushman/proxy_tools/blob/f82ae43524fd6d9917b0e9490c7d0394dff8d155/setup.py).

**Bundled fonts.** The dashboard and the Chrome extension ship Inter (https://github.com/rsms/inter), Bungee (https://github.com/djrrb/Bungee) and JetBrains Mono (https://github.com/JetBrains/JetBrainsMono), each under the SIL Open Font License 1.1. They are the uoink.app site's own WOFF files, copied unchanged. The font files and their licence texts (`inter-OFL.txt`, `bungee-OFL.txt`, `jetbrains-mono-OFL.txt`, each carrying that font's copyright line) sit together in `assets/brand/fonts/` and `extension/brand/fonts/`, which ship with the app and the extension. They are not Python packages, so the generated package table in THIRD-PARTY-NOTICES.md does not list them.

- `inter.woff`: 86,012 bytes, SHA-256 `3e5339ed054085f4a3976404b16c45fcb7616c0dd8da81a7f0020d7c8d65326b`.
- `inter-italic.woff`: 94,488 bytes, SHA-256 `91679ac4996660266cf71e0a915155d8caae95879cfd27600d1dc14c503c8ee6`.
- `bungee.woff`: 18,468 bytes, SHA-256 `95bcdf653c9b80cf0738a09fd7ac4f774490f654b947d1567cc23770c8153c0e`.
- `jetbrains-mono.woff`: 47,508 bytes, SHA-256 `e39ab79c56896dfac8152394810671984a9c1aa020c79f2126cbac1b127a2e22`.

These notices do not establish legal clearance, authenticate every package member, or qualify package installation, script execution or model behavior.

## Optional EmbeddingGemma search

The model is downloaded only after acceptance. Its weights, search vectors and
acceptance record are stored in the active installation's data folder and never
ship in an installer or MCP bundle. The bundled [model notice](EmbeddingGemma-NOTICE.md)
links to the [Gemma Terms of Use](Gemma-Terms-of-Use.txt) and
[Prohibited Use Policy](Gemma-Prohibited-Use-Policy.txt).

## Adapted documentation text

**ScrapeCreators social media research skills.** Uoink's five local research
playbooks adapt workflow steps, output templates, outlier thresholds and
pitfalls from [ScrapeCreators/social-media-research-skills](https://github.com/ScrapeCreators/social-media-research-skills)
at commit `64ba7b4dea71e130d2712ffb6c1c1024b3b7c4b2` (`64ba7b4`).
The [complete upstream MIT license](scrapecreators-social-media-research-skills-MIT-LICENSE.txt)
is retained verbatim: Copyright (c) 2026 ScrapeCreators.

Adapted files:

- `skills/outlier-post-finder/SKILL.md`
- `skills/transcript-intelligence/SKILL.md`
- `skills/comment-mining/SKILL.md`
- `skills/product-demand-research/SKILL.md`
- `skills/creator-profile-teardown/SKILL.md`
- `skills/content-repurposing/SKILL.md`

No upstream script or code is shipped. Uoink computes metrics locally and gives
the calling agent bounded, cited library evidence. The lineage pin is
`vendor/scrapecreators-research-skills/VENDOR.md` in the source repository.

**Mozilla Readability.** `article_extractor.py` adapts main-content scoring
and sibling joining from [Readability 0.6.0](https://github.com/mozilla/readability/blob/0.6.0/Readability.js).
Copyright (c) 2010 Arc90 Inc. The [Apache-2.0 license](mozilla-readability-APACHE-2.0.txt)
covers this adaptation. Uoink uses a bounded stdlib Python parser and its own
Markdown renderer, with shell detection and metadata extraction. No JavaScript
or new runtime package is bundled. This is not a complete port of Mozilla's DOM
implementation.

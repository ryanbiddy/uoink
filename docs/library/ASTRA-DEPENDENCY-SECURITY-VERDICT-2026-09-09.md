# Dependency integration verdict, 2026-09-09

Accept the four dependency updates for candidate verification: Pillow 12.3.0,
MCP 1.28.1, cryptography 50.0.1 and NLTK 3.10.3. Gemini 4d4cc9ce's raw diff is
integrated through three-way apply. The four named build/lock/documentation
suites independently pass 23 cases in the worker (5.27 s) and checkout (5.54 s).
Two exact-version unit assertions now name the reviewed security targets; their
strict equality and all other lock checks remain. No acceptance case is removed.

The independent Python 3.11 Windows resolver accepts all 142 exact runtime pins.
Its ignore-installed report also proposes setuptools 84.0.0, a build-only item;
the actual build separately pins setuptools 83.0.0 and removes build tooling.
This is a resolution check, not a built-inventory or runtime compatibility pass.
The first two resolution attempts failed on an incomplete copied interpreter
and embeddable build-environment setup; their failures and repairs are retained.

The fresh OSV observation of the revised lock reports 19 advisory entries in
four packages, forming 15 alias-connected issues. The earlier lock had 95 entries
and 55 issues. Pillow, MCP and cryptography have no matches in this observation.
NLTK 3.10.3 retains GHSA-8mgp-746c-j5xp: its model-artifact path-security bypass
is unpatched in the latest published version. Gemini 48452609's claim that this
upgrade fixes all NLTK issues is incorrect. Uoink does not expose the affected
TransitionParser, AveragedPerceptron, tagger persistence or maxent save APIs;
WhisperX uses sentence tokenization. Absence of these call sites limits observed
exposure but does not remove the advisory from the package audit.

Lightning, Torch and Transformers remain constrained as the raw report records.
The original triage also overlooks WhisperX's default PyAnnote VAD: ordinary
transcription loads whisperx/assets/pytorch_model.bin through Model.from_pretrained.
That checkpoint is packaged, not a user-selected download. Package-03's copy is
17,719,103 bytes, SHA-256
0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea.
Its origin/integrity and remaining checkpoint-loader advisories must remain in
the final package review. Speaker attribution stays outside this release's
claims; no diarization or model download was run. Consent alone is not a fix for
unsafe checkpoint deserialization, and a same-user writable model is not a
security boundary against that user. The original triage's absolute claims of
unreachability and completely safe upgrades are not adopted.

Before installation, rebuild the changed package, verify all 142 actual runtime
pins and source bindings, and exercise image handling/MCP with those packaged
versions. Scan the new executable and retain its signature status. The audit is
not clean; release notes must retain these four packages and 15 remaining issues.
No source-media fetch scope, paid API, real credential query or installation
occurred in this dependency review.

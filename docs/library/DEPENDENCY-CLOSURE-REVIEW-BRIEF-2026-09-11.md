# Remaining dependency repair review

Read RELEASE-NOTES-LIVING-LIBRARY.md and
ASTRA-DEPENDENCY-SECURITY-VERDICT-2026-09-09.md first. Ryan requested fixes to
the remaining release issues on September 11. Review the retained Lightning,
NLTK, Torch and Transformers findings against current primary upstream package
metadata and advisories. The prior 19 entries / 15 distinct issues remain a
dated result, not a current clean audit.

Determine whether a compatible WhisperX/PyAnnote dependency update now permits
patched packages on the bundled Windows Python 3.13 runtime. Inspect the actual
transcription call path and packaged checkpoint loader. Propose exact version
changes only when upstream constraints and Windows wheel availability support
them. If an affected path can be repaired in first-party code, describe a
bounded fix and meaningful regressions; do not claim an API is unreachable
merely because speaker attribution is disabled.

This run writes a report only:
docs/library/DEPENDENCY-CLOSURE-REVIEW-2026-09-11.md. Include primary URLs,
retrieval dates, exact compatibility constraints, feasible repairs, unresolved
issues and required verification. Do not edit lockfiles, product or tests, install
packages, download models/checkpoints/media, invoke inference, or start clients.
Public upstream metadata/advisory requests are allowed. No paid API, credential
inspection, ordinary index, port 5179, new source-media fetch, diarization,
commits or pushes. No subagents. Write findings early; report unavailable
evidence honestly. Astra will independently review before any dependency change.

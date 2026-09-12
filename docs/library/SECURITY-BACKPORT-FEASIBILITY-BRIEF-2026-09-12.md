# Bounded security repair feasibility review

Ryan asked to fix security findings using Control Room. The metadata review at
a6b9cf0 found no compatible drop-in pin update, but did not rule out a reviewed
backport or migration. This assignment determines the smallest defensible next
repair. It is not a rerun of a failed measurement or a security clearance.

Write docs/library/SECURITY-BACKPORT-FEASIBILITY-2026-09-12.md early. Read
ASTRA-SECURITY-REPAIR-REVIEW-2026-09-12.md and the retained OSV/PyPI metadata in
proof/security-repair-gemini-2026-09-12. Inspect only repository source and these
staged dependency source directories read-only:
E:/AI/projects/uoink/checkouts/Yoink-library/installer/staging/python/Lib/site-packages/whisperx
and its torch, transformers, nltk and pyannote neighbors. No execution/imports
of these dependencies or model code. No network access is needed or authorized.

Cover three questions with exact file/line evidence and advisory IDs:
1. Which unsafe checkpoint/tokenizer paths are reached by Uoink's default
   transcription/VAD route? Explain why diarization=false is insufficient.
2. Can a small first-party boundary or vendor backport prevent each reachable
   unsafe deserialization/download behavior while keeping existing capabilities?
   Specify the smallest concrete patch and limitations; don't claim runtime hash
   checks protect against same-user mutation or that unused paths clear a package.
3. If safe closure requires migrating WhisperX/Torch/Transformers or exercising
   real inference, identify the exact compatible constraints and necessary
   qualification. Distinguish what can be tested offline with synthetic inputs
   from prohibited checkpoint/model download/load/inference. List an actionable
   repair brief outline, rather than repeating that a bigger review is needed.

Produce documentary findings only, no production/test/dependency edits. No live
index access (including metadata), no port 5179, no helper/GUI/installer, no paid
API, no models/download/inference/diarization, no credentials, no commits/pushes,
no subagents. Apply remains false. Do not alter acceptance tests or relabel the
19 raw entries /15 groups. Bound the report to supported findings and precise
next patches, including when there is no adequate mitigation without disabling
an advertised feature. Astra owns integration and final release decisions.

# Companion B root-reviewed proposal — 2026-09-13

Root reviewed the exact derivative patch, harness, launcher and all six preserved
assertions, then independently ran the candidate with synthetic seams. Root
accepts this exact selected-source proposal for further derivative planning.
This records the scope of the parent integrator's review decision; it does not
grant full-module, runtime, packaging or market acceptance.

The original source result remains **1 passed, 5 failed, 0 errors, 0 skips**,
actual exit 1. The first candidate and the independent root candidate each
record **6 passed, 0 failed, 0 errors, 0 skips**, actual exit 0. Both candidate
runs use the same six case IDs and assertion bytes, with retained guards and no
heavy imports. These are two executions of six cases, not twelve distinct
behavior contracts. All tokenizer/model seams were inert; no real tokenizer,
model or complete dependency module was executed.

The accepted proposal text SHA-256 is
`e500e12b0a58420ce5f41b202ba7d942b901a9b99c617d6ca3d3304b9493f269`;
its patch SHA-256 is
`ef6e3ea49d4a30279ec6a37dc5d737db5ea8d8d1191af25c578f6411c407b764`.
It prepares available tokenizer input before CTranslate2 construction and refuses
missing local-only tokenizer input before that constructor, while retaining the
explicit non-local fallback. The input remains captured staging source recorded
as faster-whisper 1.2.1, without newly establishing full upstream wheel identity.
The original review's compatibility limits remain in force.

This archive preserves the original 46-payload seal and its nested 24-payload
proposal unchanged, plus the independent eight input bindings, source review
record, raw plans/results/logs and preparer. Assembly performed only byte copying,
hash verification and existing-receipt checks. No source, frozen fixture,
dependency, shared staging or tracked documentation changed. A separately
identified derivative and provenance/build plan is the next reviewable step;
no dependency application or build has occurred.

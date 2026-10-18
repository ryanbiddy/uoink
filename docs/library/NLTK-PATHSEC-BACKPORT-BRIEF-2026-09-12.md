# Repair the NLTK artifact-path bypass without loading a model

The retained GHSA-8mgp-746c-j5xp finding identifies raw model-artifact file
operations that bypass NLTK's pathsec policy. A missing upstream release does
not prevent preparing a reviewed source backport. Ryan has requested all fixes.
This task prepares the patch and its focused qualification; it does not change
the installed candidate or claim the raw advisory scan is clean.

Read Standing rules, ASTRA-SECURITY-BACKPORT-REVIEW-2026-09-12.md and the exact
advisory under proof/security-repair-gemini-2026-09-12/osv/advisories/ first. Work
only in the new worktree and fresh scratch directories. No commits, subagents,
existing test/fixture edits, live index, port 5179, paid API, client launch,
model/checkpoint download/load, training, inference or diarization. Imports and
synthetic tests at mocked serialization boundaries are allowed; real model
payloads are not. Read staged third-party source only from
E:/AI/projects/uoink/checkouts/Yoink-library/installer/staging/python/Lib/site-packages/nltk.
Never change that staging tree. Source/advisory inspection on official NLTK
GitHub is allowed, but no model/data fetch. Do not assume a nonexistent 3.10.4.

Write these deliverables early:

1. vendor/nltk-pathsec/README.md and an exact source patch covering the six APIs
   listed by the advisory: TransitionParser.train/parse, AveragedPerceptron.save/
   load, PerceptronTagger.save_to_json and save_maxent_params. Route every affected
   read/write/directory creation through the intended pathsec policy, including
   intermediate paths and symlinks. Preserve authorized inside-root behavior.
   Do not disable APIs, broaden policy roots, force the policy off or use an
   unreviewed monkeypatch. Inspect actual 3.10.3 source and upstream fixes first;
   report exact unaffected paths and unresolved cases honestly.
2. scripts/prepare_nltk_pathsec_backport.py: a deterministic preparation utility
   that checks exact original input hashes before patching a copied source tree
   in an explicitly new destination. It must never import the input package,
   write to staging, fetch resources, accept path traversal or overwrite an
   existing destination. Emit original/patched hashes, patch identity and a
   truthful preparation receipt. Prefer a small declarative exact patch with
   fail-closed source checks. No production lock/build edit in this worker.
3. NEW tests/test_nltk_pathsec_backport.py with meaningful before/after cases.
   Pair each outside-root refusal with an inside-root routing control, cover
   nested traversal/symlinks where supported, unchanged original source and
   tampered/reapplied/wrong-version input refusal. Intercept serialization and
   training before they execute. Do not load a checkpoint, unpickle a model or
   invoke inference for these tests. Identify any case that cannot be tested
   within this boundary instead of counting it passed.

Record a one-page review and focused suite commands/results in
docs/library/NLTK-PATHSEC-BACKPORT-2026-09-12.md. Include exact remaining packaging
steps: an explicitly labelled local distribution, lock/notices and wheel-hash
provenance, installed graph/decoder checks and a new full candidate tree. No
transcription-quality credit is needed or granted for path routing tests. The
scanner's original entry stays visible even if the local patch later qualifies.

Astra will inspect the patch, execute the new suite in the worker, integrate
using raw git diff and git apply --3way, then run the same suite in the checkout.
The intended outcome is a reviewable tested repair, not another version survey.

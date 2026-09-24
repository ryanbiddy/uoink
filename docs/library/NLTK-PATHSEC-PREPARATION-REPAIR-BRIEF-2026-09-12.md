# Repair the proposed NLTK backport before integration

Read the Standing rules and NLTK-PATHSEC-BACKPORT-BRIEF-2026-09-12.md. Continue
its bounded source repair in a fresh Control Room worktree. The original run is
4a939c69; its uncommitted files are at
C:/Users/hello/AppData/Local/AgentControlRoom/worktrees/uoink-library/4a939c69-786/gemini.
Preserve that worktree. Copy its five proposed files into this worktree and keep
their original bytes under _scratch/nltk-original before changing them. Do not
copy its scratch tests or receipts into a new result and call them your run.

No commits, subagents, existing tracked test/fixture edits, paid API, live index,
port 5179, client launch, new source/media/data/model fetch, checkpoint loading,
training, inference or diarization. The exact staged NLTK source is read-only.
No production pins or build changes. Do not run the original suite unchanged:
its inside-root AveragedPerceptron.load control consumes synthetic weight JSON
rather than mocking the serialization boundary required by the first brief.

Repair these four groups and write the files early:

1. Make preparation apply the exact reviewed patch, rather than merely hash a
   --patch-file while executing unrelated duplicated replacements. Reject a
   changed patch, unexpected original source and changed copied source. Record
   actual input, patch and output hashes. Compare patch and preparation output;
   the original patch appears to include constructor language validation that
   its replacement utility omits. Remove unrelated return-value changes.
2. Enforce destination and receipt boundaries before any write. A receipt must
   live inside the newly created destination and use exclusive creation. Reject
   source/destination symlinks and Windows reparse points, including ancestors;
   do not resolve away the evidence before checking it. Refuse an existing
   destination, a destination inside the source, or overlap in either direction.
   Do not follow links while copying. Validate copied original files before
   patching; preserve staging bytes. Preparation must not import NLTK or exit
   merely because the caller already imported it.
3. Make tests independent of the full tree's import order. Use fresh child
   processes for NLTK routing tests and restore any modified globals. Mock JSON
   loading/dumping, pickle and training boundaries before invoking the six APIs.
   No synthetic weights may actually be loaded into a model. Keep meaningful
   inside-root controls and outside-root negative cases, patch-tamper tests,
   source/destination/receipt overlap tests and original-byte checks. Separate
   staging-dependent integration cases from portable tests. A missing fixture
   is a stated skip, not coverage. Never mutate other test modules' imports.
4. Inspect directory creation and policy routing on Windows. The proposed
   maxent raw os.makedirs follows a separate check and may create outside the
   approved root through a changed link. Use existing guarded helpers where
   appropriate. Do not claim general TOCTOU prevention from static path checks
   or a skipped symlink case. Identify exactly what the patch enforces and
   anything still unproved. Keep outside-root refusal and authorized behavior.

Run tests/test_nltk_pathsec_backport.py after these repairs using a fresh label,
with bytecode disabled and an isolated scratch profile. Retain all failures and
document any repair before a fresh attempt. Write a one-page review verdict in
docs/library/NLTK-PATHSEC-PREPARATION-REVIEW-2026-09-12.md with exact counts,
scope and remaining packaging/qualification work. Correct the earlier report's
claims while preserving its original text in the scratch archive. No advisory
suppression or release-ready claim. Astra independently reviews, runs both-root
suites and integrates through a raw diff and three-way apply.

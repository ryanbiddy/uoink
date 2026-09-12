# Remaining security findings stay open

Gemini Control Room run 0ee38a14 produced new upstream evidence and no product
repair. Astra accepts the verified evidence with the corrections below. The
candidate is not security-cleared. This review supersedes conflicting claims
in SECURITY-REPAIR-WORKER-2026-09-12.md; the worker's original bytes are retained.

All 35 sealed metadata payloads match their hashes. The OSV request exactly
matches the checkout's 140 pins. An independent count finds **19 entries / 15
alias groups / four packages**: Lightning one, NLTK one, Torch eight and
Transformers nine entries. Lightning's already verified 2.6.6 code repair is
separate from the scanner's inconsistent fixed-version event. Subtracting its
one entry leaves **18 entries / 14 groups**, not the worker's 17. The raw scan
remains 19 / 15; no entry is suppressed.

The current [WhisperX 3.8.6 requirements](https://github.com/m-bain/whisperX/blob/v3.8.6/pyproject.toml)
require Torch 2.8.x and Hugging Face Hub below 1.0. The verified current package
metadata offers no compatible drop-in repair for the retained Torch and
Transformers stack. NLTK's [model-artifact advisory](https://github.com/advisories/GHSA-8mgp-746c-j5xp)
still has no published patched version. This does not prove that every possible
migration or reviewed backport is impossible. A larger stack migration would
need its own brief and compatibility/inference qualification; none was run.
Advisory-specific fixed versions differ, so the worker's broad statements about
Torch 2.9/2.10 or Transformers 5.0 fixing everything are not accepted.

Default PyAnnote VAD checkpoint loading remains relevant even when speakers are
disabled. Narrow observed NLTK/Transformers call paths do not establish a general
security boundary or justify the worker's "Low" risk labels. The normal Inno
root is LOCALAPPDATA/Uoink, not LOCALAPPDATA/Programs/Uoink. Same-user writes and
unsafe deserialization cannot be neutralized by a preflight file hash.

Astra independently ran all worker tests: **25 passed**, including the 21
existing named cases and four proposed cases. Those four proposed tests are
rejected from the active tree: two merely freeze current vulnerable pins, one
duplicates unavailable-runtime behavior, and the claimed redirected-DLL test
ends in `isinstance(res, object)`, which cannot reject a returned value. It does
not test the claimed redirection. Their original bytes and passing result stay
in the review proof. The accepted documentary patch has **21 existing passes
in the checkout**; these are the same 21 existing cases in the worker result.

Both reviews use the established `--runxfail` qualification mode, retaining the
unchanged SEC-06 behavior assertion and historical strict-XPASS result. Worker
attempt logs remain separate. One Astra metadata reader failed because Windows
decoded UTF-8 JSON as cp1252. Its documented reader-only correction used explicit
UTF-8 under a fresh output label; no evidence or product measurement changed.

Integration used the full retained binary worker diff and a documented accepted
documentary subset with `git apply --3way`. The index received exact proof bytes,
but checkout materialization changed line endings in 12 files before the new
byte-preservation rule took effect. A retained preflight proves each mismatch
was only CRLF conversion and the index was exact. Restoring those 12 paths from
their verified index blobs repairs transport without changing the measurement.

No dependency, first-party production file, existing test, fixture, assertion or
mark changed in this integration. Proof: `proof/security12-astra-review-2026-09-12`
and the separately sealed `proof/security-repair-gemini-2026-09-12`. The native
note display repair is a different Control Room run and, if integrated, requires
a fresh full tree and build.

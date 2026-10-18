# Process ownership repair accepted for combined qualification

The mirror now retains native process handles from ownership discovery through
assignment, termination and cleanup. A distinct writer PID must belong to the
proved process tree before publication. Cancellation cannot drop a handle
another operation still uses, and a borrowed Popen handle keeps its owner alive.
These changes close the reviewed process-authority defects. They do not establish
the cause of tree08's failures or make the release ready.

Astra reviewed the final source, then observed **233 passed, zero failed, zero
skipped** in each root: worker `a3w02` took 118.37 seconds and checkout `a3c01`
took 113.20 seconds. Both actual pytest/verifier exits are zero and both XML
case sets are identical. The scope contains all Phase 4 files, the accepted
owner-admission cases and 49 synthetic authority cases. Before that broader
qualification, Astra independently observed all 49 focused cases pass in 0.65
seconds. No committed test, fixture, assertion or marker was changed.

The worker source SHA256 is
`67432bf13905b8c28c2048ce51bbebd74490d463f8b1a4e08fdd3ce4e53a0a23`.
Integration used raw `git diff --binary HEAD` in the completed Grok worktree,
then `git apply --3way` in checkout at `099a724`. All seven source/test/helper
files match after Git line-ending normalization. The accepted ff67b84 exclusion
owner and prepare method remain unchanged. Four uncommitted synthetic test
modules gained an inert handle fixture import; their remaining ASTs and earlier
behavior assertions are unchanged. The exact setup diffs and reasons are saved.

The first broader worker observation remains **174 passed / 59 failed**,
100.51 seconds, exit one. My descriptive verifier label made the first export's
temporary path 256 characters, above the existing 240-character product cap.
The fresh short label reduced that path to 220 characters. Source, test setup,
selectors, guard and product path limits were unchanged for the corrected run.
The original log, XML, ledger and manifest are retained; it is not relabeled.

The [116-payload proof](proof/astra-authority-repair03-2026-09-13/README.md)
preserves the 39/44/46/49 intermediate stages, review and integration instruments,
both-root results and their source bytes. Its manifest SHA256 is
`4b4f9950e44a4ec1311fdda45f0936ddb3714d2757c44bfdead1b3081b4fc2bf`.
Earlier Gemini and Grok proposals remain historical held/rejected evidence.

Next is committed combined-tree qualification with the reviewed durable observer.
Runtime security, signing, installed-package and client gates remain separate.
No model, live-index, port 5179, fetch, installation, website, marketing or push
was part of this repair qualification.

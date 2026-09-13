# Partition receipt repair before tree09

Do not run the product tree yet. Independent review found that the unused
tree09 runner ignores abnormal pytest exits after reports are written, and
its XML accounting cannot preserve a call failure plus teardown error for
one case. Both flaws also exist in earlier runner copies; this is an
instrument repair, with no retrospective change to any recorded result.

The preliminary 54-payload mirror-tree09-preflight seal preserves the original
unused runner, sealer and observer evidence. Keep those bytes unchanged.

Add a pure scratch validation module and synthetic tests. Require each tested
partition's selected cases, complete phase reports, session receipt, actual
pytest exit in verifier results, outer verifier exit and JUnit results to
agree. A completed failed run has exit 1 and remains failed. A session error,
missing receipt, abnormal exit or disagreement is incomplete qualification,
even if its case reports are green. Count each case once while retaining all
failed phases. Normalize JUnit elements by testcase identity; refuse identity
ambiguity or unexpected duplicates instead of dropping outcomes.

Cover pass, assertion failure, setup/teardown failures, a call failure followed
by teardown error, and shutdown failure after green case reports. Run only
inert scratch cases through the existing guarded verifier. Every execution
uses a fresh label and preserves actual nonzero status. No product tests,
fixtures, assertions, processes, model calls or installed applications change.

After helper review, wire the runner and sealer to the same contract, retain
before/diffs and test the real receipt pipeline with deliberate failures.
Only then qualify the instrument for a future product run. The process repair
must independently pass review and both-root suites before tree09 starts.

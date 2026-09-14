# Draft correction, 2026-09-14

The root source review found that a missing manager token entry could make `_flush_quarantine` replace an existing failure. The source author moved its token lookup inside the existing preserving `try` in durable source `ce69903d93daf41ae3717008f8d0dbd0b3ead7b11662b674eddf43828567b222`.

Two new subcases remove that entry after the actual bind or finish returns, then raise a retained `RuntimeError`. They require the same exception object, original token/worker/attempt custody, one exact stop, no publication or release, and the specific unconfirmed-quarantine note. The ten method identities and fixture remain unchanged. The earlier 102 proposed subtest iterations become 104; no case has executed.

`draft02/` preserves the previous test and mechanical patches. It also preserves the first passive checker: before running it, its empty-source array expression was wrapped in `@(...)` so new-file reconstruction has an empty array rather than `$null`. This is a checker preparation correction, not a candidate outcome.

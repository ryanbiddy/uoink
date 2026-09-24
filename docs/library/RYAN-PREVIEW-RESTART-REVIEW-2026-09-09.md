# Existing preview read: review verdict — 2026-09-09

**Accept the read-opening repair for integration.** The original stdio entry
returned the right preview answers but changed stored state while opening an
existing index. Its normal opener migrated/backfilled storage and attached
the work service, whose recovery rewrote authoritative files. Six new frozen
subprocess cases reproduced these mutations. The initial missing-service
hypothesis in the brief was disproved and remains documented there.

`Index.open_existing` now opens SQLite in read-only mode without initialization.
An explicit ordinary backend operation promotes the same Index under its lock;
failed initialization retains the original readable connection. Ordinary first
startup still uses the original opener. The preview reader shares Phase 2's
binding, taxonomy, evidence and delta checks without attaching a service or
recovering a journal. An already-injected service remains supported. Resolution
occurs after request admission and retains the existing response deadline.

The six original-entry tests cover a valid preview, altered evidence, altered
taxonomy, altered projection, expiry and a missing preview. They require correct
responses, unchanged SQLite contents and unchanged authoritative file bytes.
Three additional tests cover absent storage, explicit write promotion and its
failure path. All **nine pass**, 7.67 seconds. The broader Phase 2 / Phase 4
work, resource, prompt, brief, stdio and AW/AW2/AW3 union has **212 passed and
eight failed**, 72.66 seconds. All eight are the existing mirror interception
cases; their separate fixture proposal remains unapplied. No existing test,
assertion, timeout, parameter or skip changed.

The retained reproduction is **six failed**, 7.36 seconds. Raw logs, XML,
commands, guard, verifier, exact patch and source hashes are sealed in
`proof/ryan-preview-read-2026-09-09/SHA256.json`. These are disposable protocol
observations, not installed or real-client credit. Final committed-tree and
bundled original-entry verification must include this source change. This
review does not accept the remaining eight cases, historical AT6 exit gap,
installed C22/Phase 4 gates or the old package.

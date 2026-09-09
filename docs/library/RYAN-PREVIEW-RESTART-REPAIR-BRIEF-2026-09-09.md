# Read an existing preview after client restart — 2026-09-09

The Phase 4 contract promises a read of an existing valid reshelving preview.
The original stdio entry instead supplies only an already-attached Phase 2
service. A fresh process opens the existing index without that service, so
reshelve-review refuses feature_unavailable even when all preview tables and
authoritative inputs exist. Constructing the normal service is unsuitable:
its initializer attaches state and may run mutation/recovery.

Astra will first reproduce this through the original uoink_mcp.py subprocess
on a disposable existing database. New tests must check a valid preview,
changed evidence/taxonomy/projection, expiry and missing preview, preserving
the full stored state and authoritative file bytes across each read. Do not
alter any existing fixture or the original stdio entry for the reproduction.

Repair with an explicit read-only preview validator sharing the existing
Phase 2 binding/delta checks. It must not initialize the work service, attach
it to the index, recover a journal, reap leases, mint previews or approvals,
write state or loosen missing-storage/deadline behavior. Retain the injected
service behavior used by existing callers. Resolve this reader only after
request admission and retain the whole-response size and time budget.

Run the new original-entry regression file, Phase 2 work/apply/undo tests,
Phase 4 prompt/resource/stdio tests, and AW/AW2 companions. The eight known
mirror interception failures stay failed and their proposal stays unapplied.
Record a focused new-file reproduction before repair and a fresh full named
union afterward, with raw log/XML/source hashes. The later complete candidate
tree and packaged original-entry verifier must include this change. No live
index, 5179, API keys, paid API, model/client process, new fetch, Inno, existing
test changes or applied labels. A stdio protocol driver is synthetic evidence.

## Reproduction changes the diagnosis

The six-case original-entry observation pre-r1 has **six failures**, 7.36 s.
All prompt responses have the intended valid/refusal behavior. All six fail
the unchanged-state check instead: Index.open automatically constructs the
service and runs its recovery while _get_existing_index opens a read. It
rewrites pins.json; altered taxonomy/projection also change persisted state.
The initial missing-service hypothesis above was not the observed defect.

Repair the actual opening boundary first: an existing-index read must neither
create/migrate/backfill nor recover Phase 2. Preserve normal initialization for
an explicit legacy/mutation path, including when that path follows an earlier
read. Once auto-recovery is removed, supply the pure validator described above
so a valid stored preview still works. Freeze the six tests unchanged. Record
both their initial failure and the final result. Add a new test for explicit
initialization after an existing-only read if this repair introduces that seam.

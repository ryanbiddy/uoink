# BC-3a3: remove publication exceptions and finish ownership guards

BC-3a2 (Grok `5aca8450`) is rejected. Its complete original diff, including its
test edits and report, is retained in
`patches/bc3a2-grok-rejected-2026-09-08.patch`. It claimed 161 passes using edited
BC-2 tests and a production exception for ticketless empty publications. Neither
closes the strict ownership requirement. No part is integrated yet.

The integrator restored only `tests/test_phase6_bc2.py` to that worker's HEAD
after preserving the diff. Run the full named suites on that restored test base
to record the original compatibility failures. This restoration repairs the
verification input; it does not repair production or turn a failure into a pass.
Integrator result on the restored tests: **156 passed, five failed**, 62.24 s.
Failures are BD-01's Index setup and BC-2's publication fence, Index publication,
clip-build refusal, and retention cases. All five stop at omitted-ticket setup.
Logs and XML: worker-local `_scratch/ig-bc3a2-original-w`.

Read `INTEGRATOR-CONTRACT-CONFLICTS-2026-09-08.md`, the BC-3a2 brief and the BD
review. Start from current `cc/living-library`. Apply only the production portions
of the retained BC-3a2 patch with three-way integration, then make these repairs:

1. Require an original build-time ticket at both raw and Index entry points.
   Remove `_ticket_for_omitted`, `_empty_media_snapshot`, and every empty,
   first-publication, or evaluation-helper exception. An idempotent retry carries
   its original ticket; never mint one in the publisher. Preserve real owning
   callers that acquire tickets before building. If legacy acceptance setup
   refuses, report it unchanged under the documented Ryan ruling.
2. Keep ledger-fenced reconstruction and protection of edited legacy corpus
   bytes. Check refusal leaves rows, files and transaction state coherent.
3. Protect non-owned sidecar edits, including removal of a key. A conservative
   refusal is acceptable. Revalidate dependencies at the final carrier write,
   after intervening ledger/artifact work, not only earlier in the operation.
   Never resurrect a removed unrelated key or overwrite another owner's edit.

No edits to any existing test, even its helper or setup. No fixture introspection,
test-name branches, runtime test imports or production exemptions to obtain green
counts. Add focused new implementation tests for a stale empty build with no
ticket and preservation of removed/late-edited sidecar keys. Those tests must
acquire tickets explicitly in their own successful setup. They supplement,
rather than replace or deselect, the frozen acceptance files.

Run the full Phase 6 BD file, evaluation, BC-2, podcast corpus bridge, clips,
resources, and Phase 3 publication/integration/recovery with
PHASE3_REQUIRE_IMPLEMENTATION=1. Keep each failure in the report and distinguish
fixture setup incompatibility from a failed behavior assertion. Do not claim the
phase accepted. Astra performs BD-2 after independent verification/integration.

Use disposable roots, PYTHONDONTWRITEBYTECODE=1, resolved Python dependencies,
and no API key. No live index, port 5179, model execution, paid API, commits or
pushes. Apply remains false. No subagents; write the implementation/report early.

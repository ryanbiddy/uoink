# Authorized fixture corrections: review verdict

Reviewer: Astra. Date: 2026-09-09. Base: `ee1293f`.

**Verdict: approved for one corrected full-tree run. Product acceptance is
pending that result.** Ryan explicitly authorized these five setup/cleanup
corrections. The exact 23,425-byte patch and reasons are recorded in
[the conflicts log](INTEGRATOR-CONTRACT-CONFLICTS-2026-09-08.md).

AW-11 now closes its originating helper through production stop/forget before
the existing death check. It no longer drops the Mirror pointer directly.
The foreign caller must still preserve the original bytes and return within
the same bound. D13 creates the personal edit after the returned timeout and
before releasing the delayed work; creating that edit no longer requires an
illegal replacement. D15 injects the same binding-path failure through the
actual atomic-persistence entry. Neither case relaxes its ownership checks.

The Phase 5 clock probe accepts the shared caller's keyword and forwards it
to the real reader. The simulated serialization delay, deadline and error
assertion remain fixed. Phase 6's optional fixture connection acquires a ticket
before constructing publication inputs. The raw and Index callers pass that
saved ticket; crash retries retain it. Each fresh crash scenario constructs its
replacement against that scenario's base. Intentional missing-ticket and bad-
ticket cases remain intentional. No helper obtains fresh authority at publish
time for a previously built stale snapshot.

Static verification found all **690 assertion syntax trees unchanged** across
six files, including their messages. The files parse, and the authored diff
passes whitespace checking. Review also confirmed unchanged parameter cases,
skip/xfail markings and production source. These are static observations,
not passing runtime results. The other Phase 4 syscall interceptors and old
refusal-code expectations are retained; their failures cannot be waived by
this review.

Commit these changes and the owner rulings before execution. Run the existing
isolated integrator runner against `tests`, excluding only
`tests/library_work_astra/test_phase3_s21.py` as required by the handoff. Keep
`PHASE3_REQUIRE_IMPLEMENTATION=1`, bytecode/cache disabled, the disposable
profile, live-index/5179 guards and model-process refusal. Preserve the full
command, log, XML, interpreter metadata, assertion audit and tested commit.

There is no additional fixture-correction round. Any remaining failed test
is a product defect under Ryan's 2026-09-09 ruling: retain it and write a repair
brief before any product repair or rerun. Previous failed measurements remain
failed. Rebuild only if production source changes; test/documentation edits
alone do not replace the existing installer receipt.

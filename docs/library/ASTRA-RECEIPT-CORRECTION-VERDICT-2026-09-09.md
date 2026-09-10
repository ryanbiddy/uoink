# Receipt correction integration review, 2026-09-09

Astra accepts the three narrowly scoped receipt corrections after independent
verification in the worker and checkout. The same 14-file union passed 172 tests
in the repaired worker (818.26 seconds) and 172 tests (816.08 seconds). This is an instrument
and source-runtime result, not an installed Inno receipt.

The Inno plan unit test now requires the supported `/ISOLATED=1`, `/PROFILE=` and
`/PORT=` arguments. It retains the refusal to execute Inno and the prohibited-port
assertion. The Phase 4 fixture reads the actual isolated `profile/settings.json`;
its apply-false and protected-sentinel assertions are unchanged. The C22 scenario
fixture now provisions the existing copied production runtime with synthetic
acquisition. That exercises the original child-registration methods and module
provenance required by the newer oracles. All 17 assertions in that scenario are
identical syntax trees to `c7a8426`; no case or success requirement was removed.
The source copier excludes `build/`, which contains cached packages and old
installer archives rather than inputs to this source-runtime fixture.

Gemini worker `269acc98` ended partial. Its original HTTP-stub patch is retained
but rejected. Astra's first attempted instrument repair had 171 passes and one
failure: the stub could not meet the real child and provenance oracles. That
failed result and its scenario evidence remain. The next observation was aborted
before a final suite count because the worker lacked the integrated credential
repair. Its log and exact owned-process termination record are retained. No
partial progress is counted as a passing suite. No actual credential was queried
to investigate the older fixture's unproven keyring boundary.

Before the successful worker run, Astra applied the already accepted credential
repair to its baseline. Only the three receipt fixture/copier files were exported
with a raw Git diff and applied through three-way integration. The credential
patch was not duplicated. The final patch, original and rejected patches,
interrupted observation, assertion audit and independent test records are sealed
under `proof/ryan-receipt-correction-2026-09-09/SHA256.json`.

The historical failed full tree remains failed. Run the complete committed tree
with only S21 excluded next. Rebuild the changed packaged source, verify actual
package contents, then use the reviewed same-account installation procedure.
Installed acceptance requires actual Setup effects, original helper and client
evidence, and the recorded account/isolation limitations.

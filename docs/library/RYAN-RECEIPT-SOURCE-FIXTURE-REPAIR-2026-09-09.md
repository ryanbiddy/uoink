# Receipt fixture correction after instrument review, 2026-09-09

Receipt worker 269acc98 did not finish its requested review. Astra's first
instrument repair restored actual fixture RSS discovery and explicit podcast
publication, but the old all-scenarios test still fails. Its stand-alone HTTP
stub has no production child-registration methods or required module provenance.
Those newer scenario oracles correctly reject it. A missing provenance module
or a synthetic child row cannot be converted into successful evidence.

Complete the approved third receipt-test correction in its setup: the single
test_synthetic_helper_scenarios_and_verdict case must provision the existing
source-runtime fixture, as test_final_source_runtime_corrected_oracles already
does. Use the current copied production helper and modules with synthetic
acquisition and transcription guards. Keep every original test assertion,
scenario name, all-success requirement and installed-credit prohibition intact.
Other unit tests may retain the stand-alone HTTP stub. Revert the unaccepted
stub patch in the worker after archiving it; no stub changes enter the candidate.

This is a source-runtime instrument observation, never an Inno installation.
The source copier must exclude build/ artifacts: copying installer caches and
old ZIPs into every source fixture is unrelated to its executable inputs and
can consume gigabytes. Add build to its existing excluded-directory set. Keep
production Python, SQL, assets and current isolation source unchanged.

First preserve the receipt-c-w1 outcome and its failed scenario receipts. Run
the same complete 14-file C22/P4 union in the corrected worker and checkout,
using fresh labels receipt-c-w2 and receipt-c-c2. Compare assertion syntax trees
for the corrected scenario against c7a8426: every original assertion must match.
The two plan/profile contract corrections are also retained. Record all diffs
and reasons in the conflicts log and an integrator verdict before acceptance.
If any behavior still fails, repair the actual product/instrument defect; do
not weaken the oracle or keep modifying the scenario's setup.

Verification baseline repair: receipt-c-w2 was interrupted after partial progress
because worker 269acc98 still starts from d8d3b4f, before credential isolation.
Archive its partial log and exact owned-process stop record; it has no passing
suite count. Its source-runtime helper copies cannot prove the new credential
boundary, and earlier source-runtime tests did not explicitly prevent OS keyring
access. Do not query any real credential to investigate that uncertainty.
Before receipt-c-w3, apply the reviewed credential patch to this worker's source
baseline. Export only the three receipt fixture/copier files for integration;
the credential repair is already in the checkout. Repeat the same 14-file union
in that repaired worker and then checkout; no assertion or scenario change.

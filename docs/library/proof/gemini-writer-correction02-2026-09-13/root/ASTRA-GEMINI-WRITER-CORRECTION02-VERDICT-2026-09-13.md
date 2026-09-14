# Astra verdict: Group B writer connection correction

Accept the limited source conclusion only with this addendum. The completed Gemini report has factual errors in its description of phases, observation sources and fixture setup. Root and independent peer review found no new actionable component defect in the five selected files. This is source review; no product suite or native observation was requested or repeated.

The run is 5444c59a-8ae1-4188-9b57-d967f04bbbb6, worker 13ca0121-9ced-4519-a43c-a4314f487ea2, based on 223a31d10bc629376f2202a7f8846d728064bf2c. Gemini 3.8 Flash High ran through the existing Antigravity subscription. Actual bf2f65 returned exit 0; its returned output was truncated and remains preserved as returned.

Read the original report with these corrections:

1. B-01:118–127 checks the lifecycle record as Phase.NATIVE_RESERVED and the confirmed journal phase as the string RESERVED. They are separate states. B-03:135–159 checks the retained token, cached bytes/revision and decoded frame.
2. PID and creation time are read from retained worker fields. Milestones annotate expected phases before calls. Exit observation delegates to the imported _observe_graceful_exit helper, whose implementation is outside this selection. These sources cannot independently establish the native origin or correctness of all observations.
3. On failure, the code marks a retained worker unconfirmed only if it is not already quiescent, attempts partial stopping only after creation returned, and marks an existing read set unconfirmed. An unexpected successful journal handle is retained until process death while the check fails; this does not establish a general prevention-of-reuse guarantee.
4. B-04:459–464 activates the 16,384-call/60-second work budget. B-04:378–411 defines the separate 64-call/10-second cleanup reserve. These checks are cooperative; the successful writer04 observation did not exhaust or exercise the cleanup reserve. B-05:46–54 creates five fixed literal fixtures and records their hashes. It does not validate pre-existing fixtures against an external manifest.

Root d90742 and peer 31c1b1 verify five source pairs totaling 120,375 bytes, coverage schema/bounds and the 483-word report. Report SHA-256 is 266bed30fd2ba50b2b3d4fda488ea567e94e86de9ea1fbf494f072543de0093f; coverage SHA-256 is 5f4a48ae431e980679962539e7ac4b07001f0077f0414cfa312b6bd742c5611b. Root checked the cited blocks; the peer read all five files. Catalog endpoints include terminal empty slots, and the worker's viewing history remains unverified.

Raw worker patch 370e1d was applied with git apply --3way; actual 4c0acd returned 0 with new-file direct-application fallback. Preserve the worker's report and coverage bytes unchanged. The archive includes the exact returned run records, raw patch, root checker and independent verdict/checker/result. No execution receipts were selected by the brief.

The earlier 48-input council review remains failed at 89c1579. Directory Group A acceptance at a74e178 also requires its own mandatory addendum. Neither correction supplies model, crash/restart, package, installed-client or market acceptance.

# Remaining receipt-test defect disposition, 2026-09-09

Source: 12ce8a5fbd34c3472d55ae76afa17535b43c5282. The final complete tree
has 2,429 passed / 13 failed / three skipped / one xfailed, 1,542.35 seconds.
Preserve that FAIL result. This brief assigns the three additional receipt-test
failures; the prior ten remain assigned in the earlier product/fixture reviews.
No fixture or assertion change is authorized here.

| Case | Conflict and bounded next action |
|---|---|
| test_install_receipt_c22_kit.py:223, test_plan_inno_does_not_execute | The frozen assertion requires /ISOLATEDPROFILE= and /ISOLATEDPORT=. The reviewed Inno contract requires /ISOLATED=1, /PROFILE= and /PORT=, with close/restart suppression. Do not add ignored arguments merely to satisfy the old assertion. Ryan must give a contract/test disposition before that expectation changes. Actual Inno behavior still needs the installed receipt. |
| test_install_receipt_c22_kit.py:328, test_synthetic_helper_scenarios_and_verdict | The test copies scripts/install_receipt/stub_helper.py into its fake app. That older fixture lacks the current /podcasts/feeds route, so manual-first fails before its episode can be registered; its all-scenarios-pass assertion fails. The actual original bundled manual-first and all other executable C22 scenarios pass. Extending or replacing that frozen fixture is outside the five authorized corrections. Keep the failure and request a specific fixture disposition; do not weaken the scenario oracle. |
| test_install_receipt_p4_kit.py:453, test_prepare_fixture_seeds_synthetic_items_and_keeps_apply_false | The test reads profile/Uoink/settings.json, while supported isolation stores profile/settings.json and the actual bundled receipt reports apply false. Do not duplicate settings into a second root to satisfy this probe. Ryan must authorize a setup/contract disposition; preserve its current failure. |

Review verdict: the observed original application routes do not justify changing
product behavior to match these three old expectations. The instrument contracts
and their newer positive/negative checks remain in force. Any unexpected failure
in Ryan's actual installed session is new product work: archive it, write a repair
brief, fix the product and repeat only the justified observation. No outcome is
promoted from failed/partial to passed, and no installed acceptance is inferred.

Evidence: [complete test result](proof/ryan-final-kit-tree-01-2026-09-09/SHA256.json),
[all failed case details](proof/ryan-final-kit-tree-01-2026-09-09/failures.json),
[new original C22](proof/ryan-c22-bundled-02-2026-09-09/SHA256.json), and
[new original Phase 4](proof/ryan-p4-bundled-03-2026-09-09/SHA256.json).
The eight mirror and one getter setup cases retain their two exact unapplied
proposals. The original AT6 exit status remains unavailable and cannot be inferred
from replacement AT7. Ryan's further-fixture freeze is the reason these decisions
remain open; no additional correction has been applied.

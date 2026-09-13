# Authority repair03 seal preparation

No version of the seal script has been executed during preparation.

Draft01 anticipated the original descriptive Phase 4 labels. It was preserved
before the first completed result showed 174 passed and 59 failed. The
integrator diagnosed the first failed export's overlong temporary path and
documented shorter labels without changing source, assertions, or fixtures.

Draft02 added the original failed run, its a0 ledger and manifest, and the
integrator's path-budget repair brief. Its final qualification slots use a3w02
and a3c01. It preserves missing checkout qualification explicitly.

Draft03 adds the integrator-observed a3w02 result: 233 passed,
zero failed or skipped, exit 0. It verifies that a completed checkout receipt
has the same case identities. Both earlier draft scripts remain beside the
current script and are included as evidence. Final sealing still waits for the
integrator's completed checkout result and instruction to seal.

The current draft adds the raw three-way integration patch, check/apply logs,
pre-checkout-test integration receipt, and integration instrument. It also
retains checkout source/test/helper bytes and checks their equality with the
reviewed worker files after Git line-ending normalization. The receipt's
`checkout_tests_run: false` is preserved as the state when it was written;
the final checkout result is a separate measured receipt.

The original failed run is retained as failed. The worker report and prior
Grok report remain records of their own observations, not current release or
complete-tree acceptance. No product or test file was edited for this seal.

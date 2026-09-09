# Bundled P4 collection correction — 2026-09-09

Source `5109c98`, original staged Python 3.11.9 and original packaged app, using
the reviewed system-Python driver. No Setup, client/model or external fetch.
Preparation, original stdio checks and original-client config preparation exit
zero. Collection exits one: 12 passed / three failed / eight unobserved.
All four command jobs are cleaned; guard removed, `_pth` unchanged, installer
hash and all 142 source bindings unchanged. Keep this failed observation.

The three collection failures share a receipt-tool cause. The collector treats
the deliberately unavailable-storage and terminated-transport sessions as full
packet/prompt sessions. Both declared normal sessions have complete equal packets,
32/5/4 inventories and both native prompt successes. Inspect full-packet sessions
by the scenario purpose declared by the stdio driver; retain and evaluate the two
negative scenarios separately. Unknown or partial normal sessions must still
fail. Do not select records based on whether they passed. Preserve every raw frame.

Review of the same collection also finds that `deletion_cleanup` passes merely
because four keys exist in a newly constructed dictionary. It reports one pending
deletion as passed. The generator calls a mirror tombstone hint while its fixture
item is still active; the authoritative index has not been soft-deleted. Follow
the actual production index mutation, then the mirror event, and retain ledger,
ownership, intents and affected file bytes. Require a content-free tombstone and
then absent purged owned bytes, accounted pending/conflict paths and preserved
user-edited/unmanaged bytes. A generic status flag or key presence is insufficient.
The old collection's reported pass is preserved but supplies no deletion credit.

Bound: receipt-tool source and new regressions only. Existing tests, assertions,
fixtures, skips and product source remain unchanged. Keep Phase 4's X 403 blocked,
visual/client checkpoints unobserved or pending review, apply false and no speaker
claims. Verify the new negatives and complete P4/operator union in the finished
worktree and checkout. Then observe a fresh `p4-bundled-02` fixture using the same
sealed installer/compiler inputs. Any real product failure gets a repair brief;
do not weaken the oracle or overwrite the first observation.

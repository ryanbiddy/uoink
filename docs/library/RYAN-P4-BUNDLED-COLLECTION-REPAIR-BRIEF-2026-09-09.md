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


## Astra review and integration result

Accept the instrument correction for a fresh bundled observation. Full packet
scope excludes only the two exact driver-declared negative scenario prefixes;
unknown and partial normal sessions remain in scope. All raw recordings remain.
The deletion scenario now performs Index.soft_delete_yoink, observes tombstone
bytes with source title/URL stripped, then deletes the synthetic index row and
purges. Its result requires owned item/dependent-brief absence, no unaccounted
pending keys or extant temporary files, and preserved edited/unmanaged bytes.
The complete ledger and intents are retained. No product or existing test edits.

Final worker pc-w2: **68 passed / one failed, 26.24 s**. Three-way checkout pc-c1:
**68 passed / one failed, 25.65 s**. Eleven new checks pass. The frozen nested
settings-path assertion remains the only failure. Preceding pc-w1 was 68/1,
26.42 s before adding the explicit operator-json argument to generated collection
commands. Ten proof files preserve every result and the exact patch at
proof/ryan-p4-collection-repair-2026-09-09/SHA256.json. These unit/source results do
not establish installed acceptance or the next bundled deletion observation.

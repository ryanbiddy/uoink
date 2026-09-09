# Read-opening fixture proposal: review verdict — 2026-09-09

**The two-line setup correction is justified; it is not applied or verified
as a passing result.** Ryan froze further fixture changes, so this review
does not authorize editing the test.

The unchanged discovery-route test assigns server._get_index to a lambda
returning its own fixture Index and leaves it assigned after completion.
Astra's new read-opening test then calls that lambda instead of the original
production getter. The two-file ordered reproduction has **three passed,
one failed**, 1.25 seconds, matching the new failure in the complete 8fc6a40
tree. The original production path had passed the earlier focused and
isolation unions; neither observation replaces the ordered failure.

The proposal captures the original getter at test collection and binds it
with monkeypatch for this test. It restores the preceding substituted callable
afterward. All **13 assertion syntax trees are identical**. It changes no
product source, timeout, expected value, case, skip or xfail. The earlier
discovery-route fixture is unchanged. Production will not inspect or undo
test monkeypatches to satisfy this check.

Exact patch: patches/ryan-proposed-read-fixture-2026-09-09.patch, **649 bytes**,
SHA-256 `32ecbcce8d4040308324cc739914eb56106535e91e780991d7cc02683659a0f5`.
The five-file reproduction/audit seal is
proof/ryan-read-order-2026-09-09/SHA256.json. This proposal is separate from
the three-file mirror-hook proposal and the historical AT6 exit gap.

After explicit approval, apply only this patch, run the same ordered pair,
then the named read/prompt/resource companions and final complete candidate
tree. Any residual failure remains a failure and needs its own diagnosis.

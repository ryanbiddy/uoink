# Controller10 test-contract diagnosis

2026-09-14 — two expectation defects; no product defect identified in these refusal branches. Source-only diagnosis by the test author, not an independent acceptance review.

| Failed subgroup | Expected in admitted test | Contract and recorded result |
|---|---|---|
| wrong_permit, test line 128 | REFUSALS | SessionClosed: "Native permit is stale or already consumed". Final durable factory lines 560–566 reject the changed raw permit before owner/create. |
| active, test line 300 | fail_start default REFUSALS | SessionClosed: "Factory start owner is not live and unpublished". Final durable lines 511–514, called at 659 after real bind, reject active ownership before pre-resume/resume. |

Both SessionClosed and LifecycleUnavailable directly subclass RuntimeError in unchanged snapshot_lifecycle.py; one is not a subtype of the other. The briefs require these refusals and error preservation, without selecting the test's narrower tuple.

The author run remains 8/2/0, with 104 subtests: 102 pass, two fail. Its ten guard flags are true and qualification_exit is 1. The recorded messages match the exact called branches. No rerun occurred. Passing guards do not make the two cases pass.

The proposed UNAPPLIED patch selects SessionClosed only for these two named faults. It does not broaden REFUSALS or alter product source, fixtures, case membership, fault timing or downstream assertions. In the failed subgroups, assertions 149–155 and 301–309 were skipped after the unexpected exception type and remain unverified.

See PROPOSED-EXPECTATIONS.UNAPPLIED.patch.txt and REASON.md. Root will seek approval for this concrete change; 58335df supplies no authority for it. All original sources and failed receipts stay unchanged. Complete source hashes and passive checks are recorded beside this verdict.

# Living Library candidate delivery, 2026-09-09

The local candidate bundle is complete. **Release approval remains blocked** by
Ryan's installed receipts and the recorded test/contract dispositions. No main
merge or publication has occurred. The agreed release scope and all phases are
in [the full notes](RELEASE-NOTES-LIVING-LIBRARY.md).

| Deliverable | Recorded identity |
|---|---|
| Receipt ZIP | build/Uoink-Living-Library-3-8-0-Receipt-Kit-2026-09-09.zip |
| ZIP bytes | 358,530,295 |
| ZIP SHA-256 | 7fb55a3a121aa99d56c2b652bdf1c979167baeba5085f92b13af233c1a5fc655 |
| Manifest SHA-256 | 034fde70e8205c287c55cc9fb4f776d16066adfc02f3585ed403c31088c14007 |
| Bundle source | 25d043cbd9e3035a38e0e466d33d6ff18f927e84 |
| Whole-tree validation source | 12ce8a5fbd34c3472d55ae76afa17535b43c5282 |
| Installer build source | 67a274d5d0c67f48405c4fa242a1011c2cf671c1 |
| Installer SHA-256 | a89112bb53425cbd9c5c0c662a2f239cbdde069294af9389c90021ddc2af60fe |

All 771 payload files and the manifest passed ZIP and extracted-file checks.
The exported operator preparation passes both commands and creates all nine
profiles. The final ZIP contains 71 byte-identical measured inputs; its two
operator manifests differ only in the recorded bundle-source commit. This is
not a repeated product measurement. No packaged source changed after the tree,
so another installer rebuild is unnecessary.

Full tree: **2,429 passed / 13 failed / three skipped / one xfailed**,
183 warnings, 1,542.35 seconds; only standing S21 excluded. All 178 new cases
are present and no prior case is missing. The prior ten failures remain, plus
three already reviewed receipt-test conflicts. The failed result is unchanged.
Original bundled C22 separately has **11 passed / zero failed / three unexecuted**;
Phase 4 has **15 passed / zero failed / eight unobserved**. No installed credit.

The [archive seal](proof/ryan-final-receipt-bundle-2026-09-09/SHA256.json) retains
both manifests, verification details and builder/checker scripts. The ZIP stays
local; it is not pushed into Git. The authorized branch backup's independent
transport result is written to build/Uoink-Living-Library-3-8-0-Receipt-Kit-2026-09-09.backup.json. Check verified=true
and its source/remote values; absence or failure is not a completed backup.

Next: use [the exact runbook](INSTALL-RECEIPT-RUNBOOK-2026-09-09.md) once in a
throwaway Windows account, then return the private receipt directory for review.
The two exact fixture proposals, three receipt-test conflicts and original AT6
exit gap remain open as described in [the final disposition](FINAL-RELEASE-VALIDATION-2026-09-09.md).
No extra fixture changes were made. Phase 2 keeps 0.90/apply false; X 403 stays
blocked; speakers remain outside the Phase 6 release scope; Phase 5 Part B is
deferred. Main merge and release approval are Ryan's decisions.

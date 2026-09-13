This proof preserves the original defect, failed verification attempts, two
product repairs and the passing worker/checkout verification. Extracting the
ZIP is optional: verify_archive.py checks every member in place using only the
Python standard library. No test, product module or model is executed.

| Attempt | Actual outcome | Qualification |
| --- | --- | --- |
| Keyword probe01 | Exit 1, zero cases | AST setup failure; observed failure receipt preserved |
| Keyword probe02 | 2 passed, 1 failed; exit 1 | Original default incorrectly enabled acquisition |
| rlw01 | 53 collected, pytest/verifier 0, outer 1; no tests or Node children | Invalid guard: local gethostname refused |
| rlw02 | 47 passed, 6 failed, 13 passed subtests; exits 1 | Invalid test guard: five Node startup refusals; alias case also failed |
| rlw03 | 51 passed, 2 failed, 13 passed subtests; exits 1 | Valid guards; exact alias and cross-model-size defects reproduced |
| rlw04 | 53 passed, 13 passed subtests; exits 0 | Valid guards, 36 valid Node children |
| rlc04 | 53 passed, 13 passed subtests; exits 0 | Valid guards, 36 valid Node children; same case membership and final bytes |

The passing runs each have 53 top-level testcase elements and JUnit tests=66
because 13 passing subtests are counted separately. Do not describe 66 as the
number of collected tests. Earlier failures remain failures.

receipts.zip contains 563 exact documentary members. ZIP-MEMBERS-SHA256.json
binds every member's size and bytes; INPUT-LIST.json adds the original source
path. The four preparation children retain their original manifests and every
listed payload unchanged: 31, 36, 33 and 35 payloads. Their subsequent raw runs
are separate. Original worker files and the final raw patch are retained.

The archive also preserves root admissions, every generated verifier and
membership receipt, Node stdin/stdout/stderr/argv/guard records, actual outer
exits, the final admitted source/tests/report and the CRLF transport correction.
Probe01's initial shell log was not present as a standalone raw file; its source,
observed exit/failure receipt and setup repair are preserved without inventing
a missing transcript.

No temporary fake cache/model/audio/database data, model assets, runtime
executables or unrelated scratch were selected. The Node executable hash is
recorded in receipts; the executable itself is absent. The inventory's initial
.html omission and its explicit preparation repair are preserved in the outer
proof. No credential exclusion or evidence redaction was required.

Run the documentary validator from any working directory:

```powershell
& 'C:\Python314\python.exe' -I -S -B 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\reliability-integration-proof01\verify_archive.py'
```

Add --check-source-disk to compare the archive against the exact 563 approved
source paths as well. This option requires those original paths still to exist
unchanged. Root can separately verify the outer SHA256.json against Git-staged
bytes. VERDICT.md records the independent source review and its coverage limit.

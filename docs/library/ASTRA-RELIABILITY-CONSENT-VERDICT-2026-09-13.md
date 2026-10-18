# Reliability consent and settings review

2026-09-13. Accept the scoped product repair from Grok run
0851b440-86a5-4ced-8d33-cbdbd27d6e9c, with Astra's two documented corrections.
Ordinary reliability loads now require local files. Readiness requires the
consent marker and a complete contained snapshot. Settings include Turbo and
use the selected model's approximate size, or state that its size is unknown.
Repository mappings and all existing assertions remain unchanged.

The original-source probe recorded two passing controls and one failed
ordinary-default requirement, actual exit 1. The first probe failed before
cases because it accessed the wrong AST field; its failure and repair remain.
The completed worker patch was preserved before adding independent regressions.
A valid baseline then reproduced two remaining defects: resolving a cache root
before checking aliases, and borrowing the saved model's size for an unknown
unsaved selection. Astra corrected those two product lines under brief b109e66.

| Attempt | Actual result | Disposition |
| --- | --- | --- |
| rlw01 | 53 collected; pytest/verifier 0, outer 1; no tests ran | Invalid guard: local hostname query refused |
| rlw02 | 47 passed / 6 failed, plus 13 passed subtests; all exits 1 | Invalid Node startup guard; five UI failures occurred before the harness, one alias assertion failed |
| rlw03 | 51 passed / 2 failed, plus 13 passed subtests; all exits 1 | Valid baseline: both documented product defects reproduced |
| rlw04 | 53 passed, plus 13 passed subtests; all exits 0 | Corrected worker union accepted |
| rlc04 | 53 passed, plus 13 passed subtests; all exits 0 | Same checkout union accepted |

Every valid execution used all nine named files, unchanged membership and
assertions, 36 recorded Node children and valid Python/Node guards. The worker
base is 6774d197; checkout verification used HEAD01a30247 plus the exact applied
patch. Input hashes remained unchanged. Raw patch SHA-256 is
bb3d7c2aa0309d9bf71aac17b4bf0caf4a014dd2ec06dcd28871866fe49bc1d4.
Three-way application was clean. Seven CRLF-only working-file differences were
verified and restored to exact worker bytes before checkout verification.

Each instrumentation rerun has a retained repair. The actual local hostname
caller was jaraco.context through platform.system; the earlier JUnit explanation
was an unobserved hypothesis and is withdrawn. Node's versioned startup source
supported defining its global module slot before import closure, without adding
a module allowance or changing the frozen UI harness. The tests use fake DOM,
fetch and constructors; they provide no native model or ordinary-client credit.

Independent source review found no blocking defect within this brief. Two
worker directory-creation assertions run after temporary-directory cleanup and
therefore do not independently prove that property; source review confirms the
creation call is limited to explicit acquisition. Those assertions were retained.
The worker's reported helper execution exceeded its syntax-only Python allowance
and has no independent raw receipt; it is not acceptance evidence here.

Structural readiness does not authenticate model bytes or establish usable
tokenizers, a stable native-use lease, safe VAD, or runtime compatibility. The
current complete-tree result predates this repair and remains 2,796 passed,
one failed, three skipped, plus 13 passed subtests. A new complete run is due
after the remaining source work settles. No package, installation, website,
marketing or market-readiness acceptance follows from these focused passes.

The [sealed proof](proof/reliability-consent-integration-2026-09-13/SHA256.json)
contains 19 payloads and an archive of 563 individually hashed members. Root
verified all archive members against their original files. The first Git/disk
check failed because an ignore rule omitted receipts.zip from staging; the
exact sealed archive was force-added before fresh validation. No proof or test
bytes changed to repair that staging failure.

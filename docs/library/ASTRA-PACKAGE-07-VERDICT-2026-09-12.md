# Package-07 qualification verdict

The SQLite cleanup repair is qualified in the complete test tree and built into
a new installer. Fresh installed observations remain required. The aggregate
test result is FAIL because the historical AT6 exit-record assertion still
fails; no new product failure appeared.

Frozen source 6a89189d601467eeff33d304c2c9b69cdd2e6d0b records **2,540 passed,
one failed and two skipped**, across 2,543 cases. Every prior case is present,
and all five added real-SQLite regressions pass. The disjoint main/media processes
ran with --runxfail and retained the original assertions and fixture guard.
Only the previously excluded S21 suite is absent. The two skips are POSIX build
execution and unavailable Windows symlink privilege. Test processes took
1,779.570 seconds; including collection, 1,794.078 seconds. The
[44-payload tree seal](proof/ryan-final-partitioned-04-2026-09-12/SHA256.json)
retains membership, reports, XML, process exits and the original failure.

| Package field | Observed value |
|---|---|
| Build source | 6a89189d601467eeff33d304c2c9b69cdd2e6d0b |
| Installer | Uoink-Setup-3.8.0.exe, package-07 |
| Bytes | 389,569,575 |
| SHA-256 | 308205ec6273dafe3fb0b2f5273e713803e6e78ea989d883217ecd813a17d32b |
| Build interval, UTC | 2026-09-12 08:02:41 to 08:10:09; 448.374 seconds |
| Runtime | Python 3.13.15; MCP 1.28.1; schema 30 |
| Compiler inputs | 32,506: 32,497 installed files, eight wizard images, one setup-only script |
| Source bindings | 142 matching checkout/staged files |

The staged startup checks pass. All 140 runtime pins match and all 283 active
dependency requirements are satisfied. All 983 compared repair-wheel payloads
match the independent Lightning/setuptools downloads, excluding the explicitly
recorded installation-rewritten RECORD files. The packaged WhisperX checkpoint
is unchanged; no checkpoint inference, diarization or source acquisition ran.

Notices-only commit f9d9f1f changes the generation and review dates. The review
again obtains 50 license expressions from the exact staged metadata and leaves
seven absent declarations unknown. Notices are outside the installer inputs.
No packaged source changed after the complete tree. The final export includes
the fresh dependency graph and pin/checkpoint records before creating its seal;
its pre-execution instrument changes are retained.

Defender's custom scan exits zero and reports no threats, with equal before/after
EXE hashes. Antivirus and real-time protection remain enabled; existing cloud
policies are unchanged. The EXE is unsigned. The dated raw OSV result of 19
entries / 15 issues remains open and is not cleared by this scan. See the
[85-payload package seal](proof/candidate-package-07-2026-09-12/SHA256.json).

Package-06's EXE is preserved byte-identically, along with its existing ZIP and
all failed/partial client evidence. The authorized backup branch was verified
at 6a89189 before this documentary checkpoint. The new isolated installation,
C22/browser observations and bounded client/range checks follow the
[qualification brief](SQLITE-REPAIRED-CANDIDATE-QUALIFICATION-2026-09-12.md).
No ordinary upgrade, main merge or publication is approved by this verdict.

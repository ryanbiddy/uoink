# Candidate verification, updated 2026-09-10

At `393010f80c53a95a6fa3c853a98b77924efa0250`, the complete partitioned tree
records 2,493 passed, 1 failed, 2 skipped and 1 xfailed. Its aggregate status is FAIL. The two actual
test-process exits, complete node lists, original XML/logs and per-test reports
are retained in [the final proof](proof/ryan-final-partitioned-02-2026-09-10/SHA256.json).
The result is a two-process aggregate, not a monolithic pytest pass.

All 2,497 collected cases are accounted for exactly once across the two test
processes. Only tests/library_work_astra/test_phase3_s21.py is absent. Compared
with the preceding 2,493-case collection, four embedded-probe regressions
were added and no case is missing. Existing tests and P4's in-process guard
are unchanged. The first process retains normal order except for the two media
cases; the second runs those exact cases with verified private GPL FFmpeg tools.
Those tools do not ship in the installer.

The only failed case is the unchanged historical AT6 exit assertion. New probe regressions pass; no previous case is missing.

The earlier monolithic tree at `7109182` retains 2,484 passes, three failures,
two skips and one xfail in 1,568.94 seconds. Two media cases were refused by the
P4 parent guard before FFmpeg could start. Removing that guard was rejected
because the parent later imports product modules. The documented partition
repair changes execution conditions while preserving the original assertions.
Earlier passed labels from the long-video test's early return without FFmpeg
did not establish execution of its media body.

The original AT6 shell wrapper discarded the child exit. A replacement run
cannot reconstruct it. Its unchanged audit assertion stays failed and requires
Ryan's release disposition. SEC-06 remains the existing expected failure for
non-ASCII search parsing. Neither limitation is counted as a successful repair.
The two skips are the POSIX build case and the Windows symlink case without the required privilege. No privilege or protection setting was changed.

Package-05 was built from `6b5aed8`, then its generated notices were reviewed
at `45cd6f7`. The notices are outside the compiler inputs. The package has
32,063 compiler inputs: 32,054 installed destinations, eight wizard resources
and one setup-only script. Its 142 source bindings distinguish the 141 installed
source files from that script. All 139 actual runtime distributions match the
Python 3.13 lock; the reviewed LGPL CLI and shared-decoder runtimes are separate.
See [the package seal](proof/candidate-package-05-2026-09-09/SHA256.json).

Actual Setup and same-version reinstall each exit zero in Agent Install 05,
outside the checkout under the same non-elevated Windows account. All 32,054
installed file hashes match. The original installer observer refused the
OneDrive-redirected Desktop before Setup; the reviewed supplement records its
metadata without traversing contents, verifies actual empty Tasks settings and
checks the actual Inno/shortcut/registry effects. Ordinary Uoink was not replaced.

Installed C22 records **11 passed / zero failed / three unexecuted manual
placeholders**. Four actual browser images are paired with the same persisted
state before, after and after stop. Only labels/timestamps change. The visible
source/allowance/idle state agrees; consent revision and the worker_lost outcome
are not shown, so the visual receipt remains **partial**. The helper exits zero,
its port is freed, and guard/interpreter bytes are restored. See the bounded
[browser repair brief](BROWSER-RECOVERY-UX-REPAIR-BRIEF-2026-09-10.md).

Installed image/encryption and product-loader WAV observations pass using
temporary no-site instrumentation, with byte-exact interpreter restoration.
They establish instrumented decoder compatibility. The original launcher and
startup-flag failures are retained; no model download or inference occurred.

After receipt repair `393010f`, the original installed Phase 4 route observes
32 tools, five resource templates and four prompts. Its collector records
**15 passed / zero failed / eight unobserved**, with zero product findings.
Native packets/prompts, reconnect, storage refusal, Recall silence, protected
bytes and mirror/deletion checks have separate evidence. The raw collector's
overall installed_credit remains false; it is not a completed client gate.
Owned transport termination retains exit one and is not described as a graceful
client exit. The first prepare import failure and missing-input collection
refusal remain recorded.

See [the installed evidence seal](proof/ryan-agent-installed-05-2026-09-09/SHA256.json)
and [Astra's installed verdict](ASTRA-INSTALLED-CANDIDATE-VERDICT-2026-09-10.md).

Fresh isolated client configuration is prepared, empty and unsigned-in.
No ordinary credentials were read or copied, and no client/model was invoked.
Fresh subscription sign-in and confirmation that extra paid usage is off remain
user-controlled prerequisites. Actual ordinary/Recall client streams, hostile
client actions, and visual citation/brief/chapter flows remain unobserved. X's
historical HTTP 403 and BD-27's earlier player observation retain their separate
scope; neither was fetched again. The eight unobserved collector rows include
the optional player row and are not eight newly failing product features.

The complete test tree uses the private Python 3.14 verification environment.
Actual installed observations use Python 3.13.15 and the original installed
application files. No main merge, new source fetch, speaker claim, paid API or
Phase 5 Part B is included. Remaining dependency advisories and the unsigned
package stay explicit in the [release notes](RELEASE-NOTES-LIVING-LIBRARY.md).

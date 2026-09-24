# Native binaries and media execution: integrator verdict

The diagnostic is accepted; its proposed guard deletion is rejected. The native
review identifies an outdated FFmpeg pin, but does not establish a clean security
audit or justify retaining Python 3.11.9 without testing upgrade feasibility.
Both original Gemini reports and their raw patches remain part of the record.

Gemini e0082e87 traced the full-tree failures to p4_prepare_fixture.prepare's
in-process execution of the receipt audit hook. Astra reproduced the exact
P4-then-media sequence in both roots: one passed / one failed, 1.93 seconds
in the worker and 1.57 seconds in the checkout. These are negative diagnostic
observations. The guard refused FFmpeg before execution. The worker separately
observed the short media test passing and the long test failing for libx264.
Its first diagnostic-wrapper attempt is also retained; the report lists only
the corrected wrapper among its five principal observations.

Deleting the guard installation would leave subsequent _load_installed imports
and fixture preparation unguarded in that process. A successful child canary
does not protect its parent. No guard, product file, fixture, assertion or skip
is changed. Under the final-media repair brief, the final tree will use two
processes: the two original FFmpeg cases in a dedicated process, and every other
case in the usual process and order. Both retain the integrator's live-index,
network, model-process and 5179 prohibitions. The P4 preparation guard remains
active for the full lifetime of its own process. Record exact node IDs for both
partitions, require disjoint sets and their complete union, and retain per-process
logs, XML, actual exits and an explicitly labeled aggregate. Only S21 is absent
from the overall union. This is an execution-condition repair, not a monolithic
pass or a replacement for the failed 7109182 observation.

The shipping pin repair targets the retained August 2026 LGPL 8.1.2 archive,
whose SHA256 is f6274bbd9c247f9e90c1bbed066b03ed4a3907cece2fb91be6dd352393936365.
The independent download is 146,078,616 bytes and matches both GitHub's release
asset digest and the release checksums file. A separate September 9 GPL 8.1.2
archive supplies libx264 only to the private test PATH. It is never a compiler
input. Both scans exit zero with unchanged bytes; neither scan certifies freedom
from vulnerabilities. Exact archive, extracted binary and version receipts are
retained. The original two GPL media cases pass in both roots (2.86 and 2.24
seconds). The shipping LGPL observation has four passes in 2.68 seconds:
three original screenshot cases and one independent long-video/audio probe.
Its first observation has three passes / one failure because Astra's new probe
omitted the production caller's interval-cap loop. That failed probe, unchanged
assertion and precise instrument correction remain sealed alongside the rerun.
No original test changed. Proof: proof/ryan-native-guard-review-2026-09-09/SHA256.json.

Corrections to Gemini a8752e4f's native report:

- Its libx264 section identifies a real prerequisite, but the recorded full-tree
  failures were guard refusals. No decoder ran in those two failed cases.
- Package-04 has 32,227 compiler inputs and 32,218 installed destinations, not
  25,781 inputs. No Setup had run; installed-byte equivalence was still unobserved.
- Hash equality establishes byte identity with the recorded input. It does not
  prove publisher identity, deterministic builds or the absence of extra files
  unless the corresponding checks were actually performed.
- The unsigned installer can encounter Windows reputation warnings; their exact
  appearance is not guaranteed or observed by a signature-status query.
- Later upstream FFmpeg releases list fixes absent from the dated pin's release
  history. This does not prove that every listed CVE exploits Uoink's build.
- Python 3.11.9 is the final official 3.11 Windows binary. Python 3.12 is also
  past binary maintenance. Astra therefore commissioned exact-pin Python 3.13.15
  qualification. A minor ABI change requires new wheels, but does not by itself
  prove that the 142 package versions need changing. No runtime upgrade is yet
  accepted, and no model or diarization execution is authorized.

The first raw-patch export used a nonexistent checkout-root patches directory;
Git wrote no patch and both apply attempts failed. Re-export to the existing
scratch directory and three-way apply succeeded, with Git's new-file direct
fallback. No test was rerun to conceal this file-operation error.

Next: review the bounded FFmpeg pin change, finish Python qualification, verify
the unchanged media cases and shipping decoder, then freeze and measure the
complete partitioned tree. Preserve package-04 before any replacement build.
The prepared Agent Install 04 profile remains uninstalled. Actual installation
and everyday-flow evidence remain Astra's delegated work.

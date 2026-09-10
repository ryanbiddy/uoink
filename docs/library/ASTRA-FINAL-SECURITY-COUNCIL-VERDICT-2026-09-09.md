# Security council: integrator verdict, 2026-09-09

The current installer is not yet cleared for the delegated installed-helper
check. Gemini Role B identified a shared credential-store namespace, confirmed
by Astra in server.py. RYAN-ISOLATED-CREDENTIAL-REPAIR-BRIEF-2026-09-09.md assigns
the repair and fake-backend regressions. Rebuild the changed server before any
new installed-helper observation. Do not query actual stored credentials to
demonstrate the defect.

Role A's named isolation suites independently pass **53 tests** in its worker
(7.51 seconds) and checkout (6.75 seconds). Role B's named security suites
independently pass **40 tests with one existing xfail** in its worker (1.38
seconds) and checkout (1.18 seconds). The xfail is the documented non-ASCII FTS
search defect, not a newly accepted security fix. Both raw report diffs were
integrated through git apply --3way; new-file patches used Git's direct fallback.

The Gemini reports are retained as worker assessments, not certification.
Astra does not adopt Role A's absolute claims such as impossible collisions,
airtight isolation, or no possible credential-store access. Skipping migration
does not skip server key reads. Its description of marker persistence as atomic
is unsupported: Inno writes with SaveStringToFile and then verifies the bytes.
Its 51-case inventory is also superseded by the observed 53-case result.
An empty MERGETASKS is not relied on to disable default desktop tasks.

Role A correctly identifies the isolated uninstall registration and shortcuts
as host-account effects. The previous runbook uses a separate Windows account.
Ryan has delegated the installation; a reviewed supplement may observe the
supported isolated app/profile in this account, but must record the actual SID
and host effects and cannot claim a fresh Windows-account observation. That
supplement is not yet executed. No elevation, antivirus/firewall change or
system-feature installation is authorized or required by this review.

Defender's custom scan of package-03 exits zero and reports no threats; package
bytes are unchanged. It used the existing Defender configuration, with cloud
and sample settings unchanged. The installer is unsigned. This scan does not
establish absence of all malicious behavior. A public OSV lookup of the exact
142 pinned package versions completed: seven packages have 95 advisory entries,
including aliases. This is not 95 distinct vulnerabilities or an exploitability
verdict. All 95 full records were fetched for applicability review. Only public
package names/versions were sent. Raw evidence is sealed with the council. The
lookup uses the documented OSV batch API:
https://google.github.io/osv.dev/post-v1-querybatch/.

Existing documented limits remain: same-user programs are outside the local
trust boundary, prompt fences do not guarantee model obedience, wheel artifacts
are not hash-locked, and source-fetch scope has not expanded. Do not change the
X blocked-link decision or run speakers/diarization as security work.

Proof: proof/ryan-security-council-ab-2026-09-09/SHA256.json.

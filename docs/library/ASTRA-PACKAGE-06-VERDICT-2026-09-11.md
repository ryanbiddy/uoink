# Package-06 verdict

The repaired 3.8.0 candidate builds from
`6697dffc30c98e97b22ecc9a5a35dfd3e8a91f5d`. Its EXE is 389,568,844 bytes,
SHA-256 `91120b4a8d1baf13c4b20aab098e889fab008c7ce4e4bea59d68a052fe8224cb`.
Build time was 415.509 seconds, from 18:10:15 to 18:17:10 UTC on September 11.
This verdict authorizes the already delegated isolated receipt procedure;
it does not approve an ordinary upgrade or public release.

The [complete tree](REPAIRED-CANDIDATE-VERIFICATION-2026-09-11.md) on the same
source records 2,535 passed, one historical AT6 failure and two skips. The
installer contains Python 3.13.15, MCP 1.28.1 and schema 30. All 140 exact runtime
pins match staging; all 283 active dependency requirements are satisfied.
Staged startup checks pass, including server, desktop modules and WhisperX.

The [package seal](proof/candidate-package-06-2026-09-11/SHA256.json) records
32,506 compiler inputs: 32,497 installed destinations, eight wizard images and
one setup-only script. The 142 source bindings include 141 installed source
files and that separate script. These counts describe compilation inputs;
actual Setup and installed-file evidence follow separately.

All 983 compared payload files from the two Lightning 2.6.6 wheels and
setuptools 83.0.0 match the independently verified downloads. Only the RECORD
files rewritten by installation/build are excluded. The packaged WhisperX
checkpoint remains 17,719,103 bytes with its prior `0b5b3216...e209ea` hash.
No model download, checkpoint loading or inference was part of this comparison.

The [fresh audit](proof/repaired-lock-audit-2026-09-11/SHA256.json) retains
19 raw OSV entries / 15 alias groups in four top-level packages. Both Lightning
2.6.6 namespaces contain the verified upstream repair; OSV's inconsistent fixed
event remains in the unfiltered record. NLTK, Torch and Transformers findings
retain their prior reachability and compatibility limits. A separate query of
the 12 distributions vendored by setuptools returns zero entries. This is not
a complete security clearance or a scan of every native library.

Defender's custom EXE scan exits zero, reports no threats and preserves the
package hash. The EXE remains unsigned. Existing protection/cloud/sample
policies were unchanged. Same-account isolation does not contain same-user malware.

Notices commit `d363c04` is the only change after the frozen build source.
The raw generator output is retained. Fifty UNKNOWN license fields are filled
only from exact packaged License-Expression metadata; seven remain unknown.
The declarations do not replace the shipped license files. Notices are outside
the compiler inputs, so this documentary review requires no rebuild. Future
builds must repeat this metadata review while the generator lacks those fields.

Package-05's exact EXE and review ZIP remain preserved. Its owned isolated
test app was uninstalled with exit zero; ordinary observed settings were unchanged
and the old receipt profiles remain. Package-06 requires fresh app/profile paths
and fresh C22/P4 observations, with user-controlled client sign-in still separate.

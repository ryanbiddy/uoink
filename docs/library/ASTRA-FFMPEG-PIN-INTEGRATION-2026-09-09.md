# FFmpeg pin integration verdict

Accept Gemini cadfc013's bounded build change. Independent verification of all
seven named build, lock and documentation suites has 36 passes in each root:
4.09 seconds in the worker and 3.10 seconds after three-way checkout application.
The four core suites are included in that union. No existing test changed.

The build now selects the retained August 31 LGPL 8.1.2 archive, hash
f6274bbd9c247f9e90c1bbed066b03ed4a3907cece2fb91be6dd352393936365, and a new
versioned cache filename. The old cached archive remains intact. Astra already
verified the actual download against two published hash records, scanned it,
and qualified the extracted shipping decoder on synthetic media. GPL is a
private test dependency only. Its distinct version and digest are recorded.

The worker report's attempted corrections still cite the old package-03 input
count and incorrectly explain the full-tree failure as a missing encoder.
Package-04 has 32,227 compiler inputs / 32,218 installed destinations; its two
media failures were P4 guard refusals. The old long test returned early with a
passed label when FFmpeg was absent; this was not a pytest skip. The current
source emits repeated frames through an fps filter, not only a single-frame
command. ASTRA-NATIVE-AND-GUARD-REVIEW-2026-09-09.md controls these distinctions.
Preserve the raw report without treating those statements as accepted evidence.

The worker's missing-startup-variable and refused network attempts are reported
as failed invocations. Its four raw suite observations, Astra's independent
observations, exact patch and brief are sealed in
proof/ryan-ffmpeg-pin-repair-2026-09-09/SHA256.json. The native archive, scan and
decoder records are in the preceding native-guard proof seal. These checks do
not certify absence of vulnerabilities or complete installation behavior.

The compiler input changed, so preserve package-04 and produce a replacement
after Python qualification. Then run the complete accounted tree and the
delegated isolated installation. No Setup has run yet.

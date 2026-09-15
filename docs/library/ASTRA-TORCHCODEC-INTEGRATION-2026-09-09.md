# Packaged decoder integration verdict

Accept Astra's bounded repair from the detached 9ce27a2 worktree. Gemini's
c662e389 run failed at the subscription limit without a diff; it did not review
this implementation. No paid fallback or new model run occurred.

The seven existing build/doc/lock suites, existing podcast workflow suite and
three new loader regressions passed independently: 42 tests in 4.43 seconds in
the repair worktree, then 42 in 1.96 seconds in the checkout. Git applied the
raw patch cleanly with three-way application for existing files. Existing tests
and the P4 parent guard are unchanged. The three new cases cover the exact
application directory, retained handle, incomplete installation and redirected
DLL refusal.

The build extracts seven exact members of the pinned LGPL shared FFmpeg 7.1.5
archive into bin/torchcodec. whisper_runner.py registers that resolved directory
before lazy WhisperX imports, retains its handle, and rejects missing or
redirected libraries. The server imports this same module. Standalone LGPL
FFmpeg 8.1.2 and Python 3.13.15 remain unchanged. Notices identify both ABIs.

A real Python 3.13.15 / PyTorch 2.8.0+cpu / TorchCodec 0.7.0 process imported
the repaired product module from a staged application layout, then decoded a
generated WAV into one channel and 16,000 samples at 16 kHz. It passed with
zero network/subprocess guard events and no model. This is staged-layout
evidence; installed decoding is still owed. The downloaded archive matches the
recorded upstream checksum and its unchanged Defender scan reports no threats.
The proof is proof/ryan-torchcodec-repair-2026-09-09/SHA256.json.

This changes packaged source, so package-04 is retained separately and a new
package is required. The exact committed final source needs the complete
partitioned tree before Setup. Native checks do not clear the remaining Python
advisories, unsigned distribution or historical AT6 receipt gap.

Record correction: python313-conflicted-application.patch in the preceding
Python proof is empty. It is not a conflict-diff receipt. The original worker
patch, actual application outcome and resolved final diff remain preserved.
Approximate minute labels on three preceding handoff entries have been removed;
the dated entries and actual command/commit timestamps remain authoritative.

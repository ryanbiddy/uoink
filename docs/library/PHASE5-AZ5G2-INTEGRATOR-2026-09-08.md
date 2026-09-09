# AZ-5g2 integration verification and transport supplement

Independent G2 union: **574 passed, two failed** in each root, 117.69
seconds worker and 126.97 seconds checkout. Commands, logs and XML are in
worker scratch `az5g2-wi` and checkout scratch `az5g2-ci`. The two failures
remain the frozen unary/clock fixture and the replaced BA-4 SDK route.
All four measurement-document cases now pass. No existing test changed.

The original G2 source base is `d1d5fb8`, tree
`079170c1f70f4addcfaed15006a51f751ae60f67`. Its four analysis/resource/MCP
production blobs match the checkout at `9a089fa`. All nine captured reader
packets, every pagination total/returned/omitted count and seven corresponding
live-reader shipped frames were checked from the retained complete bytes.
Each shipped packet equals its reader packet. The 548/10,000 primary frames
are **64,732 / 64,601 bytes before newline**, or 64,733 / 64,602 with it.
The missed 24,576-byte dashboard target remains disclosed.

## Separately observed exchange boundaries

The supplement brief is `PHASE5-AZ5G2-SUPPLEMENT-BRIEF-2026-09-08.md`.
The original G2 activity frames remain untouched. The additional observation
retains **104 events, all 24 input frames and all 16 output frames** across
eight exchanges, including each initialization response. It records input
delivery, actual SDK serialization, output write and flush. Every response
flush observes one held admission; every exchange ends with zero. All frame
lengths and hashes were recomputed from the lossless bytes.

| Exchange | Input delivery to response flush | Result |
|---|---:|---|
| 548 primary | 46.398 ms | success |
| 10,000 primary | 464.668 ms | success |
| 548 with three memberships | 65.571 ms | success |
| 50 items, ten operations | 10.055 ms | success |
| 100,000 observations | 892.353 ms | success |
| 70 MiB journal | 43.156 ms | typed refusal |
| 548 proved replay interval | 64.204 ms | success |
| Expired inbound | 1.078 ms physical elapsed | typed refusal after a separately recorded 2.1-second clock injection |

This drives the actual shipped writer with observed **in-memory I/O**. It is
neither a physical stdio-pipe measurement nor a real-client receipt. Instrument
recording contributes overhead. These observations do not guarantee every
load or storage environment meets the same time.

Separate profiling passes directly observed populated replay state on both
548 and 10,000 primary fixtures. Both returned partial coverage with
`interval_precedes_first_apply`. They use an explicit 30-second diagnostic
deadline and establish path execution, not normal deadline performance.
The reused helper's `path` label says 548 in both records; `db_key`, the exact
database path and measured dimensions identify the actual scale. This label
limitation is retained rather than silently changing the original output.
All six immutable synthetic database hashes match before and after.

The exact executed supplement script and outputs are under
`proof/az5g2-supplement-2026-09-08/`. Its original invocation used the scratch
copy `az5g2_supplement.py`, the finished G2 worker and fresh output directory
`az5g2-supplement-01`. A new execution needs a new brief and fresh scratch
output; do not overwrite either retained measurement set.

## Byte preservation and earlier attempts

`proof/az5g2-2026-09-08/INTEGRATOR-SEAL.json` maps all 36 entries in G2's
original working-byte manifest to preserved bytes. The old rejected Gemini
patch had CRLF in G2's worktree and LF in its pre-existing Git blob. Its exact
G2 working bytes are archived separately as `rejected-az5g-worker-bytes.patch`;
the original patch is unchanged. The remaining original manifest entries
retain their observed bytes. The final artifact manifest covers the added
raw command logs, validation and supplement too.

Three-way integration conflicted only in `.gitattributes`; both AW-8 and G2
preservation rules were kept. The G2 proof blobs in the index matched their
hashes, but some initial working files had newline conversion while that
conflict was unresolved. Restoring them from the verified index after resolving
the attributes preserved their exact bytes. The G2 measurement document,
report and two instruments also have explicit byte-preservation rules.

G2's first measurement launch failed at SDK import on missing `pywintypes`.
It produced no measurements. Resolving the installed pywin32 paths allowed
the measured run. Its first union launcher returned before pytest because
`os.execv` did not wait in that Windows invocation; `subprocess.run` repaired
the launcher. The empty launcher output is not a passing union. All four raw
command records, including those two failed/incomplete attempts, are retained
under `proof/az5g2-2026-09-08/worker-command-records/`.

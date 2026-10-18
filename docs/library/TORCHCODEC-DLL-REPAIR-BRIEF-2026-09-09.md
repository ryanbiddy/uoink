# TorchCodec native dependency repair

Gemini: bounded product/packaging repair in your worktree; no subagents or commit.
Read the Standing rules. Astra's exact Python 3.13.15 disposable runtime has 139
resolved and installed dependencies with unchanged retained versions. Its guarded
native probe has 15 passes / one failure. The failure is torchcodec==0.7.0:
libtorchcodec_core7.dll exists but cannot load a dependency. Static FFmpeg.exe
does not supply FFmpeg shared DLLs. The installed PyAnnote audio reader imports
TorchCodec, catches failure and disables file decoding. Diagnose precisely rather
than attributing this to Python ABI. No model, weights or diarization run.

Evidence in main checkout:
_scratch/python313-runtime-probe-01/results.json and guard-events.json;
_scratch/python313-graph-01/python/Lib/site-packages/torchcodec/_core/ops.py;
_scratch/python313-graph-01/python/Lib/site-packages/pyannote/audio/core/io.py.
The main checkout currently holds Astra's reviewed Python 3.13 pin/139-lock diff
awaiting commit. Your Control Room frozen base may precede that patch. Preserve
the already integrated static LGPL FFmpeg 8.1.2 pin and all existing tests.

Find a compatible patched LGPL shared FFmpeg 7 runtime using public primary
metadata, preferably BtbN's retained July 31 2026 7.1.5 release. Verify exact tag,
archive URL/hash and dependency DLL inventory. Do not use an old vulnerable 7.1
snapshot or ship GPL. Do not download models/media or use paid API. You may
download/inspect a checksum-verified software archive but do not execute its
binaries; Astra scans and executes. No OS installation, PATH/registry permanence,
elevation, AV changes, credential query, live index or port 5179.

Implement the narrow missing-runtime packaging/loader repair if confirmed:
versioned pinned archive/cache; stage required shared DLLs in an app-owned
subdirectory; preserve licensing/source notices; explicitly register only that
trusted app-relative directory before the real transcription imports, retain the
DLL-directory handle for process lifetime, and avoid current-directory or user
PATH DLL search. Existing standalone FFmpeg 8.1.2 remains the CLI decoder. Cover
the actual server and transcription entry path; do not add a fake TorchCodec
module, suppress the warning or alter a third-party package/test to hide failure.

Add small independent loader/build regressions if needed, then run the existing
seven build/lock/doc suites named in ASTRA-FFMPEG-PIN-INTEGRATION-2026-09-09.md
plus applicable existing transcription tests. Use the main guarded ig-native
runner and set IG_FORBIDDEN_LIVE before launching it. Strip paid API keys. No
existing fixture/assertion edits. Write docs/library/GEMINI-TORCHCODEC-DLL-REPAIR-
2026-09-09.md early with exact scope, commands/exits, raw diff and required
independent suites. Preserve any failed/partial attempt. Astra will verify real
TorchCodec decoding of a generated WAV under the repaired installed layout.

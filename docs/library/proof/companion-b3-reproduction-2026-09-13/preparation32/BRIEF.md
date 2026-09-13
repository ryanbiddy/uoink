# B3 real byte-build proposal — 2026-09-13

Prepare only for root review. Worker and root independently passed the same
68 synthetic builder cases with valid guards and actual child/outer exits 0.
The exact B3 builder is `f25530a3…b81892`; its five fixed recipes propose
`faster-whisper 1.2.1+uoink.localassets2`. No actual B3 wheel has been read or
built by this preparation. Its first output hash remains unknown.

The first proposed command uses reviewed Python 3.14.6 `-I -S -B` and fresh
`_scratch/b3-real-wheel-py314-01`. It reads only the already captured upstream
wheel, exactly 1,118,909 bytes, SHA-256
`79a66ad50688c0b794dd501dc340a736992a6342f7f95e5811be60b5224a26a7`.
It copies verified bytes under the expected filename and executes the exact
reviewed stdlib builder with unchanged B3 recipes. As in successful B2, it
checks every output member, complete RECORD, fixed ZIP metadata and unchanged
opaque asset/license bytes. Its actual output identity and exits are recorded.

After root reviews that real result, the second proposed command uses the
already existing `_scratch/b2-stdlib313-runtime01/python.exe`. Revalidate all
34 runtime files and private no-site configuration before and after launch;
never recopy a runtime or launch either original embedded interpreter. The
child checks Python 3.13.15, isolation flags, no `site`, the exact executable
and two private stdlib search paths before wheel access. It repeats the build
in fresh `_scratch/b3-real-wheel-py313-01`, with epoch `2000000000` versus `1`.
Root must supply the first output's observed SHA-256 and size. The launcher
cross-checks its successful receipt and manifest, and the child requires exact
first-wheel identity and byte equality. No expected first hash is invented.

Both children retain the successful B2 stdlib/import/network/process/ctypes/
file guards. Only the packaging utility executes. Package Python sources and
the bundled ONNX member are opaque ZIP bytes for decompression, hash/RECORD
validation and repacking; no model parser, tokenizer, converter, checkpoint,
Hub request, inference, native model package or installer runs. There are no
source/pin/frozen-test/staging edits, downloads or provider calls.

Proposed commands after root pins this preparation seal externally:

```powershell
C:\Python314\python.exe -I -S -B _scratch\b3-real-wheel-preparation01\launch.py py314-01 --manifest-sha256 <reviewed-preparation-sha256> --execute-reviewed-build
C:\Python314\python.exe -I -S -B _scratch\b3-real-wheel-preparation01\launch.py py313-01 --manifest-sha256 <same-reviewed-sha256> --comparison-sha256 <observed-first-wheel-sha256> --comparison-size <observed-first-wheel-bytes> --execute-reviewed-build
```

These commands have not run here. Keep raw exits and failures; any repair/rerun
needs a new brief and label. All prior B2/B3 synthetic evidence remains intact.
Paths must be quiescent: bounded identity checks are not atomic protection
against a hostile same-user process, and ZIP member-count checks follow bounded
central-directory parsing. Packaging reproduction does not accept runtime
migration, the distribution, an installation or market release.

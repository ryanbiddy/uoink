# B2 real-wheel invocation proposal — 2026-09-13

Prepared for root review only. No invocation is authorized by this file. The
proposed action creates an isolated local derivative wheel; it does not install
or execute faster-whisper, interpret a model, or accept a release.

Read the already captured upstream cache body at
`_scratch/python313-graph-01/cache/http-v2/7/5/8/3/f/7583fef67084ddf87aa2564c995bb7778718a460ee10db0da2a67f4b.body`.
Require exactly 1,118,909 bytes and SHA-256
`79a66ad50688c0b794dd501dc340a736992a6342f7f95e5811be60b5224a26a7`.
Copy those bytes exclusively into a fresh run directory under the expected
upstream filename. Invoke only the copied reviewed builder
`ef7189180bc443f7b0b68386b8452d0b57b2be4beca3eee9d81409a7658b4c3f`
and its four fixed recipe inputs. No fetch, resolver, upstream hook, source/pin/
fixture edit, staging write or package installation is in scope.

ZIP decoding will decompress package members, including the existing Silero ONNX
asset, to opaque bytes for RECORD/hash verification and unchanged repacking.
It will not parse the ONNX model, import model/native dependencies, deserialize
checkpoints, convert models, infer, diarize or call a provider. Preserve the
asset bytes exactly. The reviewed builder checks all 16 output members and their
RECORD/manifest identities; the wrapper additionally compares unchanged asset
and license bytes and verifies fixed ZIP metadata/order. Keep raw exits, hashes,
provenance and failures, without substituting a synthetic success.

The first proposed run uses Python 3.14.6 at `C:\Python314\python.exe`. Its child
checks its version and `-I -S -B` flags before wheel access, rejects preloaded
heavy packages, blocks heavy/non-stdlib imports, sockets, subprocess creation
and ctypes loading, and records the guard at exit. The outer launcher scrubs
provider credentials and sets offline flags.

Python 3.13 reproduction remains pending. Historical NLTK receipts name a
staging interpreter with `-I -S -B`, but record no startup flags; its embedded
configuration contains `import site`. Do not infer isolation from those flags
or launch either original embedded interpreter. The separate exact-file plan
proposes a fresh private stdlib runtime with `python313.zip` and `.` only in its
private `_pth`. No runtime copy or interpreter launch occurs in this preparation.

Require quiescent local input/output paths. Capped reads and handle/path identity
checks detect observed changes; they do not establish atomic protection against
a hostile same-user Windows process. ZIP central-directory objects are allocated
before member-count checks, within the bounded/exact-hash input gate. No standalone
asset file is extracted. Output wheels stay in new scratch run directories.

Proposed commands, only after root's review decision:

```powershell
C:\Python314\python.exe -I -S -B _scratch\b2-real-wheel-preparation01\launch.py py314-01 --execute-reviewed-build
```

A later reviewed private Python 3.13 run must compare final wheel bytes with the
first, using a different root and ambient epoch. That comparison has no result
yet. Matching wheels would qualify this packaging recipe only. Frozen lock
changes, native runtime/model qualification, installation and market approval
remain separate. Neither launcher nor real builder has been run in this proposal.

# Python 3.13 integration verdict

Accept the Python 3.13.15 build configuration and 139-package graph, with the
native TorchCodec dependency failure assigned to a repair brief. This is not
complete runtime acceptance or installation credit.

The official Windows archive is 11,009,825 bytes, SHA256
d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf. Astra matched
the download to Python.org's SPDX record and observed a zero-exit Defender scan
with unchanged bytes. A fresh disposable interpreter bootstrapped the exact
build tools, resolved the real direct dependencies and installed them successfully.
Its final inventory, minus the three separate build tools, exactly matches all
139 proposed runtime pins. No retained runtime version changed.

Python 3.13 no longer selects backports.tarfile, importlib-metadata or zipp.
Removing those three pins and notice rows follows the actual dependency graph.
The resolver's --ignore-installed mode selected setuptools 84.0.0, while the
actual build retained its preinstalled 83.0.0; the raw and actual inventories
remain separate. The first collector failed decoding UTF-8 as cp1252 after
pip had exited zero. A separate reader processed the same saved report. No
resolver rerun or fabricated success was needed.

Gemini c7a2ded2 established wheel availability, not complete runtime behavior.
Its raw qualification includes five initial failed package checks, and several
classification examples name free-threaded cp313t wheels. Those examples do not
qualify the normal CPython ABI. Astra's actual resolver selected normal cp313
or compatible wheels. The worker's --no-deps batch could not prove that all 142
packages remain required; the real graph disproved that claim. The report's
proposed inference and ordinary GUI launches are not authorized instructions.
No model, weights, diarization or ordinary helper was run.

Astra authored the bounded pin/lock/doc supplement in the completed worker.
All seven named build/doc/lock suites passed there: 36 in 2.43 seconds. Three-way
integration conflicted where the new Python and existing FFmpeg hashes and
documentation shared lines. Both new native pins were retained. A premature
checkout run reported 36 static passes while conflicts still existed; this
cannot accept the build script and is preserved with that limitation. After
resolution, zero unmerged paths and a real PowerShell parse preceded 36 passes
in 1.95 seconds. No existing acceptance test changed.

The actual Python 3.13 probe has 15 passed / one failed. Pillow, cryptography,
MCP, Pydantic, NumPy, PyAV, PyTorch, TorchAudio, TorchVision, CTranslate2, ONNX
Runtime, Faster-Whisper, CLR, WebView imports and Win32 bindings pass; the
image/tensor/audio operations use generated data only. TorchCodec cannot load
its existing core DLL because a native dependency is absent. Its loader supports
shared FFmpeg versions 4-7; a standalone FFmpeg 8 executable cannot supply them.
One runtime socket-bind attempt was refused and retained; zero-attempt language
would be false. No model inference was performed.

The TorchCodec repair brief requires a compatible patched LGPL shared runtime
and an app-relative loader, with no global DLL search or hidden failure. Gemini
is implementing that bounded repair from e1d81bc. The old failed native probe
stays failed. Proof: proof/ryan-python313-qualification-2026-09-09/SHA256.json.
Preserve package-04; build and measure the replacement after this repair, then
perform the delegated installation and everyday-flow checks.

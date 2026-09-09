# Verification process identity — 2026-09-09

The first isolation verification used the existing private Windows venv.
Its `Scripts/python.exe` is a redirector, so `Popen.pid` names the redirector
while the helper's process identity names the real child. The recorded
90-pass/two-fail observation stays failed; no PID assertion is edited.

For final process checks, Astra prepared `_scratch/ig-native` with unchanged
Python 3.14.6 native executables and runtime DLLs copied from `C:/Python314`.
The private venv configuration still resolves the same standard library and
dependencies. The native executable avoids the redirector, preserving actual
`Popen.pid` identity while retaining the private site-packages guard path.
No global Python installation or user settings were edited.

An actual child probe confirmed Popen PID equals the child's reported PID,
with exit zero. Before using this runtime for product verification, record
binary hashes, prove the inherited guard loads with PYTHONPATH removed, and
check rejection against a disposable canary path. Never probe the real live
index or port 5179 to test the guard. Then rerun the original installer suite
on the unchanged original worker to distinguish the repaired invocation from
the separately rejected product ownership checks. This observation cannot
accept the original installer: seven read-only ownership/configuration
failures and the source review still require the replacement worker.

The final full tree will name this exact runtime, source commit, test counts
and the standing S21 exclusion. Runtime changes do not erase earlier results
or authorize fixture edits. The bundled Python 3.11.9 installed check remains
separate.

Native runtime confirmation on the unchanged first installer worker:
**92 passed, one skipped**, five warnings, 18.81 seconds (`iso-wi2`). The
same original suite still has the separate private-redirector failure record.
Seven ownership/configuration review failures and the source rejection remain.
The native vendor binaries match their original SHA-256 values; inherited
sitecustomize loaded with PYTHONPATH absent and rejected a disposable canary
write. No real live database or port was probed. The native runtime is the
next complete-tree runner; this is distinct from installed bundled Python.

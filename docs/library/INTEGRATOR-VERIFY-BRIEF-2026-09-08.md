# Integrator verification environment repair

The AS-9 full-tree observation on 2026-09-08 remains **failed**: 1,966 passed,
14 failed, three skipped and one existing xfail in 297.24 seconds. It ran the
queue's full-tree command with S21 excluded, plus the still-open AW-3, BA-3,
BA-measurements3 and BD reproduction files excluded. The four AS-7 failures
against superseded evidence were retained. No test assertion was changed.

The other ten failures stopped during child-process imports. Nine mock proof /
induction cases lacked `jsonschema`; the installed-tree smoke could not import
the MCP SDK. Those tests intentionally replace PYTHONPATH or use Python `-I`.
Redirecting APPDATA also changed the user-site directory, so the parent's
resolved package paths did not reach those children. This is not evidence that
their product assertions pass.

Repair the test environment with a disposable virtual environment under this
checkout's scratch directory. Point a local `.pth` file at the already-installed
third-party package directory and its pywin32 subdirectories. Do not install,
upgrade or change global packages. Do not put the source checkout itself in that
file: the installed-tree smoke must continue to prove imports come from its
staged tree. Carry the live-index and port-5179 guard through that environment,
including isolated Python children. Keep all data/profile/output/temp directories
disposable, model calls blocked, bytecode disabled and the API key absent.

First rerun the three affected files: `tests/test_induce_run.py`,
`tests/test_proof_run.py` and `tests/test_installed_library_runtime.py`. Retain
their exact output and counts. Use the repaired environment for later phase and
candidate full-tree runs; record each run separately from the failed observation.
Existing symlink/ffmpeg skips and SEC-06 xfail must remain explicit. Any product
failure after dependency imports work needs its own repair and verification.

The AS-9 confirmation and companion sets ran successfully with the original
environment in both worker and checkout. This repair does not replace those
results, the historical evidence assertions, or Ryan's installed Inno gate.

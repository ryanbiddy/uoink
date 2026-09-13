# Qualification protocol for root review — not admitted or run

The proposed first command uses PowerShell 7 to invoke run_preflight01.ps1
with the exact final INPUT-HASHES.json digest as ExpectedManifestSha256. That
launcher runs only `C:\Python314\python.exe -I -S -B qualify.py qualification01`.
Root must review the final hashes and admit that exact command before a run.
Both launch and child receipt directories refuse reuse.

The scope is 50 planned top-level cases: 27 new builder/loader/refusal contracts
and the unchanged 23 Pipeline cases. Builder bytes are generated in memory from
the 21 enumerated source/metadata text payloads; no wheel is written, installed
or imported. The only generated file outside receipts is the tiny fresh text
fixture used to test overwrite refusal. All model/NPZ/storage reads and real
package imports are prohibited. The builder and verifier main functions and
the captured Pipeline initializer are profile-guarded against execution.

The new source functions use explicit fake array/tensor/constructor/VAD/port
seams; selected function body ASTs are unchanged and only signature annotations
are removed. These tests can establish wiring and refusal order, not numerical
NumPy/Torch behavior, safe imports, model equivalence, decoding, GPU support or
native session lifetime. The inherited CUDA-device seam assertions remain
unchanged as generator mechanics; they grant no GPU runtime approval. The
direct-empty-list observation stays separate and unaccepted.

Before Python startup the launcher binds the exact forbidden-live path string,
disables Torch backend autoload and Pyannote metrics, scrubs provider/proxy/path
variables and sets offline flags. The child asserts isolated/no-site/no-bytecode
startup and no preloaded heavy packages, then installs package/import, file,
network, child-process, database and native-library guards. These are scoped
instrumentation, not an OS sandbox. The 60-second child budget is cooperative;
it is not a hard kernel timeout. Source and manifest bytes are checked before
and after. No live-path filesystem query is needed or allowed.

Before any owned module is compiled, the runner installs fixed-path metadata
and realpath wrappers. Only enumerated text inputs, exact already-loaded stdlib
setup files and named ancestors, and the four named generated paths are allowed.
Directory enumeration is limited to the generated-fixture directory. Source
content closes during behavior and reopens only for posthash. Full same-API
source identities and exact wrapper identities are checked at finish. Setup
and behavior guard refusals remain failures; they do not authorize expansion.

The launcher explicitly sets PSNativeCommandUseErrorActionPreference=false.
Immediately after native return it captures global:LASTEXITCODE without resetting
it and durably records the raw value/type before any postcheck. A null/noninteger
value receives instrumentation exit 99. Each process log is limited to 256 KiB,
stderr must be empty, and the child JSON is limited to 512 KiB. Child PASS requires
exactly 50 actual passes, zero failures/errors/skips/subtests, the exact ordered
EXPECTED-CASES IDs and observations, unchanged inputs and healthy guards. The
launcher independently checks those ordered IDs. A nonzero child or mismatched postcheck
remains failed. Preserve every log, raw exit, partial result and source draft;
do not rerun without a documented diagnosis/repair and a fresh brief.

Actual wheel publication is a separate later admission under Python 3.13. The
builder and independent verifier source are prepared here, but no build is
authorized by synthetic success. A later wrapper must pin the interpreter and
the same manifest, invoke build_wheel.py build01 then verify_wheel.py build01,
and durably capture each actual native exit before postchecks. A fresh output
and unchanged inputs are mandatory; a verifier failure retains the output as
unaccepted. No builder invokes uv, pip, setuptools or dependency resolution.

The retained pyproject tool.uv.sources routes Windows x86_64 to a CUDA index.
It must not govern installation of the CPU-only proposed runtime. Do not use
ordinary uv sync on this proposal. The future approved CPU artifact/source
plan, complete lock and byte identities must govern installation independently.
No source/index, model fetch, real runtime port or owner approval is supplied.

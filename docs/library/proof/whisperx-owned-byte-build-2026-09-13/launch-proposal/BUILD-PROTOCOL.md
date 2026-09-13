# Byte-build protocol awaiting root review — 2026-09-13

Neither script has run. The sole future entry is run_build01.ps1 with the
reviewed INSTRUMENT-HASHES digest, under the observed PowerShell 7 executable.
The launcher checks the frozen 46-input source manifest, its own instruments
and the exact previously retained 34-file private Python 3.13.15 plan. It refuses
existing launch-build01 or source runs/build01 directories.

The child must have exactly the private directory and its python313.zip in
sys.path, with isolated/no-site/no-bytecode startup. It binds the forbidden-live
string, disables Torch backend autoload, and blocks unapproved imports, paths,
network, child processes, database/ctypes access and directory enumeration.
Only exact source text, enumerated private stdlib files and named generated
wheel/receipt paths are allowed. Metadata wrappers check lexical ancestors
before following paths. The same quiescent-directory assumption applies; this
is not a native handle lease or an OS sandbox. The 30-second budget is cooperative.

Mode build invokes only the reviewed builder main. Its output is a stored ZIP
of 21 text payloads plus RECORD. Mode verify invokes the independent manual
byte-layout verifier only after build and guard receipts pass. Neither mode
imports a wheel member or calls dependency resolution. The launcher preserves
each raw global native exit before log/receipt/hash checks, requires bounded
logs and empty stderr, and checks source/runtime identities between modes and
at finish. Failed or partial artifacts remain unaccepted and are not overwritten.

Success requires both native phases and the actual outer tool to return zero,
exact 22-member/22-RECORD-row verification, complete byte-layout agreement,
valid guards and unchanged inputs/runtime. Root must retain the actual outer
tool object separately. This proves packaging only. No model fetching, loading,
installation, native ASR/VAD runtime or release approval follows from it.

The unused prepare_root_qualification.ps1 is superseded by root's completed
independent repeat and is excluded from the executable build manifest. Its
unexecuted draft defect is retained in COPY-PREPARER-SUPERSEDED.md.

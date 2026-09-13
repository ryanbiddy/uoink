# Optional output-directory Hub compatibility repair

Prepare a separate inert source patch on 2026-09-13. The captured
faster-whisper 1.2.1 helper passes `local_dir_use_symlinks=False` when
`output_dir` is supplied; the captured candidate Hub 1.31.0 signature has no
such parameter or catch-all kwargs. Remove only that obsolete assignment.
Retain local_dir, cache_dir, revision, token, local-only policy, model mapping,
allowed filenames and return behavior. This does not implement asset integrity
or containment; those remain the caller's separately reviewed responsibilities.

Use the already captured 4,946-byte utils.py with SHA256
5b36ceb9d0fd3961de8cfb144bd82f9a4ef3151b2e5958405a11efb4f3ac4f82,
and the 31,197-byte Hub source with SHA256
29c2316ec5d0862d0311b0a2cfd97cd39be636042073cef427279b4261893a93.
Do not import either package or run captured Hub code. Extract only its literal
public function signature into inspect.Signature, ignoring annotation and
default expressions. Execute only the reviewed download_model AST with fake
Hub/tqdm seams and stdlib re. Every fake call must bind to the captured signature.

Run identical contract cases on baseline01 and patched01 with fresh receipts.
Exercise explicit output/cache directories, both local-only modes, revision and
token forwarding, mapped and explicit repository IDs, invalid names and helper
error propagation. Baseline API mismatches stay failures. The repair is declared
here before either run; no assertion or fixture changes between those runs.

Use C:\Python314\python.exe -I -S -B and explicit forbidden-live binding. Block
network, processes and model/package imports in the test process. No fetch,
model access, package installation, frozen-test edit or wheel build. B2's existing
wheel and seals remain unchanged. Independent review must precede any combined
derivative or integration decision. This is an optional-call compatibility
check, not native runtime, security or release acceptance.

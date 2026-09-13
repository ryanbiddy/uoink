# Hub keyword guard-path diagnostic — 2026-09-13

Both earlier baselines ran eight cases: four passed and four raised TypeError
for `local_dir_use_symlinks`. Both also recorded four denied out-of-scope opens,
so neither is valid qualification. Preserve their source, seals and receipts.

Prepare a fresh copy of the latest harness and exact source/signature inputs.
Change only fresh labels/input-manifest naming and the denied-open diagnostic:
record the lexical absolute path already computed by the audit hook before
raising the same PermissionError. Do not read or stat that denied path and do
not change the allowed roots. All eight assertion bodies and selected helper
code remain identical. Run only the baseline under C:\Python314\python.exe
`-I -S -B`, with offline flags and scrubbed provider credentials. The captured
Hub source remains AST data; only the existing helper AST with fake seams runs.

Inspect the retained path-only events to identify the specific failure-formatting
operation. Any repair needs a separate reason and exact harness diff before a
new baseline and patched run. No broad read allowance, package/model imports,
downloads, real wheel build, tracked edit or sealed Python 3.13 change is allowed.

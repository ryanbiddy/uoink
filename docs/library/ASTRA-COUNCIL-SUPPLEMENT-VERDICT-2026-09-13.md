# Council supplement verdict

Accept Gemini's three component verdicts with the corrections below. Run
`ca1e1356-b943-4a8a-bee4-6a3016a7ee64` reviewed notice packaging, generated worker
operations and the actual proposed adapter connection from `8a81250`. It finished
at 23:44:12.448Z on September 13; root tool `3b847e` returned exit 0. The original
report at `870fa00` remains partial. This separate supplement supplies additional
review; it does not change that historical result.

Root read the complete supplement in `6e34fd`, checked the cited source sections
in `78d1cc` and `42d4ad`, and independently verified all 69 selected input files
in both checkouts: 716,129 bytes per root (`54217e`). The worker's sole diff was
exported and applied with `git apply --3way` in `517b80`. The applied normalized
text matches, and exact worker bytes were restored. No executable suite was
assigned or rerun for this documentary review.

The retained activity records access to all 39 previously omitted paths. It
contains 55 completed views, one report write and one failed coverage-index view.
View records contain paths and file-size summaries, without displayed source
bodies or requested line ranges. The worker's full-file claims therefore remain
its assertions. Its explicit Inno boundary is lines 1–150, including the notice
entries; lines 151–1898 remain unread by this supplement. Root accepts that
boundary for notice staging, with no review credit for the remaining installer.

The supplement correctly limits fixed notice hashes to the two upstream license
files and fixes the build/Inno references. Three qualifications remain:

- Its phrase "strict sandboxing" overstates the observed boundary. Fixed API
  dispatch, Python traps, retained handles and job accounting are not a complete
  Windows sandbox or a native-loader audit. The pending-I/O finalizer calls
  `os._exit(1)` on uncertainty; that is a fail-closed action, not a new successful
  cancellation or quiescence observation.
- A nonzero generator exit reaches cleanup and fails the build. A native
  invocation exception still unwinds the environment/preference `finally`
  blocks and fails, but can skip the later uninstall command. Preserve that
  distinction from the earlier Astra verdict.
- `OwnedSession.close_and_join()` establishes `NATIVE_STOPPED` through the fixed
  port's shutdown checks. `lease.confirm_native_closed()` then changes that state
  to `NATIVE_CLOSED`. Neither method alone supplies every shutdown observation.

No new product defect follows from this supplement. The original measured case
counts remain unchanged. No new signature, legal warranty or approval requirement
is introduced. Real model loading, durable Windows recovery, current-source
complete tests, signing and isolated installation remain release work. Website
and marketing remain paused until the council and integrator accept the product.

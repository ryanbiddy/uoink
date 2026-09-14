# Windows reservation source and first-run admission

2026-09-13. Astra admits one generated-only run under the existing authorization for isolated source qualification. This is an integrator decision; it does not admit native model or Windows execution.

The 28-file PINS digest is `4f5cd502c563f7dc23b3be81bffd93429eea8c30434e56da96b4d49f5cc42ee7`. The launcher is `7a5b5b23c7dc3d8efd9d016b478d79e508ebc043de00e8a866de16490baa6094`, and the qualifier is `8581cdfda702991777392f00bd91882db97c5d339023f6418de8b918fe1e22d5`. Exact membership is 42 retained cases and 23 new cases; nested subtests are reported separately.

Root reviewed the concrete port, durable startup split, adapter migration, no-worker retirement, changed test setup and new controls. Earlier source reviews and preserved refinements cover cached-confirmation poisoning, avoiding journal I/O under the state lock, one forced-stop attempt and cleanup when worker startup never began. The no-worker witness requires actual read-set retirement and makes no child-exit claim. Peer review reported no remaining actionable source finding in the frozen functional changes. The final adapter-flow change is comment wording only.

Root read the complete protocol, API note, no-worker note, launcher and qualifier in `2b4a6f` and `668b47`; the current fake fixture prefix, pins and exact case membership in `d02ec1`; the port controls in `492fa2` supplement earlier full source reads. These reads support review, not execution credit. The combined reference read in `668b47` truncated prose; its qualifier output was complete. A shell glob used during import inspection failed in `0c7129`; no qualification was attempted by that read command.

The child uses C:\Python314\python.exe with `-I -S -B`, with the forbidden live path set lexically before startup. It captures 19 fixed inputs, then closes content reads and runs 17 reviewed modules from those bytes. The known baseline winreg module has callable traps; metadata and import guards retain their prior limits. No ctypes, network, process, native service or model library is installed. The launcher verifies original and copied inputs and controls before and after execution, preserves native exit immediately, and validates all ten guards, exact case membership and bounded output. This constrains the reviewed process; it is not an OS sandbox.

Preserve any failure and stop. No retry is admitted by this record. Actual Windows exclusion, flush behavior, crash recovery, native model correctness and installed readiness remain unmeasured here.

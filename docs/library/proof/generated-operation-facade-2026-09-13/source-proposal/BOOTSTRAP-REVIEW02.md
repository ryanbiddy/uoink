# Bootstrap interface correction, 2026-09-13

A static inventory of the existing bootstrap's `FLOW` attributes found one missing export in draft `2e80a244`: bootstrap line 250 calls `FLOW.declare_exit_call` before constructing the port. Re-export the exact unchanged function from `generated_worker_flow`. This declares the already-admitted `GetExitCodeProcess` prototype; it adds no native symbol or source behavior. No candidate or native code was executed.

Preserve the previous candidate, source bindings and first repair diff under `before-bootstrap-review02`. The final preparation will bind the corrected module and all four bootstrap-facing names: `declare_exit_call`, `GeneratedLifecyclePort`, `controller_flow` and `child_flow`.

# First stable-handle attempt

The 39-pass baseline lacked retained discovered-child handles. This repair
holds parent and child process objects through a final relationship snapshot,
uses full FILETIME ordering, retains verified handles for mutation, and adds
pending-discovery cancellation cleanup. Borrowed Popen handles retain their
owner object. Session mutations no longer reopen a PID without a retained
owned identity. The accepted owner reserve/attach/sweep implementation remains.

Four uncommitted synthetic modules gain only an import of
`_mirror_stable_native_fixture.stable_native_authority`. That fixture adapts
their existing inert PID/liveness observations to explicit synthetic handles.
The four baseline files are retained; no behavior assertions were edited.
Five additional tests exercise the native mechanism with a fake Windows handle
lifetime model, including refusing PID reuse while any original handle exists.

An initial multi-hunk apply_patch command was refused because its expected
termination-loop context differed from the parent's narrow repair. It did not
apply. The edit was split into matching hunks before this first test run.

Run label: `astra-authority-repair03-01`. This is a first execution, not a
repeat of the 39-pass measurement. No result is claimed before execution.

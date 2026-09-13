# Reporting-only repair verdict

The revised reader passed 45 synthetic/static checks with real process exit 0
in `static-reporting-preflight01`, using `-I -S -B`. It is ready for the
integrator to review; no further actual checkpoint inspection was performed.

Reader SHA256:
`17545bb938104e88eacba85978ab353b41e78df55c13ec6214a564d0fbf351fc`.

The original 36 synthetic cases remain unchanged. Six new cases require exact
numeric refusal details for unsupported needed versions 0, 9 and 46, a split
disk, an excessive filename length, and a directory-entry extent conflict.
Three AST comparisons confirm unchanged refusal predicates/messages,
top-level constants/fixed paths, and file-read expressions against the
preserved executed reader. These checks validate reporting behavior; they do
not approve additional ZIP versions or establish actual artifact compatibility.

The repair attaches 14 bounded integer header values under
`refusal_context.zip_directory_entry` when a decoded central-directory entry
fails the existing compatibility, metadata-size or extent checks. The same
checks still refuse, and exit 2 is unchanged. It adds no member-name output,
extra artifact read, format relaxation, model import, object construction or
loading fallback. The receipt root remains the original proposal's `results`
directory; the integrator must choose a fresh run ID for any later execution.

The original `run01` remains **refused**, reader exit 2, before pickle
inventory. Its recorded hash is
`0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`
over 17,719,103 bytes. The enclosing exec exit 1 is recorded as reported by
the integrator, separately from the launcher's measured reader exit 2.
Neither outcome is a pass. No actual header values beyond that existing
receipt are known from this repair task.

The original 27-payload seal and its reader remain untouched and were copied
after verifying every recorded payload hash. `preserved-run01` contains the
refused receipt, root launcher and all four launch logs. This new seal also
contains the before/after source, exact diffs, repair brief, synthetic stdout,
stderr and exit record. It includes no checkpoint bytes.

Only the integrator may perform the next reviewed static inspection. Numeric
metadata may inform a compatibility proposal, but this work cannot authorize
deserialization, a fixed model architecture, tensor loading, conversion,
inference, downloads, frozen-stack changes or release acceptance. No product
or frozen-test changes, actual artifact reads, reader-main execution, model
or provider actions, installation, staging, commit or push occurred here.

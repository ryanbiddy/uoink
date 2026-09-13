# Startup-binding qualification repair

The reviewer confirmed the recorded outcomes: preflight01 is 56 passed and
1 failed; preflight02 is 57 passed and 0 failed. Both launchers invoked
isolated Python with `-I -S -B`, and the harness installed its own audit
refusals before importing the tracer. Neither launcher explicitly set or
recorded `IG_FORBIDDEN_LIVE`. The exact outer invocations did not set it
either. A later shell check found it absent, which cannot reconstruct any
earlier process environment. Do not claim inherited startup binding or
qualified native startup protection from those two runs.

Preserve both attempts unchanged. For fresh `symbolic-preflight03`, set
the known forbidden-live path as an environment string before launching
Python. In the child harness, assert exact string equality without opening,
resolving or probing that path. Record a boolean for this assertion in the
raw result and the explicit binding in the launcher receipt. Keep all 57
behavioral cases and the tracer source unchanged; archive the exact setup
and launcher diffs before execution. No native gate test, product suite,
model, database or artifact operation is added.

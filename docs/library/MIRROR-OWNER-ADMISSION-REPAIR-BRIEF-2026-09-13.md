# Preserve writer admission through session attachment

The controlled admission01 probe on b62aab3 fails once: a normal owner sweep
releases the new gate between acquisition and session attachment. The prepared
session then returns with launching=true and held=false. Kernel acquire/release
are inert recorders; no process launches. The original probe, result and event
log are preserved under proof/mirror-owner-admission01-2026-09-13. This is a
confirmed race, but does not establish the cause of tree08's fifty failures.

Astra owns this bounded product repair in a separate Git worktree. Reserve a
new or context-reused owner before exposing it to the caller. Transfer that
reservation to the attached session, and release it on every failed preparation.
Serialize reservation, attachment and the decision to stop an owner so that a
stale sweep cannot release newly admitted work. A stopping owner must refuse
attachment and reuse. Do not hold the global guard while waiting for the kernel
mutex or for the owner thread to exit. Preserve unknown-child retention and
same-operation context reuse; foreign callers still need kernel admission.

Add new controlled cases for the reproduced handoff, preparation failure,
reservation acquired during a stale sweep, attachment during a stale sweep,
stopping-owner refusal, cancellation before launch and retention of an unknown
child. Use inert kernel gates for these cases. Existing product tests and
fixtures are frozen. Run the new cases, the unchanged original diagnostic, and
all tests/test_phase4*.py plus tests/library_work_astra/test_phase4*.py in the
worktree. Preserve every attempt with a fresh label. A failing attempt requires
a documented cause and repair before another run. Run the same suites in the
checkout after applying the raw binary Git diff with git apply --3way, then
record a one-page review verdict and commit. No full-tree rerun or installer
build until the other confirmed process-authority findings are resolved.

Gemini run 213914a5 is independently reviewing inert process-identity boundaries
from MIRROR-TREE08-REPAIR-BRIEF-2026-09-13.md. It owns no production edits. Keep
its diagnosis separate and independently verify its claims. Neither assignment
authorizes live-index access, port 5179, model execution, new fetch, paid API,
existing-test edits, main merge, website work or marketing.

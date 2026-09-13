# Relative-script path diagnostic before attempt 02

Diagnostic01 used an absolute script argument with the diagnostic directory as
cwd. Its unchanged eight contracts yielded four passes and four expected API
TypeErrors, with guard valid and no denied paths. Retain this as a nonreproduction
of the earlier guard events, not a passing product result.

Root supplied the exact earlier invocation: Python 3.14 `-I -S -B`, repository
checkout cwd, and a relative `_scratch/.../qualify.py` script argument. Prepare
another fresh path-diagnostic source with identical assertions and read policy.
Change labels only, then launch with that same cwd/relative-script convention.
Keep path-only diagnostics; reject every denied open without reading or statting
it. Retain offline flags and environment scrubbing. No patched source run yet.

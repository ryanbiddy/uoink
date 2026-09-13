# Source-free error receipts before baseline03 and patched03

The exact root launch convention was reproduced in diagnostic02: relative
script argument, checkout cwd, eight unchanged cases, four passes/four API
TypeErrors, and four guard denials for the lexical path
`E:\AI\projects\uoink\checkouts\Yoink-library\<unknown>`.
The hook recorded the path before raising PermissionError; it did not open
or stat it. Diagnostic01, using an absolute script and its own directory cwd,
did not reproduce the guard event. Both diagnostics and both original failed
guard runs are retained unchanged.

The failure is in error-report source lookup. Python 3.14's traceback formatter
calls `ast.parse` at traceback.py:714 and :841; ast.py:26 uses `<unknown>` as
the default filename. This is a source-based lead for the sentinel's origin,
not a separately instrumented proof of the complete internal call stack.
The measured denied pathname itself is exact.

Repair only the harness's unittest result formatter. `_exc_info_to_string`
will render exception type/message and traceback frame file/line/function
fields directly, without source lookup, locals or captured values. Keep the
same exception instances and unittest success/error/failure accounting. Do not
change the read allowlist, helper AST, fake seams, signature or eight assertion
bodies. Preserve an exact formatter diff and compare the Contracts class AST.

Run baseline03 with the original relative-script/check-out-cwd convention under
the existing isolated, offline stdlib guard. If it yields the expected four
passes/four obsolete-keyword TypeErrors with a valid guard, run the identical
protocol once as patched03 against the existing one-line product patch.
Retain actual exits and all failures. No retries without a new repair brief.

Captured Hub code remains inert AST data. No package/model imports, model
assets, downloads, real builds, tracked files or sealed Python 3.13 inputs are
in scope. Qualification concerns optional argument forwarding only.

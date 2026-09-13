# Static audit startup refusal

The first static AST-audit launch exited 1 before the script opened. Its
interpreter's existing sitecustomize guard required IG_FORBIDDEN_LIVE, which
this separate command had not set. The traceback ended with
`KeyError: 'IG_FORBIDDEN_LIVE'`. No AST audit or test ran in that launch.

Repair: set the same guard variable, offline flags and scrubbed process
environment used by the successful test commands. The next static audit is
attempt02 and its output is retained separately. Product code and all tests
stay unchanged. This startup refusal does not alter the three test results.

# Adapter static-check setup repair

`adapter-preflight01` remains failed: 23 passed, 1 failed, actual qualification
exit 1 in 0.056542 seconds. Its source, harness, raw result and receipt are
preserved. All behavior cases and exact permitted AST composition passed.

The failing new generic call audit matched every function attribute named
`compile`, including the unchanged reader's `re.compile` of its fixed
IDENTIFIER regular expression. That is regex construction, not Python code
compilation or model-target execution. The exact AST comparison already
requires that expression to remain identical to the reviewed reader.

Before fresh `adapter-preflight02`, exempt only an AST call whose function
is `Attribute(Name('re'), 'compile')` from the generic prohibited-name test.
Keep builtin compile, other qualified compile targets, dynamic imports and
loader calls prohibited, and keep the exact baseline AST check unchanged.
Preserve the before/after harness diff. No adapter source, tracer behavior,
accepted tests, artifact access or bound changes are made. Rerun the same
24 synthetic cases with the explicit startup binding and audit guards.

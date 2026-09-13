# Qualification receipt-path repair before baseline02 and patched02

Baseline01 returned exit one: eight cases ran, four passed and four errored.
The guard also refused four out-of-scope opens during failure formatting,
so this is an invalid-guard attempt, not accepted baseline qualification.
Keep its log, result, outer exit, original harness and input seal unchanged.

The extracted function was compiled under a synthetic filename. Bind that
compile filename to the already copied, hash-checked source file inside the
test directory so traceback source lookup has the correct contained origin.
Do not expand the file allowlist. Function code and all eight assertions stay
unchanged. Use fresh labels baseline02 and patched02; retain the source diff
and new input seal. If unexpected guard events remain, stop and investigate.

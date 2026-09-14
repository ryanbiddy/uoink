# Source-order check correction

Passive check f6f2e1 exited 1 before producing final bindings because it incorrectly required the test module's definition order to match the supplied qualification order. Diagnostic b1c99a shows the same six methods: the reentrant case is last in source and fourth in the supplied alphabetical list. The test author confirmed this distinction.

The qualifier explicitly selects the fixed EXPECTED list with the accepted module-relative loader. Source declaration order is not its execution-order contract. The corrected passive check compares exact six-method membership separately, retains both sequences, and leaves the qualifier, expected list, test source and assertions unchanged. A future actual run must still report the exact EXPECTED order. These are text-check outcomes, with no candidate or Python startup.

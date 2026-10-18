# Exact metadata graph diagnostic

Astra's first full metadata-edge traversal stopped at CTranslate2's declared
setuptools dependency, which the existing build removes. This was a failed
diagnostic, not a successful closed-graph result. No output file was written
before its assertion; the command output records:
AssertionError: ('ctranslate2', 'setuptools').

The worker's checks of the two changed packages do not establish closure of all
139 distributions. Run a second diagnostic that collects every unsatisfied edge
instead of stopping at the first, preserving the first result. Evaluate the
changed Lightning edges separately from the preexisting inventory. Do not
silently add a package, edit acceptance tests or claim the full graph is closed.
The replacement runtime still needs its own package validation and scan.

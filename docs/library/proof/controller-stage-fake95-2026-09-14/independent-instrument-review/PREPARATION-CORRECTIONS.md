# Reviewer preparation corrections

The first frozen-control read (6cf628, outer exit 0) guessed `qualify_windows_reservations.diff` and `run_preflight01.diff`. Those names were absent. The inventory supplied the actual names, `qualify_windows_reservations.py.diff` and `run_preflight01.ps1.diff`; 30b011 read both complete files. The initial read and its errors are retained.

The first independent passive checker (8e5115, exit 1) counted quoted names through the subsequent module-execution line, including its literal `"exec"`. Its 38-capture assertion therefore failed. The original checker is preserved as `check_instrument01-before.ps1`. The sole executed-check correction ends the parsed region at `) for method in methods)`. Corrected check 79a326 exited 0; a separate copy check b8bb17 also confirms the original 36 names are the exact prefix of the 38 current captures.

These are reviewer data/read diagnostics. Neither command invoked the candidate qualifier, tests or launcher. No author source or assertion changed.

The full map/brief display 62ecf4 was observed but its complete tool object was not retained. It is not reconstructed here. The saved checker actuals independently bind those current map bytes and their selected source copies.


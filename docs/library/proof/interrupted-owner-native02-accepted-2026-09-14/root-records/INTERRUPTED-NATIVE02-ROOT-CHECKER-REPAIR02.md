The first passive checker failed as bbc2c5 at its saved source-pair lookup.
It used PowerShell's automatic `$input` variable inside `Where-Object`.
Diagnosis cce7c5 shows the exact first saved pair agrees, but that lookup returns
all 32 rows; using a dedicated `$taskInputRow` returns the required one row.

The second checker changes only that variable name throughout the two added
loops. Every comparison and subject receipt remains unchanged. Preserve the
first source, failure and diagnosis. This is a passive checker repair and fresh
check label, not a repeat of the native observation or a product/test change.

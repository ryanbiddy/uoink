# Compact map preparation repair

The first compact-map writer failed before writing INPUT-SELECTION.json because its final map expression used bare false instead of PowerShell's $false. Actual 5ae907 exited1 and is preserved. The passive excerpt had already been produced successfully by separate actual802993; it was not recreated.

The corrected data-only writer uses $false, preserves the prior selection and excerpt, and writes the fresh compact map. Actual bc71ff exited0: 48 files,480562 bytes,9372 lines. This is preparation bookkeeping, not a product test or native result. Earlier proposal01's two metadata/display errors and their actual receipts remain in that directory; no original proof changed.

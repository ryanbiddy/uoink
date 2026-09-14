# Line-count convention correction — 2026-09-13

Map preparation f0aa4a exited 1 before writing INPUT-SELECTION.json. It compared the original catalog's LF-split count with PowerShell ReadAllLines, which omits the final empty slot. The resulting “selected input changed: A-01” error was an instrument conclusion, not evidence that source changed.

Read-only diagnostic 41522e exited 0: A-01 has the exact expected 29,660 bytes and SHA-256, ends in LF, and gives 589 LF-split slots versus 588 ReadAllLines entries. The output map did not exist. Both actual tool objects are preserved unchanged.

The corrected preparation uses the original UTF-8/LF-split convention and states it in the map. It preserves the five original IDs, paths, sizes, hashes and catalog counts. The brief calls these catalog slots rather than substantive source lines. Coverage must record actually viewed ranges; an unrendered terminal empty slot is not read evidence. No test, candidate source or accepted fixture changed, and no execution measurement is repeated.

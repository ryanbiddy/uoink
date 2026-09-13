2026-09-13. Before any sealer execution, root requested an explicit character
overload for Windows separator normalization. Replace string-literal separator
arguments with `.Replace([char]92,[char]47)` in the sealer and verifier. This
avoids confusing PowerShell's literal backslashes with language escape syntax.
The original unexecuted scripts are retained under drafts/path-normalization01.

SOURCE-MAP.json already uses forward slashes in every relative path and remains
unchanged. The 207 source files and their three source directories remain frozen.
The proof now includes this note and both original script drafts as three extra
payloads: 217 payloads plus the final manifest. This is an instrument preparation
correction, not a test/source change or a rerun. No sealer has executed.
